"""Robustness of the calls to the local model: unreadable tool calls, Ollama errors, step
budget and Ollama version (the model is simulated)."""

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from binder.agent import loop
from binder.db import get_engine
from binder.services import llm, setup

PARSE_ERROR = 'error parsing tool call: raw=\'<tool_call>{"name": "search_documents"\''


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


class Script:
    """Replies of the model, in order: a dict is a message, an exception is raised."""

    def __init__(self, *steps: dict[str, Any] | Exception) -> None:
        self.steps = list(steps)
        self.requests: list[list[dict[str, Any]]] = []

    def __call__(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.requests.append([dict(m) for m in messages])
        step = self.steps.pop(0) if self.steps else {"content": "Done."}
        if isinstance(step, Exception):
            raise step
        return {"role": "assistant", **step}


def _use(monkeypatch: pytest.MonkeyPatch, script: Script) -> Script:
    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "has_vision", lambda: False)
    monkeypatch.setattr(llm, "chat", script)
    return script


def _search() -> dict[str, Any]:
    return {
        "content": "",
        "tool_calls": [{"function": {"name": "search_documents", "arguments": {"query": "EDF"}}}],
    }


def test_unparsable_tool_call_is_sent_back_and_retried(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    script = _use(
        monkeypatch,
        Script(llm.ModelError(PARSE_ERROR), _search(), {"content": "Nothing from EDF yet."}),
    )
    response = loop.run(session, "Mes factures EDF ?", [])
    assert response.answer == "Nothing from EDF yet." and response.engine == "llm"
    retry = script.requests[1][-1]
    assert retry["role"] == "user" and "could not be read" in retry["content"]


def test_repeated_unparsable_calls_end_with_an_explicit_error(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    errors = [llm.ModelError(PARSE_ERROR) for _ in range(loop.MAX_CALL_RETRIES + 1)]
    script = _use(monkeypatch, Script(*errors))
    with pytest.raises(loop.AgentError) as raised:
        loop.run(session, "Mes factures EDF ?", [])
    assert str(raised.value) == loop.T("model_unreadable")
    assert len(script.requests) == loop.MAX_CALL_RETRIES + 1


def test_ollama_down_is_an_error_not_the_router(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    _use(monkeypatch, Script(httpx.ConnectError("refused")))
    with pytest.raises(loop.AgentError) as raised:
        # The router would answer this one on its own: it must not stand in for the model.
        loop.run(session, "Quelles échéances ce mois-ci ?", [])
    assert str(raised.value) == loop.T("model_failed")


def test_other_model_errors_are_not_retried(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    script = _use(monkeypatch, Script(llm.ModelError("model requires more system memory")))
    with pytest.raises(loop.AgentError):
        loop.run(session, "Bonjour", [])
    assert len(script.requests) == 1


def test_every_model_turn_counts_in_the_step_budget(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    script = _use(monkeypatch, Script(*[_search() for _ in range(20)]))
    loop.run(session, "Mes factures EDF ?", [])
    assert len(script.requests) == loop.MAX_STEPS


def test_stream_route_reports_the_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    errors = [llm.ModelError(PARSE_ERROR) for _ in range(loop.MAX_CALL_RETRIES + 1)]
    _use(monkeypatch, Script(*errors))
    r = client.post("/api/agent/chat/stream", json={"message": "Mes factures ?", "history": []})
    events = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    assert events[-1] == {"type": "error", "message": loop.T("model_unreadable")}
    _use(monkeypatch, Script(httpx.ConnectError("refused")))
    r = client.post("/api/agent/chat", json={"message": "Mes factures ?", "history": []})
    assert r.status_code == 503 and r.json()["detail"] == loop.T("model_failed")


def _ollama(handler: Any) -> None:
    llm.transport = httpx.MockTransport(handler)


@pytest.fixture
def mock_transport() -> Iterator[None]:
    yield
    llm.transport = None


def test_ollama_errors_become_model_errors(mock_transport: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["stream"]:
            lines = [{"message": {"content": "Je "}}, {"error": PARSE_ERROR}]
            return httpx.Response(200, text="\n".join(json.dumps(x) for x in lines))
        return httpx.Response(500, json={"error": PARSE_ERROR})

    _ollama(handler)
    with pytest.raises(llm.ModelError) as raised:
        llm.chat([{"role": "user", "content": "hi"}])
    assert raised.value.unparsable
    with pytest.raises(llm.ModelError):
        llm.chat([{"role": "user", "content": "hi"}], on_token=lambda _: None)
    assert not llm.ModelError("model requires more system memory").unparsable


def test_outdated_ollama_is_reported_without_blocking(mock_transport: None) -> None:
    assert llm.outdated_ollama("0.17.4") and llm.outdated_ollama("0.9.0")
    assert not llm.outdated_ollama(llm.MIN_OLLAMA_VERSION)
    assert not llm.outdated_ollama("0.35.0") and not llm.outdated_ollama(None)
    assert not llm.outdated_ollama("0.18.0-rc1")
    version = "0.12.3"
    _ollama(lambda request: httpx.Response(200, json={"version": version}))
    setup.check_version()
    warning = setup._state.warning
    assert warning and "0.12.3" in warning and llm.MIN_OLLAMA_VERSION in warning
    version = "0.35.0"
    setup.check_version()
    assert setup._state.warning is None
