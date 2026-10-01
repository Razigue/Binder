"""Journal d'activité : chaque action de Binder ou de l'utilisateur, en langage clair.

Les fonctions ajoutent l'entrée à la session sans valider : elle part avec la transaction
de l'action qu'elle décrit (ou disparaît avec elle en cas d'échec).
"""

import json
from datetime import date
from typing import Any

from sqlmodel import Session

from binder.models import Activity, Document

FIELD_NAMES = {
    "title": "le titre",
    "category": "la catégorie",
    "issuer": "l'émetteur",
    "amount": "le montant",
    "issue_date": "la date d'émission",
    "due_date": "l'échéance",
    "reference": "la référence",
    "doc_type": "le type de document",
    "expiry_date": "la date d'expiration",
}


def display(value: object) -> str:
    """Valeur lisible pour le journal : 1 240,00 €, 15/10/2026, « — » pour vide."""
    if value in (None, ""):
        return "—"
    if isinstance(value, float):
        return f"{value:,.2f} €".replace(",", " ").replace(".", ",")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(getattr(value, "value", value))


def log(
    session: Session,
    action: str,
    summary: str,
    *,
    actor: str = "binder",
    document: Document | None = None,
    document_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> Activity:
    entry = Activity(
        actor=actor,
        action=action,
        summary=summary,
        document_id=document.id if document else document_id,
        details=json.dumps(details or {}, ensure_ascii=False, default=str),
    )
    session.add(entry)
    return entry


def changes_summary(title: str, changes: dict[str, tuple[object, object]]) -> str:
    parts = [
        f"{FIELD_NAMES.get(field, field)} : {display(old)} → {display(new)}"
        for field, (old, new) in changes.items()
    ]
    return f"« {title} » modifié ({'; '.join(parts)})"
