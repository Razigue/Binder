"""Document packs (rental, mortgage, CAF): expected pieces, pieces found, missing pieces.

For each piece, the most recent documents in force are used (not in the trash, not
superseded, not duplicates). A piece that is too old or expired is flagged as to be renewed
rather than counted.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT
from binder.models import Category, DocType, Document

T = i18n.catalog(
    "folders",
    {
        # Packs.
        "rental_title": {"en": "Rental application", "fr": "Dossier de location"},
        "rental_description": {
            "en": "Documents a landlord may ask for (French decree no. 2015-1437).",
            "fr": "Pièces qu'un propriétaire peut demander (décret n° 2015-1437).",
        },
        "mortgage_title": {"en": "Mortgage application", "fr": "Demande de prêt immobilier"},
        "mortgage_description": {
            "en": "Documents banks usually ask for.",
            "fr": "Pièces habituellement demandées par les banques.",
        },
        "caf_title": {"en": "CAF housing benefit", "fr": "Aide au logement (CAF)"},
        "caf_description": {
            "en": "Documents to attach to a housing benefit claim with the CAF.",
            "fr": "Pièces à joindre à une demande d'aide au logement.",
        },
        # Pieces: label and hint.
        "identity_label": {
            "en": "Valid identity document",
            "fr": "Pièce d'identité en cours de validité",
        },
        "identity_hint": {
            "en": "Identity card, passport or residence permit.",
            "fr": "Carte d'identité, passeport ou titre de séjour.",
        },
        "tax_notice_label": {"en": "Latest tax notice", "fr": "Dernier avis d'imposition"},
        "tax_notice_hint": {
            "en": "Downloadable from your impots.gouv.fr account.",
            "fr": "Téléchargeable dans votre espace impots.gouv.fr.",
        },
        "tax_notice_optional_hint": {
            "en": "Sometimes requested to check your income.",
            "fr": "Parfois demandé pour vérifier vos ressources.",
        },
        "income_label": {"en": "Last 3 payslips", "fr": "3 derniers bulletins de paie"},
        "income_hint": {
            "en": "Ask your employer for them or download them from your HR document portal.",
            "fr": "Demandez-les à votre employeur ou téléchargez-les sur votre coffre-fort RH.",
        },
        "work_contract_label": {"en": "Employment contract", "fr": "Contrat de travail"},
        "work_contract_hint": {
            "en": "Or an employer's certificate less than 3 months old.",
            "fr": "Ou une attestation d'employeur de moins de 3 mois.",
        },
        "rent_receipts_label": {
            "en": "Last 3 rent receipts",
            "fr": "3 dernières quittances de loyer",
        },
        "rent_receipts_hint": {
            "en": "Ask your current landlord for them.",
            "fr": "Demandez-les à votre propriétaire actuel.",
        },
        "proof_of_address_label": {
            "en": "Proof of address less than 3 months old",
            "fr": "Justificatif de domicile de moins de 3 mois",
        },
        "proof_of_address_hint": {
            "en": "Recent energy or internet bill, or rent receipt.",
            "fr": "Facture d'énergie, d'internet ou quittance de loyer récente.",
        },
        "tax_notices_label": {"en": "Last 2 tax notices", "fr": "2 derniers avis d'imposition"},
        "tax_notices_hint": {
            "en": "Downloadable from your impots.gouv.fr account.",
            "fr": "Téléchargeables dans votre espace impots.gouv.fr.",
        },
        "bank_statements_label": {
            "en": "Last 3 bank statements",
            "fr": "3 derniers relevés de compte",
        },
        "bank_statements_hint": {
            "en": "Downloadable from your online banking.",
            "fr": "Téléchargeables dans votre espace bancaire.",
        },
        "bank_details_label": {
            "en": "Bank account details (RIB)",
            "fr": "Relevé d'identité bancaire (RIB)",
        },
        "bank_details_hint": {
            "en": "Downloadable from your online banking.",
            "fr": "Téléchargeable dans votre espace bancaire.",
        },
        "housing_label": {
            "en": "Lease or recent rent receipt",
            "fr": "Bail ou quittance de loyer récente",
        },
        "housing_hint": {
            "en": "The signed lease, or a rent receipt less than 3 months old.",
            "fr": "Le bail signé, ou une quittance de moins de 3 mois.",
        },
        # Status notes.
        "partial": {"en": "{found} of {needed}", "fr": "{found} sur {needed}"},
        "expired": {
            "en": "“{title}” expired on {expiry:date}",
            "fr": "« {title} » a expiré le {expiry:date}",
        },
        "too_old": {
            "en": "The most recent one is dated {issued:date}: too old",
            "fr": "Le plus récent date du {issued:date} : trop ancien",
        },
        # Export (ZIP archive and activity log).
        "readme_name": {"en": "README.txt", "fr": "A_LIRE.txt"},
        "readme_missing": {"en": "Documents to add:", "fr": "Pièces à ajouter :"},
        "readme_complete": {"en": "Folder complete.", "fr": "Dossier complet."},
        "readme_optional": {"en": " [optional]", "fr": " [facultatif]"},
        "exported": {
            "en": "{title} exported ({ready}/{total} documents)",
            "fr": "{title} exporté ({ready}/{total} pièces)",
        },
    },
)

IDENTITY_TYPES = {DocType.IDENTITY_CARD, DocType.PASSPORT, DocType.RESIDENCE_PERMIT}
PROOF_OF_ADDRESS = {DocType.INVOICE, DocType.RENT_RECEIPT, DocType.PAYMENT_NOTICE}


@dataclass(frozen=True)
class Piece:
    key: str
    match: Callable[[Document], bool]
    count: int = 1
    # Maximum age (days) from the document's date.
    max_age: int | None = None
    optional: bool = False
    # Catalog keys of the label and hint (default: "<key>_label", "<key>_hint").
    text: str = ""
    hint_text: str = ""

    @property
    def label(self) -> str:
        return T(f"{self.text or self.key}_label")

    @property
    def hint(self) -> str:
        return T(self.hint_text or f"{self.text or self.key}_hint")


@dataclass(frozen=True)
class FolderKind:
    key: str
    pieces: list[Piece] = field(default_factory=list)

    @property
    def title(self) -> str:
        return T(f"{self.key}_title")

    @property
    def description(self) -> str:
        return T(f"{self.key}_description")


def _type_in(*types: DocType) -> Callable[[Document], bool]:
    return lambda d: d.doc_type in types


IDENTITY = Piece("identity", lambda d: d.doc_type in IDENTITY_TYPES)
TAX_NOTICE = Piece("tax_notice", _type_in(DocType.TAX_NOTICE), max_age=550)
PAYSLIPS = Piece("income", _type_in(DocType.PAYSLIP), count=3, max_age=100)
WORK_CONTRACT = Piece("work_contract", _type_in(DocType.EMPLOYMENT_CONTRACT))

KINDS: dict[str, FolderKind] = {
    k.key: k
    for k in [
        FolderKind(
            "rental",
            [
                IDENTITY,
                Piece("rent_receipts", _type_in(DocType.RENT_RECEIPT), count=3, max_age=120),
                WORK_CONTRACT,
                PAYSLIPS,
                TAX_NOTICE,
            ],
        ),
        FolderKind(
            "mortgage",
            [
                IDENTITY,
                Piece(
                    "proof_of_address",
                    lambda d: (
                        d.doc_type in PROOF_OF_ADDRESS
                        and d.category in {Category.ENERGY, Category.TELECOM, Category.HOUSING}
                    ),
                    max_age=92,
                ),
                PAYSLIPS,
                Piece("tax_notices", _type_in(DocType.TAX_NOTICE), count=2, max_age=915),
                Piece("bank_statements", _type_in(DocType.BANK_STATEMENT), count=3, max_age=100),
                WORK_CONTRACT,
            ],
        ),
        FolderKind(
            "caf",
            [
                IDENTITY,
                Piece("bank_details", _type_in(DocType.BANK_DETAILS)),
                Piece("housing", _type_in(DocType.LEASE, DocType.RENT_RECEIPT)),
                Piece(
                    "tax_notice",
                    _type_in(DocType.TAX_NOTICE),
                    max_age=550,
                    optional=True,
                    hint_text="tax_notice_optional_hint",
                ),
            ],
        ),
    ]
}


class PieceStatus(BaseModel):
    key: str
    label: str
    # "ok", "partial" (not enough documents), "outdated" (too old or expired), "missing".
    status: str
    found: int
    needed: int
    optional: bool
    hint: str
    document_ids: list[int]
    note: str = ""


class FolderStatus(BaseModel):
    key: str
    title: str
    description: str
    complete: bool
    ready: int
    total: int
    pieces: list[PieceStatus]


def _date_of(doc: Document) -> date:
    return doc.issue_date or doc.due_date or doc.created_at.date()


def _is_fresh(doc: Document, piece: Piece, today: date) -> bool:
    if doc.expiry_date is not None and doc.expiry_date < today:
        return False
    return piece.max_age is None or _date_of(doc) >= today - timedelta(days=piece.max_age)


def current_documents(session: Session) -> list[Document]:
    """Documents in force: neither trashed, nor replaced, nor duplicates."""
    return list(
        session.exec(
            select(Document)
            .options(*WITHOUT_TEXT)
            .where(
                col(Document.deleted_at).is_(None),
                col(Document.superseded_by).is_(None),
                col(Document.duplicate_of).is_(None),
            )
        )
    )


def evaluate(
    session: Session,
    kind: FolderKind,
    today: date | None = None,
    docs: list[Document] | None = None,
) -> FolderStatus:
    """`docs`: documents from current_documents(), to share one query between folders."""
    today = today or date.today()
    if docs is None:
        docs = current_documents(session)
    pieces = []
    for piece in kind.pieces:
        matching = sorted((d for d in docs if piece.match(d)), key=_date_of, reverse=True)
        fresh = [d for d in matching if _is_fresh(d, piece, today)][: piece.count]
        note = ""
        if len(fresh) >= piece.count:
            status = "ok"
        elif fresh:
            status = "partial"
            note = T("partial", found=len(fresh), needed=piece.count)
        elif matching:
            status = "outdated"
            latest = matching[0]
            expired = latest.expiry_date is not None and latest.expiry_date < today
            note = (
                T("expired", title=latest.title, expiry=latest.expiry_date)
                if expired
                else T("too_old", issued=_date_of(latest))
            )
        else:
            status = "missing"
        chosen = matching[:1] if status == "outdated" else fresh
        pieces.append(
            PieceStatus(
                key=piece.key,
                label=piece.label,
                status=status,
                found=len(fresh),
                needed=piece.count,
                optional=piece.optional,
                hint=piece.hint,
                document_ids=[d.id for d in chosen if d.id is not None],
                note=note,
            )
        )
    required = [p for p in pieces if not p.optional]
    ready = sum(p.status == "ok" for p in required)
    return FolderStatus(
        key=kind.key,
        title=kind.title,
        description=kind.description,
        complete=ready == len(required),
        ready=ready,
        total=len(required),
        pieces=pieces,
    )


def readme(status: FolderStatus) -> str:
    """Text file of an exported folder: what it is for and which pieces are still missing."""
    missing = []
    for piece in status.pieces:
        if piece.status != "ok":
            extra = f" ({piece.note})" if piece.note else ""
            optional = T("readme_optional") if piece.optional else ""
            missing.append(f"- {piece.label}{optional}{extra}. {piece.hint}")
    lines = [status.title, "", status.description, ""]
    lines += [T("readme_missing"), *missing] if missing else [T("readme_complete")]
    return "\n".join(lines) + "\n"


def exported_msg(status: FolderStatus) -> i18n.Msg:
    """Activity log entry for an export (the pack title follows the display language)."""
    return T.msg(
        "exported",
        title=T.msg(f"{status.key}_title"),
        ready=status.ready,
        total=status.total,
    )
