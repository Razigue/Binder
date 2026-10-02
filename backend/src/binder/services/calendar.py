"""The administrative year: what usually comes back each month (France).

Static on purpose: these dates are the same every year, give or take a few days, and they help
the user see what is coming before any letter arrives. An entry is marked as concerning the user
when their papers show it does (a property tax notice, a donation receipt…). Other countries get
no calendar: Binder does not know theirs.
"""

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import in_use
from binder.models import DocType, Document

T = i18n.catalog(
    "calendar",
    {
        "withholding": {
            "en": "Your new withholding tax rate applies: check it on your first payslip.",
            "fr": "Votre nouveau taux de prélèvement à la source s'applique : vérifiez-le sur "
            "votre première fiche de paie.",
        },
        "statements": {
            "en": "Banks and employers send the yearly statements used for the tax return.",
            "fr": "Banques et employeurs envoient les relevés annuels utiles à la déclaration "
            "de revenus.",
        },
        "return_opens": {
            "en": "The income tax return opens online, usually in mid-April.",
            "fr": "La déclaration de revenus ouvre en ligne, en général mi-avril.",
        },
        "return_due": {
            "en": "Deadlines of the online tax return, by département, from late May to early "
            "June.",
            "fr": "Dates limites de la déclaration en ligne, selon le département, de fin mai à "
            "début juin.",
        },
        "tax_notice": {
            "en": "The income tax notice arrives (late July to early September): check it, a "
            "balance is taken from September.",
            "fr": "L'avis d'impôt sur le revenu arrive (fin juillet à début septembre) : "
            "vérifiez-le, un solde est prélevé à partir de septembre.",
        },
        "property_tax_notice": {
            "en": "The property tax notice is sent, at the end of August or in September.",
            "fr": "L'avis de taxe foncière est envoyé, fin août ou en septembre.",
        },
        "property_tax_due": {
            "en": "Property tax due, around 15 October (a few days more online).",
            "fr": "Taxe foncière à payer, vers le 15 octobre (quelques jours de plus en ligne).",
        },
        "school": {
            "en": "Back to school: school certificates, insurance and the CAF back-to-school "
            "allowance.",
            "fr": "Rentrée : certificats de scolarité, assurance scolaire et allocation de "
            "rentrée de la CAF.",
        },
        "second_home": {
            "en": "Housing tax on second homes due, around 15 December.",
            "fr": "Taxe d'habitation sur les résidences secondaires à payer, vers le 15 décembre.",
        },
        "donations": {
            "en": "Donations made before 31 December count for this year's tax reduction.",
            "fr": "Les dons faits avant le 31 décembre comptent pour la réduction d'impôt de "
            "l'année.",
        },
        "insurance": {
            "en": "Many insurance contracts renew on their anniversary date: after one year, you "
            "can end them at any time.",
            "fr": "Beaucoup de contrats d'assurance se renouvellent à leur date anniversaire : "
            "après un an, vous pouvez les résilier à tout moment.",
        },
    },
)

# (month, entry, document types showing that it concerns the user).
YEAR: list[tuple[int, str, tuple[str, ...]]] = [
    (1, "withholding", (DocType.PAYSLIP,)),
    (2, "statements", (DocType.ANNUAL_TAX_STATEMENT, DocType.PAYSLIP)),
    (4, "return_opens", (DocType.TAX_NOTICE,)),
    (5, "return_due", (DocType.TAX_NOTICE,)),
    (7, "tax_notice", (DocType.TAX_NOTICE,)),
    (8, "school", (DocType.SCHOOL_CERTIFICATE, DocType.CHILDCARE_CERTIFICATE)),
    (9, "property_tax_notice", (DocType.PROPERTY_TAX,)),
    (10, "property_tax_due", (DocType.PROPERTY_TAX,)),
    (11, "insurance", (DocType.INSURANCE_CERTIFICATE, DocType.PAYMENT_NOTICE)),
    (12, "second_home", (DocType.HOUSING_TAX,)),
    (12, "donations", (DocType.DONATION_RECEIPT,)),
]
COUNTRIES = {"FR"}


class CalendarEntry(BaseModel):
    month: int
    key: str
    text: str
    # The user's papers show it concerns them.
    concerns_you: bool


def year(session: Session, country: str | None) -> list[CalendarEntry]:
    if (country or "FR").upper() not in COUNTRIES:
        return []
    held = set(
        session.exec(
            select(Document.doc_type).where(in_use(), col(Document.doc_type).is_not(None))
        ).all()
    )
    return [
        CalendarEntry(month=month, key=key, text=T(key), concerns_you=bool(held & set(types)))
        for month, key, types in YEAR
    ]
