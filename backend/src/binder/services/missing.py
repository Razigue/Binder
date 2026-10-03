"""Documents that should be there and are not.

- A recurring bill that has not arrived when the next one was expected.
- A gap in the payslips, and last month's payslip once it is out.
- A yearly document published online on known dates (tax notice, property tax), from the day it
  is out: when last year's is filed, or when the papers show the user is concerned (payslips of
  last year for a first tax notice, an owner for the property tax).
- An insurance certificate past its end date, with no newer one.
- The essentials every application asks for (identity document, bank details).

Each carries, when Binder knows it, the online account to fetch it from (services/portals.py).
"""

from datetime import date, timedelta

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT, in_use
from binder.models import DocType, Document
from binder.services import areas, portals, profile, subscriptions
from binder.services.areas import Area
from binder.services.deadlines import document_date
from binder.services.portals import Portal

T = i18n.catalog(
    "missing",
    {
        "late_title": {
            "en": "{label}: {month} bill not received",
            "fr": "{label} : facture de {month} pas reçue",
        },
        "late_detail": {
            "en": "It usually arrives around {expected:date}. Download it from your customer "
            "account, or forward the email it came with.",
            "fr": "Elle arrive d'habitude vers le {expected:date}. Téléchargez-la dans votre "
            "espace client, ou transférez l'e-mail qui l'accompagnait.",
        },
        "payslip_title": {
            "en": "Payslip for {month} missing",
            "fr": "Bulletin de paie de {month} manquant",
        },
        "payslip_detail": {
            "en": "Keep every payslip until you retire. Ask your employer or download it from "
            "your HR document portal.",
            "fr": "Chaque bulletin se garde jusqu'à la retraite. Demandez-le à votre employeur ou "
            "téléchargez-le sur votre coffre-fort RH.",
        },
        "payslip_letter": {
            "en": "Ask my employer for a copy of my payslip for {month}",
            "fr": "Demander à mon employeur une copie de mon bulletin de paie de {month}",
        },
        "payslip_out_title": {
            "en": "Your {month} payslip is out",
            "fr": "Votre bulletin de paie de {month} est sorti",
        },
        "payslip_out_detail": {
            "en": "Download it from your employer's HR portal, or forward the email it came "
            "with: keep every payslip until you retire.",
            "fr": "Téléchargez-le sur le coffre-fort RH de votre employeur, ou transférez "
            "l'e-mail qui l'accompagnait : chaque bulletin se garde jusqu'à la retraite.",
        },
        "tax_title": {
            "en": "Tax notice {year}: fetch it",
            "fr": "Avis d'impôt {year} : à récupérer",
        },
        "tax_detail": {
            "en": "It is online in your impots.gouv.fr account since the summer. It proves your "
            "income for a rental, a loan or the CAF.",
            "fr": "Il est en ligne dans votre espace impots.gouv.fr depuis l'été. Il prouve vos "
            "revenus pour une location, un prêt ou la CAF.",
        },
        "property_title": {
            "en": "Property tax {year}: fetch it",
            "fr": "Taxe foncière {year} : à récupérer",
        },
        "property_detail": {
            "en": "It is online in your impots.gouv.fr account from the end of August, to pay "
            "around 15 October.",
            "fr": "Elle est en ligne dans votre espace impots.gouv.fr dès fin août, à payer vers "
            "le 15 octobre.",
        },
        "certificate_title": {
            "en": "New {issuer} insurance certificate",
            "fr": "Nouvelle attestation d'assurance {issuer}",
        },
        "certificate_detail": {
            "en": "The last one ended on {expiry:date}. Download the new one from your insurer's "
            "website: landlords and schools ask for it.",
            "fr": "La dernière a pris fin le {expiry:date}. Téléchargez la nouvelle sur le site "
            "de votre assureur : propriétaires et écoles la demandent.",
        },
        "certificate_letter": {
            "en": "Ask {issuer} for my insurance certificate for the current year",
            "fr": "Demander à {issuer} mon attestation d'assurance pour l'année en cours",
        },
        "identity_title": {
            "en": "Add an identity document",
            "fr": "Ajoutez une pièce d'identité",
        },
        "identity_detail": {
            "en": "Almost every application asks for it. A photo of both sides is enough.",
            "fr": "Presque tous les dossiers la demandent. Une photo recto verso suffit.",
        },
        "rib_title": {"en": "Add your bank details (RIB)", "fr": "Ajoutez votre RIB"},
        "rib_detail": {
            "en": "Asked for by employers, the CAF and landlords. Download it from your online "
            "banking.",
            "fr": "Demandé par l'employeur, la CAF et les propriétaires. Téléchargeable dans "
            "votre espace bancaire.",
        },
    },
)

MONTH_NAMES: dict[i18n.Language, list[str]] = {
    "en": [
        "January", "February", "March", "April", "May", "June", "July", "August",
        "September", "October", "November", "December",
    ],
    "fr": [
        "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre",
    ],
}  # fmt: skip
# A recurring bill is late after 1.5 of its usual interval.
LATE_FACTOR = 1.5
LATE_CADENCES = {"monthly", "bimonthly", "quarterly", "half_yearly"}
# Last month's payslip is expected from this day of the month (most are out by then).
PAYSLIP_OUT_DAY = 5
# (month, day) from which each yearly notice is online: impots.gouv.fr publishes the income tax
# notice from late July, the property tax notice from late August.
TAX_NOTICE_OUT = (8, 1)
PROPERTY_TAX_OUT = (9, 1)
# Before this many documents, the library is too young to say what is missing.
ESSENTIALS_AFTER = 5
PAYSLIP_LOOKBACK = 12  # months


class MissingDoc(BaseModel):
    key: str
    title: str
    detail: str
    area: Area | None = None
    expected: date | None = None
    # Documents of the same series, to show what is expected.
    document_ids: list[int] = []
    # What a request letter should ask for, when a letter is the way to get it.
    letter: str | None = None
    # The online account to download it from, when Binder knows it.
    portal: Portal | None = None


def month_name(d: date) -> str:
    return f"{MONTH_NAMES[i18n.current_language()][d.month - 1]} {d.year}"


def _late_bills(session: Session, today: date) -> list[MissingDoc]:
    found = []
    for sub in subscriptions.detect(session):
        if sub.cadence not in LATE_CADENCES or not sub.interval_days or not sub.history:
            continue
        last = sub.history[-1]
        expected = last.date + timedelta(days=sub.interval_days)
        if today <= last.date + timedelta(days=round(sub.interval_days * LATE_FACTOR)):
            continue
        latest = session.get(Document, last.document_id)
        found.append(
            MissingDoc(
                key=f"late:{sub.key}:{expected.isoformat()[:7]}",
                title=T("late_title", label=sub.label, month=month_name(expected)),
                detail=T("late_detail", expected=expected),
                area=areas.BY_CATEGORY.get(sub.category),
                expected=expected,
                document_ids=[p.document_id for p in sub.history[-2:]],
                portal=portals.find(session, latest.issuer, latest.doc_type) if latest else None,
            )
        )
    return found


def _months(first: date, last: date) -> list[date]:
    out, current = [], date(first.year, first.month, 1)
    while current <= last:
        out.append(current)
        current = date(current.year + current.month // 12, current.month % 12 + 1, 1)
    return out


def _month_before(d: date) -> date:
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


def _payslip_gaps(session: Session, docs: list[Document], today: date) -> list[MissingDoc]:
    slips = [d for d in docs if d.doc_type == DocType.PAYSLIP]
    if len(slips) < 2:
        return []
    found = []
    by_person: dict[str, list[Document]] = {}
    for d in slips:
        by_person.setdefault((d.person or "").lower(), []).append(d)
    since = date(today.year - 1, today.month, 1)
    for group in by_person.values():
        have = {(document_date(d).year, document_date(d).month) for d in group}
        first = max(min(document_date(d) for d in group), since)
        latest = max(group, key=document_date)
        last = date(document_date(latest).year, document_date(latest).month, 1)
        # Last month's payslip once it is out, only right after the previous one: a job that
        # ended leaves no endless card behind.
        just_out = _month_before(today)
        out = today.day >= PAYSLIP_OUT_DAY and last == _month_before(just_out)
        portal = portals.find(session, latest.issuer)
        for month in _months(first, just_out if out else last):
            if (month.year, month.month) in have:
                continue
            new = out and month == just_out
            found.append(
                MissingDoc(
                    key=f"payslip:{group[0].person or ''}:{month.isoformat()[:7]}",
                    title=T(
                        "payslip_out_title" if new else "payslip_title", month=month_name(month)
                    ),
                    detail=T("payslip_out_detail" if new else "payslip_detail"),
                    area="work",
                    expected=month,
                    document_ids=[d.id for d in group[-2:] if d.id is not None],
                    # Just out: it is downloaded, not asked for.
                    letter=None if new else T("payslip_letter", month=month_name(month)),
                    portal=portal,
                )
            )
    return found


def _concerned(session: Session, docs: list[Document], doc_type: str, today: date) -> bool:
    """This year's notice concerns the user, though last year's is not in Binder."""
    if doc_type == DocType.TAX_NOTICE:
        # Income last year (a first job): declared in the spring, the notice follows.
        earned = (DocType.PAYSLIP, DocType.PENSION_STATEMENT)
        return any(d.doc_type in earned and document_date(d).year == today.year - 1 for d in docs)
    return profile.load(session).housing == "owner"


def _yearly(session: Session, docs: list[Document], today: date) -> list[MissingDoc]:
    found = []
    checks = (
        (DocType.TAX_NOTICE, TAX_NOTICE_OUT, "tax", "money"),
        (DocType.PROPERTY_TAX, PROPERTY_TAX_OUT, "property", "housing"),
    )
    for doc_type, (month, day), key, area in checks:
        out = date(today.year, month, day)
        years = {document_date(d).year for d in docs if d.doc_type == doc_type}
        if today < out or today.year in years:
            continue
        if today.year - 1 in years or _concerned(session, docs, doc_type, today):
            found.append(
                MissingDoc(
                    key=f"{key}:{today.year}",
                    title=T(f"{key}_title", year=today.year),
                    detail=T(f"{key}_detail"),
                    area=area,
                    expected=out,
                    portal=portals.public("impots"),
                )
            )
    return found


def _certificates(session: Session, docs: list[Document], today: date) -> list[MissingDoc]:
    found = []
    for d in docs:
        if (
            d.doc_type != DocType.INSURANCE_CERTIFICATE
            or d.superseded_by is not None
            or d.expiry_date is None
            or d.expiry_date >= today
            or d.id is None
        ):
            continue
        issuer = d.issuer or d.title
        found.append(
            MissingDoc(
                key=f"certificate:{d.id}",
                title=T("certificate_title", issuer=issuer),
                detail=T("certificate_detail", expiry=d.expiry_date),
                area=d.area if d.area in areas.AREAS else "money",
                expected=d.expiry_date,
                document_ids=[d.id],
                letter=T("certificate_letter", issuer=issuer),
                portal=portals.find(session, d.issuer),
            )
        )
    return found


def _essentials(docs: list[Document]) -> list[MissingDoc]:
    if len(docs) < ESSENTIALS_AFTER:
        return []
    types = {d.doc_type for d in docs}
    found = []
    if not types & {DocType.IDENTITY_CARD, DocType.PASSPORT, DocType.RESIDENCE_PERMIT}:
        found.append(
            MissingDoc(
                key="essential:identity",
                title=T("identity_title"),
                detail=T("identity_detail"),
                area="identity",
            )
        )
    if DocType.BANK_DETAILS not in types:
        found.append(
            MissingDoc(
                key="essential:rib", title=T("rib_title"), detail=T("rib_detail"), area="money"
            )
        )
    return found


def detect(session: Session, today: date | None = None) -> list[MissingDoc]:
    today = today or date.today()
    docs = list(
        session.exec(
            select(Document)
            .options(*WITHOUT_TEXT)
            .where(in_use(), col(Document.duplicate_of).is_(None))
        )
    )
    return (
        _late_bills(session, today)
        + _payslip_gaps(session, docs, today)
        + _yearly(session, docs, today)
        + _certificates(session, docs, today)
        + _essentials(docs)
    )
