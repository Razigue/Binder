from pathlib import Path

import pytest

from binder import config


@pytest.mark.parametrize(
    ("platform", "env", "expected"),
    [
        ("linux", {}, Path("/home/u/.local/share/binder")),
        ("linux", {"XDG_DATA_HOME": "/data"}, Path("/data/binder")),
        ("darwin", {}, Path("/home/u/Library/Application Support/Binder")),
        ("win32", {"LOCALAPPDATA": "/appdata"}, Path("/appdata/Binder")),
        ("win32", {}, Path("/home/u/AppData/Local/Binder")),
    ],
)
def test_default_data_dir(
    monkeypatch: pytest.MonkeyPatch, platform: str, env: dict[str, str], expected: Path
) -> None:
    monkeypatch.setattr(config.sys, "platform", platform)
    monkeypatch.setattr(config.Path, "home", lambda: Path("/home/u"))
    for name in ("XDG_DATA_HOME", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert config._default_data_dir() == expected
