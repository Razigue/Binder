"""Client Ollama minimal : disponibilité, sortie JSON structurée et appels d'outils."""

import json
import logging
import time
from typing import Any

import httpx
from pydantic import ValidationError

from binder.config import get_settings
from binder.models import Category
from binder.schemas import Extraction

log = logging.getLogger(__name__)

_availability: tuple[float, bool] | None = None
AVAILABILITY_TTL = 30.0
MAX_CHARS = 8000

EXTRACTION_PROMPT = """Tu analyses un document administratif français.
Réponds uniquement en JSON avec les clés :
- category : une valeur parmi {categories}
- title : titre court (ex. « Taxe foncière 2026 », « Facture EDF », « Attestation CAF »)
- issuer : organisme émetteur ou null
- amount : montant principal à payer ou perçu, en euros (nombre) ou null
- issue_date : date d'émission AAAA-MM-JJ ou null
- due_date : date limite de paiement, d'échéance ou d'expiration AAAA-MM-JJ ou null
- reference : référence du document, du contrat ou du client, ou null
- confidence : ta confiance entre 0 et 1
N'invente rien : si une information est absente, mets null.

Document :
\"\"\"
{text}
\"\"\"
"""


def is_available() -> bool:
    """Vérifie qu'Ollama répond et que le modèle configuré est installé (résultat mis en cache)."""
    global _availability
    settings = get_settings()
    if not settings.llm_enabled:
        return False
    now = time.monotonic()
    if _availability and now - _availability[0] < AVAILABILITY_TTL:
        return _availability[1]
    ok = False
    try:
        r = httpx.get(f"{settings.ollama_url}/api/tags", timeout=2)
        names = {m["name"] for m in r.json().get("models", [])}
        wanted = settings.llm_model
        ok = wanted in names or f"{wanted}:latest" in names
    except (httpx.HTTPError, ValueError, KeyError):
        ok = False
    _availability = (now, ok)
    return ok


def chat(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    fmt: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }
    if tools:
        payload["tools"] = tools
    if fmt:
        payload["format"] = fmt
    r = httpx.post(f"{settings.ollama_url}/api/chat", json=payload, timeout=settings.llm_timeout)
    r.raise_for_status()
    message: dict[str, Any] = r.json()["message"]
    return message


def extract(text: str) -> Extraction | None:
    """Extraction par le modèle local. None en cas d'échec : le pipeline garde les règles."""
    schema = Extraction.model_json_schema()
    for key in ("missing_fields", "extractor"):
        schema["properties"].pop(key, None)
    prompt = EXTRACTION_PROMPT.format(
        categories=", ".join(c.value for c in Category), text=text[:MAX_CHARS]
    )
    try:
        message = chat([{"role": "user", "content": prompt}], fmt=schema)
        data = json.loads(message.get("content") or "{}")
        data.pop("missing_fields", None)
        # Les petits modèles recopient parfois l'étiquette : « N° client : 6012… » → « 6012… ».
        if isinstance(data.get("reference"), str) and ":" in data["reference"]:
            data["reference"] = data["reference"].split(":", 1)[1].strip() or None
        return Extraction.model_validate({**data, "extractor": "llm"})
    except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError):
        log.exception("Extraction LLM impossible, repli sur les règles")
        return None
