"""Schémas Pydantic exposés par l'API et utilisés pour l'extraction."""

import json
from datetime import date, datetime

from pydantic import BaseModel, Field

from binder.models import Category, Deadline, Document, DocumentStatus


class Extraction(BaseModel):
    """Informations clés extraites d'un document."""

    category: Category = Category.AUTRE
    title: str = ""
    issuer: str | None = None
    amount: float | None = None
    issue_date: date | None = None
    due_date: date | None = None
    reference: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    missing_fields: list[str] = []
    extractor: str = "rules"


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
    reference: str | None
    confidence: float
    status: DocumentStatus
    missing_fields: list[str]
    extractor: str
    page_count: int
    created_at: datetime

    @classmethod
    def from_model(cls, doc: Document) -> "DocumentOut":
        data = doc.model_dump(exclude={"text", "missing_fields", "sha256", "stored_name"})
        return cls(**data, missing_fields=json.loads(doc.missing_fields))


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
    reference: str | None = None
    # Valider manuellement le document le sort de la file « à vérifier ».
    validated: bool | None = None


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
    engine: str


class SystemStatus(BaseModel):
    llm_available: bool
    llm_model: str
    ocr_engine: str | None
    encrypted: bool
    data_dir: str
