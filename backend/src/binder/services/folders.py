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
    title: str | i18n.Msg = T.msg(f"{status.key}_title") if status.key in KINDS else status.title
    return T.msg("exported", title=title, ready=status.ready, total=status.total)


# --- Packs asked for in words -----------------------------------------------------------

CUSTOM_KEY = "folders.custom"
# Words naming the common packs (normalized).
KIND_WORDS = {
    "rental": r"locat|louer|bail|proprietaire|landlord|rent(?:al|ing)|flat|apartment|appartement",
    "mortgage": r"pret|credit immobilier|emprunt|banque|mortgage|loan",
    "caf": r"(?<![a-z])caf(?![a-z])|apl|aide au logement|allocation logement|housing benefit",
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
    except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError):
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
