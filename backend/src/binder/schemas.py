"""Schémas Pydantic exposés par l'API et utilisés pour l'extraction."""

import json
from datetime import date, datetime

from pydantic import BaseModel, Field

from binder.models import Activity, Category, Deadline, Document, DocumentStatus


class Extraction(BaseModel):
    """Informations clés extraites d'un document."""

    category: Category = Category.AUTRE
    title: str = ""
    issuer: str | None = None
    amount: float | None = None
    issue_date: date | None = None
    due_date: date | None = None
    expiry_date: date | None = None
    reference: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    missing_fields: list[str] = []
    extractor: str = "rules"
    # Type détecté par les règles (« Facture », « Attestation d'assurance »…).
    doc_type: str | None = None


class DocumentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    size: int
    title: str
    category: Category
    issuer: str | None
    amount: float | None
    issue_date: date | None
    due_date: date | None
    expiry_date: date | None = None
    keep_forever: bool = False
    reference: str | None
    confidence: float
    status: DocumentStatus
    missing_fields: list[str]
    extractor: str
    page_count: int
    created_at: datetime
    deleted_at: datetime | None = None
    doc_type: str | None = None
    duplicate_of: int | None = None
    superseded_by: int | None = None
    # Nom normalisé utilisé au téléchargement et à l'export (« 2026-09-18 Facture EDF.pdf »).
    standard_name: str = ""
    # Conservation : règle applicable, date jusqu'à laquelle garder, raison de trier.
    retention_rule: str | None = None
    keep_until: date | None = None
    deletable_reason: str | None = None
    # Date à partir de laquelle renouveler un document qui expire.
    renew_from: date | None = None

    @classmethod
    def from_model(cls, doc: Document) -> "DocumentOut":
        from binder.services import deadlines, organize, retention

        data = doc.model_dump(
            exclude={"text", "missing_fields", "sha256", "stored_name", "explanation"}
        )
        rule = retention.rule_for(doc)
        return cls(
            **data,
            missing_fields=json.loads(doc.missing_fields),
            standard_name=organize.standard_name(doc),
            retention_rule=rule.label if rule else None,
            keep_until=retention.keep_until(doc),
            deletable_reason=retention.deletion_reason(doc),
            renew_from=deadlines.renew_from(doc),
        )


class DocumentDetail(DocumentOut):
    text: str

    @classmethod
    def from_model(cls, doc: Document) -> "DocumentDetail":
        base = DocumentOut.from_model(doc)
        return cls(**base.model_dump(), text=doc.text)


class DocumentUpdate(BaseModel):
    title: str | None = None
    category: Category | None = None
    issuer: str | None = None
    amount: float | None = None
    issue_date: date | None = None
    due_date: date | None = None
    expiry_date: date | None = None
    reference: str | None = None
    doc_type: str | None = None
    keep_forever: bool | None = None
    # Valider manuellement le document le sort de la file « à vérifier ».
    validated: bool | None = None


class ExpirationOut(BaseModel):
    document: DocumentOut
    expiry_date: date
    renew_from: date
    days_left: int
    # « expired », « renew » (dans le délai de renouvellement) ou « valid ».
    state: str


class TrashRequest(BaseModel):
    ids: list[int]


class DeadlineOut(BaseModel):
    id: int
    document_id: int | None
    title: str
    category: Category
    due_date: date
    amount: float | None
    done: bool
    source: str
    days_left: int

    @classmethod
    def from_model(cls, d: Deadline, today: date) -> "DeadlineOut":
        return cls(**d.model_dump(exclude={"created_at"}), days_left=(d.due_date - today).days)


class DeadlineCreate(BaseModel):
    title: str
    due_date: date
    category: Category = Category.AUTRE
    amount: float | None = None
    document_id: int | None = None


class DeadlineUpdate(BaseModel):
    done: bool | None = None
    title: str | None = None
    due_date: date | None = None


class Stats(BaseModel):
    upcoming_deadlines: int
    to_review: int
    classified_this_week: int
    total_documents: int
    trashed: int = 0
    by_category: dict[str, int]


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ToolCallTrace(BaseModel):
    name: str
    arguments: dict[str, object]


class ChatResponse(BaseModel):
    answer: str
    documents: list[DocumentOut] = []
    deadlines: list[DeadlineOut] = []
    tool_calls: list[ToolCallTrace] = []
    # Documents cités dans la réponse ([#id]), tous issus des résultats d'outils.
    citations: list[int] = []
    engine: str


class SystemStatus(BaseModel):
    llm_available: bool
    llm_model: str
    ocr_engine: str | None
    encrypted: bool
    data_dir: str


class ActivityOut(BaseModel):
    id: int
    created_at: datetime
    actor: str
    action: str
    summary: str
    document_id: int | None
    details: dict[str, object]

    @classmethod
    def from_model(cls, a: Activity) -> "ActivityOut":
        data = a.model_dump(exclude={"details"})
        return cls(**data, details=json.loads(a.details))


class FolderSettings(BaseModel):
    enabled: bool = False
    path: str = ""
    last_check: datetime | None = None
    last_error: str | None = None


class MailSettings(BaseModel):
    enabled: bool = False
    host: str = ""
    port: int = 993
    user: str = ""
    folder: str = "INBOX"
    since_days: int = 30
    # Le mot de passe n'est jamais renvoyé par l'API.
    password_set: bool = False
    last_check: datetime | None = None
    last_error: str | None = None


class ImportSettings(BaseModel):
    folder: FolderSettings
    mail: MailSettings


class FolderSettingsIn(BaseModel):
    enabled: bool
    path: str = ""


class MailSettingsIn(BaseModel):
    enabled: bool
    host: str = ""
    port: int = 993
    user: str = ""
    folder: str = "INBOX"
    since_days: int = Field(default=30, ge=1, le=365)
    # Absent : on garde le mot de passe enregistré.
    password: str | None = None


class ImportSettingsIn(BaseModel):
    folder: FolderSettingsIn | None = None
    mail: MailSettingsIn | None = None
