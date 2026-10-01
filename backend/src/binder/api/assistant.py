"""Routes of the agent's proactive side: Today feed and its actions, undo, import reports, life
areas, household, letters, packs, local AI setup and backups."""

import contextlib
import io
import re
import tempfile
import zipfile
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT, get_engine, get_session, reset_engine
from binder.models import Correspondence, Deadline, Document
from binder.schemas import DeadlineOut, DocumentOut, Letter, LetterEdit, LetterRequest
from binder.services import (
    areas,
    backup,
    feed,
    folders,
    household,
    ingest,
    letters,
    llm_models,
    organize,
    reports,
    setup,
    sources,
    subscriptions,
    undo,
)

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]

T = i18n.catalog(
    "assistant_api",
    {
        "bad_action": {"en": "This action is no longer possible", "fr": "Action impossible"},
        "undo_expired": {
            "en": "Too late to undo this action",
            "fr": "Trop tard pour annuler cette action",
        },
        "report_not_found": {"en": "Import not found", "fr": "Import introuvable"},
        "letter_not_found": {"en": "Letter not found", "fr": "Courrier introuvable"},
        "not_sent": {"en": "This letter has not been sent", "fr": "Ce courrier n'est pas parti"},
        "unknown_area": {"en": "Unknown area", "fr": "Espace inconnu"},
        "unknown_folder": {"en": "Unknown folder", "fr": "Dossier inconnu"},
        "unknown_letter": {"en": "Unknown letter type", "fr": "Type de courrier inconnu"},
        "letter_needs_purpose": {
            "en": "Say what the letter is for",
            "fr": "Dites à quoi sert le courrier",
        },
        "doc_not_found": {"en": "Document not found", "fr": "Document introuvable"},
        "library_not_empty": {
            "en": "A backup can only be restored into an empty library",
            "fr": "Une sauvegarde ne se restaure que dans une bibliothèque vide",
        },
        "readme_name": {"en": "README.txt", "fr": "A_LIRE.txt"},
    },
)

UNDO_HEADER = "X-Undo"


@contextlib.contextmanager
def undoable(session: Session, response: Response, actor: str = "user") -> Iterator[None]:
    """Collects what the block changes and offers it to undo (X-Undo header)."""
    with undo.capture() as cap:
        yield
    token = undo.save(session, cap, actor=actor)
    if token:
        response.headers[UNDO_HEADER] = token


def _doc(session: Session, doc_id: int) -> Document:
    doc = session.get(Document, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise HTTPException(404, T("doc_not_found"))
    return doc


# --- Today feed ------------------------------------------------------------------------------


class FeedOut(BaseModel):
    items: list[feed.FeedItem]
    documents: int
    setup: setup.SetupStatus


@router.get("/feed")
def get_feed(session: SessionDep) -> FeedOut:
    items = feed.build(session)
    session.commit()  # the recovery code is created on first use
    total = session.exec(
        select(func.count()).select_from(Document).where(col(Document.deleted_at).is_(None))
    ).one()
    return FeedOut(items=items, documents=total, setup=setup.status())


class ActionIn(BaseModel):
    type: str = Field(max_length=40)
    params: dict[str, Any] = {}


@router.post("/actions")
def run_action(body: ActionIn, session: SessionDep, response: Response) -> feed.ActResult:
    if body.type not in feed.SERVER_ACTIONS:
        raise HTTPException(400, T("bad_action"))
    try:
        with undoable(session, response):
            result = feed.act(session, body.type, body.params)
    except feed.BadAction as e:
        session.rollback()
        raise HTTPException(409, T("bad_action")) from e
    session.commit()
    return result


@router.post("/undo/{token}", status_code=204)
def undo_action(token: str, session: SessionDep) -> None:
    if not undo.undo(session, token):
        raise HTTPException(410, T("undo_expired"))
    session.commit()


# --- Import reports --------------------------------------------------------------------------


@router.get("/reports/{batch}")
def get_report(batch: str, session: SessionDep) -> reports.ImportReport:
    report = reports.build(session, batch)
    if report is None:
        raise HTTPException(404, T("report_not_found"))
    return report


@router.post("/reports/{batch}/seen", status_code=204)
def report_seen(batch: str, session: SessionDep) -> None:
    reports.mark_seen(session, batch)
    session.commit()


# --- Life areas and household --------------------------------------------------------------


class AreaSummary(BaseModel):
    area: str
    label: str
    documents: int
    attention: int


class AreaOut(BaseModel):
    area: str
    label: str
    documents: list[DocumentOut]
    deadlines: list[DeadlineOut]
    subscriptions: list[subscriptions.Subscription]
    items: list[feed.FeedItem]
    members: list[household.Member]
    yearly_cost: float


def _active_docs(session: Session) -> list[Document]:
    return list(
        session.exec(
            select(Document)
            .options(*WITHOUT_TEXT)
            .where(col(Document.deleted_at).is_(None))
            .order_by(col(Document.issue_date).desc(), col(Document.created_at).desc())
        )
    )


@router.get("/areas")
def list_areas(session: SessionDep) -> list[AreaSummary]:
    docs = _active_docs(session)
    items = feed.build(session)
    return [
        AreaSummary(
            area=a,
            label=areas.label(a),
            documents=sum(d.area == a for d in docs),
            attention=sum(i.area == a and i.tone != "info" for i in items),
        )
        for a in areas.AREAS
    ]


@router.get("/areas/{area}")
def get_area(area: str, session: SessionDep) -> AreaOut:
    if area not in areas.AREAS:
        raise HTTPException(404, T("unknown_area"))
    docs = [d for d in _active_docs(session) if d.area == area]
    ids = {d.id for d in docs}
    today = date.today()
    deadline_rows = session.exec(
        select(Deadline)
        .where(Deadline.done == False, Deadline.due_date <= today + timedelta(days=90))  # noqa: E712
        .order_by(col(Deadline.due_date))
    ).all()
    in_area = [
        d
        for d in deadline_rows
        if d.document_id in ids
        or (d.document_id is None and areas.BY_CATEGORY.get(d.category) == area)
    ]
    subs = [
        s for s in subscriptions.detect(session) if s.history and s.history[-1].document_id in ids
    ]
    members = [m for m in household.members(session) if area in m.areas]
    return AreaOut(
        area=area,
        label=areas.label(area),
        documents=[DocumentOut.from_model(d) for d in docs],
        deadlines=[DeadlineOut.from_model(d, today) for d in in_area],
        subscriptions=subs,
        items=[i for i in feed.build(session) if i.area == area],
        members=members,
        yearly_cost=round(sum(s.yearly_estimate or 0 for s in subs), 2),
    )


@router.get("/household")
def get_household(session: SessionDep) -> list[household.Member]:
    return household.members(session)


@router.get("/documents/{doc_id}/sources")
def document_sources(doc_id: int, session: SessionDep) -> list[sources.FieldSource]:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, T("doc_not_found"))
    return sources.locate(doc, ingest.load_file(doc))


# --- Letters ---------------------------------------------------------------------------------


def _letter(session: Session, letter_id: int) -> Correspondence:
    row = session.get(Correspondence, letter_id)
    if row is None:
        raise HTTPException(404, T("letter_not_found"))
    return row


@router.post("/letters")
def write_letter(body: LetterRequest, session: SessionDep, response: Response) -> Letter:
    if body.kind is not None and body.kind not in letters.KINDS:
        raise HTTPException(400, T("unknown_letter"))
    if body.kind is None and not body.purpose.strip():
        raise HTTPException(400, T("letter_needs_purpose"))
    doc = _doc(session, body.document_id) if body.document_id is not None else None
    with undoable(session, response):
        if body.kind is not None and body.details:
            profile = letters.profile_for(session)
            address = letters.recipient_address(doc, profile)
            letter = letters.save(
                session, letters.write(body.kind, doc, profile, body.details, address)
            )
        else:
            letter = letters.compose(session, body.purpose, doc, kind=body.kind)
    session.commit()
    return letter


@router.get("/letters")
def list_letters(session: SessionDep) -> list[Letter]:
    rows = session.exec(
        select(Correspondence).order_by(col(Correspondence.created_at).desc()).limit(200)
    )
    return [letters.out(r) for r in rows]


@router.get("/letters/{letter_id}")
def get_letter(letter_id: int, session: SessionDep) -> Letter:
    return letters.out(_letter(session, letter_id))


@router.put("/letters/{letter_id}")
def edit_letter(
    letter_id: int, body: LetterEdit, session: SessionDep, response: Response
) -> Letter:
    row = _letter(session, letter_id)
    with undoable(session, response):
        undo.row_changed(row)
        row.body = body.body
        session.add(row)
    session.commit()
    return letters.out(row)


@router.get("/letters/{letter_id}/pdf")
def letter_pdf(letter_id: int, session: SessionDep) -> Response:
    from binder.api.routes import _disposition

    row = _letter(session, letter_id)
    return Response(
        letters.pdf(row),
        media_type="application/pdf",
        headers={"Content-Disposition": _disposition("attachment", letters.file_name(row))},
    )


@router.post("/letters/{letter_id}/sent")
def letter_sent(letter_id: int, session: SessionDep, response: Response) -> Letter:
    row = _letter(session, letter_id)
    with undoable(session, response):
        letters.mark_sent(session, row)
    session.commit()
    return letters.out(row)


@router.post("/letters/{letter_id}/answered")
def letter_answered(letter_id: int, session: SessionDep, response: Response) -> Letter:
    row = _letter(session, letter_id)
    with undoable(session, response):
        letters.mark_answered(session, row)
    session.commit()
    return letters.out(row)


@router.post("/letters/{letter_id}/follow-up")
def letter_follow_up(letter_id: int, session: SessionDep, response: Response) -> Letter:
    row = _letter(session, letter_id)
    if row.sent_on is None:
        raise HTTPException(409, T("not_sent"))
    with undoable(session, response):
        letter = letters.follow_up(session, row)
    session.commit()
    return letter


# --- Packs asked for in words ---------------------------------------------------------------


class FolderRequest(BaseModel):
    purpose: str = Field(min_length=1, max_length=500)


@router.post("/folders/prepare")
def prepare_folder(body: FolderRequest, session: SessionDep) -> folders.FolderStatus:
    status = folders.prepare(session, body.purpose.strip())
    session.commit()
    return status


def folder_status(session: Session, key: str) -> folders.FolderStatus:
    if key.startswith("custom-"):
        status = folders.saved(session, key)
    else:
        kind = folders.KINDS.get(key)
        status = folders.evaluate(session, kind) if kind else None
    if status is None:
        raise HTTPException(404, T("unknown_folder"))
    return status


def folder_zip(session: Session, status: folders.FolderStatus) -> StreamingResponse:
    """ZIP of the documents found, numbered, with the list of what is still missing."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for n, piece in enumerate(status.pieces, 1):
            if piece.status == "outdated":
                continue
            for doc_id in piece.document_ids:
                doc = session.get(Document, doc_id)
                if doc is None:
                    continue
                label = re.sub(r'[\\/:*?"<>|]+', " ", piece.label)
                path = f"{n:02d} {label}/{organize.standard_name(doc)}"
                archive.writestr(path, ingest.load_file(doc))
        archive.writestr(T("readme_name"), folders.readme(status))
    from binder.services import activity

    activity.log(session, "export", folders.exported_msg(status), actor="user")
    session.commit()
    buffer.seek(0)
    name = f"binder-{status.key}-{date.today()}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# --- Local AI setup --------------------------------------------------------------------------


@router.get("/setup")
def setup_status() -> setup.SetupStatus:
    return setup.status()


@router.post("/setup/retry")
def setup_retry() -> setup.SetupStatus:
    setup.start()
    return setup.status()


# --- Backups ---------------------------------------------------------------------------------


@router.get("/backup")
def backup_info(session: SessionDep) -> backup.BackupInfo:
    return backup.info(session)


@router.post("/backup/now")
def backup_now(session: SessionDep) -> backup.BackupInfo:
    backup.create(session)
    return backup.info(session)


@router.post("/backup/code")
def backup_new_code(session: SessionDep) -> backup.BackupInfo:
    backup.renew_code(session)
    session.commit()
    return backup.info(session)


@router.post("/backup/restore", status_code=204)
async def backup_restore(file: UploadFile, code: Annotated[str, Form(max_length=64)]) -> None:
    with Session(get_engine()) as session:
        count = session.exec(select(func.count()).select_from(Document)).one()
    if count:
        raise HTTPException(409, T("library_not_empty"))
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "backup.zip"
        with archive.open("wb") as f:
            while chunk := await file.read(1 << 20):
                f.write(chunk)
        reset_engine()
        try:
            backup.restore(archive, code)
        except (backup.WrongCode, ValueError) as e:
            raise HTTPException(400, str(e)) from e
        finally:
            reset_engine()
    with Session(get_engine()) as session:
        backup.log_restored(session)
        llm_models.restore(session)
