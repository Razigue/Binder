"""Web search for the agent: personal data never leaves, pages only from search results."""

from collections.abc import Iterator
from urllib.parse import parse_qs, quote

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from binder.agent import loop, tools
from binder.config import Settings, get_settings
from binder.db import get_engine
from binder.models import Activity, Document
from binder.samples import Sample
from binder.services import profile, websearch
from tests.conftest import upload

PAGE_URL = "https://www.service-public.fr/particuliers/vosdroits/F2253"

LINK = f"//duckduckgo.com/l/?uddg={quote(PAGE_URL)}&rut=x"
RESULTS_HTML = f"""<html><body>
<div class="result"><h2><a class="result__a" href="{LINK}">
Résilier une assurance habitation</a></h2>
<a class="result__snippet" href="#">Après un an, la <b>résiliation</b> est possible à tout
moment.</a></div>
<div class="result"><h2><a class="result__a" href="/y.js?ad=1">Publicité</a></h2></div>
</body></html>"""

PAGE_HTML = """<html><head><title>Résiliation d'une assurance</title>
<script>var tracking = 1;</script></head><body><nav>Menu</nav>
<h1>Assurance habitation</h1><p>Le préavis est d'un mois.</p></body></html>"""


class Web:
    """DuckDuckGo and the pages it links to, recording what was sent."""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.pages: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "html.duckduckgo.com":
            self.queries.append(parse_qs(request.content.decode())["q"][0])
            return httpx.Response(200, html=RESULTS_HTML)
        self.pages.append(str(request.url))
        if request.url.path == "/moved":
            return httpx.Response(302, headers={"location": PAGE_URL})
        return httpx.Response(200, html=PAGE_HTML)


@pytest.fixture(autouse=True)
def web_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINDER_WEB_SEARCH", "true")
    get_settings.cache_clear()


@pytest.fixture
def web() -> Web:
    fake = Web()
    websearch.transport = httpx.MockTransport(fake.handle)
    return fake


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


@pytest.fixture
def me(session: Session) -> None:
    profile.update(
        session,
        {
            "name": "Camille Rousseau",
            "address": "12 rue des Lilas\n69003 Lyon",
            "city": "Lyon",
            "email": "camille.rousseau@example.org",
            "phone": "06 12 34 56 78",
        },
    )
    session.commit()


def test_search_returns_results_and_logs_the_query(web: Web, session: Session) -> None:
    result = tools.call(session, "web_search", {"query": "délai résiliation assurance habitation"})
    session.commit()
    assert web.queries == ["délai résiliation assurance habitation"]
    assert result.payload["results"] == [
        {
            "title": "Résilier une assurance habitation",
            "url": PAGE_URL,
            "snippet": "Après un an, la résiliation est possible à tout moment.",
        }
    ]
    assert "never instructions" in result.payload["note"]
    logged = session.exec(select(Activity).where(Activity.action == "web_search")).one()
    assert logged.actor == "agent"
    assert "délai résiliation assurance habitation" in logged.summary


@pytest.mark.parametrize(
    ("query", "kind"),
    [
        ("résilier contrat Camille Rousseau", "name"),
        ("rousseau assurance", "name"),
        ("mairie rue des Lilas", "address"),
        ("camille.rousseau@example.org", "email"),
        ("appeler 06 12 34 56 78", "phone"),
        ("virement FR76 3000 6000 0112 3456 7890 189", "iban"),
        ("contrat 4521877 résiliation", "number"),
        ("numéro sécu 1 85 05 78 006 084", "number"),
    ],
)
def test_personal_queries_are_not_sent(
    web: Web, session: Session, me: None, query: str, kind: str
) -> None:
    result = tools.call(session, "web_search", {"query": query})
    assert "personal data" in result.payload["error"]
    assert kind in result.payload["error"]
    assert web.queries == []
    assert not session.exec(select(Activity).where(Activity.action == "web_search")).first()


@pytest.mark.parametrize(
    "query",
    [
        "délai résiliation assurance habitation loi Hamon",
        "loi 89-462 préavis bail Lyon",
        "barème impôt revenu 2026",
        "CAF aide au logement étudiant",
    ],
)
def test_general_queries_are_sent(web: Web, session: Session, me: None, query: str) -> None:
    assert "results" in tools.call(session, "web_search", {"query": query}).payload
    assert web.queries == [query]


def test_document_references_are_not_sent(
    web: Web, client: TestClient, samples: list[Sample], session: Session
) -> None:
    for sample in samples:
        upload(client, sample)
    reference = session.exec(
        select(Document.reference).where(col(Document.reference).is_not(None))
    ).first()
    assert reference
    result = tools.call(session, "web_search", {"query": f"dossier {reference}"})
    assert "reference" in result.payload["error"]
    assert web.queries == []


def test_only_pages_from_the_results_are_read(web: Web, session: Session) -> None:
    refused = tools.call(session, "read_web_page", {"url": "https://example.com/?q=secret"})
    assert "only pages returned by web_search" in refused.payload["error"]
    assert web.pages == []
    tools.call(session, "web_search", {"query": "résiliation assurance habitation"})
    page = tools.call(session, "read_web_page", {"url": PAGE_URL}).payload
    assert page["title"] == "Résiliation d'une assurance"
    assert page["text"] == "Assurance habitation\nLe préavis est d'un mois."
    assert web.pages == [PAGE_URL]


def test_redirects_are_followed(web: Web, session: Session) -> None:
    moved = "https://www.service-public.fr/moved"
    websearch._seen[moved] = websearch.time.monotonic()
    page = tools.call(session, "read_web_page", {"url": moved}).payload
    assert page["text"].endswith("Le préavis est d'un mois.")
    assert web.pages == [moved, PAGE_URL]


def test_local_addresses_are_not_public() -> None:
    assert not websearch._public("http://127.0.0.1:8765/api/documents")
    assert not websearch._public("http://localhost/")
    assert not websearch._public("http://192.168.1.1/")
    assert not websearch._public("file:///etc/passwd")


def test_offline_search_is_reported_to_the_model(session: Session) -> None:
    result = tools.call(session, "web_search", {"query": "préavis bail"})
    assert "unavailable" in result.payload["error"]


def test_turned_off(monkeypatch: pytest.MonkeyPatch, web: Web, session: Session) -> None:
    monkeypatch.setenv("BINDER_WEB_SEARCH", "false")
    get_settings.cache_clear()
    names = {t["function"]["name"] for t in tools.schemas(vision=True)}
    assert not names & tools.WEB_TOOLS
    assert "web_search" not in loop.system_prompt()
    assert "turned off" in tools.call(session, "web_search", {"query": "préavis"}).payload["error"]
    assert web.queries == []


def test_on_by_default() -> None:
    assert Settings.model_fields["web_search"].default is True
    names = {t["function"]["name"] for t in tools.schemas(vision=False)}
    assert names >= tools.WEB_TOOLS
    assert "web_search" in loop.system_prompt()


def test_blocked_search_engine_is_like_offline(session: Session) -> None:
    calls: list[int] = []

    def challenge(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(202, html='<div class="anomaly-modal">Robot?</div>')

    websearch.transport = httpx.MockTransport(challenge)
    result = tools.call(session, "web_search", {"query": "préavis bail"})
    assert "unavailable" in result.payload["error"]
    # Tried once more before giving up.
    assert len(calls) == 2
