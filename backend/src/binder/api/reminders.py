"""Routes of the reminders while Binder is closed (services/reminders.py)."""

from fastapi import APIRouter
from pydantic import BaseModel

from binder.api.common import SessionDep
from binder.services import os_task, reminders

router = APIRouter(prefix="/api/reminders")


class RemindersOut(BaseModel):
    enabled: bool
    # The system can start Binder while it is closed (the installed application).
    available: bool
    hour: int


class RemindersIn(BaseModel):
    enabled: bool


def _out(settings: reminders.ReminderSettings) -> RemindersOut:
    return RemindersOut(
        enabled=settings.enabled, available=reminders.available(), hour=os_task.HOUR
    )


@router.get("")
def get_reminders(session: SessionDep) -> RemindersOut:
    return _out(reminders.load(session))


@router.put("")
def update_reminders(body: RemindersIn, session: SessionDep) -> RemindersOut:
    settings = reminders.update(session, body.enabled)
    session.commit()
    return _out(settings)
