"""What the local model is given depends on it: context, document length, tools, sampling,
reasoning; the model is loaded ahead; documents of a known sender come with an example."""

import json
from collections.abc import Iterator
from datetime import date
from typing import Any

import httpx
import pytest
from sqlmodel import Session

from binder.agent import loop, tools
from binder.config import get_settings
from binder.db import get_engine
from binder.models import Category, Document, DocumentStatus
from binder.samples import build_samples
from binder.services import ingest, learning, llm
from tests.conftest import TODAY

LARGE = "qwen3.6:27b"


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


def _record(sent: list[dict[str, Any]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "{}"}})

    llm.transport = httpx.MockTransport(handler)


def test_a_large_model_gets_more() -> None:
    assert llm.profile() == llm.SMALL and llm.context_window() == llm.SMALL.context
    long_text = "mot " * 10_000
    llm.select(LARGE)
    assert llm.profile() == llm.LARGE and llm.context_window() == llm.LARGE.context
    assert len(llm.compact(long_text)) == llm.LARGE.doc_chars
    llm.select("someone/else:7b")
    assert llm.profile() == llm.SMALL
    assert len(llm.compact(long_text)) == llm.SMALL.doc_chars


def test_the_context_set_by_hand_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_context", 8192)
    llm.select(LARGE)
    sent: list[dict[str, Any]] = []
    _record(sent)
    llm.chat([{"role": "user", "content": "hi"}])
    assert sent[0]["options"]["num_ctx"] == 8192


def test_answers_are_greedy_reasoning_is_sampled_as_qwen_advises() -> None:
    sent: list[dict[str, Any]] = []
    _record(sent)
    llm.chat([{"role": "user", "content": "read"}], fmt={"type": "object"})
    llm.chat([{"role": "user", "content": "think"}], think=True)
    exact, thinking = (s["options"] for s in sent)
    assert exact["temperature"] == 0 and "top_k" not in exact
    assert thinking["temperature"] == 1.0 and thinking["presence_penalty"] == 1.5
    assert sent[1]["think"] is True
    # Same seed and same window everywhere: reproducible, and the model is never reloaded.
    assert {o["seed"] for o in (exact, thinking)} == {llm.SEED}
    assert {o["num_ctx"] for o in (exact, thinking)} == {llm.context_window()}


def test_a_large_model_sees_every_tool_always_in_the_same_order() -> None:
    message = "On déménage le 15 novembre"
    assert len(loop.select_tools(message, vision=True)) <= tools.MAX_TOOLS
    llm.select(LARGE)
    names = loop.select_tools(message, vision=True)
    assert set(names) == set(tools.NAMES) and len(names) == len(set(names))
    # The same for any request: the schemas stay in Ollama's prompt cache.
    assert names == loop.select_tools("Bonjour", vision=True)


def test_reasoning_needs_a_large_model_on_a_graphics_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm.select(LARGE)
    assert not llm.think_hard()
    llm.set_accelerated(True)
    assert llm.think_hard()
    llm.select("qwen3.5:9b")
    assert not llm.think_hard()
    monkeypatch.setattr(get_settings(), "llm_think", True)
    assert llm.think_hard()


def test_warming_reads_the_agent_prompt_start_with_the_requests_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []
    _record(sent)
    llm.select(LARGE)
    monkeypatch.setattr(llm, "has_vision", lambda: False)
    llm._warming.acquire()
    llm._load(LARGE)
    assert not llm.warming()
    (payload,) = sent
    system, schemas = loop.warm_prefix()
    assert payload["messages"] == system and payload["tools"] == schemas
    assert payload["options"]["num_ctx"] == llm.LARGE.context
    assert payload["options"]["num_predict"] == 1 and payload["keep_alive"] == "30m"
    # Ollama failing: nothing raised, the first question loads the model instead.
    llm.transport = httpx.MockTransport(lambda r: httpx.Response(500))
    llm._warming.acquire()
    llm._load(LARGE)
    assert not llm.warming()


def test_binder_s_own_ollama_keeps_the_model_for_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert llm.keep_alive() == "30m"
    llm.set_owned(True)
    try:
        assert llm.keep_alive() == -1
        monkeypatch.setattr(get_settings(), "llm_keep_alive", "10m")
        assert llm.keep_alive() == "10m"
    finally:
        llm.set_owned(False)


def test_loaded_follows_ollama_s_running_models() -> None:
    running: list[dict[str, Any]] = []
    llm.transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"models": running}))
    llm.select(LARGE)
    assert llm.loaded() is False
    running.append({"name": LARGE})
    assert llm.loaded() is True
    llm.transport = httpx.MockTransport(lambda r: httpx.Response(500))
    assert llm.loaded() is None


def _filed(session: Session, n: int, issuer: str, title: str, **fields: Any) -> Document:
    doc = Document(
        filename=f"{n}.pdf",
        mime_type="application/pdf",
        size=1,
        sha256=str(n),
        stored_name=str(n),
        title=title,
        issuer=issuer,
        category=Category.HOUSING,
        doc_type="invoice",
        status=DocumentStatus.CLASSIFIED,
        **fields,
    )
    session.add(doc)
    session.commit()
    return doc


def _title(example: dict[str, Any] | None) -> str | None:
    return example["title"] if example else None


def test_the_sender_s_last_document_is_the_example(session: Session) -> None:
    _filed(session, 1, "EDF", "Facture EDF juin", issue_date=date(2026, 6, 1))
    last = _filed(
        session, 2, "EDF", "Facture EDF août", issue_date=date(2026, 8, 1), amount_ttc=94.37
    )
    _filed(session, 3, "EDF Entreprises", "Contrat pro", issue_date=date(2026, 7, 1))
    text = "EDF\nFacture d'électricité\nMontant 81,20 €"
    assert learning.example(session, text) == {
        "category": Category.HOUSING.value,
        "doc_type": "invoice",
        "issuer": "EDF",
        "title": "Facture EDF août",
        "fields": ["amount_ttc", "issue_date"],
    }
    # Reading that very document again: the one before it is the example.
    assert _title(learning.example(session, text, exclude=last.id)) == "Facture EDF juin"
    # The longest issuer named wins; a name inside a word does not count.
    assert _title(learning.example(session, "EDF Entreprises : devis")) == "Contrat pro"
    assert learning.example(session, "CREDFIN\nRelevé") is None


def test_the_example_reaches_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = next(s for s in build_samples(TODAY) if s.filename == "facture-edf.pdf")
    sent: list[dict[str, Any]] = []
    _record(sent)
    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "has_vision", lambda: False)
    seen: list[str] = []

    def example(text: str) -> dict[str, Any]:
        seen.append(text)
        return {"issuer": "EDF", "title": "Facture EDF août"}

    ingest.extract(sample.pdf(), "application/pdf", example=example)
    assert seen and "EDF" in seen[0]
    prompt = sent[0]["messages"][0]["content"]
    assert prompt.startswith("A previous document from the same sender")
    assert '"title":"Facture EDF août"' in prompt


@pytest.mark.parametrize("content", ["[1, 2]", '"facture"', "not json"])
def test_an_extraction_that_is_not_an_object_falls_back_on_the_rules(content: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})

    llm.transport = httpx.MockTransport(handler)
    assert llm.extract("Facture EDF") is None
