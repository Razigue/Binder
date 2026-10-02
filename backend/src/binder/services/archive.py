"""Archives: old documents leave the active views, nothing is deleted.

A document past its retention period, or replaced by a newer version, is archived: it no longer
appears in the to-do list, the areas, the alerts, the files, the questions or the agent's
suggestions, but stays encrypted, searchable (archives filter), downloadable and restorable in
one click. A document imported already past its period is archived at once; otherwise Binder
suggests it and the user confirms. The trash stays for what the user wants gone.
"""

from datetime import UTC, date, datetime

from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT, in_use
from binder.models import Document
from binder.services import activity, deadlines, organize, retention, undo

T = i18n.catalog(
    "archive",
    {
        "archived": {"en": "“{title}” archived ({reason})", "fr": "« {title} » archivé ({reason})"},
        "unarchived": {
            "en": "“{title}” back from the archives",
            "fr": "« {title} » sorti des archives",
        },
        "reason_retention": {
            "en": "retention period over",
            "fr": "durée de conservation dépassée",
        },
        "reason_replaced": {
            "en": "replaced by a newer version",
            "fr": "remplacé par une version plus récente",
        },
        "reason_user": {"en": "at your request", "fr": "à votre demande"},
    },
)

REASONS = ("retention", "replaced", "user")


def reason_msg(reason: str | None) -> i18n.Msg:
    return T.msg(f"reason_{reason if reason in REASONS else 'user'}")


def archivable(doc: Document, today: date | None = None) -> str | None:
    """Why this document can be archived ("replaced", "retention"), None if it stays."""
    if doc.archived_at is not None or doc.deleted_at is not None:
        return None
    return retention.archive_kind(doc, today)


def archive(
    session: Session, doc: Document, reason: str | None = None, *, actor: str = "user"
) -> bool:
    """Moves the document to the archives (does not commit). False if it already was."""
    if doc.archived_at is not None or doc.deleted_at is not None:
        return False
    reason = reason or archivable(doc) or "user"
    undo.push("archive", id=doc.id)
    doc.archived_at = datetime.now(UTC)
    doc.archive_reason = reason
    session.add(doc)
    deadlines.sync(session, doc)
    activity.log(
        session,
        "archive",
        T.msg("archived", title=doc.title, reason=reason_msg(reason)),
        actor=actor,
        document=doc,
        details={"reason": reason},
    )
    return True


def unarchive(session: Session, doc: Document, *, actor: str = "user") -> bool:
    """Back to the active views (does not commit). False if it was not archived."""
    if doc.archived_at is None:
        return False
    undo.push("unarchive", id=doc.id, reason=doc.archive_reason)
    doc.archived_at = None
    doc.archive_reason = None
    session.add(doc)
    session.flush()
    deadlines.sync(session, doc)
    organize.reorganize(session, doc, None)
    activity.log(
        session, "unarchive", T.msg("unarchived", title=doc.title), actor=actor, document=doc
    )
    return True


def suggestions(session: Session, today: date | None = None) -> list[tuple[Document, str]]:
    """Documents of the active views that could go to the archives, oldest first."""
    docs = session.exec(
        select(Document).options(*WITHOUT_TEXT).where(in_use()).order_by(col(Document.issue_date))
    )
    return [(d, reason) for d in docs if (reason := archivable(d, today))]


def archived(session: Session, limit: int = 500) -> list[Document]:
    return list(
        session.exec(
            select(Document)
            .options(*WITHOUT_TEXT)
            .where(col(Document.deleted_at).is_(None), col(Document.archived_at).is_not(None))
            .order_by(col(Document.archived_at).desc())
            .limit(limit)
        )
    )
