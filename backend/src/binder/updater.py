"""Desktop application update from GitHub releases, at launch.

Installed with the installer (Velopack: Setup.exe, .pkg, AppImage), Binder updates through
Velopack: delta packages, verified, applied while Binder restarts. See `installed()`.

The portable archives (and the versions published before the installer) use the update below.
Like Discord: on startup, Binder queries the latest release. If it is newer, the archive for
this system is downloaded next to the installation, verified (SHA-256) and extracted, then
replaces the old version, and Binder restarts.

- Linux and macOS: folders are renamed while the application runs, which POSIX allows.
- Windows locks running files: the new version, started from the update folder, waits for
  the old one to close, copies itself in its place, then relaunches the installation.
  Temporary folders are removed at the next launch.

A failed update (offline, read-only folder, corrupted archive) never prevents Binder from
starting. Error messages here are developer-facing (logged), not shown to the user.
"""

import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from binder import __version__
from binder.config import get_settings

log = logging.getLogger(__name__)

# Archives published by the "Release" workflow (names shared with release.yml).
ASSETS = {
    "linux": "Binder-linux-x64.tar.gz",
    "win32": "Binder-windows-x64.zip",
    "darwin": "Binder-macos-arm64.zip",
}
CHECKSUMS = "SHA256SUMS.txt"

# Replaceable in tests by an httpx.MockTransport.
transport: httpx.BaseTransport | None = None

Progress = Callable[[int, int], None]


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    asset: str
    url: str
    size: int
    sha256: str


def _client(timeout: float | httpx.Timeout = 10.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        transport=transport,
        follow_redirects=True,
        headers={"User-Agent": f"Binder/{__version__}"},
    )


# --- Installed application (Velopack) -----------------------------------------------------


def installed() -> Any | None:
    """Velopack's update manager when Binder runs from its installer, otherwise None.

    Velopack refuses to create one outside an installation (portable archive, sources).
    """
    if not getattr(sys, "frozen", False):
        return None
    try:
        import velopack

        return velopack.UpdateManager(velopack.GithubSource(get_settings().update_repo))
    except Exception as e:
        log.info("Not installed by the installer: %s", e)
        return None


def download_size(info: Any) -> int:
    """Bytes Velopack downloads for an update: the deltas when it can, else the full package."""
    deltas = sum(int(d.Size) for d in info.DeltasToTarget)
    return deltas or int(info.TargetFullRelease.Size)


# --- Versions ------------------------------------------------------------------------------


def parse_version(text: str) -> tuple[int, ...]:
    """ "v1.2.3" → (1, 2, 3). Suffixes (-beta, rc1…) are ignored."""
    match = re.match(r"[vV]?(\d+(?:\.\d+)*)", text.strip())
    if match is None:
        raise ValueError(f"Unreadable version: {text!r}")
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


# --- Locations -----------------------------------------------------------------------------


def install_root() -> Path | None:
    """Folder replaced by an update: Binder/ or Binder.app. None outside the packaged app."""
    if not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable).resolve()
    # macOS: Binder.app/Contents/MacOS/Binder
    return exe.parents[2] if sys.platform == "darwin" else exe.parent


def staging_dir(root: Path) -> Path:
    return root.with_name(f"{root.name}.update")


def backup_dir(root: Path) -> Path:
    return root.with_name(f"{root.name}.old")


def executable(root: Path, platform: str = sys.platform) -> Path:
    if platform == "darwin":
        return root / "Contents" / "MacOS" / "Binder"
    return root / ("Binder.exe" if platform == "win32" else "Binder")


# --- Check and download --------------------------------------------------------------------


def check(current: str = __version__, platform: str = sys.platform) -> Release | None:
    """Latest release if it is newer and verifiable, otherwise None."""
    name = ASSETS.get(platform)
    if name is None:
        return None
    with _client(timeout=5.0) as c:
        r = c.get(get_settings().update_url, headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 404:  # no release published
            return None
        r.raise_for_status()
        data = r.json()
        tag = str(data.get("tag_name") or "")
        try:
            newer = is_newer(tag, current)
        except ValueError:
            log.warning("Release tag ignored: %r", tag)
            return None
        if data.get("draft") or data.get("prerelease") or not newer:
            return None
        assets = {a["name"]: a for a in data.get("assets", [])}
        asset = assets.get(name)
        if asset is None:
            log.warning("Release %s has no archive %s", tag, name)
            return None
        sha256 = _expected_sha256(c, asset, assets.get(CHECKSUMS))
        if sha256 is None:
            log.warning("Release %s has no checksum: update skipped", tag)
            return None
        return Release(
            version=tag.removeprefix("v").removeprefix("V"),
            asset=name,
            url=str(asset["browser_download_url"]),
            size=int(asset.get("size") or 0),
            sha256=sha256,
        )


def _expected_sha256(
    c: httpx.Client, asset: dict[str, Any], sums: dict[str, Any] | None
) -> str | None:
    # GitHub computes the digest of files attached to a release itself.
    digest = str(asset.get("digest") or "")
    if digest.startswith("sha256:"):
        return digest.removeprefix("sha256:").lower()
    if sums is None:
        return None
    r = c.get(str(sums["browser_download_url"]))
    r.raise_for_status()
    for line in r.text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == asset["name"]:
            return parts[0].lower()
    return None


def download(release: Release, dest: Path, progress: Progress | None = None) -> Path:
    archive = dest / release.asset
    sha = hashlib.sha256()
    done = 0
    with (
        _client(timeout=httpx.Timeout(10.0, read=60.0)) as c,
        c.stream("GET", release.url) as r,
        archive.open("wb") as f,
    ):
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or release.size or 0)
        for chunk in r.iter_bytes(1 << 20):
            f.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if sha.hexdigest() != release.sha256:
        archive.unlink()
        raise UpdateError("Corrupted archive: checksum mismatch")
    return archive


def extract(archive: Path, into: Path, platform: str = sys.platform) -> Path:
    """Extracts the archive and returns the application folder it contains."""
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive) as tar:
            tar.extractall(into, filter="data")
    elif platform == "darwin":
        # ditto keeps the symlinks and permissions of the .app bundle, zipfile does not.
        subprocess.run(["ditto", "-x", "-k", str(archive), str(into)], check=True)
    else:
        with zipfile.ZipFile(archive) as z:
            z.extractall(into)
    roots = [p for p in into.iterdir() if p.is_dir()]
    if len(roots) != 1 or not executable(roots[0], platform).is_file():
        raise UpdateError("Unexpected archive: application not found")
    return roots[0]


def prepare(
    root: Path, release: Release, progress: Progress | None = None, platform: str = sys.platform
) -> Path:
    """Downloads and extracts the new version next to the installation."""
    staging = staging_dir(root)
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    archive = download(release, staging, progress)
    new_root = extract(archive, staging, platform)
    archive.unlink()
    return new_root


# --- Installation --------------------------------------------------------------------------


def swap(root: Path, new_root: Path) -> None:
    """Linux, macOS: replaces the installation while the old version is still running."""
    backup = backup_dir(root)
    shutil.rmtree(backup, ignore_errors=True)
    root.rename(backup)
    try:
        new_root.rename(root)
    except OSError:
        backup.rename(root)
        raise


def finish(root: Path, new_root: Path, timeout: float = 60.0) -> None:
    """Windows: the new version, started from the update folder, takes the place of the old
    one as soon as it has closed."""
    if new_root.resolve().parent != staging_dir(root).resolve():
        raise UpdateError(f"Unexpected update location: {new_root}")
    backup = backup_dir(root)
    shutil.rmtree(backup, ignore_errors=True)
    deadline = time.monotonic() + timeout
    while root.exists():
        try:
            root.rename(backup)
        except OSError:
            # Files still locked: the old version has not finished closing.
            if time.monotonic() > deadline:
                raise UpdateError("The old version of Binder is still open") from None
            time.sleep(0.5)
    try:
        shutil.copytree(new_root, root)
    except OSError:
        shutil.rmtree(root, ignore_errors=True)
        backup.rename(root)
        raise


def cleanup(root: Path, attempts: int = 30, delay: float = 1.0) -> None:
    """Removes the leftovers of an update (old version, download folder).

    On Windows, the process that just installed the update may take a few seconds to close:
    retry.
    """
    for _ in range(attempts):
        leftovers = [d for d in (backup_dir(root), staging_dir(root)) if d.exists()]
        if not leftovers:
            return
        for d in leftovers:
            shutil.rmtree(d, ignore_errors=True)
        time.sleep(delay)


def launch(root: Path, *args: str, platform: str = sys.platform) -> None:
    """Starts the application installed in `root`, independently of the current process."""
    env = dict(os.environ)
    # The launched process is a full PyInstaller application, not a child.
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if platform == "darwin" and not args:
        cmd = ["open", "-n", str(root)]
    else:
        cmd = [str(executable(root, platform)), *args]
    options: dict[str, Any] = {}
    if platform == "win32":
        options["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        options["start_new_session"] = True
    subprocess.Popen(cmd, env=env, cwd=root.parent, close_fds=True, **options)


def install(root: Path, new_root: Path, platform: str = sys.platform) -> None:
    """Installs the prepared version and starts it. The caller must then exit."""
    if platform == "win32":
        launch(new_root, "--finish-update", str(root), platform=platform)
    else:
        swap(root, new_root)
        launch(root, platform=platform)
