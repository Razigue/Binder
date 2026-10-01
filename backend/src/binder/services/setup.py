"""Local AI with no steps.

At launch, in the background: Binder starts its own Ollama, hidden, on a free loopback port, with
its models in Binder's data folder. The user never sees it: no tray icon, no shared port, nothing
left running after Binder closes (even after a crash). Binder then picks the model that suits the
machine (memory, graphics card, free disk space) and downloads it, then the small search model.
The interface only shows the progress. Nothing about the user's documents is sent: the downloads
are Ollama itself and the model weights.

Ollama is pinned to the version Binder is tested with (OLLAMA_VERSION), downloaded from its
official release with a checksum written here. The first launch uses an Ollama already on the
machine if there is one, to start at once; the pinned version is then fetched in the background
and takes over at the next launch. Models the user's Ollama already pulled are hard-linked into
Binder's folder: no download, no extra disk space.

With BINDER_OLLAMA_URL set, that Ollama is used as it is (started if local and not answering).
"""

import contextlib
import ctypes
import hashlib
import logging
import os
import platform
import shutil
import signal
import socket
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
# The Ollama version Binder is tested with. To upgrade: new tag, and the SHA-256 of its assets
# from the release's sha256sum.txt.
OLLAMA_VERSION = "v0.35.0"
# Ollama's own release archives of that version, per system and processor: (name, SHA-256).
ASSETS = {
    ("linux", "x86_64"): (
        "ollama-linux-amd64.tar.zst",
        "1c114a6b220c5efca2ef2b1e5f01d1e535e26f6cd6d1678c8489325d2835e525",
    ),
    ("linux", "aarch64"): (
        "ollama-linux-arm64.tar.zst",
        "cb627d332b1fe5055bd5485ca10d595da8429e447648209e375390ec3bd09374",
    ),
    ("darwin", "x86_64"): (
        "ollama-darwin.tgz",
        "2608dbb0a0f0136a198db9d48b4f74ece55f452314a39452fca35b7cf20c2589",
    ),
    ("darwin", "arm64"): (
        "ollama-darwin.tgz",
        "2608dbb0a0f0136a198db9d48b4f74ece55f452314a39452fca35b7cf20c2589",
    ),
    ("win32", "amd64"): (
        "ollama-windows-amd64.zip",
        "d6f7d3dd4f5d013553a78c1e78b2521fcf41d43dd2863e4596cdc046fe6036db",
    ),
    ("win32", "arm64"): (
        "ollama-windows-arm64.zip",
        "99d061915a68fb563da0fb9316fd112cfc6fce0c9478601b2765b1f973cb715e",
    ),
}
# Written next to an installed Ollama: the version it is.
VERSION_FILE = ".binder-version"
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
    # Address of Binder's own Ollama, drawn once per launch (None: BINDER_OLLAMA_URL is used).
    own_url: str | None = None
    # Windows job object that ends Ollama with Binder; kept open for the whole session.
    job: int | None = None
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
        # Set before anything asks the AI: never fall back on another Ollama on port 11434.
        if _state.own_url is None and "ollama_url" not in settings.model_fields_set:
            _state.own_url = f"http://127.0.0.1:{_free_port()}"
            settings.ollama_url = _state.own_url
            llm.forget_availability()
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
    _pid_file().unlink(missing_ok=True)


def _set(**changes: Any) -> None:
    with _lock:
        for key, value in changes.items():
            setattr(_state, key, value)


def _run() -> None:
    served = False
    try:
        if llm.installed_models() is None:
            if not _local():
                raise RuntimeError(T("not_starting"))
            _stop_orphan()
            _apply_upgrade()
            binary = find_ollama() or _install(managed_dir(), foreground=True)
            _set(phase="starting", completed=0, total=0)
            _serve(binary)
            served = True
        _ensure_models()
        _set(phase="ready", completed=0, total=0)
    except Exception as e:
        log.warning("Local AI setup failed: %s", e)
        _set(phase="error", error=str(e) or T("download_failed"))
        return
    if served:
        _upgrade()


def _local() -> bool:
    host = urlparse(get_settings().ollama_url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1")


def _owned() -> bool:
    return _state.own_url is not None and get_settings().ollama_url == _state.own_url


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


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


def _user_models_dir() -> Path:
    """Where the user's own Ollama keeps its models."""
    custom = os.environ.get("OLLAMA_MODELS")
    return Path(custom).expanduser() if custom else Path.home() / ".ollama" / "models"


def _models_dir() -> Path:
    if not _owned():
        return _user_models_dir()
    own = get_settings().data_dir / "models"
    # Models that could not be linked from the user's Ollama (other disk) are used where they
    # are rather than downloaded again.
    return own if own.is_dir() or not _has_models(_user_models_dir()) else _user_models_dir()


def _has_models(models: Path) -> bool:
    manifests = models / "manifests"
    return manifests.is_dir() and any(p.is_file() for p in manifests.rglob("*"))


def adopt_models(source: Path, target: Path) -> bool:
    """Hard-links the models of the user's Ollama into Binder's folder (once).

    Blobs are immutable and named by their digest: links cost no disk space, and the user's
    Ollama keeps its copies. False when links are impossible (another disk, FAT32).
    """
    if target.exists() or not _has_models(source):
        return True
    staging = target.with_name(f"{target.name}.partial")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        for file in source.rglob("*"):
            if file.is_file():
                dest = staging / file.relative_to(source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.link(file, dest)
        staging.rename(target)
    except OSError as e:
        log.info("Models of the user's Ollama not linked: %s", e)
        shutil.rmtree(staging, ignore_errors=True)
        return False
    return True


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


def _next_dir() -> Path:
    """The pinned version, downloaded in the background, used from the next launch."""
    return managed_dir().with_name("ollama.next")


def _executable_name() -> str:
    return "ollama.exe" if sys.platform == "win32" else "ollama"


def _binary_in(folder: Path) -> Path | None:
    if not folder.is_dir():
        return None
    return min(folder.rglob(_executable_name()), key=lambda p: len(p.parts), default=None)


def installed_version(folder: Path) -> str | None:
    try:
        return (folder / VERSION_FILE).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def find_ollama() -> Path | None:
    """An Ollama already on the machine: Binder's own, on the PATH, or at a usual place."""
    own = _binary_in(managed_dir())
    if own is not None:
        return own
    candidates = []
    on_path = shutil.which("ollama")
    if on_path:
        candidates.append(Path(on_path))
    candidates += [Path(p).expanduser() for p in KNOWN_PATHS]
    return next((p for p in candidates if p.is_file()), None)


def _machine() -> str:
    machine = platform.machine().lower()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)


def _asset(system: str = sys.platform, machine: str | None = None) -> tuple[str, str] | None:
    machine = machine or _machine()
    if system == "win32":
        machine = "arm64" if machine == "aarch64" else "amd64"
    elif system == "darwin":
        machine = "arm64" if machine in ("aarch64", "arm64") else "x86_64"
    return ASSETS.get((system, machine))


def asset_name(system: str = sys.platform, machine: str | None = None) -> str | None:
    asset = _asset(system, machine)
    return asset[0] if asset else None


def _client(timeout: float | httpx.Timeout = 15.0) -> httpx.Client:
    from binder import updater

    return httpx.Client(
        timeout=timeout,
        transport=updater.transport,
        follow_redirects=True,
        headers={"User-Agent": f"Binder/{__version__}"},
    )


def _install(target: Path, foreground: bool) -> Path:
    """Downloads the pinned Ollama into `target` (no administrator rights needed).

    In the foreground the interface shows the progress; in the background (upgrade), nothing.
    """
    asset = _asset()
    if asset is None:
        raise RuntimeError(T("unsupported"))
    name, sha256 = asset
    url = f"{get_settings().ollama_download_url.rstrip('/')}/{OLLAMA_VERSION}/{name}"
    staging = target.with_name(f"{target.name}.partial")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    archive = staging / name
    digest = hashlib.sha256()
    done = 0
    try:
        with (
            _client(httpx.Timeout(15.0, read=120.0)) as c,
            c.stream("GET", url) as r,
        ):
            r.raise_for_status()
            size = int(r.headers.get("Content-Length") or 0)
            if size and size * 2.5 > _free_disk():
                raise RuntimeError(T("no_space", size=round(size * 2.5 / GB, 1)))
            if foreground:
                _set(phase="installing", completed=0, total=size)
            with archive.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    if _state.stop.is_set():
                        raise RuntimeError(T("download_failed"))
                    f.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if foreground:
                        _set(completed=done)
    except httpx.HTTPError as e:
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError(T("download_failed")) from e
    except RuntimeError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if digest.hexdigest() != sha256:
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError(T("corrupted"))
    _extract(archive, staging)
    archive.unlink()
    (staging / VERSION_FILE).write_text(OLLAMA_VERSION, encoding="utf-8")
    shutil.rmtree(target, ignore_errors=True)
    staging.rename(target)
    binary = _binary_in(target)
    if binary is None:
        raise RuntimeError(T("unsupported"))
    if sys.platform != "win32":
        binary.chmod(0o755)
    return binary


def _upgrade() -> None:
    """In the background, once ready: fetches the pinned Ollama when another one is in use."""
    if _asset() is None or OLLAMA_VERSION in (
        installed_version(managed_dir()),
        installed_version(_next_dir()),
    ):
        return
    try:
        _install(_next_dir(), foreground=False)
        log.info("Ollama %s ready for the next launch", OLLAMA_VERSION)
    except Exception as e:  # tried again at the next launch
        log.info("Ollama upgrade postponed: %s", e)


def _apply_upgrade() -> None:
    """At launch, before Ollama runs: puts the version fetched last time in place."""
    upcoming = _next_dir()
    if installed_version(upcoming) != OLLAMA_VERSION:
        return
    current, old = managed_dir(), managed_dir().with_name("ollama.old")
    try:
        shutil.rmtree(old, ignore_errors=True)
        if current.exists():
            current.rename(old)
        upcoming.rename(current)
    except OSError as e:
        log.warning("Ollama upgrade not applied: %s", e)
        if old.exists() and not current.exists():
            old.rename(current)
        return
    shutil.rmtree(old, ignore_errors=True)


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


# --- Ollama's process ------------------------------------------------------------------------


def _pid_file() -> Path:
    return get_settings().data_dir / "ollama.pid"


def _stop_orphan() -> None:
    """Linux, macOS: stops the Ollama a crashed Binder left running (Windows: see _tie)."""
    pid_file = _pid_file()
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return
    pid_file.unlink(missing_ok=True)
    if sys.platform == "win32" or pid == os.getpid():
        return
    try:
        out = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=3
        )
    except (OSError, subprocess.SubprocessError):
        return
    # The number may belong to another program by now: only an Ollama server is stopped.
    command = out.stdout.strip()
    if "ollama" in command and "serve" in command:
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)


def _tie(process: subprocess.Popen[bytes]) -> None:
    """Windows: Ollama (and the runners it starts) end with Binder, even after a crash.

    A job object with KILL_ON_JOB_CLOSE: Windows closes its handle when Binder's process ends,
    however it ends, and then stops every process in the job.
    """
    if sys.platform != "win32":
        return
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", ctypes.c_ulonglong * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kill_on_job_close, extended_limit_information = 0x2000, 9
    set_quota, terminate = 0x0100, 0x0001
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.OpenProcess.restype = wintypes.HANDLE
    if _state.job is None:
        job = kernel32.CreateJobObjectW(None, None)
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = kill_on_job_close
        if not job or not kernel32.SetInformationJobObject(
            wintypes.HANDLE(job),
            extended_limit_information,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            log.warning("Ollama not tied to Binder: error %s", ctypes.get_last_error())
            return
        _state.job = int(job)
    handle = kernel32.OpenProcess(set_quota | terminate, False, process.pid)
    if not handle:
        return
    if not kernel32.AssignProcessToJobObject(wintypes.HANDLE(_state.job), wintypes.HANDLE(handle)):
        log.warning("Ollama not tied to Binder: error %s", ctypes.get_last_error())
    kernel32.CloseHandle(wintypes.HANDLE(handle))


def _serve(binary: Path) -> None:
    """Starts `ollama serve` for this session and waits until it answers."""
    url = urlparse(get_settings().ollama_url)
    env = {**os.environ, "OLLAMA_HOST": f"{url.hostname}:{url.port or 11434}"}
    if _owned():
        adopt_models(_user_models_dir(), get_settings().data_dir / "models")
        env["OLLAMA_MODELS"] = str(_models_dir())
    log_file = (get_settings().data_dir / "ollama.log").open("ab")
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
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
    _tie(_state.process)
    with contextlib.suppress(OSError):
        _pid_file().write_text(str(_state.process.pid), encoding="utf-8")
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
