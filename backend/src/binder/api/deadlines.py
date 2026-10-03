"""Deadline routes: list, reminders created by the user, edit, delete."""

from datetime import date

from fastapi import APIRouter, Response
from sqlmodel import Session, col, select

from binder import i18n
from binder.api.assistant import undoable
from binder.api.common import SessionDep, get_or_404
from binder.models import Deadline
from binder.schemas import DeadlineCreate, DeadlineOut, DeadlineUpdate
from binder.services import activity, editing, undo

router = APIRouter(prefix="/api")

T = i18n.catalog(
    "api",
    {
        "deadline_not_found": {"en": "Deadline not found", "fr": "Échéance introuvable"},
        # Activity log.
        "reminder_created": {
            "en": "Reminder “{title}” created for {due:date}",
            "fr": "Rappel « {title} » créé pour le {due:date}",
        },
        "deadline_deleted": {
            "en": "Deadline “{title}” deleted",
            "fr": "Échéance « {title} » supprimée",
        },
    },
)


def _deadline(session: Session, deadline_id: int) -> Deadline:
    return get_or_404(session, Deadline, deadline_id, T("deadline_not_found"))


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
    deadline = _deadline(session, deadline_id)
    with undoable(session, response):
        editing.update_deadline(session, deadline, body.model_dump(exclude_unset=True))
    session.commit()
    session.refresh(deadline)
    return DeadlineOut.from_model(deadline, date.today())


@router.delete("/deadlines/{deadline_id}", status_code=204)
def delete_deadline(deadline_id: int, session: SessionDep, response: Response) -> None:
    deadline = _deadline(session, deadline_id)
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
