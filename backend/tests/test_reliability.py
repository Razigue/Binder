from fastapi.testclient import TestClient
from sqlalchemy import text

from binder import i18n
from binder.db import get_engine, reset_engine
from binder.samples import Sample
from tests.conftest import upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


def test_delete_goes_to_trash_then_restore(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, by_name(samples, "avis-imposition.pdf"))
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204

    assert client.get(f"/api/documents/{doc['id']}").status_code == 404
    assert client.get("/api/documents").json() == []
    assert client.get("/api/documents", params={"q": "impot"}).json() == []
    assert client.get("/api/deadlines").json() == []
    assert client.get("/api/stats").json()["trashed"] == 1
    assert [d["id"] for d in client.get("/api/trash").json()] == [doc["id"]]

    r = client.post(f"/api/documents/{doc['id']}/restore")
    assert r.status_code == 200
    assert client.get("/api/documents", params={"q": "impot"}).json()[0]["id"] == doc["id"]
    assert [d["document_id"] for d in client.get("/api/deadlines").json()] == [doc["id"]]


def test_purge_requires_trash_and_confirmation(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, samples[0])
    url = f"/api/documents/{doc['id']}/purge"
    assert client.delete(url, params={"confirm": True}).status_code == 409
    client.delete(f"/api/documents/{doc['id']}")
    assert client.delete(url).status_code == 428
    assert client.delete(url, params={"confirm": True}).status_code == 204
    assert client.get("/api/trash").json() == []
    assert client.get(f"/api/documents/{doc['id']}/file").status_code == 404


def test_reimporting_a_trashed_document_restores_it(
    client: TestClient, samples: list[Sample]
) -> None:
    doc = upload(client, samples[0])
    client.delete(f"/api/documents/{doc['id']}")
    again = upload(client, samples[0])
    assert again["id"] == doc["id"]
    assert again["deleted_at"] is None


def test_activity_log_is_readable(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, by_name(samples, "facture-edf-juillet.pdf"))
    client.patch(f"/api/documents/{doc['id']}", json={"due_date": "2026-10-20", "validated": True})
    upload(client, by_name(samples, "facture-edf-juillet.pdf"))
    client.delete(f"/api/documents/{doc['id']}")

    entries = client.get("/api/activity", params={"document_id": doc["id"]}).json()
    actions = [e["action"] for e in reversed(entries)]
    assert actions == ["import", "analyze", "update", "validate", "duplicate", "trash"]
    summaries = [e["summary"] for e in entries]
    assert any("set aside for review (missing due date)" in s for s in summaries)
    assert any("due date: — → 20 Oct 2026" in s for s in summaries)
    update = next(e for e in entries if e["action"] == "update")
    assert update["actor"] == "user"
    assert update["details"]["due_date"]["new"] == "2026-10-20"

    # Stored as messages: the same log reads in French once the language changes.
    with i18n.using("fr"):
        summaries = [e["summary"] for e in client.get("/api/activity").json()]
    assert any("mis de côté pour vérification (manque l'échéance)" in s for s in summaries)
    assert any("l'échéance : — → 20/10/2026" in s for s in summaries)


def test_agent_reminder_is_logged(client: TestClient) -> None:
    client.post(
        "/api/agent/chat", json={"message": "Rappelle-moi de payer la cantine le 12/11/2026"}
    )
    entry = client.get("/api/activity").json()[0]
    assert entry["actor"] == "agent"
    assert "12 Nov 2026" in entry["summary"]


def test_migration_adds_missing_columns(client: TestClient, samples: list[Sample]) -> None:
    upload(client, samples[0])
    engine = get_engine()
    # Database from a previous version: no deleted_at column and no activity log.
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_document_deleted_at"))
        conn.execute(text("ALTER TABLE document DROP COLUMN deleted_at"))
        conn.execute(text("DROP TABLE activity"))
    reset_engine()
    engine = get_engine()
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(document)"))}
        assert "deleted_at" in columns
        assert conn.execute(text("SELECT deleted_at FROM document")).scalar() is None
    assert len(client.get("/api/documents").json()) == 1


def _document_columns() -> list[str]:
    with get_engine().connect() as conn:
        return [row[1] for row in conn.execute(text("PRAGMA table_info(document)"))]


def test_large_columns_are_moved_last(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, by_name(samples, "avis-imposition.pdf"))
    assert _document_columns()[-2:] == ["explanation", "text"]
    # Previous layout: a column stored after the text (here re-added by the migration).
    with get_engine().begin() as conn:
        conn.execute(text("ALTER TABLE document DROP COLUMN page_count"))
    reset_engine()
    assert _document_columns()[-2:] == ["explanation", "text"]

    detail = client.get(f"/api/documents/{doc['id']}").json()
    assert detail["title"] == doc["title"] and detail["text"] == doc["text"]
    assert [d["document_id"] for d in client.get("/api/deadlines").json()] == [doc["id"]]
    assert client.get("/api/documents", params={"q": "impot"}).json()[0]["id"] == doc["id"]
    with get_engine().connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        indexes = {row[1] for row in conn.execute(text("PRAGMA index_list(document)"))}
    assert {"ix_document_sha256", "ix_document_deleted_at"} <= indexes
    # The unique index still rejects a second copy of the same file.
    upload(client, by_name(samples, "avis-imposition.pdf"))
    assert len(client.get("/api/documents").json()) == 1


def test_unknown_columns_prevent_the_rebuild(client: TestClient, samples: list[Sample]) -> None:
    upload(client, by_name(samples, "avis-imposition.pdf"))
    # Database written by a newer version: its column must not be lost.
    with get_engine().begin() as conn:
        conn.execute(text("ALTER TABLE document ADD COLUMN future TEXT DEFAULT 'kept'"))
    reset_engine()
    assert _document_columns()[-1] == "future"
    assert len(client.get("/api/documents").json()) == 1
