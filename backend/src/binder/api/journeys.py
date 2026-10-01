"""Routes of the guided journeys (services/journeys.py): moving, a birth, a death, the tax
return."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from binder import i18n
from binder.api.assistant import undoable
from binder.db import get_session
from binder.models import Journey
from binder.services import journeys

router = APIRouter(prefix="/api/journeys")
SessionDep = Annotated[Session, Depends(get_session)]

T = i18n.catalog(
    "journeys_api",
    {
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


def _journey(session: Session, journey_id: int) -> Journey:
    row = session.get(Journey, journey_id)
    if row is None:
        raise HTTPException(404, T("not_found"))
    return row


@router.get("/kinds")
def list_kinds() -> list[journeys.KindInfo]:
    return journeys.kinds()


@router.get("")
def list_journeys(session: SessionDep) -> list[journeys.JourneyOut]:
    rows = session.exec(
        select(Journey).order_by(col(Journey.closed), col(Journey.event_date)).limit(50)
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
