"""Moteur SQLite chiffré (SQLCipher) et index plein texte FTS5."""

from collections.abc import Iterator
from typing import Any

import sqlcipher3
from sqlalchemy import Column, Engine, text
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


def _column_default(column: Column[Any]) -> str:
    """Valeur par défaut SQL d'une colonne ajoutée à une table existante."""
    default = getattr(column.default, "arg", None)
    if isinstance(default, bool):
        return "1" if default else "0"
    if isinstance(default, int | float):
        return str(default)
    if isinstance(default, str):
        return "'" + default.replace("'", "''") + "'"
    if column.nullable:
        return "NULL"
    python_type = column.type.python_type
    return "0" if python_type in (int, float, bool) else "''"


def migrate(engine: Engine) -> None:
    """Ajoute les colonnes apparues depuis la création de la base (pas de suppression ni de
    renommage : les bases des versions précédentes restent lisibles)."""
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            existing = {row[1] for row in conn.execute(text(f'PRAGMA table_info("{table.name}")'))}
            if not existing:
                continue
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = column.type.compile(dialect=conn.dialect)
                conn.execute(
                    text(
                        f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl} '
                        f"DEFAULT {_column_default(column)}"
                    )
                )
                if column.index:
                    conn.execute(
                        text(
                            f'CREATE INDEX IF NOT EXISTS "ix_{table.name}_{column.name}" '
                            f'ON "{table.name}" ("{column.name}")'
                        )
                    )


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    migrate(engine)
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
