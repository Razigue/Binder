"""Weekly briefing: the week ahead in a few sentences, every Monday (or at the first launch of
the week), with a system notification.

The figures come from the library (payments of the week, late ones, renewals, anomalies,
questions, missing documents); the local model words them, the rules otherwise.
"""

import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from binder import i18n
from binder.db import WITHOUT_TEXT, in_use
from binder.models import Correspondence, Deadline, Document
from binder.services import anomalies, deadlines, llm, missing, questions, settings_store

log = logging.getLogger(__name__)

T = i18n.catalog(
    "briefing",
    {
        "title": {"en": "Your week of {monday:date}", "fr": "Votre semaine du {monday:date}"},
        "pay_one": {
            "en": "{n} payment this week, {amount:money} in all.",
            "fr": "{n} paiement cette semaine, {amount:money} en tout.",
        },
        "pay_other": {
            "en": "{n} payments this week, {amount:money} in all.",
            "fr": "{n} paiements cette semaine, {amount:money} en tout.",
        },
        "nothing_to_pay": {
            "en": "Nothing to pay this week.",
            "fr": "Rien à payer cette semaine.",
        },
        "late_one": {"en": "{n} is late.", "fr": "{n} est en retard."},
        "late_other": {"en": "{n} are late.", "fr": "{n} sont en retard."},
        "renew_one": {
            "en": "{n} document to renew soon.",
            "fr": "{n} document à renouveler bientôt.",
        },
        "renew_other": {
            "en": "{n} documents to renew soon.",
            "fr": "{n} documents à renouveler bientôt.",
        },
        "anomalies_one": {
            "en": "Binder spotted {n} thing to check.",
            "fr": "Binder a repéré {n} point à vérifier.",
        },
        "anomalies_other": {
            "en": "Binder spotted {n} things to check.",
            "fr": "Binder a repéré {n} points à vérifier.",
        },
        "questions_one": {
            "en": "{n} quick question is waiting for you.",
            "fr": "{n} petite question vous attend.",
        },
        "questions_other": {
            "en": "{n} quick questions are waiting for you.",
            "fr": "{n} petites questions vous attendent.",
        },
        "added_one": {
            "en": "{n} document filed last week.",
            "fr": "{n} document rangé la semaine dernière.",
        },
        "added_other": {
            "en": "{n} documents filed last week.",
            "fr": "{n} documents rangés la semaine dernière.",
        },
        "all_good": {
            "en": "Nothing urgent. Everything is in order.",
            "fr": "Rien d'urgent. Tout est en ordre.",
        },
        "notification": {"en": "Your week is ready", "fr": "Votre point de la semaine est prêt"},
    },
)

KEY = "briefing"
PROMPT = """Write the user's weekly paperwork briefing in {language}: 2 or 3 short, calm \
sentences, second person, no greeting, no list, exact figures, amounts in {currency}. Facts \
(JSON): {facts}"""


class Briefing(BaseModel):
    week: str
    created_at: datetime
    title: str
    text: str
    to_pay: float = 0.0
    figures: dict[str, Any] = {}


def week_of(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def current(session: Session, today: date | None = None) -> Briefing | None:
    today = today or date.today()
    row = settings_store.load(session, KEY, _Stored)
    if row.briefing is None or row.briefing.week != week_of(today):
        return None
    return row.briefing


class _Stored(BaseModel):
    briefing: Briefing | None = None


def figures(session: Session, today: date) -> dict[str, Any]:
    week_end = today + timedelta(days=6 - today.weekday())
    open_rows = session.exec(
        select(Deadline)
        .where(Deadline.done == False, Deadline.due_date <= week_end)  # noqa: E712
        .where(col(Deadline.source).in_(["extracted", "manual"]))
    ).all()
    this_week = [d for d in open_rows if d.due_date >= today]
    late = [d for d in open_rows if d.due_date < today]
    expiring = session.exec(
        select(Document)
        .options(*WITHOUT_TEXT)
        .where(
            in_use(),
            col(Document.expiry_date).is_not(None),
            col(Document.superseded_by).is_(None),
        )
    ).all()
    renew = [
        d
        for d in expiring
        if d.expiry_date is not None
        and (deadlines.renew_from(d) or d.expiry_date) <= today + timedelta(days=30)
    ]
    added = session.exec(
        select(func.count())
        .select_from(Document)
        .where(col(Document.deleted_at).is_(None))
        .where(col(Document.created_at) >= datetime.now(UTC) - timedelta(days=7))
    ).one()
    waiting = session.exec(
        select(func.count())
        .select_from(Correspondence)
        .where(col(Correspondence.sent_on).is_not(None), Correspondence.answered == False)  # noqa: E712
    ).one()
    return {
        "payments_this_week": len(this_week),
        "amount_this_week": round(sum(d.amount or 0 for d in this_week), 2),
        "payments": [
            {"title": d.title, "date": d.due_date.isoformat(), "amount": d.amount}
            for d in this_week[:6]
        ],
        "late": len(late),
        "to_renew": len(renew),
        "anomalies": len(anomalies.detect(session, today)),
        "questions": len(questions.pending(session)),
        "missing": len(missing.detect(session, today)),
        "filed_last_week": added,
        "letters_awaiting_answer": waiting,
    }


def _rules_text(f: dict[str, Any]) -> str:
    parts = []
    if f["payments_this_week"]:
        parts.append(T.plural("pay", f["payments_this_week"], amount=f["amount_this_week"]))
    else:
        parts.append(T("nothing_to_pay"))
    for key, name in (
        ("late", "late"),
        ("to_renew", "renew"),
        ("anomalies", "anomalies"),
        ("questions", "questions"),
        ("filed_last_week", "added"),
    ):
        if f[key]:
            parts.append(T.plural(name, f[key]))
    if len(parts) == 1 and not f["payments_this_week"]:
        parts.append(T("all_good"))
    return " ".join(parts)


def _llm_text(f: dict[str, Any]) -> str | None:
    context = llm.user_context()
    prompt = PROMPT.format(
        language=context["language"], currency=context["currency"], facts=json.dumps(f)
    )
    try:
        reply = llm.chat([{"role": "user", "content": prompt}])
    except (httpx.HTTPError, KeyError, ValueError):
        log.exception("Briefing by the model failed")
        return None
    text = str(reply.get("content") or "").strip()
    return text[:800] or None


def ensure(session: Session, today: date | None = None) -> Briefing | None:
    """Writes this week's briefing if it does not exist yet; returns it only when new."""
    today = today or date.today()
    if current(session, today) is not None:
        return None
    if not session.exec(select(func.count()).select_from(Document)).one():
        return None
    f = figures(session, today)
    text = (_llm_text(f) if llm.is_available() else None) or _rules_text(f)
    monday = today - timedelta(days=today.weekday())
    briefing = Briefing(
        week=week_of(today),
        created_at=datetime.now(UTC),
        title=T("title", monday=monday),
        text=text,
        to_pay=f["amount_this_week"],
        figures=f,
    )
    settings_store.save(session, KEY, _Stored(briefing=briefing))
    session.commit()
    return briefing


def notification_title() -> str:
    return T("notification")
