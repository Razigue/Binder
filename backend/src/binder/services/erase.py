"""Erasing everything Binder holds about the user, on explicit request from Settings.

Documents (and their encrypted files), reminders, letters, life events, learned corrections,
history and what Binder deduced (profile, briefing...) go. The machine's configuration stays:
language and country, chosen model, import sources and backups, so Binder keeps working and an
earlier backup can still bring the data back.
"""

from sqlalchemy import delete, text
from sqlmodel import Session, col, select

from binder import i18n
from binder.config import get_settings
from binder.models import (
    Activity,
    Correspondence,
    Deadline,
    Document,
    Journey,
    Learned,
    Setting,
    UndoEntry,
)
from binder.services import activity, backup, embeddings, importers, llm_models, preferences

T = i18n.catalog(
    "erase",
    {
        "erased_one": {
            "en": "All data erased ({n} document)",
            "fr": "Toutes les données effacées ({n} document)",
        },
        "erased_other": {
            "en": "All data erased ({n} documents)",
            "fr": "Toutes les données effacées ({n} documents)",
        },
    },
)

# Settings describing the machine rather than the user's papers.
KEPT_SETTINGS = frozenset(
    {
        preferences.KEY,
        llm_models.KEY,
        backup.KEY,
        importers.FOLDER_KEY,
        importers.MAIL_KEY,
    }
)


def erase_all(session: Session) -> int:
    """Removes the user's data from the database; returns the number of documents erased.
    Call `delete_files` once committed, so a failed transaction never loses a file.

    The history keeps a single entry saying it happened.
    """
    count = len(session.exec(select(Document.id)).all())
    for model in (Deadline, Correspondence, Journey, Learned, UndoEntry, Activity, Document):
        session.execute(delete(model))
    session.execute(text("DELETE FROM document_fts"))
    embeddings.forget_all(session)
    session.execute(delete(Setting).where(col(Setting.key).not_in(KEPT_SETTINGS)))
    activity.log(session, "purge", T.plural_msg("erased", count), actor="user")
    session.flush()
    return count


def delete_files(session: Session) -> int:
    """Deletes every stored file no document points to: the erased ones and those older
    versions left behind."""
    files_dir = get_settings().files_dir
    if not files_dir.is_dir():
        return 0
    known = set(session.exec(select(Document.stored_name)))
    orphans = [p for p in files_dir.iterdir() if p.is_file() and p.name not in known]
    for path in orphans:
        path.unlink(missing_ok=True)
    return len(orphans)
