"""Choice and download of local models, against a fake Ollama."""

import json
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from binder.config import get_settings
from binder.services import llm, llm_models

GB = 1_000_000_000


class FakeOllama:
    def __init__(self) -> None:
        self.models = {"qwen3:14b": 9 * GB}
        self.error: str | None = None
        # Holds the download after the first line (cancellation test).
        self.gate: threading.Event | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/tags":
            models = [{"name": n, "size": s} for n, s in self.models.items()]
            return httpx.Response(200, json={"models": models})
        body = json.loads(request.content or b"{}")
        if path == "/api/pull":
            return httpx.Response(200, content=self._pull(body["model"]))
        if path == "/api/delete":
            if self.models.pop(body["model"], None) is None:
                return httpx.Response(404, json={"error": "model not found"})
            return httpx.Response(200)
        return httpx.Response(404)

    def _pull(self, name: str) -> Iterator[bytes]:
        def line(**event: object) -> bytes:
            return json.dumps(event).encode() + b"\n"

        yield line(status="pulling manifest")
        if self.gate is not None:
            self.gate.wait(5)
        if self.error:
            yield line(error=self.error)
            return
        for done in (2 * GB, 6 * GB):
            yield line(status="pulling a1", digest="sha256:a1", total=6 * GB, completed=done)
        yield line(status="pulling b2", digest="sha256:b2", total=100, completed=100)
        yield line(status="verifying sha256 digest")
        yield line(status="writing manifest")
        self.models[name] = 6 * GB
        yield line(status="success")


@pytest.fixture
def ollama(monkeypatch: pytest.MonkeyPatch) -> FakeOllama:
    monkeypatch.setenv("BINDER_LLM_ENABLED", "true")
    get_settings.cache_clear()
    fake = FakeOllama()
    llm.transport = httpx.MockTransport(fake.handle)
    return fake


def by_name(overview: dict[str, object], name: str) -> dict[str, object]:
    models = overview["models"]
    assert isinstance(models, list)
    return next(m for m in models if m["name"] == name)


def download(client: TestClient, name: str) -> dict[str, object]:
    r = client.post(f"/api/llm/models/{name}/download")
    assert r.status_code == 202, r.text
    llm_models.wait(name)
    overview: dict[str, object] = client.get("/api/llm").json()
    return overview


def test_disabled_by_configuration(client: TestClient) -> None:
    data = client.get("/api/llm").json()
    assert data["enabled"] is False
    assert data["ollama"] is False
    # No model ships with Binder: the catalogue is offered for download.
    assert [m["name"] for m in data["models"]] == [e.name for e in llm_models.CATALOG]
    assert not any(m["installed"] for m in data["models"])


def test_ollama_not_running(client: TestClient, ollama: FakeOllama) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    llm.transport = httpx.MockTransport(refuse)
    data = client.get("/api/llm").json()
    assert data["enabled"] is True and data["ollama"] is False
    assert data["active_installed"] is False
    assert client.put("/api/llm/model", json={"name": "qwen3:14b"}).status_code == 503


def test_catalog_and_external_models(client: TestClient, ollama: FakeOllama) -> None:
    data = client.get("/api/llm").json()
    assert data["ollama"] is True
    assert data["active"] == "qwen3.5:9b" and data["active_installed"] is False
    assert by_name(data, "qwen3.5:9b")["recommended"] is True
    external = by_name(data, "qwen3:14b")
    assert external == {
        "name": "qwen3:14b",
        "label": "qwen3:14b",
        "description": "Installed outside Binder.",
        "size": 9 * GB,
        "recommended": False,
        "kind": "chat",
        "in_catalog": False,
        "installed": True,
        "download": None,
    }


def test_embedding_model_is_never_the_active_one(client: TestClient, ollama: FakeOllama) -> None:
    data = download(client, "qwen3-embedding:0.6b")
    model = by_name(data, "qwen3-embedding:0.6b")
    assert model["kind"] == "embedding" and model["installed"] is True
    # No chat model installed: the active one is unchanged, semantic search simply works.
    assert data["active"] == "qwen3.5:9b"
    assert client.put("/api/llm/model", json={"name": "qwen3-embedding:0.6b"}).status_code == 400


def test_download_then_use(client: TestClient, ollama: FakeOllama) -> None:
    data = download(client, "qwen3.5:4b")
    model = by_name(data, "qwen3.5:4b")
    assert model["installed"] is True and model["download"] is None
    # The active model (9B) is not installed: Binder switches to the one just downloaded.
    assert data["active"] == "qwen3.5:4b" and data["active_installed"] is True
    status = client.get("/api/status").json()
    assert status["llm_available"] is True and status["llm_model"] == "qwen3.5:4b"

    summaries = [e["summary"] for e in client.get("/api/activity").json()]
    assert "Model Qwen 3.5 · 4B downloaded" in summaries
    assert "Local AI model: Qwen 3.5 · 4B" in summaries


def test_download_progress(client: TestClient, ollama: FakeOllama) -> None:
    ollama.gate = threading.Event()
    client.post("/api/llm/models/qwen3.5:2b/download")
    progress = wait_phase(client, "qwen3.5:2b", "starting")
    assert progress == {"phase": "starting", "completed": 0, "total": 0, "error": None}
    # A second click does not restart the download.
    assert client.post("/api/llm/models/qwen3.5:2b/download").status_code == 202
    ollama.gate.set()
    llm_models.wait("qwen3.5:2b")
    assert by_name(client.get("/api/llm").json(), "qwen3.5:2b")["installed"] is True


def wait_phase(client: TestClient, name: str, phase: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while True:
        download = by_name(client.get("/api/llm").json(), name)["download"]
        if isinstance(download, dict) and download["phase"] == phase:
            return download
        assert time.monotonic() < deadline, download
        time.sleep(0.01)


def test_downloads_run_one_at_a_time(client: TestClient, ollama: FakeOllama) -> None:
    ollama.gate = threading.Event()
    client.post("/api/llm/models/qwen3.5:2b/download")
    wait_phase(client, "qwen3.5:2b", "starting")
    client.post("/api/llm/models/qwen3.5:4b/download")
    client.post("/api/llm/models/qwen3.5:9b/download")
    wait_phase(client, "qwen3.5:4b", "queued")
    # Cancelling a queued download removes it from the queue.
    client.delete("/api/llm/models/qwen3.5:9b/download")
    # No deletion during a download (Ollama shares layers between models).
    r = client.delete("/api/llm/models/qwen3:14b")
    assert r.status_code == 404
    ollama.models["qwen3.5:27b"] = 17 * GB
    assert client.delete("/api/llm/models/qwen3.5:27b").status_code == 409

    ollama.gate.set()
    llm_models.wait("qwen3.5:2b")
    llm_models.wait("qwen3.5:4b")
    data = client.get("/api/llm").json()
    assert by_name(data, "qwen3.5:2b")["installed"] and by_name(data, "qwen3.5:4b")["installed"]
    assert not by_name(data, "qwen3.5:9b")["installed"]
    assert client.delete("/api/llm/models/qwen3.5:27b").status_code == 204


def test_ollama_refuses_deletion(client: TestClient, ollama: FakeOllama) -> None:
    ollama.models["qwen3.5:4b"] = 3 * GB
    handle = ollama.handle

    def failing(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/delete":
            return httpx.Response(500, json={"error": "file in use"})
        return handle(request)

    llm.transport = httpx.MockTransport(failing)
    r = client.delete("/api/llm/models/qwen3.5:4b")
    assert r.status_code == 502 and "500" in r.json()["detail"]


def test_layers_are_summed() -> None:
    d = llm_models._Download(layers={"a": (2 * GB, 6 * GB), "b": (100, 100)})
    out = d.out()
    assert (out.completed, out.total) == (2 * GB + 100, 6 * GB + 100)


def test_cancel_download(client: TestClient, ollama: FakeOllama) -> None:
    ollama.gate = threading.Event()
    client.post("/api/llm/models/qwen3.5:27b/download")
    thread = llm_models._downloads["qwen3.5:27b"].thread
    assert client.delete("/api/llm/models/qwen3.5:27b/download").status_code == 204
    ollama.gate.set()
    assert thread is not None
    thread.join(5)
    model = by_name(client.get("/api/llm").json(), "qwen3.5:27b")
    assert model["download"] is None and model["installed"] is False


def test_download_error_then_retry(client: TestClient, ollama: FakeOllama) -> None:
    ollama.error = "no space left on device"
    model = by_name(download(client, "qwen3.5:9b"), "qwen3.5:9b")
    assert model["installed"] is False
    assert model["download"]["phase"] == "error"
    assert model["download"]["error"] == "no space left on device"

    ollama.error = None
    model = by_name(download(client, "qwen3.5:9b"), "qwen3.5:9b")
    assert model["installed"] is True and model["download"] is None


def test_unknown_model_is_refused(client: TestClient, ollama: FakeOllama) -> None:
    assert client.post("/api/llm/models/llama3:70b/download").status_code == 404
    assert client.delete("/api/llm/models/qwen3:14b").status_code == 404
    r = client.put("/api/llm/model", json={"name": "qwen3.5:9b"})
    assert r.status_code == 400 and "not installed" in r.json()["detail"]


def test_choice_survives_restart(ollama: FakeOllama) -> None:
    from binder.main import create_app

    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        data = client.put("/api/llm/model", json={"name": "qwen3:14b"}).json()
        assert data["active"] == "qwen3:14b" and data["active_installed"] is True
    llm.select(None)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.get("/api/status").json()["llm_model"] == "qwen3:14b"


def test_delete_active_model(client: TestClient, ollama: FakeOllama) -> None:
    download(client, "qwen3.5:2b")
    assert client.get("/api/llm").json()["active"] == "qwen3.5:2b"
    assert client.delete("/api/llm/models/qwen3.5:2b").status_code == 204
    data = client.get("/api/llm").json()
    assert by_name(data, "qwen3.5:2b")["installed"] is False
    # Back to the configured model.
    assert data["active"] == "qwen3.5:9b" and data["active_installed"] is False
    assert client.get("/api/status").json()["llm_available"] is False


def test_catalog_follows_the_language(client: TestClient, ollama: FakeOllama) -> None:
    prefs = {"language": "fr", "country": "FR", "theme": "system"}
    assert client.put("/api/preferences", json=prefs).status_code == 200
    data = client.get("/api/llm").json()
    assert by_name(data, "qwen3:14b")["description"] == "Installé hors de Binder."
    assert by_name(data, "qwen3.5:9b")["description"].startswith("Le plus fiable")
    r = client.put("/api/llm/model", json={"name": "qwen3.5:9b"})
    assert r.json()["detail"] == "Modèle non installé : qwen3.5:9b"
