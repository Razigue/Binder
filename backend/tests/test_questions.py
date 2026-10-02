"""Questions: only what changes something today, grouped, a few at a time."""

import json
from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from binder.db import get_engine
from binder.models import Category, DocType, Document, DocumentStatus
from binder.samples import Sample
from binder.services import questions, relevance
from tests.conftest import upload

TODAY = date.today()


def make(session: Session, n: int, **fields: Any) -> Document:
    values: dict[str, Any] = {
        "filename": f"doc-{n}.pdf",
        "mime_type": "application/pdf",
        "size": 1,
        "sha256": f"sha-{n}",
        "stored_name": f"{n}.bin",
        "title": f"Document {n}",
        "status": DocumentStatus.TO_REVIEW,
        "text": "Facture\nMontant 12,00 €",
        "confidence": 0.9,
        **fields,
    }
    if "missing" in values:
        values["missing_fields"] = json.dumps(values.pop("missing"))
    doc = Document(**values)
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def feed_items(client: TestClient) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = client.get("/api/feed").json()["items"]
    return items


def test_old_documents_are_never_asked_about(client: TestClient) -> None:
    with Session(get_engine()) as session:
        old = make(
            session,
            1,
            category=Category.OTHER,
            issue_date=TODAY - timedelta(days=relevance.OLD_AFTER_DAYS + 30),
        )
        stale = make(
            session,
            2,
            category=Category.ENERGY,
            issuer="EDF",
            due_date=TODAY - timedelta(days=relevance.STALE_DUE_DAYS + 10),
            missing=["amount"],
        )
        replaced = make(session, 3, category=Category.OTHER, superseded_by=old.id)
        for doc in (old, stale, replaced):
            assert relevance.is_old(doc, TODAY)
            assert questions.question_for(session, doc) is None
        assert questions.pending(session) == []


def test_old_document_imported_is_filed_without_a_question(client: TestClient) -> None:
    html = """<h1>Facture</h1><p>Plomberie Martin</p><p>Date de facture : 12/03/2021</p>
    <p>Intervention à domicile</p>"""
    doc = upload(client, Sample("vieille-facture.pdf", html, {}))
    assert doc["status"] == "classified"
    assert not any(i["kind"] == "question" for i in feed_items(client))


def test_a_field_without_effect_is_not_asked(client: TestClient) -> None:
    with Session(get_engine()) as session:
        # A bill of eight months ago with no amount: nothing to pay or follow any more.
        quiet = make(
            session,
            1,
            category=Category.ENERGY,
            issuer="EDF",
            issue_date=TODAY - timedelta(days=240),
            missing=["amount"],
        )
        assert relevance.worth_asking(quiet, TODAY) == []
        assert questions.question_for(session, quiet) is None
        # The same bill due next week: its amount matters.
        due = make(
            session,
            2,
            category=Category.ENERGY,
            issuer="EDF",
            issue_date=TODAY - timedelta(days=240),
            due_date=TODAY + timedelta(days=7),
            missing=["amount"],
        )
        assert relevance.worth_asking(due, TODAY) == ["amount"]
        # An identity card in force without its end date: asked; no issue date: never asked.
        card = make(
            session,
            3,
            category=Category.IDENTITY,
            doc_type=DocType.IDENTITY_CARD,
            missing=["expiry_date", "issue_date"],
        )
        assert relevance.worth_asking(card, TODAY) == ["expiry_date"]


def test_a_document_not_worth_a_question_is_filed_as_it_is(client: TestClient) -> None:
    html = """<h1>Facture</h1><p>EDF</p><p>Date de facture : 02/01/2026</p>
    <p>Électricité, consommation du trimestre</p>"""
    doc = upload(client, Sample("edf-sans-montant.pdf", html, {}))
    assert doc["status"] == "classified"
    # Shown as not filled in, nothing asked.
    assert "amount" in doc["missing_fields"]


def test_same_question_about_one_sender_is_one_card(client: TestClient) -> None:
    with Session(get_engine()) as session:
        # Where the other documents of this sender already are.
        make(
            session,
            0,
            category=Category.HOUSING,
            area="housing",
            issuer="Free",
            status=DocumentStatus.CLASSIFIED,
        )
        unknown = [make(session, n, category=Category.OTHER, issuer="Free") for n in (1, 2, 3)]
        [card] = questions.pending(session)
    assert sorted(card.document_ids) == sorted(d.id for d in unknown if d.id)
    assert card.title == "These 3 documents from Free go in Housing?"

    [item] = [i for i in feed_items(client) if i["kind"] == "question"]
    yes = item["actions"][0]
    assert yes["params"] == {"document_ids": card.document_ids, "choice": "area:housing"}
    r = client.post("/api/actions", json={"type": "answer", "params": yes["params"]})
    assert r.json()["message"] == "Answer saved for 3 documents"
    for doc in unknown:
        assert client.get(f"/api/documents/{doc.id}").json()["area"] == "housing"
    # Filed in Housing, they are now asked about together (their amount), not one by one.
    keys = [i["key"] for i in feed_items(client) if i["kind"] == "question"]
    assert item["key"] not in keys and len(keys) == 1 and keys[0].startswith("group:amount")


def test_at_most_three_questions_shown(client: TestClient) -> None:
    with Session(get_engine()) as session:
        for n in range(1, 6):
            make(session, n, category=Category.OTHER, issuer=f"Sender {n}")
        make(
            session,
            9,
            category=Category.ENERGY,
            issuer="EDF",
            due_date=TODAY + timedelta(days=3),
            missing=["amount"],
        )
    items = [i for i in feed_items(client) if i["kind"] in ("question", "questions")]
    asked = [i for i in items if i["kind"] == "question"]
    assert len(asked) == questions.MAX_VISIBLE
    # The bill due in three days comes first.
    assert asked[0]["title"].startswith("What is the amount")
    [more] = [i for i in items if i["kind"] == "questions"]
    assert more["title"] == "3 more questions, whenever you like"
    assert more["actions"][0]["type"] == "triage"
    assert len(client.get("/api/questions").json()) == 6
    one = client.get("/api/questions", params={"documents": [1, 2]}).json()
    assert sorted(i["document_ids"][0] for i in one) == [1, 2]


def test_demo_import_asks_at_most_three_questions(client: TestClient) -> None:
    r = client.post("/api/demo").json()
    asked = [i for i in feed_items(client) if i["kind"] == "question"]
    assert len(asked) <= questions.MAX_VISIBLE
    report = client.get(f"/api/reports/{r['batch']}").json()
    assert sum(item["question"] is not None for item in report["items"]) <= 3
