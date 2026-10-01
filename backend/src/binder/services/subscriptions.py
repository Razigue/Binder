"""Abonnements et factures récurrentes : regroupement par émetteur, rythme, hausses.

Une série = au moins deux documents du même émetteur, de même type et de même catégorie,
avec un montant. Une hausse est signalée quand le dernier montant dépasse le précédent
de 10 % et d'au moins 2 €.
"""

from datetime import date
from statistics import median

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder.models import Category, Document
from binder.services import activity
from binder.services.rules import normalize

RECURRING_TYPES = {"Facture", "Avis d'échéance", "Quittance de loyer", "Échéancier"}
RECURRING_CATEGORIES = {Category.ENERGIE, Category.TELECOM, Category.ASSURANCE, Category.LOGEMENT}
INCREASE_RATIO = 0.10
INCREASE_MIN = 2.0

CADENCES = [
    (25, 35, "mensuel"),
    (50, 70, "bimestriel"),
    (80, 100, "trimestriel"),
    (170, 200, "semestriel"),
    (330, 400, "annuel"),
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
    cadence: str
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
    if not who and doc.doc_type != "Quittance de loyer":
        return None
    return f"{doc.category.name}|{doc.doc_type or ''}|{who}"


def _date(doc: Document) -> date:
    return doc.issue_date or doc.due_date or doc.created_at.date()


def _cadence(interval: float | None) -> str:
    if interval is None:
        return "irrégulier"
    return next((name for lo, hi, name in CADENCES if lo <= interval <= hi), "irrégulier")


def _build(key: str, docs: list[Document]) -> Subscription:
    docs = sorted(docs, key=lambda d: (_date(d), d.id or 0))
    gaps = [(_date(b) - _date(a)).days for a, b in zip(docs, docs[1:], strict=False)]
    gaps = [g for g in gaps if g > 0]
    interval = median(gaps) if gaps else None
    last, previous = docs[-1], docs[-2]
    assert last.amount is not None and previous.amount is not None
    change = (last.amount - previous.amount) / previous.amount if previous.amount else 0.0
    label = "Loyer" if last.doc_type == "Quittance de loyer" else last.issuer or last.title
    return Subscription(
        key=key,
        label=label,
        category=last.category,
        doc_type=last.doc_type,
        cadence=_cadence(interval),
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


def detect(session: Session) -> list[Subscription]:
    groups: dict[str, list[Document]] = {}
    for doc in session.exec(select(Document).where(col(Document.deleted_at).is_(None))):
        key = _key(doc)
        if key:
            groups.setdefault(key, []).append(doc)
    subs = [_build(k, docs) for k, docs in groups.items() if len(docs) >= 2]
    return sorted(subs, key=lambda s: (not s.increase, -(s.yearly_estimate or s.last_amount)))


def check_increase(session: Session, doc: Document) -> None:
    """Après l'analyse d'un document : journalise une hausse s'il est le dernier de sa série."""
    key = _key(doc)
    if key is None:
        return
    sub = next((s for s in detect(session) if s.key == key), None)
    if sub is None or not sub.increase or sub.history[-1].document_id != doc.id:
        return
    activity.log(
        session,
        "increase",
        f"Hausse de {sub.change_pct:.0f} % sur {sub.label} : "
        f"{activity.display(sub.last_amount)} contre {activity.display(sub.previous_amount)}",
        document=doc,
        details={"avant": sub.previous_amount, "apres": sub.last_amount},
    )
