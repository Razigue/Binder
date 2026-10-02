"""Legal points checked online before the user relies on them.

Law changes (notice periods, rates, articles renumbered or repealed), and both the templates and
the model's own knowledge date from when they were written. Every legal point of a letter is
therefore looked up the day it is written: the country's official publishers first
(service-public.gouv.fr through its own search, then official pages found on the web), read,
then judged by the local model against today's date. A verdict counts only if the sentence it
rests on is really in the official page and carries the point's figures.

The letter itself is never rewritten: a small local model reads a neighbouring case (the
increased fine, a furnished let) as the rule often enough that a silent correction would be
worse than none. A point the source contradicts is shown with the source's own sentence and a
proposed wording the user can apply; a point that could not be checked (offline, web search
off, no model, sources silent) is shown as such, with the sources found.

Results are kept a week per point: the same template does not trigger the same searches for
every letter.
"""

import json
import logging
import re
from datetime import date, timedelta
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from binder import i18n
from binder.schemas import LegalCheck, LegalPoint, LegalSource
from binder.services import llm, settings_store, websearch
from binder.services.rules import normalize

log = logging.getLogger(__name__)

CACHE_KEY = "lawcheck.cache"
CACHE_DAYS = 7
# Points checked per text, and sources read per point: each costs a search and a model turn.
MAX_POINTS = 4
MAX_SOURCES = 2
# Page text read per source, then cut down to the passages about the point.
PAGE_CHARS = 30000
EXCERPT_CHARS = 2500

# Official publishers of law and procedures, preferred over law firms' and insurers' blogs.
OFFICIAL = (
    ".gouv.fr", "legifrance.gouv.fr", "service-public.fr", "ameli.fr", "caf.fr",
    "urssaf.fr", "anil.org", "conseil-etat.fr", "courdecassation.fr", "belgium.be",
    "fgov.be", "ejustice.just.fgov.be", "public.lu", "guichet.lu", "legilux.public.lu",
    "legimonaco.mc", "gouv.mc", "admin.ch", "gov.uk", "legislation.gov.uk",
)  # fmt: skip

# Searched first: official publishers of law and procedures, by country.
# (Légifrance refuses automated reading; service-public.gouv.fr quotes the articles in force.)
OFFICIAL_SEARCH = {
    "FR": ("service-public.gouv.fr",),
    "BE": ("ejustice.just.fgov.be", "belgium.be"),
    "LU": ("legilux.public.lu", "guichet.lu"),
    "MC": ("legimonaco.mc",),
}
# Words of a law reference, left out of an official site's search by subject.
LAW_WORDS = {
    "article", "articles", "art", "loi", "law", "code", "decret", "decree", "du", "de", "des",
    "la", "n", "no", "of", "the",
}  # fmt: skip
# A sentence citing the law, for texts checked without a model.
LEGAL = re.compile(
    r"\barticles?\s+[LRD]?\.?\s?\d[\d-]*|\bloi\s+n|\blaw\s+no|\bd[ée]cret\b|\bdecree\b|"
    r"\bcode\s+(?:des|de la|du|de l'|civil|p[ée]nal)|\b(?:insurance|civil|consumer)\s+code\b",
    re.IGNORECASE,
)
# The reference itself, searched as it is: "article L113-15-2 du Code des assurances".
REFERENCE = re.compile(
    r"\barticles?\s+[LRD]?\.?\s?\d[\d-]*(?:\s+(?:du|de la|de l'|of the(?: French)?)\s+"
    r"[A-Za-zÀ-ÿ' ]+?(?=[;,.()]|\s+(?:la|le|the|prendra|will)\b|$))?|"
    r"\b(?:loi|law)\s+n[o°]\.?\s*[\d-]+(?:\s+(?:du|of)\s+\d{1,2}\s+\w+\s+\d{4})?",
    re.IGNORECASE,
)

Status = Literal["verified", "outdated", "unverified", "none"]
Source = LegalSource
Point = LegalPoint
Verification = LegalCheck


class _Cached(BaseModel):
    checked_on: date
    point: Point


class _Cache(BaseModel):
    points: dict[str, _Cached] = {}


EXTRACT_PROMPT = """List the legal points of this text: statements of law, rights, legal \
delays or notice periods, rates, thresholds or official procedures (not facts about the \
person or their contract). Country: {country}.
Return JSON: points, each with claim (the sentence exactly as written in the text) and query \
(a short web search to check it, in the text's language, general terms only: the subject \
and the law or article, without the figures to check, never a name, address, amount, date or \
reference of the person). At most {limit} points; an \
empty list if there are none.
Text:
\"\"\"
{text}
\"\"\""""
EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"claim": {"type": "string"}, "query": {"type": "string"}},
                "required": ["claim", "query"],
            },
        }
    },
    "required": ["points"],
}

JUDGE_PROMPT = """Check a legal point against the sources below, as of today ({today}). \
Country: {country}.
Point: {claim}
{sources}
A source may show a past version of a text: rely on the version in force today. Compare every \
figure of the point (delays, rates, amounts) with the sources.
Return JSON: status ("confirmed": the sources state it, figures included, and it is in force \
today; "outdated": the sources state something different, or that it was repealed; \
"not_found": the sources do not say), evidence (the sentence of the source that decides, \
copied word for word; empty if not_found), source (its number, 0 if none), correction (only \
when outdated: the point rewritten as the law stands today, from the evidence, ready to \
replace it in a letter: in {language} whatever the sources' language, same tone and person \
("je" stays "je"), keeping its details that are still right, with no mention of what changed; \
one sentence)."""
JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["confirmed", "outdated", "not_found"]},
        "evidence": {"type": "string"},
        "source": {"type": "integer"},
        "correction": {"type": "string"},
    },
    "required": ["status", "evidence", "source"],
}


class _Judged(BaseModel):
    status: Literal["confirmed", "outdated", "not_found"]
    evidence: str = ""
    source: int = 0
    correction: str = ""


# Figures of a legal point, compared with the source: "trois mois" against "un mois".
NUMBER_WORDS = {
    "deux": "2", "trois": "3", "quatre": "4", "cinq": "5", "six": "6", "sept": "7",
    "huit": "8", "neuf": "9", "dix": "10", "onze": "11", "douze": "12", "quinze": "15",
    "vingt": "20", "trente": "30", "quarante-cinq": "45", "soixante": "60", "two": "2",
    "three": "3", "four": "4", "five": "5", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "twelve": "12", "fifteen": "15", "twenty": "20", "thirty": "30",
}  # fmt: skip


def figures(text: str) -> set[str]:
    """Numbers a text states, written in digits or words, without the law references it
    cites ("article 22 de la loi n° 89-462" are not figures of the point)."""
    norm = normalize(REFERENCE.sub(" ", text))
    found = set(re.findall(r"\d+(?:[.,]\d+)?", norm.replace(" ", "").replace(" %", "%")))
    found |= {NUMBER_WORDS[w] for w in re.findall(r"[a-z]+(?:-[a-z]+)?", norm) if w in NUMBER_WORDS}
    return {f.replace(",", ".") for f in found}


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", normalize(text)).strip(" .;:\"'«»")


def _supported(judged: _Judged, claim: str, page: str) -> bool:
    """The verdict holds only if its evidence is really in the source and carries the figures
    of what it confirms or of the correction (small models also judge from memory)."""
    evidence = _flat(judged.evidence)
    if len(evidence) < 20 or evidence not in _flat(page):
        return False
    stated = figures(judged.correction if judged.status == "outdated" else claim)
    return stated <= figures(judged.evidence)


def _read(results: list[websearch.Result], pages: list[tuple[Source, str]]) -> None:
    """Adds the readable pages of the results, best first (some official sites, Légifrance
    among them, refuse automated reading: the next one is read instead)."""
    for result in sorted(results, key=_rank):
        if len(pages) >= MAX_SOURCES:
            return
        if any(src.url == result.url for src, _ in pages):
            continue
        try:
            _, body = websearch.read_page(result.url, PAGE_CHARS)
        except (ValueError, httpx.HTTPError):
            continue
        if body:
            pages.append((Source(title=result.title, url=result.url), body))


def _rank(result: websearch.Result) -> tuple[bool, int]:
    """Official sources first; on Légifrance, the version in force (no date) then the most
    recent ones: URLs of past versions end with their date (…/LEGIARTI000028806696/2017-01-29)."""
    version = re.search(r"/(\d{4})-(\d{2})-(\d{2})/?$", result.url)
    age = -int("".join(version.groups())) if version else -99999999
    return not official(result.url), age


def official(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d.lstrip(".") or host.endswith("." + d.lstrip(".")) for d in OFFICIAL)


def _sentences(text: str) -> list[str]:
    # Not after "no." or "art.": a sentence starts with a capital letter.
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý])|\n+", text) if s.strip()]


def references(sentence: str) -> str:
    """The laws and articles a sentence cites, as a search: "article 22 law no. 89-462…"."""
    return " ".join(m[0].strip() for m in REFERENCE.finditer(sentence))


def _extract_rules(text: str) -> list[tuple[str, str]]:
    """Sentences citing the law, searched by the reference they cite."""
    found = []
    for sentence in _sentences(text):
        if LEGAL.search(sentence):
            found.append((sentence, references(sentence) or sentence[:120]))
    return found[:MAX_POINTS]


def _extract_llm(text: str) -> list[tuple[str, str]] | None:
    prompt = EXTRACT_PROMPT.format(
        country=llm.user_context()["country"], limit=MAX_POINTS, text=text[:6000]
    )
    try:
        reply = llm.chat([{"role": "user", "content": prompt}], fmt=EXTRACT_SCHEMA)
        points = json.loads(reply.get("content") or "{}").get("points") or []
    except (httpx.HTTPError, llm.ModelError, json.JSONDecodeError, KeyError, AttributeError):
        log.exception("Legal points could not be listed by the model")
        return None
    found = []
    for item in points:
        if isinstance(item, dict) and item.get("claim") and item.get("query"):
            found.append((str(item["claim"]).strip(), str(item["query"]).strip()))
    return found[:MAX_POINTS]


def excerpt(body: str, claim: str) -> str:
    """The part of a page about the point: around the paragraph sharing most of its words."""
    words = {w for w in re.findall(r"[a-z0-9]{4,}", normalize(claim))}
    paragraphs = body.split("\n")
    if not words or len(body) <= EXCERPT_CHARS:
        return body[:EXCERPT_CHARS]
    scores = [len(words & set(re.findall(r"[a-z0-9]{4,}", normalize(p)))) for p in paragraphs]
    best = max(range(len(paragraphs)), key=lambda i: scores[i])
    start = sum(len(p) + 1 for p in paragraphs[:best])
    start = max(0, start - EXCERPT_CHARS // 4)
    return body[start : start + EXCERPT_CHARS]


def _judge(claim: str, pages: list[tuple[Source, str]]) -> _Judged | None:
    sources = "\n".join(
        f'[{i}] {src.url}\n"""\n{excerpt(body, claim)}\n"""'
        for i, (src, body) in enumerate(pages, 1)
    )
    prompt = JUDGE_PROMPT.format(
        today=date.today().isoformat(),
        country=llm.user_context()["country"],
        claim=claim,
        sources=sources,
        # The text's language (letters: the recipient's, set by letters.compose).
        language=i18n.language_name(i18n.current_language()),
    )
    try:
        # No reasoning step: as accurate here once the evidence is checked, and minutes faster.
        reply = llm.chat([{"role": "user", "content": prompt}], fmt=JUDGE_SCHEMA)
        return _Judged.model_validate(json.loads(reply.get("content") or "{}"))
    except (httpx.HTTPError, llm.ModelError, json.JSONDecodeError, ValidationError, KeyError):
        log.exception("Legal point could not be judged")
        return None


def _search(
    session: Session, claim: str, query: str, site: str | None = None
) -> list[websearch.Result] | None:
    """Results for the point, on one official site or the whole web; None when unreachable.
    A query the model wrote with a detail about the user is replaced by the law reference."""

    def run(q: str) -> list[websearch.Result]:
        if site in websearch.SITE_SEARCHES:
            return websearch.search_site(session, site, q)
        return websearch.search(session, f"{q} site:{site}" if site else q)

    try:
        return run(query)
    except websearch.PersonalData:
        ref = references(claim)
        try:
            return run(ref) if ref else []
        except websearch.PersonalData:
            return []
    except httpx.HTTPError:
        return None


def subject(query: str) -> str:
    """A query without its law references, for an official site's own search engine, which
    finds its guides by subject ("délai restitution caution location"), not by article."""
    words = REFERENCE.sub(" ", query).split()
    kept = [w for w in words if not re.search(r"\d", w) and normalize(w) not in LAW_WORDS]
    return " ".join(kept) or query


def _verdict(claim: str, pages: list[tuple[Source, str]]) -> tuple[_Judged, Source] | None:
    """The model's verdict and the source it rests on, when that source backs it."""
    judged = _judge(claim, pages)
    if judged is None or judged.status == "not_found" or not 1 <= judged.source <= len(pages):
        return None
    used, page = pages[judged.source - 1]
    if not _supported(judged, claim, page):
        log.info("Verdict on a legal point not backed by its source: %s", judged)
        return None
    if judged.status == "outdated" and not judged.correction.strip():
        return None
    return judged, used


def check_point(session: Session, claim: str, query: str) -> Point:
    """One point looked up and judged; `unverified` whenever any step is missing or the
    verdict is not backed by an official source."""
    point = Point(claim=claim, status="unverified")
    if not websearch.enabled():
        return point
    # The country's official publishers first (their own search, by subject), then the whole
    # web: law firms' pages often lead to the official text.
    sites = OFFICIAL_SEARCH.get((i18n.current_country() or "").upper(), ())
    queries = [(site, subject(query)) for site in sites] + [(None, query)]
    results: list[websearch.Result] = []
    read: list[tuple[Source, str]] = []
    for site, search in queries:
        found = _search(session, claim, search, site)
        if found is None:
            continue  # unreachable (or the search engine refused): the next source
        results += found
        if not llm.is_available():
            continue
        pages: list[tuple[Source, str]] = []
        _read(
            [r for r in found if official(r.url) and r.url not in {s.url for s, _ in read}], pages
        )
        read += pages
        verdict = _verdict(claim, pages) if pages else None
        if verdict is None:
            continue
        judged, used = verdict
        point.sources = [used] + [s for s, _ in pages if s.url != used.url]
        point.status = "outdated" if judged.status == "outdated" else "confirmed"
        point.evidence = judged.evidence.strip()
        if judged.status == "outdated":
            point.correction = judged.correction.strip()
        return point
    listed = [Source(title=r.title, url=r.url) for r in sorted(results, key=_rank)]
    point.sources = ([src for src, _ in read] or listed)[:MAX_SOURCES]
    return point


def _cached(session: Session, claim: str, query: str) -> Point:
    cache = settings_store.load(session, CACHE_KEY, _Cache)
    key = normalize(claim).strip()
    today = date.today()
    hit = cache.points.get(key)
    if hit is not None and today - hit.checked_on < timedelta(days=CACHE_DAYS):
        return hit.point.model_copy(update={"claim": claim})
    point = check_point(session, claim, query)
    if point.status != "unverified":
        # Unverified points are tried again next time (back online, model ready).
        cache.points = {
            k: v for k, v in cache.points.items() if today - v.checked_on < timedelta(CACHE_DAYS)
        }
        cache.points[key] = _Cached(checked_on=today, point=point)
        settings_store.save(session, CACHE_KEY, cache)
    return point


def verify(session: Session, text: str) -> Verification:
    """Every legal point of `text` checked online today; the text is not changed."""
    # Web search off: nothing can be checked, the model is not asked to list the points.
    online = websearch.enabled()
    found = _extract_llm(text) if online and llm.is_available() else None
    if found is None:
        found = _extract_rules(text)
    points = [_cached(session, claim, query) for claim, query in found]
    if not points:
        status: Status = "none"
    elif any(p.status == "outdated" for p in points):
        status = "outdated"
    elif any(p.status == "unverified" for p in points):
        status = "unverified"
    else:
        status = "verified"
    return Verification(status=status, checked_on=date.today(), points=points)
