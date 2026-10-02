from datetime import date, timedelta

from fastapi.testclient import TestClient

from binder import i18n
from binder.samples import Sample
from tests.conftest import upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


def test_identity_card_expiry_and_renewal_window(client: TestClient, samples: list[Sample]) -> None:
    card = upload(client, by_name(samples, "carte-identite.pdf"))
    assert card["category"] == "identity"
    assert card["status"] == "classified"
    expiry = date.fromisoformat(card["expiry_date"])
    # Identity card: dealt with three months ahead.
    assert card["renew_from"] == (expiry - timedelta(days=90)).isoformat()

    [item] = client.get("/api/expirations").json()
    assert item["document"]["id"] == card["id"]
    assert item["state"] == ("renew" if expiry - date.today() <= timedelta(days=90) else "valid")
    expiry_deadlines = [d for d in client.get("/api/deadlines").json() if d["source"] == "expiry"]
    assert [d["document_id"] for d in expiry_deadlines] == [card["id"]]


def test_technical_inspection_is_an_expiry_not_a_payment(
    client: TestClient, samples: list[Sample]
) -> None:
    ct = upload(client, by_name(samples, "controle-technique.pdf"))
    assert ct["category"] == "vehicle"
    assert ct["due_date"] is None
    assert ct["expiry_date"] is not None
    assert ct["issuer"] == "Autosur"


def test_identity_card_without_expiry_goes_to_review(client: TestClient) -> None:
    html = "<h1>Carte nationale d'identité</h1><p>Lieu de naissance : Lyon</p>"
    doc = upload(client, Sample("cni-floue.pdf", html, {}))
    assert doc["status"] == "to_review"
    assert doc["missing_fields"] == ["expiry_date"]


def test_superseded_document_loses_its_expiry_deadline(
    client: TestClient, samples: list[Sample]
) -> None:
    old = upload(client, by_name(samples, "attestation-maif-ancienne.pdf"))
    new = upload(client, by_name(samples, "attestation-maif.pdf"))
    ids = [
        d["document_id"]
        for d in client.get("/api/deadlines", params={"start": "2000-01-01"}).json()
    ]
    assert new["id"] in ids
    assert old["id"] not in ids
    assert [e["document"]["id"] for e in client.get("/api/expirations").json()] == [new["id"]]


def test_retention_rules(client: TestClient, samples: list[Sample]) -> None:
    phone = upload(client, by_name(samples, "facture-orange.pdf"))
    slip = upload(client, by_name(samples, "bulletin-paie.pdf"))
    assert phone["retention_rule"] == "1 year"
    assert slip["retention_rule"] == "Until you claim your pension"
    with i18n.using("fr"):
        french = client.get(f"/api/documents/{slip['id']}").json()
    assert french["retention_rule"] == "Jusqu'à la liquidation de la retraite"
    # Archiving the old ones: see test_archive.py.


def test_keep_forever_removes_suggestion(client: TestClient, samples: list[Sample]) -> None:
    phone = upload(client, by_name(samples, "facture-orange.pdf"))
    long_ago = (date.today() - timedelta(days=800)).isoformat()
    client.patch(f"/api/documents/{phone['id']}", json={"issue_date": long_ago})
    kept = client.patch(f"/api/documents/{phone['id']}", json={"keep_forever": True}).json()
    assert kept["archivable_reason"] is None
    assert client.get("/api/retention").json() == []
    log = client.get("/api/activity", params={"document_id": phone["id"]}).json()
    assert log[0]["summary"].endswith("kept beyond the recommended period")


def identity_card(issued: date, expires: date) -> Sample:
    html = f"""<h1>Carte nationale d'identité</h1><p>Lieu de naissance : Lyon</p>
    <p>Date de délivrance : {issued:%d/%m/%Y}</p><p>Date d'expiration : {expires:%d/%m/%Y}</p>"""
    return Sample(f"cni-{issued}.pdf", html, {})


def test_replaced_identity_card_can_be_sorted(client: TestClient) -> None:
    today = date.today()
    old = upload(client, identity_card(today - timedelta(days=3600), today + timedelta(days=20)))
    new = upload(client, identity_card(today - timedelta(days=5), today + timedelta(days=3645)))
    [suggested] = client.get("/api/retention").json()
    assert suggested["id"] == old["id"]
    assert suggested["archivable_reason"] == "Replaced by a newer version"
    assert [e["document"]["id"] for e in client.get("/api/expirations").json()] == [new["id"]]
