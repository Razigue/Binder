"""One-tap questions instead of a review queue.

When Binder is unsure about a document, it asks one plain question in the Today feed, with the
likely answers as buttons: the amounts or dates it saw in the document, the life areas, "yes,
it's a duplicate"… Answering fixes the document; when nothing is left to ask, it is filed.
"""

import json
import re
from collections import Counter
from datetime import date

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.models import Category, Document, DocumentStatus
from binder.services import areas, editing, ingest, learning, rules

T = i18n.catalog(
    "questions",
    {
        "duplicate": {
            "en": "Is “{title}” the same document as “{other}”?",
            "fr": "« {title} » est-il le même document que « {other} » ?",
        },
        "duplicate_detail": {
            "en": "Their content is almost identical.",
            "fr": "Leur contenu est presque identique.",
        },
        "duplicate_yes": {"en": "Yes, remove the copy", "fr": "Oui, retirer la copie"},
        "duplicate_no": {"en": "No, keep both", "fr": "Non, garder les deux"},
        "unreadable": {
            "en": "Binder cannot read “{title}”.",
            "fr": "Binder n'arrive pas à lire « {title} ».",
        },
        "unreadable_detail": {
            "en": "The scan may be blurred or cut. Open it to fill in what matters, or scan it "
            "again.",
            "fr": "Le scan est peut-être flou ou coupé. Ouvrez-le pour compléter l'essentiel, ou "
            "scannez-le à nouveau.",
        },
        "open": {"en": "Open", "fr": "Ouvrir"},
        "trash": {"en": "Remove", "fr": "Retirer"},
        "where": {"en": "Where does “{title}” go?", "fr": "Où ranger « {title} » ?"},
        "where_detail": {
            "en": "Binder could not tell what it is about.",
            "fr": "Binder n'a pas reconnu de quoi il s'agit.",
        },
        "amount": {
            "en": "What is the amount of “{title}”?",
            "fr": "Quel est le montant de « {title} » ?",
        },
        "amount_none": {"en": "No amount", "fr": "Pas de montant"},
        "due_date": {
            "en": "When must “{title}” be paid?",
            "fr": "Quand faut-il payer « {title} » ?",
        },
        "due_date_none": {"en": "Nothing to pay", "fr": "Rien à payer"},
        "expiry_date": {
            "en": "Until when is “{title}” valid?",
            "fr": "Jusqu'à quand « {title} » est-il valable ?",
        },
        "expiry_date_none": {"en": "No end date", "fr": "Pas de date de fin"},
        "issue_date": {
            "en": "What is the date of “{title}”?",
            "fr": "De quand date « {title} » ?",
        },
        "issue_date_none": {"en": "I don't know", "fr": "Je ne sais pas"},
        "seen_in_document": {
            "en": "Here is what Binder saw in it.",
            "fr": "Voici ce que Binder y a vu.",
        },
        "not_seen": {
            "en": "Binder did not find it in the document.",
            "fr": "Binder ne l'a pas trouvé dans le document.",
        },
        "confirm": {"en": "Is this right? {summary}", "fr": "C'est bien ça ? {summary}"},
        "confirm_detail": {
            "en": "Binder is not sure of its reading.",
            "fr": "Binder n'est pas sûr de sa lecture.",
        },
        "yes": {"en": "Yes", "fr": "Oui"},
        "fix": {"en": "Correct", "fr": "Corriger"},
        "due": {"en": "due {date:date}", "fr": "à payer le {date:date}"},
        "valid_until": {"en": "valid until {date:date}", "fr": "valable jusqu'au {date:date}"},
    },
)

MAX_CHOICES = 3
DATE_FIELDS = ("due_date", "expiry_date", "issue_date")


class Choice(BaseModel):
    id: str
    label: str
    primary: bool = False


class Question(BaseModel):
    key: str
    document_id: int
    title: str
    detail: str
    category: Category
    choices: list[Choice]


class UnknownChoice(ValueError):
    pass


def _amounts(text: str) -> list[float]:
    """Figures written like amounts (two decimals), with or without a currency sign."""
    found = Counter(
        rules.parse_amount(m[1], m[2]) for m in learning.NUMBER.finditer(rules.normalize(text))
    )
    # The most repeated first (a total is often written twice), then the largest.
    ranked = sorted(found, key=lambda a: (-found[a], -a))
    return [a for a in ranked if a > 0][:MAX_CHOICES]


def _dates(text: str, field: str, doc: Document) -> list[date]:
    found: list[date] = []
    for line in rules.normalize(text).splitlines():
        for d in rules.find_dates(line):
            if d not in found:
                found.append(d)
    if field in ("due_date", "expiry_date") and doc.issue_date:
        found = [d for d in found if d > doc.issue_date]
    if field == "expiry_date":
        found.sort(reverse=True)
    return found[:MAX_CHOICES]


def _summary(doc: Document) -> str:
    parts = [doc.title, areas.label(areas.area_of(doc) or "money")]
    if doc.amount is not None:
        parts.append(i18n.format_money(doc.amount))
    if doc.due_date:
        parts.append(T("due", date=doc.due_date))
    elif doc.expiry_date:
        parts.append(T("valid_until", date=doc.expiry_date))
    return " · ".join(parts)


def question_for(session: Session, doc: Document) -> Question | None:
    if doc.id is None or doc.status != DocumentStatus.TO_REVIEW or doc.deleted_at:
        return None
    title = doc.title or doc.filename
    missing = [m for m in json.loads(doc.missing_fields) if m != "duplicate"]

    def ask(key: str, text: str, detail: str, choices: list[Choice]) -> Question:
        assert doc.id is not None
        return Question(
            key=f"doc:{doc.id}:{key}",
            document_id=doc.id,
            title=text,
            detail=detail,
            category=doc.category,
            choices=choices,
        )

    original = session.get(Document, doc.duplicate_of) if doc.duplicate_of else None
    if original is not None:
        return ask(
            "duplicate",
            T("duplicate", title=title, other=original.title),
            T("duplicate_detail"),
            [
                Choice(id="trash", label=T("duplicate_yes"), primary=True),
                Choice(id="keep", label=T("duplicate_no")),
            ],
        )
    if "text" in missing or not doc.text.strip():
        return ask(
            "unreadable",
            T("unreadable", title=title),
            T("unreadable_detail"),
            [
                Choice(id="open", label=T("open"), primary=True),
                Choice(id="trash", label=T("trash")),
            ],
        )
    if doc.category == Category.OTHER:
        return ask(
            "area",
            T("where", title=title),
            T("where_detail"),
            [Choice(id=f"area:{a}", label=areas.label(a)) for a in areas.AREAS],
        )
    for field in ("amount", *DATE_FIELDS):
        if field not in missing:
            continue
        if field == "amount":
            values = [
                Choice(id=f"amount:{a}", label=i18n.format_money(a)) for a in _amounts(doc.text)
            ]
        else:
            values = [
                Choice(id=f"{field}:{d.isoformat()}", label=i18n.format_date(d))
                for d in _dates(doc.text, field, doc)
            ]
        detail = T("seen_in_document") if values else T("not_seen")
        choices = [*values, Choice(id="none", label=T(f"{field}_none"))]
        if not values:
            choices.insert(0, Choice(id="open", label=T("open"), primary=True))
        return ask(field, T(field, title=title), detail, choices)
    return ask(
        "confirm",
        T("confirm", summary=_summary(doc)),
        T("confirm_detail"),
        [Choice(id="yes", label=T("yes"), primary=True), Choice(id="open", label=T("fix"))],
    )


def pending(session: Session) -> list[Question]:
    docs = session.exec(
        select(Document)
        .where(Document.status == DocumentStatus.TO_REVIEW, col(Document.deleted_at).is_(None))
        .order_by(col(Document.created_at).desc())
    )
    return [q for d in docs if (q := question_for(session, d)) is not None]


_VALUE = re.compile(r"^(amount|due_date|expiry_date|issue_date):(.+)$")


def answer(session: Session, doc: Document, choice: str) -> None:
    """Applies the answer (does not commit). "open" changes nothing: the interface opens it."""
    if choice == "open":
        return
    if choice == "trash":
        ingest.trash(session, doc)
        return
    if choice in ("keep", "yes", "none"):
        editing.update_document(session, doc, {}, validated=True)
        return
    changes: dict[str, object] = {}
    if choice.startswith("area:"):
        area = choice.removeprefix("area:")
        if area not in areas.AREAS:
            raise UnknownChoice(choice)
        changes["category"] = areas.DEFAULT_CATEGORY[area]
    elif m := _VALUE.match(choice):
        field, raw = m[1], m[2]
        try:
            changes[field] = float(raw) if field == "amount" else date.fromisoformat(raw)
        except ValueError as e:
            raise UnknownChoice(choice) from e
    else:
        raise UnknownChoice(choice)
    fields = {**doc.model_dump(), **changes}
    category = changes.get("category", doc.category)
    assert isinstance(category, Category)
    done = not rules.missing_for(category, fields)
    editing.update_document(session, doc, changes, validated=done)
