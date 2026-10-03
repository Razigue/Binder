"""Document routes: upload, list, edit, trash, archives, files, export, expiry and retention."""

import io
import json
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlmodel import Session, col, select

from binder import i18n
from binder.agent import tools
from binder.api.assistant import undoable
from binder.api.common import (
    ACTIVE,
    SessionDep,
    disposition,
    document_or_404,
    safe_filename,
    selected,
)
from binder.db import WITHOUT_TEXT, in_use
from binder.models import Category, Document, DocumentStatus
from binder.schemas import (
    BulkPurge,
    BulkResult,
    BulkUpdate,
    DocumentDetail,
    DocumentIds,
    DocumentOut,
    DocumentUpdate,
    ExpirationOut,
)
from binder.services import activity, archive, deadlines, editing, explain, ingest, organize
from binder.services.text import render_page

router = APIRouter(prefix="/api")
MAX_UPLOAD = 25 * 1024 * 1024
BATCH = re.compile(r"[A-Za-z0-9_-]{1,64}")

T = i18n.catalog(
    "api",
    {
        # HTTP errors shown to the user.
        "file_too_large": {
            "en": "File too large (25 MB maximum)",
            "fr": "Fichier trop volumineux (25 Mo maximum)",
        },
        "file_empty": {"en": "Empty file", "fr": "Fichier vide"},
        "not_in_trash": {
            "en": "This document is not in the trash",
            "fr": "Ce document n'est pas à la corbeille",
        },
        "trash_first": {
            "en": "Move the document to the trash first",
            "fr": "Mettez d'abord le document à la corbeille",
        },
        "confirm_purge": {
            "en": "Permanent deletion: confirmation required (confirm=true)",
            "fr": "Suppression définitive : confirmation requise (confirm=true)",
        },
        # Activity log.
        "reanalyze": {
            "en": "New analysis of “{title}” requested",
            "fr": "Nouvelle analyse de « {title} » demandée",
        },
        "bulk_trashed_one": {
            "en": "{n} document moved to the trash",
            "fr": "{n} document mis à la corbeille",
        },
        "bulk_trashed_other": {
            "en": "{n} documents moved to the trash",
            "fr": "{n} documents mis à la corbeille",
        },
        "bulk_updated_one": {"en": "{n} document updated", "fr": "{n} document modifié"},
        "bulk_updated_other": {"en": "{n} documents updated", "fr": "{n} documents modifiés"},
        "bulk_archived_one": {"en": "{n} document archived", "fr": "{n} document archivé"},
        "bulk_archived_other": {"en": "{n} documents archived", "fr": "{n} documents archivés"},
        "bulk_unarchived_one": {
            "en": "{n} document back from the archives",
            "fr": "{n} document sorti des archives",
        },
        "bulk_unarchived_other": {
            "en": "{n} documents back from the archives",
            "fr": "{n} documents sortis des archives",
        },
        "bulk_restored_one": {"en": "{n} document restored", "fr": "{n} document restauré"},
        "bulk_restored_other": {
            "en": "{n} documents restored",
            "fr": "{n} documents restaurés",
        },
        "bulk_purged_one": {
            "en": "{n} document permanently deleted",
            "fr": "{n} document supprimé définitivement",
        },
        "bulk_purged_other": {
            "en": "{n} documents permanently deleted",
            "fr": "{n} documents supprimés définitivement",
        },
        "bulk_reanalyze_one": {
            "en": "New analysis of {n} document started",
            "fr": "Nouvelle analyse de {n} document lancée",
        },
        "bulk_reanalyze_other": {
            "en": "New analysis of {n} documents started",
            "fr": "Nouvelle analyse de {n} documents lancée",
        },
        "export_one": {"en": "Exported {n} document", "fr": "Export de {n} document"},
        "export_other": {"en": "Exported {n} documents", "fr": "Export de {n} documents"},
        "export_category_one": {
            "en": "Exported {n} document ({category:category})",
            "fr": "Export de {n} document ({category:category})",
        },
        "export_category_other": {
            "en": "Exported {n} documents ({category:category})",
            "fr": "Export de {n} documents ({category:category})",
        },
        # Exported archives.
        "archive_all": {"en": "documents", "fr": "dossier"},
    },
)


def _detail(session: Session, doc: Document) -> DocumentDetail:
    """The document as saved, after a change committed by the route."""
    session.refresh(doc)
    return DocumentDetail.from_model(doc)


@router.post("/documents", status_code=201)
def upload(
    file: UploadFile,
    background: BackgroundTasks,
    session: SessionDep,
    batch: str | None = None,
) -> DocumentOut:
    """`batch`: chosen by the interface for one drop of files (the import report groups them)."""
    # A plain function, run in the thread pool: encrypting and storing must not block the event
    # loop (the multipart body is already spooled, reading it here does not wait on the client).
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, T("file_too_large"))
    if not data:
        raise HTTPException(400, T("file_empty"))
    try:
        mime = ingest.guess_mime(file.filename or "document", file.content_type)
    except ingest.UnsupportedFile as exc:
        raise HTTPException(415, str(exc)) from exc
    if batch is not None and not BATCH.fullmatch(batch):
        batch = None
    doc, created = ingest.store(
        session,
        data,
        file.filename or "document",
        mime,
        batch=f"upload-{batch}" if batch else ingest.new_batch("upload"),
    )
    if created and doc.id is not None:
        background.add_task(ingest.analyze_in_background, doc.id)
    return DocumentOut.from_model(doc)


@router.get("/documents")
def list_documents(
    session: SessionDep,
    q: str | None = None,
    category: Category | None = None,
    status: DocumentStatus | None = None,
    archived: bool = False,
    limit: Annotated[int, Query(le=500)] = 100,
) -> list[DocumentOut]:
    """Documents of the active views, or with `archived` those of the archives."""
    if q:
        result = tools.search_documents(
            session, q, category.value if category else None, limit=limit, archived=archived
        )
        docs = result.documents
        if status:
            docs = [d for d in docs if d.status == status]
    else:
        stmt = select(Document).options(*WITHOUT_TEXT)
        if archived:
            stmt = stmt.where(ACTIVE, col(Document.archived_at).is_not(None))
        else:
            stmt = stmt.where(in_use())
        if category:
            stmt = stmt.where(Document.category == category)
        if status:
            stmt = stmt.where(Document.status == status)
        docs = list(session.exec(stmt.order_by(col(Document.created_at).desc()).limit(limit)))
    return [DocumentOut.from_model(d) for d in docs]


# Grouped actions on the documents selected in a list: one request, one "Undo" for all of
# them. Ids that are unknown (or not in the expected place) are skipped.
# Declared before /documents/{doc_id}/...: "bulk" would be taken for a document id.


@router.post("/documents/bulk/trash")
def bulk_trash(body: DocumentIds, session: SessionDep, response: Response) -> BulkResult:
    docs = selected(session, body.ids)
    with undoable(session, response):
        for doc in docs:
            ingest.trash(session, doc)
    session.commit()
    return BulkResult(count=len(docs), message=T.plural("bulk_trashed", len(docs)))


@router.post("/documents/bulk/update")
def bulk_update(body: BulkUpdate, session: SessionDep, response: Response) -> BulkResult:
    changes = body.model_dump(exclude_unset=True, exclude={"ids", "validated"})
    changes = {k: v for k, v in changes.items() if v is not None}
    docs = selected(session, body.ids)
    with undoable(session, response):
        for doc in docs:
            editing.update_document(session, doc, changes, validated=bool(body.validated))
    session.commit()
    return BulkResult(count=len(docs), message=T.plural("bulk_updated", len(docs)))


@router.post("/documents/bulk/reanalyze", status_code=202)
def bulk_reanalyze(
    body: DocumentIds, session: SessionDep, background: BackgroundTasks
) -> BulkResult:
    """Read again in the background, one after the other, like a fresh import."""
    docs = [d for d in selected(session, body.ids) if d.status != DocumentStatus.PROCESSING]
    for doc in docs:
        activity.log(
            session, "reanalyze", T.msg("reanalyze", title=doc.title), actor="user", document=doc
        )
        doc.status = DocumentStatus.PROCESSING
        session.add(doc)
    session.commit()
    ids = [d.id for d in docs if d.id is not None]
    background.add_task(_analyze_all, ids)
    return BulkResult(count=len(ids), message=T.plural("bulk_reanalyze", len(ids)))


def _analyze_all(ids: list[int]) -> None:
    for doc_id in ids:
        ingest.analyze_in_background(doc_id)


@router.post("/documents/bulk/archive")
def bulk_archive(body: DocumentIds, session: SessionDep, response: Response) -> BulkResult:
    docs = selected(session, body.ids)
    with undoable(session, response):
        count = sum(archive.archive(session, doc) for doc in docs)
    session.commit()
    return BulkResult(count=count, message=T.plural("bulk_archived", count))


@router.post("/archives/restore")
def bulk_unarchive(body: DocumentIds, session: SessionDep, response: Response) -> BulkResult:
    docs = selected(session, body.ids)
    with undoable(session, response):
        count = sum(archive.unarchive(session, doc) for doc in docs)
    session.commit()
    return BulkResult(count=count, message=T.plural("bulk_unarchived", count))


@router.post("/trash/restore")
def bulk_restore(body: DocumentIds, session: SessionDep, response: Response) -> BulkResult:
    docs = selected(session, body.ids, trashed=True)
    with undoable(session, response):
        for doc in docs:
            ingest.restore(session, doc)
    session.commit()
    return BulkResult(count=len(docs), message=T.plural("bulk_restored", len(docs)))


@router.post("/trash/purge")
def bulk_purge(body: BulkPurge, session: SessionDep) -> BulkResult:
    """Permanent deletion of documents already in the trash: requires `confirm`."""
    if not body.confirm:
        raise HTTPException(428, T("confirm_purge"))
    docs = selected(session, body.ids, trashed=True)
    for doc in docs:
        ingest.purge(session, doc)
    session.commit()
    return BulkResult(count=len(docs), message=T.plural("bulk_purged", len(docs)))


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, session: SessionDep) -> DocumentDetail:
    return DocumentDetail.from_model(document_or_404(session, doc_id))


@router.patch("/documents/{doc_id}")
def update_document(
    doc_id: int, patch: DocumentUpdate, session: SessionDep, response: Response
) -> DocumentDetail:
    doc = document_or_404(session, doc_id)
    changes = patch.model_dump(exclude_unset=True)
    validated = bool(changes.pop("validated", False))
    with undoable(session, response):
        editing.update_document(session, doc, changes, validated=validated)
    session.commit()
    return _detail(session, doc)


@router.post("/documents/{doc_id}/reanalyze")
def reanalyze(doc_id: int, session: SessionDep) -> DocumentDetail:
    doc = document_or_404(session, doc_id)
    activity.log(
        session, "reanalyze", T.msg("reanalyze", title=doc.title), actor="user", document=doc
    )
    return DocumentDetail.from_model(ingest.analyze(session, doc))


@router.get("/documents/{doc_id}/explanation")
def explain_document(
    doc_id: int, session: SessionDep, refresh: bool = False
) -> explain.Explanation:
    """Plain-language explanation and actions to take (cached on the document)."""
    result = explain.get(session, document_or_404(session, doc_id), refresh=refresh)
    session.commit()
    return result


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, session: SessionDep, response: Response) -> None:
    """Moves the document to the trash (reversible)."""
    doc = document_or_404(session, doc_id)
    with undoable(session, response):
        ingest.trash(session, doc)
    session.commit()


@router.post("/documents/{doc_id}/archive")
def archive_document(doc_id: int, session: SessionDep, response: Response) -> DocumentDetail:
    """Moves the document to the archives: out of the active views, still readable."""
    doc = document_or_404(session, doc_id)
    with undoable(session, response):
        archive.archive(session, doc)
    session.commit()
    return _detail(session, doc)


@router.post("/documents/{doc_id}/unarchive")
def unarchive_document(doc_id: int, session: SessionDep, response: Response) -> DocumentDetail:
    doc = document_or_404(session, doc_id)
    with undoable(session, response):
        archive.unarchive(session, doc)
    session.commit()
    return _detail(session, doc)


@router.get("/trash")
def list_trash(session: SessionDep) -> list[DocumentOut]:
    docs = session.exec(
        select(Document)
        .options(*WITHOUT_TEXT)
        .where(~ACTIVE)
        .order_by(col(Document.deleted_at).desc())
    )
    return [DocumentOut.from_model(d) for d in docs]


@router.post("/documents/{doc_id}/restore")
def restore_document(doc_id: int, session: SessionDep, response: Response) -> DocumentDetail:
    doc = document_or_404(session, doc_id, trashed=True)
    if doc.deleted_at is None:
        raise HTTPException(409, T("not_in_trash"))
    with undoable(session, response):
        ingest.restore(session, doc)
    session.commit()
    return _detail(session, doc)


@router.delete("/documents/{doc_id}/purge", status_code=204)
def purge_document(doc_id: int, session: SessionDep, confirm: bool = False) -> None:
    """Permanent deletion: requires a document in the trash and `confirm=true`."""
    doc = document_or_404(session, doc_id, trashed=True)
    if doc.deleted_at is None:
        raise HTTPException(409, T("trash_first"))
    if not confirm:
        raise HTTPException(428, T("confirm_purge"))
    ingest.purge(session, doc)
    session.commit()


@router.get("/documents/{doc_id}/file")
def download(doc_id: int, session: SessionDep) -> Response:
    doc = document_or_404(session, doc_id, trashed=True)
    return Response(
        ingest.load_file(doc),
        media_type=doc.mime_type,
        headers={"Content-Disposition": disposition("inline", organize.standard_name(doc))},
    )


@router.get("/documents/{doc_id}/preview")
def preview(doc_id: int, session: SessionDep, page: int = 0) -> Response:
    doc = document_or_404(session, doc_id, trashed=True)
    png = render_page(ingest.load_file(doc), doc.mime_type, page)
    # Not cached: the browser cache would keep the decrypted page on disk (guard: no-store).
    return Response(png, media_type="image/png")


@router.get("/export")
def export(
    session: SessionDep,
    category: Category | None = None,
    ids: Annotated[list[int] | None, Query(max_length=1000)] = None,
) -> StreamingResponse:
    """ZIP archive of the decrypted documents, sorted by category, with a JSON index.

    `ids`: only the documents selected in a list."""
    stmt = select(Document).options(*WITHOUT_TEXT).where(ACTIVE)
    if category:
        stmt = stmt.where(Document.category == category)
    if ids:
        stmt = stmt.where(col(Document.id).in_(ids))
    docs = list(session.exec(stmt))
    activity.log(
        session,
        "export",
        T.plural_msg("export_category", len(docs), category=category)
        if category
        else T.plural_msg("export", len(docs)),
        actor="user",
    )
    session.commit()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
        index = []
        used: set[str] = set()
        for doc in docs:
            # Sorted by category (label in the current language) then by year, under its
            # standard name.
            year = deadlines.document_date(doc).year
            folder = f"{i18n.category_label(doc.category.value)}/{year}"
            standard = Path(organize.standard_name(doc))
            stem, ext = standard.stem, standard.suffix
            path, n = f"{folder}/{stem}{ext}", 2
            while path in used:
                path, n = f"{folder}/{stem} ({n}){ext}", n + 1
            used.add(path)
            zipped.writestr(path, ingest.load_file(doc))
            index.append({**DocumentOut.from_model(doc).model_dump(mode="json"), "file": path})
        zipped.writestr("index.json", json.dumps(index, ensure_ascii=False, indent=2))
    buffer.seek(0)
    label = i18n.category_label(category.value) if category else T("archive_all")
    name = f"binder-{safe_filename(label)}-{date.today()}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# --- Expiry and retention ------------------------------------------------------------------


@router.get("/expirations")
def list_expirations(session: SessionDep) -> list[ExpirationOut]:
    """Documents with an expiry date (current version only), most urgent first."""
    today = date.today()
    docs = session.exec(
        select(Document)
        .options(*WITHOUT_TEXT)
        .where(in_use(), col(Document.expiry_date).is_not(None))
        .where(col(Document.superseded_by).is_(None), col(Document.duplicate_of).is_(None))
        .order_by(col(Document.expiry_date))
    )
    out = []
    for doc in docs:
        assert doc.expiry_date is not None
        renew = deadlines.renew_from(doc) or doc.expiry_date
        state = "expired" if doc.expiry_date < today else "renew" if renew <= today else "valid"
        out.append(
            ExpirationOut(
                document=DocumentOut.from_model(doc),
                expiry_date=doc.expiry_date,
                renew_from=renew,
                days_left=(doc.expiry_date - today).days,
                state=state,
            )
        )
    return out


@router.get("/retention")
def list_archivable(session: SessionDep) -> list[DocumentOut]:
    """Documents that can go to the archives: retention period over or version replaced."""
    return [DocumentOut.from_model(d) for d, _ in archive.suggestions(session)]


@router.post("/retention/archive")
def archive_old(body: DocumentIds, session: SessionDep, response: Response) -> BulkResult:
    """Archives the documents the user chose, if they can indeed be archived."""
    count = 0
    with undoable(session, response):
        for doc in selected(session, body.ids):
            reason = archive.archivable(doc)
            if reason is not None:
                count += archive.archive(session, doc, reason)
    session.commit()
    return BulkResult(count=count, message=T.plural("bulk_archived", count))
