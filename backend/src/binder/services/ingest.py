"""Pipeline d'import : stockage chiffré, lecture, extraction, échéances, indexation."""

import hashlib
import json
import logging
import mimetypes
import uuid
from datetime import UTC, datetime

from sqlmodel import Session, select

from binder import security
from binder.config import get_settings
from binder.db import get_engine, index_document, unindex_document
from binder.models import Category, Deadline, Document, DocumentStatus
from binder.schemas import Extraction
from binder.services import activity, llm, rules
from binder.services.text import SUPPORTED_MIME, read_document

log = logging.getLogger(__name__)

REVIEW_THRESHOLD = 0.6


class UnsupportedFile(ValueError):
    pass


def guess_mime(filename: str, declared: str | None) -> str:
    mime = declared if declared in SUPPORTED_MIME else mimetypes.guess_type(filename)[0]
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in SUPPORTED_MIME:
        raise UnsupportedFile(f"Format non pris en charge : {filename}")
    return mime


def store(
    session: Session, data: bytes, filename: str, mime: str, *, actor: str = "user"
) -> tuple[Document, bool]:
    """Enregistre le fichier chiffré. Retourne (document, créé) ; un doublon renvoie l'existant
    (et le sort de la corbeille s'il y était)."""
    digest = hashlib.sha256(data).hexdigest()
    existing = session.exec(select(Document).where(Document.sha256 == digest)).first()
    if existing:
        if existing.deleted_at is not None:
            restore(session, existing, actor=actor, reason="réimporté")
            session.commit()
        else:
            known = existing.title or existing.filename
            activity.log(
                session,
                "duplicate",
                f"« {filename} » ignoré : déjà présent sous « {known} »",
                actor=actor,
                document=existing,
            )
            session.commit()
        session.refresh(existing)
        return existing, False
    files_dir = get_settings().files_dir
    files_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.bin"
    (files_dir / stored_name).write_bytes(security.encrypt(data))
    doc = Document(
        filename=filename, mime_type=mime, size=len(data), sha256=digest, stored_name=stored_name
    )
    session.add(doc)
    session.flush()
    source = {"watcher": "depuis le dossier surveillé", "demo": "(démonstration)"}.get(actor, "")
    activity.log(
        session,
        "import",
        f"« {filename} » importé {source}".strip(),
        actor=actor,
        document=doc,
        details={"taille": len(data)},
    )
    session.commit()
    session.refresh(doc)
    return doc, True


def load_file(doc: Document) -> bytes:
    return security.decrypt((get_settings().files_dir / doc.stored_name).read_bytes())


def delete_file(doc: Document) -> None:
    (get_settings().files_dir / doc.stored_name).unlink(missing_ok=True)


def merge(by_rules: Extraction, by_llm: Extraction | None) -> Extraction:
    """Combine les deux extractions : le modèle prime, les règles comblent ses trous."""
    if by_llm is None:
        return by_rules
    merged = by_llm.model_copy()
    for field in ("issuer", "amount", "issue_date", "due_date", "reference"):
        if getattr(merged, field) in (None, ""):
            setattr(merged, field, getattr(by_rules, field))
    if merged.category == Category.AUTRE and by_rules.category != Category.AUTRE:
        merged.category = by_rules.category
    merged.title = merged.title or by_rules.title
    if by_rules.category == merged.category:
        merged.confidence = round(max(by_llm.confidence, by_rules.confidence), 2)
    else:
        merged.confidence = round(min(by_llm.confidence, by_rules.confidence) * 0.8, 2)
    merged.extractor = "llm+rules"
    return merged


def apply_extraction(doc: Document, ext: Extraction) -> None:
    doc.title = ext.title or doc.filename
    doc.category = ext.category
    doc.issuer = ext.issuer
    doc.amount = ext.amount
    doc.issue_date = ext.issue_date
    doc.due_date = ext.due_date
    doc.reference = ext.reference
    doc.confidence = ext.confidence
    doc.extractor = ext.extractor
    refresh_status(doc)


def refresh_status(doc: Document, validated: bool = False) -> None:
    missing = rules.missing_for(doc.category, doc.model_dump())
    doc.missing_fields = json.dumps(missing)
    if validated:
        doc.status = DocumentStatus.CLASSIFIED
    elif missing or doc.confidence < REVIEW_THRESHOLD or doc.category == Category.AUTRE:
        doc.status = DocumentStatus.TO_REVIEW
    else:
        doc.status = DocumentStatus.CLASSIFIED
    doc.updated_at = datetime.now(UTC)


def sync_deadline(session: Session, doc: Document) -> None:
    """Une échéance « extraite » par document, alignée sur sa date limite."""
    existing = session.exec(
        select(Deadline).where(Deadline.document_id == doc.id, Deadline.source == "extracted")
    ).first()
    if doc.due_date is None:
        if existing:
            session.delete(existing)
        return
    deadline = existing or Deadline(document_id=doc.id, title="", due_date=doc.due_date)
    deadline.title = doc.title
    deadline.category = doc.category
    deadline.due_date = doc.due_date
    deadline.amount = doc.amount
    session.add(deadline)


def analyze(session: Session, doc: Document) -> Document:
    read = read_document(load_file(doc), doc.mime_type)
    doc.text = read.text
    doc.page_count = read.page_count
    by_rules = rules.extract(read.text)
    by_llm = llm.extract(read.text) if read.text.strip() and llm.is_available() else None
    ext = merge(by_rules, by_llm)
    if not read.text.strip():
        ext.confidence = 0.0
        ext.title = ext.title if ext.title != "Document" else doc.filename.rsplit(".", 1)[0]
    apply_extraction(doc, ext)
    session.add(doc)
    session.flush()
    sync_deadline(session, doc)
    index_document(session, doc)
    _log_analysis(session, doc)
    session.commit()
    session.refresh(doc)
    return doc


def _log_analysis(session: Session, doc: Document) -> None:
    confidence = f"confiance {round(doc.confidence * 100)} %"
    if doc.status == DocumentStatus.TO_REVIEW:
        missing = json.loads(doc.missing_fields)
        reasons = [activity.FIELD_NAMES.get(f, f) for f in missing if f != "text"]
        if "text" in missing or not doc.text.strip():
            why = "texte illisible"
        elif reasons:
            why = "manque " + ", ".join(reasons)
        elif doc.category == Category.AUTRE:
            why = "catégorie inconnue"
        else:
            why = confidence
        summary = f"« {doc.title} » mis de côté pour vérification ({why})"
    else:
        summary = f"« {doc.title} » classé dans {doc.category.value} ({confidence})"
    activity.log(
        session,
        "analyze",
        summary,
        document=doc,
        details={
            "categorie": doc.category.value,
            "confiance": doc.confidence,
            "moteur": doc.extractor,
            "montant": doc.amount,
            "echeance": doc.due_date,
            "reference": doc.reference,
        },
    )


def trash(session: Session, doc: Document, *, actor: str = "user", reason: str = "") -> None:
    """Met le document à la corbeille : caché partout, restaurable, fichier conservé."""
    doc.deleted_at = datetime.now(UTC)
    for dl in session.exec(select(Deadline).where(Deadline.document_id == doc.id)):
        if dl.source == "extracted":
            session.delete(dl)
    if doc.id is not None:
        unindex_document(session, doc.id)
    session.add(doc)
    suffix = f" ({reason})" if reason else ""
    activity.log(
        session, "trash", f"« {doc.title} » mis à la corbeille{suffix}", actor=actor, document=doc
    )


def restore(session: Session, doc: Document, *, actor: str = "user", reason: str = "") -> None:
    doc.deleted_at = None
    session.add(doc)
    session.flush()
    sync_deadline(session, doc)
    index_document(session, doc)
    suffix = f" ({reason})" if reason else ""
    activity.log(session, "restore", f"« {doc.title} » restauré{suffix}", actor=actor, document=doc)


def purge(session: Session, doc: Document, *, actor: str = "user") -> None:
    """Suppression définitive (fichier compris). Réservée aux documents déjà à la corbeille."""
    if doc.deleted_at is None:
        raise ValueError("Seul un document à la corbeille peut être supprimé définitivement")
    for dl in session.exec(select(Deadline).where(Deadline.document_id == doc.id)):
        session.delete(dl)
    activity.log(
        session,
        "purge",
        f"« {doc.title} » supprimé définitivement",
        actor=actor,
        document=doc,
    )
    delete_file(doc)
    session.delete(doc)


def analyze_in_background(doc_id: int) -> None:
    with Session(get_engine()) as session:
        doc = session.get(Document, doc_id)
        if doc is None:
            return
        try:
            analyze(session, doc)
        except Exception:
            log.exception("Analyse du document %s impossible", doc_id)
            session.rollback()
            doc = session.get(Document, doc_id)
            if doc:
                doc.status = DocumentStatus.TO_REVIEW
                doc.title = doc.title or doc.filename
                doc.missing_fields = json.dumps(["text"])
                session.add(doc)
                activity.log(
                    session,
                    "analyze",
                    f"« {doc.title} » : analyse impossible, à vérifier à la main",
                    document=doc,
                )
                session.commit()


def seed_demo(session: Session) -> list[tuple[Document, bool]]:
    """Importe les documents fictifs de démonstration (dates relatives à aujourd'hui)."""
    from binder.samples import build_samples

    results = []
    for sample in build_samples():
        doc, created = store(
            session, sample.pdf(), sample.filename, "application/pdf", actor="demo"
        )
        if created:
            analyze(session, doc)
        results.append((doc, created))
    return results
