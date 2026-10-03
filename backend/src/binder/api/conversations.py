"""Conversations with the agent, kept in the encrypted database so the user can go back to them.

The interface owns the turns (question, attachments, answer as shown) and saves them after each
answer; the agent only receives the last ones as history with each question."""

import json
import re
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from binder import i18n
from binder.api.common import SessionDep, get_or_404
from binder.db import WITHOUT_TEXT
from binder.models import Conversation, Document
from binder.services import activity

router = APIRouter(prefix="/api/conversations")

T = i18n.catalog(
    "conversations",
    {
        "not_found": {"en": "Conversation not found", "fr": "Conversation introuvable"},
        "too_large": {"en": "Conversation too long to save", "fr": "Conversation trop longue"},
        "deleted": {
            "en": "Conversation “{title}” deleted",
            "fr": "Conversation « {title} » supprimée",
        },
    },
)

# Conversations listed, newest first.
LIST_LIMIT = 100
TITLE_CHARS = 80
# Document references in questions sent from a page ("renew “Identity card” [#15]").
CITATION = re.compile(r"\s*\[#\d+\]")
# Serialized turns: answers carry their documents, a long conversation stays far below this.
MAX_BYTES = 5_000_000

Turns = Annotated[list[dict[str, Any]], Field(max_length=500)]


class ConversationCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    document_id: int | None = None
    turns: Turns = []


class ConversationEdit(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    turns: Turns | None = None


class ConversationSummary(BaseModel):
    id: int
    title: str
    document_id: int | None
    # Title of that document, None once it is deleted.
    document_title: str | None
    created_at: datetime
    updated_at: datetime
    turns: int


class ConversationOut(ConversationSummary):
    messages: list[dict[str, Any]]


def _title(turns: list[dict[str, Any]]) -> str:
    """The first question, cut at a word; the first attachment's title without one."""
    for turn in turns:
        question = " ".join(CITATION.sub("", str(turn.get("question") or "")).split())
        if question:
            if len(question) <= TITLE_CHARS:
                return question
            return question[:TITLE_CHARS].rsplit(" ", 1)[0] + "…"
        for attachment in turn.get("attachments") or []:
            if isinstance(attachment, dict) and attachment.get("title"):
                return str(attachment["title"])[:TITLE_CHARS]
    return ""


def _dump(turns: list[dict[str, Any]]) -> str:
    text = json.dumps(turns, ensure_ascii=False)
    if len(text.encode()) > MAX_BYTES:
        raise HTTPException(413, T("too_large"))
    return text


def _conversation(session: Session, conversation_id: int) -> Conversation:
    return get_or_404(session, Conversation, conversation_id, T("not_found"))


def _summary(row: Conversation, turns: int, doc: Document | None) -> ConversationSummary:
    assert row.id is not None
    return ConversationSummary(
        id=row.id,
        title=row.title,
        document_id=row.document_id,
        document_title=doc.title if doc and doc.deleted_at is None else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        turns=turns,
    )


def _out(session: Session, row: Conversation) -> ConversationOut:
    turns: list[dict[str, Any]] = json.loads(row.turns)
    doc = session.get(Document, row.document_id) if row.document_id else None
    return ConversationOut(**_summary(row, len(turns), doc).model_dump(), messages=turns)


@router.get("")
def list_conversations(session: SessionDep) -> list[ConversationSummary]:
    rows = session.exec(
        select(Conversation).order_by(col(Conversation.updated_at).desc()).limit(LIST_LIMIT)
    ).all()
    ids = {r.document_id for r in rows if r.document_id}
    docs = {
        d.id: d
        for d in session.exec(
            select(Document).options(*WITHOUT_TEXT).where(col(Document.id).in_(ids))
        )
    }
    return [_summary(r, len(json.loads(r.turns)), docs.get(r.document_id)) for r in rows]


@router.post("")
def create_conversation(body: ConversationCreate, session: SessionDep) -> ConversationOut:
    row = Conversation(
        title=body.title.strip() or _title(body.turns),
        document_id=body.document_id,
        turns=_dump(body.turns),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(session, row)


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, session: SessionDep) -> ConversationOut:
    return _out(session, _conversation(session, conversation_id))


@router.patch("/{conversation_id}")
def edit_conversation(
    conversation_id: int, body: ConversationEdit, session: SessionDep
) -> ConversationOut:
    row = _conversation(session, conversation_id)
    if body.turns is not None:
        row.turns = _dump(body.turns)
        row.updated_at = datetime.now(UTC)
        if not row.title:
            row.title = _title(body.turns)
    if body.title is not None:
        row.title = body.title.strip() or _title(json.loads(row.turns))
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(session, row)


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, session: SessionDep) -> None:
    """Deleted on the user's request (the interface offers to bring it back for a moment)."""
    row = _conversation(session, conversation_id)
    activity.log(session, "conversation", T.msg("deleted", title=row.title), actor="user")
    session.delete(row)
    session.commit()
