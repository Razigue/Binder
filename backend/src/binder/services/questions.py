"""One-tap questions instead of a review queue, and only the ones that matter.

When Binder is unsure about a document and the answer changes something today
(services/relevance.py), it asks one plain question with the likely answers as buttons: the
amounts or dates it saw in the document, the life areas, "yes, it's a duplicate"… The same
question about several documents of one sender becomes one card ("These 6 Free bills go in
Housing?"). The to-do list shows the most useful ones first, a few at a time (`visible`); the
others wait for a sorting session. Answering fixes the documents; when nothing is left to ask,
they are filed.
"""

import json
import re
from collections import Counter
from datetime import date, timedelta

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import in_use
from binder.models import Category, Document, DocumentStatus
from binder.services import areas, editing, ingest, learning, relevance, rules

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
        # Grouped questions: one card for several documents of the same sender.
        "detail": {"en": "See one by one", "fr": "Voir le détail"},
        "group_area": {
            "en": "These {n} documents from {issuer} go in {area}?",
            "fr": "Ces {n} documents de {issuer} vont dans {area} ?",
        },
        "group_area_detail": {
            "en": "Your other documents from {issuer} are there.",
            "fr": "Vos autres documents de {issuer} y sont déjà.",
        },
        "group_where": {
            "en": "Where do these {n} documents from {issuer} go?",
            "fr": "Où ranger ces {n} documents de {issuer} ?",
        },
        "group_confirm": {
            "en": "Did Binder read these {n} documents from {issuer} right?",
            "fr": "Binder a-t-il bien lu ces {n} documents de {issuer} ?",
        },
        "group_confirm_detail": {
            "en": "Check one if you like: Binder applies what you tell it to the others.",
            "fr": "Vérifiez-en un si vous voulez : Binder applique ce que vous lui dites aux "
            "autres.",
        },
        "group_amount": {
            "en": "{n} documents from {issuer} without an amount",
            "fr": "{n} documents de {issuer} sans montant",
        },
        "group_due_date": {
            "en": "{n} documents from {issuer} without a payment date",
            "fr": "{n} documents de {issuer} sans date de paiement",
        },
        "group_expiry_date": {
            "en": "{n} documents from {issuer} without an end date",
            "fr": "{n} documents de {issuer} sans date de fin",
        },
        "group_field_detail": {
            "en": "Fill them in one by one, or tell Binder there is none.",
            "fr": "Complétez-les un par un, ou dites à Binder qu'il n'y en a pas.",
        },
        "group_duplicate": {
            "en": "{n} copies of documents from {issuer}",
            "fr": "{n} copies de documents de {issuer}",
        },
        "group_duplicate_yes": {"en": "Remove the copies", "fr": "Retirer les copies"},
        "group_unreadable": {
            "en": "Binder cannot read {n} documents from {issuer}",
            "fr": "Binder n'arrive pas à lire {n} documents de {issuer}",
        },
    },
)

MAX_CHOICES = 3
DATE_FIELDS = ("due_date", "expiry_date")
FIELDS = ("amount", *DATE_FIELDS)
# At most this many questions in the to-do list; the others wait for a sorting session.
MAX_VISIBLE = 3
# The same question about this many documents of one sender becomes one card.
GROUP_FROM = 2


class Choice(BaseModel):
    id: str
    label: str
    primary: bool = False


class Question(BaseModel):
    key: str
    # First document asked about; `document_ids` holds all of them for a grouped question.
    document_id: int
    document_ids: list[int] = []
    title: str
    detail: str
    category: Category
    choices: list[Choice]
    # What is asked: "duplicate", "text", "area", a field name or "confirm".
    kind: str = ""
    # Field read in the document, highlighted next to the question.
    field: str | None = None
    issuer: str | None = None
    # Lower first: deadline close, then documents in force, then the rest.
    rank: int = 3
    when: date | None = None


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


def _rank(doc: Document, today: date) -> tuple[int, date | None]:
    if doc.due_date is not None and doc.due_date <= today + timedelta(days=relevance.ACTIVE_DAYS):
        return 0, doc.due_date
    if doc.expiry_date is not None and doc.expiry_date >= today:
        return 1, doc.expiry_date
    if doc.duplicate_of is not None:
        return 2, None
    return 3, None


def question_for(session: Session, doc: Document, today: date | None = None) -> Question | None:
    """The question about this document, None when there is nothing worth asking."""
    if doc.id is None or doc.status != DocumentStatus.TO_REVIEW or doc.deleted_at:
        return None
    if doc.archived_at is not None:
        return None
    today = today or date.today()
    asked = relevance.worth_asking(doc, today)
    if not asked:
        return None
    title = doc.title or doc.filename
    rank, when = _rank(doc, today)

    def ask(
        kind: str, text: str, detail: str, choices: list[Choice], field: str | None = None
    ) -> Question:
        assert doc.id is not None
        return Question(
            key=f"doc:{doc.id}:{kind}",
            document_id=doc.id,
            document_ids=[doc.id],
            title=text,
            detail=detail,
            category=doc.category,
            choices=choices,
            kind=kind,
            field=field,
            issuer=doc.issuer,
            rank=rank,
            when=when,
        )

    problem = asked[0]
    original = session.get(Document, doc.duplicate_of) if doc.duplicate_of else None
    if problem == "duplicate" and original is not None:
        return ask(
            "duplicate",
            T("duplicate", title=title, other=original.title),
            T("duplicate_detail"),
            [
                Choice(id="trash", label=T("duplicate_yes"), primary=True),
                Choice(id="keep", label=T("duplicate_no")),
            ],
        )
    if problem == "text":
        return ask(
            "text",
            T("unreadable", title=title),
            T("unreadable_detail"),
            [
                Choice(id="open", label=T("open"), primary=True),
                Choice(id="trash", label=T("trash")),
            ],
        )
    if problem == "category":
        return ask(
            "area",
            T("where", title=title),
            T("where_detail"),
            [Choice(id=f"area:{a}", label=areas.label(a)) for a in areas.AREAS],
        )
    if problem in FIELDS:
        if problem == "amount":
            values = [
                Choice(id=f"amount:{a}", label=i18n.format_money(a)) for a in _amounts(doc.text)
            ]
        else:
            values = [
                Choice(id=f"{problem}:{d.isoformat()}", label=i18n.format_date(d))
                for d in _dates(doc.text, problem, doc)
            ]
        detail = T("seen_in_document") if values else T("not_seen")
        choices = [*values, Choice(id="none", label=T(f"{problem}_none"))]
        if not values:
            choices.insert(0, Choice(id="open", label=T("open"), primary=True))
        return ask(problem, T(problem, title=title), detail, choices, field=problem)
    doubted = next(
        (
            d.partition(":")[2]
            for d in json.loads(doc.doubts or "[]")
            if d.partition(":")[2] and relevance.field_matters(doc, d.partition(":")[2], today)
        ),
        None,
    )
    return ask(
        "confirm",
        T("confirm", summary=_summary(doc)),
        T("confirm_detail"),
        [Choice(id="yes", label=T("yes"), primary=True), Choice(id="open", label=T("fix"))],
        field=doubted,
    )


def _known_area(session: Session, issuer: str) -> str | None:
    """The area where the other documents of this sender are filed, if they agree."""
    rows = session.exec(
        select(Document.area).where(
            in_use(),
            Document.issuer == issuer,
            Document.status == DocumentStatus.CLASSIFIED,
            col(Document.area).is_not(None),
        )
    ).all()
    found = Counter(a for a in rows if a)
    if len(found) == 1:
        return next(iter(found))
    return None


def _group(session: Session, kind: str, items: list[Question]) -> Question:
    """One question for the same question about several documents of one sender."""
    first = items[0]
    ids = [i for q in items for i in q.document_ids]
    issuer = first.issuer or ""
    n = len(ids)
    detail_choice = Choice(id="detail", label=T("detail"))
    title, detail, choices = "", "", [detail_choice]
    if kind == "area":
        area = _known_area(session, issuer)
        if area:
            title = T("group_area", n=n, issuer=issuer, area=areas.label(area))
            detail = T("group_area_detail", issuer=issuer)
            choices = [Choice(id=f"area:{area}", label=T("yes"), primary=True), detail_choice]
        else:
            title = T("group_where", n=n, issuer=issuer)
            detail = T("where_detail")
            choices = [Choice(id=f"area:{a}", label=areas.label(a)) for a in areas.AREAS]
            choices.append(detail_choice)
    elif kind == "confirm":
        title = T("group_confirm", n=n, issuer=issuer)
        detail = T("group_confirm_detail")
        choices = [Choice(id="yes", label=T("yes"), primary=True), detail_choice]
    elif kind in FIELDS:
        title = T(f"group_{kind}", n=n, issuer=issuer)
        detail = T("group_field_detail")
        choices = [
            Choice(id="detail", label=T("detail"), primary=True),
            Choice(id="none", label=T(f"{kind}_none")),
        ]
    elif kind == "duplicate":
        title = T("group_duplicate", n=n, issuer=issuer)
        detail = T("duplicate_detail")
        choices = [
            Choice(id="trash", label=T("group_duplicate_yes"), primary=True),
            detail_choice,
        ]
    else:
        title = T("group_unreadable", n=n, issuer=issuer)
        detail = T("unreadable_detail")
        choices = [Choice(id="detail", label=T("detail"), primary=True)]
    dates = [q.when for q in items if q.when is not None]
    return first.model_copy(
        update={
            "key": f"group:{kind}:{'-'.join(map(str, sorted(ids)))}",
            "document_ids": ids,
            "title": title,
            "detail": detail,
            "choices": choices,
            "rank": min(q.rank for q in items),
            "when": min(dates) if dates else None,
        }
    )


def _order(q: Question) -> tuple[int, date, int]:
    return q.rank, q.when or date.max, -len(q.document_ids)


def pending(
    session: Session,
    today: date | None = None,
    *,
    group: bool = True,
    ids: list[int] | None = None,
) -> list[Question]:
    """Every question worth asking, grouped by sender, most useful first. `group=False`: one
    question per document; `ids`: only about these documents (a group seen one by one)."""
    today = today or date.today()
    stmt = (
        select(Document)
        .where(Document.status == DocumentStatus.TO_REVIEW, in_use())
        .order_by(col(Document.created_at).desc())
    )
    if ids is not None:
        stmt = stmt.where(col(Document.id).in_(ids))
    single = [q for d in session.exec(stmt) if (q := question_for(session, d, today))]
    if not group:
        return sorted(single, key=_order)
    buckets: dict[tuple[str, str], list[Question]] = {}
    for q in single:
        if q.issuer:
            buckets.setdefault((q.kind, q.issuer), []).append(q)
    out: list[Question] = []
    grouped: set[int] = set()
    for (kind, _), items in buckets.items():
        if len(items) >= GROUP_FROM:
            out.append(_group(session, kind, items))
            grouped.update(q.document_id for q in items)
    out += [q for q in single if q.document_id not in grouped]
    return sorted(out, key=_order)


def visible(session: Session, today: date | None = None) -> tuple[list[Question], list[Question]]:
    """The questions shown in the to-do list, and those left for a sorting session."""
    questions = pending(session, today)
    return questions[:MAX_VISIBLE], questions[MAX_VISIBLE:]


_VALUE = re.compile(r"^(amount|due_date|expiry_date|issue_date):(.+)$")


def answer(session: Session, doc: Document, choice: str) -> None:
    """Applies the answer (does not commit). "open" and "detail" change nothing: the interface
    shows the documents."""
    if choice in ("open", "detail"):
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


def answer_all(session: Session, docs: list[Document], choice: str) -> None:
    """The same answer for every document of a grouped question (does not commit)."""
    if choice == "trash" and len(docs) > 1:
        # Only the copies go: a grouped duplicate question never removes an original.
        docs = [d for d in docs if d.duplicate_of is not None]
    for doc in docs:
        answer(session, doc, choice)
