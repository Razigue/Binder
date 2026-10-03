"""Conversations with the agent kept in the database: saved, listed, renamed, deleted."""

from fastapi.testclient import TestClient

from binder.samples import Sample
from tests.conftest import upload


def turn(question: str, answer: str = "Done.") -> dict[str, object]:
    return {"question": question, "attachments": [], "response": {"answer": answer}}


def test_saved_listed_newest_first_and_reloaded(client: TestClient) -> None:
    first = client.post("/api/conversations", json={"turns": [turn("What do I owe in October?")]})
    assert first.status_code == 200, first.text
    assert first.json()["title"] == "What do I owe in October?"
    second = client.post("/api/conversations", json={"turns": [turn("Rent receipts")]}).json()

    # A new answer moves the first one back to the top.
    edited = client.patch(
        f"/api/conversations/{first.json()['id']}",
        json={"turns": [turn("What do I owe in October?"), turn("And in November?")]},
    ).json()
    assert edited["turns"] == 2
    assert [c["id"] for c in client.get("/api/conversations").json()][:2] == [
        edited["id"],
        second["id"],
    ]

    loaded = client.get(f"/api/conversations/{edited['id']}").json()
    assert [t["question"] for t in loaded["messages"]] == [
        "What do I owe in October?",
        "And in November?",
    ]
    assert loaded["messages"][1]["response"] == {"answer": "Done."}


def test_title_from_the_first_question_then_renamed(client: TestClient) -> None:
    long = "Can you explain " + "the electricity bill " * 10
    row = client.post("/api/conversations", json={"turns": [turn(long)]}).json()
    assert row["title"].endswith("…") and len(row["title"]) <= 81
    assert long.startswith(row["title"][:-1])

    renamed = client.patch(f"/api/conversations/{row['id']}", json={"title": "  EDF  "}).json()
    assert renamed["title"] == "EDF"
    # An empty name brings the first question back.
    reset = client.patch(f"/api/conversations/{row['id']}", json={"title": ""}).json()
    assert reset["title"] == row["title"]

    # Questions sent from a page name their document by id, the title does not.
    cited = client.post("/api/conversations", json={"turns": [turn("Renew “ID card” [#15]?")]})
    assert cited.json()["title"] == "Renew “ID card”?"


def test_linked_to_the_document_on_screen(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, samples[0])
    row = client.post(
        "/api/conversations", json={"document_id": doc["id"], "turns": [turn("Explain it")]}
    ).json()
    assert row["document_id"] == doc["id"]
    assert row["document_title"] == doc["title"]

    client.delete(f"/api/documents/{doc['id']}")
    listed = next(c for c in client.get("/api/conversations").json() if c["id"] == row["id"])
    assert listed["document_title"] is None


def test_deleted_on_request_and_logged(client: TestClient) -> None:
    row = client.post("/api/conversations", json={"turns": [turn("Rent receipts")]}).json()
    assert client.delete(f"/api/conversations/{row['id']}").status_code == 204
    assert client.get(f"/api/conversations/{row['id']}").status_code == 404
    assert client.patch(f"/api/conversations/{row['id']}", json={"title": "x"}).status_code == 404
    assert any("Rent receipts" in e["summary"] for e in client.get("/api/activity").json())


def test_oversized_conversation_refused(client: TestClient) -> None:
    huge = [turn("x", "y" * 1_000_000) for _ in range(6)]
    assert client.post("/api/conversations", json={"turns": huge}).status_code == 413
