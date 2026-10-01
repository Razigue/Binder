"""Web search for the agent: general facts around paperwork (legal delays, official procedures,
rates, an organisation's contact), never the user's data.

Only the query leaves the machine, and it is checked first: a query carrying anything personal
(the household's names, the home address, an email, a phone number, an IBAN, a long number, a
document reference) is refused and the model is asked to rewrite it in general terms. Pages are
read only when a search returned them, so a page cannot steer the agent into sending data
elsewhere through a crafted URL. Every search is written to the activity log.
"""

import ipaddress
import re
import socket
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx
from sqlmodel import Session, col, select

from binder import __version__, i18n
from binder.config import get_settings
from binder.models import Document
from binder.services import activity, household, profile
from binder.services.rules import normalize

T = i18n.catalog(
    "websearch",
    {
        "searched": {
            "en": "Web search: “{query}”",
            "fr": "Recherche sur le web : « {query} »",
        },
    },
)

# Tests replace it with an httpx.MockTransport.
transport: httpx.BaseTransport | None = None

TIMEOUT = 10.0
RESULTS = 5
# Page text sent to the model: about a screen of an official page.
PAGE_CHARS = 4000
# Bigger pages are cut: the text that matters is near the top.
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3
# How long a URL returned by a search can be read.
SEEN_SECONDS = 3600
# Between two searches, and before trying again when the search engine refuses.
MIN_INTERVAL = 1.5
RETRY_SECONDS = 5.0

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,}", re.IGNORECASE)
_PHONE = re.compile(r"(?:\+\d{2,3}[\s.]?|\b0)\d(?:[\s.-]?\d{2}){4}\b")
# Account, contract, tax or social security numbers, postcodes: five digits in a row, or four
# groups of digits ("1 85 05 78 006"). Law numbers ("loi 89-462") and years stay allowed.
_NUMBER = re.compile(r"\b\d{5,}\b|\b\d+(?:[\s.]\d+){3,}\b")
# Words too common to tell anything when they are part of a name or an address.
_COMMON = {
    "rue", "avenue", "boulevard", "chemin", "place", "allee", "impasse", "route", "quai",
    "cours", "bis", "ter", "les", "des", "del", "van", "von", "der", "saint", "sainte",
}  # fmt: skip

_seen: dict[str, float] = {}
_last = 0.0


@dataclass
class Result:
    title: str
    url: str
    snippet: str


class Blocked(httpx.HTTPError):
    """The search engine took us for a robot (too many searches in a row): like offline."""


def _challenged(r: httpx.Response) -> bool:
    # DuckDuckGo answers 202 with an "anomaly" page instead of results.
    return r.status_code == 202 or "anomaly-modal" in r.text


def _wait() -> None:
    """Spaces searches out: a burst (a letter checks several points) gets us blocked."""
    global _last
    if transport is None:
        time.sleep(max(0.0, _last + MIN_INTERVAL - time.monotonic()))
    _last = time.monotonic()


class PersonalData(ValueError):
    """The query names something about the user: it is not sent."""

    def __init__(self, kinds: list[str]) -> None:
        super().__init__(", ".join(kinds))
        self.kinds = kinds


def enabled() -> bool:
    return get_settings().web_search


def _words(value: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", normalize(value)) if w not in _COMMON}


def _personal_words(session: Session) -> dict[str, str]:
    """Words of the household's names and home address, with the kind each one reveals."""
    me = profile.load(session)
    found: dict[str, str] = {}
    names = [me.name, *(m.name for m in household.members(session))]
    for name in names:
        found.update(dict.fromkeys(_words(name), "name"))
    street = me.address.splitlines()[0] if me.address else ""
    home = household.home_address(session)
    for line in (street, home[0] if home else ""):
        found.update(dict.fromkeys(_words(line), "address"))
    return found


def _references(session: Session) -> set[str]:
    rows = session.exec(
        select(Document.reference).where(
            col(Document.deleted_at).is_(None), col(Document.reference).is_not(None)
        )
    )
    return {normalize(r).strip() for r in rows if r and len(r.strip()) >= 4}


def check(session: Session, query: str) -> None:
    """Raises PersonalData when the query carries something about the user."""
    kinds: list[str] = []
    if _EMAIL.search(query):
        kinds.append("email")
    if _IBAN.search(query):
        kinds.append("iban")
    if _PHONE.search(query):
        kinds.append("phone")
    elif _NUMBER.search(query):
        kinds.append("number")
    norm = normalize(query)
    words = set(re.findall(r"[a-z]{3,}", norm))
    for word, kind in _personal_words(session).items():
        if word in words and kind not in kinds:
            kinds.append(kind)
    if any(ref in norm for ref in _references(session)):
        kinds.append("reference")
    if kinds:
        raise PersonalData(kinds)


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT,
        transport=transport,
        headers={"User-Agent": f"Mozilla/5.0 (compatible; Binder/{__version__})"},
    )


class _ResultsParser(HTMLParser):
    """Results of DuckDuckGo's HTML page: a.result__a (title, link) then .result__snippet."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[Result] = []
        self._field: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if tag == "a" and "result__a" in classes:
            self.results.append(Result(title="", url=_target(dict(attrs).get("href")), snippet=""))
            self._field = "title"
        elif "result__snippet" in classes and self.results:
            self._field = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if tag in ("a", "td", "div"):
            self._field = None

    def handle_data(self, data: str) -> None:
        if self._field and self.results:
            last = self.results[-1]
            setattr(last, self._field, getattr(last, self._field) + data)


def _target(href: str | None) -> str:
    """The result's own URL: DuckDuckGo links go through //duckduckgo.com/l/?uddg=<url>."""
    if not href:
        return ""
    parts = urlsplit(urljoin("https://duckduckgo.com", href))
    if parts.path == "/l/":
        return parse_qs(parts.query).get("uddg", [""])[0]
    return href


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def search(session: Session, query: str) -> list[Result]:
    """Results for a general query (raises PersonalData, or httpx.HTTPError when offline)."""
    query = _clean(query)
    check(session, query)
    # DuckDuckGo regions: fr-fr, be-fr, uk-en…
    country = (i18n.current().country or "").lower()
    region = {"gb": "uk"}.get(country, country)
    language = i18n.current().language
    form = {"q": query, "kl": f"{region}-{language}" if region else "wt-wt"}
    with _client() as c:
        for attempt in range(2):
            _wait()
            r = c.post(get_settings().web_search_url, data=form)
            r.raise_for_status()
            if not _challenged(r):
                break
            if attempt:
                raise Blocked("the search engine asks to slow down")
            time.sleep(RETRY_SECONDS if transport is None else 0)
    parser = _ResultsParser()
    parser.feed(r.text)
    return _found(session, query, parser.results)


def _found(session: Session, query: str, items: list[Result]) -> list[Result]:
    """The results kept, made readable by read_page, and the search logged."""
    results = []
    for item in items:
        if item.url.startswith(("http://", "https://")):
            results.append(Result(_clean(item.title), item.url, _clean(item.snippet)))
        if len(results) == RESULTS:
            break
    now = time.monotonic()
    for url in [u for u, t in _seen.items() if now - t > SEEN_SECONDS]:
        del _seen[url]
    _seen.update(dict.fromkeys((x.url for x in results), now))
    activity.log(session, "web_search", T.msg("searched", query=query), actor="agent")
    return results


class _SiteResultsParser(HTMLParser):
    """Links of an official site's own results: <li id="result_…"><a href=…>title</a>."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[Result] = []
        self._depth = 0
        self._link = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "li" and (values.get("id") or "").startswith("result_"):
            self._depth = 1
        elif tag == "li" and self._depth:
            self._depth += 1
        elif tag == "a" and self._depth and values.get("href"):
            self.results.append(Result(title="", url=values["href"] or "", snippet=""))
            self._link = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._link = False
        elif tag == "li" and self._depth:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._link and self.results:
            self.results[-1].title += data


# Official sites searched through their own search page (no search engine in between): the
# practical guides of service-public.gouv.fr quote the law in force with its articles.
SITE_SEARCHES = {
    "service-public.gouv.fr": (
        "https://www.service-public.gouv.fr/particuliers/recherche",
        {"rubricFilter": "fichePratique"},
    ),
}


def search_site(session: Session, site: str, query: str) -> list[Result]:
    """Results of an official site's own search (SITE_SEARCHES); same checks as search()."""
    query = _clean(query)
    check(session, query)
    url, params = SITE_SEARCHES[site]
    with _client() as c:
        r = c.get(url, params={"keyword": query, **params}, follow_redirects=True)
        r.raise_for_status()
    parser = _SiteResultsParser()
    parser.feed(r.text)
    return _found(session, f"{query} ({site})", parser.results)


def _public(url: str) -> bool:
    """A public web address: not this machine nor the local network."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443)
    except OSError:
        return False
    return all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


class _TextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}
    BLOCKS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "section", "article"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        lines = "".join(self.parts).split("\n")
        cleaned = (re.sub(r"[ \t\xa0]+", " ", line).strip() for line in lines)
        return "\n".join(line for line in cleaned if line)


def known(url: str) -> bool:
    seen = _seen.get(url)
    return seen is not None and time.monotonic() - seen <= SEEN_SECONDS


def read_page(url: str, limit: int = PAGE_CHARS) -> tuple[str, str]:
    """Title and text of a page a search returned (raises ValueError or httpx.HTTPError)."""
    if not known(url):
        raise ValueError("only pages returned by web_search can be read")
    with _client() as c:
        for _ in range(MAX_REDIRECTS + 1):
            # Checked at each hop: a redirect could lead to this machine or the local network.
            # (Tests serve pages from a mock transport, with no real address to resolve.)
            if transport is None and not _public(url):
                raise ValueError("not a public web page")
            with c.stream("GET", url) as r:
                if r.is_redirect and "location" in r.headers:
                    url = urljoin(url, r.headers["location"])
                    continue
                r.raise_for_status()
                kind = r.headers.get("content-type", "")
                if "html" not in kind and "text/plain" not in kind:
                    raise ValueError(f"not a web page ({kind or 'unknown type'})")
                body = b""
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) >= MAX_BYTES:
                        break
                encoding = r.encoding or "utf-8"
            break
        else:
            raise ValueError("too many redirects")
    page = body.decode(encoding, errors="replace")
    if "html" not in kind:
        return "", _clean(page)[:limit]
    parser = _TextParser()
    parser.feed(page)
    return _clean(parser.title), parser.text()[:limit]
