from datetime import date, timedelta

from fastapi.testclient import TestClient

from binder.samples import Sample
from tests.conftest import upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


def orange_bill(days_ago: int, amount: str) -> Sample:
    d = date.today() - timedelta(days=days_ago)
    html = f"""<h1>Orange</h1><h2>Facture mobile et internet</h2>
    <p>Facture n° {days_ago}-1 du {d:%d/%m/%Y}</p><p>Montant total à payer : {amount} €</p>"""
    return Sample(f"orange-{days_ago}.pdf", html, {})


def test_edf_increase_is_detected_and_logged(client: TestClient, samples: list[Sample]) -> None:
    upload(client, by_name(samples, "facture-edf-juillet.pdf"))
    latest = upload(client, by_name(samples, "facture-edf.pdf"))
    [edf] = client.get("/api/subscriptions").json()
    assert edf["label"] == "EDF"
    assert edf["cadence"] == "bimonthly"
    assert edf["cadence_label"] == "every two months"
    assert (edf["previous_amount"], edf["last_amount"]) == (81.05, 94.37)
    assert edf["change_pct"] == 16.4
    assert edf["increase"] is True
    assert [p["amount"] for p in edf["history"]] == [81.05, 94.37]

    log = client.get("/api/activity", params={"document_id": latest["id"]}).json()
    assert any(e["summary"] == "EDF up 16%: $94.37 instead of $81.05" for e in log)


def test_stable_monthly_subscription(client: TestClient) -> None:
    for days, amount in ((62, "39,99"), (31, "39,99"), (1, "40,49")):
        upload(client, orange_bill(days, amount))
    [orange] = client.get("/api/subscriptions").json()
    assert orange["cadence"] == "monthly"
    assert orange["increase"] is False  # +1.3%: below the threshold
    assert orange["yearly_estimate"] == round(40.49 * 365 / 30.5, 2)


def test_old_bill_imported_late_does_not_raise_alert(client: TestClient) -> None:
    upload(client, orange_bill(1, "45,00"))
    old = upload(client, orange_bill(31, "39,99"))
    log = client.get("/api/activity", params={"document_id": old["id"]}).json()
    assert not any(e["action"] == "increase" for e in log)
    # The increase does exist, but it is not attributed to the old bill.
    assert client.get("/api/subscriptions").json()[0]["increase"] is True


def test_single_document_is_not_a_subscription(client: TestClient, samples: list[Sample]) -> None:
    upload(client, by_name(samples, "facture-orange.pdf"))
    upload(client, by_name(samples, "avis-imposition.pdf"))
    assert client.get("/api/subscriptions").json() == []


def test_increase_alert_in_french(client: TestClient, samples: list[Sample]) -> None:
    client.put("/api/preferences", json={"language": "fr", "country": "FR", "theme": "system"})
    upload(client, by_name(samples, "facture-edf-juillet.pdf"))
    latest = upload(client, by_name(samples, "facture-edf.pdf"))
    [edf] = client.get("/api/subscriptions").json()
    assert (edf["cadence"], edf["cadence_label"]) == ("bimonthly", "bimestriel")
    log = client.get("/api/activity", params={"document_id": latest["id"]}).json()
    expected = "Hausse de 16 % sur EDF : 94,37\xa0€ contre 81,05\xa0€"
    assert any(e["summary"] == expected for e in log)
