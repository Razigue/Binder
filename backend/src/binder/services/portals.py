"""Where to fetch a paper online: the user's account on the issuer's website.

Most French papers are no longer posted: the tax notice, the CAF certificates or a bill wait in
an online account. A card that says "missing" is only half useful without the way to get it, so
each one carries a link when Binder knows where to look:

- the public services, from a short static list (stable home pages, never deep links that move);
- any other issuer, from the website printed on its own documents ("espace client sur edf.fr"),
  kept only when the address names the issuer.

Only a link is shown: the user opens it in their browser, nothing is sent from Binder.
"""

import re
from dataclasses import dataclass

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder.db import in_use
from binder.models import DocType, Document
from binder.services.rules import normalize


class Portal(BaseModel):
    name: str
    url: str


@dataclass(frozen=True)
class Public:
    name: str
    url: str
    # Issuer names that point to this service (normalised, matched as words).
    issuers: tuple[str, ...]
    doc_types: tuple[str, ...] = ()


PUBLIC: dict[str, Public] = {
    "impots": Public(
        "impots.gouv.fr",
        "https://www.impots.gouv.fr",
        ("dgfip", "finances publiques", "impots", "tresor public", "sip"),
        (DocType.TAX_NOTICE, DocType.PROPERTY_TAX, DocType.HOUSING_TAX),
    ),
    "caf": Public("caf.fr", "https://www.caf.fr", ("caf", "allocations familiales")),
    "ameli": Public(
        "ameli.fr",
        "https://www.ameli.fr",
        ("cpam", "ameli", "assurance maladie"),
        (DocType.REIMBURSEMENT_STATEMENT,),
    ),
    "france_travail": Public(
        "francetravail.fr", "https://www.francetravail.fr", ("france travail", "pole emploi")
    ),
    "retraite": Public(
        "info-retraite.fr",
        "https://www.info-retraite.fr",
        ("carsat", "cnav", "agirc", "arrco", "assurance retraite"),
        (DocType.PENSION_STATEMENT,),
    ),
    "ants": Public(
        "ants.gouv.fr",
        "https://ants.gouv.fr",
        ("ants", "prefecture"),
        (DocType.VEHICLE_REGISTRATION, DocType.DRIVING_LICENCE),
    ),
    "etudiant": Public(
        "messervices.etudiant.gouv.fr",
        "https://messervices.etudiant.gouv.fr",
        ("crous",),
    ),
}

# A website as documents print it: "edf.fr", "www.free.fr", "https://particulier.edf.fr/…".
WEBSITE = re.compile(
    r"(?<![@\w.-])(?:https?://)?((?:[a-z0-9-]+\.)+(?:fr|com|net|eu|be|lu))\b(?![@\w-])",
    re.IGNORECASE,
)
# Short words that would match too many websites.
MIN_TOKEN = 3
# Documents of an issuer read to find its website (the most recent first).
LOOK_AT = 3


def public(key: str) -> Portal:
    service = PUBLIC[key]
    return Portal(name=service.name, url=service.url)


def _words(text: str) -> str:
    return f" {' '.join(re.split(r'[^a-z0-9]+', normalize(text)))} "


def _public_for(issuer: str | None, doc_type: str | None) -> Portal | None:
    words = _words(issuer or "")
    for key, service in PUBLIC.items():
        if doc_type in service.doc_types or any(f" {i} " in words for i in service.issuers):
            return public(key)
    return None


def _names_issuer(host: str, issuer: str) -> bool:
    """The website belongs to the issuer: one of its labels is a word of the issuer's name
    ("edf.fr" for "EDF", "bouyguestelecom.fr" for "Bouygues Telecom")."""
    tokens = [t for t in _words(issuer).split() if len(t) >= MIN_TOKEN]
    if not tokens:
        return False
    labels = host.lower().split(".")[:-1]
    squashed = "".join(tokens)
    return any(label in tokens or label == squashed for label in labels)


def website(text: str, issuer: str) -> Portal | None:
    """The issuer's own website among the addresses written in its document."""
    for match in WEBSITE.finditer(text):
        host = match.group(1).lower()
        if _names_issuer(host, issuer):
            bare = host.removeprefix("www.")
            return Portal(name=bare, url=f"https://{host}")
    return None


def find(session: Session, issuer: str | None, doc_type: str | None = None) -> Portal | None:
    """Where to fetch the next paper of this issuer (or of this type), if Binder knows."""
    known = _public_for(issuer, doc_type)
    if known or not issuer:
        return known
    texts = session.exec(
        select(Document.text)
        .where(in_use(), Document.issuer == issuer)
        .order_by(col(Document.issue_date).desc(), col(Document.id).desc())
        .limit(LOOK_AT)
    ).all()
    for text in texts:
        found = website(text or "", issuer)
        if found:
            return found
    return None
