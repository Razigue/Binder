from fastapi.testclient import TestClient

from binder.samples import Sample
from tests.conftest import upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


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
        "/api/letters", json={"kind": "resiliation", "document_id": doc["id"]}
    ).json()
    assert letter["recipient"] == "MAIF"
    assert letter["registered"] is True
    body = letter["body"]
    assert body.startswith("Camille Martin\n12 rue des Tilleuls\n69003 Lyon")
    assert "Référence : 4521877 H" in body
    assert "L113-15-2" in body  # assurance habitation : résiliation à tout moment après un an
    assert "Lettre recommandée avec accusé de réception" in body
    log = client.get("/api/activity", params={"document_id": doc["id"]}).json()
    assert log[0]["action"] == "letter"


def test_telecom_cancellation_has_no_insurance_clause(
    client: TestClient, samples: list[Sample]
) -> None:
    doc = upload(client, by_name(samples, "facture-orange.pdf"))
    body = client.post(
        "/api/letters", json={"kind": "resiliation", "document_id": doc["id"]}
    ).json()["body"]
    assert "résilier mon abonnement" in body
    assert "L113-15-2" not in body


def test_complaint_without_profile_keeps_placeholders(
    client: TestClient, samples: list[Sample]
) -> None:
    doc = upload(client, by_name(samples, "facture-edf.pdf"))
    letter = client.post(
        "/api/letters",
        json={
            "kind": "reclamation",
            "document_id": doc["id"],
            "details": "Relevé de compteur erroné.",
        },
    ).json()
    assert letter["body"].startswith("[Prénom Nom]")
    assert "d'un montant de 94,37 €" in letter["body"]
    assert "Relevé de compteur erroné." in letter["body"]
    assert letter["registered"] is False


def test_unknown_letter_kind(client: TestClient) -> None:
    assert client.post("/api/letters", json={"kind": "menace"}).status_code == 400
    assert set(client.get("/api/letters/kinds").json()) == {"resiliation", "reclamation", "demande"}
