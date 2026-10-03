"""The best model for each machine: the memory ladder, Binder's Ollama, and the upgrades
re-evaluated at each launch (fetched in the background, never a downgrade)."""

import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from binder.db import get_engine
from binder.services import llm, llm_models, setup
from tests.test_models import FakeOllama, by_name, ollama  # noqa: F401

GB = setup.GB


@pytest.mark.parametrize(
    ("ram", "vram", "apple", "expected"),
    [
        # Processor alone.
        (8, 0, False, "qwen3.5:2b"),
        (12, 0, False, "qwen3.5:4b"),
        (16, 0, False, "qwen3.5:9b"),
        (32, 0, False, "qwen3.6:35b-a3b"),
        (64, 0, False, "qwen3.6:35b-a3b"),
        # An 8 GB graphics card: RAM and VRAM add up for the mixture of experts.
        (16, 8, False, "qwen3.5:9b"),
        (32, 8, False, "qwen3.6:35b-a3b"),
        # A 24 GB card holds the dense 27B whole.
        (32, 24, False, "qwen3.6:27b"),
        (16, 24, False, "qwen3.6:27b"),
        # Apple silicon: unified memory, RAM alone.
        (16, 0, True, "qwen3.5:9b"),
        (32, 0, True, "qwen3.6:35b-a3b"),
        (64, 0, True, "qwen3.6:27b"),
    ],
)
def test_model_suits_the_machine(ram: int, vram: int, apple: bool, expected: str) -> None:
    assert setup.pick_model(ram * GB, vram * GB, 500 * GB, apple) == expected


def test_smaller_model_when_the_disk_is_short() -> None:
    # The 35B-A3B needs ~27 GB free: the next rank down that fits.
    assert setup.pick_model(64 * GB, 0, 25 * GB) == "qwen3.5:9b"
    assert setup.pick_model(32 * GB, 24 * GB, 25 * GB) == "qwen3.6:27b"
    assert setup.pick_model(32 * GB, 24 * GB, 20 * GB) == "qwen3.5:9b"
    assert setup.pick_model(16 * GB, 0, 5 * GB) == "qwen3.5:4b"
    assert setup.pick_model(16 * GB, 0, 1 * GB) is None


def test_an_old_ollama_gets_a_model_it_runs() -> None:
    assert setup.pick_model(32 * GB, 24 * GB, 500 * GB, ollama="0.20.0") == "qwen3.5:9b"
    assert setup.pick_model(32 * GB, 24 * GB, 500 * GB, ollama="0.35.0") == "qwen3.6:27b"


def test_catalog_ranks_are_distinct_and_ordered() -> None:
    ranks = [e.rank for e in llm_models.CHAT]
    assert ranks == sorted(set(ranks)) and all(ranks)
    # Every model the ladder can name is in the catalogue.
    for ram, vram, apple in ((8, 0, False), (12, 0, False), (16, 0, False), (64, 24, True)):
        assert setup.memory_tier(ram * GB, vram * GB, apple) in llm_models.BY_NAME


class FakeProcess:
    pid = 4242

    def poll(self) -> None:
        return None


def serve_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    seen: dict[str, str] = {}

    def popen(args: list[str], env: dict[str, str], **kwargs: Any) -> FakeProcess:
        seen.update(env)
        return FakeProcess()

    monkeypatch.setattr(setup, "_state", setup._State())
    monkeypatch.setattr(setup.subprocess, "Popen", popen)
    monkeypatch.setattr(setup, "_tie", lambda process: None)
    monkeypatch.setattr(llm, "installed_models", dict)
    setup._serve(Path("ollama"))
    return seen


def test_binders_ollama_uses_flash_attention_and_a_q8_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OLLAMA_FLASH_ATTENTION", raising=False)
    monkeypatch.delenv("OLLAMA_KV_CACHE_TYPE", raising=False)
    env = serve_env(monkeypatch)
    assert env["OLLAMA_FLASH_ATTENTION"] == "1" and env["OLLAMA_KV_CACHE_TYPE"] == "q8_0"


def test_ollama_settings_of_the_user_are_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_FLASH_ATTENTION", "0")
    monkeypatch.setenv("OLLAMA_KV_CACHE_TYPE", "f16")
    env = serve_env(monkeypatch)
    assert env["OLLAMA_FLASH_ATTENTION"] == "0" and env["OLLAMA_KV_CACHE_TYPE"] == "f16"


# --- Upgrades, re-evaluated at each launch -------------------------------------------------


def launch(ram: int, vram: int = 0, apple: bool = False) -> None:
    """What setup does at each launch once Ollama runs: measure, then advise."""
    setup._advise(setup.Machine(ram * GB, vram * GB, 500 * GB, apple, "0.35.0"))


def offer(client: TestClient) -> dict[str, Any] | None:
    upgrade: dict[str, Any] | None = client.get("/api/setup").json()["upgrade"]
    return upgrade


@pytest.fixture
def chosen_by_binder(
    client: TestClient,
    ollama: FakeOllama,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> FakeOllama:
    """The 9B, picked by Binder on a 16 GB machine."""
    monkeypatch.setattr(setup, "_state", setup._State())
    ollama.models = {"qwen3.5:9b": int(6.6 * GB)}
    with Session(get_engine()) as session:
        llm_models.choose(session, "qwen3.5:9b", actor="binder")
        session.commit()
    launch(16)
    assert offer(client) is None
    return ollama


def test_better_model_is_downloaded_then_replaces_the_former_one(
    client: TestClient, chosen_by_binder: FakeOllama
) -> None:
    llm.set_owned(True)
    launch(32)
    # Binder chose the model: the better one is fetched without asking, and shown meanwhile.
    upgrade = offer(client)
    assert upgrade is None or (upgrade["name"] == "qwen3.6:35b-a3b" and upgrade["accepted"])
    llm_models.wait("qwen3.6:35b-a3b")
    data = client.get("/api/llm").json()
    assert data["active"] == "qwen3.6:35b-a3b" and data["upgrade"] is None
    # Only the model in use stays on the disk.
    assert by_name(data, "qwen3.5:9b")["installed"] is False
    summaries = [e["summary"] for e in client.get("/api/activity").json()]
    assert "Local AI upgraded: Qwen 3.5 · 9B → Qwen 3.6 · 35B-A3B" in summaries
    assert "Unused model Qwen 3.5 · 9B deleted (disk space freed)" in summaries


def test_only_the_models_in_use_stay_on_the_disk(
    client: TestClient, chosen_by_binder: FakeOllama
) -> None:
    chosen_by_binder.models |= {
        "qwen3.5:4b": GB,  # replaced earlier
        "qwen3.5:27b": GB,  # dropped from the catalogue by an update
        "qwen3-embedding:0.6b": GB,  # search by meaning
        "mistral:7b": GB,  # installed outside Binder
    }
    with Session(get_engine()) as session:
        # A shared Ollama serves other apps: nothing is deleted there.
        assert llm_models.prune(session) == []
        llm.set_owned(True)
        assert sorted(llm_models.prune(session)) == ["qwen3.5:27b", "qwen3.5:4b"]
    assert set(chosen_by_binder.models) == {"qwen3.5:9b", "qwen3-embedding:0.6b", "mistral:7b"}


def test_stopped_upgrade_comes_back_only_when_the_advice_changes(
    client: TestClient, chosen_by_binder: FakeOllama
) -> None:
    chosen_by_binder.gate = threading.Event()
    launch(32)
    # Stopped by the user while it downloads.
    assert client.post("/api/llm/upgrade/decline").status_code == 200
    chosen_by_binder.gate.set()
    llm_models.wait("qwen3.6:35b-a3b")
    assert offer(client) is None
    assert client.get("/api/llm").json()["active"] == "qwen3.5:9b"
    launch(32)  # next launch, same machine
    assert offer(client) is None
    chosen_by_binder.gate = threading.Event()
    launch(64, vram=24)  # a graphics card was added
    upgrade = offer(client)
    assert upgrade is not None and upgrade["name"] == "qwen3.6:27b" and upgrade["accepted"]
    chosen_by_binder.gate.set()
    llm_models.wait("qwen3.6:27b")


def test_weaker_machine_never_downgrades(client: TestClient, chosen_by_binder: FakeOllama) -> None:
    launch(8)
    assert offer(client) is None
    assert client.get("/api/llm").json()["active"] == "qwen3.5:9b"
    warning = setup.status().warning
    assert warning is not None and warning.startswith("Qwen 3.5 · 9B is heavier")


def test_model_chosen_by_hand_is_left_alone(
    client: TestClient, chosen_by_binder: FakeOllama
) -> None:
    assert client.put("/api/llm/model", json={"name": "qwen3.5:9b"}).status_code == 200
    launch(32)
    assert offer(client) is None
    launch(8)
    assert setup.status().warning is None
    data = client.get("/api/llm").json()
    # Only shown: the model that would suit the machine.
    assert data["automatic"] is False and data["recommended"] == "qwen3.5:2b"
    launch(32)
    data = client.get("/api/llm").json()
    assert data["recommended"] == "qwen3.6:35b-a3b"
    assert data["recommended_label"] == "Qwen 3.6 · 35B-A3B"
    assert client.post("/api/llm/upgrade").status_code == 409


def test_graphics_memory_is_read_from_ollama_for_every_vendor(tmp_path: Path) -> None:
    log = tmp_path / "ollama.log"
    start = 'level=INFO msg="server config" env="map[]"\n'
    device = (
        'level=INFO source=types.go:32 msg="inference compute" id={id} library={lib} '
        'name={lib}0 description="{name}" type={kind} total="{total}" available="1.0 GiB"\n'
    )
    log.write_text(
        start
        + device.format(id=0, lib="CUDA", name="old card", kind="discrete", total="8.0 GiB")
        + start
        + device.format(id=0, lib="ROCm", name="Radeon RX 7900", kind="discrete", total="24.0 GiB")
        + device.format(id=1, lib="Vulkan", name="Radeon 780M", kind="iGPU", total="4.0 GiB")
        + device.format(id=2, lib="cpu", name="cpu", kind="", total="64.0 GiB"),
        encoding="utf-8",
    )
    # The last start only, integrated graphics and the processor left out.
    assert setup.ollama_gpu_bytes(log) == 24 * 1024**3
    assert setup.ollama_gpu_bytes(tmp_path / "missing.log") == 0


def test_download_progress_is_read_without_asking_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "qwen3.5:2b"
    download = llm_models._Download(phase="downloading", layers={"a": (1, 4), "b": (2, 6)})
    monkeypatch.setitem(llm_models._downloads, name, download)
    state = llm_models.download_state(name)
    assert state is not None and (state.completed, state.total) == (3, 10)
    monkeypatch.delitem(llm_models._downloads, name)
    assert llm_models.download_state(name) is None
