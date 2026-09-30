from typing import Any

import pytest
from fastapi.testclient import TestClient

from binder.samples import Sample
from binder.services import llm
from tests.conftest import upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


def ask(client: TestClient, message: str) -> dict[str, Any]:
    r = client.post("/api/agent/chat", json={"message": message})
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


def test_explanation_of_a_bill_to_pay(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, by_name(samples, "taxe-fonciere.pdf"))
    ex = client.get(f"/api/documents/{doc['id']}/explanation").json()
    assert ex["engine"] == "rules"
    assert ex["action_required"] is True
    assert ex["actions"][0] == {"label": "Payer 1 240,00 €", "due_date": doc["due_date"]}
    assert "avis d'impôt" in ex["summary"]


def test_direct_debit_and_certificates_need_no_action(
    client: TestClient, samples: list[Sample]
) -> None:
    edf = upload(client, by_name(samples, "facture-edf.pdf"))
    caf = upload(client, by_name(samples, "attestation-caf.pdf"))
    ex = client.get(f"/api/documents/{edf['id']}/explanation").json()
    assert ex["action_required"] is False
    assert ex["summary"].startswith("C'est une facture d'EDF")
    assert any("prélevé automatiquement" in p for p in ex["key_points"])
    assert client.get(f"/api/documents/{caf['id']}/explanation").json()["action_required"] is False


def test_reminder_letter_asks_for_action(client: TestClient) -> None:
    html = """<h1>Orange</h1><h2>Relance : facture impayée</h2>
    <p>Facture n° 2026-1 du 01/09/2026</p>
    <p>Sauf erreur de notre part, votre facture de 39,99 € reste impayée.</p>
    <p>Merci de nous retourner le coupon avant le 15/10/2026.</p>"""
    doc = upload(client, Sample("relance.pdf", html, {}))
    ex = client.get(f"/api/documents/{doc['id']}/explanation").json()
    labels = [a["label"] for a in ex["actions"]]
    assert labels[0].startswith("Régulariser rapidement")
    assert {
        "label": "Renvoyer les documents ou informations demandés",
        "due_date": "2026-10-15",
    } in ex["actions"]


def test_explanation_is_cached_and_reset_on_edit(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, by_name(samples, "taxe-fonciere.pdf"))
    url = f"/api/documents/{doc['id']}/explanation"
    client.get(url)
    client.patch(f"/api/documents/{doc['id']}", json={"amount": 1300.0})
    assert client.get(url).json()["actions"][0]["label"] == "Payer 1 300,00 €"


def test_questions_are_answered_with_their_source(
    client: TestClient, samples: list[Sample]
) -> None:
    for s in samples:
        upload(client, s)
    tax = client.get("/api/documents", params={"q": "taxe fonciere"}).json()[0]

    r = ask(client, "Combien je dois payer pour la taxe foncière ?")
    assert r["answer"] == f"Montant de « Taxe foncière 2026 » : 1 240,00 € [#{tax['id']}]."
    assert r["citations"] == [tax["id"]]

    card = client.get("/api/documents", params={"q": "carte identite"}).json()[0]
    r = ask(client, "Quand expire ma carte d'identité ?")
    assert f"[#{card['id']}]" in r["answer"]
    assert card["expiry_date"][:4] in r["answer"]

    r = ask(client, "Explique-moi l'avis d'échéance MAIF, dois-je faire quelque chose ?")
    assert "À faire : Payer 278,00 €" in r["answer"]
    assert len(r["citations"]) == 1

    # Les intentions existantes ne sont pas capturées par les questions.
    assert ask(client, "Quels documents arrivent bientôt ?")["deadlines"]


def test_llm_citations_are_checked(
    client: TestClient, samples: list[Sample], monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = upload(client, by_name(samples, "facture-edf.pdf"))
    replies = iter(
        [
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "search_documents", "arguments": {"query": "edf"}}}
            ]},
            {"role": "assistant", "content": f"Votre facture fait 94,37 € [#{doc['id']}] [#999]."},
        ]
    )  # fmt: skip
    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: next(replies))
    r = ask(client, "Combien fait ma facture EDF ?")
    assert r["engine"] == "llm"
    assert r["answer"] == f"Votre facture fait 94,37 € [#{doc['id']}]."
    assert r["citations"] == [doc["id"]]
