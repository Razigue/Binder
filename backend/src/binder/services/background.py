"""Background work while Binder runs: automatic import, system notifications, the weekly
briefing and the daily backup. One thread, each task at its own pace; a failing task never
stops the others."""

import logging
import threading
import time
from collections.abc import Callable

from sqlmodel import Session

from binder import i18n
from binder.config import get_settings
from binder.db import get_engine
from binder.services import backup, briefing, feed, importers, notify, reports

log = logging.getLogger(__name__)

TICK = 30.0
ALERT_INTERVAL = 600.0
BRIEFING_INTERVAL = 3600.0
BACKUP_INTERVAL = 3600.0
# Cards worth interrupting the user for.
ALERT_KINDS = {"deadline", "expiry", "anomaly"}


def alerts(session: Session) -> int:
    """Notifies urgent cards and documents that arrived on their own. Returns how many."""
    sent = 0
    for item in feed.build(session):
        urgent = item.tone == "urgent" and item.kind in ALERT_KINDS
        arrived = item.kind == "report" and reports.source_of(item.extra["batch"]) in (
            "mail",
            "folder",
        )
        if (urgent or arrived) and notify.once(session, item.key, item.title, item.detail):
            sent += 1
    session.commit()
    return sent


def weekly(session: Session) -> None:
    new = briefing.ensure(session)
    if new is not None and get_settings().notifications:
        notify.once(session, f"briefing:{new.week}", briefing.notification_title(), new.text)
        session.commit()


class Scheduler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="binder-background", daemon=True)
        self._last: dict[str, float] = {}
        # Language of the user at start (the thread renders notifications and briefings).
        self._language = i18n.current_language()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _due(self, name: str, every: float) -> bool:
        now = time.monotonic()
        if now - self._last.get(name, -every) < every:
            return False
        self._last[name] = now
        return True

    def _run(self, name: str, task: Callable[[Session], object]) -> None:
        try:
            with Session(get_engine()) as session:
                task(session)
        except Exception:
            log.exception("Background task %s", name)

    def _loop(self) -> None:
        settings = get_settings()
        # First pass shortly after start: the interface is up before anything heavy runs.
        while not self._stop.wait(TICK):
            if settings.auto_import:
                check_mail = self._due("mail", importers.MAIL_INTERVAL)

                def imports(session: Session, mail: bool = check_mail) -> object:
                    return importers.run(session, mail=mail)

                self._run("import", imports)
            if self._due("briefing", BRIEFING_INTERVAL):
                self._run("briefing", weekly)
            if settings.notifications and self._due("alerts", ALERT_INTERVAL):
                self._run("alerts", alerts)
            if settings.auto_backup and self._due("backup", BACKUP_INTERVAL):
                self._run("backup", backup.run_if_due)


def enabled() -> bool:
    settings = get_settings()
    return settings.auto_import or settings.notifications or settings.auto_backup
