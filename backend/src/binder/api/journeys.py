"""Routes of the guided journeys (services/journeys.py): moving, a birth, a death, the tax
return."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from binder import i18n
from binder.api.assistant import undoable
from binder.api.common import SessionDep, get_or_404
from binder.models import Journey
from binder.services import activity, journeys, undo

router = APIRouter(prefix="/api/journeys")

T = i18n.catalog(
    "journeys_api",
    {
        "archive_only": {
            "en": "Only archived journeys can be deleted",
            "fr": "Seules les démarches archivées peuvent être supprimées",
        },
        "confirm": {
            "en": "Confirm permanent deletion",
            "fr": "Confirmez la suppression définitive",
        },
        "trashed": {
            "en": "I moved “{title}” to the trash",
            "fr": "J'ai placé « {title} » dans la corbeille",
        },
        "restored": {
            "en": "I restored “{title}” to the archives",
            "fr": "J'ai restauré « {title} » dans les archives",
        },
        "purged": {
            "en": "I permanently deleted “{title}”",
            "fr": "J'ai supprimé définitivement « {title} »",
        },
        "not_found": {"en": "Journey not found", "fr": "Démarche introuvable"},
    },
)


class JourneyRequest(BaseModel):
    kind: str
    event_date: date | None = None
    details: dict[str, str] = Field(default_factory=dict)


class JourneyEdit(BaseModel):
    event_date: date | None = None
    details: dict[str, str] | None = None
    closed: bool | None = None


class StepEdit(BaseModel):
    done: bool


def _journey(session: Session, journey_id: int, *, trashed: bool = False) -> Journey:
    row = get_or_404(session, Journey, journey_id, T("not_found"))
    if (row.deleted_at is not None) != trashed:
        raise HTTPException(404, T("not_found"))
    return row


@router.get("/kinds")
def list_kinds() -> list[journeys.KindInfo]:
    return journeys.kinds()


@router.get("")
def list_journeys(session: SessionDep) -> list[journeys.JourneyOut]:
    rows = session.exec(
        select(Journey)
        .where(col(Journey.deleted_at).is_(None))
        .order_by(col(Journey.closed), col(Journey.event_date))
    )
    return [journeys.out(session, row) for row in rows]


@router.post("")
def start_journey(
    body: JourneyRequest, session: SessionDep, response: Response
) -> journeys.JourneyOut:
    try:
        with undoable(session, response):
            row = journeys.start(session, body.kind, body.event_date, body.details)
    except journeys.UnknownKind as e:
        raise HTTPException(400, journeys.T("unknown_kind")) from e
    session.commit()
    return journeys.out(session, row)


@router.get("/trash")
def list_trashed_journeys(session: SessionDep) -> list[journeys.JourneyOut]:
    rows = session.exec(
        select(Journey)
        .where(col(Journey.deleted_at).is_not(None))
        .order_by(col(Journey.deleted_at).desc())
    )
    return [journeys.out(session, row) for row in rows]


@router.delete("/{journey_id}", status_code=204)
def trash_journey(journey_id: int, session: SessionDep, response: Response) -> None:
    row = _journey(session, journey_id)
    if not row.closed:
        raise HTTPException(409, T("archive_only"))
    with undoable(session, response):
        undo.row_changed(row)
        row.deleted_at = datetime.now(UTC)
        session.add(row)
        activity.log(session, "journey", T.msg("trashed", title=journeys.title(row)), actor="user")
    session.commit()


@router.post("/{journey_id}/restore")
def restore_journey(
    journey_id: int, session: SessionDep, response: Response
) -> journeys.JourneyOut:
    row = _journey(session, journey_id, trashed=True)
    with undoable(session, response):
        undo.row_changed(row)
        row.deleted_at = None
        session.add(row)
        activity.log(session, "journey", T.msg("restored", title=journeys.title(row)), actor="user")
    session.commit()
    return journeys.out(session, row)


@router.delete("/{journey_id}/permanent", status_code=204)
def purge_journey(journey_id: int, session: SessionDep, confirm: bool = False) -> None:
    if not confirm:
        raise HTTPException(400, T("confirm"))
    row = _journey(session, journey_id, trashed=True)
    activity.log(session, "journey", T.msg("purged", title=journeys.title(row)), actor="user")
    session.delete(row)
    session.commit()


@router.get("/{journey_id}")
def get_journey(journey_id: int, session: SessionDep) -> journeys.JourneyOut:
    return journeys.out(session, _journey(session, journey_id))


@router.patch("/{journey_id}")
def edit_journey(
    journey_id: int, body: JourneyEdit, session: SessionDep, response: Response
) -> journeys.JourneyOut:
    row = _journey(session, journey_id)
    with undoable(session, response):
        journeys.update(
            session, row, event_date=body.event_date, details=body.details, closed=body.closed
        )
    session.commit()
    return journeys.out(session, row)


@router.put("/{journey_id}/steps/{key}")
def edit_step(
    journey_id: int, key: str, body: StepEdit, session: SessionDep, response: Response
) -> journeys.JourneyOut:
    row = _journey(session, journey_id)
    try:
        with undoable(session, response):
            journeys.set_step(session, row, key, body.done)
    except journeys.UnknownStep as e:
        raise HTTPException(404, journeys.T("unknown_step")) from e
    session.commit()
    return journeys.out(session, row)
