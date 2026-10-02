"""Documents that should be there and are not.

- A recurring bill that has not arrived when the next one was expected.
- A gap in the payslips.
- A yearly document that comes every year (tax notice, property tax) missing this year.
- An insurance certificate past its end date, with no newer one.
- The essentials every application asks for (identity document, bank details).
"""

from datetime import date, timedelta

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT, in_use
from binder.models import DocType, Document
from binder.services import areas, subscriptions
from binder.services.areas import Area

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
        "tax_title": {
            "en": "Tax notice {year} not filed yet",
            "fr": "Avis d'impôt {year} pas encore rangé",
        },
        "tax_detail": {
            "en": "It is available in your impots.gouv.fr account since the summer.",
            "fr": "Il est disponible dans votre espace impots.gouv.fr depuis l'été.",
        },
        "property_title": {
            "en": "Property tax {year} not filed yet",
            "fr": "Taxe foncière {year} pas encore rangée",
        },
        "property_detail": {
            "en": "It is sent at the end of summer and available in your impots.gouv.fr account.",
            "fr": "Elle est envoyée fin août et disponible dans votre espace impots.gouv.fr.",
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


def month_name(d: date) -> str:
    return f"{MONTH_NAMES[i18n.current_language()][d.month - 1]} {d.year}"


def _when(doc: Document) -> date:
    return doc.issue_date or doc.due_date or doc.created_at.date()


def _late_bills(session: Session, today: date) -> list[MissingDoc]:
    found = []
    for sub in subscriptions.detect(session):
        if sub.cadence not in LATE_CADENCES or not sub.interval_days or not sub.history:
            continue
        last = sub.history[-1]
        expected = last.date + timedelta(days=sub.interval_days)
        if today <= last.date + timedelta(days=round(sub.interval_days * LATE_FACTOR)):
            continue
        found.append(
            MissingDoc(
                key=f"late:{sub.key}:{expected.isoformat()[:7]}",
                title=T("late_title", label=sub.label, month=month_name(expected)),
                detail=T("late_detail", expected=expected),
                area=areas.BY_CATEGORY.get(sub.category),
                expected=expected,
                document_ids=[p.document_id for p in sub.history[-2:]],
            )
        )
    return found


def _months(first: date, last: date) -> list[date]:
    out, current = [], date(first.year, first.month, 1)
    while current <= last:
        out.append(current)
        current = date(current.year + current.month // 12, current.month % 12 + 1, 1)
    return out


def _payslip_gaps(docs: list[Document], today: date) -> list[MissingDoc]:
    slips = [d for d in docs if d.doc_type == DocType.PAYSLIP]
    if len(slips) < 2:
        return []
    found = []
    by_person: dict[str, list[Document]] = {}
    for d in slips:
        by_person.setdefault((d.person or "").lower(), []).append(d)
    since = date(today.year - 1, today.month, 1)
    for group in by_person.values():
        have = {(_when(d).year, _when(d).month) for d in group}
        first = max(min(_when(d) for d in group), since)
        last = max(_when(d) for d in group)
        for month in _months(first, last):
            if (month.year, month.month) in have:
                continue
            found.append(
                MissingDoc(
                    key=f"payslip:{group[0].person or ''}:{month.isoformat()[:7]}",
                    title=T("payslip_title", month=month_name(month)),
                    detail=T("payslip_detail"),
                    area="work",
                    expected=month,
                    document_ids=[d.id for d in group[-2:] if d.id is not None],
                    letter=T("payslip_letter", month=month_name(month)),
                )
            )
    return found


def _yearly(docs: list[Document], today: date) -> list[MissingDoc]:
    found = []
    checks = (
        (DocType.TAX_NOTICE, date(today.year, 9, 15), "tax"),
        (DocType.PROPERTY_TAX, date(today.year, 10, 1), "property"),
    )
    for doc_type, from_day, key in checks:
        if today < from_day:
            continue
        years = {_when(d).year for d in docs if d.doc_type == doc_type}
        if today.year - 1 in years and today.year not in years:
            found.append(
                MissingDoc(
                    key=f"{key}:{today.year}",
                    title=T(f"{key}_title", year=today.year),
                    detail=T(f"{key}_detail"),
                    area="money",
                )
            )
    return found


def _certificates(docs: list[Document], today: date) -> list[MissingDoc]:
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
        + _payslip_gaps(docs, today)
        + _yearly(docs, today)
        + _certificates(docs, today)
        + _essentials(docs)
    )
