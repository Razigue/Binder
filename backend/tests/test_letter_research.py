"""Letters adapted to the organisation: its own procedure looked up online before writing."""

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, quote

import httpx
import pytest
from sqlmodel import Session, select

from binder.config import get_settings
from binder.db import get_engine
from binder.models import Correspondence
from binder.services import letters, llm, research, websearch

OWN_URL = "https://www.sfr.fr/assistance/resilier-forfait-mobile"
BLOG_URL = "https://www.forum-conso.example/resiliation-sfr"
ADDRESS = "SFR Service Résiliation\nTSA 30103\n69947 Lyon Cedex 20"
PAGE = (
    "Pour résilier votre forfait mobile, envoyez votre demande à SFR Service Résiliation, "
    "TSA 30103, 69947 Lyon Cedex 20. Indiquez votre numéro de ligne. La résiliation prend "
    "effet 10 jours après réception. Pensez à demander votre code RIO au 3179."
)
PLAN = {"organisation": "SFR", "queries": ["adresse résiliation forfait mobile SFR"]}


class Web:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.pages: list[str] = []
        self.offline = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.offline:
            raise httpx.ConnectError("offline")
        if request.url.host == "html.duckduckgo.com":
            self.queries.append(parse_qs(request.content.decode())["q"][0])
            links = [(BLOG_URL, "Résilier SFR : avis"), (OWN_URL, "Résilier votre forfait")]
            items = "".join(
                f'<div><a class="result__a" href="//duckduckgo.com/l/?uddg={quote(u)}">{t}</a>'
                f'<a class="result__snippet">Résiliation SFR.</a></div>'
                for u, t in links
            )
            return httpx.Response(200, html=f"<html><body>{items}</body></html>")
        self.pages.append(str(request.url))
        return httpx.Response(200, html=f"<html><body><p>{PAGE}</p></body></html>")


class Model:
    """Plans the searches and writes the letter; lists no legal point to check."""

    def __init__(self, plan: dict[str, Any], letter: dict[str, Any]) -> None:
        self.plan = plan
        self.letter = letter
        self.prompts: list[str] = []

    def __call__(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        if prompt.startswith("A letter is about to be written"):
            return {"content": json.dumps(self.plan)}
        if prompt.startswith("List the legal points"):
            return {"content": json.dumps({"points": []})}
        return {"content": json.dumps(self.letter)}

    def writing(self) -> str:
        return next(p for p in self.prompts if p.startswith("Write the body"))


def letter(**extra: Any) -> dict[str, Any]:
    return {
        "subject": "Résiliation de mon forfait mobile",
        "recipient": "SFR Service Résiliation",
        "paragraphs": ["Je vous informe de ma décision de résilier mon forfait mobile."],
        "registered": True,
        **extra,
    }


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch) -> Web:
    monkeypatch.setenv("BINDER_WEB_SEARCH", "true")
    get_settings.cache_clear()
    fake = Web()
    websearch.transport = httpx.MockTransport(fake.handle)
    return fake


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


def use(monkeypatch: pytest.MonkeyPatch, model: Model) -> Model:
    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "chat", model)
    return model


def test_termination_is_written_from_the_organisation_procedure(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = use(monkeypatch, Model(PLAN, letter(recipient_address=ADDRESS, sources=[1])))
    purpose = "résilier mon forfait mobile SFR, je pars chez un autre opérateur"
    written = letters.compose(session, purpose, kind="termination")
    session.commit()
    assert web.queries == ["adresse résiliation forfait mobile SFR"]
    # The organisation's own page is read first, then given to the model with the user's words.
    assert web.pages[0] == OWN_URL
    prompt = model.writing()
    assert "TSA 30103" in prompt and "pars chez un autre opérateur" in prompt
    assert "notice and commitment period" in prompt
    # Its address for terminations, and the page it came from.
    assert written.recipient == "SFR Service Résiliation"
    assert written.recipient_address == ADDRESS and "TSA 30103" in written.body
    assert [s.url for s in written.sources] == [OWN_URL]
    row = session.exec(select(Correspondence)).one()
    assert letters.out(row).sources == written.sources


def test_an_address_the_sources_do_not_give_is_not_used(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    invented = "SFR\n12 rue Imaginaire\n75999 Paris"
    use(monkeypatch, Model(PLAN, letter(recipient_address=invented, sources=[1])))
    written = letters.compose(session, "résilier mon forfait SFR", kind="termination")
    assert "Imaginaire" not in written.body and written.recipient_address == ""


def test_queries_naming_the_person_are_not_sent(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = {"organisation": "SFR", "queries": ["résiliation SFR ligne 0612345678"]}
    model = use(monkeypatch, Model(plan, letter()))
    written = letters.compose(session, "résilier ma ligne SFR", kind="termination")
    assert web.queries == [] and written.sources == []
    assert "Found on the web" not in model.writing()


def test_offline_the_letter_is_still_written_by_the_model(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    web.offline = True
    model = use(monkeypatch, Model(PLAN, letter(sources=[1])))
    written = letters.compose(session, "résilier mon forfait SFR", kind="termination")
    assert "décision de résilier mon forfait mobile" in written.body
    assert written.sources == [] and "résilier mon forfait SFR" in model.writing()


def test_without_web_search_nothing_leaves(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = use(monkeypatch, Model(PLAN, letter()))
    written = letters.compose(session, "résilier mon forfait SFR", kind="termination")
    assert not any(p.startswith("A letter is about to be written") for p in model.prompts)
    assert "décision de résilier" in written.body


def test_addresses_must_be_in_a_source() -> None:
    assert research.backed("TSA 30103\n69947 Lyon Cedex 20", [PAGE])
    assert not research.backed("75999 Paris", [PAGE])
    assert not research.backed("Service clients", [PAGE])


class FreeWeb(Web):
    """The organisation's own pages give a phone number only; a guide gives the address deep in
    a long page, far from the passage about the request."""

    OWN = ("https://assistance.free.fr/articles/287", "https://www.free.fr/resiliation")
    GUIDE = "https://www.guide-conso.example/free/resiliation"

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "html.duckduckgo.com":
            self.queries.append(parse_qs(request.content.decode())["q"][0])
            items = "".join(
                f'<div><a class="result__a" href="//duckduckgo.com/l/?uddg={quote(u)}">Free</a>'
                f'<a class="result__snippet">Résiliation Freebox.</a></div>'
                for u in [self.GUIDE, *self.OWN]
            )
            return httpx.Response(200, html=f"<html><body>{items}</body></html>")
        url = str(request.url)
        self.pages.append(url)
        if url in self.OWN:
            body = "<p>Résiliation Freebox : appelez le 3244 ou votre Espace Abonné.</p>"
        else:
            filler = "".join(f"<p>Conseil {i} sur les offres et les prix.</p>" for i in range(200))
            body = (
                "<p>Résilier sa Freebox : délai de résiliation de 10 jours.</p>"
                f"{filler}<p>Publidispatch, Free Résiliation, BP 40090, 91003 Évry Cedex</p>"
            )
        return httpx.Response(200, html=f"<html><body>{body}</body></html>")


def test_an_address_far_into_a_page_reaches_the_model(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BINDER_WEB_SEARCH", "true")
    get_settings.cache_clear()
    web = FreeWeb()
    websearch.transport = httpx.MockTransport(web.handle)
    plan = {"organisation": "Free", "queries": ["adresse résiliation Freebox"]}
    found = "Publidispatch - Free Résiliation\nBP 40090\n91003 Évry Cedex"
    model = use(monkeypatch, Model(plan, letter(recipient_address=found, sources=[3])))
    written = letters.compose(session, "Résiliation box Free", kind="termination")
    # Free's own pages are read first, then the guide for the address they lack.
    assert web.pages[-1] == FreeWeb.GUIDE
    assert "BP 40090, 91003 Évry Cedex" in model.writing()
    assert written.recipient_address == found


def test_addresses_are_the_passages_around_postcodes() -> None:
    body = "Siège : 16 rue de la Ville l'Evêque\n75008 PARIS\nAppelez le 3244, prix 2024 €."
    assert research.addresses(body, "Free siège") == [body.split("\nAppelez")[0]]
    assert research.addresses("Appelez le 3244 en 2024.", "Free") == []
