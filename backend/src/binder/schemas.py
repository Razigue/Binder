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
    # Main figure, derived from the amounts below (verify.main_amount): what is left to pay or
    # received, else the total.
    amount: float | None = None
    amount_ht: float | None = None
    amount_tva: float | None = None
    amount_ttc: float | None = None
    # Left to pay or received now: net pay, refund, balance after a deposit.
    amount_due: float | None = None
    issue_date: date | None = None
    due_date: date | None = None
    expiry_date: date | None = None
    # Period the document covers (billing, pay, rent).
    period_start: date | None = None
    period_end: date | None = None
    reference: str | None = None
    iban: str | None = None
    siret: str | None = None
    # Computed from the checks of services/verify.py, never declared by the model.
    confidence: float = Field(default=0.0, ge=0, le=1)
    missing_fields: list[str] = []
    # Doubts raised by the checks ("unverified:due_date"): the document goes to review.
    doubts: list[str] = []
    extractor: str = "rules"
    # Document type (a DocType value: "invoice", "insurance_certificate"…).
    doc_type: str | None = None
    # Person the document concerns (holder, employee, tenant, insured…).
    person: str | None = None


class DocumentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    size: int
    title: str
    category: Category
    issuer: str | None
    amount: float | None
    amount_ht: float | None = None
    amount_tva: float | None = None
    amount_ttc: float | None = None
    amount_due: float | None = None
    issue_date: date | None
    due_date: date | None
    expiry_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    keep_forever: bool = False
    reference: str | None
    iban: str | None = None
    siret: str | None = None
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
    # Set when this document is a copy of a letter Binder itself wrote, not mail received.
    source_letter_id: int | None = None
    # Standard name used for downloads and exports ("2026-09-18 EDF invoice.pdf").
    standard_name: str = ""
    # Retention: applicable rule, date until which to keep it, reason to sort it out.
    retention_rule: str | None = None
    keep_until: date | None = None
    deletable_reason: str | None = None
    # Date from which an expiring document should be renewed.
    renew_from: date | None = None
    person: str | None = None
    area: str | None = None
    batch: str | None = None

    @classmethod
    def from_model(cls, doc: Document) -> "DocumentOut":
        from binder.services import deadlines, organize, retention

        data = doc.model_dump(
            exclude={"text", "missing_fields", "doubts", "sha256", "stored_name", "explanation"}
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
    person: str | None = None
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


class DocumentIds(BaseModel):
    """Documents selected together in a list (grouped actions)."""

    ids: list[int] = Field(min_length=1, max_length=1000)


class BulkUpdate(DocumentIds):
    category: Category | None = None
    keep_forever: bool | None = None
    validated: bool | None = None


class BulkPurge(DocumentIds):
    confirm: bool = False


class BulkResult(BaseModel):
    count: int
    # Shown in the "Undo" toast.
    message: str


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
    # Document open on screen while asking: "this document", "how much?" refer to it.
    viewing: int | None = None


class ToolCallTrace(BaseModel):
    name: str
    arguments: dict[str, object]
    # Time the tool took, and whether it answered with an error.
    duration_ms: int | None = None
    error: bool = False


class ChatStats(BaseModel):
    """What the local model did for one answer: shown under it for the curious."""

    model: str
    # Model turns (each tool round trip is one).
    turns: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    # Generation speed, output tokens over the time spent writing them.
    tokens_per_second: float | None = None
    # Prompt reading speed.
    prompt_tokens_per_second: float | None = None
    # Whole answer, tools included.
    seconds: float = 0


class LegalSource(BaseModel):
    title: str
    url: str


class LegalPoint(BaseModel):
    """A legal point of a text and what the official source says about it. `outdated`: the
    source states something else (`evidence`, copied from it); the text is left as it is and
    the user decides, `correction` being the wording proposed."""

    # The point as written in the text.
    claim: str
    status: Literal["confirmed", "outdated", "unverified"]
    evidence: str = ""
    correction: str = ""
    sources: list[LegalSource] = []


class LegalCheck(BaseModel):
    """Legal points of a text checked online (services/lawcheck.py), and when. `outdated`: a
    source contradicts a point; `unverified`: a point could not be checked; `none`: no legal
    point."""

    status: Literal["verified", "outdated", "unverified", "none"]
    checked_on: date
    points: list[LegalPoint] = []


class Letter(BaseModel):
    kind: str
    subject: str
    recipient: str
    body: str
    # Sending by registered mail with acknowledgement of receipt is advised.
    registered: bool
    # Language the letter is written in ("en" or "fr"), may differ from the interface.
    language: Literal["en", "fr"]
    # Saved letter (Correspondence): PDF, "sent", follow-up.
    id: int | None = None
    document_id: int | None = None
    recipient_address: str = ""
    sent_on: date | None = None
    follow_up_on: date | None = None
    answered: bool = False
    # Words still to fill in ([to be completed]); none when Binder knew everything.
    blanks: int = 0
    # Its legal points checked online when it was written.
    verification: LegalCheck | None = None
    # Web pages it was adapted from (the organisation's procedure, its conditions).
    sources: list[LegalSource] = []


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
    # Token to undo what the agent changed during this turn.
    undo: str | None = None
    # Packs put together during the turn.
    folders: list[dict[str, object]] = []
    # Journeys started or read during the turn.
    journeys: list[dict[str, object]] = []
    # Token counts and speed of the model, None without a model.
    stats: ChatStats | None = None
    # Changes held back for the user's confirmation (agent/confirm.py): token, description.
    confirmations: list[dict[str, str]] = []
    # Shown under the answer (a legal point that could not be checked online).
    warnings: list[str] = []


class ConfirmResult(BaseModel):
    message: str
    changed: bool = False
    undo: str | None = None


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
    # A template kind ("termination"…) or, with `purpose`, any letter described in words.
    kind: str | None = None
    purpose: str = Field(default="", max_length=2000)
    document_id: int | None = None
    details: str = Field(default="", max_length=4000)


class LetterEdit(BaseModel):
    body: str = Field(max_length=20000)


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
