"""Deadlines deduced from documents: payment ("extracted") and end of validity ("expiry")."""

from datetime import date, timedelta

from sqlmodel import Session, select

from binder import i18n
from binder.models import Deadline, DocType, Document

T = i18n.catalog(
    "deadlines",
    {
        "expiry_title": {"en": "Expiry: {title}", "fr": "Fin de validité : {title}"},
        "warranty_title": {"en": "End of warranty: {title}", "fr": "Fin de garantie : {title}"},
    },
)

# Recommended lead time to start the renewal (appointment at the town hall, prefecture…).
NOTICE_DAYS: dict[str, int] = {
    DocType.IDENTITY_CARD: 90,
    DocType.PASSPORT: 120,
    DocType.RESIDENCE_PERMIT: 120,
    DocType.DRIVING_LICENCE: 90,
    DocType.ROADWORTHINESS_TEST: 30,
    # Time to have a fault repaired while it is still covered.
    DocType.PURCHASE_RECEIPT: 45,
}
DEFAULT_NOTICE_DAYS = 30


def notice_days(doc: Document) -> int:
    return NOTICE_DAYS.get(doc.doc_type or "", DEFAULT_NOTICE_DAYS)


def renew_from(doc: Document) -> date | None:
    """Date from which the renewal should be taken care of."""
    if doc.expiry_date is None:
        return None
    return doc.expiry_date - timedelta(days=notice_days(doc))


def _upsert(session: Session, doc: Document, source: str, when: date | None, title: str) -> None:
    existing = session.exec(
        select(Deadline).where(Deadline.document_id == doc.id, Deadline.source == source)
    ).first()
    if when is None:
        if existing:
            session.delete(existing)
        return
    deadline = existing or Deadline(document_id=doc.id, title="", due_date=when, source=source)
    deadline.title = title
    deadline.category = doc.category
    deadline.due_date = when
    deadline.amount = doc.amount if source == "extracted" else None
    session.add(deadline)


def sync(session: Session, doc: Document) -> None:
    """Aligns the deduced deadlines with the document.

    A duplicate, a former version or a document in the trash has none: they would be counted
    twice, or for a document that is no longer in force.

    The title is stored as text, in the language current when the document was last synced.
    """
    inactive = doc.duplicate_of is not None or doc.deleted_at is not None
    _upsert(session, doc, "extracted", None if inactive else doc.due_date, doc.title)
    expiring = not inactive and doc.superseded_by is None
    _upsert(
        session,
        doc,
        "expiry",
        doc.expiry_date if expiring else None,
        T(
            "warranty_title" if doc.doc_type == DocType.PURCHASE_RECEIPT else "expiry_title",
            title=doc.title,
        ),
    )
