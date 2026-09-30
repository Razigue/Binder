from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from binder.config import get_settings
from binder.db import reset_engine
from binder.samples import Sample, build_samples

TODAY = date(2026, 9, 30)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("BINDER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BINDER_LLM_ENABLED", "false")
    monkeypatch.delenv("BINDER_DB_KEY", raising=False)
    get_settings.cache_clear()
    reset_engine()
    yield tmp_path
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    from binder.main import create_app

    with TestClient(create_app()) as c:
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
