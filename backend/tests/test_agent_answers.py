"""Answers: calculations done in code, a fixed seed, the user's language."""

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from sqlmodel import Session

from binder import i18n
from binder.agent import loop, tools
from binder.db import get_engine
from binder.services import llm
from tests.test_agent import FakeModel, answer, call


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeModel]:
    fake = FakeModel()
    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "has_vision", lambda: False)
    monkeypatch.setattr(llm, "chat", fake)
    yield fake


def test_calculations_are_done_in_code(session: Session) -> None:
    def result(expression: str) -> Any:
        return tools.call(session, "calculate", {"expression": expression}).payload.get("result")

    assert result("94.37 + 81.05") == 175.42
    assert result("94,37 + 1") == 95.37
    assert result("(1240 - 1180) / 1180 * 100") == 5.08
    assert result("'2026-11-06' - '2026-09-22'") == 45
    assert result("'2026-10-01' + 30") == "2026-10-31"
    # A date cannot be multiplied, divided or negated: refused rather than misread or crashing.
    invalid = ("'2026-10-01' * 30", "'2026-10-01' / 2", "-'2026-10-01'", "True + 1")
    for unsafe in ("__import__('os')", "1/0", "'hello' - 1", "2 ** 100000", *invalid):
        error = tools.call(session, "calculate", {"expression": unsafe}).payload["error"]
        assert "Cannot calculate" in error


def test_prompt_no_longer_asks_to_compute_in_the_head() -> None:
    prompt = loop.system_prompt(None)
    assert "yourself" not in prompt and "calculate" in prompt
    assert "calculate" in loop.select_tools("Combien au total pour EDF ?", vision=False)


def test_every_call_has_a_fixed_seed() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})

    llm.transport = httpx.MockTransport(handler)
    llm.chat([{"role": "user", "content": "hi"}])
    llm.chat([{"role": "user", "content": "hi"}])
    assert sent[0]["options"]["seed"] == sent[1]["options"]["seed"] == llm.SEED
    assert sent[0]["options"]["temperature"] == 0


def test_language_is_guessed_from_frequent_words() -> None:
    assert i18n.guess_language("Votre facture EDF est à payer avant le 14 octobre.") == "fr"
    assert i18n.guess_language("Your EDF bill is due before 14 October, for €94.37.") == "en"
    assert i18n.guess_language("EDF : 94,37 €") is None


def test_answer_in_the_wrong_language_is_asked_again_once(
    session: Session, model: FakeModel
) -> None:
    model.replies = [
        call("list", kind="deadlines"),
        answer("Vous avez une facture EDF à payer avant le 14 octobre."),
        answer("You have an EDF bill to pay before 14 October."),
    ]
    response = loop.run(session, "What is due?", [])
    assert response.answer == "You have an EDF bill to pay before 14 October."
    assert model.requests[2][-1]["content"] == loop.WRONG_LANGUAGE.format(language="English")
    # Only once: a second answer in French is kept rather than asked again.
    model.replies = [
        call("list", kind="deadlines"),
        answer("Vous avez une facture EDF à payer avant le 14 octobre."),
        answer("Vous avez toujours une facture EDF à payer avant le 14 octobre."),
    ]
    response = loop.run(session, "What is due?", [])
    assert response.answer.startswith("Vous avez toujours")
