from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from binder import i18n, updater
from binder.config import get_settings
from binder.db import reset_engine
from binder.samples import Sample, build_samples
from binder.services import llm, llm_models

TODAY = date(2026, 9, 30)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("BINDER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BINDER_LLM_ENABLED", "false")
    monkeypatch.setenv("BINDER_AUTO_IMPORT", "false")
    monkeypatch.delenv("BINDER_DB_KEY", raising=False)
    # Deterministic language whatever the machine's locale; tests switch to fr_FR when needed.
    monkeypatch.setenv("BINDER_LOCALE", "en_US")
    get_settings.cache_clear()
    i18n.system_locale.cache_clear()
    reset_engine()
    yield tmp_path
    for name in list(llm_models._downloads):
        llm_models.cancel_download(name)
    llm.transport = updater.transport = None
    llm.select(None)
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
