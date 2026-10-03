"""Agent routes: a question (whole answer or streamed), and the confirmation of a change the
agent proposed."""

import json
import logging
import queue
import threading
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from binder import i18n
from binder.agent import confirm, loop, tools
from binder.api.common import SessionDep, document_or_404
from binder.db import get_engine
from binder.models import Document
from binder.schemas import ChatRequest, ChatResponse, ConfirmResult
from binder.services import ingest, undo

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

T = i18n.catalog(
    "api",
    {
        "agent_failed": {
            "en": "The assistant ran into a problem. Try again.",
            "fr": "L'assistant a rencontré un problème. Réessayez.",
        },
    },
)


def _viewed(session: Session, body: ChatRequest) -> Document | None:
    """The document open on screen, unless it is attached or gone (a stale page): ignored rather
    than refused, the question still gets an answer."""
    if body.viewing is None or body.viewing in body.attachments:
        return None
    doc = session.get(Document, body.viewing)
    return doc if doc is not None and doc.deleted_at is None else None


@router.post("/agent/chat")
def chat(body: ChatRequest, session: SessionDep) -> ChatResponse:
    attached = [
        ingest.wait_for_analysis(session, document_or_404(session, doc_id))
        for doc_id in dict.fromkeys(body.attachments)
    ]
    with undo.capture() as cap:
        try:
            response = loop.run(
                session, body.message, body.history, attached, viewing=_viewed(session, body)
            )
        except loop.AgentError as exc:
            raise HTTPException(503, str(exc)) from exc
    response.undo = undo.save(session, cap, actor="agent")
    session.commit()
    return response


@router.post("/agent/confirm/{token}")
def confirm_action(token: str, session: SessionDep) -> ConfirmResult:
    """Makes a change the agent proposed after reading a document or the web, once the user
    confirmed it."""
    proposal = confirm.take(token)
    if proposal is None:
        raise HTTPException(410, confirm.T("expired"))
    name, arguments = proposal
    with undo.capture() as cap:
        result = tools.call(session, name, arguments)
    if "error" in result.payload:
        session.rollback()
        raise HTTPException(422, str(result.payload["error"]))
    token_undo = undo.save(session, cap, actor="user")
    session.commit()
    return ConfirmResult(message=confirm.T("done"), changed=result.changed, undo=token_undo)


class _Stopped(Exception):
    """The client went away: the agent stops at its next step."""


@router.post("/agent/chat/stream")
def chat_stream(body: ChatRequest, session: SessionDep) -> StreamingResponse:
    """Same as /agent/chat, as newline-delimited JSON events: {"type": "tool"} when a tool
    starts, {"type": "tool_done"} when it ends, {"type": "stats"} after each model turn,
    {"type": "token"} as the answer is written, {"type": "step"} to discard the text
    so far, then {"type": "done", "response"} or {"type": "error", "message"}."""
    ids = list(dict.fromkeys(body.attachments))
    for doc_id in ids:
        document_or_404(session, doc_id)
    events: queue.Queue[dict[str, object] | None] = queue.Queue()
    stopped = threading.Event()
    language = i18n.current_language()

    def emit(event: dict[str, object]) -> None:
        if stopped.is_set():
            raise _Stopped
        events.put(event)

    def work() -> None:
        with i18n.using(language), Session(get_engine()) as worker:
            try:
                attached = [
                    ingest.wait_for_analysis(worker, document_or_404(worker, doc_id))
                    for doc_id in ids
                ]
                with undo.capture() as cap:
                    viewing = _viewed(worker, body)
                    response = loop.run(
                        worker, body.message, body.history, attached, emit, viewing=viewing
                    )
                response.undo = undo.save(worker, cap, actor="agent")
                worker.commit()
                events.put({"type": "done", "response": response.model_dump(mode="json")})
            except _Stopped:
                worker.rollback()
            except loop.AgentError as exc:
                worker.rollback()
                events.put({"type": "error", "message": str(exc)})
            except Exception:
                # Last resort of a background thread: the client gets a message, the log the
                # traceback.
                log.exception("Agent failed")
                worker.rollback()
                events.put({"type": "error", "message": T("agent_failed")})
            finally:
                events.put(None)

    threading.Thread(target=work, name="agent", daemon=True).start()

    def stream() -> Iterator[str]:
        try:
            while (event := events.get()) is not None:
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            stopped.set()

    return StreamingResponse(
        stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"}
    )
