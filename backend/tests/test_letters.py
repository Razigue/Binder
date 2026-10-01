import re

from fastapi.testclient import TestClient

from binder.samples import Sample
from tests.conftest import upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


def anonymous(sample: Sample) -> Sample:
    """The sample without its holder's name and address: no sender can be found."""
    html = re.sub(r"<p>(?:Titulaire|Souscripteur|Logement)[^<]*</p>", "", sample.html)
    return Sample(sample.filename, html, sample.expected)


def set_locale(client: TestClient, language: str, country: str) -> None:
    r = client.put(
        "/api/preferences", json={"language": language, "country": country, "theme": "system"}
    )
    assert r.status_code == 200, r.text


def test_cancellation_letter_uses_document_and_profile(
    client: TestClient, samples: list[Sample]
) -> None:
    client.put(
        "/api/profile",
        json={
            "name": "Camille Martin",
            "address": "12 rue des Tilleuls\n69003 Lyon",
            "city": "Lyon",
        },
    )
    doc = upload(client, by_name(samples, "maif-echeance.pdf"))
    letter = client.post(
        "/api/letters", json={"kind": "termination", "document_id": doc["id"]}
    ).json()
    assert letter["recipient"] == "MAIF"
    assert letter["registered"] is True
    assert letter["language"] == "en"
    body = letter["body"]
    assert body.startswith("Camille Martin\n12 rue des Tilleuls\n69003 Lyon")
    assert "Reference: 4521877 H" in body
    assert "Dear Sir or Madam," in body
    assert "Sent by registered mail with acknowledgement of receipt" in body
    # French insurance law is only cited in letters to France.
    assert "L113-15-2" not in body
    log = client.get("/api/activity", params={"document_id": doc["id"]}).json()
    assert log[0]["action"] == "letter"


def test_letter_to_france_is_in_french_whatever_the_interface_language(
    client: TestClient, samples: list[Sample]
) -> None:
    set_locale(client, "en", "FR")
    doc = upload(client, anonymous(by_name(samples, "maif-echeance.pdf")))
    letter = client.post(
        "/api/letters", json={"kind": "termination", "document_id": doc["id"]}
    ).json()
    assert letter["language"] == "fr"
    body = letter["body"]
    assert body.startswith("[Prénom Nom]")
    assert "Référence : 4521877 H" in body
    assert "Madame, Monsieur," in body
    assert "L113-15-2" in body  # home insurance: termination at any time after one year
    assert "Lettre recommandée avec accusé de réception" in body
    # Kind titles follow the interface language.
    kinds = client.get("/api/letters/kinds").json()
    assert kinds["termination"] == "Termination of a contract or subscription"


def test_letter_to_united_kingdom_is_in_english(client: TestClient, samples: list[Sample]) -> None:
    set_locale(client, "en", "GB")
    doc = upload(client, by_name(samples, "facture-edf.pdf"))
    letter = client.post(
        "/api/letters", json={"kind": "complaint", "document_id": doc["id"]}
    ).json()
    assert letter["language"] == "en"
    assert "for an amount of £94.37" in letter["body"]
    assert "Yours faithfully," in letter["body"]


def test_telecom_cancellation_has_no_insurance_clause(
    client: TestClient, samples: list[Sample]
) -> None:
    set_locale(client, "fr", "FR")
    doc = upload(client, by_name(samples, "facture-orange.pdf"))
    body = client.post(
        "/api/letters", json={"kind": "termination", "document_id": doc["id"]}
    ).json()["body"]
    assert "résilier mon abonnement" in body
    assert "L113-15-2" not in body


def test_complaint_without_profile_keeps_placeholders(
    client: TestClient, samples: list[Sample]
) -> None:
    doc = upload(client, anonymous(by_name(samples, "facture-edf.pdf")))
    letter = client.post(
        "/api/letters",
        json={
            "kind": "complaint",
            "document_id": doc["id"],
            "details": "Wrong meter reading.",
        },
    ).json()
    assert letter["body"].startswith("[First and last name]")
    assert "for an amount of $94.37" in letter["body"]
    assert "Wrong meter reading." in letter["body"]
    assert letter["registered"] is False


def test_unknown_letter_kind(client: TestClient) -> None:
    assert client.post("/api/letters", json={"kind": "threat"}).status_code == 400
    assert set(client.get("/api/letters/kinds").json()) == {
        "termination",
        "complaint",
        "request",
        "payment_plan",
        "appeal",
        "formal_notice",
        "address_change",
    }
