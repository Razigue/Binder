"""Binder REST routes."""

import io
import json
import logging
import os
import queue
import re
import threading
import unicodedata
import zipfile
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func
from sqlmodel import Session, col, select

from binder import __version__, i18n
from binder.agent import confirm, loop, tools
from binder.api.assistant import folder_status, folder_zip, undoable
from binder.config import get_settings
from binder.db import WITHOUT_TEXT, get_engine, get_session
from binder.models import Activity, Category, Deadline, Document, DocumentStatus
from binder.schemas import (
    ActivityOut,
    BulkPurge,
    BulkResult,
    BulkUpdate,
    ChatRequest,
    ChatResponse,
    ConfirmResult,
    DeadlineCreate,
    DeadlineOut,
    DeadlineUpdate,
    DocumentDetail,
    DocumentIds,
    DocumentOut,
    DocumentUpdate,
    ExpirationOut,
    FolderSettings,
    ImportSettings,
    ImportSettingsIn,
    MailSettings,
    ModelChoice,
    ModelsOverview,
    PreferencesOut,
    Stats,
    SystemStatus,
    TrashRequest,
)
from binder.services import (
    activity,
    deadlines,
    editing,
    erase,
    explain,
    folders,
    importers,
    ingest,
    letters,
    llm,
    llm_models,
    organize,
    preferences,
    profile,
    retention,
    settings_store,
    subscriptions,
    undo,
)
from binder.services.text import ocr_engine, render_page

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]
MAX_UPLOAD = 25 * 1024 * 1024

T = i18n.catalog(
    "api",
    {
        # HTTP errors shown to the user.
        "doc_not_found": {"en": "Document not found", "fr": "Document introuvable"},
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
        "confirm_erase": {
            "en": "Erasing all data: confirmation required (confirm=true)",
            "fr": "Effacement de toutes les données : confirmation requise (confirm=true)",
        },
        "unknown_folder": {"en": "Unknown folder", "fr": "Dossier inconnu"},
        "unknown_letter": {"en": "Unknown letter type", "fr": "Type de courrier inconnu"},
        "deadline_not_found": {"en": "Deadline not found", "fr": "Échéance introuvable"},
        "dir_not_found": {"en": "Folder not found: {path}", "fr": "Dossier introuvable : {path}"},
        "empty_path": {"en": "(empty)", "fr": "(vide)"},
        "mail_incomplete": {
            "en": "Server, username and password are required",
            "fr": "Serveur, identifiant et mot de passe sont nécessaires",
        },
        "ollama_delete_failed": {
            "en": "Ollama could not delete the model ({status})",
            "fr": "Ollama n'a pas pu supprimer le modèle ({status})",
        },
        "ollama_down": {"en": "Ollama is not responding", "fr": "Ollama ne répond pas"},
        "agent_failed": {
            "en": "The assistant ran into a problem. Try again.",
            "fr": "L'assistant a rencontré un problème. Réessayez.",
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
        "reminder_created": {
            "en": "Reminder “{title}” created for {due:date}",
            "fr": "Rappel « {title} » créé pour le {due:date}",
        },
        "deadline_deleted": {
            "en": "Deadline “{title}” deleted",
            "fr": "Échéance « {title} » supprimée",
        },
        "watch_enabled": {
            "en": "Watched folder enabled on {path}",
            "fr": "Dossier surveillé activé sur {path}",
        },
        "watch_disabled": {"en": "Watched folder disabled", "fr": "Dossier surveillé désactivé"},
        "mail_enabled": {
            "en": "Mailbox import enabled ({user})",
            "fr": "Import depuis la boîte mail activé ({user})",
        },
        "mail_disabled": {
            "en": "Mailbox import disabled",
            "fr": "Import depuis la boîte mail désactivé",
        },
        # Exported archives.
        "archive_all": {"en": "documents", "fr": "dossier"},
        "readme_name": {"en": "README.txt", "fr": "A_LIRE.txt"},
    },
)


def _get_doc(session: Session, doc_id: int, *, trashed: bool = False) -> Document:
    """Active document (or, with `trashed`, including those in the trash)."""
    doc = session.get(Document, doc_id)
    if doc is None or (doc.deleted_at is not None and not trashed):
        raise HTTPException(404, T("doc_not_found"))
    return doc


ACTIVE = col(Document.deleted_at).is_(None)


# --- System --------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _ocr_engine() -> str | None:
    """Installed OCR engine. Cached: checking Tesseract starts a process."""
    return ocr_engine()


@router.get("/status")
def status() -> SystemStatus:
    settings = get_settings()
    return SystemStatus(
        version=__version__,
        llm_available=llm.is_available(),
        llm_model=llm.model(),
        ocr_engine=_ocr_engine(),
        encrypted=True,
        data_dir=str(settings.data_dir),
    )


def _preferences_out(prefs: preferences.Preferences) -> PreferencesOut:
    loc = preferences.effective(prefs)
    system_language, system_country = i18n.system_locale()
    return PreferencesOut(
        **prefs.model_dump(),
        effective_language=loc.language,
        effective_country=loc.country,
        currency=loc.currency,
        system_language=system_language,
        system_country=system_country,
    )


@router.get("/preferences")
def get_preferences(session: SessionDep) -> PreferencesOut:
    return _preferences_out(preferences.load(session))


@router.put("/preferences")
def update_preferences(body: preferences.Preferences, session: SessionDep) -> PreferencesOut:
    preferences.save(session, body)
    session.commit()
    return _preferences_out(body)


@router.get("/stats")
def stats(session: SessionDep) -> Stats:
    today = date.today()
    week_ago = datetime.now(UTC) - timedelta(days=7)
    upcoming = session.exec(
        select(func.count())
        .select_from(Deadline)
        .where(Deadline.done == False, Deadline.due_date >= today)  # noqa: E712
        .where(Deadline.due_date <= today + timedelta(days=30))
    ).one()
    to_review = session.exec(
        select(func.count()).where(Document.status == DocumentStatus.TO_REVIEW, ACTIVE)
    ).one()
    classified = session.exec(
        select(func.count())
        .where(Document.status == DocumentStatus.CLASSIFIED, ACTIVE)
        .where(Document.created_at >= week_ago)
    ).one()
    total = session.exec(select(func.count()).select_from(Document).where(ACTIVE)).one()
    trashed = session.exec(select(func.count()).select_from(Document).where(~ACTIVE)).one()
    rows = session.exec(
        select(Document.category, func.count()).where(ACTIVE).group_by(Document.category)
    ).all()
    return Stats(
        upcoming_deadlines=upcoming,
        to_review=to_review,
        classified_this_week=classified,
        total_documents=total,
        trashed=trashed,
        by_category={Category(cat).value: n for cat, n in rows},
    )


# --- Documents -----------------------------------------------------------------------------


BATCH = re.compile(r"[A-Za-z0-9_-]{1,64}")


@router.post("/documents", status_code=201)
async def upload(
    file: UploadFile,
    background: BackgroundTasks,
    session: SessionDep,
    batch: str | None = None,
) -> DocumentOut:
    """`batch`: chosen by the interface for one drop of files (the import report groups them)."""
    data = await file.read(MAX_UPLOAD + 1)
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
    limit: Annotated[int, Query(le=500)] = 100,
) -> list[DocumentOut]:
    if q:
        result = tools.search_documents(
            session, q, category.value if category else None, limit=limit
        )
        docs = result.documents
        if status:
            docs = [d for d in docs if d.status == status]
    else:
        stmt = select(Document).options(*WITHOUT_TEXT).where(ACTIVE)
        if category:
            stmt = stmt.where(Document.category == category)
        if status:
            stmt = stmt.where(Document.status == status)
        docs = list(session.exec(stmt.order_by(col(Document.created_at).desc()).limit(limit)))
    return [DocumentOut.from_model(d) for d in docs]


# Grouped actions on the documents selected in a list: one request, one "Undo" for all of
# them. Ids that are unknown (or not in the expected place) are skipped.


def _selected(session: Session, ids: list[int], *, trashed: bool = False) -> list[Document]:
    docs = session.exec(select(Document).where(col(Document.id).in_(set(ids))))
    return [d for d in docs if (d.deleted_at is not None) == trashed]


@router.post("/documents/bulk/trash")
def bulk_trash(body: DocumentIds, session: SessionDep, response: Response) -> BulkResult:
    docs = _selected(session, body.ids)
    with undoable(session, response):
        for doc in docs:
            ingest.trash(session, doc)
    session.commit()
    return BulkResult(count=len(docs), message=T.plural("bulk_trashed", len(docs)))


@router.post("/documents/bulk/update")
def bulk_update(body: BulkUpdate, session: SessionDep, response: Response) -> BulkResult:
    changes = body.model_dump(exclude_unset=True, exclude={"ids", "validated"})
    changes = {k: v for k, v in changes.items() if v is not None}
    docs = _selected(session, body.ids)
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
    docs = [d for d in _selected(session, body.ids) if d.status != DocumentStatus.PROCESSING]
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


@router.post("/trash/restore")
def bulk_restore(body: DocumentIds, session: SessionDep, response: Response) -> BulkResult:
    docs = _selected(session, body.ids, trashed=True)
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
    docs = _selected(session, body.ids, trashed=True)
    for doc in docs:
        ingest.purge(session, doc)
    session.commit()
    return BulkResult(count=len(docs), message=T.plural("bulk_purged", len(docs)))


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, session: SessionDep) -> DocumentDetail:
    return DocumentDetail.from_model(_get_doc(session, doc_id))


@router.patch("/documents/{doc_id}")
def update_document(
    doc_id: int, patch: DocumentUpdate, session: SessionDep, response: Response
) -> DocumentDetail:
    doc = _get_doc(session, doc_id)
    changes = patch.model_dump(exclude_unset=True)
    validated = bool(changes.pop("validated", False))
    with undoable(session, response):
        editing.update_document(session, doc, changes, validated=validated)
    session.commit()
    session.refresh(doc)
    return DocumentDetail.from_model(doc)


@router.post("/documents/{doc_id}/reanalyze")
def reanalyze(doc_id: int, session: SessionDep) -> DocumentDetail:
    doc = _get_doc(session, doc_id)
    activity.log(
        session,
        "reanalyze",
        T.msg("reanalyze", title=doc.title),
        actor="user",
        document=doc,
    )
    doc = ingest.analyze(session, doc)
    return DocumentDetail.from_model(doc)


@router.get("/documents/{doc_id}/explanation")
def explain_document(
    doc_id: int, session: SessionDep, refresh: bool = False
) -> explain.Explanation:
    """Plain-language explanation and actions to take (cached on the document)."""
    doc = _get_doc(session, doc_id)
    result = explain.get(session, doc, refresh=refresh)
    session.commit()
    return result


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, session: SessionDep, response: Response) -> None:
    """Moves the document to the trash (reversible)."""
    with undoable(session, response):
        ingest.trash(session, _get_doc(session, doc_id))
    session.commit()


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
    doc = _get_doc(session, doc_id, trashed=True)
    if doc.deleted_at is None:
        raise HTTPException(409, T("not_in_trash"))
    with undoable(session, response):
        ingest.restore(session, doc)
    session.commit()
    session.refresh(doc)
    return DocumentDetail.from_model(doc)


@router.delete("/documents/{doc_id}/purge", status_code=204)
def purge_document(doc_id: int, session: SessionDep, confirm: bool = False) -> None:
    """Permanent deletion: requires a document in the trash and `confirm=true`."""
    doc = _get_doc(session, doc_id, trashed=True)
    if doc.deleted_at is None:
        raise HTTPException(409, T("trash_first"))
    if not confirm:
        raise HTTPException(428, T("confirm_purge"))
    ingest.purge(session, doc)
    session.commit()


@router.get("/documents/{doc_id}/file")
def download(doc_id: int, session: SessionDep) -> Response:
    doc = _get_doc(session, doc_id, trashed=True)
    return Response(
        ingest.load_file(doc),
        media_type=doc.mime_type,
        headers={"Content-Disposition": _disposition("inline", organize.standard_name(doc))},
    )


@router.get("/documents/{doc_id}/preview")
def preview(doc_id: int, session: SessionDep, page: int = 0) -> Response:
    doc = _get_doc(session, doc_id, trashed=True)
    png = render_page(ingest.load_file(doc), doc.mime_type, page)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


def _safe(name: str) -> str:
    """ASCII file name, safe for HTTP headers and archive paths."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9.\- ]", "_", ascii_name)


def _disposition(kind: str, name: str) -> str:
    """Content-Disposition header: ASCII fallback + full UTF-8 name (RFC 6266)."""
    return f"{kind}; filename=\"{_safe(name)}\"; filename*=UTF-8''{quote(name)}"


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
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        index = []
        used: set[str] = set()
        for doc in docs:
            # Sorted by category (label in the current language) then by year, under its
            # standard name.
            year = (doc.issue_date or doc.due_date or doc.created_at.date()).year
            folder = f"{i18n.category_label(doc.category.value)}/{year}"
            stem, ext = os.path.splitext(organize.standard_name(doc))
            path, n = f"{folder}/{stem}{ext}", 2
            while path in used:
                path, n = f"{folder}/{stem} ({n}){ext}", n + 1
            used.add(path)
            archive.writestr(path, ingest.load_file(doc))
            index.append({**DocumentOut.from_model(doc).model_dump(mode="json"), "file": path})
        archive.writestr("index.json", json.dumps(index, ensure_ascii=False, indent=2))
    buffer.seek(0)
    label = i18n.category_label(category.value) if category else T("archive_all")
    name = f"binder-{_safe(label)}-{date.today()}.zip"
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
        .where(ACTIVE, col(Document.expiry_date).is_not(None))
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
def list_deletable(session: SessionDep) -> list[DocumentOut]:
    """Documents that can be sorted out: retention period over or version replaced."""
    docs = session.exec(
        select(Document).options(*WITHOUT_TEXT).where(ACTIVE).order_by(col(Document.issue_date))
    )
    return [DocumentOut.from_model(d) for d in docs if retention.deletion_reason(d)]


@router.post("/retention/trash")
def trash_deletable(body: TrashRequest, session: SessionDep, response: Response) -> dict[str, int]:
    """Moves the documents chosen by the user to the trash, if they can indeed be sorted out."""
    trashed = 0
    with undoable(session, response):
        for doc_id in body.ids:
            doc = session.get(Document, doc_id)
            reason = retention.deletion_msg(doc, inline=True) if doc else None
            if doc is None or reason is None:
                continue
            ingest.trash(session, doc, reason=reason)
            trashed += 1
    session.commit()
    return {"trashed": trashed}


# --- Folders (checklists) ------------------------------------------------------------------


@router.get("/folders")
def list_folders(session: SessionDep) -> list[folders.FolderStatus]:
    docs = folders.current_documents(session)
    return [folders.evaluate(session, kind, docs=docs) for kind in folders.KINDS.values()]


@router.get("/folders/{key}")
def get_folder(key: str, session: SessionDep) -> folders.FolderStatus:
    return folder_status(session, key)


@router.get("/folders/{key}/export")
def export_folder(key: str, session: SessionDep) -> StreamingResponse:
    """ZIP of the documents found, numbered, with the list of what is still missing."""
    return folder_zip(session, folder_status(session, key))


# --- Subscriptions -------------------------------------------------------------------------


@router.get("/subscriptions")
def list_subscriptions(session: SessionDep) -> list[subscriptions.Subscription]:
    return subscriptions.detect(session)


# --- Letter templates ----------------------------------------------------------------------


@router.get("/profile")
def get_profile(session: SessionDep) -> profile.Profile:
    return profile.load(session)


@router.put("/profile")
def update_profile(body: profile.Profile, session: SessionDep) -> profile.Profile:
    saved = profile.update(session, body.model_dump(exclude={"auto"}))
    session.commit()
    return saved


@router.get("/letters/kinds")
def letter_kinds() -> dict[str, str]:
    return letters.kind_titles()


# --- Deadlines -----------------------------------------------------------------------------


@router.get("/deadlines")
def list_deadlines(
    session: SessionDep,
    start: date | None = None,
    end: date | None = None,
    include_done: bool = False,
) -> list[DeadlineOut]:
    stmt = select(Deadline)
    if start:
        stmt = stmt.where(Deadline.due_date >= start)
    if end:
        stmt = stmt.where(Deadline.due_date <= end)
    if not include_done:
        stmt = stmt.where(Deadline.done == False)  # noqa: E712
    today = date.today()
    return [
        DeadlineOut.from_model(d, today)
        for d in session.exec(stmt.order_by(col(Deadline.due_date)))
    ]


@router.post("/deadlines", status_code=201)
def create_deadline(body: DeadlineCreate, session: SessionDep, response: Response) -> DeadlineOut:
    deadline = Deadline(**body.model_dump(), source="manual")
    session.add(deadline)
    session.flush()
    with undoable(session, response):
        undo.push("deadline_created", id=deadline.id)
    activity.log(
        session,
        "reminder",
        T.msg("reminder_created", title=deadline.title, due=deadline.due_date),
        actor="user",
        document_id=deadline.document_id,
    )
    session.commit()
    session.refresh(deadline)
    return DeadlineOut.from_model(deadline, date.today())


@router.patch("/deadlines/{deadline_id}")
def update_deadline(
    deadline_id: int, body: DeadlineUpdate, session: SessionDep, response: Response
) -> DeadlineOut:
    deadline = session.get(Deadline, deadline_id)
    if deadline is None:
        raise HTTPException(404, T("deadline_not_found"))
    with undoable(session, response):
        editing.update_deadline(session, deadline, body.model_dump(exclude_unset=True))
    session.commit()
    session.refresh(deadline)
    return DeadlineOut.from_model(deadline, date.today())


@router.delete("/deadlines/{deadline_id}", status_code=204)
def delete_deadline(deadline_id: int, session: SessionDep, response: Response) -> None:
    deadline = session.get(Deadline, deadline_id)
    if deadline is None:
        raise HTTPException(404, T("deadline_not_found"))
    with undoable(session, response):
        undo.push("deadline_deleted", state=undo.deadline_state(deadline))
    activity.log(
        session,
        "deadline",
        T.msg("deadline_deleted", title=deadline.title),
        actor="user",
        document_id=deadline.document_id,
    )
    session.delete(deadline)
    session.commit()


# --- Automatic import ----------------------------------------------------------------------


def _import_settings(session: Session) -> ImportSettings:
    folder = settings_store.load(session, importers.FOLDER_KEY, importers.FolderConfig)
    mail = settings_store.load(session, importers.MAIL_KEY, importers.MailConfig)
    return ImportSettings(
        folder=FolderSettings(**folder.model_dump()),
        mail=MailSettings(
            **mail.model_dump(exclude={"password"}), password_set=bool(mail.password)
        ),
    )


@router.get("/import/settings")
def get_import_settings(session: SessionDep) -> ImportSettings:
    return _import_settings(session)


@router.put("/import/settings")
def update_import_settings(body: ImportSettingsIn, session: SessionDep) -> ImportSettings:
    if body.folder is not None:
        folder = settings_store.load(session, importers.FOLDER_KEY, importers.FolderConfig)
        path = body.folder.path.strip()
        if body.folder.enabled and not Path(path).expanduser().is_dir():
            raise HTTPException(400, T("dir_not_found", path=path or T("empty_path")))
        if (folder.enabled, folder.path) != (body.folder.enabled, path):
            msg = (
                T.msg("watch_enabled", path=path)
                if body.folder.enabled
                else T.msg("watch_disabled")
            )
            activity.log(session, "settings", msg, actor="user")
        folder.enabled, folder.path, folder.last_error = body.folder.enabled, path, None
        settings_store.save(session, importers.FOLDER_KEY, folder)
    if body.mail is not None:
        mail = settings_store.load(session, importers.MAIL_KEY, importers.MailConfig)
        new = body.mail
        if new.enabled and not (new.host and new.user and (new.password or mail.password)):
            raise HTTPException(400, T("mail_incomplete"))
        if (mail.host, mail.user, mail.folder) != (new.host, new.user, new.folder):
            mail.uidvalidity, mail.last_uid = None, 0
        if mail.enabled != new.enabled:
            msg = T.msg("mail_enabled", user=new.user) if new.enabled else T.msg("mail_disabled")
            activity.log(session, "settings", msg, actor="user")
        mail = mail.model_copy(update=new.model_dump(exclude={"password"}))
        if new.password is not None:
            mail.password = new.password
        mail.last_error = None
        settings_store.save(session, importers.MAIL_KEY, mail)
    session.commit()
    return _import_settings(session)


@router.post("/import/run")
def run_imports(session: SessionDep) -> dict[str, object]:
    """Checks the folder and the mailbox right away (otherwise: every 30 s / 5 min)."""
    return importers.run(session)


# --- Local AI ------------------------------------------------------------------------------


@router.get("/llm")
def llm_overview() -> ModelsOverview:
    return llm_models.overview()


@router.put("/llm/model")
def choose_model(body: ModelChoice, session: SessionDep) -> ModelsOverview:
    try:
        llm_models.choose(session, body.name)
    except ConnectionError as e:
        raise HTTPException(503, str(e)) from e
    except llm_models.UnknownModel as e:
        raise HTTPException(400, str(e)) from e
    session.commit()
    return llm_models.overview()


@router.post("/llm/models/{name}/download", status_code=202)
def download_model(name: str) -> ModelsOverview:
    try:
        llm_models.start_download(name)
    except llm_models.UnknownModel as e:
        raise HTTPException(404, str(e)) from e
    return llm_models.overview()


@router.delete("/llm/models/{name}/download", status_code=204)
def cancel_model_download(name: str) -> None:
    llm_models.cancel_download(name)


@router.delete("/llm/models/{name}", status_code=204)
def delete_model(name: str, session: SessionDep) -> None:
    try:
        llm_models.remove(session, name)
    except llm_models.UnknownModel as e:
        raise HTTPException(404, str(e)) from e
    except llm_models.Busy as e:
        raise HTTPException(409, str(e)) from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, T("ollama_delete_failed", status=e.response.status_code)) from e
    except httpx.HTTPError as e:
        raise HTTPException(503, T("ollama_down")) from e
    session.commit()


# --- Activity ------------------------------------------------------------------------------


@router.get("/activity")
def list_activity(
    session: SessionDep,
    document_id: int | None = None,
    limit: Annotated[int, Query(le=500)] = 100,
    before: int | None = None,
) -> list[ActivityOut]:
    stmt = select(Activity)
    if document_id is not None:
        stmt = stmt.where(Activity.document_id == document_id)
    if before is not None:
        stmt = stmt.where(col(Activity.id) < before)
    rows = session.exec(stmt.order_by(col(Activity.id).desc()).limit(limit))
    return [ActivityOut.from_model(a) for a in rows]


# --- Agent ---------------------------------------------------------------------------------


@router.post("/agent/chat")
def chat(body: ChatRequest, session: SessionDep) -> ChatResponse:
    attached = [
        ingest.wait_for_analysis(session, _get_doc(session, doc_id))
        for doc_id in dict.fromkeys(body.attachments)
    ]
    with undo.capture() as cap:
        try:
            response = loop.run(session, body.message, body.history, attached)
        except loop.AgentError as exc:
            raise HTTPException(503, str(exc)) from exc
    response.undo = undo.save(session, cap, actor="agent")
    session.commit()
    return response


@router.post("/agent/confirm/{token}")
def confirm_action(token: str, session: SessionDep) -> ConfirmResult:
    """Makes a change the agent proposed after reading a document or the web, once the user
    confirmed it."""
    proposal = confirm.take(token)
    if proposal is None:
        raise HTTPException(410, confirm.T("expired"))
    name, arguments = proposal
    with undo.capture() as cap:
        result = tools.call(session, name, arguments)
    if "error" in result.payload:
        session.rollback()
        raise HTTPException(422, str(result.payload["error"]))
    token_undo = undo.save(session, cap, actor="user")
    session.commit()
    return ConfirmResult(message=confirm.T("done"), changed=result.changed, undo=token_undo)


class _Stopped(Exception):
    """The client went away: the agent stops at its next step."""


@router.post("/agent/chat/stream")
def chat_stream(body: ChatRequest, session: SessionDep) -> StreamingResponse:
    """Same as /agent/chat, as newline-delimited JSON events: {"type": "tool"} when a tool
    starts, {"type": "tool_done"} when it ends, {"type": "stats"} after each model turn,
    {"type": "token"} as the answer is written, {"type": "step"} to discard the text
    so far, then {"type": "done", "response"} or {"type": "error", "message"}."""
    ids = list(dict.fromkeys(body.attachments))
    for doc_id in ids:
        _get_doc(session, doc_id)
    events: queue.Queue[dict[str, object] | None] = queue.Queue()
    stopped = threading.Event()
    language = i18n.current_language()

    def emit(event: dict[str, object]) -> None:
        if stopped.is_set():
            raise _Stopped
        events.put(event)

    def work() -> None:
        with i18n.using(language), Session(get_engine()) as worker:
            try:
                attached = [
                    ingest.wait_for_analysis(worker, _get_doc(worker, doc_id)) for doc_id in ids
                ]
                with undo.capture() as cap:
                    response = loop.run(worker, body.message, body.history, attached, emit)
                response.undo = undo.save(worker, cap, actor="agent")
                worker.commit()
                events.put({"type": "done", "response": response.model_dump(mode="json")})
            except _Stopped:
                worker.rollback()
            except loop.AgentError as exc:
                worker.rollback()
                events.put({"type": "error", "message": str(exc)})
            except Exception:
                log.exception("Agent failed")
                worker.rollback()
                events.put({"type": "error", "message": T("agent_failed")})
            finally:
                events.put(None)

    threading.Thread(target=work, name="agent", daemon=True).start()

    def stream() -> Iterator[str]:
        try:
            while (event := events.get()) is not None:
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            stopped.set()

    return StreamingResponse(
        stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"}
    )


@router.post("/demo")
def seed_demo(session: SessionDep) -> dict[str, object]:
    """Imports the fictitious demo documents."""
    results = ingest.seed_demo(session)
    batch = next((doc.batch for doc, created in results if created), None)
    return {"imported": sum(created for _, created in results), "batch": batch}


@router.get("/demo")
def demo_status(session: SessionDep) -> dict[str, int]:
    """Demo documents in the library and demo files older versions left behind (Settings
    offers to clear them, or to load the demo when there is none)."""
    return {
        "documents": len(ingest.demo_documents(session)),
        "leftovers": len(ingest.demo_leftover_files(session)),
    }


@router.delete("/demo")
def clear_demo(session: SessionDep) -> dict[str, int]:
    """Permanently removes the demo documents, what came from them and leftover demo files."""
    removed, files = ingest.clear_demo(session)
    session.commit()
    for path in files:
        path.unlink(missing_ok=True)
    return {"removed": removed, "files": len(files)}


@router.delete("/data")
def erase_data(session: SessionDep, confirm: bool = False) -> dict[str, int]:
    """Permanently erases everything Binder holds about the user (Settings); `confirm=true`."""
    if not confirm:
        raise HTTPException(428, T("confirm_erase"))
    removed = erase.erase_all(session)
    session.commit()
    erase.delete_files(session)
    return {"removed": removed}
