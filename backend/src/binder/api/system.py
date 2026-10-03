"""System routes: status, preferences, dashboard counts, activity log, demo and erasing."""

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func
from sqlmodel import col, select

from binder import __version__, i18n
from binder.api.common import ACTIVE, SessionDep
from binder.config import get_settings
from binder.db import in_use
from binder.models import Activity, Category, Deadline, Document, DocumentStatus
from binder.schemas import (
    ActivityOut,
    DemoCleared,
    DemoImported,
    DemoStatus,
    ErasedData,
    PreferencesOut,
    Stats,
    SystemStatus,
)
from binder.services import erase, ingest, llm, preferences
from binder.services.text import ocr_engine

router = APIRouter(prefix="/api")

T = i18n.catalog(
    "api",
    {
        "confirm_erase": {
            "en": "Erasing all data: confirmation required (confirm=true)",
            "fr": "Effacement de toutes les données : confirmation requise (confirm=true)",
        },
    },
)


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
        select(func.count()).where(Document.status == DocumentStatus.TO_REVIEW, in_use())
    ).one()
    classified = session.exec(
        select(func.count())
        .where(Document.status == DocumentStatus.CLASSIFIED, in_use())
        .where(Document.created_at >= week_ago)
    ).one()
    total = session.exec(select(func.count()).select_from(Document).where(in_use())).one()
    trashed = session.exec(select(func.count()).select_from(Document).where(~ACTIVE)).one()
    archived = session.exec(
        select(func.count())
        .select_from(Document)
        .where(ACTIVE, col(Document.archived_at).is_not(None))
    ).one()
    rows = session.exec(
        select(Document.category, func.count()).where(in_use()).group_by(Document.category)
    ).all()
    return Stats(
        upcoming_deadlines=upcoming,
        to_review=to_review,
        classified_this_week=classified,
        total_documents=total,
        trashed=trashed,
        archived=archived,
        by_category={Category(cat).value: n for cat, n in rows},
    )


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


@router.post("/demo")
def seed_demo(session: SessionDep) -> DemoImported:
    """Imports the fictitious demo documents."""
    results = ingest.seed_demo(session)
    batch = next((doc.batch for doc, created in results if created), None)
    return DemoImported(imported=sum(created for _, created in results), batch=batch)


@router.get("/demo")
def demo_status(session: SessionDep) -> DemoStatus:
    """Demo documents in the library and demo files older versions left behind (Settings
    offers to clear them, or to load the demo when there is none)."""
    return DemoStatus(
        documents=len(ingest.demo_documents(session)),
        leftovers=len(ingest.demo_leftover_files(session)),
    )


@router.delete("/demo")
def clear_demo(session: SessionDep) -> DemoCleared:
    """Permanently removes the demo documents, what came from them and leftover demo files."""
    removed, files = ingest.clear_demo(session)
    session.commit()
    for path in files:
        path.unlink(missing_ok=True)
    return DemoCleared(removed=removed, files=len(files))


@router.delete("/data")
def erase_data(session: SessionDep, confirm: bool = False) -> ErasedData:
    """Permanently erases everything Binder holds about the user (Settings); `confirm=true`."""
    if not confirm:
        raise HTTPException(428, T("confirm_erase"))
    removed = erase.erase_all(session)
    session.commit()
    erase.delete_files(session)
    return ErasedData(removed=removed)
