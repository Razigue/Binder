"""Subscriptions and recurring bills: grouped by issuer, with their rhythm and price increases.

A series = at least two documents from the same issuer, of the same type and category, with an
amount. An increase is flagged when the latest amount exceeds the previous one by 10% and by at
least 2 (in the user's currency).
"""

from datetime import date
from statistics import median

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT, in_use
from binder.models import Category, DocType, Document
from binder.services import activity
from binder.services.rules import normalize

T = i18n.catalog(
    "subscriptions",
    {
        "rent": {"en": "Rent", "fr": "Loyer"},
        "monthly": {"en": "monthly", "fr": "mensuel"},
        "bimonthly": {"en": "every two months", "fr": "bimestriel"},
        "quarterly": {"en": "quarterly", "fr": "trimestriel"},
        "half_yearly": {"en": "every six months", "fr": "semestriel"},
        "yearly": {"en": "yearly", "fr": "annuel"},
        "irregular": {"en": "irregular", "fr": "irrégulier"},
        "increase": {
            "en": "{label} up {pct:.0f}%: {last:money} instead of {previous:money}",
            "fr": "Hausse de {pct:.0f} % sur {label} : {last:money} contre {previous:money}",
        },
    },
)

RECURRING_TYPES = {
    DocType.INVOICE,
    DocType.PAYMENT_NOTICE,
    DocType.RENT_RECEIPT,
    DocType.PAYMENT_SCHEDULE,
}
RECURRING_CATEGORIES = {Category.ENERGY, Category.TELECOM, Category.INSURANCE, Category.HOUSING}
INCREASE_RATIO = 0.10
INCREASE_MIN = 2.0

# (min days, max days, cadence identifier); labels in T.
CADENCES = [
    (25, 35, "monthly"),
    (50, 70, "bimonthly"),
    (80, 100, "quarterly"),
    (170, 200, "half_yearly"),
    (330, 400, "yearly"),
]


class Point(BaseModel):
    document_id: int
    date: date
    amount: float


class Subscription(BaseModel):
    key: str
    label: str
    category: Category
    doc_type: str | None
    # Identifier ("monthly", "bimonthly", "quarterly", "half_yearly", "yearly", "irregular")
    # and its label in the interface language.
    cadence: str
    cadence_label: str
    interval_days: int | None
    last_amount: float
    previous_amount: float
    change_pct: float
    yearly_estimate: float | None
    increase: bool
    history: list[Point]


def _key(doc: Document) -> str | None:
    if doc.amount is None or doc.duplicate_of is not None or doc.deleted_at is not None:
        return None
    if doc.doc_type not in RECURRING_TYPES and doc.category not in RECURRING_CATEGORIES:
        return None
    who = normalize(doc.issuer or "")
    if not who and doc.doc_type != DocType.RENT_RECEIPT:
        return None
    return f"{doc.category.name}|{doc.doc_type or ''}|{who}"


def _date(doc: Document) -> date:
    return doc.issue_date or doc.due_date or doc.created_at.date()


def _cadence(interval: float | None) -> str:
    if interval is None:
        return "irregular"
    return next((name for lo, hi, name in CADENCES if lo <= interval <= hi), "irregular")


def _build(key: str, docs: list[Document]) -> Subscription:
    docs = sorted(docs, key=lambda d: (_date(d), d.id or 0))
    gaps = [(_date(b) - _date(a)).days for a, b in zip(docs, docs[1:], strict=False)]
    gaps = [g for g in gaps if g > 0]
    interval = median(gaps) if gaps else None
    last, previous = docs[-1], docs[-2]
    assert last.amount is not None and previous.amount is not None
    change = (last.amount - previous.amount) / previous.amount if previous.amount else 0.0
    label = T("rent") if last.doc_type == DocType.RENT_RECEIPT else last.issuer or last.title
    cadence = _cadence(interval)
    return Subscription(
        key=key,
        label=label,
        category=last.category,
        doc_type=last.doc_type,
        cadence=cadence,
        cadence_label=T(cadence),
        interval_days=round(interval) if interval else None,
        last_amount=last.amount,
        previous_amount=previous.amount,
        change_pct=round(change * 100, 1),
        yearly_estimate=round(last.amount * 365 / interval, 2) if interval else None,
        increase=change >= INCREASE_RATIO and last.amount - previous.amount >= INCREASE_MIN,
        history=[
            Point(document_id=d.id, date=_date(d), amount=d.amount)
            for d in docs
            if d.id is not None and d.amount is not None
        ],
    )


def detect(session: Session, like: Document | None = None) -> list[Subscription]:
    """`like`: only the series of this document (same category and type)."""
    stmt = (
        select(Document).options(*WITHOUT_TEXT).where(in_use(), col(Document.amount).is_not(None))
    )
    if like is not None:
        stmt = stmt.where(Document.category == like.category)
        stmt = stmt.where(
            col(Document.doc_type).is_(None)
            if like.doc_type is None
            else Document.doc_type == like.doc_type
        )
    groups: dict[str, list[Document]] = {}
    for doc in session.exec(stmt):
        key = _key(doc)
        if key:
            groups.setdefault(key, []).append(doc)
    subs = [_build(k, docs) for k, docs in groups.items() if len(docs) >= 2]
    return sorted(subs, key=lambda s: (not s.increase, -(s.yearly_estimate or s.last_amount)))


def check_increase(session: Session, doc: Document) -> None:
    """After a document is analysed: logs an increase if it is the latest of its series."""
    key = _key(doc)
    if key is None:
        return
    sub = next((s for s in detect(session, like=doc) if s.key == key), None)
    if sub is None or not sub.increase or sub.history[-1].document_id != doc.id:
        return
    activity.log(
        session,
        "increase",
        T.msg(
            "increase",
            pct=sub.change_pct,
            label=T.msg("rent") if sub.doc_type == DocType.RENT_RECEIPT else sub.label,
            last=sub.last_amount,
            previous=sub.previous_amount,
        ),
        document=doc,
        details={"before": sub.previous_amount, "after": sub.last_amount},
    )
