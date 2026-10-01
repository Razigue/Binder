"""Household members, detected from the documents themselves.

Each document may name the person it concerns: the holder of an identity card, the employee
on a payslip, the tenant on a rent receipt, the insured person… The local model reads it
(extraction field `person`); the patterns below fill in when it is absent. Members are the
distinct people found; "M. Martin" joins "Camille Martin" when only one Martin is known.
"""

import re
from collections import Counter

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder.models import Document
from binder.services import areas
from binder.services.rules import normalize

_NAME = r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’-]+"
# "Nom : MARTIN — Prénom : Camille" (identity documents).
_NAME_FIRST = re.compile(
    rf"\bNom\s*:\s*({_NAME}(?:[ \t]{_NAME})?)\s*[—–\-,;]?\s*Pr[ée]noms?\s*:\s*({_NAME})"
)
# "Salarié : Camille Martin", "Locataire : M. Martin"…
_ROLE = re.compile(
    r"\b(?:Salari[ée]e?|Locataire|Allocataire|B[ée]n[ée]ficiaire|Assur[ée]e?|Titulaire|"
    r"Souscripteur|Contribuable|D[ée]clarant(?:\s1)?|Patient|Employ[ée]e?)\s*:\s*"
    rf"(?:M\.|Mme|Mlle|Monsieur|Madame)?[ \t]*((?:{_NAME}[ \t]){{0,2}}{_NAME})"
)
# "M. Martin est assuré", "Madame Camille MARTIN".
_CIVILITY = re.compile(rf"\b(?:M\.|Mme|Mlle|Monsieur|Madame)[ \t]+((?:{_NAME}[ \t])?{_NAME})")
# Words that follow a civility without being a name ("Madame, Monsieur").
_NOT_NAMES = {"monsieur", "madame", "le", "la", "les", "votre", "vous"}


def display(name: str) -> str:
    """ "MARTIN Camille", "camille martin" → "Camille Martin"."""
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    return " ".join(
        p[:1].upper() + p[1:].lower() if p.isupper() or p.islower() else p for p in parts
    )


def detect(text: str) -> str | None:
    """Person a document concerns, from its text (rules)."""
    m = _NAME_FIRST.search(text)
    if m:
        return display(f"{m[2]} {m[1]}")
    for pattern in (_ROLE, _CIVILITY):
        for m in pattern.finditer(text):
            name = m[1].strip()
            if normalize(name.split()[0]) not in _NOT_NAMES:
                return display(name)
    return None


def _key(name: str) -> tuple[str, ...]:
    return tuple(sorted(normalize(name).replace("-", " ").split()))


class Member(BaseModel):
    name: str
    documents: int
    areas: list[str]


def members(session: Session) -> list[Member]:
    """Distinct people named in the active documents, most documents first."""
    rows = session.exec(
        select(Document.person, Document.area).where(
            col(Document.deleted_at).is_(None), col(Document.person).is_not(None)
        )
    ).all()
    full: dict[tuple[str, ...], Counter[str]] = {}
    found_areas: dict[tuple[str, ...], set[str]] = {}
    alone: list[tuple[str, str | None]] = []
    for person, area in rows:
        assert person is not None
        key = _key(person)
        if len(key) < 2:
            alone.append((person, area))
            continue
        full.setdefault(key, Counter())[person] += 1
        if area:
            found_areas.setdefault(key, set()).add(area)
    for person, area in alone:
        surname = normalize(person)
        owners = [k for k in full if surname in k]
        key = owners[0] if len(owners) == 1 else (surname,)
        full.setdefault(key, Counter())[person] += 1
        if area:
            found_areas.setdefault(key, set()).add(area)
    out = []
    for key, names in full.items():
        # The fullest spelling names the member.
        name = max(names, key=lambda n: (len(n.split()), names[n]))
        out.append(
            Member(
                name=name,
                documents=sum(names.values()),
                areas=[a for a in areas.AREAS if a in found_areas.get(key, set())],
            )
        )
    return sorted(out, key=lambda m: -m.documents)


def main_person(session: Session) -> str | None:
    """The member named on most documents: the sender of letters by default."""
    found = members(session)
    full = [m for m in found if len(m.name.split()) >= 2]
    return (full or found)[0].name if found else None


def same_person(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    ka, kb = set(_key(a)), set(_key(b))
    return ka <= kb or kb <= ka


_ADDRESS = re.compile(
    r"(\d{1,4}(?:\s?(?:bis|ter))?,?\s+(?:rue|avenue|av\.|boulevard|bd|place|chemin|all[ée]e|"
    r"impasse|route|quai|cours|square|r[ée]sidence|lotissement)\s+[^\n,]{2,60}?)[,\s]+"
    r"(\d{5})\s+([A-ZÀ-Ÿa-zà-ÿ][A-Za-zÀ-ÿ' -]{1,40}?)(?=[\s.,;)]|$)",
    re.IGNORECASE | re.MULTILINE,
)


def addresses_in(text: str) -> list[tuple[str, str]]:
    """Postal addresses written in a text: [(street, "69003 Lyon")]."""
    found = []
    for m in _ADDRESS.finditer(text):
        street = re.sub(r"\s+", " ", m[1]).strip()
        town = f"{m[2]} {display(m[3].strip())}"
        found.append((street, town))
    return found


def home_address(session: Session, *, at_least: int = 1) -> tuple[str, str] | None:
    """The household's address: the one written on most documents (bills, receipts…), and on
    `at_least` of them."""
    counts: Counter[tuple[str, str]] = Counter()
    spelling: dict[tuple[str, str], tuple[str, str]] = {}
    for text in session.exec(select(Document.text).where(col(Document.deleted_at).is_(None))):
        for street, town in dict.fromkeys(addresses_in(text)):
            key = (normalize(street), normalize(town))
            counts[key] += 1
            spelling.setdefault(key, (street, town))
    if not counts:
        return None
    key, count = counts.most_common(1)[0]
    return spelling[key] if count >= at_least else None


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Mobile numbers only: landlines and short numbers in documents belong to the issuers.
_MOBILE = re.compile(r"(?<![\d+])(?:\+33\s?|0033\s?|0)([67](?:[\s.-]?\d{2}){4})(?![\d])")
# Addresses of organisations, not of a person.
_SERVICE = re.compile(
    r"no-?reply|ne-?pas-?repondre|contact|service|client|support|info|dpo|rgpd|courrier|"
    r"reclamation|facturation|bonjour|hello|admin|accueil|webmaster",
    re.IGNORECASE,
)


def contact_details(session: Session) -> dict[str, str]:
    """The household's own email and mobile number: the ones written in documents from at
    least two different issuers (an issuer's contact details only appear in its own)."""
    seen: dict[str, dict[str, set[str]]] = {"email": {}, "phone": {}}
    rows = session.exec(
        select(Document.text, Document.issuer).where(col(Document.deleted_at).is_(None))
    )
    for text, issuer in rows:
        source = normalize(issuer or "") or text[:80]
        for email in _EMAIL.findall(text):
            if not _SERVICE.search(email.split("@")[0]):
                seen["email"].setdefault(email.lower(), set()).add(source)
        for digits in _MOBILE.findall(text):
            number = "0" + re.sub(r"\D", "", digits)
            seen["phone"].setdefault(" ".join(re.findall(r"\d{2}", number)), set()).add(source)
    found = {}
    for field, values in seen.items():
        shared = [(len(sources), value) for value, sources in values.items() if len(sources) >= 2]
        if shared:
            found[field] = max(shared)[1]
    return found
