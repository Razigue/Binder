"""Encrypted SQLite engine (SQLCipher) and FTS5 full-text index."""

import threading
from collections.abc import Iterator
from typing import Any

import sqlcipher3
from sqlalchemy import Column, Engine, MetaData, text
from sqlalchemy.orm import defer
from sqlalchemy.pool import QueuePool
from sqlalchemy.schema import CreateTable
from sqlmodel import Session, SQLModel, create_engine, select

from binder import i18n, security
from binder.config import get_settings
from binder.models import HEAVY_COLUMNS, LEGACY_CATEGORY_NAMES, LEGACY_DOC_TYPES, Document

_engine: Engine | None = None
_engine_lock = threading.Lock()

# Large columns that lists never read: loaded only when accessed.
WITHOUT_TEXT = (defer(Document.text), defer(Document.explanation))  # type: ignore[arg-type]


def _connect() -> Any:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlcipher3.connect(str(settings.db_path), check_same_thread=False)
    conn.execute(f"PRAGMA key = \"x'{security.db_key()}'\"")
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL: readers do not wait for the background analysis, and a commit costs one fsync
    # less (NORMAL stays safe in WAL mode: a power cut loses at most the last commits).
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def get_engine() -> Engine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = create_engine("sqlite://", creator=_connect, poolclass=QueuePool, pool_size=5)
            init_db(_engine)
        return _engine


def reset_engine() -> None:
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
    security.reset_caches()


def _column_default(column: Column[Any]) -> str:
    """SQL default value of a column added to an existing table."""
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


# Filled when their column is added: values carried over from an older column.
BACKFILL = {
    # The former single amount becomes the total including tax.
    ("document", "amount_ttc"): "UPDATE document SET amount_ttc = amount",
}


def migrate(engine: Engine) -> None:
    """Adds the columns that appeared since the database was created (no column is dropped or
    renamed: databases from previous versions stay readable)."""
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
                if (table.name, column.name) in BACKFILL:
                    conn.execute(text(BACKFILL[(table.name, column.name)]))
                if column.index:
                    conn.execute(
                        text(
                            f'CREATE INDEX IF NOT EXISTS "ix_{table.name}_{column.name}" '
                            f'ON "{table.name}" ("{column.name}")'
                        )
                    )


def heavy_columns_last(engine: Engine) -> bool:
    """Rebuilds the document table when a column is stored after its large columns (databases
    created before they were moved, columns added since by ALTER TABLE): reading that column
    would go through every document's text. Returns True when the table was rebuilt.

    Follows SQLite's procedure for schema changes: new table, copy, drop, rename. Skipped when
    the table has columns this version does not know (newer database): they would be lost.
    """
    table = Document.__table__  # type: ignore[attr-defined]
    with engine.connect() as conn:
        names = [row[1] for row in conn.execute(text('PRAGMA table_info("document")'))]
        known = [c.name for c in table.columns]
        if set(names[-len(HEAVY_COLUMNS) :]) == set(HEAVY_COLUMNS) or set(names) - set(known):
            return False
        columns = ", ".join(f'"{name}"' for name in known)
        new = table.to_metadata(MetaData(), name="document_rebuild")
        # Only outside a transaction: the deadlines keep referencing the documents.
        conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
        conn.commit()
        try:
            # Explicit BEGIN: the driver would leave CREATE TABLE outside the transaction.
            conn.exec_driver_sql("BEGIN")
            conn.exec_driver_sql("DROP TABLE IF EXISTS document_rebuild")
            conn.execute(CreateTable(new))
            conn.exec_driver_sql(
                f"INSERT INTO document_rebuild ({columns}) SELECT {columns} FROM document"
            )
            conn.exec_driver_sql("DROP TABLE document")
            conn.exec_driver_sql("ALTER TABLE document_rebuild RENAME TO document")
            for index in table.indexes:
                index.create(conn)
            if conn.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                raise RuntimeError("Foreign key violation after rebuilding the documents")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.exec_driver_sql("PRAGMA foreign_keys = ON")
            conn.commit()
    return True


def migrate_identifiers(engine: Engine) -> bool:
    """Converts French category and document type identifiers to the English ones.

    Idempotent; returns True when rows changed (the full-text index must then be rebuilt).
    """
    changed = 0
    with engine.begin() as conn:
        for table in ("document", "deadline"):
            for old, new in LEGACY_CATEGORY_NAMES.items():
                result = conn.execute(
                    text(f'UPDATE "{table}" SET category = :new WHERE category = :old'),
                    {"old": old, "new": new},
                )
                changed += result.rowcount
        for label, doc_type in LEGACY_DOC_TYPES.items():
            result = conn.execute(
                text("UPDATE document SET doc_type = :new WHERE doc_type = :old"),
                {"old": label, "new": doc_type.value},
            )
            changed += result.rowcount
    return changed > 0


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    migrate(engine)
    heavy_columns_last(engine)
    reindex = migrate_identifiers(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5("
                "title, category, issuer, reference, body, "
                "tokenize = 'unicode61 remove_diacritics 2')"
            )
        )
    if reindex:
        with Session(engine) as session:
            for doc in session.exec(select(Document)):
                index_document(session, doc)
            session.commit()


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
            # Category labels in every language: "impôts" and "taxes" both find tax documents.
            "category": " ".join(
                i18n.category_label(doc.category.value, lang) for lang in i18n.LANGUAGES
            ),
            "issuer": doc.issuer or "",
            "reference": doc.reference or "",
            "body": doc.text,
        },
    )


def unindex_document(session: Session, doc_id: int) -> None:
    session.execute(text("DELETE FROM document_fts WHERE rowid = :id"), {"id": doc_id})
