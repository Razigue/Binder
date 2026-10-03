"""The papers you should have: a static list by profile, with why and how long to keep each.

Built from the three answers of the first launch (situation, housing, vehicle: see
profile.CHOICES) and checked against the library: each paper is marked present or missing.
Static on purpose: it is general knowledge about French paperwork, the same for everyone in the
same situation, and it works without the local model.
"""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT, in_use
from binder.models import Category, DocType, Document
from binder.services import areas, portals
from binder.services.portals import Portal
from binder.services.profile import Profile

T = i18n.catalog(
    "essentials",
    {
        "identity": {"en": "ID card or passport", "fr": "Carte d'identité ou passeport"},
        "identity_why": {
            "en": "Asked for almost every procedure, and needed to renew it in time.",
            "fr": "Demandée pour presque toutes les démarches, et à renouveler à temps.",
        },
        "rib": {"en": "Bank details (RIB)", "fr": "RIB"},
        "rib_why": {
            "en": "Asked for by employers, the CAF, landlords and every direct debit.",
            "fr": "Demandé par l'employeur, la CAF, le propriétaire et chaque prélèvement.",
        },
        "tax_notice": {"en": "Last income tax notice", "fr": "Dernier avis d'impôt"},
        "tax_notice_why": {
            "en": "Proof of income for a rental, a loan, the CAF or a reduced rate.",
            "fr": "Justificatif de revenus pour une location, un prêt, la CAF ou un tarif réduit.",
        },
        "health": {"en": "Health insurance papers", "fr": "Papiers d'Assurance Maladie"},
        "health_why": {
            "en": "Your rights and reimbursements: useful for a supplementary insurance or a "
            "dispute.",
            "fr": "Vos droits et remboursements : utiles pour une mutuelle ou une contestation.",
        },
        "contract": {"en": "Employment contract", "fr": "Contrat de travail"},
        "contract_why": {
            "en": "Proves your job and its conditions; counts for your pension.",
            "fr": "Prouve votre emploi et ses conditions ; compte pour votre retraite.",
        },
        "payslips": {"en": "Payslips", "fr": "Bulletins de paie"},
        "payslips_why": {
            "en": "Proof of income, and of your career when you claim your pension.",
            "fr": "Justificatifs de revenus, et de carrière au moment de la retraite.",
        },
        "pension": {"en": "Pension statements", "fr": "Relevés de pension"},
        "pension_why": {
            "en": "What you receive and from whom: asked for the tax return and by the CAF.",
            "fr": "Ce que vous touchez et de qui : demandés pour la déclaration et par la CAF.",
        },
        "school": {"en": "School or university certificate", "fr": "Certificat de scolarité"},
        "school_why": {
            "en": "Asked for grants, housing benefit, transport and student rates.",
            "fr": "Demandé pour les bourses, l'aide au logement, les transports et les tarifs "
            "étudiants.",
        },
        "benefits": {"en": "Benefits decisions", "fr": "Décisions d'allocations"},
        "benefits_why": {
            "en": "What France Travail or the CAF decided: keep them in case of an overpayment "
            "claim.",
            "fr": "Ce que France Travail ou la CAF ont décidé : à garder en cas de trop-perçu.",
        },
        "lease": {"en": "Lease", "fr": "Bail"},
        "lease_why": {
            "en": "Your rights as a tenant, the notice period and the deposit to get back.",
            "fr": "Vos droits de locataire, le préavis et le dépôt de garantie à récupérer.",
        },
        "rent_receipts": {"en": "Rent receipts", "fr": "Quittances de loyer"},
        "rent_receipts_why": {
            "en": "Proof of address and of payment, asked for a new rental.",
            "fr": "Justificatif de domicile et de paiement, demandé pour une nouvelle location.",
        },
        "home_insurance": {
            "en": "Home insurance certificate",
            "fr": "Attestation d'assurance habitation",
        },
        "home_insurance_why": {
            "en": "Compulsory for tenants; asked for by the landlord every year.",
            "fr": "Obligatoire pour un locataire ; demandée chaque année par le propriétaire.",
        },
        "property_tax": {"en": "Property tax notice", "fr": "Avis de taxe foncière"},
        "property_tax_why": {
            "en": "What you pay each autumn, and proof that you own the home.",
            "fr": "Ce que vous payez chaque automne, et preuve que vous êtes propriétaire.",
        },
        "registration": {"en": "Vehicle registration", "fr": "Carte grise"},
        "registration_why": {
            "en": "Compulsory in the car; needed to sell it or to change your address.",
            "fr": "Obligatoire dans la voiture ; nécessaire pour la vendre ou changer d'adresse.",
        },
        "car_insurance": {"en": "Car insurance certificate", "fr": "Attestation d'assurance auto"},
        "car_insurance_why": {
            "en": "Compulsory: to show after an accident or a road check.",
            "fr": "Obligatoire : à présenter après un accident ou lors d'un contrôle.",
        },
        "inspection": {"en": "Roadworthiness test", "fr": "Contrôle technique"},
        "inspection_why": {
            "en": "Every two years after the car's fourth year; asked for to sell it.",
            "fr": "Tous les deux ans après les quatre ans de la voiture ; demandé pour la vendre.",
        },
        "licence": {"en": "Driving licence", "fr": "Permis de conduire"},
        "licence_why": {
            "en": "To carry when driving; the new card format expires after 15 years.",
            "fr": "À avoir sur soi en conduisant ; le format carte expire au bout de 15 ans.",
        },
        "keep_valid": {"en": "As long as it is valid", "fr": "Tant qu'il est valable"},
        "keep_years_one": {"en": "{n} year", "fr": "{n} an"},
        "keep_years_other": {"en": "{n} years", "fr": "{n} ans"},
        "keep_tax": {
            "en": "3 years after the tax year",
            "fr": "3 ans après l'année d'imposition",
        },
        "keep_retirement": {
            "en": "Until you claim your pension",
            "fr": "Jusqu'à la liquidation de la retraite",
        },
        "keep_forever": {"en": "For good", "fr": "Sans limite"},
        "keep_lease": {
            "en": "The whole tenancy, then 3 years",
            "fr": "Toute la location, puis 3 ans",
        },
        "keep_account": {
            "en": "As long as the account is open",
            "fr": "Tant que le compte est ouvert",
        },
        "keep_vehicle": {
            "en": "As long as you own the vehicle",
            "fr": "Tant que vous avez le véhicule",
        },
        "keep_next": {"en": "Until the next one", "fr": "Jusqu'au suivant"},
    },
)

Match = Callable[[Document], bool]


def _types(*types: str) -> Match:
    return lambda d: d.doc_type in types


def _insurance(area: str) -> Match:
    return lambda d: d.doc_type == DocType.INSURANCE_CERTIFICATE and d.area == area


@dataclass(frozen=True)
class Paper:
    key: str
    area: areas.Area
    match: Match
    # Message key of how long to keep it, with its parameters.
    keep: str
    keep_years: int | None = None
    # Who needs it: (profile field, values); None: everyone.
    for_: tuple[str, tuple[str, ...]] | None = None


PAPERS: list[Paper] = [
    Paper("identity", "identity", _types(DocType.IDENTITY_CARD, DocType.PASSPORT,
          DocType.RESIDENCE_PERMIT), "keep_valid"),
    Paper("rib", "money", _types(DocType.BANK_DETAILS), "keep_account"),
    Paper("tax_notice", "money", _types(DocType.TAX_NOTICE), "keep_tax"),
    Paper("health", "health", lambda d: d.category == Category.HEALTH, "keep_years", 2),
    Paper("contract", "work", _types(DocType.EMPLOYMENT_CONTRACT), "keep_retirement",
          for_=("situation", ("employee",))),
    Paper("payslips", "work", _types(DocType.PAYSLIP), "keep_retirement",
          for_=("situation", ("employee",))),
    Paper("pension", "work", _types(DocType.PENSION_STATEMENT), "keep_forever",
          for_=("situation", ("retired",))),
    Paper("school", "family", _types(DocType.SCHOOL_CERTIFICATE), "keep_years", 1,
          for_=("situation", ("student",))),
    Paper("benefits", "work", _types(DocType.BENEFIT_DECISION), "keep_years", 2,
          for_=("situation", ("job_seeker",))),
    Paper("lease", "housing", _types(DocType.LEASE), "keep_lease",
          for_=("housing", ("tenant",))),
    Paper("rent_receipts", "housing", _types(DocType.RENT_RECEIPT), "keep_years", 3,
          for_=("housing", ("tenant",))),
    Paper("home_insurance", "housing", _insurance("housing"), "keep_years", 2,
          for_=("housing", ("tenant", "owner"))),
    Paper("property_tax", "housing", _types(DocType.PROPERTY_TAX), "keep_tax",
          for_=("housing", ("owner",))),
    Paper("registration", "vehicle", _types(DocType.VEHICLE_REGISTRATION), "keep_vehicle",
          for_=("vehicle", ("yes",))),
    Paper("car_insurance", "vehicle", _insurance("vehicle"), "keep_years", 2,
          for_=("vehicle", ("yes",))),
    Paper("inspection", "vehicle", _types(DocType.ROADWORTHINESS_TEST), "keep_next",
          for_=("vehicle", ("yes",))),
    Paper("licence", "vehicle", _types(DocType.DRIVING_LICENCE), "keep_valid",
          for_=("vehicle", ("yes",))),
]  # fmt: skip


# Papers downloadable from a public online account (services/portals.py), to fetch a missing one.
WHERE: dict[str, str] = {
    "tax_notice": "impots",
    "property_tax": "impots",
    "health": "ameli",
    "benefits": "france_travail",
    "pension": "retraite",
}


class PaperOut(BaseModel):
    key: str
    area: str
    title: str
    why: str
    keep: str
    present: bool
    # The most recent matching document, to open it.
    document_id: int | None = None
    # Where to download it when it is missing.
    portal: Portal | None = None


def _applies(paper: Paper, me: Profile) -> bool:
    if paper.for_ is None:
        return True
    field, values = paper.for_
    return getattr(me, field) in values


def _keep(paper: Paper) -> str:
    if paper.keep == "keep_years" and paper.keep_years is not None:
        return T.plural("keep_years", paper.keep_years)
    return T(paper.keep)


def papers(session: Session, me: Profile) -> list[PaperOut]:
    """The papers to have for this profile, present ones last."""
    docs = list(
        session.exec(
            select(Document)
            .options(*WITHOUT_TEXT)
            .where(in_use(), col(Document.duplicate_of).is_(None))
            .order_by(col(Document.issue_date).desc(), col(Document.id).desc())
        )
    )
    out = []
    for paper in PAPERS:
        if not _applies(paper, me):
            continue
        found = next((d for d in docs if paper.match(d)), None)
        out.append(
            PaperOut(
                key=paper.key,
                area=paper.area,
                title=T(paper.key),
                why=T(f"{paper.key}_why"),
                keep=_keep(paper),
                present=found is not None,
                document_id=found.id if found else None,
                portal=portals.public(WHERE[paper.key])
                if not found and paper.key in WHERE
                else None,
            )
        )
    return sorted(out, key=lambda p: p.present)
