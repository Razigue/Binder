"""Invisible learning: what the user corrects is applied to the next documents of the sender.

A correction of the category, type or sender name is remembered as is. For an amount or a date,
Binder remembers the label written just before the right value ("Net à payer", "Prélevé le"),
and reads the value after that label in the next documents of the same sender. Nothing is shown
to the user; the history notes when a lesson was applied.
"""

import json
import re
from datetime import UTC, date, datetime
from typing import Any

from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT
from binder.models import Category, Document, DocumentStatus, Learned
from binder.schemas import Extraction
from binder.services import activity, rules

T = i18n.catalog(
    "learning",
    {
        "applied": {
            "en": "“{title}”: your earlier corrections for {sender} applied",
            "fr": "« {title} » : vos corrections précédentes pour {sender} appliquées",
        },
    },
)

# Fields remembered as values, and fields remembered by the label preceding them.
VALUE_FIELDS = ("issuer", "category", "doc_type")
LABEL_FIELDS = ("amount", "due_date", "issue_date", "expiry_date")
# Words kept before a value to recognise it next time.
LABEL_WORDS = 4

NUMBER = re.compile(r"(?<![\d,.])(\d{1,3}(?:[ .  ]\d{3})+|\d+)[,.](\d{2})(?!\d)")


def sender_key(issuer: str | None, text: str) -> str:
    """Who sent the document: its issuer, otherwise its first line (letterhead)."""
    if issuer:
        return rules.normalize(issuer).strip()
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return rules.normalize(first)[:40]


def _amount_variants(value: float) -> list[str]:
    units, cents = f"{value:.2f}".split(".")
    grouped = f"{int(units):,}".replace(",", " ")
    return [f"{grouped},{cents}", f"{units},{cents}", f"{units}.{cents}", f"{grouped}.{cents}"]


def _date_variants(value: date) -> list[str]:
    month = next(name for name, n in rules.MONTHS.items() if n == value.month)
    return [
        value.strftime("%d/%m/%Y"),
        value.strftime("%d.%m.%Y"),
        value.strftime("%d-%m-%Y"),
        value.isoformat(),
        f"{value.day} {month} {value.year}",
        f"{value.day:02d} {month} {value.year}",
        f"1er {month} {value.year}" if value.day == 1 else "",
    ]


def _clean(line: str) -> str:
    return rules.normalize(line).replace("\u00a0", " ").replace("\u202f", " ")


def _label_before(text: str, needles: list[str]) -> str:
    """Normalized words written just before the first occurrence of the value: on its line,
    or on the line above when the value stands alone (a table cell)."""
    lines = [_clean(raw) for raw in text.splitlines() if raw.strip()]
    for i, line in enumerate(lines):
        for needle in filter(None, needles):
            at = line.find(needle)
            if at < 0:
                continue
            words = re.findall(r"[a-z]+(?:'[a-z]+)?", line[:at])
            if not words and i > 0:
                words = re.findall(r"[a-z]+(?:'[a-z]+)?", lines[i - 1])
            if words:
                return " ".join(words[-LABEL_WORDS:])
    return ""


def remember(session: Session, doc: Document, diff: dict[str, tuple[Any, Any]]) -> None:
    """Stores the user's corrections of `doc` (diff: field → (old, new)). Does not commit."""
    if not diff:
        return
    old_issuer = diff["issuer"][0] if "issuer" in diff else doc.issuer
    sender = sender_key(old_issuer, doc.text)
    if not sender:
        return
    for name, (_, new) in diff.items():
        label = ""
        if name in LABEL_FIELDS:
            if new is None:
                continue
            needles = _amount_variants(new) if name == "amount" else _date_variants(new)
            label = _label_before(doc.text, needles)
            if not label:
                continue
        elif name not in VALUE_FIELDS:
            continue
        value = json.dumps(i18n.jsonable(new.value if isinstance(new, Category) else new))
        row = session.exec(
            select(Learned).where(Learned.sender == sender, Learned.field == name)
        ).first()
        if row is None:
            row = Learned(sender=sender, field=name, value=value, label=label, count=0)
        row.value, row.label = value, label
        row.count += 1
        row.updated_at = datetime.now(UTC)
        session.add(row)


def _value_after(lines: list[str], label: str, field: str) -> Any:
    for i, line in enumerate(lines):
        at = line.find(label)
        if at < 0:
            continue
        rest = line[at + len(label) :]
        following = " ".join(lines[i + 1 : i + 2])
        if field == "amount":
            m = NUMBER.search(rest) or NUMBER.search(following)
            if m:
                return rules.parse_amount(m[1], m[2])
        else:
            found = rules.find_dates(rest) or rules.find_dates(following)
            if found:
                return found[0]
    return None


def apply(session: Session, text: str, ext: Extraction) -> list[str]:
    """Applies the lessons learned for this sender to a fresh extraction; returns the fields
    it changed."""
    sender = sender_key(ext.issuer, text)
    if not sender:
        return []
    lessons = session.exec(select(Learned).where(Learned.sender == sender)).all()
    if not lessons:
        return []
    lines = [
        rules.normalize(line).replace(" ", " ").replace(" ", " ")
        for line in text.splitlines()
        if line.strip()
    ]
    changed = []
    for lesson in lessons:
        if lesson.field in LABEL_FIELDS:
            value = _value_after(lines, lesson.label, lesson.field)
        else:
            value = json.loads(lesson.value)
            if lesson.field == "category":
                value = Category(value)
        if value is None or getattr(ext, lesson.field) == value:
            continue
        setattr(ext, lesson.field, value)
        changed.append(lesson.field)
    if changed:
        # The user already decided for this sender: no need to ask again.
        ext.confidence = max(ext.confidence, 0.9)
    return changed


def log_applied(session: Session, doc: Document, fields: list[str]) -> None:
    if fields:
        activity.log(
            session,
            "learned",
            T.msg("applied", title=doc.title, sender=doc.issuer or doc.title),
            document=doc,
            details={"fields": fields},
        )


# Where the sender's name stands: the letterhead and the first lines.
HEAD_CHARS = 1500
# Fields whose presence the example reports (not their values: they are each document's own).
EXAMPLE_FIELDS = (
    "amount_ht", "amount_tva", "amount_ttc", "amount_due", "issue_date", "due_date",
    "expiry_date", "period_start", "period_end", "reference", "iban", "siret", "person",
)  # fmt: skip


def example(session: Session, text: str, exclude: int | None = None) -> dict[str, Any] | None:
    """How the last filed document of the sender of `text` was read, shown to the model with
    the new one: recurring bills and payslips are then filed alike. The sender is the issuer
    of the library whose name the first lines of `text` carry (the longest, most specific)."""
    head = rules.normalize(text[:HEAD_CHARS])
    issuers = session.exec(
        select(Document.issuer)
        .where(
            col(Document.deleted_at).is_(None),
            Document.status == DocumentStatus.CLASSIFIED,
            col(Document.issuer).is_not(None),
        )
        .distinct()
    ).all()
    named = [
        issuer
        for issuer in issuers
        if issuer
        and len(key := rules.normalize(issuer).strip()) >= 3
        and re.search(rf"(?<!\w){re.escape(key)}(?!\w)", head)
    ]
    if not named:
        return None
    sender = max(named, key=len)
    stmt = (
        select(Document)
        .options(*WITHOUT_TEXT)
        .where(
            col(Document.deleted_at).is_(None),
            Document.status == DocumentStatus.CLASSIFIED,
            Document.issuer == sender,
        )
    )
    if exclude is not None:
        stmt = stmt.where(Document.id != exclude)
    order = (col(Document.issue_date).desc(), col(Document.id).desc())
    doc = session.exec(stmt.order_by(*order)).first()
    if doc is None:
        return None
    return {
        "category": doc.category.value,
        "doc_type": doc.doc_type,
        "issuer": doc.issuer,
        "title": doc.title,
        "fields": [f for f in EXAMPLE_FIELDS if getattr(doc, f) is not None],
    }
