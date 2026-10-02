"""Context window: prompt size logged, requests trimmed before sending, fixed part checked."""

import json
import logging
from typing import Any

import httpx
import pytest

from binder.agent import loop, tools
from binder.config import get_settings
from binder.services import llm


def _messages() -> list[dict[str, Any]]:
    big = "x" * 9000
    return [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "old question " + big},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "Mes factures EDF ?", "turn": True},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "a"}}]},
        {"role": "tool", "content": "first result " + big, "images": ["img"] * 4},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "b"}}]},
        {"role": "tool", "content": "latest result", "images": ["img"]},
    ]


def test_estimate_counts_text_tools_and_images() -> None:
    messages = [{"role": "user", "content": "x" * 300, "images": ["a", "b"]}]
    assert llm.estimate_tokens(messages) == 100 + 2 * llm.IMAGE_TOKENS
    assert llm.estimate_tokens(messages, tools.TOOL_SCHEMAS[:1]) > 100 + 2 * llm.IMAGE_TOKENS


def _window(monkeypatch: pytest.MonkeyPatch, tokens: int) -> None:
    monkeypatch.setattr(get_settings(), "llm_context", tokens)


def test_past_images_go_first(monkeypatch: pytest.MonkeyPatch) -> None:
    messages = _messages()
    # Room for all the text, not for five images.
    _window(monkeypatch, llm.ANSWER_TOKENS + 7500)
    loop.fit_context(messages, None)
    assert "images" not in messages[5] and messages[7]["images"] == ["img"]
    assert messages[5]["content"].startswith("first result") and len(messages) == 8


def test_then_old_results_then_earlier_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    messages = _messages()
    _window(monkeypatch, llm.ANSWER_TOKENS + 4500)
    loop.fit_context(messages, None)
    assert messages[5]["content"] == loop.DROPPED_RESULT
    assert messages[1]["content"].startswith("old question")  # history still there
    messages = _messages()
    _window(monkeypatch, llm.ANSWER_TOKENS + 1500)
    loop.fit_context(messages, None)
    # The oldest turn removed; system prompt, request and latest step untouched.
    assert [m["content"] for m in messages[:3]] == ["SYSTEM", "old answer", "Mes factures EDF ?"]
    assert messages[-1] == {"role": "tool", "content": "latest result", "images": ["img"]}


def test_tool_schemas_are_never_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    messages = _messages()
    schemas = tools.TOOL_SCHEMAS[:3]
    _window(monkeypatch, llm.ANSWER_TOKENS + 1500)
    loop.fit_context(messages, schemas)
    assert schemas == tools.TOOL_SCHEMAS[:3] and messages[0]["content"] == "SYSTEM"


def test_fixed_part_must_leave_room(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_enabled", True)
    loop.check_context()
    _window(monkeypatch, 4096)
    with pytest.raises(RuntimeError, match="BINDER_LLM_CONTEXT"):
        loop.check_context()


def test_prompt_size_is_logged_with_an_alert_near_the_limit(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    counted = {"tokens": 1000}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        message = {"role": "assistant", "content": "ok"}
        if body["stream"]:
            lines = [{"message": message}, {"done": True, "prompt_eval_count": counted["tokens"]}]
            return httpx.Response(200, text="\n".join(json.dumps(x) for x in lines))
        return httpx.Response(
            200, json={"message": message, "prompt_eval_count": counted["tokens"]}
        )

    llm.transport = httpx.MockTransport(handler)
    _window(monkeypatch, 10000)
    with caplog.at_level(logging.INFO, logger="binder.services.llm"):
        llm.chat([{"role": "user", "content": "hi"}])
        assert llm.last_prompt_tokens == 1000
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        counted["tokens"] = 8500
        llm.chat([{"role": "user", "content": "hi"}], on_token=lambda _: None)
    assert llm.last_prompt_tokens == 8500
    assert any(r.levelno == logging.WARNING and "85%" in r.getMessage() for r in caplog.records)
