from collections.abc import Iterator
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from binder import i18n, updater
from binder.config import get_settings
from binder.db import reset_engine
from binder.samples import Sample, build_samples
from binder.services import llm, llm_models, scan, websearch

TODAY = date(2026, 9, 30)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("BINDER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BINDER_LLM_ENABLED", "false")
    monkeypatch.setenv("BINDER_AUTO_IMPORT", "false")
    # No Ollama install, system notification or backup written by the tests themselves.
    monkeypatch.setenv("BINDER_AUTO_SETUP", "false")
    monkeypatch.setenv("BINDER_NOTIFICATIONS", "false")
    monkeypatch.setenv("BINDER_AUTO_BACKUP", "false")
    # No web search unless a test serves its own pages (test_websearch, test_lawcheck).
    monkeypatch.setenv("BINDER_WEB_SEARCH", "false")
    monkeypatch.delenv("BINDER_DB_KEY", raising=False)
    # Deterministic language whatever the machine's locale; tests switch to fr_FR when needed.
    monkeypatch.setenv("BINDER_LOCALE", "en_US")
    get_settings.cache_clear()
    i18n.system_locale.cache_clear()
    reset_engine()
    # Even when a test turns it on, nothing reaches the network.
    websearch.transport = httpx.MockTransport(lambda r: httpx.Response(503))
    yield tmp_path
    websearch.transport = None
    websearch._seen.clear()
    for name in list(llm_models._downloads):
        llm_models.cancel_download(name)
    # What a launch measured stays with that test.
    llm_models._advice = llm_models._Advice()
    # A scan's analysis would otherwise write into the next test's database.
    scan.wait_for_analysis()
    llm.transport = updater.transport = None
    llm.select(None)
    llm.set_accelerated(False)
    llm.set_owned(False)
    reset_engine()
    get_settings.cache_clear()
    i18n.system_locale.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    from binder.main import create_app

    # Only local hosts are accepted (protection against DNS rebinding).
    with TestClient(create_app(), base_url="http://127.0.0.1") as c:
        yield c


@pytest.fixture
def samples() -> list[Sample]:
    return build_samples(TODAY)


def upload(client: TestClient, sample: Sample) -> dict[str, object]:
    r = client.post(
        "/api/documents", files={"file": (sample.filename, sample.pdf(), "application/pdf")}
    )
    assert r.status_code == 201, r.text
    doc: dict[str, object] = client.get(f"/api/documents/{r.json()['id']}").json()
    return doc
