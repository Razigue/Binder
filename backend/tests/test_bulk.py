import io
import json
import zipfile

from fastapi.testclient import TestClient

from binder.samples import Sample
from tests.conftest import upload


def three(client: TestClient, samples: list[Sample]) -> list[int]:
    return [int(str(upload(client, s)["id"])) for s in samples[:3]]


def active_ids(client: TestClient) -> set[int]:
    return {d["id"] for d in client.get("/api/documents").json()}


def test_bulk_trash_is_undone_in_one_go(client: TestClient, samples: list[Sample]) -> None:
    ids = three(client, samples)
    r = client.post("/api/documents/bulk/trash", json={"ids": [*ids[:2], 9999]})
    assert r.status_code == 200
    assert r.json() == {"count": 2, "message": "2 documents moved to the trash"}
    assert active_ids(client) == {ids[2]}
    assert client.post(f"/api/undo/{r.headers['X-Undo']}").status_code == 204
    assert active_ids(client) == set(ids)


def test_bulk_update_changes_category_and_keep_forever(
    client: TestClient, samples: list[Sample]
) -> None:
    ids = three(client, samples)
    before = {i: client.get(f"/api/documents/{i}").json()["category"] for i in ids}
    r = client.post(
        "/api/documents/bulk/update", json={"ids": ids, "category": "other", "keep_forever": True}
    )
    assert r.json()["count"] == 3
    for i in ids:
        doc = client.get(f"/api/documents/{i}").json()
        assert doc["category"] == "other" and doc["keep_forever"] is True
    client.post(f"/api/undo/{r.headers['X-Undo']}")
    assert {i: client.get(f"/api/documents/{i}").json()["category"] for i in ids} == before


def test_bulk_validate_empties_review_queue(client: TestClient, samples: list[Sample]) -> None:
    ids = three(client, samples)
    client.post("/api/documents/bulk/update", json={"ids": ids, "validated": True})
    statuses = {client.get(f"/api/documents/{i}").json()["status"] for i in ids}
    assert statuses == {"classified"}


def test_bulk_reanalyze_reads_documents_again(client: TestClient, samples: list[Sample]) -> None:
    ids = three(client, samples)
    r = client.post("/api/documents/bulk/reanalyze", json={"ids": ids})
    assert r.status_code == 202 and r.json()["count"] == 3
    # Background tasks run before the test client returns.
    assert all(client.get(f"/api/documents/{i}").json()["status"] != "processing" for i in ids)


def test_bulk_restore_and_purge_from_trash(client: TestClient, samples: list[Sample]) -> None:
    ids = three(client, samples)
    client.post("/api/documents/bulk/trash", json={"ids": ids})
    # Only documents in the trash can be restored or purged.
    r = client.post("/api/trash/restore", json={"ids": ids[:1]})
    assert r.json()["count"] == 1 and active_ids(client) == {ids[0]}
    assert client.post("/api/trash/purge", json={"ids": ids}).status_code == 428
    r = client.post("/api/trash/purge", json={"ids": ids, "confirm": True})
    assert r.json()["count"] == 2
    assert client.get("/api/trash").json() == []
    assert active_ids(client) == {ids[0]}


def test_empty_selection_is_refused(client: TestClient) -> None:
    assert client.post("/api/documents/bulk/trash", json={"ids": []}).status_code == 422


def test_export_only_selected_documents(client: TestClient, samples: list[Sample]) -> None:
    ids = three(client, samples)
    r = client.get("/api/export", params={"ids": ids[:2]})
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        index = json.loads(archive.read("index.json"))
    assert {d["id"] for d in index} == set(ids[:2])
