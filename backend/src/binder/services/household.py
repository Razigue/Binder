"""Household members, detected from the documents themselves.

Each document may name the person it concerns: the holder of an identity card, the employee
on a payslip, the tenant on a rent receipt, the insured person… The local model reads it
(extraction field `person`); the patterns below fill in when it is absent. Members are the
distinct people found; "M. Martin" joins "Camille Martin" when only one Martin is known.
The user corrects that list (add, rename or merge, remove): their edits win over the reading.
"""

import re
from collections import Counter

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.models import Document
from binder.services import activity, areas, settings_store, undo
from binder.services.rules import normalize

T = i18n.catalog(
    "household",
    {
        "added": {
            "en": "{name} added to the household",
            "fr": "{name} ajouté(e) au foyer",
        },
        "removed": {
            "en": "{name} is no longer part of the household",
            "fr": "{name} ne fait plus partie du foyer",
        },
        "renamed": {"en": "“{old}” renamed “{new}”", "fr": "« {old} » renommé « {new} »"},
    },
)

EDITS_KEY = "household"

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
    """ "MARTIN Camille", "camille martin" → "Camille Martin"; "MARTIN-LEROY" → "Martin-Leroy"."""
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    return " ".join(
        "-".join(w[:1].upper() + w[1:].lower() for w in p.split("-"))
        if p.isupper() or p.islower()
        else p
        for p in parts
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


def _id(name: str) -> str:
    return " ".join(_key(name))


class Member(BaseModel):
    name: str
    documents: int
    areas: list[str]
    # Added by the user (not, or not yet, named in a document).
    added: bool = False


class Edits(BaseModel):
    """The user's corrections to the household Binder found."""

    # Spellings replaced by the user's (`_id` of the spelling → name): later documents follow.
    renamed: dict[str, str] = {}
    # People named in documents who are not in the household (a landlord, a doctor…), by `_id`.
    removed: list[str] = []
    # Members the user added.
    added: list[str] = []


class UnknownMember(ValueError):
    pass


def load_edits(session: Session) -> Edits:
    return settings_store.load(session, EDITS_KEY, Edits)


def canonical(session: Session, name: str | None) -> str | None:
    """A name as the user wrote it, when they corrected that spelling."""
    if not name:
        return name
    return load_edits(session).renamed.get(_id(name), name)


def _found(session: Session) -> tuple[list[Member], dict[str, str]]:
    """Distinct people named in the active documents, and the member each spelling belongs to."""
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
    owner: dict[str, str] = {}
    for key, names in full.items():
        # The fullest spelling names the member.
        name = max(names, key=lambda n: (len(n.split()), names[n]))
        owner.update(dict.fromkeys(names, name))
        out.append(
            Member(
                name=name,
                documents=sum(names.values()),
                areas=[a for a in areas.AREAS if a in found_areas.get(key, set())],
            )
        )
    return out, owner


def members(session: Session, *, everyone: bool = False) -> list[Member]:
    """The household, most documents first: the people named in the documents, as the user
    corrected it. `everyone` keeps the people the user said are not in it."""
    found, _ = _found(session)
    edits = load_edits(session)
    out = [m for m in found if everyone or _id(m.name) not in edits.removed]
    out.extend(
        Member(name=name, documents=0, areas=[], added=True)
        for name in edits.added
        if not any(same_person(name, m.name) for m in found)
    )
    return sorted(out, key=lambda m: -m.documents)


def main_person(session: Session) -> str | None:
    """The member named on most documents: the sender of letters by default."""
    found = members(session)
    full = [m for m in found if len(m.name.split()) >= 2]
    return (full or found)[0].name if found else None


def _save(session: Session, edits: Edits, msg: i18n.Msg) -> None:
    undo.setting_changed(session, EDITS_KEY)
    settings_store.save(session, EDITS_KEY, edits)
    activity.log(session, "settings", msg)


def add(session: Session, name: str) -> None:
    """Adds someone to the household (or takes them back after a removal)."""
    name = display(name)
    if not name:
        raise UnknownMember(name)
    edits = load_edits(session)
    edits.removed = [r for r in edits.removed if r != _id(name)]
    if not any(same_person(name, a) for a in edits.added):
        edits.added.append(name)
    _save(session, edits, T.msg("added", name=name))


def remove(session: Session, name: str) -> None:
    """Not in the household: no longer listed, nor taken as the user. Their documents stay as
    they are (they do concern that person)."""
    if not any(m.name == name for m in members(session)):
        raise UnknownMember(name)
    edits = load_edits(session)
    edits.added = [a for a in edits.added if a != name]
    if _id(name) not in edits.removed:
        edits.removed.append(_id(name))
    _save(session, edits, T.msg("removed", name=name))


def rename(session: Session, old: str, new: str) -> int:
    """Corrects a member's name on their documents, and for the documents to come. Giving the
    name of another member merges both. Returns how many documents changed."""
    new = display(new)
    if not new or not any(m.name == old for m in members(session)):
        raise UnknownMember(old)
    _, owner = _found(session)
    spellings = [s for s, member in owner.items() if member == old]
    changed = 0
    if spellings:
        docs = session.exec(
            select(Document).where(
                col(Document.deleted_at).is_(None), col(Document.person).in_(spellings)
            )
        )
        for doc in docs:
            if doc.person == new:
                continue
            before = undo.snapshot(doc)
            doc.person = new
            undo.document_changed(doc, before)
            session.add(doc)
            changed += 1
    edits = load_edits(session)
    # Names that led to the old one now lead to the new one, and so do its spellings.
    edits.renamed = {k: new if v == old else v for k, v in edits.renamed.items()}
    for spelling in {*spellings, old}:
        if _id(spelling) != _id(new):
            edits.renamed[_id(spelling)] = new
    edits.renamed.pop(_id(new), None)
    edits.added = [new if a == old else a for a in edits.added]
    edits.removed = [r for r in edits.removed if r != _id(new)]
    _save(session, edits, T.msg("renamed", old=old, new=new))
    return changed


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
