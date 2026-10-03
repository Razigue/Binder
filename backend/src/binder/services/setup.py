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
import re
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
from sqlmodel import Session

from binder import __version__, i18n
from binder.config import get_settings
from binder.db import get_engine
from binder.schemas import ModelUpgrade
from binder.services import llm, llm_models, process

log = logging.getLogger(__name__)

T = i18n.catalog(
    "setup",
    {
        "ollama_outdated": {
            "en": "Ollama {version} is older than {minimum}: the local AI may misread its own "
            "actions. Update Ollama.",
            "fr": "Ollama {version} est antérieur à {minimum} : l'IA locale peut mal lire ses "
            "propres actions. Mettez Ollama à jour.",
        },
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
        "too_large": {
            "en": "{label} is heavier than this computer now runs comfortably: Binder keeps it, "
            "but reading may be slow.",
            "fr": "{label} est plus lourd que ce que cet ordinateur fait tourner confortablement "
            "aujourd'hui : Binder le garde, mais la lecture peut être lente.",
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
# Given to the Ollama Binder starts, unless already set: flash attention and an 8-bit KV cache
# halve the cache's memory at no visible cost, which leaves more of the graphics card to the
# model's layers.
SERVE_ENV = {"OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0"}

# Memory ladder of pick_model (decimal GB, as measured). Each threshold leaves room for the
# context cache and for the system.
# Qwen 3.6 27B (17.8 GB) is dense: fast only when it fits the graphics card entirely, i.e. a
# 24 GB card (20 GB ones included), or a Mac whose GPU gets ~3/4 of 48 GB of unified memory.
DENSE_VRAM = 20 * GB
DENSE_APPLE_RAM = 48 * GB
# Qwen 3.6 35B-A3B (22.6 GB) is a mixture of experts: ~3B parameters work per token, so the
# layers Ollama keeps in RAM cost little speed. RAM and graphics memory add up (a Mac's memory is
# shared: RAM alone); on the CPU alone it is faster than the dense 9B.
MOE_BUDGET = 32 * GB
# Qwen 3.5 9B (6.6 GB): on an 8 GB card, or in RAM on a "16 GB" machine (which reports a little
# less once the firmware and integrated graphics have taken their share).
MID_VRAM = 8 * GB
MID_RAM = 15 * GB
# Qwen 3.5 4B (3.4 GB) needs ~10 GB of RAM next to the system; below, the 2B.
SMALL_RAM = 10 * GB
# Free disk needed per byte of model: Ollama writes partial files before the final blobs.
DISK_MARGIN = 1.2


class SetupStatus(BaseModel):
    phase: Phase
    # Bytes done / to do in the current step (installing, downloading).
    completed: int = 0
    total: int = 0
    # Model being installed or in use.
    model: str | None = None
    error: str | None = None
    # Works, but not as well as it should (an outdated Ollama, a model too heavy for the machine).
    warning: str | None = None
    # A better model for this machine, offered (never downloaded without the user's yes).
    upgrade: ModelUpgrade | None = None


@dataclass
class _State:
    phase: Phase = "checking"
    completed: int = 0
    total: int = 0
    model: str | None = None
    error: str | None = None
    warning: str | None = None
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
            warning=state.warning,
            upgrade=llm_models.upgrade_offer(),
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
        llm.set_owned(_owned())
        check_version()
        # Measured at each launch: memory, a graphics card or free space may have changed.
        machine = measure()
        # A graphics card (or Apple silicon) runs a large model fast enough to reason.
        llm.set_accelerated(machine.vram >= MID_VRAM or machine.apple)
        _ensure_models(machine)
        _advise(machine)
        _set(phase="ready", completed=0, total=0)
        llm.warm()
    except Exception as e:
        log.warning("Local AI setup failed: %s", e)
        _set(phase="error", error=str(e) or T("download_failed"))
        return
    if served:
        _upgrade()


def check_version() -> None:
    """Warns, without blocking, when Ollama predates the model support Binder relies on."""
    version = llm.ollama_version()
    warning = None
    if llm.outdated_ollama(version):
        warning = T("ollama_outdated", version=version, minimum=llm.MIN_OLLAMA_VERSION)
        log.warning("Ollama %s is older than %s", version, llm.MIN_OLLAMA_VERSION)
    _set(warning=warning)


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


# What Ollama found at startup, in its log: one line per device it can run models on.
INFERENCE_COMPUTE = re.compile(r'msg="inference compute".*')
_FIELD = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+))')
_UNITS = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}
# Tail of ollama.log read for them: the last start is near its end.
LOG_TAIL = 2_000_000


def _bytes(size: str) -> int:
    number, _, unit = size.partition(" ")
    try:
        return int(float(number) * _UNITS.get(unit, 1))
    except ValueError:
        return 0


def ollama_gpu_bytes(log_file: Path | None = None) -> int:
    """Graphics memory Ollama reported at its last start, all vendors (CUDA, ROCm, Vulkan,
    Metal): integrated graphics and the processor left out. 0 when it reported none."""
    path = log_file or get_settings().data_dir / "ollama.log"
    try:
        with path.open("rb") as f:
            f.seek(max(0, path.stat().st_size - LOG_TAIL))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return 0
    # Only the devices of the last start (one "server config" line per start).
    text = text[text.rfind('msg="server config"') + 1 :]
    devices: dict[str, int] = {}
    for line in INFERENCE_COMPUTE.findall(text):
        fields = {k: a or b for k, a, b in _FIELD.findall(line)}
        if fields.get("library", "").lower() == "cpu" or fields.get("type", "").lower() == "igpu":
            continue
        key = fields.get("pci_id") or fields.get("id") or str(len(devices))
        devices[key] = _bytes(fields.get("total", ""))
    return sum(devices.values())


def gpu_memory_bytes() -> int:
    """Graphics card memory: what Ollama found, or an NVIDIA card's (0 without one)."""
    return max(ollama_gpu_bytes() if _owned() else 0, _nvidia_bytes())


def _nvidia_bytes() -> int:
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


def memory_tier(ram: int, vram: int, apple: bool = False) -> str:
    """The best chat model this memory runs comfortably, disk aside.

    `apple`: Apple silicon, whose memory is shared by the processor and the GPU (`ram` alone).
    """
    budget = ram if apple else ram + vram
    if vram >= DENSE_VRAM or (apple and ram >= DENSE_APPLE_RAM):
        return "qwen3.6:27b"
    if budget >= MOE_BUDGET:
        return "qwen3.6:35b-a3b"
    if vram >= MID_VRAM or ram >= MID_RAM:
        return "qwen3.5:9b"
    # Memory unknown (0): the middle of the ladder rather than its bottom.
    if ram >= SMALL_RAM or ram == 0:
        return "qwen3.5:4b"
    return "qwen3.5:2b"


def pick_model(
    ram: int, vram: int, free_disk: int, apple: bool = False, ollama: str | None = None
) -> str | None:
    """The best chat model of the catalogue this machine runs comfortably and can store.

    Steps down the ranks while the disk lacks room, or the running Ollama (`ollama`, its
    version when known) is too old for a model.
    """
    wanted = llm_models.rank(memory_tier(ram, vram, apple))
    for entry in reversed(llm_models.CHAT):
        if entry.rank > wanted or llm.outdated_ollama(ollama, entry.min_ollama):
            continue
        if entry.size * DISK_MARGIN < free_disk:
            return entry.name
    return None


@dataclass(frozen=True)
class Machine:
    ram: int
    vram: int
    free_disk: int
    apple: bool
    ollama: str | None

    def pick(self) -> str | None:
        return pick_model(self.ram, self.vram, self.free_disk, self.apple, self.ollama)


def measure() -> Machine:
    """This machine as it is now (never cached: it may change between launches)."""
    return Machine(
        ram=memory_bytes(),
        vram=gpu_memory_bytes(),
        free_disk=_free_disk(),
        apple=sys.platform == "darwin" and _machine() == "aarch64",
        ollama=llm.ollama_version(),
    )


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
    try:
        if _fetch(url, archive, foreground) != sha256:
            raise RuntimeError(T("corrupted"))
        _extract(archive, staging)
        archive.unlink()
        (staging / VERSION_FILE).write_text(OLLAMA_VERSION, encoding="utf-8")
    except BaseException:
        # Never a half-written Ollama: a disk full or a bad archive leaves nothing behind.
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(target, ignore_errors=True)
    staging.rename(target)
    binary = _binary_in(target)
    if binary is None:
        raise RuntimeError(T("unsupported"))
    if sys.platform != "win32":
        binary.chmod(0o755)
    return binary


def _fetch(url: str, archive: Path, foreground: bool) -> str:
    """Downloads `url` into `archive`; returns its SHA-256."""
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
        raise RuntimeError(T("download_failed")) from e
    return digest.hexdigest()


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
    env = {**SERVE_ENV, **os.environ, "OLLAMA_HOST": f"{url.hostname}:{url.port or 11434}"}
    if _owned():
        adopt_models(_user_models_dir(), get_settings().data_dir / "models")
        env["OLLAMA_MODELS"] = str(_models_dir())
    kwargs = process.no_window()
    if sys.platform != "win32":
        kwargs["start_new_session"] = True
    # Ollama writes to its own copy of the handle: Binder's is closed once it started.
    with (get_settings().data_dir / "ollama.log").open("ab") as log_file:
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


def _ensure_models(machine: Machine) -> None:
    installed = llm.installed_models() or {}
    chat_ready = any(
        llm.is_installed(e.name, installed) for e in llm_models.CHAT
    ) or llm.is_installed(llm.model(), installed)
    if not chat_ready:
        name = machine.pick()
        if name is None:
            smallest = min(e.size for e in llm_models.CHAT)
            raise RuntimeError(T("no_space", size=round(smallest * DISK_MARGIN / GB, 1)))
        _download(name)
    embed = get_settings().embed_model
    if not llm.is_installed(embed, llm.installed_models() or {}):
        try:
            _download(embed)
        except Exception as e:  # search by meaning is a bonus
            log.info("Search model %s not installed: %s", embed, e)


def _advise(machine: Machine) -> None:
    """Offers a better model when one now suits the machine; warns when the active one is too
    heavy for it (never a silent download, never a downgrade)."""
    fits = memory_tier(machine.ram, machine.vram, machine.apple) if machine.ram else None
    with Session(get_engine()) as session:
        too_large = llm_models.advise(session, machine.pick(), fits)
        # Models no longer used (dropped from the catalogue, replaced) leave the disk.
        llm_models.prune(session)
        session.commit()
    if too_large:
        heavy = T("too_large", label=llm_models.label(llm.model()))
        _set(warning=" ".join(w for w in (_state.warning, heavy) if w))


def _download(name: str) -> None:
    _set(phase="downloading", model=name, completed=0, total=0)
    llm_models.start_download(name)
    while (download := llm_models.download_state(name)) is not None:
        if download.phase == "error":
            raise RuntimeError(download.error or T("download_failed"))
        _set(completed=download.completed, total=download.total)
        if _state.stop.wait(1.0):
            return
    if not llm.is_installed(name, llm.installed_models() or {}):
        raise RuntimeError(T("download_failed"))
