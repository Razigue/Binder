"""Échéances déduites des documents : paiement (« extracted ») et fin de validité (« expiry »)."""

from datetime import date, timedelta

from sqlmodel import Session, select

from binder.models import Deadline, Document

# Délai conseillé pour lancer le renouvellement (rendez-vous en mairie, préfecture…).
NOTICE_DAYS: dict[str, int] = {
    "Carte d'identité": 90,
    "Passeport": 120,
    "Titre de séjour": 120,
    "Permis de conduire": 90,
    "Contrôle technique": 30,
}
DEFAULT_NOTICE_DAYS = 30


def notice_days(doc: Document) -> int:
    return NOTICE_DAYS.get(doc.doc_type or "", DEFAULT_NOTICE_DAYS)


def renew_from(doc: Document) -> date | None:
    """Date à partir de laquelle il faut s'occuper du renouvellement."""
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
    """Aligne les échéances déduites sur le document.

    Un doublon, une ancienne version ou un document à la corbeille n'en a aucune : elles
    compteraient deux fois, ou pour un document qui n'est plus en vigueur.
    """
    inactive = doc.duplicate_of is not None or doc.deleted_at is not None
    _upsert(session, doc, "extracted", None if inactive else doc.due_date, doc.title)
    expiring = not inactive and doc.superseded_by is None
    _upsert(
        session,
        doc,
        "expiry",
        doc.expiry_date if expiring else None,
        f"Fin de validité : {doc.title}",
    )
