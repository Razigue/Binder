"""Import report: what Binder did with each document of a batch, in plain sentences.

Shown right after a drop of files, a phone scan, or documents arriving by email or in the
watched folder: where each document went, what it asks of the user (amount and date to pay,
renewal), what Binder did on its own (replaced an older version, noticed a price rise or an
anomaly, applied a past correction) and the questions still open.
"""

import json
from datetime import date

from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from binder import i18n
from binder.db import WITHOUT_TEXT
from binder.models import Activity, Deadline, Document, DocumentStatus
from binder.schemas import DocumentOut
from binder.services import (
    activity,
    archive,
    areas,
    deadlines,
    questions,
    retention,
    settings_store,
    undo,
)

T = i18n.catalog(
    "reports",
    {
        "filed": {"en": "Filed under {area}", "fr": "Rangé dans {area}"},
        "to_pay": {
            "en": "{amount:money} to pay by {date:date}",
            "fr": "{amount:money} à payer avant le {date:date}",
        },
        "pay_by": {"en": "To pay by {date:date}", "fr": "À payer avant le {date:date}"},
        "valid_until": {"en": "Valid until {date:date}", "fr": "Valable jusqu'au {date:date}"},
        "renew_from": {
            "en": "Renew it from {date:date}",
            "fr": "À renouveler à partir du {date:date}",
        },
        "amount": {"en": "Amount: {amount:money}", "fr": "Montant : {amount:money}"},
        "for_person": {"en": "Concerns {person}", "fr": "Concerne {person}"},
        "question": {"en": "One question for you", "fr": "Une question pour vous"},
        "summary_filed_one": {"en": "{n} document filed", "fr": "{n} document rangé"},
        "summary_filed_other": {"en": "{n} documents filed", "fr": "{n} documents rangés"},
        "brief_nothing": {"en": "Nothing to do", "fr": "Rien à faire"},
        "brief_archived": {
            "en": "Old paper, kept in the archives",
            "fr": "Ancien papier, gardé aux archives",
        },
        "brief_keep": {"en": "kept: {keep}", "fr": "gardé : {keep}"},
        "summary_archived_one": {
            "en": "{n} old document archived",
            "fr": "{n} ancien document archivé",
        },
        "summary_archived_other": {
            "en": "{n} old documents archived",
            "fr": "{n} anciens documents archivés",
        },
        "archived": {
            "en": "Archived: {reason}",
            "fr": "Archivé : {reason}",
        },
        "summary_waiting_one": {
            "en": "{n} waiting for the local AI",
            "fr": "{n} en attente de l'IA locale",
        },
        "summary_waiting_other": {
            "en": "{n} waiting for the local AI",
            "fr": "{n} en attente de l'IA locale",
        },
        "summary_questions_one": {"en": "{n} question", "fr": "{n} question"},
        "summary_questions_other": {"en": "{n} questions", "fr": "{n} questions"},
        "summary_to_pay": {
            "en": "{amount:money} to pay",
            "fr": "{amount:money} à payer",
        },
        "summary_events_one": {"en": "{n} thing to know", "fr": "{n} point à savoir"},
        "summary_events_other": {"en": "{n} things to know", "fr": "{n} points à savoir"},
        "separator": {"en": " · ", "fr": " · "},
    },
)

SEEN_KEY = "reports.seen"
# Activity worth reporting: what Binder did on its own after reading the document.
EVENTS = {"supersede", "increase", "anomaly", "learned", "duplicate"}


class ReportItem(BaseModel):
    document: DocumentOut
    # "In short", right away: what it is, whether to act and by when, how long it is kept.
    brief: str = ""
    facts: list[str]
    events: list[str]
    question: questions.Question | None = None


class ImportReport(BaseModel):
    batch: str
    source: str
    processing: int
    items: list[ReportItem]
    summary: str
    to_pay: float


class Seen(BaseModel):
    batches: list[str] = []


def source_of(batch: str) -> str:
    return batch.split("-", 1)[0]


def _facts(doc: Document) -> list[str]:
    """Details under the brief line: what it does not say already (the payment and the renewal
    are in it)."""
    if doc.archived_at is not None:
        return [T("archived", reason=archive.reason_msg(doc.archive_reason))]
    facts = []
    area = doc.area or areas.area_of(doc)
    if area and doc.status not in (DocumentStatus.PROCESSING, DocumentStatus.WAITING):
        facts.append(T("filed", area=areas.label(area)))
    due = doc.due_date is not None and doc.due_date >= date.today()
    if not due and doc.amount is not None:
        facts.append(T("amount", amount=doc.amount))
    if doc.expiry_date and doc.superseded_by is None and doc.expiry_date >= date.today():
        renew = deadlines.renew_from(doc)
        if renew and renew > date.today():
            facts.append(T("valid_until", date=doc.expiry_date))
    if doc.person:
        facts.append(T("for_person", person=doc.person))
    return facts


def brief(doc: Document, today: date | None = None) -> str:
    """One line on a document just added: "Tax notice · $1,240 to pay by 7 Oct · kept: 3 years
    after the tax year"."""
    if doc.status in (DocumentStatus.PROCESSING, DocumentStatus.WAITING):
        return ""
    today = today or date.today()
    what = i18n.doc_type_label(doc.doc_type) if doc.doc_type else i18n.category_label(doc.category)
    if doc.archived_at is not None:
        action = T("brief_archived")
    elif doc.due_date and doc.due_date >= today:
        action = (
            T("to_pay", amount=doc.amount, date=doc.due_date)
            if doc.amount is not None
            else T("pay_by", date=doc.due_date)
        )
    elif doc.expiry_date and doc.expiry_date >= today and doc.superseded_by is None:
        renew = deadlines.renew_from(doc)
        action = (
            T("renew_from", date=renew)
            if renew and renew > today
            else T("valid_until", date=doc.expiry_date)
        )
    else:
        action = T("brief_nothing")
    parts = [what, action[:1].lower() + action[1:]]
    rule = retention.rule_for(doc)
    if rule is not None:
        label = rule.label
        parts.append(T("brief_keep", keep=label[:1].lower() + label[1:]))
    return T("separator").join(parts)


def build(session: Session, batch: str) -> ImportReport | None:
    docs = list(
        session.exec(
            select(Document)
            .where(Document.batch == batch, col(Document.deleted_at).is_(None))
            .order_by(col(Document.id))
        )
    )
    if not docs:
        return None
    ids = [d.id for d in docs]
    entries = session.exec(
        select(Activity)
        .where(col(Activity.document_id).in_(ids), col(Activity.action).in_(EVENTS))
        .order_by(col(Activity.id))
    ).all()
    events: dict[int, list[str]] = {}
    for entry in entries:
        assert entry.document_id is not None
        events.setdefault(entry.document_id, []).append(
            activity.summary(entry, json.loads(entry.details))
        )
    items = []
    for doc in docs:
        assert doc.id is not None
        items.append(
            ReportItem(
                document=DocumentOut.from_model(doc),
                brief=brief(doc),
                facts=_facts(doc),
                events=events.get(doc.id, []),
                question=questions.question_for(session, doc),
            )
        )
    processing = sum(d.status == DocumentStatus.PROCESSING for d in docs)
    waiting = sum(d.status == DocumentStatus.WAITING for d in docs)
    to_pay = round(
        sum(
            d.amount or 0
            for d in docs
            if d.due_date
            and d.due_date >= date.today()
            and d.amount is not None
            and d.archived_at is None
        ),
        2,
    )
    asked = sum(i.question is not None for i in items)
    noted = sum(len(i.events) for i in items)
    old = sum(d.archived_at is not None for d in docs)
    parts = [T.plural("summary_filed", len(docs) - processing - waiting - asked - old)]
    if old:
        parts.append(T.plural("summary_archived", old))
    if waiting:
        parts.append(T.plural("summary_waiting", waiting))
    if asked:
        parts.append(T.plural("summary_questions", asked))
    if to_pay:
        parts.append(T("summary_to_pay", amount=to_pay))
    if noted:
        parts.append(T.plural("summary_events", noted))
    return ImportReport(
        batch=batch,
        source=source_of(batch),
        processing=processing,
        items=items,
        summary=T("separator").join(parts),
        to_pay=to_pay,
    )


def latest_unseen(session: Session) -> list[str]:
    """Batches imported in the background that the user has not looked at yet, newest first."""
    seen = set(settings_store.load(session, SEEN_KEY, Seen).batches)
    rows = session.exec(
        select(Document.batch, func.max(Document.created_at))
        .where(col(Document.batch).is_not(None), col(Document.deleted_at).is_(None))
        .group_by(Document.batch)
        .order_by(func.max(Document.created_at).desc())
        .limit(5)
    ).all()
    return [b for b, _ in rows if b and b not in seen]


def mark_seen(session: Session, batch: str) -> None:
    undo.setting_changed(session, SEEN_KEY)
    seen = settings_store.load(session, SEEN_KEY, Seen)
    if batch not in seen.batches:
        seen.batches = [*seen.batches[-99:], batch]
        settings_store.save(session, SEEN_KEY, seen)


def batch_documents(session: Session, batch: str) -> list[Document]:
    return list(
        session.exec(select(Document).options(*WITHOUT_TEXT).where(Document.batch == batch))
    )


def unpaid(session: Session, doc: Document) -> list[Deadline]:
    return list(
        session.exec(
            select(Deadline).where(Deadline.document_id == doc.id, Deadline.done == False)  # noqa: E712
        )
    )
