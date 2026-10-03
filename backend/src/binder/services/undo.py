"""Undo right after an action.

Services that change data push a step describing how to put it back (`push`) while a capture is
open (`capture`); the route or the agent then saves the steps under a token (`save`) that the
interface offers as "Undo" for a moment. Undoing replays the steps in reverse order and is
logged like any other action.
"""

import contextlib
import json
import secrets
from collections.abc import Iterator
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

from pydantic import TypeAdapter
from sqlmodel import Session, SQLModel, col, select

from binder import i18n, models
from binder.db import index_document
from binder.models import Deadline, Document, Setting, UndoEntry
from binder.services import activity, deadlines, organize

T = i18n.catalog(
    "undo",
    {
        "undone": {"en": "Undone: {what}", "fr": "Annulé : {what}"},
        "action": {"en": "last action", "fr": "dernière action"},
    },
)

# An undo is offered right after the action; older entries are dropped.
KEEP = timedelta(days=1)
# Document columns an action may change (not the file, its text or its identity).
DOCUMENT_STATE = (
    "title", "category", "issuer", "amount", "issue_date", "due_date", "expiry_date",
    "reference", "keep_forever", "confidence", "status", "missing_fields", "extractor",
    "doc_type", "duplicate_of", "duplicate_dismissed", "superseded_by", "person",
    "source_letter_id",
)  # fmt: skip
DEADLINE_STATE = ("title", "category", "due_date", "amount", "done", "source", "document_id")

# A step: its "kind" and what is needed to put things back (JSON values).
type Step = dict[str, Any]

_steps: ContextVar[list[Step] | None] = ContextVar("undo_steps", default=None)


class Capture:
    def __init__(self) -> None:
        self.steps: list[Step] = []
        self.label: str | i18n.Msg = ""


@contextlib.contextmanager
def capture() -> Iterator[Capture]:
    """Collects the undo steps of the actions run inside the block."""
    cap = Capture()
    token = _steps.set(cap.steps)
    try:
        yield cap
    finally:
        _steps.reset(token)


def active() -> bool:
    return _steps.get() is not None


def push(kind: str, **data: Any) -> None:
    steps = _steps.get()
    if steps is not None:
        steps.append({"kind": kind, **json.loads(json.dumps(data, default=str))})


def snapshot(doc: Document) -> dict[str, Any]:
    return {name: getattr(doc, name) for name in DOCUMENT_STATE}


def document_changed(doc: Document, before: dict[str, Any]) -> None:
    push("document", id=doc.id, state=before)


def deadline_state(deadline: Deadline) -> dict[str, Any]:
    return {name: getattr(deadline, name) for name in DEADLINE_STATE}


def save(session: Session, cap: Capture, *, actor: str = "user") -> str | None:
    """Stores the steps; returns the token to undo them, None when nothing changed."""
    if not cap.steps:
        return None
    _cleanup(session)
    token = secrets.token_urlsafe(12)
    session.add(UndoEntry(token=token, actor=actor, steps=json.dumps(cap.steps)))
    return token


def _cleanup(session: Session) -> None:
    limit = datetime.now(UTC) - KEEP
    for old in session.exec(select(UndoEntry).where(col(UndoEntry.created_at) < limit)):
        session.delete(old)


def _typed(model: type[SQLModel], name: str, value: Any) -> Any:
    return _adapter(model, name).validate_python(value)


@cache
def _adapter(model: type[SQLModel], name: str) -> TypeAdapter[Any]:
    return TypeAdapter(model.model_fields[name].annotation)


def _restore_document(session: Session, step: Step) -> None:
    doc = session.get(Document, step["id"])
    if doc is None:
        return
    previous_key = organize.series_key(doc)
    for name, value in step["state"].items():
        setattr(doc, name, _typed(Document, name, value))
    doc.explanation = None
    doc.updated_at = datetime.now(UTC)
    session.add(doc)
    session.flush()
    deadlines.sync(session, doc)
    if doc.deleted_at is None:
        index_document(session, doc)
    organize.reorganize(session, doc, previous_key)


def _apply(session: Session, step: Step, actor: str) -> None:
    # Imported here: these services push undo steps themselves.
    from binder.services import archive, ingest

    match step["kind"]:
        case "document":
            _restore_document(session, step)
        case "trash":
            doc = session.get(Document, step["id"])
            if doc is not None and doc.deleted_at is not None:
                ingest.restore(session, doc, actor=actor)
        case "restore":
            doc = session.get(Document, step["id"])
            if doc is not None and doc.deleted_at is None:
                ingest.trash(session, doc, actor=actor)
        case "archive":
            doc = session.get(Document, step["id"])
            if doc is not None:
                archive.unarchive(session, doc, actor=actor)
        case "unarchive":
            doc = session.get(Document, step["id"])
            if doc is not None:
                archive.archive(session, doc, step.get("reason"), actor=actor)
        case "deadline":
            _restore_row(session, Deadline, step)
        case "deadline_created":
            _delete_row(session, Deadline, step)
        case "deadline_deleted":
            session.add(Deadline(**_state(Deadline, step)))
        case "setting":
            row = session.get(Setting, step["key"])
            if step["value"] is None:
                if row is not None:
                    session.delete(row)
            else:
                row = row or Setting(key=step["key"])
                row.value = step["value"]
                session.add(row)
        case "row_state":
            _restore_row(session, getattr(models, step["model"]), step)
        case "row_created":
            _delete_row(session, getattr(models, step["model"]), step)
        case "row_deleted":
            table = getattr(models, step["model"])
            if session.get(table, step["id"]) is None:
                session.add(table(**_state(table, step)))


def _state(table: type[Any], step: Step) -> dict[str, Any]:
    return {k: _typed(table, k, v) for k, v in step["state"].items()}


def _restore_row(session: Session, table: type[Any], step: Step) -> None:
    row = session.get(table, step["id"])
    if row is not None:
        for name, value in _state(table, step).items():
            setattr(row, name, value)
        session.add(row)


def _delete_row(session: Session, table: type[Any], step: Step) -> None:
    row = session.get(table, step["id"])
    if row is not None:
        session.delete(row)


def undo(session: Session, token: str, *, actor: str = "user") -> bool:
    """Puts back what the action changed. False if the token is unknown or already used."""
    entry = session.exec(select(UndoEntry).where(UndoEntry.token == token)).first()
    if entry is None or entry.undone:
        return False
    for step in reversed(json.loads(entry.steps)):
        _apply(session, step, actor)
        session.flush()
    entry.undone = True
    session.add(entry)
    activity.log(session, "undo", T.msg("undone", what=T.msg("action")), actor=actor)
    return True


def row_changed(row: Any) -> None:
    """Call before changing a row of a simple table (no side effects to replay)."""
    state = row.model_dump(exclude={"id"})
    push("row_state", model=type(row).__name__, id=row.id, state=state)


def row_deleted(row: Any) -> None:
    """Call before deleting a row of a simple table: undo recreates it as it was."""
    push("row_deleted", model=type(row).__name__, id=row.id, state=row.model_dump())


def setting_changed(session: Session, key: str) -> None:
    """Call before changing a Setting: the undo puts its former value back."""
    row = session.get(Setting, key)
    push("setting", key=key, value=row.value if row else None)
