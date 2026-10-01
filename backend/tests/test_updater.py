"""Automatic update: release check, verification, installation."""

import hashlib
import io
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest

from binder import updater

API = "https://api.github.com/repos/Razigue/Binder/releases/latest"
DL = "https://github.com/Razigue/Binder/releases/download/v1.3.0"


@pytest.mark.parametrize(
    ("candidate", "current", "newer"),
    [
        ("v1.3.0", "1.2.9", True),
        ("v1.10.0", "1.9.0", True),
        ("v1.2", "1.2.0", False),
        ("v1.2.0", "1.2.0", False),
        ("1.2.1", "1.2", True),
        ("v0.9.0", "1.0.0", False),
        ("v2.0.0-beta.1", "1.9.0", True),
    ],
)
def test_is_newer(candidate: str, current: str, newer: bool) -> None:
    assert updater.is_newer(candidate, current) is newer


def test_unreadable_version() -> None:
    with pytest.raises(ValueError):
        updater.parse_version("latest")


def app_archive(platform: str, version: str = "1.3.0") -> bytes:
    """Archive like those of the "Release" workflow: a Binder/ folder with the executable."""
    exe = "Binder/Binder.exe" if platform == "win32" else "Binder/Binder"
    files = {exe: b"binary", "Binder/_internal/VERSION": version.encode()}
    buf = io.BytesIO()
    if platform == "linux":
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), 0o755
                tar.addfile(info, io.BytesIO(data))
    else:
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in files.items():
                z.writestr(name, data)
    return buf.getvalue()


class FakeGitHub:
    def __init__(self, platform: str) -> None:
        self.asset = updater.ASSETS[platform]
        self.archive = app_archive(platform)
        self.sha = hashlib.sha256(self.archive).hexdigest()
        self.release: dict[str, Any] = {
            "tag_name": "v1.3.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": self.asset,
                    "size": len(self.archive),
                    "digest": f"sha256:{self.sha}",
                    "browser_download_url": f"{DL}/{self.asset}",
                }
            ],
        }
        self.checksums: str | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == API:
            assert request.headers["User-Agent"].startswith("Binder/")
            return httpx.Response(200, json=self.release)
        if url == f"{DL}/{self.asset}":
            return httpx.Response(200, content=self.archive)
        if url == f"{DL}/SHA256SUMS.txt" and self.checksums is not None:
            return httpx.Response(200, text=self.checksums)
        return httpx.Response(404)


@pytest.fixture
def github() -> FakeGitHub:
    fake = FakeGitHub("linux")
    updater.transport = httpx.MockTransport(fake.handle)
    return fake


def test_check_finds_newer_release(github: FakeGitHub) -> None:
    release = updater.check("1.2.0", platform="linux")
    assert release == updater.Release(
        version="1.3.0",
        asset="Binder-linux-x64.tar.gz",
        url=f"{DL}/Binder-linux-x64.tar.gz",
        size=len(github.archive),
        sha256=github.sha,
    )


def test_check_ignores_same_or_older_release(github: FakeGitHub) -> None:
    assert updater.check("1.3.0", platform="linux") is None
    assert updater.check("2.0.0", platform="linux") is None


@pytest.mark.parametrize("flag", ["draft", "prerelease"])
def test_check_ignores_unpublished_release(github: FakeGitHub, flag: str) -> None:
    github.release[flag] = True
    assert updater.check("1.2.0", platform="linux") is None


def test_check_without_archive_for_this_system(github: FakeGitHub) -> None:
    assert updater.check("1.2.0", platform="darwin") is None
    assert updater.check("1.2.0", platform="freebsd") is None


def test_check_without_any_release() -> None:
    updater.transport = httpx.MockTransport(lambda r: httpx.Response(404))
    assert updater.check("1.2.0", platform="linux") is None


def test_check_falls_back_on_checksums_file(github: FakeGitHub) -> None:
    del github.release["assets"][0]["digest"]
    github.release["assets"].append(
        {"name": "SHA256SUMS.txt", "size": 1, "browser_download_url": f"{DL}/SHA256SUMS.txt"}
    )
    github.checksums = f"{'0' * 64}  Binder-windows-x64.zip\n{github.sha}  {github.asset}\n"
    release = updater.check("1.2.0", platform="linux")
    assert release is not None and release.sha256 == github.sha


def test_check_refuses_unverifiable_release(github: FakeGitHub) -> None:
    del github.release["assets"][0]["digest"]
    assert updater.check("1.2.0", platform="linux") is None


def install_dir(tmp_path: Path, platform: str) -> Path:
    root = tmp_path / "apps" / "Binder"
    updater.executable(root, platform).parent.mkdir(parents=True)
    updater.executable(root, platform).write_bytes(b"old version")
    return root


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_prepare_downloads_and_extracts(tmp_path: Path, platform: str) -> None:
    fake = FakeGitHub(platform)
    updater.transport = httpx.MockTransport(fake.handle)
    root = install_dir(tmp_path, platform)
    release = updater.check("1.2.0", platform=platform)
    assert release is not None

    seen: list[tuple[int, int]] = []
    new_root = updater.prepare(root, release, lambda d, t: seen.append((d, t)), platform)
    assert new_root == updater.staging_dir(root) / "Binder"
    assert updater.executable(new_root, platform).read_bytes() == b"binary"
    assert (new_root / "_internal" / "VERSION").read_text() == "1.3.0"
    # The downloaded archive does not stay on disk.
    assert [p.name for p in updater.staging_dir(root).iterdir()] == ["Binder"]
    assert seen[-1] == (len(fake.archive), len(fake.archive))


def test_corrupted_archive_is_rejected(tmp_path: Path, github: FakeGitHub) -> None:
    root = install_dir(tmp_path, "linux")
    release = updater.check("1.2.0", platform="linux")
    assert release is not None
    github.archive = github.archive[:-1] + b"x"
    with pytest.raises(updater.UpdateError, match="checksum"):
        updater.prepare(root, release, platform="linux")
    assert not list(updater.staging_dir(root).iterdir())
    assert updater.executable(root, "linux").read_bytes() == b"old version"


def test_archive_without_application_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "Binder-windows-x64.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("other/file.txt", "?")
    into = tmp_path / "out"
    into.mkdir()
    with pytest.raises(updater.UpdateError, match="application not found"):
        updater.extract(archive, into, "win32")


@pytest.mark.skipif(sys.platform != "darwin", reason="ditto only exists on macOS")
def test_extract_app_bundle_with_ditto(tmp_path: Path) -> None:
    archive = tmp_path / "Binder-macos-arm64.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("Binder.app/Contents/MacOS/Binder", "binary")
    into = tmp_path / "out"
    into.mkdir()
    assert updater.extract(archive, into, "darwin") == into / "Binder.app"


def test_swap_keeps_old_version_aside(tmp_path: Path) -> None:
    root = install_dir(tmp_path, "linux")
    new_root = updater.staging_dir(root) / "Binder"
    updater.executable(new_root, "linux").parent.mkdir(parents=True)
    updater.executable(new_root, "linux").write_bytes(b"new version")

    updater.swap(root, new_root)
    assert updater.executable(root, "linux").read_bytes() == b"new version"
    assert (updater.backup_dir(root) / "Binder").read_bytes() == b"old version"

    updater.cleanup(root, attempts=1, delay=0)
    assert sorted(p.name for p in root.parent.iterdir()) == ["Binder"]


def test_finish_replaces_installation(tmp_path: Path) -> None:
    root = install_dir(tmp_path, "win32")
    (root / "obsolete.dll").write_bytes(b"")
    new_root = updater.staging_dir(root) / "Binder"
    updater.executable(new_root, "win32").parent.mkdir(parents=True)
    updater.executable(new_root, "win32").write_bytes(b"new version")

    updater.finish(root, new_root, timeout=1)
    assert updater.executable(root, "win32").read_bytes() == b"new version"
    assert not (root / "obsolete.dll").exists()
    # The update copy stays in place until the next launch (it is still running).
    assert new_root.is_dir()


def test_finish_refuses_unexpected_location(tmp_path: Path) -> None:
    root = install_dir(tmp_path, "win32")
    elsewhere = tmp_path / "ailleurs" / "Binder"
    elsewhere.mkdir(parents=True)
    with pytest.raises(updater.UpdateError, match="Unexpected"):
        updater.finish(root, elsewhere, timeout=1)
    assert updater.executable(root, "win32").read_bytes() == b"old version"


@pytest.fixture
def popen(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        updater.subprocess, "Popen", lambda cmd, **kw: calls.append({"cmd": cmd, **kw})
    )
    return calls


def test_install_on_windows_hands_over_to_new_version(
    tmp_path: Path, popen: list[dict[str, Any]]
) -> None:
    root = install_dir(tmp_path, "win32")
    new_root = updater.staging_dir(root) / "Binder"
    updater.install(root, new_root, platform="win32")
    [call] = popen
    assert call["cmd"] == [str(new_root / "Binder.exe"), "--finish-update", str(root)]
    assert call["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert call["creationflags"] == getattr(updater.subprocess, "DETACHED_PROCESS", 0) | getattr(
        updater.subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    # Nothing is moved while the old version is running.
    assert updater.executable(root, "win32").read_bytes() == b"old version"


def test_install_on_linux_swaps_then_restarts(tmp_path: Path, popen: list[dict[str, Any]]) -> None:
    root = install_dir(tmp_path, "linux")
    new_root = updater.staging_dir(root) / "Binder"
    updater.executable(new_root, "linux").parent.mkdir(parents=True)
    updater.executable(new_root, "linux").write_bytes(b"new version")
    updater.install(root, new_root, platform="linux")
    [call] = popen
    assert call["cmd"] == [str(root / "Binder")]
    assert call["start_new_session"] is True
    assert updater.executable(root, "linux").read_bytes() == b"new version"


def test_launch_on_macos_uses_open(tmp_path: Path, popen: list[dict[str, Any]]) -> None:
    app = tmp_path / "Binder.app"
    updater.launch(app, platform="darwin")
    assert popen[0]["cmd"] == ["open", "-n", str(app)]


def test_not_frozen_means_no_update() -> None:
    assert updater.install_root() is None
