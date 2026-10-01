"""Installer commands must use options supported by each platform's Velopack CLI."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    ("platform", "machine", "runtime", "no_portable"),
    [
        ("linux", "x86_64", "linux-x64", False),
        ("linux", "aarch64", "linux-arm64", False),
        ("win32", "AMD64", "win-x64", True),
        ("darwin", "arm64", "osx-arm64", True),
    ],
)
def test_installer_platform_options(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    machine: str,
    runtime: str,
    no_portable: bool,
) -> None:
    script = Path(__file__).resolve().parents[2] / "packaging" / "build.py"
    spec = importlib.util.spec_from_file_location("binder_packaging_build", script)
    assert spec is not None and spec.loader is not None
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    commands: list[tuple[str, ...]] = []

    def capture(*args: str, cwd: Path) -> None:
        commands.append(args)

    monkeypatch.setattr(build, "run", capture)
    monkeypatch.setattr(build, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(build.platform, "machine", lambda: machine)
    monkeypatch.delenv("RELEASE_NOTES", raising=False)
    build.installer("0.3.1")

    command = commands[-1]
    assert command[:2] == ("vpk", "pack")
    assert ("--noPortable" in command) is no_portable
    assert command[command.index("--runtime") + 1] == runtime
    assert command[command.index("--packVersion") + 1] == "0.3.1"
    if platform == "linux":
        assert command[command.index("--icon") + 1].endswith("binder.png")
