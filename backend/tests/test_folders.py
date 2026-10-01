import io
import zipfile
from datetime import date, timedelta

from fastapi.testclient import TestClient

from binder.samples import Sample
from tests.conftest import upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


def pieces(client: TestClient, kind: str) -> dict[str, dict[str, object]]:
    return {p["key"]: p for p in client.get(f"/api/folders/{kind}").json()["pieces"]}


def payslip(days_ago: int) -> Sample:
    d = date.today() - timedelta(days=days_ago)
    html = f"""<h1>Bulletin de paie</h1><p>Employeur : Studio Atlas SAS</p>
    <p>Édité le {d:%d/%m/%Y}</p><p>Net à payer : 2 134,56 €</p><p>Mois {days_ago}</p>"""
    return Sample(f"paie-{days_ago}.pdf", html, {})


def test_rental_folder_reports_missing_and_partial(
    client: TestClient, samples: list[Sample]
) -> None:
    for name in ("carte-identite.pdf", "bulletin-paie.pdf", "avis-imposition.pdf"):
        upload(client, by_name(samples, name))
    p = pieces(client, "rental")
    assert p["identity"]["status"] == "ok"
    assert p["tax_notice"]["status"] == "ok"
    assert p["income"]["status"] == "partial"
    assert p["income"]["note"] == "1 of 3"
    assert p["rent_receipts"]["status"] == "missing"
    assert p["work_contract"]["status"] == "missing"

    for days in (58, 88):
        upload(client, payslip(days))
    assert pieces(client, "rental")["income"]["status"] == "ok"
    folder = client.get("/api/folders/rental").json()
    assert (folder["ready"], folder["total"], folder["complete"]) == (3, 5, False)


def test_expired_identity_is_outdated(client: TestClient) -> None:
    today = date.today()
    html = f"""<h1>Carte nationale d'identité</h1><p>Lieu de naissance : Lyon</p>
    <p>Date de délivrance : {today - timedelta(days=4000):%d/%m/%Y}</p>
    <p>Date d'expiration : {today - timedelta(days=10):%d/%m/%Y}</p>"""
    upload(client, Sample("cni.pdf", html, {}))
    identity = pieces(client, "caf")["identity"]
    assert identity["status"] == "outdated"
    assert "expired on" in str(identity["note"])


def test_old_documents_do_not_count(client: TestClient) -> None:
    upload(client, payslip(400))
    p = pieces(client, "mortgage")["income"]
    assert p["status"] == "outdated"
    assert p["found"] == 0


def test_folder_export_lists_what_is_missing(client: TestClient, samples: list[Sample]) -> None:
    upload(client, by_name(samples, "carte-identite.pdf"))
    upload(client, by_name(samples, "quittance-loyer.pdf"))
    r = client.get("/api/folders/caf/export")
    archive = zipfile.ZipFile(io.BytesIO(r.content))
    names = archive.namelist()
    assert any(n.startswith("01 Valid identity document") for n in names)
    assert any(n.startswith("03 Lease or recent rent receipt") for n in names)
    readme = archive.read("README.txt").decode()
    assert "Bank account details (RIB)" in readme
    assert "[optional]" in readme
    assert client.get("/api/folders/unknown").status_code == 404


def test_folder_in_french(client: TestClient, samples: list[Sample]) -> None:
    client.put("/api/preferences", json={"language": "fr", "country": "FR", "theme": "system"})
    upload(client, by_name(samples, "bulletin-paie.pdf"))
    folder = client.get("/api/folders/rental").json()
    assert folder["title"] == "Dossier de location"
    income = {p["key"]: p for p in folder["pieces"]}["income"]
    assert income["label"] == "3 derniers bulletins de paie"
    assert income["note"] == "1 sur 3"
