"""Local models: Qwen catalogue, choice of the active model and download through Ollama.

No model ships with Binder: at launch, setup.py picks the best one the machine runs and downloads
it. The download runs in the background; the interface follows its progress. Each launch measures
the machine again: when Binder chose the model and a better one now suits the machine, the
upgrade is offered (never downloaded silently, never a downgrade). docs/models.md: adding one.
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
from binder.schemas import ModelDownload, ModelOut, ModelsOverview, ModelUpgrade
from binder.services import activity, embeddings, llm, settings_store

log = logging.getLogger(__name__)

KEY = "llm"

T = i18n.catalog(
    "llm_models",
    {
        "label_2b": {"en": "Qwen 3.5 · 2B", "fr": "Qwen 3.5 · 2B"},
        "label_4b": {"en": "Qwen 3.5 · 4B", "fr": "Qwen 3.5 · 4B"},
        "label_9b": {"en": "Qwen 3.5 · 9B", "fr": "Qwen 3.5 · 9B"},
        "label_35b_a3b": {"en": "Qwen 3.6 · 35B-A3B", "fr": "Qwen 3.6 · 35B-A3B"},
        "label_27b": {"en": "Qwen 3.6 · 27B", "fr": "Qwen 3.6 · 27B"},
        "label_embed": {"en": "Qwen 3 Embedding · 0.6B", "fr": "Qwen 3 Embedding · 0.6B"},
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
            "en": "Reliable for reading your documents day to day (16 GB of memory, or a "
            "graphics card with 8 GB).",
            "fr": "Fiable pour lire vos documents au quotidien (16 Go de mémoire, ou carte "
            "graphique de 8 Go).",
        },
        "desc_35b_a3b": {
            "en": "More accurate and still fast: only 3B of its 35B parameters work on each "
            "word. 32 GB of memory, with or without a graphics card.",
            "fr": "Plus précis et toujours rapide : seuls 3 milliards de ses 35 milliards de "
            "paramètres travaillent à chaque mot. 32 Go de mémoire, avec ou sans carte "
            "graphique.",
        },
        "desc_27b": {
            "en": "The most accurate, for a powerful machine (a graphics card with 20 GB, or a "
            "Mac with 48 GB).",
            "fr": "Le plus précis, pour une machine puissante (carte graphique de 20 Go, ou Mac "
            "de 48 Go).",
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
        "upgraded": {
            "en": "Local AI upgraded: {old} → {new} (the former model stays installed)",
            "fr": "IA locale améliorée : {old} → {new} (l'ancien modèle reste installé)",
        },
        "upgrade_declined": {
            "en": "Upgrade to {label} declined",
            "fr": "Passage à {label} refusé",
        },
        "no_upgrade": {"en": "No upgrade to offer", "fr": "Aucune amélioration à proposer"},
    },
)


class LlmConfig(BaseModel):
    # None: the configured model (BINDER_LLM_MODEL).
    model: str | None = None
    # Picked by Binder for this machine, not by the user: only such a choice is upgraded. True
    # for settings saved before the field existed, when Binder made the choice.
    auto: bool = True
    # Upgrade the user turned down: offered again only once the recommendation changes.
    declined: str | None = None


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    label: str  # message key in T
    description: str  # message key in T, rendered in the current language
    size: int  # download size, in bytes
    # Quality, higher is better: decides upgrades. Chat models only (0 for the embedding).
    rank: int = 0
    # "chat" (reads documents, answers) or "embedding" (semantic search, always used if
    # installed, never the active model).
    kind: str = "chat"
    # Oldest Ollama that runs it ("requires" in the tag's config on registry.ollama.ai).
    min_ollama: str = llm.MIN_OLLAMA_VERSION


GB = 1_000_000_000
# Sizes: the tag's layers on registry.ollama.ai (weights and vision projector). Every chat model
# reads images and calls tools.
CATALOG = [
    CatalogEntry("qwen3.5:2b", "label_2b", "desc_2b", int(2.7 * GB), rank=1),
    CatalogEntry("qwen3.5:4b", "label_4b", "desc_4b", int(3.4 * GB), rank=2),
    CatalogEntry("qwen3.5:9b", "label_9b", "desc_9b", int(6.6 * GB), rank=3),
    # Mixture of experts: ~3B parameters active per token, so it stays fast with most of its
    # weights in RAM (Ollama keeps there what the graphics card cannot hold).
    CatalogEntry(
        "qwen3.6:35b-a3b",
        "label_35b_a3b",
        "desc_35b_a3b",
        int(22.6 * GB),
        rank=4,
        min_ollama="0.30.0",
    ),
    # Dense: every parameter works on every token. The most accurate; fast on a large GPU only.
    CatalogEntry(
        "qwen3.6:27b", "label_27b", "desc_27b", int(17.8 * GB), rank=5, min_ollama="0.30.0"
    ),
    CatalogEntry(
        "qwen3-embedding:0.6b", "label_embed", "desc_embed", int(0.64 * GB), kind="embedding"
    ),
]
BY_NAME = {e.name: e for e in CATALOG}
# Chat models, from the weakest to the best.
CHAT = sorted((e for e in CATALOG if e.kind == "chat"), key=lambda e: e.rank)


class UnknownModel(ValueError):
    pass


class Busy(RuntimeError):
    pass


@dataclass
class _Advice:
    """What this launch found about the machine (measured again at each launch)."""

    # Best model for the machine; None until measured, or when nothing fits the disk.
    recommended: str | None = None
    # Better model offered to the user, waiting for their answer.
    upgrade: str | None = None
    # Upgrade accepted: Binder switches to it as soon as its download ends.
    accepted: str | None = None
    # The active model was picked by Binder, not by the user.
    automatic: bool = True


_advice = _Advice()


def rank(name: str) -> int:
    """Quality rank of a catalogue chat model; 0 for any other (never compared)."""
    entry = BY_NAME.get(name.removesuffix(":latest"))
    return entry.rank if entry else 0


def _automatic(config: LlmConfig) -> bool:
    # BINDER_LLM_MODEL set by hand is the user's choice too.
    return config.auto and (
        config.model is not None or "llm_model" not in get_settings().model_fields_set
    )


# --- Model choice -----------------------------------------------------------------------


def restore(session: Session) -> None:
    """Reapplies at startup the model chosen in the settings."""
    config = settings_store.load(session, KEY, LlmConfig)
    _advice.automatic = _automatic(config)
    llm.select(config.model)


def advise(session: Session, recommended: str | None, fits: str | None) -> bool:
    """Called at each launch with the best model for the machine as measured now.

    `fits`: the best model its memory runs, disk aside (None: memory unknown). Offers an upgrade
    when Binder chose the active model and a better one is recommended, unless the user declined
    that very one. Never downgrades: True when the active model is now too heavy (a warning).
    """
    config = settings_store.load(session, KEY, LlmConfig)
    active = llm.model()
    _advice.recommended, _advice.upgrade = recommended, None
    _advice.automatic = _automatic(config)
    if not _advice.automatic or not rank(active):
        return False
    if recommended and rank(recommended) > rank(active) and recommended != config.declined:
        _advice.upgrade = recommended
    return fits is not None and rank(active) > rank(fits)


def accept_upgrade() -> None:
    """Downloads the offered model; Binder switches to it once it is ready."""
    name = _advice.upgrade
    if name is None:
        raise UnknownModel(T("no_upgrade"))
    _advice.accepted = name
    start_download(name)


def decline_upgrade(session: Session) -> None:
    name = _advice.upgrade
    if name is None:
        raise UnknownModel(T("no_upgrade"))
    cancel_download(name)
    config = settings_store.load(session, KEY, LlmConfig)
    config.declined = name
    settings_store.save(session, KEY, config)
    _advice.upgrade = _advice.accepted = None
    activity.log(session, "settings", T.msg("upgrade_declined", label=label(name)), actor="user")


def upgrade_offer() -> ModelUpgrade | None:
    name = _advice.upgrade
    if name is None:
        return None
    with _lock:
        download = _downloads.get(name)
    return ModelUpgrade(
        name=name,
        label=label(name),
        size=BY_NAME[name].size,
        accepted=_advice.accepted == name,
        download=download.out() if download else None,
    )


def _switch(session: Session, name: str) -> None:
    """Moves to the upgrade just downloaded; the former model stays installed."""
    previous = llm.model()
    config = settings_store.load(session, KEY, LlmConfig)
    config.model, config.auto = name, True
    settings_store.save(session, KEY, config)
    llm.select(name)
    llm.warm()
    _advice.upgrade = _advice.accepted = None
    _advice.automatic = _automatic(config)
    msg = T.msg("upgraded", old=label(previous), new=label(name))
    activity.log(session, "settings", msg, actor="binder")


def choose(session: Session, name: str, *, actor: str = "user") -> None:
    if name in BY_NAME and BY_NAME[name].kind != "chat":
        raise UnknownModel(T("not_in_catalog", name=name))
    installed = llm.installed_models()
    if installed is None:
        raise ConnectionError(T("ollama_down"))
    if not llm.is_installed(name, installed):
        raise UnknownModel(T("not_installed", name=name))
    if name != llm.model():
        activity.log(session, "settings", T.msg("chosen", label=label(name)), actor=actor)
    config = settings_store.load(session, KEY, LlmConfig)
    # A model the user picks is theirs: Binder stops offering upgrades over it.
    config.model, config.auto = name, actor != "user"
    settings_store.save(session, KEY, config)
    _advice.automatic = _automatic(config)
    changed = name != llm.model()
    llm.select(name)
    if changed:
        llm.warm()


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
    config = settings_store.load(session, KEY, LlmConfig)
    if config.model == name:
        config.model, config.auto = None, True
        settings_store.save(session, KEY, config)
        _advice.automatic = _automatic(config)
        llm.select(None)
    llm.forget_availability()
    embeddings.forget_availability()
    activity.log(session, "settings", T.msg("removed", label=label(name)), actor="user")


def label(name: str) -> str:
    """The model's name as shown to the user."""
    entry = BY_NAME.get(name.removesuffix(":latest"))
    return T(entry.label) if entry else name


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
        activity.log(session, "settings", T.msg("downloaded", label=label(name)))
        # First model installed, or active model missing: switch to the new one.
        installed = llm.installed_models() or {}
        is_chat = BY_NAME[name].kind == "chat" if name in BY_NAME else True
        if name == _advice.accepted:
            _switch(session, name)
        elif is_chat and not llm.is_installed(llm.model(), installed):
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
    # Before the machine is measured (or without automatic setup): the configured default.
    recommended = _advice.recommended or settings.llm_model
    with _lock:
        downloads = {name: d.out() for name, d in _downloads.items()}

    models = [
        ModelOut(
            name=e.name,
            label=T(e.label),
            description=T(e.description),
            size=installed.get(e.name, e.size) if installed else e.size,
            recommended=e.kind == "embedding" or e.name == recommended,
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
        active_label=label(active),
        recommended=recommended,
        recommended_label=label(recommended),
        automatic=_advice.automatic,
        upgrade=upgrade_offer(),
        models=models,
    )
