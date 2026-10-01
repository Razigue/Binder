"""Changes to a document or a deadline, by the user (interface) or the agent: same rules, same
activity log."""

from typing import Any

from sqlmodel import Session

from binder import i18n
from binder.db import index_document
from binder.models import Deadline, Document, DocumentStatus
from binder.services import activity, embeddings, ingest, learning, organize, undo

# Namespace "api": these entries were logged from the routes, the keys must stay the same.
T = i18n.catalog(
    "api",
    {
        "kept_forever": {
            "en": "“{title}” kept beyond the recommended period",
            "fr": "« {title} » gardé au-delà de la durée conseillée",
        },
        "retention_again": {
            "en": "“{title}” back under the retention rules",
            "fr": "« {title} » de nouveau soumis au tri",
        },
        "not_duplicate": {
            "en": "“{title}” kept: it is not a duplicate",
            "fr": "« {title} » conservé : ce n'est pas un doublon",
        },
        "validated": {"en": "“{title}” validated", "fr": "« {title} » validé"},
        "deadline_done": {
            "en": "Deadline “{title}” marked as paid",
            "fr": "Échéance « {title} » marquée réglée",
        },
        "deadline_reopened": {
            "en": "Deadline “{title}” reopened",
            "fr": "Échéance « {title} » rouverte",
        },
        "deadline_updated": {
            "en": "Deadline “{title}” updated",
            "fr": "Échéance « {title} » modifiée",
        },
    },
)


def update_document(
    session: Session,
    doc: Document,
    changes: dict[str, Any],
    *,
    validated: bool = False,
    actor: str = "user",
) -> dict[str, tuple[Any, Any]]:
    """Applies field changes, logs them and refreshes status, deadlines, index and series.

    Returns the fields that actually changed (old, new). Does not commit."""
    previous_key = organize.series_key(doc)
    undo.document_changed(doc, undo.snapshot(doc))
    diff = {k: (getattr(doc, k), v) for k, v in changes.items() if getattr(doc, k) != v}
    if actor == "user":
        # The user corrected Binder: the next documents of this sender get the same treatment.
        learning.remember(session, doc, diff)
    for key, value in changes.items():
        setattr(doc, key, value)
    if "keep_forever" in diff:
        keep = diff.pop("keep_forever")[1]
        activity.log(
            session,
            "retention",
            T.msg("kept_forever" if keep else "retention_again", title=doc.title),
            actor=actor,
            document=doc,
        )
    if diff:
        doc.explanation = None
        doc.extractor = "manual" if doc.extractor == "rules" else doc.extractor
        activity.log(
            session,
            "update",
            activity.changes_summary(doc.title, diff),
            actor=actor,
            document=doc,
            details={k: {"old": old, "new": new} for k, (old, new) in diff.items()},
        )
    was_review = doc.status == DocumentStatus.TO_REVIEW
    was_duplicate = doc.duplicate_of is not None
    ingest.refresh_status(doc, validated=validated)
    if validated and was_duplicate:
        activity.log(
            session,
            "keep_duplicate",
            T.msg("not_duplicate", title=doc.title),
            actor=actor,
            document=doc,
        )
    elif validated and was_review:
        activity.log(
            session, "validate", T.msg("validated", title=doc.title), actor=actor, document=doc
        )
    session.add(doc)
    ingest.sync_deadline(session, doc)
    index_document(session, doc)
    if diff.keys() & {"title", "issuer", "category", "doc_type"}:
        embeddings.index(session, doc)
    organize.reorganize(session, doc, previous_key)
    return diff


def update_deadline(
    session: Session, deadline: Deadline, changes: dict[str, Any], *, actor: str = "user"
) -> None:
    """Applies the changes (e.g. done=True when paid) and logs them. Does not commit."""
    undo.push("deadline", id=deadline.id, state=undo.deadline_state(deadline))
    for key, value in changes.items():
        setattr(deadline, key, value)
    if "done" in changes:
        key = "deadline_done" if deadline.done else "deadline_reopened"
    else:
        key = "deadline_updated"
    summary = T.msg(key, title=deadline.title)
    activity.log(session, "deadline", summary, actor=actor, document_id=deadline.document_id)
    session.add(deadline)
