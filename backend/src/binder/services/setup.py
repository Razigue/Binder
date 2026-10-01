"""Local AI with no steps.

At launch, in the background: Binder finds Ollama (or installs it in its data folder, from the
official release, checksum verified), starts it if it is not running, picks the model that suits
the machine (memory, graphics card, free disk space) and downloads it, then the small search
model. The interface only shows the progress. Nothing about the user's documents is sent: the
downloads are Ollama itself and the model weights.

Only a local Ollama (localhost) is managed; a remote BINDER_OLLAMA_URL is used as it is.
"""

import contextlib
import ctypes
import hashlib
import logging
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from binder import __version__, i18n
from binder.config import get_settings
from binder.services import llm, llm_models

log = logging.getLogger(__name__)

T = i18n.catalog(
    "setup",
    {
        "no_space": {
            "en": "Not enough free disk space for the local AI ({size} GB needed).",
            "fr": "Pas assez d'espace disque pour l'IA locale ({size} Go nécessaires).",
        },
        "unsupported": {
            "en": "The local AI cannot be installed automatically on this system.",
            "fr": "L'IA locale ne peut pas être installée automatiquement sur ce système.",
        },
        "download_failed": {
            "en": "Download interrupted. Binder will try again at next launch.",
            "fr": "Téléchargement interrompu. Binder réessaiera au prochain lancement.",
        },
        "corrupted": {
            "en": "The download was corrupted. Binder will try again.",
            "fr": "Le téléchargement était corrompu. Binder réessaiera.",
        },
        "not_starting": {
            "en": "The local AI did not start.",
            "fr": "L'IA locale n'a pas démarré.",
        },
    },
)

Phase = Literal["disabled", "checking", "installing", "starting", "downloading", "ready", "error"]
GB = 1_000_000_000
# Ollama's own release archives, per system and processor.
ASSETS = {
    ("linux", "x86_64"): "ollama-linux-amd64.tar.zst",
    ("linux", "aarch64"): "ollama-linux-arm64.tar.zst",
    ("darwin", "x86_64"): "ollama-darwin.tgz",
    ("darwin", "arm64"): "ollama-darwin.tgz",
    ("win32", "amd64"): "ollama-windows-amd64.zip",
    ("win32", "arm64"): "ollama-windows-arm64.zip",
}
# Where a system-wide Ollama usually lives.
KNOWN_PATHS = [
    "/usr/local/bin/ollama",
    "/usr/bin/ollama",
    "/opt/homebrew/bin/ollama",
    "/Applications/Ollama.app/Contents/Resources/ollama",
    "~/AppData/Local/Programs/Ollama/ollama.exe",
]
START_TIMEOUT = 60.0


class SetupStatus(BaseModel):
    phase: Phase
    # Bytes done / to do in the current step (installing, downloading).
    completed: int = 0
    total: int = 0
    # Model being installed or in use.
    model: str | None = None
    error: str | None = None


@dataclass
class _State:
    phase: Phase = "checking"
    completed: int = 0
    total: int = 0
    model: str | None = None
    error: str | None = None
    process: subprocess.Popen[bytes] | None = None
    thread: threading.Thread | None = None
    stop: threading.Event = field(default_factory=threading.Event)


_state = _State()
_lock = threading.Lock()


def status() -> SetupStatus:
    if not get_settings().llm_enabled:
        return SetupStatus(phase="disabled")
    with _lock:
        state = _state
        phase: Phase = state.phase
        if phase == "checking" and state.thread is None and llm.is_available():
            phase = "ready"
        return SetupStatus(
            phase=phase,
            completed=state.completed,
            total=state.total,
            model=state.model or llm.model(),
            error=state.error,
        )


def start() -> None:
    """Runs the setup in the background (once; again after an error)."""
    settings = get_settings()
    if not settings.llm_enabled or not settings.auto_setup:
        return
    with _lock:
        if _state.thread is not None and _state.thread.is_alive():
            return
        _state.phase, _state.error, _state.completed, _state.total = "checking", None, 0, 0
        _state.stop.clear()
        _state.thread = threading.Thread(target=_run, name="binder-setup", daemon=True)
        _state.thread.start()


def wait(timeout: float = 10.0) -> None:
    """Waits for the setup to end (tests)."""
    if _state.thread is not None:
        _state.thread.join(timeout)


def shutdown() -> None:
    """Stops the Ollama server Binder started (not one the user runs)."""
    _state.stop.set()
    process = _state.process
    if process is not None and process.poll() is None:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(5)
    _state.process = None


def _set(**changes: Any) -> None:
    with _lock:
        for key, value in changes.items():
            setattr(_state, key, value)


def _run() -> None:
    try:
        if llm.installed_models() is None:
            if not _local():
                raise RuntimeError(T("not_starting"))
            binary = find_ollama() or _install()
            _set(phase="starting", completed=0, total=0)
            _serve(binary)
        _ensure_models()
        _set(phase="ready", completed=0, total=0)
    except Exception as e:
        log.warning("Local AI setup failed: %s", e)
        _set(phase="error", error=str(e) or T("download_failed"))


def _local() -> bool:
    host = urlparse(get_settings().ollama_url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1")


# --- The machine ---------------------------------------------------------------------------


def memory_bytes() -> int:
    """Physical memory (0 if unknown)."""
    try:
        if sys.platform == "win32":

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MemoryStatus()
            stat.dwLength = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullTotalPhys)
        if sys.platform == "darwin":
            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3
            )
            return int(out.stdout.strip() or 0)
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        return 0


def gpu_memory_bytes() -> int:
    """Memory of an NVIDIA graphics card (0 without one)."""
    nvidia = shutil.which("nvidia-smi")
    if nvidia is None:
        return 0
    try:
        out = subprocess.run(
            [nvidia, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return max((int(x) for x in out.stdout.split() if x.isdigit()), default=0) * 1024**2
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def pick_model(ram: int, vram: int, free_disk: int, apple: bool = False) -> str | None:
    """The best chat model of the catalogue this machine runs comfortably and can store."""
    if vram >= 20 * GB or (apple and ram >= 48 * GB):
        wanted = "qwen3.5:27b"
    elif vram >= 8 * GB or ram >= 15 * GB:
        wanted = "qwen3.5:9b"
    elif ram >= 10 * GB or ram == 0:
        wanted = "qwen3.5:4b"
    else:
        wanted = "qwen3.5:2b"
    chat = [e for e in llm_models.CATALOG if e.kind == "chat"]
    names = [e.name for e in chat]
    for entry in chat[names.index(wanted) :: -1]:
        if entry.size * 1.2 < free_disk:
            return entry.name
    return None


def _models_dir() -> Path:
    custom = os.environ.get("OLLAMA_MODELS")
    return Path(custom).expanduser() if custom else Path.home() / ".ollama" / "models"


def _free_disk() -> int:
    target = _models_dir()
    while not target.exists() and target != target.parent:
        target = target.parent
    try:
        return shutil.disk_usage(target).free
    except OSError:
        return 0


# --- Ollama ----------------------------------------------------------------------------------


def managed_dir() -> Path:
    return get_settings().data_dir / "ollama"


def _executable_name() -> str:
    return "ollama.exe" if sys.platform == "win32" else "ollama"


def find_ollama() -> Path | None:
    """An Ollama already on the machine: Binder's own, on the PATH, or at a usual place."""
    candidates = sorted(
        managed_dir().rglob(_executable_name()) if managed_dir().is_dir() else [],
        key=lambda p: len(p.parts),
    )
    on_path = shutil.which("ollama")
    if on_path:
        candidates.append(Path(on_path))
    candidates += [Path(p).expanduser() for p in KNOWN_PATHS]
    return next((p for p in candidates if p.is_file()), None)


def _machine() -> str:
    machine = platform.machine().lower()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)


def asset_name(system: str = sys.platform, machine: str | None = None) -> str | None:
    machine = machine or _machine()
    if system == "win32":
        machine = "arm64" if machine == "aarch64" else "amd64"
    elif system == "darwin":
        machine = "arm64" if machine in ("aarch64", "arm64") else "x86_64"
    return ASSETS.get((system, machine))


def _client(timeout: float | httpx.Timeout = 15.0) -> httpx.Client:
    from binder import updater

    return httpx.Client(
        timeout=timeout,
        transport=updater.transport,
        follow_redirects=True,
        headers={"User-Agent": f"Binder/{__version__}"},
    )


def _release_asset(name: str) -> tuple[str, int, str]:
    """(download URL, size, sha256) of an asset of Ollama's latest release."""
    with _client() as c:
        r = c.get(get_settings().ollama_release_url)
        r.raise_for_status()
        assets = {a["name"]: a for a in r.json().get("assets", [])}
        asset = assets.get(name)
        if asset is None:
            raise RuntimeError(T("unsupported"))
        digest = str(asset.get("digest") or "")
        sha = digest.removeprefix("sha256:") if digest.startswith("sha256:") else ""
        if not sha and "sha256sum.txt" in assets:
            sums = c.get(str(assets["sha256sum.txt"]["browser_download_url"]))
            sums.raise_for_status()
            for line in sums.text.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].lstrip("*").lstrip("./") == name:
                    sha = parts[0]
        if not sha:
            raise RuntimeError(T("corrupted"))
        return str(asset["browser_download_url"]), int(asset.get("size") or 0), sha.lower()


def _install() -> Path:
    """Downloads Ollama into Binder's data folder (no administrator rights needed)."""
    name = asset_name()
    if name is None:
        raise RuntimeError(T("unsupported"))
    url, size, sha256 = _release_asset(name)
    if size and size * 2.5 > _free_disk():
        raise RuntimeError(T("no_space", size=round(size * 2.5 / GB, 1)))
    _set(phase="installing", completed=0, total=size)
    target = managed_dir()
    staging = target.with_name("ollama.partial")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    archive = staging / name
    digest = hashlib.sha256()
    done = 0
    try:
        with (
            _client(httpx.Timeout(15.0, read=120.0)) as c,
            c.stream("GET", url) as r,
            archive.open("wb") as f,
        ):
            r.raise_for_status()
            for chunk in r.iter_bytes(1 << 20):
                if _state.stop.is_set():
                    raise RuntimeError(T("download_failed"))
                f.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                _set(completed=done)
    except httpx.HTTPError as e:
        raise RuntimeError(T("download_failed")) from e
    if digest.hexdigest() != sha256:
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError(T("corrupted"))
    _extract(archive, staging)
    archive.unlink()
    shutil.rmtree(target, ignore_errors=True)
    staging.rename(target)
    binary = find_ollama()
    if binary is None or not binary.is_relative_to(target):
        raise RuntimeError(T("unsupported"))
    if sys.platform != "win32":
        binary.chmod(0o755)
    return binary


def _extract(archive: Path, into: Path) -> None:
    name = archive.name
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(into)
    elif name.endswith(".tar.zst"):
        import zstandard

        with (
            archive.open("rb") as f,
            zstandard.ZstdDecompressor().stream_reader(f) as reader,
            tarfile.open(fileobj=reader, mode="r|") as tar,
        ):
            tar.extractall(into, filter="data")
    else:
        with tarfile.open(archive) as tar:
            tar.extractall(into, filter="data")


def _serve(binary: Path) -> None:
    """Starts `ollama serve` for this session and waits until it answers."""
    url = urlparse(get_settings().ollama_url)
    env = {**os.environ, "OLLAMA_HOST": f"{url.hostname}:{url.port or 11434}"}
    log_file = (get_settings().data_dir / "ollama.log").open("ab")
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    _state.process = subprocess.Popen(
        [str(binary), "serve"],
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        **kwargs,
    )
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if llm.installed_models() is not None:
            llm.forget_availability()
            return
        if _state.process.poll() is not None:
            break
        time.sleep(0.5)
    raise RuntimeError(T("not_starting"))


def _ensure_models() -> None:
    installed = llm.installed_models() or {}
    chat_ready = any(
        llm.is_installed(e.name, installed) for e in llm_models.CATALOG if e.kind == "chat"
    ) or llm.is_installed(llm.model(), installed)
    if not chat_ready:
        apple = sys.platform == "darwin" and _machine() == "aarch64"
        name = pick_model(memory_bytes(), gpu_memory_bytes(), _free_disk(), apple)
        if name is None:
            smallest = min(e.size for e in llm_models.CATALOG if e.kind == "chat")
            raise RuntimeError(T("no_space", size=round(smallest * 1.2 / GB, 1)))
        _download(name)
    embed = get_settings().embed_model
    if not llm.is_installed(embed, llm.installed_models() or {}):
        with contextlib.suppress(Exception):  # search by meaning is a bonus
            _download(embed)


def _download(name: str) -> None:
    _set(phase="downloading", model=name, completed=0, total=0)
    llm_models.start_download(name)
    while True:
        overview = {m.name: m for m in llm_models.overview().models}
        model = overview.get(name)
        if model is None or model.download is None:
            break
        if model.download.phase == "error":
            raise RuntimeError(model.download.error or T("download_failed"))
        _set(completed=model.download.completed, total=model.download.total)
        if _state.stop.wait(1.0):
            return
    if not llm.is_installed(name, llm.installed_models() or {}):
        raise RuntimeError(T("download_failed"))
