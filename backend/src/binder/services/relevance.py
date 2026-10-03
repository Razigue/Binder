"""Whether a doubt about a document is worth bothering the user.

Binder asks only when the answer changes something today: a deadline coming up or unpaid, a
document still in force (identity, contract, insurance, vehicle), a bill that is still being
followed. An old document is never asked about; a field that has no effect is left "not filled
in" and the document is filed as it is. The thresholds below are named so that they are easy
to change (docs/ux-refonte.md).
"""

import json
from datetime import date

from binder.models import Category, DocType, Document
from binder.services import retention

# An old document: issued more than two years ago with nothing in the future…
OLD_AFTER_DAYS = 730
# …or a payment date passed for more than 90 days.
STALE_DUE_DAYS = 90
# A deadline within this window, or a document this recent, is followed.
ACTIVE_DAYS = 90

# Documents whose validity is still running matter as long as they are in force.
VALIDITY_CATEGORIES = {Category.IDENTITY, Category.INSURANCE, Category.VEHICLE}
VALIDITY_TYPES = {
    DocType.CONTRACT, DocType.EMPLOYMENT_CONTRACT, DocType.LEASE, DocType.LOAN_STATEMENT,
    DocType.INSURANCE_CERTIFICATE, DocType.PURCHASE_RECEIPT,
}  # fmt: skip
# Bills that come back (subscriptions): a recent one is followed.
RECURRING_CATEGORIES = {Category.ENERGY, Category.TELECOM, Category.INSURANCE, Category.HOUSING}

# Below this confidence, a recent or valid document gets a "is this right?" question.
CONFIDENT = 0.6
# Doubts of the reading that concern the whole document, not one field.
WHOLE_DOCUMENT = {"inconsistent_amounts", "truncated", "several_documents", "transcribed"}


def is_old(doc: Document, today: date | None = None) -> bool:
    """Past documents: never a question, filed (or archived) as they are."""
    today = today or date.today()
    if doc.archived_at is not None or doc.superseded_by is not None:
        return True
    if retention.archive_kind(doc, today) is not None:
        return True
    if any(d is not None and d >= today for d in (doc.due_date, doc.expiry_date)):
        return False
    if doc.due_date is not None and (today - doc.due_date).days > STALE_DUE_DAYS:
        return True
    return doc.issue_date is not None and (today - doc.issue_date).days > OLD_AFTER_DAYS


def _recent(doc: Document, today: date) -> bool:
    when = doc.issue_date or doc.created_at.date()
    return (today - when).days <= ACTIVE_DAYS


def _in_force(doc: Document) -> bool:
    return doc.category in VALIDITY_CATEGORIES or doc.doc_type in VALIDITY_TYPES


def _deadline_near(doc: Document, today: date) -> bool:
    """A payment due within the window, or due and not long past (unpaid)."""
    if doc.due_date is None:
        return False
    return -STALE_DUE_DAYS <= (doc.due_date - today).days <= ACTIVE_DAYS


def field_matters(doc: Document, field: str, today: date | None = None) -> bool:
    """Whether a missing or doubtful field has an effect today."""
    today = today or date.today()
    if is_old(doc, today):
        return False
    if field in ("amount", "amount_due", "amount_ttc"):
        followed = doc.category in RECURRING_CATEGORIES and _recent(doc, today)
        return _deadline_near(doc, today) or followed
    if field == "due_date":
        return _recent(doc, today) and doc.category not in VALIDITY_CATEGORIES
    if field == "expiry_date":
        return _in_force(doc)
    # Issue date, reference, issuer, person: kept "not filled in", nothing depends on them.
    return False


def worth_asking(doc: Document, today: date | None = None) -> list[str]:
    """The problems of a document that deserve a question (empty: file it as it is).

    Values: "duplicate", "text", "category", a field name, or "confirm" (a reading Binder is
    unsure of)."""
    today = today or date.today()
    if is_old(doc, today):
        return []
    missing = [m for m in json.loads(doc.missing_fields or "[]") if ":" not in m]
    doubts = json.loads(doc.doubts or "[]")
    if doc.duplicate_of is not None:
        return ["duplicate"]
    if "text" in missing or not (doc.text or "").strip():
        return ["text"]
    if doc.category == Category.OTHER:
        return ["category"]
    asked = [f for f in missing if f != "duplicate" and field_matters(doc, f, today)]
    for doubt in doubts:
        code, _, field = doubt.partition(":")
        if (field and field_matters(doc, field, today)) or (
            not field and code in WHOLE_DOCUMENT and (_recent(doc, today) or _in_force(doc))
        ):
            asked.append("confirm")
    if not asked and doc.confidence < CONFIDENT and (_recent(doc, today) or _in_force(doc)):
        asked.append("confirm")
    return list(dict.fromkeys(asked))
