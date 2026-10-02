"""Archives: old documents leave the active views, nothing is deleted."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from binder import i18n
from binder.db import get_engine, reset_engine
from binder.samples import Sample, build_samples
from tests.conftest import TODAY, upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


def _ids(rows: list[dict[str, object]]) -> list[object]:
    return [r["id"] for r in rows]


def _cards(client: TestClient) -> list[dict[str, object]]:
    """Feed cards, without the import reports (they list every document of a batch)."""
    return [i for i in client.get("/api/feed").json()["items"] if i["kind"] != "report"]


def _make_old(client: TestClient, doc: dict[str, object]) -> None:
    long_ago = (date.today() - timedelta(days=800)).isoformat()
    client.patch(f"/api/documents/{doc['id']}", json={"issue_date": long_ago})


def test_old_documents_are_suggested_then_archived_never_deleted(
    client: TestClient, samples: list[Sample]
) -> None:
    phone = upload(client, by_name(samples, "facture-orange.pdf"))
    slip = upload(client, by_name(samples, "bulletin-paie.pdf"))
    assert client.get("/api/retention").json() == []
    for doc in (phone, slip):
        _make_old(client, doc)
    [suggested] = client.get("/api/retention").json()
    assert suggested["id"] == phone["id"]
    assert suggested["archivable_reason"] == "Retention period exceeded (1 year)"

    # The feed suggests it; the user confirms.
    [card] = [i for i in client.get("/api/feed").json()["items"] if i["key"].startswith("sort:")]
    assert card["title"] == "1 old document can go to the archives"
    action = card["actions"][0]
    assert action["type"] == "archive_many"
    r = client.post("/api/actions", json={"type": action["type"], "params": action["params"]})
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "1 document archived"

    archived = client.get(f"/api/documents/{phone['id']}").json()
    assert archived["archived_at"] is not None
    assert archived["archive_reason"] == "retention"
    assert client.get("/api/trash").json() == []
    assert phone["id"] not in _ids(client.get("/api/documents").json())
    assert _ids(client.get("/api/documents", params={"archived": True}).json()) == [phone["id"]]
    log = client.get("/api/activity", params={"document_id": phone["id"]}).json()
    assert log[0]["summary"].endswith("archived (retention period over)")
    with i18n.using("fr"):
        log = client.get("/api/activity", params={"document_id": phone["id"]}).json()
    assert log[0]["summary"].endswith("archivé (durée de conservation dépassée)")
    # Only what really can be archived is.
    r = client.post("/api/retention/archive", json={"ids": [slip["id"]]}).json()
    assert r["count"] == 0


def test_restore_and_undo(client: TestClient, samples: list[Sample]) -> None:
    edf = upload(client, by_name(samples, "facture-edf.pdf"))
    r = client.post(f"/api/documents/{edf['id']}/archive")
    assert r.status_code == 200
    assert r.json()["archive_reason"] == "user"
    token = r.headers["X-Undo"]
    assert client.post(f"/api/undo/{token}").status_code == 204
    assert client.get(f"/api/documents/{edf['id']}").json()["archived_at"] is None

    client.post("/api/documents/bulk/archive", json={"ids": [edf["id"]]})
    r = client.post("/api/archives/restore", json={"ids": [edf["id"]]})
    assert r.json()["message"] == "1 document back from the archives"
    assert edf["id"] in _ids(client.get("/api/documents").json())
    assert client.get("/api/documents", params={"archived": True}).json() == []


def test_archived_documents_leave_every_active_view(
    client: TestClient, samples: list[Sample]
) -> None:
    tax = upload(client, by_name(samples, "avis-imposition.pdf"))
    card = upload(client, by_name(samples, "carte-identite.pdf"))
    feed = _cards(client)
    assert any(tax["id"] in i["document_ids"] for i in feed)
    for doc in (tax, card):
        client.post(f"/api/documents/{doc['id']}/archive")

    feed = _cards(client)
    assert not any({tax["id"], card["id"]} & set(i["document_ids"]) for i in feed)
    assert client.get("/api/deadlines", params={"start": "2000-01-01"}).json() == []
    assert client.get("/api/expirations").json() == []
    assert client.get("/api/stats").json()["total_documents"] == 0
    assert client.get("/api/stats").json()["archived"] == 2
    used = {
        i for f in client.get("/api/folders").json() for p in f["pieces"] for i in p["document_ids"]
    }
    assert tax["id"] not in used and card["id"] not in used
    # Still readable, downloadable and searchable in the archives.
    assert client.get(f"/api/documents/{tax['id']}").status_code == 200
    assert client.get(f"/api/documents/{tax['id']}/file").status_code == 200
    assert client.get("/api/documents", params={"q": "impot"}).json() == []
    found = client.get("/api/documents", params={"q": "impot", "archived": True}).json()
    assert _ids(found) == [tax["id"]]
    # Restoring brings its deadline back.
    client.post(f"/api/documents/{tax['id']}/unarchive")
    deadlines = client.get("/api/deadlines", params={"start": "2000-01-01"}).json()
    assert [d["document_id"] for d in deadlines] == [tax["id"]]


def test_document_imported_past_its_period_is_archived_at_once(client: TestClient) -> None:
    old = by_name(build_samples(TODAY - timedelta(days=800)), "facture-orange.pdf")
    doc = upload(client, old)
    assert doc["archive_reason"] == "retention"
    assert doc["status"] != "processing"
    batch = doc["batch"]
    report = client.get(f"/api/reports/{batch}").json()
    assert "1 old document archived" in report["summary"]
    # No question, no card: it is just kept.
    assert not any(doc["id"] in i["document_ids"] for i in _cards(client))
    # Taken back out of the archives, a new reading does not archive it again.
    client.post(f"/api/documents/{doc['id']}/unarchive")
    again = client.post(f"/api/documents/{doc['id']}/reanalyze").json()
    assert again["archived_at"] is None


def test_agent_archives_and_restores(client: TestClient, samples: list[Sample]) -> None:
    from binder.agent import tools
    from binder.db import get_session

    phone = upload(client, by_name(samples, "facture-orange.pdf"))
    _make_old(client, phone)
    session = next(get_session())
    listed = tools.call(session, "list", {"kind": "to_archive"}).payload
    assert [d["id"] for d in listed["can_be_archived"]] == [phone["id"]]
    result = tools.call(session, "archive_documents", {"document_ids": [phone["id"]]})
    assert result.changed and result.payload["archived"][0]["id"] == phone["id"]
    session.commit()
    found = tools.call(session, "search_documents", {"query": "orange"}).payload
    assert found["total"] == 0
    found = tools.call(session, "search_documents", {"query": "orange", "archived": True}).payload
    assert found["results"][0]["archived"] is True
    result = tools.call(session, "unarchive_documents", {"document_ids": [phone["id"]]})
    assert result.payload["restored"][0]["id"] == phone["id"]
    session.commit()
    session.close()
    assert phone["id"] in _ids(client.get("/api/documents").json())


def test_migration_adds_the_archive_columns(client: TestClient, samples: list[Sample]) -> None:
    upload(client, samples[0])
    with get_engine().begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_document_archived_at"))
        conn.execute(text("ALTER TABLE document DROP COLUMN archived_at"))
        conn.execute(text("ALTER TABLE document DROP COLUMN archive_reason"))
    reset_engine()
    with get_engine().connect() as conn:
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(document)"))]
        assert {"archived_at", "archive_reason"} <= set(columns)
        assert columns[-2:] == ["explanation", "text"]
    assert len(client.get("/api/documents").json()) == 1
