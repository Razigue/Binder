"""Agent tools. Each tool returns a serializable result for the model (English keys), along
with what the interface shows: documents, deadlines, drafted letters, page images.

Tools that change something log it with actor "agent" and stay reversible (trash, deadline
reopened, previous values in the activity log)."""

import inspect
import json
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, text
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT
from binder.models import Category, Deadline, DocType, Document, DocumentStatus
from binder.schemas import Letter
from binder.services import (
    activity,
    deadlines,
    editing,
    embeddings,
    explain,
    folders,
    ingest,
    letters,
    llm,
    retention,
    settings_store,
    subscriptions,
)
from binder.services.rules import MONTHS, normalize
from binder.services.text import page_count, page_image

T = i18n.catalog(
    "agent_tools",
    {
        "reminder_created": {
            "en": "Reminder “{title}” created for {date:date} at your request",
            "fr": "Rappel « {title} » créé pour le {date:date} à votre demande",
        },
        "trash_reason": {"en": "at your request", "fr": "à votre demande"},
    },
)

# English month names (French ones come from the document rules), for questions such as
# "what is due in October?" or "since March".
EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}  # fmt: skip
ALL_MONTHS = {**MONTHS, **EN_MONTHS}

# Words of a request that are not search terms, in French and English (normalized text).
STOP_WORDS = {
    # French
    "trouve", "trouver", "cherche", "chercher", "montre", "affiche", "liste", "donne", "moi",
    "mes", "mon", "ma", "les", "le", "la", "des", "de", "du", "un", "une", "tous", "toutes",
    "tout", "depuis", "avant", "apres", "pour", "dans", "et", "ou", "en", "sur", "avec", "quels",
    "quel", "quelle", "quelles", "documents", "document", "dernier", "derniere", "derniers",
    "classe", "range", "arrivent", "bientot", "je", "j", "ai", "a", "est", "sont", "qui", "que",
    "annee", "mois", "cette", "ce", "ces", "moins",
    # English
    "find", "search", "look", "show", "display", "list", "give", "get", "me", "my", "mine",
    "the", "an", "all", "every", "since", "before", "after", "for", "in", "and", "or", "on",
    "at", "with", "which", "what", "whats", "is", "are", "was", "were", "do", "does", "did",
    "have", "has", "had", "i", "you", "your", "it", "its", "this", "that", "these", "those",
    "of", "to", "from", "by", "about", "please", "latest", "last", "recent", "most", "newest",
    "year", "month", "week", "filed", "sorted", "received", "got", "coming", "up", "soon",
    "any", "some", "can", "could", "tell",
}  # fmt: skip

# Characters of document text sent per read: ~1,300 tokens, a dense administrative page.
READ_CHARS = 4000
# Characters around a search term in a passage.
PASSAGE_CHARS = 160


@dataclass
class ToolResult:
    payload: Any
    documents: list[Document] = field(default_factory=list)
    deadlines: list[Deadline] = field(default_factory=list)
    # JPEG pages shown to the model with the result (vision).
    images: list[bytes] = field(default_factory=list)
    letters: list[Letter] = field(default_factory=list)
    # Something was written (document, deadline…): the interface refreshes its data.
    changed: bool = False


def _error(message: str) -> ToolResult:
    return ToolResult(payload={"error": message})


def doc_summary(d: Document) -> dict[str, Any]:
    return {
        "id": d.id,
        "title": d.title,
        "category": d.category.value,
        "doc_type": d.doc_type,
        "issuer": d.issuer,
        "amount": d.amount,
        "issue_date": d.issue_date and d.issue_date.isoformat(),
        "due_date": d.due_date and d.due_date.isoformat(),
        "expiry_date": d.expiry_date and d.expiry_date.isoformat(),
        "reference": d.reference,
    }


def _deadline_summary(d: Deadline, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    return {
        "id": d.id,
        "title": d.title,
        "category": d.category.value,
        "date": d.due_date.isoformat(),
        "days_left": (d.due_date - today).days,
        "amount": d.amount,
        "document_id": d.document_id,
        "kind": d.source,
        "paid": d.done or None,
    }


def _stem(term: str) -> str:
    return term[:-1] if len(term) > 3 and term[-1] in "sx" else term


# English words for French paperwork, so that an English question finds French documents
# without the model ("property tax" → "taxe fonciere"). Document type labels give most of it.
_EXTRA_TERMS = {
    "electricity": "electricite",
    "electric": "electricite",
    "gas": "gaz",
    "water": "eau",
    "bill": "facture",
    "phone": "mobile",
    "rent": "loyer",
    "salary": "salaire",
    "pay slip": "bulletin paie",
    "income tax": "impot revenu",
    "car inspection": "controle technique",
    "mot": "controle technique",
    "car insurance": "assurance auto",
    "home insurance": "assurance habitation",
    "insurance": "assurance",
    "health": "sante",
    "id card": "carte identite",
    "driver's license": "permis conduire",
    "drivers license": "permis conduire",
    "registration": "carte grise",
    "estimate": "devis",
    "repair": "reparation",
}


def _glossary() -> list[tuple[re.Pattern[str], str]]:
    pairs = dict(_EXTRA_TERMS)
    for doc_type in DocType:
        english = re.sub(r"\s*\(.*?\)", "", normalize(i18n.doc_type_label(doc_type, "en")))
        pairs.setdefault(english, normalize(i18n.doc_type_label(doc_type, "fr")))
    # Longest first: "property tax" wins over "tax".
    return [
        (re.compile(r"(?<![a-z0-9])" + re.escape(en) + r"(?![a-z0-9])"), fr)
        for en, fr in sorted(pairs.items(), key=lambda p: -len(p[0]))
    ]


GLOSSARY = _glossary()


def keywords(query: str) -> list[str]:
    norm = normalize(query)
    for pattern, french in GLOSSARY:
        norm = pattern.sub(french, norm)
    words = re.findall(r"[a-z0-9]+", norm)
    return [_stem(w) for w in words if w not in STOP_WORDS and w not in ALL_MONTHS and len(w) > 1]


def find_category(value: str) -> Category | None:
    """Category from its slug or its label in any language ("taxes", "Impôts")."""
    wanted = normalize(value).strip()
    for c in Category:
        names = {
            c.value,
            *(normalize(i18n.category_label(c.value, lang)) for lang in i18n.LANGUAGES),
        }
        if wanted in names:
            return c
    return None


def _date(value: str | None) -> date | None:
    if not value:
        return None
    with suppress(ValueError):
        return date.fromisoformat(value[:10])
    return None


def _fts(session: Session, terms: list[str], operator: str, limit: int) -> list[int]:
    match = f" {operator} ".join(f'"{t}"*' for t in terms)
    rows = session.execute(
        text(
            "SELECT rowid FROM document_fts WHERE document_fts MATCH :q "
            "ORDER BY bm25(document_fts, 10.0, 5.0, 5.0, 3.0, 1.0) LIMIT :limit"
        ),
        {"q": match, "limit": limit},
    )
    return [int(r[0]) for r in rows]


def passages(body: str, terms: list[str], limit: int = 3) -> list[str]:
    """Lines of the text that mention the most search terms (accents and case ignored), each
    with the line after it: in administrative documents the value often follows its label
    ("Revenu fiscal de référence" / "32 480 €")."""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    patterns = [re.compile(r"(?<![a-z0-9])" + re.escape(t)) for t in terms]
    scored = []
    for i, line in enumerate(lines):
        norm = normalize(line)
        score = sum(1 for p in patterns if p.search(norm))
        if score:
            scored.append((score, i))
    chosen = sorted(i for _, i in sorted(scored, key=lambda x: (-x[0], x[1]))[:limit])
    out: list[str] = []
    last = -2
    for i in chosen:
        lines_shown = lines[i : i + 2] if i > last else lines[i + 1 : i + 2]
        text_shown = " / ".join(line[:PASSAGE_CHARS] for line in lines_shown)
        if i <= last + 1 and out:
            # Next to the previous passage: one passage rather than two overlapping ones.
            out[-1] += " / " + text_shown if text_shown else ""
        elif text_shown:
            out.append(text_shown)
        last = i + 1
    return out


def search_documents(
    session: Session,
    query: str = "",
    category: str | None = None,
    since: str | None = None,
    until: str | None = None,
    doc_type: str | None = None,
    limit: int = 10,
) -> ToolResult:
    """Full-text search (all words, otherwise at least one), filterable by category, type and
    issue date. The total amount of every match helps answer "how much did I pay for…"."""
    terms = keywords(query)
    stmt = select(Document).where(col(Document.deleted_at).is_(None))
    ranking: list[int] | None = None
    if terms:
        ids = _fts(session, terms, "AND", 200)
        if not ids:
            # No document has every word: documents close in meaning ("proof of address" →
            # EDF bill, rent receipt), merged with those that have some of the words.
            related = [doc_id for doc_id, _ in embeddings.search(session, query)]
            some_words = _fts(session, terms, "OR", 200)
            ids = ranking = _fuse(related, some_words) if related else some_words
        if not ids:
            return ToolResult(payload={"results": [], "total": 0, "hint": NO_MATCH_HINT})
        stmt = stmt.where(col(Document.id).in_(ids))
    if first := _date(since):
        stmt = stmt.where(col(Document.issue_date) >= first)
    if last := _date(until):
        stmt = stmt.where(col(Document.issue_date) <= last)
    if doc_type and doc_type in DocType.__members__.values():
        stmt = stmt.where(Document.doc_type == doc_type)
    cat = find_category(category) if category else None
    if cat:
        in_category = stmt.where(Document.category == cat)
        shown, total = _page(session, in_category, limit, ranking)
        if total or not terms:
            stmt = in_category
    if not cat or not total:
        # Models often guess the category wrong ("housing" for the property tax): the words
        # matched, so the category is ignored rather than returning nothing.
        shown, total = _page(session, stmt, limit, ranking)
    results = []
    for d in shown:
        summary = doc_summary(d)
        if terms and len(terms) <= 6:
            # Where the words were found: often answers the question without reading.
            summary["passages"] = passages(d.text, terms, limit=2) or None
        results.append(summary)
    payload: dict[str, Any] = {"results": results, "total": total}
    if total:
        payload["sum_amount"] = _sum_amount(session, stmt)
    else:
        payload["hint"] = NO_MATCH_HINT
    return ToolResult(payload=payload, documents=shown)


NO_MATCH_HINT = (
    "No match. Try fewer or other words as written in French documents (issuer, document "
    "type), or a category alone."
)


def _sum_amount(session: Session, stmt: Any) -> float:
    sub = stmt.subquery()
    total = session.execute(select(func.sum(sub.c.amount))).scalar()
    return round(float(total or 0), 2)


def _fuse(*rankings: list[int]) -> list[int]:
    """Reciprocal rank fusion: documents well placed in several rankings come first."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1 / (60 + rank)
    return sorted(scores, key=lambda doc_id: -scores[doc_id])


def _page(
    session: Session, stmt: Any, limit: int, ranking: list[int] | None = None
) -> tuple[list[Document], int]:
    """The first `limit` results, without their text, and the total: most relevant first when
    a `ranking` is given, otherwise most recent first."""
    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    if not total:
        return [], 0
    order = (col(Document.issue_date).desc(), col(Document.id).desc())
    if ranking is None:
        return list(session.exec(stmt.options(*WITHOUT_TEXT).order_by(*order).limit(limit))), total
    position = {doc_id: i for i, doc_id in enumerate(ranking)}
    docs = sorted(session.exec(stmt.options(*WITHOUT_TEXT)), key=lambda d: position[d.id])
    return docs[:limit], total


def _document(session: Session, document_id: int) -> Document | None:
    doc = session.get(Document, document_id)
    return None if doc is None or doc.deleted_at is not None else doc


def _not_found(document_id: int) -> ToolResult:
    return _error(f"Document {document_id} not found: use search_documents to find its id")


def read_document(
    session: Session, document_id: int, query: str | None = None, offset: int = 0
) -> ToolResult:
    """Details and text of a document; with `query`, only the passages that mention it."""
    doc = _document(session, document_id)
    if doc is None:
        return _not_found(document_id)
    payload: dict[str, Any] = {
        **doc_summary(doc),
        "status": doc.status.value,
        "pages": doc.page_count,
        "to_check": [f for f in json.loads(doc.missing_fields)] or None,
        "replaced_by": doc.superseded_by,
        "duplicate_of": doc.duplicate_of,
        "keep_until": (k := retention.keep_until(doc)) and k.isoformat(),
    }
    body = llm.compact(doc.text, len(doc.text))
    terms = keywords(query) if query else []
    if terms and (found := passages(body, terms, limit=6)):
        payload["passages"] = found
    else:
        offset = max(0, min(offset, len(body)))
        payload["text"] = body[offset : offset + READ_CHARS]
        if offset + READ_CHARS < len(body):
            payload["next_offset"] = offset + READ_CHARS
    if not body.strip():
        payload["text"] = None
        payload["note"] = "No text could be read: use view_document to look at the page."
    return ToolResult(payload=payload, documents=[doc])


def view_document(session: Session, document_id: int, page: int = 1) -> ToolResult:
    """Shows a page of the document to the model (vision): layout, tables, stamps, photos."""
    doc = _document(session, document_id)
    if doc is None:
        return _not_found(document_id)
    data = ingest.load_file(doc)
    pages = page_count(data, doc.mime_type)
    page = max(1, min(page, pages))
    return ToolResult(
        payload={
            "id": doc.id,
            "title": doc.title,
            "page": page,
            "pages": pages,
            "note": "The page image is attached to this message.",
        },
        documents=[doc],
        images=[page_image(data, doc.mime_type, page - 1)],
    )


def list_deadlines(
    session: Session, days: int = 30, start: str | None = None, end: str | None = None
) -> ToolResult:
    """Unpaid deadlines of a period (by default the next 30 days, plus overdue ones)."""
    today = date.today()
    first = _date(start) or today
    last = _date(end) or first + timedelta(days=max(1, days))
    rows = list(
        session.exec(
            select(Deadline)
            .where(Deadline.due_date >= first, Deadline.due_date <= last, Deadline.done == False)  # noqa: E712
            .order_by(col(Deadline.due_date))
        )
    )
    overdue: list[Deadline] = []
    if not start:
        overdue = list(
            session.exec(
                select(Deadline)
                .where(Deadline.due_date < today, Deadline.done == False)  # noqa: E712
                .order_by(col(Deadline.due_date))
            )
        )
    payload: dict[str, Any] = {
        "period": [first.isoformat(), last.isoformat()],
        "deadlines": [_deadline_summary(d, today) for d in rows],
        "total_amount": round(sum(d.amount or 0 for d in rows), 2),
    }
    if overdue:
        payload["overdue"] = [_deadline_summary(d, today) for d in overdue]
    return ToolResult(payload=payload, deadlines=overdue + rows)


def create_reminder(
    session: Session,
    title: str,
    due_date: str,
    amount: float | None = None,
    document_id: int | None = None,
) -> ToolResult:
    when = _date(due_date)
    if when is None:
        return _error("Invalid date, expected format YYYY-MM-DD")
    doc = _document(session, document_id) if document_id else None
    reminder = Deadline(
        title=title,
        due_date=when,
        amount=amount,
        source="manual",
        document_id=doc.id if doc else None,
        category=doc.category if doc else Category.OTHER,
    )
    session.add(reminder)
    activity.log(
        session,
        "reminder",
        T.msg("reminder_created", title=title, date=when),
        actor="agent",
        document_id=reminder.document_id,
    )
    # No commit here: it would expire the documents already found during this turn.
    session.flush()
    return ToolResult(
        payload={"created": _deadline_summary(reminder)}, deadlines=[reminder], changed=True
    )


def mark_deadline_paid(
    session: Session,
    deadline_id: int | None = None,
    document_id: int | None = None,
    paid: bool = True,
) -> ToolResult:
    """Marks a deadline as paid/done (or reopens it), by its id or its document's id."""
    stmt = select(Deadline)
    if deadline_id is not None:
        stmt = stmt.where(Deadline.id == deadline_id)
    elif document_id is not None:
        stmt = stmt.where(Deadline.document_id == document_id, Deadline.done == (not paid))
    else:
        return _error("Give deadline_id or document_id")
    rows = list(session.exec(stmt))
    if not rows:
        return _error("No matching deadline: use list_deadlines to find its id")
    for deadline in rows:
        editing.update_deadline(session, deadline, {"done": paid}, actor="agent")
    session.flush()
    return ToolResult(
        payload={"updated": [_deadline_summary(d) for d in rows]}, deadlines=rows, changed=True
    )


def update_document(
    session: Session,
    document_id: int,
    title: str | None = None,
    category: str | None = None,
    issuer: str | None = None,
    amount: float | None = None,
    issue_date: str | None = None,
    due_date: str | None = None,
    expiry_date: str | None = None,
    reference: str | None = None,
) -> ToolResult:
    """Corrects fields of a document at the user's request (logged with the old values)."""
    doc = _document(session, document_id)
    if doc is None:
        return _not_found(document_id)
    changes: dict[str, Any] = {}
    if title is not None and title.strip():
        changes["title"] = title.strip()
    for name, value in (("issuer", issuer), ("reference", reference)):
        if value is not None:
            changes[name] = value.strip() or None
    if amount is not None:
        changes["amount"] = amount
    if category is not None:
        cat = find_category(category)
        if cat is None:
            return _error(f"Unknown category; one of {', '.join(c.value for c in Category)}")
        changes["category"] = cat
    for name, value in (
        ("issue_date", issue_date),
        ("due_date", due_date),
        ("expiry_date", expiry_date),
    ):
        if value is not None:
            parsed = _date(value)
            if value and parsed is None:
                return _error(f"Invalid {name}, expected format YYYY-MM-DD")
            changes[name] = parsed
    if not changes:
        return _error("Nothing to change: give the fields to correct")
    diff = editing.update_document(session, doc, changes, actor="agent")
    session.flush()
    return ToolResult(
        payload={
            "id": doc.id,
            "changed": {
                k: {"old": i18n.jsonable(old), "new": i18n.jsonable(new)}
                for k, (old, new) in diff.items()
            },
            "status": doc.status.value,
        },
        documents=[doc],
        changed=bool(diff),
    )


def validate_document(session: Session, document_id: int) -> ToolResult:
    """Confirms a document set aside for review (or a flagged duplicate) is correct."""
    doc = _document(session, document_id)
    if doc is None:
        return _not_found(document_id)
    editing.update_document(session, doc, {}, validated=True, actor="agent")
    session.flush()
    return ToolResult(
        payload={"id": doc.id, "status": doc.status.value}, documents=[doc], changed=True
    )


def trash_document(session: Session, document_id: int) -> ToolResult:
    """Moves a document to the trash (restorable from the Trash page)."""
    doc = _document(session, document_id)
    if doc is None:
        return _not_found(document_id)
    ingest.trash(session, doc, actor="agent", reason=T.msg("trash_reason"))
    session.flush()
    return ToolResult(
        payload={"id": doc.id, "title": doc.title, "trashed": True, "restorable": True},
        changed=True,
    )


def documents_to_review(session: Session) -> ToolResult:
    docs = list(
        session.exec(
            select(Document)
            .options(*WITHOUT_TEXT)
            .where(Document.status == DocumentStatus.TO_REVIEW)
            .where(col(Document.deleted_at).is_(None))
            .order_by(col(Document.created_at).desc())
        )
    )
    return ToolResult(
        payload={
            "to_review": [
                {**doc_summary(d), "to_check": json.loads(d.missing_fields)} for d in docs
            ]
        },
        documents=docs,
    )


def explain_document(session: Session, document_id: int) -> ToolResult:
    doc = _document(session, document_id)
    if doc is None:
        return _not_found(document_id)
    result = explain.get(session, doc)
    session.flush()
    payload = result.model_dump(mode="json", exclude={"language"})
    return ToolResult(payload={"id": doc.id, **payload}, documents=[doc])


def check_folder(session: Session, kind: str) -> ToolResult:
    """Pieces of a standard application pack: found, to renew, missing."""
    folder = folders.KINDS.get(kind)
    if folder is None:
        return _error(f"Unknown pack; one of {', '.join(folders.KINDS)}")
    status = folders.evaluate(session, folder)
    ids = [i for piece in status.pieces for i in piece.document_ids]
    docs = [d for i in dict.fromkeys(ids) if (d := session.get(Document, i)) is not None]
    return ToolResult(
        payload={
            "title": status.title,
            "complete": status.complete,
            "ready": f"{status.ready}/{status.total}",
            "pieces": [
                {
                    "piece": p.label,
                    "status": p.status,
                    "found": f"{p.found}/{p.needed}",
                    "optional": p.optional or None,
                    "document_ids": p.document_ids or None,
                    "note": p.note or None,
                    "how_to_get": p.hint if p.status != "ok" else None,
                }
                for p in status.pieces
            ],
            "export_link": f"/api/folders/{kind}/export",
        },
        documents=docs,
    )


def list_subscriptions(session: Session) -> ToolResult:
    """Recurring bills (energy, phone, insurance…) with their cadence and price changes."""
    subs = subscriptions.detect(session)
    ids = [s.history[-1].document_id for s in subs if s.history]
    docs = [d for i in ids if (d := session.get(Document, i)) is not None]
    return ToolResult(
        payload={
            "subscriptions": [
                {
                    "name": s.label,
                    "category": s.category.value,
                    "cadence": s.cadence,
                    "last_amount": s.last_amount,
                    "previous_amount": s.previous_amount,
                    "change_pct": s.change_pct,
                    "price_increase": s.increase or None,
                    "yearly_estimate": s.yearly_estimate,
                    "latest_document_id": s.history[-1].document_id if s.history else None,
                }
                for s in subs
            ],
            "yearly_total": round(sum(s.yearly_estimate or 0 for s in subs), 2),
        },
        documents=docs,
    )


def list_expirations(session: Session) -> ToolResult:
    """Documents with an end of validity (identity, certificates, roadworthiness test…)."""
    today = date.today()
    docs = list(
        session.exec(
            select(Document)
            .options(*WITHOUT_TEXT)
            .where(col(Document.deleted_at).is_(None), col(Document.expiry_date).is_not(None))
            .where(col(Document.superseded_by).is_(None), col(Document.duplicate_of).is_(None))
            .order_by(col(Document.expiry_date))
        )
    )
    shown = []
    for doc in docs:
        assert doc.expiry_date is not None
        days_left = (doc.expiry_date - today).days
        renew = deadlines.renew_from(doc) or doc.expiry_date
        state = "expired" if days_left < 0 else "renew_now" if renew <= today else "valid"
        shown.append((doc, days_left, renew, state))
    return ToolResult(
        payload={
            "documents": [
                {
                    **doc_summary(d),
                    "days_left": left,
                    "renew_from": renew.isoformat(),
                    "state": state,
                }
                for d, left, renew, state in shown
            ]
        },
        documents=[d for d, *_ in shown],
    )


def documents_to_sort_out(session: Session) -> ToolResult:
    """Documents that can be thrown away: retention period over, or replaced by a newer one."""
    docs = list(
        session.exec(
            select(Document)
            .options(*WITHOUT_TEXT)
            .where(col(Document.deleted_at).is_(None))
            .order_by(col(Document.issue_date))
        )
    )
    found = [(d, reason) for d in docs if (reason := retention.deletion_reason(d))]
    return ToolResult(
        payload={"can_be_thrown_away": [{**doc_summary(d), "why": r} for d, r in found]},
        documents=[d for d, _ in found],
    )


def draft_letter(
    session: Session, kind: str, document_id: int | None = None, details: str = ""
) -> ToolResult:
    """Drafts a letter (termination, complaint, request) filled from a document and the
    user's profile; the interface shows it ready to copy."""
    if kind not in letters.KINDS:
        return _error(f"Unknown letter kind; one of {', '.join(letters.KINDS)}")
    doc = _document(session, document_id) if document_id else None
    if document_id and doc is None:
        return _not_found(document_id)
    profile = settings_store.load(session, letters.PROFILE_KEY, letters.Profile)
    letter = letters.write(kind, doc, profile, details)
    activity.log(session, "letter", letters.written_msg(letter), actor="agent", document=doc)
    payload: dict[str, Any] = {
        "subject": letter.subject,
        "recipient": letter.recipient,
        "registered_mail_advised": letter.registered,
        "shown_to_user": True,
    }
    if not profile.name:
        payload["note"] = "The user's name and address are not set (Letters page): placeholders."
    return ToolResult(payload=payload, documents=[doc] if doc else [], letters=[letter])


def export_folder(
    session: Session, category: str | None = None, pack: str | None = None
) -> ToolResult:
    """Download link: every document, one category, or a standard pack (rental…)."""
    if pack:
        if pack not in folders.KINDS:
            return _error(f"Unknown pack; one of {', '.join(folders.KINDS)}")
        status = folders.evaluate(session, folders.KINDS[pack])
        count = sum(len(p.document_ids) for p in status.pieces if p.status != "outdated")
        return ToolResult(payload={"link": f"/api/folders/{pack}/export", "count": count})
    cat = find_category(category) if category else None
    result = search_documents(session, category=cat.value if cat else None, limit=500)
    suffix = f"?category={cat.value}" if cat else ""
    return ToolResult(
        payload={"link": f"/api/export{suffix}", "count": result.payload["total"]},
        documents=result.documents[:10],
    )


def overview(session: Session) -> dict[str, Any]:
    """What Binder holds, in a few figures: given to the model before the first question."""
    today = date.today()
    active = col(Document.deleted_at).is_(None)
    by_category = dict(
        session.exec(
            select(Document.category, func.count()).where(active).group_by(Document.category)
        ).all()
    )
    open_deadlines = list(
        session.exec(
            select(Deadline)
            .where(Deadline.done == False)  # noqa: E712
            .where(Deadline.due_date <= today + timedelta(days=30))
        )
    )
    overdue = [d for d in open_deadlines if d.due_date < today]
    upcoming = [d for d in open_deadlines if d.due_date >= today]
    to_review = session.exec(
        select(func.count()).where(active, Document.status == DocumentStatus.TO_REVIEW)
    ).one()
    return {
        "documents": sum(by_category.values()),
        "by_category": {Category(c).value: n for c, n in by_category.items()},
        "deadlines_next_30_days": len(upcoming),
        "overdue_deadlines": len(overdue) or None,
        "to_review": to_review or None,
    }


TOOLS: dict[str, Any] = {
    "search_documents": search_documents,
    "read_document": read_document,
    "view_document": view_document,
    "explain_document": explain_document,
    "list_deadlines": list_deadlines,
    "list_expirations": list_expirations,
    "list_subscriptions": list_subscriptions,
    "check_folder": check_folder,
    "documents_to_review": documents_to_review,
    "documents_to_sort_out": documents_to_sort_out,
    "create_reminder": create_reminder,
    "mark_deadline_paid": mark_deadline_paid,
    "update_document": update_document,
    "validate_document": validate_document,
    "trash_document": trash_document,
    "draft_letter": draft_letter,
    "export_folder": export_folder,
}
# Tools that change data (the interface refreshes after them).
WRITE_TOOLS = {
    "create_reminder",
    "mark_deadline_paid",
    "update_document",
    "validate_document",
    "trash_document",
}


class InvalidArguments(ValueError):
    pass


def call(session: Session, name: str, arguments: dict[str, Any]) -> ToolResult:
    """Runs a tool with arguments checked and converted from what the model wrote ("3" for 3,
    null for an omitted value); unknown arguments are ignored rather than failing."""
    fn = TOOLS.get(name)
    if fn is None:
        return _error(f"Unknown tool {name}; available: {', '.join(TOOLS)}")
    params = inspect.signature(fn).parameters
    kwargs: dict[str, Any] = {}
    problems: list[str] = []
    for key, value in arguments.items():
        param = params.get(key)
        if param is None or key == "session":
            continue
        if value is None or value == "":
            if param.default is inspect.Parameter.empty:
                problems.append(f"{key} is required")
            continue
        try:
            kwargs[key] = TypeAdapter(param.annotation).validate_python(value)
        except ValidationError:
            problems.append(f"{key}: invalid value {value!r}")
    missing = [
        k
        for k, p in params.items()
        if k != "session" and p.default is inspect.Parameter.empty and k not in kwargs
    ]
    problems += [f"{k} is required" for k in missing if f"{k} is required" not in problems]
    if problems:
        return _error("Invalid arguments: " + "; ".join(problems))
    result: ToolResult = fn(session, **kwargs)
    return result


_CATEGORIES = [c.value for c in Category]
_DATE = {"type": "string", "description": "YYYY-MM-DD"}
_ID = {"document_id": {"type": "integer"}}


def _tool(
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {"type": "object", "properties": properties or {}}
    if required:
        parameters["required"] = required
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    }


# Sent with every agent message: descriptions say when to use the tool, briefly.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    _tool(
        "search_documents",
        "Find documents and their ids by keywords as written in them (issuer, type, words), "
        "category, type or issue date. Returns passages where the words appear, and the sum "
        "of amounts.",
        {
            "query": {"type": "string"},
            "category": {"type": "string", "enum": _CATEGORIES},
            "doc_type": {"type": "string", "enum": [t.value for t in DocType]},
            "since": _DATE,
            "until": _DATE,
            "limit": {"type": "integer"},
        },
    ),
    _tool(
        "read_document",
        "Read a document's fields and text; with `query`, only the passages about it. For "
        "details not in the fields (consumption, income, plate number…).",
        {**_ID, "query": {"type": "string"}, "offset": {"type": "integer"}},
        ["document_id"],
    ),
    _tool(
        "view_document",
        "Look at a page of a document as an image: layout, tables, handwriting, stamps, "
        "photos, or text that reads badly.",
        {**_ID, "page": {"type": "integer"}},
        ["document_id"],
    ),
    _tool(
        "explain_document",
        "Explain a document plainly and what to do about it.",
        _ID,
        ["document_id"],
    ),
    _tool(
        "list_deadlines",
        "Unpaid deadlines (payments, renewals, reminders) of the next `days` days with overdue "
        "ones, or between start and end; with their total.",
        {"days": {"type": "integer"}, "start": _DATE, "end": _DATE},
    ),
    _tool(
        "list_expirations",
        "Every document with an end of validity (ID card, passport, certificates, car "
        "inspection) and its state: expired, to renew now, valid.",
    ),
    _tool(
        "list_subscriptions",
        "Recurring bills and subscriptions, their yearly cost and price increases.",
    ),
    _tool(
        "check_folder",
        "Check a standard application pack: rental (landlord), mortgage (bank loan), caf "
        "(housing benefit). Pieces found, to renew or missing.",
        {"kind": {"type": "string", "enum": list(folders.KINDS)}},
        ["kind"],
    ),
    _tool("documents_to_review", "Documents set aside because something must be checked."),
    _tool(
        "documents_to_sort_out",
        "Documents that can be thrown away (retention period over, or replaced).",
    ),
    _tool(
        "create_reminder",
        "Create a reminder on a date (title in the user's language), linked to a document if any.",
        {
            "title": {"type": "string"},
            "due_date": _DATE,
            "amount": {"type": "number"},
            "document_id": {"type": "integer"},
        },
        ["title", "due_date"],
    ),
    _tool(
        "mark_deadline_paid",
        "Mark a deadline as paid/done when the user says so (paid=false reopens it). By "
        "deadline id, or by document id.",
        {
            "deadline_id": {"type": "integer"},
            "document_id": {"type": "integer"},
            "paid": {"type": "boolean"},
        },
    ),
    _tool(
        "update_document",
        "Correct a document's fields when the user asks (only the fields to change).",
        {
            **_ID,
            "title": {"type": "string"},
            "category": {"type": "string", "enum": _CATEGORIES},
            "issuer": {"type": "string"},
            "amount": {"type": "number"},
            "issue_date": _DATE,
            "due_date": _DATE,
            "expiry_date": _DATE,
            "reference": {"type": "string"},
        },
        ["document_id"],
    ),
    _tool(
        "validate_document",
        "Confirm that a document to review is correct, when the user says so.",
        _ID,
        ["document_id"],
    ),
    _tool(
        "trash_document",
        "Move a document to the trash (restorable), only when the user asks.",
        _ID,
        ["document_id"],
    ),
    _tool(
        "draft_letter",
        "Draft a letter shown to the user: termination (cancel a contract or subscription), "
        "complaint (dispute a bill), request (ask for a document). Pass the related document.",
        {
            "kind": {"type": "string", "enum": list(letters.KINDS)},
            "document_id": {"type": "integer"},
            "details": {"type": "string", "description": "facts to include, user's language"},
        },
        ["kind"],
    ),
    _tool(
        "export_folder",
        "ZIP download link: all documents, one category, or a pack (rental, mortgage, caf).",
        # No enum (saves tokens): find_category() accepts slugs and labels.
        {"category": {"type": "string"}, "pack": {"type": "string"}},
    ),
]


def schemas(vision: bool) -> list[dict[str, Any]]:
    """Tool definitions for the model; view_document only if it can see images."""
    if vision:
        return TOOL_SCHEMAS
    return [t for t in TOOL_SCHEMAS if t["function"]["name"] != "view_document"]
