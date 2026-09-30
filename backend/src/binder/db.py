"""Moteur SQLite chiffré (SQLCipher) et index plein texte FTS5."""

from collections.abc import Iterator
from typing import Any

import sqlcipher3
from sqlalchemy import Engine, text
from sqlalchemy.pool import QueuePool
from sqlmodel import Session, SQLModel, create_engine

from binder import security
from binder.config import get_settings
from binder.models import Document

_engine: Engine | None = None


def _connect() -> Any:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlcipher3.connect(str(settings.db_path), check_same_thread=False)
    conn.execute(f"PRAGMA key = \"x'{security.db_key()}'\"")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine("sqlite://", creator=_connect, poolclass=QueuePool, pool_size=5)
        init_db(_engine)
    return _engine


def reset_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
    security.reset_caches()


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5("
                "title, category, issuer, reference, body, "
                "tokenize = 'unicode61 remove_diacritics 2')"
            )
        )


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def index_document(session: Session, doc: Document) -> None:
    session.execute(text("DELETE FROM document_fts WHERE rowid = :id"), {"id": doc.id})
    session.execute(
        text(
            "INSERT INTO document_fts(rowid, title, category, issuer, reference, body) "
            "VALUES (:id, :title, :category, :issuer, :reference, :body)"
        ),
        {
            "id": doc.id,
            "title": doc.title,
            "category": doc.category.value,
            "issuer": doc.issuer or "",
            "reference": doc.reference or "",
            "body": doc.text,
        },
    )


def unindex_document(session: Session, doc_id: int) -> None:
    session.execute(text("DELETE FROM document_fts WHERE rowid = :id"), {"id": doc_id})
