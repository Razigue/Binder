"""Pydantic schemas exposed by the API and used for extraction."""

import json
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from binder.models import Activity, Category, Deadline, Document, DocumentStatus


class Extraction(BaseModel):
    """Key information extracted from a document."""

    category: Category = Category.OTHER
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
    # Type detected by the rules (a DocType value: "invoice", "insurance_certificate"…).
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
    # Standard name used for downloads and exports ("2026-09-18 EDF invoice.pdf").
    standard_name: str = ""
    # Retention: applicable rule, date until which to keep it, reason to sort it out.
    retention_rule: str | None = None
    keep_until: date | None = None
    deletable_reason: str | None = None
    # Date from which an expiring document should be renewed.
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
    # Validating the document manually takes it out of the "to review" queue.
    validated: bool | None = None


class ExpirationOut(BaseModel):
    document: DocumentOut
    expiry_date: date
    renew_from: date
    days_left: int
    # "expired", "renew" (within the renewal period) or "valid".
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
    category: Category = Category.OTHER
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
    # Documents an answer showed: the next question can refer to them ("and when is it due?").
    documents: list[int] = Field(default=[], max_length=50)


class ChatRequest(BaseModel):
    message: str = ""
    history: list[ChatMessage] = []
    # Documents the user attached to this message (already uploaded with POST /documents).
    attachments: list[int] = Field(default=[], max_length=10)


class ToolCallTrace(BaseModel):
    name: str
    arguments: dict[str, object]


class Letter(BaseModel):
    kind: str
    subject: str
    recipient: str
    body: str
    # Sending by registered mail with acknowledgement of receipt is advised.
    registered: bool
    # Language the letter is written in ("en" or "fr"), may differ from the interface.
    language: Literal["en", "fr"]


class ChatResponse(BaseModel):
    answer: str
    documents: list[DocumentOut] = []
    deadlines: list[DeadlineOut] = []
    # Letters drafted during the turn, shown ready to copy.
    letters: list[Letter] = []
    tool_calls: list[ToolCallTrace] = []
    # Documents cited in the answer ([#id]), all taken from tool results.
    citations: list[int] = []
    # The agent changed data (reminder, deadline paid, document corrected or trashed).
    changed: bool = False
    engine: str


class SystemStatus(BaseModel):
    version: str
    llm_available: bool
    llm_model: str
    ocr_engine: str | None
    encrypted: bool
    data_dir: str


class ModelDownload(BaseModel):
    phase: Literal["queued", "starting", "downloading", "verifying", "error"]
    completed: int
    total: int
    error: str | None = None


class ModelOut(BaseModel):
    name: str
    label: str
    description: str
    # Bytes: size on disk if installed, otherwise download size.
    size: int
    recommended: bool
    # "chat" (can be the active model) or "embedding" (semantic search).
    kind: str = "chat"
    in_catalog: bool
    installed: bool
    download: ModelDownload | None = None


class ModelsOverview(BaseModel):
    # False if BINDER_LLM_ENABLED=false.
    enabled: bool
    # Ollama responds.
    ollama: bool
    ollama_url: str
    active: str
    active_installed: bool
    models: list[ModelOut]


class ModelChoice(BaseModel):
    name: str


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
        from binder.services.activity import summary

        details = json.loads(a.details)
        data = a.model_dump(exclude={"details", "summary"})
        return cls(**data, summary=summary(a, details), details=details)


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
    # The password is never returned by the API.
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
    host: str = Field(default="", max_length=253)
    port: int = Field(default=993, ge=1, le=65535)
    user: str = Field(default="", max_length=320)
    folder: str = Field(default="INBOX", max_length=200)
    since_days: int = Field(default=30, ge=1, le=365)
    # Absent: the saved password is kept.
    password: str | None = Field(default=None, max_length=1024)

    @field_validator("host", "user", "folder", "password")
    @classmethod
    def _no_control(cls, value: str | None, info: ValidationInfo) -> str | None:
        """These values end up in IMAP commands: no line break, and no quote in the folder."""
        if value is None:
            return value
        forbidden = '"' + chr(92) if info.field_name in ("folder", "host") else ""
        if any(ord(c) < 32 or ord(c) == 127 or c in forbidden for c in value):
            raise ValueError("invalid character")
        if info.field_name == "host" and any(c.isspace() or c == "/" for c in value):
            raise ValueError("invalid host name")
        return value


class ImportSettingsIn(BaseModel):
    folder: FolderSettingsIn | None = None
    mail: MailSettingsIn | None = None


class LetterRequest(BaseModel):
    kind: str
    document_id: int | None = None
    details: str = ""


class PreferencesOut(BaseModel):
    """Saved choices, plus what they resolve to and what the operating system reports."""

    language: str
    country: str | None
    theme: str
    effective_language: str
    effective_country: str | None
    currency: str
    system_language: str
    system_country: str | None
