"""Dossiers types (location, prêt, CAF) : pièces attendues, pièces trouvées, pièces manquantes.

Pour chaque pièce, on retient les documents en vigueur les plus récents (ni à la corbeille,
ni remplacés, ni doublons). Une pièce trop ancienne ou expirée est signalée comme à
renouveler plutôt que comptée.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder.models import Category, Document

IDENTITY_TYPES = {"Carte d'identité", "Passeport", "Titre de séjour"}
PROOF_OF_ADDRESS = {"Facture", "Quittance de loyer", "Avis d'échéance"}


@dataclass(frozen=True)
class Piece:
    key: str
    label: str
    match: Callable[[Document], bool]
    count: int = 1
    # Âge maximal (jours) à partir de la date du document.
    max_age: int | None = None
    optional: bool = False
    hint: str = ""


@dataclass(frozen=True)
class FolderKind:
    key: str
    title: str
    description: str
    pieces: list[Piece] = field(default_factory=list)


def _type_in(*types: str) -> Callable[[Document], bool]:
    return lambda d: d.doc_type in types


IDENTITY = Piece(
    "identite",
    "Pièce d'identité en cours de validité",
    lambda d: d.doc_type in IDENTITY_TYPES,
    hint="Carte d'identité, passeport ou titre de séjour.",
)
TAX_NOTICE = Piece(
    "impot",
    "Dernier avis d'imposition",
    _type_in("Avis d'imposition"),
    max_age=550,
    hint="Téléchargeable dans votre espace impots.gouv.fr.",
)
PAYSLIPS = Piece(
    "revenus",
    "3 derniers bulletins de paie",
    _type_in("Bulletin de paie"),
    count=3,
    max_age=100,
    hint="Demandez-les à votre employeur ou téléchargez-les sur votre coffre-fort RH.",
)
WORK_CONTRACT = Piece(
    "contrat",
    "Contrat de travail",
    _type_in("Contrat de travail"),
    hint="Ou une attestation d'employeur de moins de 3 mois.",
)

KINDS: dict[str, FolderKind] = {
    k.key: k
    for k in [
        FolderKind(
            "location",
            "Dossier de location",
            "Pièces qu'un propriétaire peut demander (décret n° 2015-1437).",
            [
                IDENTITY,
                Piece(
                    "domicile",
                    "3 dernières quittances de loyer",
                    _type_in("Quittance de loyer"),
                    count=3,
                    max_age=120,
                    hint="Demandez-les à votre propriétaire actuel.",
                ),
                WORK_CONTRACT,
                PAYSLIPS,
                TAX_NOTICE,
            ],
        ),
        FolderKind(
            "pret",
            "Demande de prêt immobilier",
            "Pièces habituellement demandées par les banques.",
            [
                IDENTITY,
                Piece(
                    "domicile",
                    "Justificatif de domicile de moins de 3 mois",
                    lambda d: (
                        d.doc_type in PROOF_OF_ADDRESS
                        and d.category in {Category.ENERGIE, Category.TELECOM, Category.LOGEMENT}
                    ),
                    max_age=92,
                    hint="Facture d'énergie, d'internet ou quittance de loyer récente.",
                ),
                PAYSLIPS,
                Piece(
                    "impots",
                    "2 derniers avis d'imposition",
                    _type_in("Avis d'imposition"),
                    count=2,
                    max_age=915,
                    hint="Téléchargeables dans votre espace impots.gouv.fr.",
                ),
                Piece(
                    "comptes",
                    "3 derniers relevés de compte",
                    _type_in("Relevé bancaire"),
                    count=3,
                    max_age=100,
                    hint="Téléchargeables dans votre espace bancaire.",
                ),
                WORK_CONTRACT,
            ],
        ),
        FolderKind(
            "caf",
            "Aide au logement (CAF)",
            "Pièces à joindre à une demande d'aide au logement.",
            [
                IDENTITY,
                Piece(
                    "rib",
                    "Relevé d'identité bancaire (RIB)",
                    _type_in("RIB"),
                    hint="Téléchargeable dans votre espace bancaire.",
                ),
                Piece(
                    "logement",
                    "Bail ou quittance de loyer récente",
                    _type_in("Bail", "Quittance de loyer"),
                    hint="Le bail signé, ou une quittance de moins de 3 mois.",
                ),
                Piece(
                    "impot",
                    "Dernier avis d'imposition",
                    _type_in("Avis d'imposition"),
                    max_age=550,
                    optional=True,
                    hint="Parfois demandé pour vérifier vos ressources.",
                ),
            ],
        ),
    ]
}


class PieceStatus(BaseModel):
    key: str
    label: str
    # « ok », « partial » (pas assez de documents), « outdated » (trop ancien ou expiré),
    # « missing ».
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


def evaluate(session: Session, kind: FolderKind, today: date | None = None) -> FolderStatus:
    today = today or date.today()
    docs = list(
        session.exec(
            select(Document).where(
                col(Document.deleted_at).is_(None),
                col(Document.superseded_by).is_(None),
                col(Document.duplicate_of).is_(None),
            )
        )
    )
    pieces = []
    for piece in kind.pieces:
        matching = sorted((d for d in docs if piece.match(d)), key=_date_of, reverse=True)
        fresh = [d for d in matching if _is_fresh(d, piece, today)][: piece.count]
        note = ""
        if len(fresh) >= piece.count:
            status = "ok"
        elif fresh:
            status = "partial"
            note = f"{len(fresh)} sur {piece.count}"
        elif matching:
            status = "outdated"
            latest = matching[0]
            expired = latest.expiry_date is not None and latest.expiry_date < today
            note = (
                f"« {latest.title} » a expiré le {latest.expiry_date:%d/%m/%Y}"
                if expired and latest.expiry_date
                else f"Le plus récent date du {_date_of(latest):%d/%m/%Y} : trop ancien"
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
