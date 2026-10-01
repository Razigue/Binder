"""Local models: Qwen catalogue, choice of the active model and download through Ollama.

No model ships with Binder: the user downloads the one that suits their machine from the
settings. The download runs in the background; the interface follows its progress.
"""

import json
import logging
import threading
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel
from sqlmodel import Session

from binder import i18n
from binder.config import get_settings
from binder.db import get_engine
from binder.schemas import ModelDownload, ModelOut, ModelsOverview
from binder.services import activity, embeddings, llm, settings_store

log = logging.getLogger(__name__)

KEY = "llm"

T = i18n.catalog(
    "llm_models",
    {
        "desc_2b": {
            "en": "Very light, for a modest computer (8 GB of memory). Less reliable extraction.",
            "fr": "Très léger, pour un ordinateur modeste (8 Go de mémoire). Extraction moins "
            "fiable.",
        },
        "desc_4b": {
            "en": "A good compromise for a recent laptop (8 to 16 GB of memory).",
            "fr": "Bon compromis pour un portable récent (8 à 16 Go de mémoire).",
        },
        "desc_9b": {
            "en": "The most reliable for reading your documents day to day (16 GB of memory).",
            "fr": "Le plus fiable pour lire vos documents au quotidien (16 Go de mémoire).",
        },
        "desc_27b": {
            "en": "The most accurate, for a powerful machine (32 GB of memory or a graphics card).",
            "fr": "Le plus précis, pour une machine puissante (32 Go de mémoire ou carte "
            "graphique).",
        },
        "desc_embed": {
            "en": "Smart search: finds documents by meaning, not only by their words "
            "(“proof of address” finds your bills). Small and fast.",
            "fr": "Recherche intelligente : trouve les documents par leur sens, pas seulement "
            "par leurs mots (« justificatif de domicile » trouve vos factures). Petit et rapide.",
        },
        "external": {"en": "Installed outside Binder.", "fr": "Installé hors de Binder."},
        "ollama_down": {"en": "Ollama is not responding", "fr": "Ollama ne répond pas"},
        "ollama_status": {
            "en": "Ollama responded {status}",
            "fr": "Ollama a répondu {status}",
        },
        "connection_lost": {"en": "connection interrupted", "fr": "connexion interrompue"},
        "interrupted": {"en": "download interrupted", "fr": "téléchargement interrompu"},
        "not_installed": {
            "en": "Model not installed: {name}",
            "fr": "Modèle non installé : {name}",
        },
        "not_in_catalog": {
            "en": "Model not in the catalogue: {name}",
            "fr": "Modèle hors catalogue : {name}",
        },
        "busy": {
            "en": "Wait for the current download to finish",
            "fr": "Attendez la fin du téléchargement en cours",
        },
        "chosen": {"en": "Local AI model: {label}", "fr": "Modèle d'IA locale : {label}"},
        "removed": {"en": "Model {label} deleted", "fr": "Modèle {label} supprimé"},
        "downloaded": {"en": "Model {label} downloaded", "fr": "Modèle {label} téléchargé"},
    },
)


class LlmConfig(BaseModel):
    # None: the configured model (BINDER_LLM_MODEL).
    model: str | None = None


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    label: str
    description: str  # message key in T, rendered in the current language
    size: int  # download size, in bytes
    recommended: bool = False
    # "chat" (reads documents, answers) or "embedding" (semantic search, always used if
    # installed, never the active model).
    kind: str = "chat"


GB = 1_000_000_000
CATALOG = [
    CatalogEntry(
        "qwen3.5:2b",
        "Qwen 3.5 · 2B",
        "desc_2b",
        int(2.7 * GB),
    ),
    CatalogEntry(
        "qwen3.5:4b",
        "Qwen 3.5 · 4B",
        "desc_4b",
        int(3.4 * GB),
    ),
    CatalogEntry(
        "qwen3.5:9b",
        "Qwen 3.5 · 9B",
        "desc_9b",
        int(6.6 * GB),
        recommended=True,
    ),
    CatalogEntry(
        "qwen3.5:27b",
        "Qwen 3.5 · 27B",
        "desc_27b",
        17 * GB,
    ),
    CatalogEntry(
        "qwen3-embedding:0.6b",
        "Qwen 3 Embedding · 0.6B",
        "desc_embed",
        int(0.64 * GB),
        recommended=True,
        kind="embedding",
    ),
]
BY_NAME = {e.name: e for e in CATALOG}


class UnknownModel(ValueError):
    pass


class Busy(RuntimeError):
    pass


# --- Model choice -----------------------------------------------------------------------


def restore(session: Session) -> None:
    """Reapplies at startup the model chosen in the settings."""
    llm.select(settings_store.load(session, KEY, LlmConfig).model)


def choose(session: Session, name: str, *, actor: str = "user") -> None:
    if name in BY_NAME and BY_NAME[name].kind != "chat":
        raise UnknownModel(T("not_in_catalog", name=name))
    installed = llm.installed_models()
    if installed is None:
        raise ConnectionError(T("ollama_down"))
    if not llm.is_installed(name, installed):
        raise UnknownModel(T("not_installed", name=name))
    if name != llm.model():
        activity.log(session, "settings", T.msg("chosen", label=_label(name)), actor=actor)
    settings_store.save(session, KEY, LlmConfig(model=name))
    llm.select(name)


def remove(session: Session, name: str) -> None:
    """Deletes a catalogue model from the machine (frees disk space)."""
    if name not in BY_NAME:
        raise UnknownModel(T("not_in_catalog", name=name))
    # Ollama shares layers between models: delete nothing while a download is running.
    if any(d.phase != "error" for d in _downloads.values()):
        raise Busy(T("busy"))
    with llm.client() as c:
        r = c.request("DELETE", "/api/delete", json={"model": name})
        if r.status_code != 404:
            r.raise_for_status()
    if settings_store.load(session, KEY, LlmConfig).model == name:
        settings_store.save(session, KEY, LlmConfig())
        llm.select(None)
    llm.forget_availability()
    embeddings.forget_availability()
    activity.log(session, "settings", T.msg("removed", label=_label(name)), actor="user")


def _label(name: str) -> str:
    entry = BY_NAME.get(name)
    return entry.label if entry else name


# --- Downloads -----------------------------------------------------------------------


@dataclass
class _Download:
    phase: str = "queued"  # queued, starting, downloading, verifying, error
    error: str | None = None
    # Ollama downloads several layers: digest → (received, total).
    layers: dict[str, tuple[int, int]] = field(default_factory=dict)
    cancel: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    def out(self) -> ModelDownload:
        return ModelDownload(
            phase=self.phase,
            completed=sum(done for done, _ in self.layers.values()),
            total=sum(total for _, total in self.layers.values()),
            error=self.error,
        )


_downloads: dict[str, _Download] = {}
_lock = threading.Lock()
# One download at a time: Ollama hangs when several overlap.
_pulling = threading.Lock()
# Latest thread of each model, including finished ones (waited on in tests).
_threads: dict[str, threading.Thread] = {}


def start_download(name: str) -> None:
    if name not in BY_NAME:
        raise UnknownModel(T("not_in_catalog", name=name))
    with _lock:
        current = _downloads.get(name)
        if current and current.phase != "error":
            return
        download = _Download()
        download.thread = threading.Thread(
            target=_run, args=(name, download), name=f"pull-{name}", daemon=True
        )
        _downloads[name] = download
        _threads[name] = download.thread
    download.thread.start()


def cancel_download(name: str) -> None:
    with _lock:
        download = _downloads.pop(name, None)
    if download:
        download.cancel.set()


def wait(name: str, timeout: float = 10.0) -> None:
    """Waits for a download to finish (tests)."""
    thread = _threads.get(name)
    if thread:
        thread.join(timeout)


def _run(name: str, download: _Download) -> None:
    while not _pulling.acquire(timeout=0.2):
        if download.cancel.is_set():
            return
    try:
        if download.cancel.is_set():
            return
        download.phase = "starting"
        finished = _pull(name, download)
    except Exception as e:  # network error, disk full, model not found…
        log.warning("Download of %s failed: %s", name, e)
        download.phase, download.error = "error", _describe(e)
        return
    finally:
        _pulling.release()
    with _lock:
        if _downloads.get(name) is download:
            del _downloads[name]
    if finished:
        try:
            _on_success(name)
        except Exception:
            log.exception("Model %s downloaded, but it could not be activated", name)


def _pull(name: str, download: _Download) -> bool:
    """Downloads the model; False if the user cancelled."""
    # No limit on the total duration, but Ollama streams its progress continuously.
    timeout = httpx.Timeout(10.0, read=300.0)
    with (
        llm.client(timeout=timeout) as c,
        c.stream("POST", "/api/pull", json={"model": name, "stream": True}) as r,
    ):
        r.raise_for_status()
        for line in r.iter_lines():
            if download.cancel.is_set():
                return False
            if not line.strip():
                continue
            event = json.loads(line)
            if "error" in event:
                raise RuntimeError(event["error"])
            status = str(event.get("status", ""))
            if event.get("digest") and event.get("total"):
                download.phase = "downloading"
                total = int(event["total"])
                download.layers[event["digest"]] = (int(event.get("completed") or 0), total)
            elif status.startswith(("verifying", "writing")):
                download.phase = "verifying"
            elif status == "success":
                return True
    raise RuntimeError(T("interrupted"))


def _on_success(name: str) -> None:
    llm.forget_availability()
    embeddings.forget_availability()
    with Session(get_engine()) as session:
        activity.log(session, "settings", T.msg("downloaded", label=_label(name)))
        # First model installed, or active model missing: switch to the new one.
        installed = llm.installed_models() or {}
        is_chat = BY_NAME[name].kind == "chat" if name in BY_NAME else True
        if is_chat and not llm.is_installed(llm.model(), installed):
            choose(session, name, actor="binder")
        session.commit()


def _describe(e: Exception) -> str:
    if isinstance(e, httpx.ConnectError):
        return T("ollama_down")
    if isinstance(e, httpx.HTTPStatusError):
        return T("ollama_status", status=e.response.status_code)
    if isinstance(e, httpx.HTTPError):
        return T("connection_lost")
    return str(e) or type(e).__name__


# --- Overview ------------------------------------------------------------------------


def overview() -> ModelsOverview:
    settings = get_settings()
    installed = llm.installed_models() if settings.llm_enabled else None
    active = llm.model()
    with _lock:
        downloads = {name: d.out() for name, d in _downloads.items()}

    models = [
        ModelOut(
            name=e.name,
            label=e.label,
            description=T(e.description),
            size=installed.get(e.name, e.size) if installed else e.size,
            recommended=e.recommended,
            kind=e.kind,
            in_catalog=True,
            installed=bool(installed and llm.is_installed(e.name, installed)),
            download=downloads.get(e.name),
        )
        for e in CATALOG
    ]
    # Models installed separately (ollama pull): usable, but managed outside Binder.
    for name, size in sorted((installed or {}).items()):
        if name not in BY_NAME and name.removesuffix(":latest") not in BY_NAME:
            models.append(
                ModelOut(
                    name=name,
                    label=name,
                    description=T("external"),
                    size=size,
                    recommended=False,
                    in_catalog=False,
                    installed=True,
                )
            )
    return ModelsOverview(
        enabled=settings.llm_enabled,
        ollama=installed is not None,
        ollama_url=settings.ollama_url,
        active=active,
        active_installed=bool(installed and llm.is_installed(active, installed)),
        models=models,
    )
