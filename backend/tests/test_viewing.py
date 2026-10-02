"""The document open on screen: questions that name no other document are about it."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from binder.samples import Sample
from binder.services import llm
from tests.conftest import upload


@pytest.fixture
def library(client: TestClient, samples: list[Sample]) -> dict[str, int]:
    return {s.filename: int(str(upload(client, s)["id"])) for s in samples}


def ask(client: TestClient, message: str, viewing: int | None) -> dict[str, Any]:
    r = client.post("/api/agent/chat", json={"message": message, "viewing": viewing})
    assert r.status_code == 200
    result: dict[str, Any] = r.json()
    return result


def test_bare_question_is_about_the_document_on_screen(
    client: TestClient, library: dict[str, int]
) -> None:
    maif = library["maif-echeance.pdf"]
    r = ask(client, "How much?", maif)
    assert r["engine"] == "rules" and r["answer"].startswith("Amount for “")
    assert r["citations"] == [maif]

    r = ask(client, "Explain this document", maif)
    assert "To do: Pay $278.00" in r["answer"] and r["citations"] == [maif]


def test_named_document_still_searched_while_viewing_another(
    client: TestClient, library: dict[str, int]
) -> None:
    maif = library["maif-echeance.pdf"]
    edf = library["facture-edf.pdf"]
    r = ask(client, "How much is the EDF bill?", maif)
    assert r["citations"] == [edf]
    # Same question on the EDF bill's page: "this bill" is the one on screen.
    assert ask(client, "How much is this bill?", edf)["citations"] == [edf]


def test_stale_or_trashed_document_on_screen_is_ignored(
    client: TestClient, library: dict[str, int]
) -> None:
    maif = library["maif-echeance.pdf"]
    assert client.delete(f"/api/documents/{maif}").status_code in (200, 204)
    assert ask(client, "How much?", maif)["citations"] != [maif]
    assert ask(client, "How much?", 999)["engine"] == "rules"


def test_llm_receives_the_document_on_screen(
    client: TestClient, library: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    edf = library["facture-edf.pdf"]
    sent: list[list[dict[str, Any]]] = []

    def chat(messages: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        sent.append(list(messages))
        return {"role": "assistant", "content": f"94.37 € [#{edf}]."}

    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "chat", chat)
    r = ask(client, "How much do I owe?", edf)
    # Answered from the document on screen, without a search; shown since it is cited.
    assert r["citations"] == [edf] and r["documents"][0]["id"] == edf
    assert len(sent) == 1
    user = sent[0][-1]["content"]
    assert user.startswith("How much do I owe?") and "Document open on screen:" in user
    assert "EDF" in user
    assert "looking at one document" in sent[0][0]["content"]

    # Not cited: not shown with the answer.
    monkeypatch.setattr(llm, "chat", lambda *_, **__: {"role": "assistant", "content": "Hi!"})
    assert ask(client, "Hello", edf)["documents"] == []


@pytest.mark.parametrize(
    "question",
    [
        "Explain this document to me",
        "What do I need to do?",
        "When is it due?",
        "Explique-moi ce document",
        "Que dois-je faire ?",
        "Quelle est la date limite ?",
    ],
)
def test_suggestions_on_a_document_page_answer_about_it(
    client: TestClient, library: dict[str, int], question: str
) -> None:
    maif = library["maif-echeance.pdf"]
    assert ask(client, question, maif)["citations"] == [maif]
