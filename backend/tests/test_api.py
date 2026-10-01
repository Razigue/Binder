import json
from pathlib import Path

from fastapi.testclient import TestClient

from binder.samples import Sample
from tests.conftest import upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


def test_upload_classifies_and_creates_deadline(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, by_name(samples, "avis-imposition.pdf"))
    assert doc["category"] == "taxes"
    assert doc["status"] == "classified"
    assert doc["amount"] == 1240.0
    deadlines = client.get("/api/deadlines").json()
    assert [d["document_id"] for d in deadlines] == [doc["id"]]


def test_duplicate_upload_returns_existing(client: TestClient, samples: list[Sample]) -> None:
    data = samples[0].pdf()
    ids = {
        client.post("/api/documents", files={"file": ("a.pdf", data, "application/pdf")}).json()[
            "id"
        ]
        for _ in range(2)
    }
    assert len(ids) == 1
    assert len(client.get("/api/documents").json()) == 1


def test_incomplete_document_goes_to_review_then_validated(
    client: TestClient, samples: list[Sample]
) -> None:
    doc = upload(client, by_name(samples, "facture-edf-juillet.pdf"))
    assert doc["status"] == "to_review"
    assert doc["missing_fields"] == ["due_date"]
    r = client.patch(f"/api/documents/{doc['id']}", json={"due_date": "2026-10-20"})
    assert r.json()["status"] == "classified"
    assert any(d["document_id"] == doc["id"] for d in client.get("/api/deadlines").json())


def test_rejects_unsupported_file(client: TestClient) -> None:
    r = client.post("/api/documents", files={"file": ("a.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415


def test_search_stats_and_delete(client: TestClient, samples: list[Sample]) -> None:
    for s in samples:
        upload(client, s)
    results = client.get("/api/documents", params={"q": "facture edf"}).json()
    assert {d["issuer"] for d in results} == {"EDF"}
    stats = client.get("/api/stats").json()
    assert stats["total_documents"] == len(samples)
    assert stats["to_review"] >= 1
    doc_id = results[0]["id"]
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_preview_file_and_export(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, samples[0])
    assert client.get(f"/api/documents/{doc['id']}/preview").headers["content-type"] == "image/png"
    assert client.get(f"/api/documents/{doc['id']}/file").content.startswith(b"%PDF")
    r = client.get("/api/export", params={"category": "taxes"})
    assert r.headers["content-type"] == "application/zip"


def test_data_is_encrypted_at_rest(
    client: TestClient, samples: list[Sample], isolated_env: Path
) -> None:
    upload(client, by_name(samples, "avis-imposition.pdf"))
    db_bytes = (isolated_env / "binder.db").read_bytes()
    assert not db_bytes.startswith(b"SQLite format 3")
    assert b"FINANCES" not in db_bytes.upper()
    for stored in (isolated_env / "files").iterdir():
        assert not stored.read_bytes().startswith(b"%PDF")


def test_agent_without_llm(client: TestClient, samples: list[Sample]) -> None:
    for s in samples:
        upload(client, s)
    r = client.post("/api/agent/chat", json={"message": "Find my EDF invoices"}).json()
    assert r["engine"] == "rules"
    assert len(r["documents"]) == 2
    r = client.post("/api/agent/chat", json={"message": "Which documents are due soon?"}).json()
    assert r["deadlines"]
    r = client.post(
        "/api/agent/chat", json={"message": "Remind me to pay the canteen on 12/11/2026"}
    ).json()
    assert r["deadlines"][0]["due_date"] == "2026-11-12"
    assert "canteen" in r["deadlines"][0]["title"]
    r = client.post("/api/agent/chat", json={"message": "Export my tax folder"}).json()
    assert "/api/export?category=taxes" in r["answer"]
    assert json.dumps(r)


def test_demo_seed_is_idempotent(client: TestClient) -> None:
    first = client.post("/api/demo").json()["imported"]
    assert first > 0
    assert client.post("/api/demo").json()["imported"] == 0
    assert client.get("/api/stats").json()["total_documents"] == first
