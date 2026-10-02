"""SQLModel tables."""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class Category(StrEnum):
    """Stable identifiers; labels live in binder.i18n (CATEGORIES)."""

    TAXES = "taxes"
    ENERGY = "energy"
    INSURANCE = "insurance"
    BANK = "bank"
    HOUSING = "housing"
    HEALTH = "health"
    SOCIAL = "social"
    WORK = "work"
    TELECOM = "telecom"
    IDENTITY = "identity"
    VEHICLE = "vehicle"
    # School, childcare, activities of the children.
    FAMILY = "family"
    # Purchase invoices and their warranties.
    PURCHASES = "purchases"
    OTHER = "other"


class DocType(StrEnum):
    """Detected document type. Stable identifiers; labels live in binder.i18n (DOC_TYPES)."""

    IDENTITY_CARD = "identity_card"
    PASSPORT = "passport"
    DRIVING_LICENCE = "driving_licence"
    RESIDENCE_PERMIT = "residence_permit"
    ROADWORTHINESS_TEST = "roadworthiness_test"
    VEHICLE_REGISTRATION = "vehicle_registration"
    BANK_DETAILS = "bank_details"
    EMPLOYMENT_CONTRACT = "employment_contract"
    LEASE = "lease"
    PROPERTY_TAX = "property_tax"
    HOUSING_TAX = "housing_tax"
    TAX_NOTICE = "tax_notice"
    RENT_RECEIPT = "rent_receipt"
    PAYMENT_NOTICE = "payment_notice"
    INSURANCE_CERTIFICATE = "insurance_certificate"
    BANK_STATEMENT = "bank_statement"
    PAYSLIP = "payslip"
    REIMBURSEMENT_STATEMENT = "reimbursement_statement"
    CERTIFICATE = "certificate"
    QUOTE = "quote"
    PAYMENT_SCHEDULE = "payment_schedule"
    INVOICE = "invoice"
    CONTRACT = "contract"
    LOAN_STATEMENT = "loan_statement"
    SAVINGS_STATEMENT = "savings_statement"
    # Imprimé fiscal unique: what a bank declared to the tax office (interest, dividends).
    ANNUAL_TAX_STATEMENT = "annual_tax_statement"
    DONATION_RECEIPT = "donation_receipt"
    CHILDCARE_CERTIFICATE = "childcare_certificate"
    SCHOOL_CERTIFICATE = "school_certificate"
    CIVIL_STATUS = "civil_status"
    FAMILY_RECORD_BOOK = "family_record_book"
    PENSION_STATEMENT = "pension_statement"
    # Decision of a benefits office (rights, overpayment, end of payment).
    BENEFIT_DECISION = "benefit_decision"
    CHARGES_STATEMENT = "charges_statement"
    FINE = "fine"
    # Purchase invoice whose warranty is tracked (expiry_date = end of warranty).
    PURCHASE_RECEIPT = "purchase_receipt"
    # Reminder or formal notice about an unpaid bill (relance, mise en demeure).
    PAYMENT_REMINDER = "payment_reminder"


# Enum member names stored by versions before the English identifiers (SQLAlchemy stores
# member names, not values). Migrated by binder.db.
LEGACY_CATEGORY_NAMES = {
    "IMPOTS": "TAXES",
    "ENERGIE": "ENERGY",
    "ASSURANCE": "INSURANCE",
    "BANQUE": "BANK",
    "LOGEMENT": "HOUSING",
    "SANTE": "HEALTH",
    "TRAVAIL": "WORK",
    "IDENTITE": "IDENTITY",
    "VEHICULE": "VEHICLE",
    "AUTRE": "OTHER",
}
# doc_type is plain text: former versions stored the French label.
LEGACY_DOC_TYPES = {
    "Carte d'identité": DocType.IDENTITY_CARD,
    "Passeport": DocType.PASSPORT,
    "Permis de conduire": DocType.DRIVING_LICENCE,
    "Titre de séjour": DocType.RESIDENCE_PERMIT,
    "Contrôle technique": DocType.ROADWORTHINESS_TEST,
    "Carte grise": DocType.VEHICLE_REGISTRATION,
    "RIB": DocType.BANK_DETAILS,
    "Contrat de travail": DocType.EMPLOYMENT_CONTRACT,
    "Bail": DocType.LEASE,
    "Taxe foncière": DocType.PROPERTY_TAX,
    "Taxe d'habitation": DocType.HOUSING_TAX,
    "Avis d'imposition": DocType.TAX_NOTICE,
    "Quittance de loyer": DocType.RENT_RECEIPT,
    "Avis d'échéance": DocType.PAYMENT_NOTICE,
    "Attestation d'assurance": DocType.INSURANCE_CERTIFICATE,
    "Relevé bancaire": DocType.BANK_STATEMENT,
    "Bulletin de paie": DocType.PAYSLIP,
    "Décompte de remboursement": DocType.REIMBURSEMENT_STATEMENT,
    "Attestation": DocType.CERTIFICATE,
    "Devis": DocType.QUOTE,
    "Échéancier": DocType.PAYMENT_SCHEDULE,
    "Facture": DocType.INVOICE,
    "Contrat": DocType.CONTRACT,
}


class DocumentStatus(StrEnum):
    PROCESSING = "processing"
    # A real document imported before the local AI was ready: analysed as soon as it is.
    WAITING = "waiting"
    TO_REVIEW = "to_review"
    CLASSIFIED = "classified"


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    filename: str
    mime_type: str
    size: int
    sha256: str = Field(index=True, unique=True)
    stored_name: str

    title: str = ""
    category: Category = Field(default=Category.OTHER, index=True)
    issuer: str | None = None
    amount: float | None = None
    issue_date: date | None = None
    due_date: date | None = Field(default=None, index=True)
    # End of validity (identity document, certificate, roadworthiness test).
    expiry_date: date | None = Field(default=None, index=True)
    reference: str | None = None
    # The user keeps this document beyond the recommended retention period.
    keep_forever: bool = False

    confidence: float = 0.0
    status: DocumentStatus = Field(default=DocumentStatus.PROCESSING, index=True)
    # JSON list of missing or doubtful fields.
    missing_fields: str = "[]"
    extractor: str = "rules"
    # DocType value (kept as text: unknown values from newer versions stay readable).
    doc_type: str | None = None
    # Probable duplicate (content nearly identical to an existing document).
    duplicate_of: int | None = Field(default=None, index=True)
    # The user confirmed it is not a duplicate: no longer flagged.
    duplicate_dismissed: bool = False
    # Former version of a renewed document (certificate, identity document…).
    superseded_by: int | None = Field(default=None, index=True)
    page_count: int = 0
    # Import batch (one drop of files, one mailbox pass, one phone scan): the import report
    # groups its documents.
    batch: str | None = Field(default=None, index=True)
    # Household member the document concerns, as written in it ("Camille Martin").
    person: str | None = Field(default=None, index=True)
    # Life area shown in the navigation (services/areas.py), kept in step with the category.
    area: str | None = Field(default=None, index=True)
    # Breakdown of the amounts (`amount` stays the main figure every feature uses).
    amount_ht: float | None = None
    amount_tva: float | None = None
    amount_ttc: float | None = None
    amount_due: float | None = None
    period_start: date | None = None
    period_end: date | None = None
    iban: str | None = None
    siret: str | None = None
    # JSON list of the doubts the checks raised (services/verify.py), until validation.
    doubts: str = "[]"

    created_at: datetime = Field(default_factory=_now, index=True)
    updated_at: datetime = Field(default_factory=_now)
    # Trash: a deleted document can be restored until it is permanently deleted.
    deleted_at: datetime | None = Field(default=None, index=True)

    # Large columns, last (see HEAVY_COLUMNS): SQLite stores the end of a long row in
    # overflow pages, read through to reach any column stored after them.
    # Plain-language explanation (JSON), recomputed when the document or language changes.
    explanation: str | None = None
    text: str = ""


# Kept at the end of the document table (binder.db rebuilds it when a column follows them).
HEAVY_COLUMNS = ("explanation", "text")


class Deadline(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int | None = Field(default=None, foreign_key="document.id", index=True)
    title: str
    category: Category = Category.OTHER
    due_date: date = Field(index=True)
    amount: float | None = None
    done: bool = False
    # "extracted" (payment found in a document), "expiry" (end of validity of a document)
    # or "manual" (reminder created by the user or the agent).
    source: str = "extracted"
    created_at: datetime = Field(default_factory=_now)


class Activity(SQLModel, table=True):
    """Readable log of everything Binder (or the user) did.

    No foreign key to the document: the entry survives its permanent deletion.
    """

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now, index=True)
    # "user" (action in the interface), "binder" (automatic), "agent", "watcher".
    actor: str = "binder"
    action: str = Field(index=True)
    summary: str
    document_id: int | None = Field(default=None, index=True)
    # JSON details (old/new field value, confidence…), and "msg": the summary as an
    # i18n message key + parameters, rendered in the current language when displayed.
    details: str = "{}"


class Setting(SQLModel, table=True):
    """Settings editable from the interface (JSON value). Stored in the encrypted database."""

    key: str = Field(primary_key=True)
    value: str = "null"


class Embedding(SQLModel, table=True):
    """Vector of a piece of a document, for semantic search (see services/embeddings.py).

    Recomputed when the document changes; vectors of another model are ignored."""

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(index=True)
    chunk: int = 0
    model: str = Field(index=True)
    # Normalized float32 values.
    vector: bytes


class UndoEntry(SQLModel, table=True):
    """What an action changed, to put it back right after (services/undo.py)."""

    id: int | None = Field(default=None, primary_key=True)
    token: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=_now, index=True)
    actor: str = "user"
    # JSON list of steps, undone in reverse order.
    steps: str = "[]"
    undone: bool = False


class Correspondence(SQLModel, table=True):
    """A letter written by Binder, followed until it is answered."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now, index=True)
    document_id: int | None = Field(default=None, index=True)
    # Letter kind ("termination", "complaint", "request", "followup", "custom").
    kind: str = "custom"
    subject: str
    recipient: str
    recipient_address: str = ""
    body: str
    language: str = "fr"
    registered: bool = False
    sent_on: date | None = None
    # Date at which a follow-up is suggested if no answer came.
    follow_up_on: date | None = Field(default=None, index=True)
    answered: bool = False
    # Letter this one follows up.
    follows: int | None = None
    # Legal points checked online when it was written (schemas.LegalCheck, JSON).
    verification: str | None = None
    # Web pages it was adapted from (list of schemas.LegalSource, JSON).
    sources: str | None = None


class Learned(SQLModel, table=True):
    """A correction the user made, applied again to the next documents of the same sender."""

    id: int | None = Field(default=None, primary_key=True)
    # Normalized sender key (issuer, or the first line of the document).
    sender: str = Field(index=True)
    field: str
    # Value set by the user (JSON).
    value: str
    # For amounts and dates: the label preceding the value in the document ("net a payer").
    label: str = ""
    count: int = 1
    updated_at: datetime = Field(default_factory=_now)


class Journey(SQLModel, table=True):
    """A life event followed step by step (services/journeys.py): moving, a birth, the tax
    return… Steps are computed from the kind and the user's documents; only what the user did
    is stored."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now, index=True)
    # Kind identifier ("moving", "birth", "death", "tax_return").
    kind: str = Field(index=True)
    # Date the steps are counted from (moving day, birth, death, filing deadline).
    event_date: date
    # JSON: what the user told Binder (new address, person concerned…).
    details: str = "{}"
    # JSON list of the keys of the steps marked done.
    done: str = "[]"
    closed: bool = False
