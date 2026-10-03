"""Routes of the agent's proactive side: To do feed and its actions, undo, import reports, life
areas, household, letters, packs, local AI setup and backups."""

import contextlib
import io
import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, col, select

from binder import i18n
from binder.api.common import SessionDep, disposition, document_or_404, get_or_404
from binder.db import WITHOUT_TEXT, get_engine, in_use, reset_engine
from binder.models import Correspondence, Deadline, Document
from binder.schemas import DeadlineOut, DocumentOut, Letter, LetterEdit, LetterRequest
from binder.services import (
    activity,
    areas,
    backup,
    calendar,
    essentials,
    feed,
    folders,
    household,
    ingest,
    letters,
    llm_models,
    organize,
    preferences,
    profile,
    questions,
    reports,
    setup,
    sources,
    subscriptions,
    undo,
)

router = APIRouter(prefix="/api")

T = i18n.catalog(
    "assistant_api",
    {
        "bad_action": {"en": "This action is no longer possible", "fr": "Action impossible"},
        # State of a life area, in words, on its tile in My papers.
        "area_up_to_date": {"en": "Up to date", "fr": "À jour"},
        "area_empty": {"en": "Nothing here yet", "fr": "Rien pour l'instant"},
        "area_more_one": {"en": "{state} (+{n} more)", "fr": "{state} (+{n} autre)"},
        "area_more_other": {"en": "{state} (+{n} more)", "fr": "{state} (+{n} autres)"},
        "area_expires_one": {
            "en": "{title} expires in {n} month",
            "fr": "{title} expire dans {n} mois",
        },
        "area_expires_other": {
            "en": "{title} expires in {n} months",
            "fr": "{title} expire dans {n} mois",
        },
        "undo_expired": {
            "en": "Too late to undo this action",
            "fr": "Trop tard pour annuler cette action",
        },
        "report_not_found": {"en": "Import not found", "fr": "Import introuvable"},
        "letter_not_found": {"en": "Letter not found", "fr": "Courrier introuvable"},
        "not_sent": {"en": "This letter has not been sent", "fr": "Ce courrier n'est pas parti"},
        "unknown_area": {"en": "Unknown area", "fr": "Espace inconnu"},
        "unknown_member": {
            "en": "Nobody by that name in the household",
            "fr": "Personne de ce nom dans le foyer",
        },
        "unknown_folder": {"en": "Unknown folder", "fr": "Dossier inconnu"},
        "unknown_letter": {"en": "Unknown letter type", "fr": "Type de courrier inconnu"},
        "letter_needs_purpose": {
            "en": "Say what the letter is for",
            "fr": "Dites à quoi sert le courrier",
        },
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


# --- To do feed ------------------------------------------------------------------------------


class FeedOut(BaseModel):
    items: list[feed.FeedItem]
    documents: int
    setup: setup.SetupStatus


@router.get("/feed")
def get_feed(session: SessionDep) -> FeedOut:
    items = feed.build(session)
    session.commit()  # the recovery code is created on first use
    total = session.exec(select(func.count()).select_from(Document).where(in_use())).one()
    return FeedOut(items=items, documents=total, setup=setup.status())


@router.get("/questions")
def list_questions(
    session: SessionDep,
    documents: Annotated[list[int] | None, Query(max_length=500)] = None,
) -> list[feed.FeedItem]:
    """Every question worth asking, as cards (grouped, most useful first): the sorting
    session goes through them one by one, the document next to each. `documents`: one
    question per document, about these only (a grouped question seen in detail)."""
    if documents:
        found = questions.pending(session, group=False, ids=documents)
    else:
        found = questions.pending(session)
    return [feed.question_item(q) for q in found]


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
    # Its state in words ("Up to date", "Identity card: renew it") and how pressing it is:
    # "urgent", "soon", "ok" or "empty".
    state: str = ""
    tone: str = "ok"


# An end of validity this close is mentioned on the area's tile.
EXPIRY_HINT_DAYS = 180


def _area_state(
    area: str, docs: list[Document], items: list[feed.FeedItem], today: date
) -> tuple[str, str]:
    # Questions are asked in To do; the tile says what the area itself needs.
    pressing = [i for i in items if i.area == area and i.tone != "info" and i.kind != "question"]
    if pressing:
        first = pressing[0]
        # A payment says when: "Tax notice 2026 · Due 7 Oct 2026".
        state = f"{first.title} · {first.detail}" if first.kind == "deadline" else first.title
        if len(pressing) > 1:
            return T.plural("area_more", len(pressing) - 1, state=state), first.tone
        return state, first.tone
    mine = [d for d in docs if d.area == area]
    expiring = sorted(
        (
            d
            for d in mine
            if d.expiry_date is not None
            and d.superseded_by is None
            and 0 <= (d.expiry_date - today).days <= EXPIRY_HINT_DAYS
        ),
        key=lambda d: d.expiry_date or today,
    )
    if expiring:
        doc = expiring[0]
        assert doc.expiry_date is not None
        months = max(1, round((doc.expiry_date - today).days / 30))
        return T.plural("area_expires", months, title=doc.title), "ok"
    if mine:
        return T("area_up_to_date"), "ok"
    return T("area_empty"), "empty"


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
            .where(in_use())
            .order_by(col(Document.issue_date).desc(), col(Document.created_at).desc())
        )
    )


@router.get("/areas")
def list_areas(session: SessionDep) -> list[AreaSummary]:
    docs = _active_docs(session)
    items = feed.build(session)
    today = date.today()
    out = []
    for a in areas.AREAS:
        state, tone = _area_state(a, docs, items, today)
        out.append(
            AreaSummary(
                area=a,
                label=areas.label(a),
                documents=sum(d.area == a for d in docs),
                attention=sum(i.area == a and i.tone != "info" for i in items),
                state=state,
                tone=tone,
            )
        )
    return out


@router.get("/essentials")
def get_essentials(session: SessionDep) -> list[essentials.PaperOut]:
    """The papers the user should have, from the three answers of the first launch."""
    return essentials.papers(session, profile.load(session))


@router.get("/calendar")
def get_calendar(session: SessionDep) -> list[calendar.CalendarEntry]:
    """The administrative year (what usually comes back each month), for the Calendar tab."""
    country = preferences.effective(preferences.load(session)).country
    return calendar.year(session, country)


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


class MemberEdit(BaseModel):
    action: Literal["add", "remove", "rename"]
    name: str = Field(min_length=1, max_length=120)
    # rename only; the name of another member merges both.
    new_name: str = Field(default="", max_length=120)


@router.post("/household")
def edit_household(
    body: MemberEdit, session: SessionDep, response: Response
) -> list[household.Member]:
    """The user corrects the household Binder found."""
    try:
        with undoable(session, response):
            if body.action == "add":
                household.add(session, body.name)
            elif body.action == "remove":
                household.remove(session, body.name)
            else:
                household.rename(session, body.name, body.new_name)
            # The sender of letters follows the household while Binder fills it.
            profile.learn(session)
    except household.UnknownMember as e:
        session.rollback()
        raise HTTPException(404, T("unknown_member")) from e
    session.commit()
    return household.members(session)


@router.get("/documents/{doc_id}/sources")
def document_sources(doc_id: int, session: SessionDep) -> list[sources.FieldSource]:
    # Trashed documents too: the Trash page shows where their fields were read.
    doc = document_or_404(session, doc_id, trashed=True)
    return sources.locate(doc, ingest.load_file(doc))


# --- Letters ---------------------------------------------------------------------------------


def _letter(session: Session, letter_id: int) -> Correspondence:
    return get_or_404(session, Correspondence, letter_id, T("letter_not_found"))


@router.post("/letters")
def write_letter(body: LetterRequest, session: SessionDep, response: Response) -> Letter:
    if body.kind is not None and body.kind not in letters.KINDS:
        raise HTTPException(400, T("unknown_letter"))
    if body.kind is None and not body.purpose.strip():
        raise HTTPException(400, T("letter_needs_purpose"))
    doc = document_or_404(session, body.document_id) if body.document_id is not None else None
    with undoable(session, response):
        if body.kind is not None and body.details:
            sender = letters.profile_for(session)
            address = letters.recipient_address(doc, sender)
            letter = letters.save(
                session, letters.write(body.kind, doc, sender, body.details, address)
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
    row = _letter(session, letter_id)
    return Response(
        letters.pdf(row),
        media_type="application/pdf",
        headers={"Content-Disposition": disposition("attachment", letters.file_name(row))},
    )


@router.delete("/letters/{letter_id}", status_code=204)
def delete_letter(letter_id: int, session: SessionDep, response: Response) -> None:
    row = _letter(session, letter_id)
    with undoable(session, response):
        letters.delete(session, row)
    session.commit()


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
            label = re.sub(r'[\\/:*?"<>|]+', " ", piece.label)
            for doc_id in piece.document_ids:
                doc = session.get(Document, doc_id)
                if doc is None:
                    continue
                path = f"{n:02d} {label}/{organize.standard_name(doc)}"
                archive.writestr(path, ingest.load_file(doc))
        archive.writestr(T("readme_name"), folders.readme(status))
    activity.log(session, "export", folders.exported_msg(status), actor="user")
    session.commit()
    buffer.seek(0)
    name = f"binder-{status.key}-{date.today()}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": disposition("attachment", name)},
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


@router.post("/backup/confirm")
def backup_confirm(session: SessionDep) -> backup.BackupInfo:
    """The user wrote the recovery code down: Binder stops showing it."""
    backup.confirm(session)
    session.commit()
    return backup.info(session)


@router.post("/backup/code")
def backup_new_code(session: SessionDep) -> backup.BackupInfo:
    backup.renew_code(session)
    session.commit()
    return backup.info(session)


# Not async: the copy, the decryption and the database swap block, so they run in FastAPI's
# thread pool rather than on the event loop.
@router.post("/backup/restore", status_code=204)
def backup_restore(file: UploadFile, code: Annotated[str, Form(max_length=64)]) -> None:
    with Session(get_engine()) as session:
        count = session.exec(select(func.count()).select_from(Document)).one()
    if count:
        raise HTTPException(409, T("library_not_empty"))
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "backup.zip"
        with archive.open("wb") as f:
            shutil.copyfileobj(file.file, f, 1 << 20)
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
