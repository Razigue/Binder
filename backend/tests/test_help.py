import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from binder import i18n
from binder.config import get_settings
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


def use_french(client: TestClient) -> None:
    prefs = {"language": "fr", "country": "FR", "theme": "system"}
    assert client.put("/api/preferences", json=prefs).status_code == 200


def money_fr(value: float) -> str:
    return i18n.format_money(value, "fr", "EUR")


def test_explanation_of_a_bill_to_pay(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, by_name(samples, "taxe-fonciere.pdf"))
    ex = client.get(f"/api/documents/{doc['id']}/explanation").json()
    assert ex["engine"] == "rules"
    assert ex["language"] == "en"
    assert ex["action_required"] is True
    assert ex["actions"][0] == {"label": "Pay $1,240.00", "due_date": doc["due_date"]}
    assert "tax notice" in ex["summary"]


def test_direct_debit_and_certificates_need_no_action(
    client: TestClient, samples: list[Sample]
) -> None:
    edf = upload(client, by_name(samples, "facture-edf.pdf"))
    caf = upload(client, by_name(samples, "attestation-caf.pdf"))
    ex = client.get(f"/api/documents/{edf['id']}/explanation").json()
    assert ex["action_required"] is False
    assert ex["summary"].startswith("This is an invoice from EDF")
    assert any("debited automatically" in p for p in ex["key_points"])
    assert client.get(f"/api/documents/{caf['id']}/explanation").json()["action_required"] is False


def test_reminder_letter_asks_for_action(client: TestClient) -> None:
    html = """<h1>Orange</h1><h2>Relance : facture impayée</h2>
    <p>Facture n° 2026-1 du 01/09/2026</p>
    <p>Sauf erreur de notre part, votre facture de 39,99 € reste impayée.</p>
    <p>Merci de nous retourner le coupon avant le 15/10/2026.</p>"""
    doc = upload(client, Sample("relance.pdf", html, {}))
    ex = client.get(f"/api/documents/{doc['id']}/explanation").json()
    labels = [a["label"] for a in ex["actions"]]
    assert labels[0].startswith("Settle this quickly")
    assert {
        "label": "Send back the requested documents or information",
        "due_date": "2026-10-15",
    } in ex["actions"]


def test_explanation_is_cached_and_reset_on_edit(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, by_name(samples, "taxe-fonciere.pdf"))
    url = f"/api/documents/{doc['id']}/explanation"
    client.get(url)
    client.patch(f"/api/documents/{doc['id']}", json={"amount": 1300.0})
    assert client.get(url).json()["actions"][0]["label"] == "Pay $1,300.00"


def test_questions_are_answered_with_their_source(
    client: TestClient, samples: list[Sample]
) -> None:
    for s in samples:
        upload(client, s)
    tax = client.get("/api/documents", params={"q": "taxe fonciere"}).json()[0]

    r = ask(client, "Combien je dois payer pour la taxe foncière ?")
    assert r["answer"] == f"Amount for “{tax['title']}”: $1,240.00 [#{tax['id']}]."
    assert r["citations"] == [tax["id"]]

    card = client.get("/api/documents", params={"q": "carte identite"}).json()[0]
    r = ask(client, "Quand expire ma carte d'identité ?")
    assert f"[#{card['id']}]" in r["answer"]
    assert card["expiry_date"][:4] in r["answer"]

    r = ask(client, "Explique-moi l'avis d'échéance MAIF, dois-je faire quelque chose ?")
    assert "To do: Pay $278.00" in r["answer"]
    assert len(r["citations"]) == 1

    # Existing intents are not captured by questions.
    assert ask(client, "Quels documents arrivent bientôt ?")["deadlines"]


def test_english_questions(client: TestClient, samples: list[Sample]) -> None:
    for s in samples:
        upload(client, s)
    edf = client.get("/api/documents", params={"q": "edf"}).json()
    r = ask(client, "How much is my EDF bill?")
    assert r["engine"] == "rules"
    assert r["answer"].startswith("Amount for “")
    assert r["citations"] and r["citations"][0] in {d["id"] for d in edf}

    r = ask(client, "What should I do about the MAIF avis d'échéance?")
    assert "To do: Pay $278.00" in r["answer"]

    r = ask(client, "Which deadlines are coming up soon?")
    assert r["deadlines"] and r["answer"].startswith("You have ")

    r = ask(client, "Remind me to pay the school canteen on 12/11/2026")
    assert r["deadlines"][0]["due_date"] == "2026-11-12"
    assert r["deadlines"][0]["title"] == "Pay the school canteen"
    assert r["answer"] == "Done: reminder “Pay the school canteen” on 12 Nov 2026."

    r = ask(client, "Show me the latest document")
    assert r["answer"].startswith("Here is your most recent document: ")

    r = ask(client, "Export my taxes folder")
    assert "/api/export?category=taxes" in r["answer"]


def test_offline_agent_answers_in_french(client: TestClient, samples: list[Sample]) -> None:
    for s in samples:
        upload(client, s)
    tax = client.get("/api/documents", params={"q": "taxe fonciere"}).json()[0]
    # The explanation cached in English is rewritten in French.
    ask(client, "Explain the MAIF avis d'échéance, do I need to do anything?")
    use_french(client)

    r = ask(client, "How much is the property tax?")
    expected = f"Montant de « {tax['title']} » : {money_fr(1240)} [#{tax['id']}]."
    assert r["answer"] == expected

    r = ask(client, "Explique-moi l'avis d'échéance MAIF, dois-je faire quelque chose ?")
    assert f"À faire : Payer {money_fr(278)}" in r["answer"]

    r = ask(client, "Rappelle-moi de payer la cantine le 12/11/2026")
    assert r["answer"] == "C'est noté : rappel « Payer la cantine » le 12/11/2026."
    assert ask(client, "Trouve un document qui n'existe pas zzz")["answer"] == (
        "Je n'ai trouvé aucun document correspondant."
    )


def test_llm_citations_are_checked(
    client: TestClient, samples: list[Sample], monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = upload(client, by_name(samples, "facture-edf.pdf"))
    replies = iter(
        [
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "search_documents", "arguments": {"query": "edf"}}}
            ]},
            {"role": "assistant", "content": f"Your bill is €94.37 [#{doc['id']}] [#999]."},
        ]
    )  # fmt: skip
    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: next(replies))
    r = ask(client, "How much is my EDF bill?")
    assert r["engine"] == "llm"
    assert r["answer"] == f"Your bill is €94.37 [#{doc['id']}]."
    assert r["citations"] == [doc["id"]]


def test_llm_is_told_the_user_language(
    client: TestClient, samples: list[Sample], monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = upload(client, by_name(samples, "facture-edf.pdf"))
    use_french(client)
    requests: list[dict[str, Any]] = []

    def ollama(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": llm.model(), "size": 1}]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion", "tools"]})
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            call = {"function": {"name": "search_documents", "arguments": {"query": "edf"}}}
            return httpx.Response(
                200, json={"message": {"role": "assistant", "content": "", "tool_calls": [call]}}
            )
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "94,37 €"}})

    monkeypatch.setenv("BINDER_LLM_ENABLED", "true")
    get_settings.cache_clear()
    llm.forget_availability()
    llm.transport = httpx.MockTransport(ollama)
    r = ask(client, "Combien fait ma facture EDF ?")
    # The model cited nothing: its amount names the EDF bill, which becomes the source.
    assert r["engine"] == "llm" and r["answer"] == f"94,37 € [#{doc['id']}]"
    system = requests[0]["messages"][0]["content"]
    assert "Reply in French" in system and "France" in system and "EUR" in system
    # Ollama's default context (4096 tokens) would silently cut the conversation.
    assert requests[0]["options"]["num_ctx"] == get_settings().llm_context
    # Without vision, the model is not offered a tool it cannot use.
    names = {t["function"]["name"] for t in requests[0]["tools"]}
    assert "view_document" not in names and "write_letter" in names
    # Tool results are compact JSON with English keys, without null fields.
    tool = requests[1]["messages"][-1]
    assert tool["role"] == "tool" and tool["content"].startswith('{"results":[{"id":')
    assert '"title":' in tool["content"] and "null" not in tool["content"]


def test_attached_document_is_explained_offline(client: TestClient, samples: list[Sample]) -> None:
    doc = upload(client, by_name(samples, "maif-echeance.pdf"))
    r = client.post("/api/agent/chat", json={"message": "", "attachments": [doc["id"]]}).json()
    assert r["engine"] == "rules"
    assert "To do: Pay $278.00" in r["answer"]
    assert r["citations"] == [doc["id"]]

    r = client.post(
        "/api/agent/chat", json={"message": "How much?", "attachments": [doc["id"]]}
    ).json()
    assert r["answer"].startswith("Amount for “") and r["citations"] == [doc["id"]]

    missing = client.post("/api/agent/chat", json={"message": "", "attachments": [999]})
    assert missing.status_code == 404


def test_llm_receives_attached_documents(
    client: TestClient, samples: list[Sample], monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = upload(client, by_name(samples, "facture-edf.pdf"))
    sent: list[list[dict[str, Any]]] = []

    def chat(messages: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        sent.append(list(messages))
        return {"role": "assistant", "content": f"An EDF bill [#{doc['id']}]."}

    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "chat", chat)
    r = client.post(
        "/api/agent/chat", json={"message": "What is it?", "attachments": [doc["id"]]}
    ).json()
    # The attached document can be cited without any tool call.
    assert r["citations"] == [doc["id"]] and r["documents"][0]["id"] == doc["id"]
    user = sent[0][-1]["content"]
    assert user.startswith("What is it?") and "Attached documents:" in user and "EDF" in user


def test_english_questions_find_french_documents(client: TestClient, samples: list[Sample]) -> None:
    for sample in samples:
        upload(client, sample)

    def ask(message: str) -> str:
        answer: str = client.post("/api/agent/chat", json={"message": message}).json()["answer"]
        return answer

    assert "Property tax 2026" in ask("How much is the property tax?")
    # The roadworthiness test has no payment date: its end of validity answers the question.
    assert ask("When is my car inspection due?").startswith("Expiry date for")
