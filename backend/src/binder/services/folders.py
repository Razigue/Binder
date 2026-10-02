"""Document packs: expected pieces, pieces found, missing pieces.

Any pack can be asked for in words ("the file for the nursery"): the three common ones (rental,
mortgage, CAF) have their official list of pieces; for anything else the local model picks the
pieces from the library, or, without a model, the documents whose type the request names.

For each piece, the most recent documents in force are used (not in the trash, not
superseded, not duplicates). A piece that is too old or expired is flagged as to be renewed
rather than counted.
"""

import json
import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT
from binder.models import Category, DocType, Document
from binder.services import llm, settings_store
from binder.services.rules import normalize

log = logging.getLogger(__name__)

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
        "identity_renewal_title": {
            "en": "Identity card or passport renewal",
            "fr": "Renouvellement de carte d'identité ou de passeport",
        },
        "identity_renewal_description": {
            "en": "Pre-application on ants.gouv.fr, then an appointment at a town hall. Also "
            "bring an identity photo less than 6 months old and, for a passport, a tax stamp "
            "bought online.",
            "fr": "Pré-demande sur ants.gouv.fr, puis rendez-vous en mairie. Prévoyez aussi une "
            "photo d'identité de moins de 6 mois et, pour un passeport, un timbre fiscal acheté "
            "en ligne.",
        },
        "school_title": {"en": "School enrolment", "fr": "Inscription scolaire"},
        "school_description": {
            "en": "Enrolment at the town hall, then admission at the school. Also bring the "
            "child's health record (compulsory vaccinations).",
            "fr": "Inscription en mairie, puis admission à l'école. Apportez aussi le carnet de "
            "santé de l'enfant (vaccinations obligatoires).",
        },
        "retirement_title": {"en": "Retirement claim", "fr": "Demande de retraite"},
        "retirement_description": {
            "en": "One online claim on info-retraite.fr covers every scheme, 4 to 6 months "
            "before the chosen date.",
            "fr": "Une seule demande en ligne sur info-retraite.fr pour tous vos régimes, 4 à 6 "
            "mois avant la date de départ choisie.",
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
        "current_identity_label": {
            "en": "Current identity card or passport, even expired",
            "fr": "Carte d'identité ou passeport actuel, même périmé",
        },
        "current_identity_hint": {
            "en": "If it was lost or stolen: the loss or theft declaration instead.",
            "fr": "En cas de perte ou de vol : la déclaration de perte ou de vol à la place.",
        },
        "recent_address_label": {
            "en": "Proof of address less than one year old",
            "fr": "Justificatif de domicile de moins d'un an",
        },
        "birth_certificate_label": {"en": "Birth certificate", "fr": "Acte de naissance"},
        "birth_certificate_hint": {
            "en": "Only if your former document expired more than 5 years ago or was lost, and "
            "your birthplace does not share its records online.",
            "fr": "Seulement si l'ancienne pièce est périmée depuis plus de 5 ans ou perdue, et "
            "si votre commune de naissance n'est pas dématérialisée.",
        },
        "child_civil_status_label": {
            "en": "Family record book or child's birth certificate",
            "fr": "Livret de famille ou acte de naissance de l'enfant",
        },
        "child_civil_status_hint": {
            "en": "Ask the town hall of the place of birth for a copy of the birth certificate.",
            "fr": "Demandez une copie de l'acte de naissance à la mairie du lieu de naissance.",
        },
        "parent_identity_label": {
            "en": "Identity document of a parent",
            "fr": "Pièce d'identité d'un parent",
        },
        "former_school_label": {
            "en": "Certificate from the former school",
            "fr": "Certificat de radiation de l'ancienne école",
        },
        "former_school_hint": {
            "en": "Only when changing school: the former school gives it.",
            "fr": "Seulement en cas de changement d'école : l'ancienne école le délivre.",
        },
        "pension_statement_label": {"en": "Career statement", "fr": "Relevé de carrière"},
        "pension_statement_hint": {
            "en": "Downloadable from info-retraite.fr; check every year is there.",
            "fr": "Téléchargeable sur info-retraite.fr ; vérifiez que toutes vos années y sont.",
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
        "custom_title": {"en": "File: {purpose}", "fr": "Dossier : {purpose}"},
        "custom_description": {
            "en": "Pieces Binder found in your documents for this request.",
            "fr": "Pièces trouvées par Binder dans vos documents pour cette demande.",
        },
        "custom_missing_hint": {
            "en": "Not found in your documents: add it if you have it.",
            "fr": "Introuvable dans vos documents : ajoutez-le si vous l'avez.",
        },
        "found_hint": {"en": "Found in your documents.", "fr": "Trouvé dans vos documents."},
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
    # An expired document still does (the former identity card for its renewal).
    expired_ok: bool = False
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
BANK_DETAILS = Piece("bank_details", _type_in(DocType.BANK_DETAILS))


def _proof_of_address(d: Document) -> bool:
    return d.doc_type in PROOF_OF_ADDRESS and d.category in {
        Category.ENERGY,
        Category.TELECOM,
        Category.HOUSING,
    }


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
                Piece("proof_of_address", _proof_of_address, max_age=92),
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
                BANK_DETAILS,
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
        FolderKind(
            "identity_renewal",
            [
                Piece(
                    "current_identity",
                    _type_in(DocType.IDENTITY_CARD, DocType.PASSPORT),
                    expired_ok=True,
                ),
                Piece(
                    "recent_address",
                    _proof_of_address,
                    max_age=365,
                    hint_text="proof_of_address_hint",
                ),
                Piece("birth_certificate", _type_in(DocType.CIVIL_STATUS), optional=True),
            ],
        ),
        FolderKind(
            "school",
            [
                Piece(
                    "child_civil_status",
                    _type_in(DocType.FAMILY_RECORD_BOOK, DocType.CIVIL_STATUS),
                ),
                Piece("proof_of_address", _proof_of_address, max_age=92),
                Piece("parent_identity", IDENTITY.match, hint_text="identity_hint"),
                Piece("former_school", _type_in(DocType.SCHOOL_CERTIFICATE), optional=True),
            ],
        ),
        FolderKind(
            "retirement",
            [
                Piece("pension_statement", _type_in(DocType.PENSION_STATEMENT)),
                IDENTITY,
                BANK_DETAILS,
                TAX_NOTICE,
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
    if doc.expiry_date is not None and doc.expiry_date < today and not piece.expired_ok:
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
    title: str | i18n.Msg = T.msg(f"{status.key}_title") if status.key in KINDS else status.title
    return T.msg("exported", title=title, ready=status.ready, total=status.total)


# --- Packs asked for in words -----------------------------------------------------------

CUSTOM_KEY = "folders.custom"
# Words naming the common packs (normalized).
KIND_WORDS = {
    "rental": r"locat|louer|bail|proprietaire|landlord|rent(?:al|ing)|flat|apartment|appartement",
    "mortgage": r"pret|credit immobilier|emprunt|banque|mortgage|loan",
    "caf": r"(?<![a-z])caf(?![a-z])|apl|aide au logement|allocation logement|housing benefit",
    "identity_renewal": r"renouvel\w* (?:de )?(?:ma |mon |la |le )?(?:carte d'identite|cni|"
    r"passeport)|(?:identity card|passport) renewal|renew (?:my )?(?:identity card|passport)",
    "school": r"inscription (?:scolaire|a l'ecole)|school enrol",
    "retirement": r"retraite|retirement|pension claim",
}
PICK_PROMPT = """The user needs to put together a file of documents: "{purpose}". Country: \
{country}. Their documents (id, title, type, date, person):
{documents}
Return JSON: title (short, in {language}), pieces: the documents such a file usually requires, \
each with label (in {language}), document_ids (the matching ids above, most recent first; empty \
if none matches) and hint (in {language}: where to get it if missing). 3 to 8 pieces."""
PICK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "pieces": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "document_ids": {"type": "array", "items": {"type": "integer"}},
                    "hint": {"type": "string"},
                },
                "required": ["label", "document_ids", "hint"],
            },
        },
    },
    "required": ["title", "pieces"],
}


class _Picked(BaseModel):
    title: str
    pieces: list[dict[str, Any]]


def kind_for(purpose: str) -> FolderKind | None:
    """One of the common packs, when the request names it ("rental", "dossier de location")."""
    if purpose in KINDS:
        return KINDS[purpose]
    norm = normalize(purpose)
    return next((KINDS[k] for k, words in KIND_WORDS.items() if re.search(words, norm)), None)


def _date_label(doc: Document) -> str:
    return _date_of(doc).isoformat()


def _pick_llm(purpose: str, docs: list[Document]) -> _Picked | None:
    listing = "\n".join(
        f"{d.id}; {d.title}; {d.doc_type or '-'}; {_date_label(d)}; {d.person or '-'}"
        for d in docs[:200]
    )
    prompt = PICK_PROMPT.format(
        purpose=purpose,
        documents=listing,
        language=i18n.language_name(i18n.current_language()),
        country=llm.user_context()["country"],
    )
    try:
        message = llm.chat([{"role": "user", "content": prompt}], fmt=PICK_SCHEMA)
        return _Picked.model_validate(json.loads(message.get("content") or "{}"))
    except (httpx.HTTPError, llm.ModelError, json.JSONDecodeError, ValidationError, KeyError):
        log.exception("Pack by the model failed, falling back to keywords")
        return None


def _pick_rules(purpose: str, docs: list[Document]) -> _Picked:
    """Without a model: an identity document, then the types the request names."""
    words = [w for w in re.findall(r"[a-z]{4,}", normalize(purpose))]
    pieces: list[dict[str, Any]] = [
        {
            "label": IDENTITY.label,
            "document_ids": [],
            "hint": IDENTITY.hint,
            "types": IDENTITY_TYPES,
        }
    ]
    for doc_type in DocType:
        names = normalize(" ".join(i18n.doc_type_label(doc_type, lang) for lang in i18n.LANGUAGES))
        if any(w in names for w in words):
            pieces.append(
                {"label": i18n.doc_type_label(doc_type), "document_ids": [], "types": {doc_type}}
            )
    for piece in pieces:
        types = piece.pop("types")
        found = sorted((d for d in docs if d.doc_type in types), key=_date_of)
        piece["document_ids"] = [d.id for d in reversed(found)][:3]
    return _Picked(title=T("custom_title", purpose=purpose), pieces=pieces)


def prepare(session: Session, purpose: str) -> FolderStatus:
    """The pack for a request in words: a common pack, or one put together for it (saved so
    that it can be exported)."""
    kind = kind_for(purpose)
    if kind is not None:
        return evaluate(session, kind)
    docs = current_documents(session)
    picked = _pick_llm(purpose, docs) if llm.is_available() else None
    picked = picked or _pick_rules(purpose, docs)
    known = {d.id for d in docs}
    pieces = []
    for raw in picked.pieces:
        ids = [i for i in raw.get("document_ids") or [] if i in known]
        label = str(raw.get("label") or "").strip()
        if not label:
            continue
        pieces.append(
            PieceStatus(
                key=re.sub(r"[^a-z0-9]+", "_", normalize(label)).strip("_")[:40],
                label=label,
                status="ok" if ids else "missing",
                found=1 if ids else 0,
                needed=1,
                optional=False,
                hint=str(raw.get("hint") or "")
                or (T("found_hint") if ids else T("custom_missing_hint")),
                document_ids=ids,
            )
        )
    token = secrets.token_urlsafe(8)
    ready = sum(p.status == "ok" for p in pieces)
    status = FolderStatus(
        key=f"custom-{token}",
        title=picked.title.strip() or T("custom_title", purpose=purpose),
        description=purpose,
        complete=ready == len(pieces),
        ready=ready,
        total=len(pieces),
        pieces=pieces,
    )
    saved = settings_store.load(session, CUSTOM_KEY, CustomFolders)
    saved.folders = {**dict(list(saved.folders.items())[-19:]), status.key: status}
    settings_store.save(session, CUSTOM_KEY, saved)
    return status


class CustomFolders(BaseModel):
    folders: dict[str, FolderStatus] = {}


def saved(session: Session, key: str) -> FolderStatus | None:
    """A pack put together earlier, with its pieces checked again (trash, new versions)."""
    status = settings_store.load(session, CUSTOM_KEY, CustomFolders).folders.get(key)
    if status is None:
        return None
    active = {d.id for d in current_documents(session)}
    for piece in status.pieces:
        piece.document_ids = [i for i in piece.document_ids if i in active]
        piece.status = "ok" if piece.document_ids else "missing"
    status.ready = sum(p.status == "ok" for p in status.pieces)
    status.complete = status.ready == status.total
    return status
