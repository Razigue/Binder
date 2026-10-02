"""Real documents wait for the local AI, the model gives the document type, and the new types
(warranties, family papers…) find their place: area, retention, deadlines, folders."""

import json
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from binder.config import get_settings
from binder.db import get_engine
from binder.models import Category, Deadline, DocType, Document
from binder.samples import Sample
from binder.schemas import Extraction
from binder.services import deadlines, ingest, llm, retention
from tests.conftest import upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


class Ollama:
    """Ollama as Binder sees it: the model installed or not, and its extraction."""

    def __init__(self) -> None:
        self.installed = False
        self.extraction: dict[str, Any] = {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            models = [{"name": llm.model(), "size": 1}] if self.installed else []
            return httpx.Response(200, json={"models": models})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        content = json.dumps(self.extraction)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


@pytest.fixture
def ollama(monkeypatch: pytest.MonkeyPatch) -> Iterator[Ollama]:
    fake = Ollama()
    monkeypatch.setenv("BINDER_LLM_ENABLED", "true")
    get_settings.cache_clear()
    llm.forget_availability()
    llm.transport = httpx.MockTransport(fake.handle)
    yield fake


def test_real_documents_wait_for_the_ai(
    client: TestClient, samples: list[Sample], ollama: Ollama
) -> None:
    doc = upload(client, by_name(samples, "facture-edf.pdf"))
    assert doc["status"] == "waiting" and doc["title"] == "facture-edf.pdf"
    assert doc["category"] == "other" and doc["amount"] is None
    feed = client.get("/api/feed").json()["items"]
    card = next(i for i in feed if i["kind"] == "waiting")
    assert card["title"] == "1 document is waiting for the local AI"
    report = next(i for i in feed if i["kind"] == "report")
    assert "1 waiting for the local AI" in report["detail"]
    # The demo is read by the rules, so that it runs on any machine.
    demo = client.post("/api/demo").json()
    assert demo["imported"] == len(samples)
    statuses = {d["filename"]: d["status"] for d in client.get("/api/documents").json()}
    assert statuses["quittance-loyer.pdf"] == "classified"
    assert statuses["facture-edf.pdf"] in ("waiting", "classified")

    # The model is ready: the document is read by it.
    ollama.installed = True
    llm.forget_availability()
    ollama.extraction = {
        "category": "energy",
        "doc_type": "invoice",
        "title": "EDF bill",
        "issuer": "EDF",
        "amount": 94.37,
        "issue_date": "2026-09-18",
        "due_date": "2026-10-12",
        "expiry_date": None,
        "reference": "6012 3456 78",
        "person": "Camille Martin",
        "confidence": 0.95,
    }
    with Session(get_engine()) as session:
        assert ingest.analyze_waiting(session) == 1
        assert ingest.analyze_waiting(session) == 0
    read = client.get(f"/api/documents/{doc['id']}").json()
    assert read["status"] == "classified" and read["extractor"] == "llm+rules"
    assert read["title"] == "EDF bill" and read["doc_type"] == "invoice"
    assert not [i for i in client.get("/api/feed").json()["items"] if i["kind"] == "waiting"]


def test_without_a_configured_model_the_rules_read_everything(
    client: TestClient, samples: list[Sample]
) -> None:
    doc = upload(client, by_name(samples, "facture-edf.pdf"))
    assert doc["status"] == "classified" and doc["extractor"] == "rules"


def test_the_model_gives_the_type_and_the_rules_fill_in() -> None:
    by_rules = Extraction(category=Category.TAXES, doc_type=DocType.TAX_NOTICE, confidence=0.7)
    by_llm = Extraction(category=Category.TAXES, doc_type=DocType.DONATION_RECEIPT, confidence=0.9)
    assert ingest.merge(by_rules, by_llm).doc_type == DocType.DONATION_RECEIPT
    by_llm.doc_type = None
    assert ingest.merge(by_rules, by_llm).doc_type == DocType.TAX_NOTICE


def test_unknown_type_from_the_model_is_dropped(ollama: Ollama) -> None:
    ollama.installed = True
    ollama.extraction = {"category": "energy", "doc_type": "electricity_bill", "title": "EDF"}
    result = llm.extract("Facture EDF")
    assert result is not None and result.doc_type is None
    ollama.extraction["doc_type"] = "fine"
    result = llm.extract("Avis de contravention")
    assert result is not None and result.doc_type == DocType.FINE


def test_family_area(client: TestClient, samples: list[Sample]) -> None:
    for name in ("certificat-scolarite.pdf", "attestation-garde.pdf"):
        doc = upload(client, by_name(samples, name))
        assert doc["category"] == "family" and doc["area"] == "family"
    areas = {a["area"]: a for a in client.get("/api/areas").json()}
    assert areas["family"]["label"] == "Family" and areas["family"]["documents"] == 2
    assert list(areas) == ["housing", "money", "work", "family", "health", "identity", "vehicle"]


def test_warranty_retention_and_deadline() -> None:
    today = date.today()
    with Session(get_engine()) as session:
        doc = Document(
            filename="darty.pdf",
            mime_type="application/pdf",
            size=1,
            sha256="x",
            stored_name="x",
            title="Darty invoice",
            category=Category.PURCHASES,
            doc_type=DocType.PURCHASE_RECEIPT,
            amount=499.0,
            issue_date=today - timedelta(days=300),
            expiry_date=today + timedelta(days=430),
        )
        session.add(doc)
        session.flush()
        deadlines.sync(session, doc)
        deadline = session.exec(select(Deadline)).one()
        assert deadline.title == "End of warranty: Darty invoice"
        assert deadlines.renew_from(doc) == doc.expiry_date - timedelta(days=45)
        rule = retention.rule_for(doc)
        assert rule is not None and rule.label == "As long as the warranty runs"
        assert retention.keep_until(doc) == doc.expiry_date
        assert retention.archivable_reason(doc) is None
        doc.expiry_date = today - timedelta(days=1)
        assert retention.archivable_reason(doc) == (
            "Retention period exceeded (as long as the warranty runs)"
        )


def test_new_folders(client: TestClient, samples: list[Sample]) -> None:
    card = upload(client, by_name(samples, "carte-identite.pdf"))
    upload(client, by_name(samples, "facture-edf.pdf"))
    upload(client, by_name(samples, "certificat-scolarite.pdf"))
    # An expired card still does for its renewal.
    past = (date.today() - timedelta(days=10)).isoformat()
    client.patch(f"/api/documents/{card['id']}", json={"expiry_date": past})
    renewal = client.get("/api/folders/identity_renewal").json()
    pieces = {p["key"]: p for p in renewal["pieces"]}
    assert pieces["current_identity"]["status"] == "ok"
    assert pieces["recent_address"]["status"] == "ok" and pieces["birth_certificate"]["optional"]
    assert renewal["complete"]
    school = {p["key"]: p for p in client.get("/api/folders/school").json()["pieces"]}
    assert school["child_civil_status"]["status"] == "missing"
    assert school["parent_identity"]["status"] == "outdated"
    assert school["former_school"]["status"] == "ok"
    retirement = client.post("/api/folders/prepare", json={"purpose": "demande de retraite"})
    assert retirement.json()["key"] == "retirement"
