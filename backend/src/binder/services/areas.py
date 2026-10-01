"""Life areas: the seven places the interface files paperwork under.

Categories stay the fine-grained classification (rules, retention, folders); areas are what the
user browses: Housing, Money, Work & benefits, Family, Health, Identity, Vehicle. Insurance goes
where the insured thing lives (home, car, health); a document still uncategorised has no area
until the user answers the question Binder asks about it.
"""

from typing import Literal

from sqlmodel import Session, col, select

from binder import i18n
from binder.models import Category, Document
from binder.services.rules import normalize

Area = Literal["housing", "money", "work", "family", "health", "identity", "vehicle"]
AREAS: tuple[Area, ...] = ("housing", "money", "work", "family", "health", "identity", "vehicle")

T = i18n.catalog(
    "areas",
    {
        "housing": {"en": "Housing", "fr": "Logement"},
        "money": {"en": "Money", "fr": "Argent"},
        "work": {"en": "Work & benefits", "fr": "Travail & aides"},
        "family": {"en": "Family", "fr": "Famille"},
        "health": {"en": "Health", "fr": "Santé"},
        "identity": {"en": "Identity", "fr": "Identité"},
        "vehicle": {"en": "Vehicle", "fr": "Véhicule"},
    },
)

BY_CATEGORY: dict[Category, Area] = {
    Category.HOUSING: "housing",
    Category.ENERGY: "housing",
    Category.TELECOM: "housing",
    Category.TAXES: "money",
    Category.BANK: "money",
    Category.INSURANCE: "money",
    Category.PURCHASES: "money",
    Category.FAMILY: "family",
    Category.WORK: "work",
    Category.SOCIAL: "work",
    Category.HEALTH: "health",
    Category.IDENTITY: "identity",
    Category.VEHICLE: "vehicle",
}
# Category given to a document the user files under an area (answer to "Where does it go?").
DEFAULT_CATEGORY: dict[Area, Category] = {
    "housing": Category.HOUSING,
    "money": Category.BANK,
    "work": Category.WORK,
    "family": Category.FAMILY,
    "health": Category.HEALTH,
    "identity": Category.IDENTITY,
    "vehicle": Category.VEHICLE,
}
# Insurance documents follow what they insure (normalized words of the document).
INSURED: list[tuple[tuple[str, ...], Area]] = [
    (("assurance auto", "vehicule", "immatriculation", "automobile", "car insurance"), "vehicle"),
    (("habitation", "multirisque", "logement", "home insurance"), "housing"),
    (("mutuelle", "complementaire sante", "prevoyance", "health insurance"), "health"),
]


def label(area: str, language: i18n.Language | None = None) -> str:
    return T.get(area, language) if language else T(area)


def area_of(doc: Document) -> Area | None:
    if doc.category == Category.INSURANCE:
        words = normalize(f"{doc.title} {doc.issuer or ''} {doc.text[:3000]}")
        for keys, area in INSURED:
            if any(k in words for k in keys):
                return area
    return BY_CATEGORY.get(doc.category)


def backfill(session: Session) -> None:
    """Documents filed before areas existed get theirs (once, at startup)."""
    stmt = select(Document).where(col(Document.area).is_(None), Document.category != Category.OTHER)
    for doc in session.exec(stmt):
        doc.area = area_of(doc)
        session.add(doc)
    session.commit()


def categories_of(area: Area) -> list[Category]:
    return [c for c, a in BY_CATEGORY.items() if a == area]
