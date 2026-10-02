"""Semantic search with a small local embedding model (through Ollama).

Each document is cut into a few pieces (a header with its title, type and issuer, then its
text); each piece gets a vector stored in the encrypted database. A question is compared with
them: "the paper that proves my address" finds the EDF bill without sharing a word with it.
Without the model, search stays full-text only.
"""

import logging
import threading
import time
from typing import Any

import httpx
import numpy as np
from sqlalchemy import delete
from sqlmodel import Session, col, select

from binder import i18n
from binder.config import get_settings
from binder.models import Document, DocumentStatus, Embedding
from binder.services import llm

log = logging.getLogger(__name__)

# Pieces of text embedded per document: administrative documents say what matters early.
CHUNK_CHARS = 1200
MAX_CHUNKS = 6
# Qwen3 embedding models expect an instruction before a query (not before documents).
QUERY = (
    "Instruct: Given a question about a person's administrative documents, retrieve the "
    "documents that answer it\nQuery: "
)
# Below this cosine similarity, a document is not related to the question (measured on the
# demo documents: related ones score 0.5 to 0.8, unrelated ones such as "Netflix" below 0.37).
MIN_SCORE = 0.42
# Documents kept are also close to the best one: weaker matches are only shared vocabulary.
MAX_GAP = 0.08

_availability: tuple[float, bool] | None = None
AVAILABILITY_TTL = 30.0
# In-memory matrix of the vectors (model, version) → (document ids, matrix).
_cache: dict[str, tuple[int, list[int], Any]] = {}
_version = 0
_lock = threading.Lock()


def model() -> str:
    return get_settings().embed_model


def is_available() -> bool:
    """The embedding model is installed in a responding Ollama (cached result)."""
    global _availability
    if not get_settings().llm_enabled:
        return False
    now = time.monotonic()
    if _availability and now - _availability[0] < AVAILABILITY_TTL:
        return _availability[1]
    installed = llm.installed_models()
    ok = installed is not None and llm.is_installed(model(), installed)
    _availability = (now, ok)
    return ok


def forget_availability() -> None:
    global _availability
    _availability = None


def embed(texts: list[str]) -> Any:
    """Normalized vectors (one row per text). Raises httpx.HTTPError if Ollama fails."""
    settings = get_settings()
    with llm.client(timeout=settings.llm_timeout) as c:
        r = c.post(
            "/api/embed",
            json={"model": model(), "input": texts, "keep_alive": settings.llm_keep_alive},
        )
        r.raise_for_status()
        vectors = np.asarray(r.json()["embeddings"], dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-9)


def pieces(doc: Document) -> list[str]:
    """Header (title, type in both languages, issuer, category) then the text in chunks."""
    labels = {i18n.doc_type_label(doc.doc_type, lang) for lang in i18n.LANGUAGES}
    category = {i18n.category_label(doc.category.value, lang) for lang in i18n.LANGUAGES}
    header = " — ".join(
        x for x in (doc.title, *sorted(labels), doc.issuer or "", *sorted(category)) if x
    )
    body = llm.compact(doc.text, CHUNK_CHARS * MAX_CHUNKS)
    chunks = [body[i : i + CHUNK_CHARS] for i in range(0, len(body), CHUNK_CHARS)]
    # The header also leads the first chunk: its words give the text its context.
    return [header] + [f"{header}\n{c}" if i == 0 else c for i, c in enumerate(chunks)]


def _changed() -> None:
    global _version
    with _lock:
        _version += 1


def index(session: Session, doc: Document) -> bool:
    """(Re)computes the vectors of a document. False if the model is unavailable."""
    if doc.id is None or not is_available():
        return False
    try:
        vectors = embed(pieces(doc))
    except (httpx.HTTPError, KeyError, ValueError):
        log.exception("Could not embed document %s", doc.id)
        return False
    forget(session, doc.id)
    for i, vector in enumerate(vectors):
        session.add(Embedding(document_id=doc.id, chunk=i, model=model(), vector=vector.tobytes()))
    _changed()
    return True


def forget(session: Session, document_id: int) -> None:
    session.execute(delete(Embedding).where(col(Embedding.document_id) == document_id))
    _changed()


def forget_all(session: Session) -> None:
    session.execute(delete(Embedding))
    _changed()


def backfill(session: Session, limit: int = 20) -> int:
    """Embeds documents that have no vector for the current model yet (existing library,
    model installed later). Returns how many were done."""
    if not is_available():
        return 0
    done_ids = select(Embedding.document_id).where(Embedding.model == model())
    missing = session.exec(
        select(Document)
        .where(col(Document.deleted_at).is_(None))
        .where(col(Document.status).not_in((DocumentStatus.PROCESSING, DocumentStatus.WAITING)))
        .where(col(Document.id).not_in(done_ids))
        .limit(limit)
    ).all()
    count = 0
    for doc in missing:
        if not index(session, doc):
            break
        count += 1
    if count:
        session.commit()
    return count


def _matrix(session: Session) -> tuple[list[int], Any]:
    name = model()
    with _lock:
        cached = _cache.get(name)
        if cached and cached[0] == _version:
            return cached[1], cached[2]
        version = _version
    rows = session.exec(
        select(Embedding.document_id, Embedding.vector).where(Embedding.model == name)
    ).all()
    ids = [r[0] for r in rows]
    matrix = (
        np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
        if rows
        else np.zeros((0, 1), dtype=np.float32)
    )
    with _lock:
        _cache[name] = (version, ids, matrix)
    return ids, matrix


def search(session: Session, query: str, limit: int = 30) -> list[tuple[int, float]]:
    """Documents related to the question, best first: (id, similarity). [] without model."""
    if not query.strip() or not is_available():
        return []
    backfill(session)
    ids, matrix = _matrix(session)
    if not ids:
        return []
    try:
        question = embed([QUERY + query])[0]
    except (httpx.HTTPError, KeyError, ValueError):
        log.exception("Could not embed the question")
        return []
    scores = matrix @ question
    best: dict[int, float] = {}
    for doc_id, score in zip(ids, scores.tolist(), strict=True):
        if score >= MIN_SCORE and score > best.get(doc_id, -1.0):
            best[doc_id] = score
    ranked = sorted(best.items(), key=lambda x: -x[1])
    return [(i, s) for i, s in ranked if s >= ranked[0][1] - MAX_GAP][:limit] if ranked else []
