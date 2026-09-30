"""Routes REST de Binder."""

import io
import json
import re
import unicodedata
import zipfile
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func
from sqlmodel import Session, col, select

from binder.agent import loop, tools
from binder.config import get_settings
from binder.db import get_session, index_document, unindex_document
from binder.models import Category, Deadline, Document, DocumentStatus
from binder.schemas import (
    ChatRequest,
    ChatResponse,
    DeadlineCreate,
    DeadlineOut,
    DeadlineUpdate,
    DocumentDetail,
    DocumentOut,
    DocumentUpdate,
    Stats,
    SystemStatus,
)
from binder.services import ingest, llm
from binder.services.text import render_page

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]
MAX_UPLOAD = 25 * 1024 * 1024


def _get_doc(session: Session, doc_id: int) -> Document:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document introuvable")
    return doc


# --- Système -------------------------------------------------------------------------------


@router.get("/status")
def status() -> SystemStatus:
    ocr = None
    try:
        import doctr  # noqa: F401

        ocr = "docTR"
    except ImportError:
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            ocr = "Tesseract"
        except Exception:
            ocr = None
    settings = get_settings()
    return SystemStatus(
        llm_available=llm.is_available(),
        llm_model=settings.llm_model,
        ocr_engine=ocr,
        encrypted=True,
        data_dir=str(settings.data_dir),
    )


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
        select(func.count()).where(Document.status == DocumentStatus.TO_REVIEW)
    ).one()
    classified = session.exec(
        select(func.count())
        .where(Document.status == DocumentStatus.CLASSIFIED)
        .where(Document.created_at >= week_ago)
    ).one()
    total = session.exec(select(func.count()).select_from(Document)).one()
    rows = session.exec(select(Document.category, func.count()).group_by(Document.category)).all()
    return Stats(
        upcoming_deadlines=upcoming,
        to_review=to_review,
        classified_this_week=classified,
        total_documents=total,
        by_category={Category(cat).value: n for cat, n in rows},
    )


# --- Documents -----------------------------------------------------------------------------


@router.post("/documents", status_code=201)
async def upload(file: UploadFile, background: BackgroundTasks, session: SessionDep) -> DocumentOut:
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Fichier trop volumineux (25 Mo maximum)")
    if not data:
        raise HTTPException(400, "Fichier vide")
    try:
        mime = ingest.guess_mime(file.filename or "document", file.content_type)
    except ingest.UnsupportedFile as exc:
        raise HTTPException(415, str(exc)) from exc
    doc, created = ingest.store(session, data, file.filename or "document", mime)
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
        stmt = select(Document)
        if category:
            stmt = stmt.where(Document.category == category)
        if status:
            stmt = stmt.where(Document.status == status)
        docs = list(session.exec(stmt.order_by(col(Document.created_at).desc()).limit(limit)))
    return [DocumentOut.from_model(d) for d in docs]


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, session: SessionDep) -> DocumentDetail:
    return DocumentDetail.from_model(_get_doc(session, doc_id))


@router.patch("/documents/{doc_id}")
def update_document(doc_id: int, patch: DocumentUpdate, session: SessionDep) -> DocumentDetail:
    doc = _get_doc(session, doc_id)
    changes = patch.model_dump(exclude_unset=True)
    validated = bool(changes.pop("validated", False))
    for key, value in changes.items():
        setattr(doc, key, value)
    if changes:
        doc.extractor = "manual" if doc.extractor == "rules" else doc.extractor
    ingest.refresh_status(doc, validated=validated)
    session.add(doc)
    ingest.sync_deadline(session, doc)
    index_document(session, doc)
    session.commit()
    session.refresh(doc)
    return DocumentDetail.from_model(doc)


@router.post("/documents/{doc_id}/reanalyze")
def reanalyze(doc_id: int, session: SessionDep) -> DocumentDetail:
    doc = ingest.analyze(session, _get_doc(session, doc_id))
    return DocumentDetail.from_model(doc)


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, session: SessionDep) -> None:
    doc = _get_doc(session, doc_id)
    for dl in session.exec(select(Deadline).where(Deadline.document_id == doc_id)):
        session.delete(dl)
    unindex_document(session, doc_id)
    ingest.delete_file(doc)
    session.delete(doc)
    session.commit()


@router.get("/documents/{doc_id}/file")
def download(doc_id: int, session: SessionDep) -> Response:
    doc = _get_doc(session, doc_id)
    return Response(
        ingest.load_file(doc),
        media_type=doc.mime_type,
        headers={"Content-Disposition": f'inline; filename="{_safe(doc.filename)}"'},
    )


@router.get("/documents/{doc_id}/preview")
def preview(doc_id: int, session: SessionDep, page: int = 0) -> Response:
    doc = _get_doc(session, doc_id)
    png = render_page(ingest.load_file(doc), doc.mime_type, page)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


def _safe(name: str) -> str:
    """Nom de fichier ASCII, sûr pour les en-têtes HTTP et les chemins d'archive."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9.\- ]", "_", ascii_name)


@router.get("/export")
def export(session: SessionDep, category: Category | None = None) -> StreamingResponse:
    """Archive ZIP des documents déchiffrés, rangés par catégorie, avec un index JSON."""
    stmt = select(Document)
    if category:
        stmt = stmt.where(Document.category == category)
    docs = list(session.exec(stmt))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        index = []
        for doc in docs:
            path = f"{_safe(doc.category.value)}/{doc.id}-{_safe(doc.filename)}"
            archive.writestr(path, ingest.load_file(doc))
            index.append({**DocumentOut.from_model(doc).model_dump(mode="json"), "fichier": path})
        archive.writestr("index.json", json.dumps(index, ensure_ascii=False, indent=2))
    buffer.seek(0)
    name = f"binder-{_safe(category.value) if category else 'dossier'}-{date.today()}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# --- Échéances -----------------------------------------------------------------------------


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
def create_deadline(body: DeadlineCreate, session: SessionDep) -> DeadlineOut:
    deadline = Deadline(**body.model_dump(), source="manual")
    session.add(deadline)
    session.commit()
    session.refresh(deadline)
    return DeadlineOut.from_model(deadline, date.today())


@router.patch("/deadlines/{deadline_id}")
def update_deadline(deadline_id: int, body: DeadlineUpdate, session: SessionDep) -> DeadlineOut:
    deadline = session.get(Deadline, deadline_id)
    if deadline is None:
        raise HTTPException(404, "Échéance introuvable")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(deadline, key, value)
    session.add(deadline)
    session.commit()
    session.refresh(deadline)
    return DeadlineOut.from_model(deadline, date.today())


@router.delete("/deadlines/{deadline_id}", status_code=204)
def delete_deadline(deadline_id: int, session: SessionDep) -> None:
    deadline = session.get(Deadline, deadline_id)
    if deadline is None:
        raise HTTPException(404, "Échéance introuvable")
    session.delete(deadline)
    session.commit()


# --- Agent ---------------------------------------------------------------------------------


@router.post("/agent/chat")
def chat(body: ChatRequest, session: SessionDep) -> ChatResponse:
    return loop.run(session, body.message, body.history)


@router.post("/demo")
def seed_demo(session: SessionDep) -> dict[str, int]:
    """Importe les documents fictifs de démonstration."""
    return {"imported": sum(created for _, created in ingest.seed_demo(session))}
