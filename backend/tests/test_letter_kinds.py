"""Letters added for the common procedures: payment plan, appeal, formal notice, change of
address."""

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from binder.config import get_settings
from binder.samples import Sample
from binder.services import letters, llm
from tests.conftest import upload


def doc_of(client: TestClient, samples: list[Sample], name: str) -> dict[str, Any]:
    return upload(client, next(s for s in samples if s.filename == name))


def write(client: TestClient, **body: Any) -> dict[str, Any]:
    r = client.post("/api/letters", json=body)
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


@pytest.mark.parametrize(
    ("purpose", "kind"),
    [
        ("Je voudrais payer le trop-perçu en plusieurs fois", "payment_plan"),
        ("Contester l'amende pour excès de vitesse", "appeal"),
        ("Mise en demeure du propriétaire pour le dépôt de garantie", "formal_notice"),
        ("Changement d'adresse pour EDF", "address_change"),
        ("Résilier mon abonnement Orange", "termination"),
        ("Contester la facture EDF", "complaint"),
        ("Ask why the meter reading was estimated", "custom"),
    ],
)
def test_kind_guessed_from_the_request(purpose: str, kind: str) -> None:
    assert letters.guess_kind(purpose) == kind


def test_payment_plan_to_a_benefits_office(client: TestClient, samples: list[Sample]) -> None:
    claim = doc_of(client, samples, "trop-percu-caf.pdf")
    letter = write(client, kind="payment_plan", document_id=claim["id"])
    assert letter["subject"] == "Request for a payment plan" and not letter["registered"]
    assert "$423.48" in letter["body"] and "[number] monthly instalments" in letter["body"]
    # A benefits office can also write the debt off.
    assert "written off in whole or in part" in letter["body"]
    edf = doc_of(client, samples, "facture-edf.pdf")
    assert "written off" not in write(client, kind="payment_plan", document_id=edf["id"])["body"]


def test_appeal_follows_the_procedure_of_the_document(
    client: TestClient, samples: list[Sample]
) -> None:
    fine = doc_of(client, samples, "avis-contravention.pdf")
    letter = write(client, kind="appeal", document_id=fine["id"], details="I was not driving.")
    assert letter["recipient"] == "Public Prosecutor's Officer" and letter["registered"]
    assert letter["subject"] == "Request for exemption from a fine"
    assert "45-day" in letter["body"] and "I was not driving." in letter["body"]
    assert "original notice of the fine" in letter["body"]
    claim = doc_of(client, samples, "trop-percu-caf.pdf")
    letter = write(client, kind="appeal", document_id=claim["id"])
    assert letter["recipient"] == "CAF - Amicable appeals board"
    assert "within two months" in letter["body"] and letter["blanks"] >= 1
    tax = doc_of(client, samples, "avis-imposition.pdf")
    letter = write(client, kind="appeal", document_id=tax["id"])
    assert letter["subject"] == "Tax claim" and "tax relief" in letter["body"]


def test_formal_notice_for_a_deposit(client: TestClient, samples: list[Sample]) -> None:
    rent = doc_of(client, samples, "quittance-loyer.pdf")
    letter = write(
        client, kind="formal_notice", document_id=rent["id"], details="Return of my deposit"
    )
    assert letter["subject"] == "Formal notice" and letter["registered"]
    assert "return of my deposit" in letter["body"] and "article 22" in letter["body"]
    assert "fifteen days" in letter["body"]


def test_change_of_address_with_the_date(client: TestClient, samples: list[Sample]) -> None:
    edf = doc_of(client, samples, "facture-edf.pdf")
    details = letters.address_details("8 avenue Foch\n75016 Paris", None)
    letter = write(client, kind="address_change", document_id=edf["id"], details=details)
    assert "My new address is:\n8 avenue Foch\n75016 Paris" in letter["body"]
    # Only EDF's own address is left to fill in.
    assert "transfer my contract" in letter["body"] and letter["blanks"] == 1
    dated = write(
        client,
        kind="address_change",
        document_id=edf["id"],
        details="2026-11-15\n8 avenue Foch\n75016 Paris",
    )
    assert "my address changes on 15 Nov 2026" in dated["body"]


def test_the_model_writes_with_the_legal_points(
    client: TestClient, samples: list[Sample], monkeypatch: pytest.MonkeyPatch
) -> None:
    fine = doc_of(client, samples, "avis-contravention.pdf")
    edf = doc_of(client, samples, "facture-edf.pdf")
    prompts: list[str] = []

    def ollama(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": llm.model(), "size": 1}]})
        prompts.append(json.loads(request.content)["messages"][0]["content"])
        content = {
            "subject": "Contestation",
            "recipient": "ANTAI",
            "paragraphs": ["I was not driving the car that day."],
            "registered": True,
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(content)}})

    monkeypatch.setenv("BINDER_LLM_ENABLED", "true")
    get_settings.cache_clear()
    llm.forget_availability()
    llm.transport = httpx.MockTransport(ollama)
    letter = write(client, kind="appeal", document_id=fine["id"], purpose="I was not driving")
    assert "requête en exonération" in prompts[0] and "I was not driving" in prompts[0]
    assert letter["kind"] == "appeal" and letter["recipient"] == "Public Prosecutor's Officer"
    assert "I was not driving the car that day." in letter["body"]
    # A termination too: written for this contract, with the user's words, not a template.
    write(client, kind="termination", document_id=edf["id"], purpose="end it, I am moving")
    assert len(prompts) == 2
    assert "commitment period" in prompts[1] and "end it, I am moving" in prompts[1]
