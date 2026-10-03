"""Tidying up: standard file name, probable duplicates, successive versions.

Nothing is deleted here: a duplicate goes to review, an older version is simply marked as
superseded. The user decides afterwards.
"""

import mimetypes
import re
from difflib import SequenceMatcher

from sqlmodel import Session, col, or_, select

from binder import i18n
from binder.db import WITHOUT_TEXT
from binder.models import DocType, Document
from binder.services import activity, deadlines
from binder.services.rules import normalize

T = i18n.catalog(
    "organize",
    {
        "superseded": {
            "en": "“{title}” superseded by a newer version (dated {date:date})",
            "fr": "« {title} » remplacé par une version plus récente (du {date:date})",
        },
    },
)

# Documents for which only the latest version matters: the new one replaces the old one.
# Payslips are not among them: each one must be kept.
VERSIONED_TYPES = {
    DocType.CERTIFICATE,
    DocType.INSURANCE_CERTIFICATE,
    DocType.IDENTITY_CARD,
    DocType.PASSPORT,
    DocType.DRIVING_LICENCE,
    DocType.RESIDENCE_PERMIT,
    DocType.ROADWORTHINESS_TEST,
    DocType.VEHICLE_REGISTRATION,
}

SIMILARITY_THRESHOLD = 0.92
SIMILARITY_CHARS = 4000

_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def standard_name(doc: Document) -> str:
    """ "2026-09-18 EDF invoice.pdf": date, then the title (with the issuer). Sorts by date."""
    label = doc.title or doc.filename.rsplit(".", 1)[0]
    if doc.issuer and normalize(doc.issuer) not in normalize(label):
        label = f"{label} {doc.issuer}"
    when = deadlines.document_date(doc)
    ext = mimetypes.guess_extension(doc.mime_type) or ""
    if ext == ".jpe":
        ext = ".jpg"
    name = _FORBIDDEN.sub(" ", f"{when.isoformat()} {label}")
    return re.sub(r"\s+", " ", name).strip()[:120] + ext


def _candidates(session: Session, doc: Document) -> list[Document]:
    """Other originals of the same category whose date and amount do not contradict `doc`'s.

    Their text is only loaded for those compared with `doc`.
    """
    stmt = (
        select(Document)
        .options(*WITHOUT_TEXT)
        .where(col(Document.deleted_at).is_(None), Document.id != doc.id)
        .where(Document.category == doc.category, col(Document.duplicate_of).is_(None))
    )
    for column, value in (
        (Document.issue_date, doc.issue_date),
        (Document.amount, doc.amount),
        (Document.due_date, doc.due_date),
    ):
        if value is not None:
            stmt = stmt.where(or_(col(column).is_(None), column == value))
    return list(session.exec(stmt.order_by(col(Document.id))))


def _similar(a: str, b: str) -> bool:
    # normalize() keeps the length: cut first, the texts can be long.
    a, b = normalize(a[:SIMILARITY_CHARS]), normalize(b[:SIMILARITY_CHARS])
    if not a.strip() or not b.strip():
        return False
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    return matcher.real_quick_ratio() >= SIMILARITY_THRESHOLD and (
        matcher.quick_ratio() >= SIMILARITY_THRESHOLD and matcher.ratio() >= SIMILARITY_THRESHOLD
    )


def find_duplicate(session: Session, doc: Document) -> Document | None:
    """Existing document with nearly identical content (another scan, another download).

    Two documents with different dates or amounts are never duplicates: this is the case of
    a supplier's monthly bills, whose text is very similar.
    """
    for other in _candidates(session, doc):
        same_keys = (
            doc.reference is not None
            and doc.reference == other.reference
            and doc.issue_date is not None
            and doc.issue_date == other.issue_date
            and doc.amount == other.amount
        )
        if same_keys or _similar(doc.text, other.text):
            return other
    return None


def detect_duplicate(session: Session, doc: Document) -> None:
    if doc.duplicate_dismissed:
        doc.duplicate_of = None
        return
    original = find_duplicate(session, doc)
    doc.duplicate_of = original.id if original else None


def release_duplicates(session: Session, original: Document) -> list[Document]:
    """The original goes to the trash: its duplicates are no longer duplicates."""
    freed = list(session.exec(select(Document).where(Document.duplicate_of == original.id)))
    for doc in freed:
        doc.duplicate_of = None
        session.add(doc)
    return freed


def series_key(doc: Document) -> tuple[str, str] | None:
    """Version series: same (versioned) type and same issuer. None outside any series."""
    if doc.doc_type not in VERSIONED_TYPES or doc.duplicate_of is not None:
        return None
    if doc.deleted_at is not None:
        return None
    return doc.doc_type, normalize(doc.issuer or "")


def update_series(session: Session, *keys: tuple[str, str] | None) -> None:
    """In each series, marks the versions superseded by the most recent one."""
    for key in {k for k in keys if k is not None}:
        candidates = session.exec(
            select(Document)
            .options(*WITHOUT_TEXT)
            .where(
                col(Document.deleted_at).is_(None),
                Document.doc_type == key[0],
                col(Document.duplicate_of).is_(None),
            )
        )
        series = [d for d in candidates if series_key(d) == key]
        if not series:
            continue
        latest = max(series, key=lambda d: (d.issue_date or d.created_at.date(), d.id or 0))
        for d in series:
            target = None if d is latest else latest.id
            if d.superseded_by == target:
                continue
            d.superseded_by = target
            session.add(d)
            deadlines.sync(session, d)
            if target is not None:
                activity.log(
                    session,
                    "supersede",
                    T.msg("superseded", title=d.title, date=latest.issue_date),
                    document=d,
                    details={"superseded_by": latest.id},
                )


def reorganize(session: Session, doc: Document, previous_key: tuple[str, str] | None) -> None:
    """After a change (analysis, correction, trash): series before and after."""
    key = series_key(doc)
    if key is None and doc.superseded_by is not None:
        doc.superseded_by = None
        session.add(doc)
        deadlines.sync(session, doc)
    session.flush()
    update_series(session, previous_key, key)
