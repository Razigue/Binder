"""Recommended retention periods (individuals, France), with sorting suggestions.

Based on the service-public.fr page « Combien de temps conserver ses papiers ? »; when in
doubt, the longest period is used. Binder never deletes anything: a document past its period
goes to the archives (services/archive.py), still readable and restorable.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from binder import i18n
from binder.models import Category, DocType, Document
from binder.services.deadlines import document_date

T = i18n.catalog(
    "retention",
    {
        "forever": {"en": "Keep indefinitely", "fr": "À conserver sans limite"},
        "until_retirement": {
            "en": "Until you claim your pension",
            "fr": "Jusqu'à la liquidation de la retraite",
        },
        "contract": {
            "en": "For the life of the contract, then 2 years",
            "fr": "Toute la durée du contrat, puis 2 ans",
        },
        "lease": {
            "en": "For the whole tenancy, then 3 years",
            "fr": "Toute la durée de la location, puis 3 ans",
        },
        "account_open": {
            "en": "As long as the account is open",
            "fr": "Tant que le compte est ouvert",
        },
        "vehicle_owned": {
            "en": "As long as you own the vehicle",
            "fr": "Tant que vous possédez le véhicule",
        },
        "next_inspection": {"en": "Until the next inspection", "fr": "Jusqu'au contrôle suivant"},
        # French agrees with the document's gender (carte: elle, passeport: il).
        "valid_f": {"en": "As long as it is valid", "fr": "Tant qu'elle est valide"},
        "valid_m": {"en": "As long as it is valid", "fr": "Tant qu'il est valide"},
        "no_obligation": {"en": "No obligation to keep", "fr": "Sans obligation de conservation"},
        "loan": {
            "en": "Until 2 years after the last repayment",
            "fr": "Jusqu'à 2 ans après la dernière échéance",
        },
        "warranty": {
            "en": "As long as the warranty runs",
            "fr": "Pendant toute la durée de la garantie",
        },
        "years_one": {"en": "{n} year", "fr": "{n} an"},
        "years_other": {"en": "{n} years", "fr": "{n} ans"},
        "tax_years": {
            "en": "{n} years after the tax year",
            "fr": "{n} ans après l'année d'imposition",
        },
        "replaced": {
            "en": "Replaced by a newer version",
            "fr": "Remplacé par une version plus récente",
        },
        "replaced_inline": {
            "en": "replaced by a newer version",
            "fr": "remplacé par une version plus récente",
        },
        "expired": {
            "en": "Retention period exceeded ({retention_rule})",
            "fr": "Durée de conservation dépassée ({retention_rule})",
        },
        "expired_inline": {
            "en": "retention period exceeded ({retention_rule})",
            "fr": "durée de conservation dépassée ({retention_rule})",
        },
    },
)


@dataclass(frozen=True)
class Rule:
    # Message key of the label (T).
    key: str
    # Period in years from the document's date. None: no fixed period.
    years: int | None = None
    # Count until 31 December (tax reassessment period).
    end_of_year: bool = False
    # Can be sorted out as soon as a newer version replaces it.
    until_replaced: bool = False

    @property
    def msg(self) -> i18n.Msg:
        if self.key == "years" and self.years is not None:
            return T.plural_msg("years", self.years)
        if self.years is not None:
            return T.msg(self.key, n=self.years)
        return T.msg(self.key)

    @property
    def label(self) -> str:
        """Label in the current language ("2 years" / "2 ans")."""
        return self.msg.render()


FOREVER = Rule("forever")

BY_TYPE: dict[str, Rule] = {
    DocType.PAYSLIP: Rule("until_retirement"),
    DocType.CONTRACT: Rule("contract"),
    DocType.EMPLOYMENT_CONTRACT: Rule("until_retirement"),
    DocType.LEASE: Rule("lease"),
    DocType.BANK_DETAILS: Rule("account_open"),
    DocType.VEHICLE_REGISTRATION: Rule("vehicle_owned"),
    DocType.ROADWORTHINESS_TEST: Rule("next_inspection", until_replaced=True),
    DocType.IDENTITY_CARD: Rule("valid_f", until_replaced=True),
    DocType.PASSPORT: Rule("valid_m", until_replaced=True),
    DocType.DRIVING_LICENCE: Rule("valid_m", until_replaced=True),
    DocType.RESIDENCE_PERMIT: Rule("valid_m", until_replaced=True),
    # Even once replaced, it can prove coverage for a past claim.
    DocType.INSURANCE_CERTIFICATE: Rule("years", years=2),
    DocType.QUOTE: Rule("no_obligation"),
    DocType.LOAN_STATEMENT: Rule("loan"),
    DocType.ANNUAL_TAX_STATEMENT: Rule("tax_years", years=3, end_of_year=True),
    DocType.DONATION_RECEIPT: Rule("tax_years", years=3, end_of_year=True),
    DocType.CHILDCARE_CERTIFICATE: Rule("tax_years", years=3, end_of_year=True),
    DocType.CIVIL_STATUS: FOREVER,
    DocType.FAMILY_RECORD_BOOK: FOREVER,
    DocType.PENSION_STATEMENT: Rule("until_retirement"),
    DocType.SCHOOL_CERTIFICATE: Rule("years", years=1),
    # Proof of payment of a fine: the time the fine itself can still be claimed.
    DocType.FINE: Rule("years", years=3),
    DocType.PURCHASE_RECEIPT: Rule("warranty"),
}

BY_CATEGORY: dict[Category, Rule] = {
    Category.TAXES: Rule("tax_years", years=3, end_of_year=True),
    Category.ENERGY: Rule("years", years=5),
    Category.TELECOM: Rule("years", years=1),
    Category.BANK: Rule("years", years=5),
    Category.HOUSING: Rule("years", years=3),
    Category.INSURANCE: Rule("years", years=2),
    Category.HEALTH: Rule("years", years=2),
    Category.SOCIAL: Rule("years", years=2),
    Category.WORK: Rule("until_retirement"),
    Category.IDENTITY: Rule("valid_f", until_replaced=True),
    Category.VEHICLE: Rule("vehicle_owned"),
    Category.FAMILY: Rule("years", years=2),
    Category.PURCHASES: Rule("warranty"),
}


def rule_for(doc: Document) -> Rule | None:
    if doc.keep_forever:
        return FOREVER
    return BY_TYPE.get(doc.doc_type or "") or BY_CATEGORY.get(doc.category)


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 February
        return d.replace(year=d.year + years, day=28)


def keep_until(doc: Document) -> date | None:
    rule = rule_for(doc)
    if rule is not None and rule.key == "warranty":
        return doc.expiry_date
    if rule is None or rule.years is None:
        return None
    base = document_date(doc)
    if rule.end_of_year:
        return date(base.year + rule.years, 12, 31)
    return _add_years(base, rule.years)


def archive_kind(doc: Document, today: date | None = None) -> str | None:
    """ "replaced" or "retention" when the document can go to the archives, else None."""
    rule = rule_for(doc)
    if rule is None or doc.keep_forever or doc.deleted_at is not None:
        return None
    if doc.archived_at is not None:
        return None
    if rule.until_replaced and doc.superseded_by is not None:
        return "replaced"
    end = keep_until(doc)
    if end is not None and end < (today or date.today()):
        return "retention"
    return None


def archivable_msg(
    doc: Document, today: date | None = None, *, inline: bool = False
) -> i18n.Msg | None:
    """Why this document can go to the archives, or None if it stays in the active views.

    `inline`: lowercase variant, to be embedded in a sentence.
    """
    kind = archive_kind(doc, today)
    suffix = "_inline" if inline else ""
    if kind == "replaced":
        return T.msg("replaced" + suffix)
    rule = rule_for(doc)
    if kind == "retention" and rule is not None:
        return T.msg("expired" + suffix, retention_rule=rule.msg)
    return None


def archivable_reason(doc: Document, today: date | None = None) -> str | None:
    """Why this document can go to the archives, in the current language (None: it stays)."""
    msg = archivable_msg(doc, today)
    return msg.render() if msg else None


def _render_rule(value: Any, language: i18n.Language) -> str:
    """Rule label inside a sentence: "(2 years)", "(jusqu'à la liquidation de la retraite)"."""
    label = i18n.render(str(value["key"]), value.get("params") or {}, language)
    return label[:1].lower() + label[1:]


i18n.register_param_renderer("retention_rule", _render_rule)
