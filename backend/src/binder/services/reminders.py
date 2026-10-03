"""Reminders while Binder is closed: one notification a day at most, only when it matters.

The system starts `Binder --remind` every morning and after login (services/os_task.py). The run
opens the encrypted database with the key on this computer, builds the To do feed, and shows one
notification summing it up: "3 things to do · Property tax 2026: fetch it". It stays silent when
Binder is open (it notifies on its own), when nothing is urgent and nothing new appeared since
the last reminder, and when it already spoke today. It never starts the local AI.
"""

import logging
import threading
from datetime import date

from pydantic import BaseModel
from sqlmodel import Session

from binder import i18n
from binder.config import get_settings
from binder.services import activity, feed, instance, notify, os_task, settings_store

log = logging.getLogger(__name__)

T = i18n.catalog(
    "reminders",
    {
        "title_one": {"en": "Binder: {n} thing to do", "fr": "Binder : {n} chose à faire"},
        "title_other": {"en": "Binder: {n} things to do", "fr": "Binder : {n} choses à faire"},
        "body": {
            "en": "{first}. Open Binder to see it.",
            "fr": "{first}. Ouvrez Binder pour le voir.",
        },
        "body_more_one": {
            "en": "{first}, and {n} more. Open Binder to see them.",
            "fr": "{first}, et {n} autre. Ouvrez Binder pour les voir.",
        },
        "body_more_other": {
            "en": "{first}, and {n} more. Open Binder to see them.",
            "fr": "{first}, et {n} autres. Ouvrez Binder pour les voir.",
        },
        "enabled": {
            "en": "Reminders while Binder is closed turned on",
            "fr": "Rappels quand Binder est fermé activés",
        },
        "disabled": {
            "en": "Reminders while Binder is closed turned off",
            "fr": "Rappels quand Binder est fermé désactivés",
        },
    },
)

KEY = "reminders"
STATE_KEY = "reminders.state"
# Cards worth a reminder: what has a date, what is wrong, what to fetch or to check.
KINDS = {"deadline", "expiry", "anomaly", "missing", "right", "journey", "letter"}
# Cards already reminded of, remembered to tell what is new (oldest dropped first).
REMEMBER = 300


class ReminderSettings(BaseModel):
    enabled: bool = True


class ReminderState(BaseModel):
    last_day: date | None = None
    seen: list[str] = []


class Reminder(BaseModel):
    title: str
    body: str
    keys: list[str]


def load(session: Session) -> ReminderSettings:
    return settings_store.load(session, KEY, ReminderSettings)


def available() -> bool:
    """The system can start Binder while it is closed (the packaged application)."""
    return get_settings().notifications and os_task.command() is not None


def compose(session: Session, today: date | None = None) -> Reminder | None:
    """Today's reminder, or None when there is no reason to interrupt the user."""
    today = today or date.today()
    state = settings_store.load(session, STATE_KEY, ReminderState)
    if state.last_day == today:
        return None
    cards = [i for i in feed.build(session, today) if i.kind in KINDS]
    seen = set(state.seen)
    new = [i for i in cards if i.key not in seen]
    if not new and not any(i.tone == "urgent" for i in cards):
        return None
    # The most urgent first (the feed's order), what is new before what was already said.
    ranked = sorted(cards, key=lambda i: (feed.TONE_RANK[i.tone], i.key in seen))
    first = ranked[0].title.rstrip(".")
    more = len(ranked) - 1
    return Reminder(
        title=T.plural("title", len(ranked)),
        body=T.plural("body_more", more, first=first) if more else T("body", first=first),
        keys=[i.key for i in cards],
    )


def mark_sent(session: Session, reminder: Reminder, today: date | None = None) -> None:
    state = settings_store.load(session, STATE_KEY, ReminderState)
    state.last_day = today or date.today()
    state.seen = [k for k in state.seen if k not in reminder.keys] + reminder.keys
    state.seen = state.seen[-REMEMBER:]
    settings_store.save(session, STATE_KEY, state)


def remind() -> bool:
    """`binder --remind`: shows today's reminder if there is one. True if shown."""
    settings = get_settings()
    if not settings.notifications or not settings.db_path.exists():
        return False
    if instance.running():
        return False
    from binder.db import get_engine

    with Session(get_engine()) as session:
        if not load(session).enabled:
            return False
        reminder = compose(session)
        if reminder is None or not notify.send(reminder.title, reminder.body):
            return False
        mark_sent(session, reminder)
        session.commit()
    return True


def sync(session: Session) -> None:
    """Puts the system task in step with the setting (at each launch and on change)."""
    cmd = os_task.command()
    if cmd is None:
        return
    enabled = load(session).enabled and get_settings().notifications
    # schtasks and launchctl take a moment: never in the way of a request or the start.
    target = (lambda: os_task.register(cmd)) if enabled else os_task.unregister
    threading.Thread(target=target, name="binder-os-task", daemon=True).start()


def update(session: Session, enabled: bool) -> ReminderSettings:
    current = load(session)
    if current.enabled != enabled:
        current.enabled = enabled
        settings_store.save(session, KEY, current)
        activity.log(session, "settings", T.msg("enabled" if enabled else "disabled"), actor="user")
    sync(session)
    return current
