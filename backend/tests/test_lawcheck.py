"""Legal points of letters and answers checked online before the user relies on them."""

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, quote

import httpx
import pytest
from sqlmodel import Session, select

from binder import i18n
from binder.agent import loop
from binder.config import get_settings
from binder.db import get_engine
from binder.models import Correspondence
from binder.services import lawcheck, letters, llm, websearch

OFFICIAL_URL = "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000030332005"
BLOG_URL = "https://www.blog-assurance.example/loi-hamon"
HAMON = (
    "Mon contrat ayant plus d'un an, je fais usage de la faculté de résiliation à tout moment "
    "prévue par l'article L113-15-2 du Code des assurances ; la résiliation prendra effet un "
    "mois après réception de ce courrier."
)
QUERY = "article L113-15-2 Code des assurances résiliation"
GUIDE_URL = "https://www.service-public.gouv.fr/particuliers/vosdroits/F2253"
EVIDENCE = "L'assuré peut résilier sans frais après un an."
CONFIRMED = {"status": "confirmed", "evidence": EVIDENCE, "source": 1}


def results_page() -> str:
    links = [(BLOG_URL, "Loi Hamon : le guide"), (OFFICIAL_URL, "Article L113-15-2")]
    items = "".join(
        f'<div><a class="result__a" href="//duckduckgo.com/l/?uddg={quote(u)}">{t}</a>'
        f'<a class="result__snippet">Résiliation à tout moment après un an.</a></div>'
        for u, t in links
    )
    return f"<html><body>{items}</body></html>"


class Web:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.pages: list[str] = []
        self.offline = False
        self.site_queries: list[str] = []
        self.site_results = ""

    def results(self, query: str) -> str:
        return results_page()

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.offline:
            raise httpx.ConnectError("offline")
        if request.url.path == "/particuliers/recherche":
            self.site_queries.append(request.url.params["keyword"])
            return httpx.Response(200, html=self.site_results)
        if request.url.host == "html.duckduckgo.com":
            self.queries.append(parse_qs(request.content.decode())["q"][0])
            return httpx.Response(200, html=self.results(self.queries[-1]))
        self.pages.append(str(request.url))
        body = "<p>Menu</p>" * 2000 + f"<p>{EVIDENCE}</p><p>Le préavis est d'un mois.</p>"
        return httpx.Response(200, html=f"<html><body>{body}</body></html>")


class Model:
    """The local model: lists the points, judges them, writes letters."""

    def __init__(
        self,
        verdict: dict[str, Any] | list[dict[str, Any]],
        points: list[dict[str, str]] | None = None,
    ):
        self.verdict = verdict
        self.points = points if points is not None else [{"claim": HAMON, "query": QUERY}]
        self.judged: list[str] = []

    def __call__(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        prompt = messages[-1]["content"]
        if prompt.startswith("List the legal points"):
            return {"content": json.dumps({"points": self.points})}
        if prompt.startswith("Check a legal point"):
            self.judged.append(prompt)
            verdict = self.verdict.pop(0) if isinstance(self.verdict, list) else self.verdict
            return {"content": json.dumps(verdict)}
        letter = {
            "subject": "Résiliation",
            "recipient": "Assureur",
            "paragraphs": ["Je résilie mon contrat.", HAMON],
            "registered": True,
        }
        return {"content": json.dumps(letter)}


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


def test_confirmed_point_cites_the_official_source(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = use(monkeypatch, Model(CONFIRMED))
    check = lawcheck.verify(session, f"Bonjour.\n{HAMON}")
    assert check.status == "verified"
    assert web.queries == [QUERY]
    point = check.points[0]
    assert point.status == "confirmed" and point.evidence == EVIDENCE
    # The official page is read first, and only the passage about the point reaches the model.
    assert web.pages[0] == OFFICIAL_URL
    assert point.sources[0].url == OFFICIAL_URL
    assert "résilier sans frais après un an" in model.judged[0]
    assert model.judged[0].count("Menu") < 2 * lawcheck.EXCERPT_CHARS / 5


def test_contradicted_point_is_shown_not_rewritten(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = "La résiliation prend effet un mois après sa notification (article L113-15-2)."
    verdict = {"status": "outdated", "evidence": EVIDENCE, "correction": current, "source": 1}
    use(monkeypatch, Model(verdict))
    check = lawcheck.verify(session, f"Bonjour.\n{HAMON}\nMerci.")
    assert check.status == "outdated"
    point = check.points[0]
    # The source's own sentence, and a wording the user can apply.
    assert point.evidence == EVIDENCE and point.correction == current
    assert point.sources[0].url == OFFICIAL_URL


def test_letters_are_never_rewritten(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = "La résiliation prend effet un mois après sa notification (article L113-15-2)."
    verdict = {"status": "outdated", "evidence": EVIDENCE, "correction": current, "source": 1}
    use(monkeypatch, Model(verdict))
    letter = letters.compose(session, "résilier mon assurance habitation")
    assert HAMON in letter.body and current not in letter.body
    assert letter.verification is not None and letter.verification.status == "outdated"


def test_points_are_checked_once_a_week(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = use(monkeypatch, Model(CONFIRMED))
    lawcheck.verify(session, HAMON)
    session.commit()
    assert lawcheck.verify(session, HAMON).status == "verified"
    assert len(web.queries) == 1 and len(model.judged) == 1


def test_unchecked_points_are_reported(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    use(monkeypatch, Model({"status": "not_found", "source": 0}))
    check = lawcheck.verify(session, HAMON)
    assert check.status == "unverified"
    # The sources found are still given, for the user to check.
    assert check.points[0].sources[0].url == OFFICIAL_URL
    # Tried again next time.
    lawcheck.verify(session, HAMON)
    assert len(web.queries) == 2


def test_offline(web: Web, session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    web.offline = True
    use(monkeypatch, Model(CONFIRMED))
    check = lawcheck.verify(session, HAMON)
    assert check.status == "unverified" and check.points[0].sources == []


def test_personal_query_falls_back_to_the_reference(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    personal = [{"claim": HAMON, "query": "résiliation contrat 4521877 L113-15-2"}]
    use(monkeypatch, Model(CONFIRMED, personal))
    assert lawcheck.verify(session, HAMON).status == "verified"
    assert web.queries == ["article L113-15-2 du Code des assurances"]


def test_without_a_model_the_references_are_searched(web: Web, session: Session) -> None:
    text = "Bonjour.\nArticle 22 of French law no. 89-462 of 6 July 1989 applies. Thanks."
    check = lawcheck.verify(session, text)
    assert web.queries == ["Article 22 law no. 89-462 of 6 July 1989"]
    assert check.status == "unverified" and check.points[0].sources


def test_text_without_law(web: Web, session: Session) -> None:
    assert lawcheck.verify(session, "Please send me my certificate.").status == "none"
    assert web.queries == []


def test_web_search_off(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    model = use(monkeypatch, Model(CONFIRMED))
    check = lawcheck.verify(session, HAMON)
    assert check.status == "unverified" and model.judged == []


def test_letters_are_saved_with_their_check(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    use(monkeypatch, Model(CONFIRMED))
    letter = letters.compose(session, "résilier mon assurance habitation")
    session.commit()
    assert letter.verification is not None and letter.verification.status == "verified"
    row = session.exec(select(Correspondence)).one()
    assert letters.out(row).verification == letter.verification


# --- Agent answers -------------------------------------------------------------------------


def test_answer_quoting_law_is_checked_first(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies = [
        {"content": "", "tool_calls": [{"function": {"name": "app_help", "arguments": {}}}]},
        {"content": "Vous pouvez résilier à tout moment (article L113-15-2)."},
        {
            "content": "",
            "tool_calls": [{"function": {"name": "web_search", "arguments": {"query": QUERY}}}],
        },
        {"content": "Oui, après un an, d'après legifrance.gouv.fr."},
    ]
    sent: list[list[dict[str, Any]]] = []

    def chat(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        sent.append(list(messages))
        return {"role": "assistant", **replies.pop(0)}

    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "has_vision", lambda: False)
    monkeypatch.setattr(llm, "chat", chat)
    response = loop.run(session, "Puis-je résilier mon assurance ?", [])
    assert response.answer == "Oui, après un an, d'après legifrance.gouv.fr."
    assert sent[2][-1]["content"] == loop.VERIFY_LAW
    assert web.queries == [QUERY]


def test_answer_after_a_search_is_not_held(web: Web) -> None:
    collector = loop._Collector()
    assert loop._states_unchecked_law(collector, "Le préavis légal est d'un mois.")
    collector.calls.append(loop.ToolCallTrace(name="web_search", arguments={}))
    assert not loop._states_unchecked_law(collector, "Le préavis légal est d'un mois.")
    assert not loop._states_unchecked_law(loop._Collector(), "Votre facture EDF est payée.")


@pytest.fixture
def france(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINDER_LOCALE", "fr_FR")
    i18n.system_locale.cache_clear()
    get_settings.cache_clear()


def test_official_publishers_are_searched_first(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch, france: None
) -> None:
    web.site_results = (
        f'<ul><li id="result_fichePratique_1"><a href="{GUIDE_URL}">Résilier</a></li></ul>'
    )
    use(monkeypatch, Model(CONFIRMED))
    check = lawcheck.verify(session, HAMON)
    assert check.status == "verified"
    # Searched by subject on service-public.gouv.fr itself, before any search engine.
    assert web.site_queries == ["assurances résiliation"]
    assert web.queries == []
    assert web.pages == [GUIDE_URL]
    assert check.points[0].sources[0].url == GUIDE_URL


def test_past_versions_are_read_last(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = (
        f'<a class="result__a" href="{OFFICIAL_URL}/2017-01-29">Ancienne version</a>'
        f'<a class="result__a" href="{OFFICIAL_URL}">Version en vigueur</a>'
    )
    monkeypatch.setattr(web, "results", lambda q: pages)
    use(monkeypatch, Model(CONFIRMED))
    lawcheck.verify(session, HAMON)
    assert web.pages == [OFFICIAL_URL, f"{OFFICIAL_URL}/2017-01-29"]


def test_blogs_alone_do_not_verify(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch, france: None
) -> None:
    blogs = f'<a class="result__a" href="{BLOG_URL}">Blog</a>'
    monkeypatch.setattr(web, "results", lambda q: blogs)
    model = use(monkeypatch, Model(CONFIRMED))
    check = lawcheck.verify(session, HAMON)
    assert web.site_queries and web.queries == [QUERY]
    assert check.status == "unverified" and model.judged == [] and web.pages == []
    # Still listed, for the user to check.
    assert check.points[0].sources[0].url == BLOG_URL


def test_next_source_when_the_first_does_not_decide(
    web: Web, session: Session, monkeypatch: pytest.MonkeyPatch, france: None
) -> None:
    web.site_results = f'<li id="result_1"><a href="{GUIDE_URL}">Autre sujet</a></li>'
    # service-public's guide does not say; Légifrance, found next, does.
    use(monkeypatch, Model([{"status": "not_found", "evidence": "", "source": 0}, CONFIRMED]))
    check = lawcheck.verify(session, HAMON)
    assert check.status == "verified" and web.queries == [QUERY]
    assert check.points[0].sources[0].url == OFFICIAL_URL


@pytest.mark.parametrize(
    ("claim", "verdict"),
    [
        # Evidence the model made up.
        (HAMON, {**CONFIRMED, "evidence": "La résiliation est possible à tout moment."}),
        # Confirmed, but the source says one month, not three.
        (
            "Le préavis légal est de trois mois (article L113-15-2 du Code des assurances).",
            {**CONFIRMED, "evidence": "Le préavis est d'un mois."},
        ),
        # A correction whose figure the source does not give.
        (
            HAMON,
            {
                "status": "outdated",
                "evidence": EVIDENCE,
                "correction": "La résiliation prend effet quinze jours après réception.",
                "source": 1,
            },
        ),
        # A source number that does not exist.
        (HAMON, {**CONFIRMED, "source": 7}),
    ],
)
def test_verdicts_not_backed_by_the_source_are_not_trusted(
    web: Web,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    claim: str,
    verdict: dict[str, Any],
) -> None:
    use(monkeypatch, Model(verdict, [{"claim": claim, "query": QUERY}]))
    check = lawcheck.verify(session, claim)
    assert check.status == "unverified"


def test_figures() -> None:
    assert lawcheck.figures("un délai de trois mois (article 22 de la loi n° 89-462)") == {"3"}
    assert lawcheck.figures("10 % of the monthly rent, within 15 days") == {"10", "15"}
