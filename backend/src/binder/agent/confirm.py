"""Changes the agent proposes after reading content it did not write.

A document, a mail or a web page may carry instructions ("move this file to the trash",
"your address is now…"). Once a turn has read such content, the changes that cannot be
redone from the documents (trash, corrections, the user's details) are not made by the model:
they wait for the user to confirm them in the app.
"""

import secrets
import threading
import time
from typing import Any

from pydantic import BaseModel
from sqlmodel import Session

from binder import i18n
from binder.models import Document

# Changes held back for the user's confirmation once content was read.
GUARDED = {"trash_document", "archive_documents", "update_document", "update_profile"}
# Tools whose result carries content written by others (documents, mails, web pages).
READS_CONTENT = {
    "search_documents", "read_document", "view_document", "explain_document", "web_search",
    "read_web_page",
}  # fmt: skip
# How long a proposal can be confirmed.
TTL = 3600.0
# Told to the model instead of the result.
HELD_BACK = (
    "Not done yet: this change follows content read from a document, a mail or the web, so the "
    "app shows it to the user, who confirms it. Tell the user it awaits their confirmation."
)

T = i18n.catalog(
    "confirm",
    {
        "trash_document": {
            "en": "Move “{title}” to the trash",
            "fr": "Mettre « {title} » à la corbeille",
        },
        "archive_documents": {
            "en": "Archive: {titles}",
            "fr": "Archiver : {titles}",
        },
        "update_document": {
            "en": "Change {fields} of “{title}”",
            "fr": "Modifier {fields} de « {title} »",
        },
        "update_profile": {
            "en": "Save in your details: {fields}",
            "fr": "Enregistrer dans vos informations : {fields}",
        },
        "separator": {"en": ", ", "fr": ", "},
        "done": {"en": "Done.", "fr": "C'est fait."},
        "expired": {
            "en": "This proposal has expired: ask again.",
            "fr": "Cette proposition a expiré : redemandez-la.",
        },
    },
)


class PendingAction(BaseModel):
    token: str
    tool: str
    # What the change does, in the user's language.
    description: str


_pending: dict[str, tuple[float, str, dict[str, Any]]] = {}
_lock = threading.Lock()


def _describe(session: Session, name: str, arguments: dict[str, Any]) -> str:
    sep = T.get("separator")
    if name == "update_profile":
        fields = [f"{v}" for k, v in arguments.items() if v not in (None, "")]
        return T(name, fields=sep.join(fields))
    if name == "archive_documents":
        ids = [int(i) for i in arguments.get("document_ids") or [] if str(i).isdigit()]
        titles = [d.title if (d := session.get(Document, i)) else f"#{i}" for i in ids[:10]]
        return T(name, titles=sep.join(titles))
    doc_id = arguments.get("document_id")
    doc = session.get(Document, int(str(doc_id))) if str(doc_id or "").isdigit() else None
    title = doc.title if doc is not None else f"#{doc_id}"
    if name == "trash_document":
        return T(name, title=title)
    changed = [k for k, v in arguments.items() if k != "document_id" and v not in (None, "")]
    return T(name, title=title, fields=sep.join(i18n.field_label(f) for f in changed))


def propose(session: Session, name: str, arguments: dict[str, Any]) -> PendingAction:
    """Holds a change back until the user confirms it."""
    token = secrets.token_urlsafe(12)
    now = time.monotonic()
    with _lock:
        for old in [t for t, (at, _, _) in _pending.items() if now - at > TTL]:
            del _pending[old]
        _pending[token] = (now, name, dict(arguments))
    return PendingAction(token=token, tool=name, description=_describe(session, name, arguments))


def take(token: str) -> tuple[str, dict[str, Any]] | None:
    """The change to make now that the user confirmed it (once), None if unknown or expired."""
    with _lock:
        entry = _pending.pop(token, None)
    if entry is None or time.monotonic() - entry[0] > TTL:
        return None
    return entry[1], entry[2]
