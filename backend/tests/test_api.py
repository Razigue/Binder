import json
from pathlib import Path

import pytest
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


def test_erase_all_data_requires_confirmation(client: TestClient) -> None:
    from binder.config import get_settings

    client.post("/api/demo")
    client.put("/api/preferences", json={"language": "fr"})
    files_dir = get_settings().files_dir
    assert any(files_dir.iterdir())

    assert client.delete("/api/data").status_code == 428
    assert client.get("/api/stats").json()["total_documents"] > 0

    removed = client.delete("/api/data", params={"confirm": "true"}).json()["removed"]
    assert removed > 0
    assert client.get("/api/stats").json()["total_documents"] == 0
    assert client.get("/api/deadlines").json() == []
    assert not any(files_dir.iterdir())
    # One history entry remains; the machine's settings are kept.
    assert len(client.get("/api/activity").json()) == 1
    assert client.get("/api/preferences").json()["language"] == "fr"


def _real_pdf(text: str) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), text)
    doc.set_metadata({"producer": "Scanner", "creationDate": "D:20260101000000"})
    data = bytes(doc.tobytes())
    doc.close()
    return data


def test_clear_demo_finds_older_versions_and_leftover_files(client: TestClient) -> None:
    from binder import security
    from binder.config import get_settings
    from binder.samples import build_samples

    samples = build_samples()
    # Imported by an older version: no demo batch, only the file tells it apart.
    legacy = upload(client, samples[0])
    # A real document that happens to share a demo file name stays.
    real = client.post(
        "/api/documents",
        files={"file": (samples[1].filename, _real_pdf("Mon vrai avis"), "application/pdf")},
    ).json()
    # A demo file no document points to any more.
    files_dir = get_settings().files_dir
    leftover = files_dir / "leftover.bin"
    leftover.write_bytes(security.encrypt(samples[2].pdf()))

    assert client.get("/api/demo").json() == {"documents": 1, "leftovers": 1}
    r = client.delete("/api/demo").json()
    assert r == {"removed": 1, "files": 2}  # its file and the leftover
    assert client.get(f"/api/documents/{legacy['id']}").status_code == 404
    assert client.get(f"/api/documents/{real['id']}").status_code == 200
    assert not leftover.exists()
    assert client.get("/api/demo").json() == {"documents": 0, "leftovers": 0}

    # With no demo left, it can be loaded again.
    assert client.post("/api/demo").json()["imported"] > 0


def test_erase_all_data_deletes_leftover_files(client: TestClient) -> None:
    from binder.config import get_settings

    files_dir = get_settings().files_dir
    files_dir.mkdir(parents=True, exist_ok=True)
    (files_dir / "orphan.bin").write_bytes(b"old")
    client.delete("/api/data", params={"confirm": "true"})
    assert not any(files_dir.iterdir())


def test_upload_size_limits(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from binder.api import documents

    empty = client.post("/api/documents", files={"file": ("a.pdf", b"", "application/pdf")})
    assert empty.status_code == 400
    monkeypatch.setattr(documents, "MAX_UPLOAD", 10)
    big = client.post("/api/documents", files={"file": ("a.pdf", b"x" * 11, "application/pdf")})
    assert big.status_code == 413


def test_download_names_the_file_in_ascii_and_utf8(client: TestClient) -> None:
    from binder.api import routes
    from binder.api.common import disposition

    # Kept where api/assistant.py imports it from.
    assert routes._disposition is disposition
    header = disposition("attachment", "Échéance été.pdf")
    assert header == (
        'attachment; filename="Echeance ete.pdf"; '
        "filename*=UTF-8''%C3%89ch%C3%A9ance%20%C3%A9t%C3%A9.pdf"
    )


def test_unknown_ids_answer_404(client: TestClient) -> None:
    assert client.patch("/api/deadlines/999", json={"done": True}).status_code == 404
    r = client.delete("/api/deadlines/999")
    assert (r.status_code, r.json()["detail"]) == (404, "Deadline not found")
    assert client.get("/api/journeys/999").status_code == 404
    assert (
        client.post("/api/agent/chat", json={"message": "?", "attachments": [999]}).status_code
        == 404
    )


def test_bulk_routes_are_not_taken_for_a_document_id(client: TestClient) -> None:
    r = client.post("/api/documents/bulk/reanalyze", json={"ids": [999]})
    assert r.status_code == 202
    assert r.json()["count"] == 0
