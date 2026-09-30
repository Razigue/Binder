import io
import zipfile

from fastapi.testclient import TestClient

from binder.samples import Sample
from tests.conftest import upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


def rescan(sample: Sample) -> Sample:
    """Même document, octets différents (téléchargé à nouveau, mention en pied de page)."""
    html = sample.html + "<p class='muted'>Document téléchargé depuis votre espace client</p>"
    return Sample("copie-" + sample.filename, html, sample.expected)


def test_standard_name_on_download(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, by_name(samples, "facture-edf.pdf"))
    assert doc["standard_name"] == f"{doc['issue_date']} Facture EDF.pdf"
    r = client.get(f"/api/documents/{doc['id']}/file")
    assert "filename*=UTF-8''" in r.headers["content-disposition"]


def test_export_is_sorted_by_category_and_year(client: TestClient, samples: list[Sample]) -> None:
    upload(client, by_name(samples, "facture-edf.pdf"))
    upload(client, by_name(samples, "facture-edf-juillet.pdf"))
    archive = zipfile.ZipFile(io.BytesIO(client.get("/api/export").content))
    names = sorted(n for n in archive.namelist() if n != "index.json")
    assert all(n.startswith("Énergie/20") and n.endswith("Facture EDF.pdf") for n in names)
    assert len(set(names)) == 2


def test_near_duplicate_goes_to_review(client: TestClient, samples: list[Sample]) -> None:
    original = upload(client, by_name(samples, "facture-orange.pdf"))
    copy = upload(client, rescan(by_name(samples, "facture-orange.pdf")))
    assert copy["id"] != original["id"]
    assert copy["duplicate_of"] == original["id"]
    assert copy["status"] == "to_review"
    assert "duplicate" in copy["missing_fields"]
    # L'échéance n'est comptée qu'une fois.
    assert [d["document_id"] for d in client.get("/api/deadlines").json()] == [original["id"]]

    kept = client.patch(f"/api/documents/{copy['id']}", json={"validated": True}).json()
    assert kept["duplicate_of"] is None
    assert kept["status"] == "classified"
    again = client.post(f"/api/documents/{copy['id']}/reanalyze").json()
    assert again["duplicate_of"] is None


def test_monthly_bills_are_not_duplicates(client: TestClient, samples: list[Sample]) -> None:
    upload(client, by_name(samples, "facture-edf.pdf"))
    july = upload(client, by_name(samples, "facture-edf-juillet.pdf"))
    assert july["duplicate_of"] is None


def test_trashing_original_releases_duplicate(client: TestClient, samples: list[Sample]) -> None:
    original = upload(client, by_name(samples, "facture-orange.pdf"))
    copy = upload(client, rescan(by_name(samples, "facture-orange.pdf")))
    client.delete(f"/api/documents/{original['id']}")
    freed = client.get(f"/api/documents/{copy['id']}").json()
    assert freed["duplicate_of"] is None
    assert freed["status"] == "classified"
    assert [d["document_id"] for d in client.get("/api/deadlines").json()] == [copy["id"]]


def test_latest_version_supersedes_older(client: TestClient, samples: list[Sample]) -> None:
    # Import dans le désordre : c'est la date du document qui compte.
    new = upload(client, by_name(samples, "attestation-maif.pdf"))
    old = upload(client, by_name(samples, "attestation-maif-ancienne.pdf"))
    assert new["doc_type"] == "Attestation d'assurance"
    assert new["status"] == "classified"
    assert client.get(f"/api/documents/{old['id']}").json()["superseded_by"] == new["id"]
    assert client.get(f"/api/documents/{new['id']}").json()["superseded_by"] is None

    # La plus récente part à la corbeille : l'ancienne redevient la version en vigueur.
    client.delete(f"/api/documents/{new['id']}")
    assert client.get(f"/api/documents/{old['id']}").json()["superseded_by"] is None
    client.post(f"/api/documents/{new['id']}/restore")
    assert client.get(f"/api/documents/{old['id']}").json()["superseded_by"] == new["id"]
    log = client.get("/api/activity", params={"document_id": old["id"]}).json()
    assert any("remplacé par une version plus récente" in e["summary"] for e in log)


def test_payslips_are_never_superseded(client: TestClient, samples: list[Sample]) -> None:
    slip = by_name(samples, "bulletin-paie.pdf")
    first = upload(client, slip)
    upload(client, rescan(slip))
    assert client.get(f"/api/documents/{first['id']}").json()["superseded_by"] is None
