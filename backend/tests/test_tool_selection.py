"""Tools offered to the model: at most ten per call, chosen from the request."""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlmodel import Session

from binder.agent import loop, tools
from binder.config import get_settings
from binder.db import get_engine
from binder.schemas import ChatMessage, ChatResponse
from binder.services import llm

REQUESTS = [
    "Mes factures EDF ?",
    "Quelles échéances ce mois-ci ?",
    "Rappelle-moi de payer la cantine le 12/11",
    "J'ai payé la taxe foncière",
    "Mets l'ancienne attestation MAIF à la corbeille",
    "Corrige le montant de la facture Orange : 42 €",
    "Écris une lettre de résiliation à Orange",
    "On déménage le 15 novembre",
    "Prépare le dossier pour la crèche",
    "Comment connecter ma boîte Gmail en IMAP ?",
    "Explique-moi l'avis d'impôt",
    "Annule ce que tu viens de faire",
    "Mon adresse a changé : 3 rue Neuve, Lyon",
    "What is due this month and can you remind me?",
    "",
]


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


class Recorder:
    """A model that looks one thing up and answers; records the tools of each call."""

    def __init__(self) -> None:
        self.offered: list[list[str] | None] = []

    def __call__(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        sent = kwargs.get("tools")
        self.offered.append([t["function"]["name"] for t in sent] if sent else None)
        if len(self.offered) == 1:
            call = {"function": {"name": "list", "arguments": {"kind": "deadlines"}}}
            return {"role": "assistant", "content": "", "tool_calls": [call]}
        return {"role": "assistant", "content": "Done."}


def _run(monkeypatch: pytest.MonkeyPatch, session: Session, message: str, *, vision: bool,
         web: bool) -> tuple[Recorder, ChatResponse]:  # fmt: skip
    recorder = Recorder()
    monkeypatch.setattr(get_settings(), "web_search", web)
    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "has_vision", lambda: vision)
    monkeypatch.setattr(llm, "chat", recorder)
    history = [ChatMessage(role="user", content="Écris une lettre à la CAF")]
    return recorder, loop.run(session, message or "Bonjour", history)


@pytest.mark.parametrize("message", REQUESTS)
@pytest.mark.parametrize("vision", [True, False])
@pytest.mark.parametrize("web", [True, False])
def test_no_call_offers_more_than_ten_tools(
    monkeypatch: pytest.MonkeyPatch, session: Session, message: str, vision: bool, web: bool
) -> None:
    recorder, _ = _run(monkeypatch, session, message, vision=vision, web=web)
    offered = [names for names in recorder.offered if names is not None]
    assert offered and all(len(names) <= tools.MAX_TOOLS for names in offered)
    assert all(len(set(names)) == len(names) for names in offered)


@pytest.mark.parametrize("message", REQUESTS)
def test_web_search_is_offered_in_every_call_when_on(
    monkeypatch: pytest.MonkeyPatch, session: Session, message: str
) -> None:
    recorder, _ = _run(monkeypatch, session, message, vision=True, web=True)
    for names in recorder.offered:
        if names is not None:
            assert "web_search" in names and "read_web_page" in names


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Rappelle-moi de payer la cantine le 12/11", "create_reminder"),
        ("Mets l'ancienne attestation MAIF à la corbeille", "trash_document"),
        ("Écris une lettre de résiliation à Orange", "write_letter"),
        ("On déménage le 15 novembre", "start_journey"),
        ("Comment connecter ma boîte Gmail en IMAP ?", "app_help"),
        ("Mon adresse a changé : 3 rue Neuve, Lyon", "update_profile"),
        ("Annule ce que tu viens de faire", "undo_last_action"),
        ("Exporte mes documents d'impôts", "export_folder"),
    ],
)
def test_the_request_brings_its_tools(
    monkeypatch: pytest.MonkeyPatch, message: str, expected: str
) -> None:
    monkeypatch.setattr(get_settings(), "web_search", True)
    names = loop.select_tools(message, vision=True)
    assert expected in names and len(names) <= tools.MAX_TOOLS


def test_listings_are_one_tool(session: Session) -> None:
    result = tools.call(session, "list", {"kind": "deadlines", "days": 30})
    assert "deadlines" in result.payload
    assert tools.resolve("list", {"kind": "alerts"}) == ("list_alerts", {})
    assert "Unknown kind" in tools.call(session, "list", {"kind": "cats"}).payload["error"]
    assert set(tools.LIST_KINDS.values()) <= set(tools.TOOLS)


def test_listing_is_traced_by_its_own_name(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    _, response = _run(monkeypatch, session, "Quelles échéances ?", vision=False, web=False)
    assert [c.name for c in response.tool_calls] == ["list_deadlines"]
