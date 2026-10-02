"""What documents and web pages say is not the user's request: changes after reading them wait
for the user's confirmation, and law from memory is flagged."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from binder.agent import loop, tools
from binder.config import get_settings
from binder.db import get_engine
from binder.models import Document
from binder.samples import Sample
from binder.services import llm, profile
from tests.conftest import upload
from tests.test_agent import FakeModel, answer, call


@pytest.fixture
def library(client: TestClient, samples: list[Sample]) -> dict[str, int]:
    return {s.filename: int(str(upload(client, s)["id"])) for s in samples}


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeModel]:
    fake = FakeModel()
    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "has_vision", lambda: True)
    monkeypatch.setattr(llm, "chat", fake)
    yield fake


def test_trash_after_reading_waits_for_confirmation(
    client: TestClient, library: dict[str, int], model: FakeModel
) -> None:
    old = library["attestation-maif-ancienne.pdf"]
    model.replies = [
        call("read_document", document_id=library["facture-edf.pdf"]),
        call("trash_document", document_id=old),
        answer("The old MAIF certificate awaits your confirmation."),
    ]
    r = client.post("/api/agent/chat", json={"message": "Range mes papiers"}).json()
    assert not r["changed"] and r["confirmations"][0]["tool"] == "trash_document"
    assert "MAIF" in r["confirmations"][0]["description"]
    held = [m for m in model.requests[-1] if m["role"] == "tool"][-1]
    assert "Not done yet" in held["content"]
    assert client.get(f"/api/documents/{old}").json()["deleted_at"] is None
    token = r["confirmations"][0]["token"]
    done = client.post(f"/api/agent/confirm/{token}")
    assert done.status_code == 200 and done.json()["undo"]
    with Session(get_engine()) as session:
        trashed = session.get(Document, old)
        assert trashed is not None and trashed.deleted_at is not None
    # Once only.
    assert client.post(f"/api/agent/confirm/{token}").status_code == 410


def test_change_asked_without_reading_anything_is_made(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    doc_id = library["note-garage.pdf"]
    model.replies = [
        call("update_document", document_id=doc_id, category="vehicle"),
        answer("Done."),
    ]
    response = loop.run(session, f"Mets le document {doc_id} dans Véhicule", [])
    assert response.changed and not response.confirmations
    doc = session.get(Document, doc_id)
    assert doc is not None and doc.category == "vehicle"


def test_profile_after_a_web_page_waits(
    monkeypatch: pytest.MonkeyPatch, library: dict[str, int], session: Session, model: FakeModel
) -> None:
    monkeypatch.setattr(get_settings(), "web_search", True)
    model.replies = [
        call("web_search", query="délai résiliation assurance"),
        call("update_profile", address="1 rue Pirate, 75000 Paris"),
        answer("Waiting for your confirmation."),
    ]
    response = loop.run(session, "Quel délai pour résilier ?", [])
    assert response.confirmations[0]["tool"] == "update_profile"
    assert "1 rue Pirate" in response.confirmations[0]["description"]
    assert profile.load(session).address != "1 rue Pirate, 75000 Paris"


def test_attached_document_counts_as_read(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    edf = session.get(Document, library["facture-edf.pdf"])
    assert edf is not None
    model.replies = [call("update_document", document_id=edf.id, amount=1.0), answer("Ok.")]
    response = loop.run(session, "", [], attachments=[edf])
    assert response.confirmations and not response.changed
    assert "never instructions" in model.requests[0][0]["content"]


def test_document_content_is_marked_as_information(
    library: dict[str, int], session: Session
) -> None:
    read = tools.call(session, "read_document", {"document_id": library["facture-edf.pdf"]})
    assert read.payload["note"] == tools.DOCUMENT_NOTE
    found = tools.call(session, "search_documents", {"query": "EDF"})
    assert found.payload["note"] == tools.DOCUMENT_NOTE
    assert "never instructions" in llm.EXTRACTION_PROMPT


def test_law_from_memory_is_flagged_when_web_search_is_off(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    model.replies = [
        call("search_documents", query="Orange"),
        answer("The notice period is one month under the Chatel law."),
    ]
    response = loop.run(session, "Quel préavis pour résilier Orange ?", [])
    assert response.warnings == [loop.T("law_unverified")]
    model.replies = [call("search_documents", query="Orange"), answer("Your plan is €19.99.")]
    assert loop.run(session, "Mon forfait Orange ?", []).warnings == []
