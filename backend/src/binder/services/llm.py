"""Minimal Ollama client: availability, capabilities, structured JSON output, tool calls,
streaming and images (vision)."""

import base64
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import ValidationError

from binder import i18n
from binder.config import get_settings
from binder.models import Category
from binder.schemas import Extraction

log = logging.getLogger(__name__)

_availability: tuple[float, bool] | None = None
# Capabilities reported by Ollama per model ("vision", "tools", "thinking"…).
_capabilities: dict[str, set[str]] = {}
AVAILABILITY_TTL = 30.0
MAX_CHARS = 8000

# Model chosen in the settings; otherwise the configured one (BINDER_LLM_MODEL).
_selected: str | None = None
# Replaced by an httpx.MockTransport in tests.
transport: httpx.BaseTransport | None = None

# English names of the countries most users will have, for prompts (others: ISO code).
COUNTRY_NAMES = {
    "FR": "France", "BE": "Belgium", "LU": "Luxembourg", "MC": "Monaco", "CH": "Switzerland",
    "CA": "Canada", "US": "the United States", "GB": "the United Kingdom", "IE": "Ireland",
    "DE": "Germany", "ES": "Spain", "IT": "Italy", "PT": "Portugal", "NL": "the Netherlands",
    "AT": "Austria", "AU": "Australia", "NZ": "New Zealand", "MA": "Morocco", "DZ": "Algeria",
    "TN": "Tunisia", "SN": "Senegal", "CI": "Côte d'Ivoire",
}  # fmt: skip


def user_context() -> dict[str, str]:
    """Language, country and currency of the user, as written in English prompts."""
    loc = i18n.current()
    country = (loc.country or "").upper()
    return {
        "language": i18n.language_name(loc.language),
        "country": COUNTRY_NAMES.get(country, country) or "unknown",
        "currency": loc.currency,
    }


# Prompts are kept short: every token is paid on each document with small local models.
# Measured with qwen3.5:9b on the samples: as accurate as the former, longer French prompt
# with ~22% fewer prompt tokens. The examples of received amounts matter (payslip, refund),
# and "null" works better as a closing rule than up front (fewer missed amounts).
EXTRACTION_PROMPT = """Extract data from this administrative document (often French, any \
language). User country: {country}, currency {currency}.
category: one of {categories}
title: short, in {language} (e.g. {title_example})
issuer: issuing organisation
amount: main amount to pay or received, e.g. total due, net pay, rent, refund (number)
issue_date, due_date (payment or debit date), expiry_date (end of validity): YYYY-MM-DD
reference: document, contract or customer reference, value only
person: full name of the person it concerns (holder, employee, tenant, insured), not a company
confidence: 0 to 1
Use null for missing information; do not invent.
Document:
\"\"\"
{text}
\"\"\"
"""
SCAN_NOTE = """The images are the document's pages; the text below was read from them by OCR \
and may contain errors: trust the images.
"""
TRANSCRIBE_PROMPT = """Transcribe all the text of this administrative document page, line by \
line, in reading order, keeping table rows on one line. Output only the text."""
TITLE_EXAMPLES: dict[i18n.Language, str] = {
    "en": '"Property tax 2026", "EDF invoice"',
    "fr": '"Taxe foncière 2026", "Facture EDF"',
}


def _nullable(kind: str) -> dict[str, Any]:
    return {"type": [kind, "null"]}


# Output constraint given to Ollama: types only, every key required (null when absent).
EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"enum": [c.value for c in Category]},
        "title": {"type": "string"},
        "issuer": _nullable("string"),
        "amount": _nullable("number"),
        "issue_date": _nullable("string"),
        "due_date": _nullable("string"),
        "expiry_date": _nullable("string"),
        "reference": _nullable("string"),
        "person": _nullable("string"),
        "confidence": {"type": "number"},
    },
    "required": [
        "category", "title", "issuer", "amount", "issue_date", "due_date", "expiry_date",
        "reference", "person", "confidence",
    ],
}  # fmt: skip

_BLANKS = re.compile(r"[^\S\n]+")  # whitespace except newlines
_BLANK_LINES = re.compile(r"\s*\n\s*")


def compact(text: str, limit: int = MAX_CHARS) -> str:
    """Document text for a prompt: runs of spaces and blank lines cost tokens, not meaning."""
    return _BLANK_LINES.sub("\n", _BLANKS.sub(" ", text)).strip()[:limit]


def dumps(value: Any) -> str:
    """Compact JSON for the model (no spaces, no null fields)."""
    return json.dumps(_drop_nulls(value), ensure_ascii=False, separators=(",", ":"))


def _drop_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _drop_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_nulls(v) for v in value]
    return value


def client(timeout: float | httpx.Timeout = 10.0) -> httpx.Client:
    return httpx.Client(base_url=get_settings().ollama_url, timeout=timeout, transport=transport)


def model() -> str:
    """Model used for extraction, explanations and the agent."""
    return _selected or get_settings().llm_model


def select(name: str | None) -> None:
    """Changes the active model (None: the configured one)."""
    global _selected
    _selected = name
    forget_availability()


def forget_availability() -> None:
    """To call when the installed models change."""
    global _availability
    _availability = None
    _capabilities.clear()


def capabilities() -> set[str]:
    """What the active model can do, as reported by Ollama (empty if it does not answer)."""
    name = model()
    if name not in _capabilities:
        try:
            with client(timeout=5) as c:
                r = c.post("/api/show", json={"model": name})
                r.raise_for_status()
                _capabilities[name] = set(r.json().get("capabilities") or [])
        except (httpx.HTTPError, ValueError, TypeError):
            return set()
    return _capabilities[name]


def has_vision() -> bool:
    """The active model reads images (Qwen 3.5 does) and vision is enabled."""
    return get_settings().llm_vision and is_available() and "vision" in capabilities()


def image(data: bytes) -> str:
    """An image as Ollama expects it in a message's `images`."""
    return base64.b64encode(data).decode("ascii")


def installed_models() -> dict[str, int] | None:
    """Models installed in Ollama (name → size in bytes), None if Ollama does not respond."""
    try:
        with client(timeout=2) as c:
            r = c.get("/api/tags")
            r.raise_for_status()
            return {m["name"]: int(m.get("size") or 0) for m in r.json().get("models", [])}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


def is_installed(name: str, installed: dict[str, int]) -> bool:
    return name in installed or f"{name}:latest" in installed


def is_available() -> bool:
    """Checks that Ollama responds and the active model is installed (cached result)."""
    global _availability
    if not get_settings().llm_enabled:
        return False
    now = time.monotonic()
    if _availability and now - _availability[0] < AVAILABILITY_TTL:
        return _availability[1]
    installed = installed_models()
    ok = installed is not None and is_installed(model(), installed)
    _availability = (now, ok)
    return ok


def chat(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    fmt: dict[str, Any] | str | None = None,
    think: bool = False,
    on_token: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """One model turn. With `on_token`, the answer is streamed: each piece of text is passed
    to it as it comes, and the complete message is returned at the end."""
    settings = get_settings()
    payload: dict[str, Any] = {
        "model": model(),
        "messages": messages,
        "stream": on_token is not None,
        "think": think,
        "keep_alive": settings.llm_keep_alive,
        "options": {"temperature": 0, "num_ctx": settings.llm_context},
    }
    if tools:
        payload["tools"] = tools
    if fmt:
        payload["format"] = fmt
    with client(timeout=settings.llm_timeout) as c:
        if on_token is None:
            r = c.post("/api/chat", json=payload)
            r.raise_for_status()
            message: dict[str, Any] = r.json()["message"]
            return message
        return _stream(c, payload, on_token)


def _stream(
    c: httpx.Client, payload: dict[str, Any], on_token: Callable[[str], None]
) -> dict[str, Any]:
    content: list[str] = []
    thinking: list[str] = []
    calls: list[dict[str, Any]] = []
    with c.stream("POST", "/api/chat", json=payload) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.strip():
                continue
            chunk = json.loads(line)
            if chunk.get("error"):
                raise ValueError(chunk["error"])
            part = chunk.get("message") or {}
            if part.get("thinking"):
                thinking.append(part["thinking"])
            if part.get("content"):
                content.append(part["content"])
                on_token(part["content"])
            calls += part.get("tool_calls") or []
    message: dict[str, Any] = {"role": "assistant", "content": "".join(content)}
    if thinking:
        message["thinking"] = "".join(thinking)
    if calls:
        message["tool_calls"] = calls
    return message


def extract(text: str, images: list[bytes] | None = None) -> Extraction | None:
    """Extraction by the local model. None on failure: the pipeline keeps the rules.

    `images`: pages of a scan or photo, shown to the model along with the OCR text, which may
    have misread the layout or a figure."""
    context = user_context()
    prompt = EXTRACTION_PROMPT.format(
        categories=", ".join(c.value for c in Category),
        title_example=TITLE_EXAMPLES[i18n.current_language()],
        text=compact(text),
        **context,
    )
    request: dict[str, Any] = {"role": "user", "content": prompt}
    if images:
        request["content"] = SCAN_NOTE + prompt
        request["images"] = [image(i) for i in images]
    try:
        message = chat([request], fmt=EXTRACTION_SCHEMA)
        data = json.loads(message.get("content") or "{}")
        data.pop("missing_fields", None)
        data.pop("doc_type", None)
        # Small models sometimes copy the label: "N° client : 6012…" → "6012…".
        if isinstance(data.get("reference"), str) and ":" in data["reference"]:
            data["reference"] = data["reference"].split(":", 1)[1].strip() or None
        return Extraction.model_validate({**data, "extractor": "llm"})
    except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError):
        log.exception("LLM extraction failed, falling back to rules")
        return None


def transcribe(images: list[bytes]) -> str:
    """Text of scanned pages read by the model, when OCR found nothing. "" on failure."""
    pages = []
    for page in images:
        try:
            message = chat(
                [{"role": "user", "content": TRANSCRIBE_PROMPT, "images": [image(page)]}]
            )
        except (httpx.HTTPError, KeyError, ValueError):
            log.exception("Transcription by the model failed")
            return ""
        pages.append(str(message.get("content") or "").strip())
    return "\n".join(pages).strip()
