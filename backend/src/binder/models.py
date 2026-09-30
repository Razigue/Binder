"""Tables SQLModel."""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class Category(StrEnum):
    IMPOTS = "Impôts"
    ENERGIE = "Énergie"
    ASSURANCE = "Assurance"
    BANQUE = "Banque"
    LOGEMENT = "Logement"
    SANTE = "Santé"
    SOCIAL = "Social"
    TRAVAIL = "Travail"
    TELECOM = "Télécom"
    IDENTITE = "Identité"
    VEHICULE = "Véhicule"
    AUTRE = "Autre"


class DocumentStatus(StrEnum):
    PROCESSING = "processing"
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
    category: Category = Field(default=Category.AUTRE, index=True)
    issuer: str | None = None
    amount: float | None = None
    issue_date: date | None = None
    due_date: date | None = Field(default=None, index=True)
    # Fin de validité (pièce d'identité, attestation, contrôle technique).
    expiry_date: date | None = Field(default=None, index=True)
    reference: str | None = None
    # L'utilisateur garde ce document au-delà de la durée de conservation conseillée.
    keep_forever: bool = False

    confidence: float = 0.0
    status: DocumentStatus = Field(default=DocumentStatus.PROCESSING, index=True)
    # Liste JSON des champs manquants ou douteux.
    missing_fields: str = "[]"
    extractor: str = "rules"
    doc_type: str | None = None
    # Doublon probable (contenu quasi identique à un document déjà présent).
    duplicate_of: int | None = Field(default=None, index=True)
    # L'utilisateur a confirmé que ce n'est pas un doublon : on ne le signale plus.
    duplicate_dismissed: bool = False
    # Ancienne version d'un document renouvelé (attestation, pièce d'identité…).
    superseded_by: int | None = Field(default=None, index=True)
    page_count: int = 0
    text: str = ""

    created_at: datetime = Field(default_factory=_now, index=True)
    updated_at: datetime = Field(default_factory=_now)
    # Corbeille : un document supprimé reste restaurable jusqu'à sa suppression définitive.
    deleted_at: datetime | None = Field(default=None, index=True)


class Deadline(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int | None = Field(default=None, foreign_key="document.id", index=True)
    title: str
    category: Category = Category.AUTRE
    due_date: date = Field(index=True)
    amount: float | None = None
    done: bool = False
    # "extracted" (paiement déduit d'un document), "expiry" (fin de validité d'un document)
    # ou "manual" (rappel créé par l'utilisateur ou l'agent).
    source: str = "extracted"
    created_at: datetime = Field(default_factory=_now)


class Activity(SQLModel, table=True):
    """Journal lisible de tout ce que Binder (ou l'utilisateur) a fait.

    Pas de clé étrangère vers le document : l'entrée survit à sa suppression définitive.
    """

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now, index=True)
    # « user » (action dans l'interface), « binder » (automatique), « agent », « watcher ».
    actor: str = "binder"
    action: str = Field(index=True)
    summary: str
    document_id: int | None = Field(default=None, index=True)
    # Détails JSON (ancienne/nouvelle valeur d'un champ, confiance…).
    details: str = "{}"
