"""Shared by the API routers: database session dependency, lookups that answer 404, the
documents selected in a list and download headers."""

import re
import unicodedata
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, HTTPException
from sqlmodel import Session, SQLModel, col, select

from binder import i18n
from binder.db import get_session
from binder.models import Document

SessionDep = Annotated[Session, Depends(get_session)]

# Documents not in the trash (archived ones included).
ACTIVE = col(Document.deleted_at).is_(None)

# Namespace "api": the routes' messages have always lived there.
T = i18n.catalog(
    "api",
    {"doc_not_found": {"en": "Document not found", "fr": "Document introuvable"}},
)


def get_or_404[M: SQLModel](session: Session, model: type[M], row_id: object, detail: str) -> M:
    row = session.get(model, row_id)
    if row is None:
        raise HTTPException(404, detail)
    return row


def document_or_404(session: Session, doc_id: int, *, trashed: bool = False) -> Document:
    """Active document (or, with `trashed`, including those in the trash)."""
    doc = session.get(Document, doc_id)
    if doc is None or (doc.deleted_at is not None and not trashed):
        raise HTTPException(404, T("doc_not_found"))
    return doc


def selected(session: Session, ids: list[int], *, trashed: bool = False) -> list[Document]:
    """Documents chosen in a list, skipping unknown ids and those not in the expected place."""
    docs = session.exec(select(Document).where(col(Document.id).in_(set(ids))))
    return [d for d in docs if (d.deleted_at is not None) == trashed]


def safe_filename(name: str) -> str:
    """ASCII file name, safe for HTTP headers and archive paths."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9.\- ]", "_", ascii_name)


def disposition(kind: str, name: str) -> str:
    """Content-Disposition header: ASCII fallback + full UTF-8 name (RFC 6266)."""
    return f"{kind}; filename=\"{safe_filename(name)}\"; filename*=UTF-8''{quote(name)}"
