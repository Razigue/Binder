"""Import pipeline: encrypted storage, reading, extraction, deadlines, indexing."""

import hashlib
import json
import logging
import mimetypes
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, col, or_, select

from binder import i18n, security
from binder.config import get_settings
from binder.db import get_engine, index_document, unindex_document
from binder.models import Category, Correspondence, Deadline, Document, DocumentStatus
from binder.schemas import Extraction
from binder.services import (
    activity,
    anomalies,
    areas,
    deadlines,
    embeddings,
    household,
    learning,
    llm,
    organize,
    profile,
    rules,
    subscriptions,
    undo,
    verify,
)
from binder.services.text import (
    SUPPORTED_MIME,
    ReadResult,
    is_bare_a4_pdf,
    page_image,
    read_document,
    several_documents,
)

log = logging.getLogger(__name__)

T = i18n.catalog(
    "ingest",
    {
        "unsupported": {
            "en": "Unsupported format: {filename}",
            "fr": "Format non pris en charge : {filename}",
        },
        "duplicate": {
            "en": "“{filename}” ignored: already present as “{known}”",
            "fr": "« {filename} » ignoré : déjà présent sous « {known} »",
        },
        "imported": {"en": "“{filename}” imported", "fr": "« {filename} » importé"},
        "imported_from": {
            "en": "“{filename}” imported {origin}",
            "fr": "« {filename} » importé {origin}",
        },
        "demo_origin": {"en": "(demo)", "fr": "(démonstration)"},
        "reimported": {"en": "reimported", "fr": "réimporté"},
        "confidence": {"en": "{n}% confidence", "fr": "confiance {n} %"},
        "probable_duplicate": {
            "en": "probable duplicate of “{title}”",
            "fr": "doublon probable de « {title} »",
        },
        "unreadable": {"en": "unreadable text", "fr": "texte illisible"},
        "missing": {"en": "missing {ingest_missing}", "fr": "manque {ingest_missing}"},
        "unknown_category": {"en": "unknown category", "fr": "catégorie inconnue"},
        "doubtful": {"en": "to check: {ingest_doubts}", "fr": "à vérifier : {ingest_doubts}"},
        "doubt_unverified": {
            "en": "{field} not found in the text",
            "fr": "{field} introuvable dans le texte",
        },
        "doubt_ocr_mismatch": {
            "en": "image and OCR differ ({field})",
            "fr": "image et OCR divergent ({field})",
        },
        "doubt_date_swapped": {
            "en": "day and month swapped ({field})",
            "fr": "jour et mois inversés ({field})",
        },
        "doubt_invalid": {
            "en": "invalid check digits ({field})",
            "fr": "clé de contrôle invalide ({field})",
        },
        "doubt_inconsistent_amounts": {
            "en": "before tax + VAT ≠ total",
            "fr": "HT + TVA ≠ TTC",
        },
        "doubt_implausible_dates": {
            "en": "implausible date ({field})",
            "fr": "date improbable ({field})",
        },
        "doubt_disagreement": {
            "en": "two different readings ({field})",
            "fr": "deux lectures divergentes ({field})",
        },
        "doubt_truncated": {
            "en": "long document, read in part only",
            "fr": "document long, lu en partie seulement",
        },
        "doubt_several_documents": {
            "en": "several documents in one file?",
            "fr": "plusieurs documents dans un même fichier ?",
        },
        "doubt_transcribed": {
            "en": "text read by the AI only, unchecked",
            "fr": "texte lu par l'IA seule, non vérifié",
        },
        "to_review": {
            "en": "“{title}” set aside for review ({why})",
            "fr": "« {title} » mis de côté pour vérification ({why})",
        },
        "classified": {
            "en": "“{title}” filed under {category:category} ({confidence})",
            "fr": "« {title} » classé dans {category:category} ({confidence})",
        },
        "waiting": {
            "en": "“{title}” is waiting for the local AI: Binder will read it as soon as it is "
            "ready",
            "fr": "« {title} » attend l'IA locale : Binder le lira dès qu'elle sera prête",
        },
        "analysis_failed": {
            "en": "“{title}”: analysis failed, check it manually",
            "fr": "« {title} » : analyse impossible, à vérifier à la main",
        },
        "trashed": {"en": "“{title}” moved to the trash", "fr": "« {title} » mis à la corbeille"},
        "trashed_because": {
            "en": "“{title}” moved to the trash ({reason})",
            "fr": "« {title} » mis à la corbeille ({reason})",
        },
        "restored": {"en": "“{title}” restored", "fr": "« {title} » restauré"},
        "restored_because": {
            "en": "“{title}” restored ({reason})",
            "fr": "« {title} » restauré ({reason})",
        },
        "purged": {
            "en": "“{title}” permanently deleted",
            "fr": "« {title} » supprimé définitivement",
        },
        "demo_cleared_one": {
            "en": "Demo data cleared ({n} document)",
            "fr": "Données de démonstration effacées ({n} document)",
        },
        "demo_cleared_other": {
            "en": "Demo data cleared ({n} documents)",
            "fr": "Données de démonstration effacées ({n} documents)",
        },
        "separator": {"en": ", ", "fr": ", "},
    },
)
DEMO_BATCH = "demo-"
# Every file name the demo has used, older versions included.
DEMO_FILENAMES = (
    "attestation-caf.pdf", "attestation-garde.pdf", "avis-contravention.pdf",
    "avis-imposition.pdf", "bulletin-paie.pdf", "carte-identite.pdf", "certificat-scolarite.pdf",
    "controle-technique.pdf", "decompte-ameli.pdf", "facture-edf.pdf", "facture-edf-juillet.pdf",
    "facture-orange.pdf", "maif-echeance.pdf", "note-garage.pdf", "quittance-loyer.pdf",
    "recu-don.pdf", "regularisation-charges.pdf", "releve-bancaire.pdf", "taxe-fonciere.pdf",
    "trop-percu-caf.pdf",
)  # fmt: skip


def _render_missing(fields: list[str], language: i18n.Language) -> str:
    """Missing fields in a sentence: "due date, amount" / "l'échéance, le montant"."""
    return T.get("separator", language).join(i18n.field_label(f, language) for f in fields)


i18n.register_param_renderer("ingest_missing", _render_missing)


def render_doubt(doubt: str, language: i18n.Language | None = None) -> str:
    """A doubt of the checks in words: "unverified:due_date" → "due date not found…"."""
    code, _, field = doubt.partition(":")
    key = f"doubt_{code}"
    if key not in T.keys:
        return doubt
    return T.get(key, language).format(field=i18n.field_label(field, language) if field else "")


def _render_doubts(doubts: list[str], language: i18n.Language) -> str:
    return T.get("separator", language).join(render_doubt(d, language) for d in doubts)


i18n.register_param_renderer("ingest_doubts", _render_doubts)

REVIEW_THRESHOLD = 0.6
# Pages of a scan shown to the model: administrative documents say what matters up front, and
# the last page of a longer one is added (totals, signature).
VISION_PAGES = 3


class UnsupportedFile(ValueError):
    pass


def guess_mime(filename: str, declared: str | None) -> str:
    mime = declared if declared in SUPPORTED_MIME else mimetypes.guess_type(filename)[0]
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in SUPPORTED_MIME:
        raise UnsupportedFile(T("unsupported", filename=filename))
    return mime


def store(
    session: Session,
    data: bytes,
    filename: str,
    mime: str,
    *,
    actor: str = "user",
    origin: str | i18n.Msg = "",
    batch: str | None = None,
) -> tuple[Document, bool]:
    """Saves the encrypted file. Returns (document, created); a duplicate returns the existing
    one (and takes it out of the trash if it was there).

    `origin` completes the log entry ("from the watched folder…"): preferably a Msg, so that
    it follows the language.
    """
    digest = hashlib.sha256(data).hexdigest()
    existing = session.exec(select(Document).where(Document.sha256 == digest)).first()
    if existing:
        if existing.deleted_at is not None:
            restore(session, existing, actor=actor, reason=T.msg("reimported"))
            session.commit()
        else:
            known = existing.title or existing.filename
            activity.log(
                session,
                "duplicate",
                T.msg("duplicate", filename=filename, known=known),
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
        filename=filename,
        mime_type=mime,
        size=len(data),
        sha256=digest,
        stored_name=stored_name,
        batch=batch,
    )
    session.add(doc)
    session.flush()
    if not origin and actor == "demo":
        origin = T.msg("demo_origin")
    msg = (
        T.msg("imported_from", filename=filename, origin=origin)
        if origin
        else T.msg("imported", filename=filename)
    )
    activity.log(session, "import", msg, actor=actor, document=doc, details={"size": len(data)})
    session.commit()
    session.refresh(doc)
    return doc, True


def new_batch(source: str) -> str:
    """Identifier of an import batch: its source and when it started."""
    return f"{source}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"


def load_file(doc: Document) -> bytes:
    return security.decrypt((get_settings().files_dir / doc.stored_name).read_bytes())


def delete_file(doc: Document) -> None:
    (get_settings().files_dir / doc.stored_name).unlink(missing_ok=True)


def merge(
    by_rules: Extraction, by_llm: Extraction | None, reading: list[str] | None = None
) -> Extraction:
    """Combines both extractions (each already checked against the text): the model wins, the
    rules fill its gaps, and any amount or date they read differently is a doubt. The
    confidence comes from the checks only. `reading`: doubts about the reading itself (text
    cut, several documents in the file)."""
    if by_llm is None:
        merged = by_rules.model_copy()
    else:
        merged = by_llm.model_copy()
        merged.doubts = [*by_llm.doubts, *verify.disagreements(by_rules, by_llm)]
        if merged.amount is None:
            merged.amount = by_rules.amount
        for field in ("issuer", "issue_date", "due_date", "expiry_date", "reference", "person"):
            if getattr(merged, field) in (None, ""):
                setattr(merged, field, getattr(by_rules, field))
        if merged.category == Category.OTHER and by_rules.category != Category.OTHER:
            merged.category = by_rules.category
        merged.title = merged.title or by_rules.title
        merged.doc_type = by_llm.doc_type or by_rules.doc_type
        merged.extractor = "llm+rules"
    if merged.due_date is not None and merged.due_date == merged.expiry_date:
        # "Next inspection before…": an end of validity, not a payment (as in the rules).
        merged.due_date = None
    merged.doubts = list(
        dict.fromkeys([*(reading or []), *merged.doubts, *verify.consistency(merged)])
    )
    merged.missing_fields = rules.missing_for(merged.category, merged.model_dump())
    checked = verify.confidence(
        merged.doubts, merged.missing_fields, known_category=merged.category != Category.OTHER
    )
    # Without the model (demo), the keyword score of the rules is one more check.
    merged.confidence = checked if by_llm is not None else min(checked, by_rules.confidence)
    return merged


def apply_extraction(doc: Document, ext: Extraction) -> None:
    doc.title = ext.title or doc.filename
    doc.category = ext.category
    doc.issuer = ext.issuer
    doc.amount = ext.amount
    doc.amount_ht = ext.amount_ht
    doc.amount_tva = ext.amount_tva
    doc.amount_ttc = ext.amount_ttc
    doc.amount_due = ext.amount_due
    doc.issue_date = ext.issue_date
    doc.due_date = ext.due_date
    doc.expiry_date = ext.expiry_date
    doc.period_start = ext.period_start
    doc.period_end = ext.period_end
    doc.reference = ext.reference
    doc.iban = ext.iban
    doc.siret = ext.siret
    doc.doubts = json.dumps(ext.doubts)
    doc.doc_type = ext.doc_type
    doc.person = household.display(ext.person) if ext.person else None
    doc.confidence = ext.confidence
    doc.extractor = ext.extractor
    doc.explanation = None
    refresh_status(doc)


def refresh_status(doc: Document, validated: bool = False) -> None:
    if validated and doc.duplicate_of is not None:
        # Validating a flagged duplicate means deciding to keep both.
        doc.duplicate_of = None
        doc.duplicate_dismissed = True
    if validated:
        # The user checked the document: the doubts of the reading are settled.
        doc.doubts = "[]"
    missing = rules.missing_for(doc.category, doc.model_dump())
    doubts = json.loads(doc.doubts or "[]")
    if doc.duplicate_of is not None:
        missing.append("duplicate")
    doc.missing_fields = json.dumps([*missing, *doubts])
    doc.area = areas.area_of(doc)
    if validated:
        doc.status = DocumentStatus.CLASSIFIED
    elif missing or doubts or doc.confidence < REVIEW_THRESHOLD or doc.category == Category.OTHER:
        doc.status = DocumentStatus.TO_REVIEW
    else:
        doc.status = DocumentStatus.CLASSIFIED
    doc.updated_at = datetime.now(UTC)


def sync_deadline(session: Session, doc: Document) -> None:
    deadlines.sync(session, doc)


def is_demo(doc: Document) -> bool:
    return (doc.batch or "").startswith(DEMO_BATCH)


def waits_for_ai(doc: Document) -> bool:
    """Real documents are read by the local model only.

    The rules are tuned on the demo documents: on a real one they would file it badly and the
    user would have to correct what the model gets right. So while the model is being set up
    (or cannot run), real documents wait; demos keep running on modest machines. With the
    model switched off in the configuration (tests, BINDER_LLM_ENABLED=false), the rules read
    everything."""
    return get_settings().llm_enabled and not is_demo(doc) and not llm.is_available()


def _wait(session: Session, doc: Document) -> Document:
    if doc.status != DocumentStatus.WAITING:
        doc.status = DocumentStatus.WAITING
        doc.title = doc.title or doc.filename
        session.add(doc)
        activity.log(session, "analyze", T.msg("waiting", title=doc.title), document=doc)
    session.commit()
    session.refresh(doc)
    return doc


def analyze_waiting(session: Session, limit: int = 3) -> int:
    """Reads the documents that waited for the local AI, once it is ready. Returns how many;
    a few per call, so that the background loop keeps its pace."""
    if not llm.is_available():
        return 0
    ids = session.exec(
        select(Document.id)
        .where(Document.status == DocumentStatus.WAITING, col(Document.deleted_at).is_(None))
        .order_by(col(Document.id))
        .limit(limit)
    ).all()
    for doc_id in ids:
        if doc_id is not None:
            analyze_in_background(doc_id)
    return len(ids)


def extract(data: bytes, mime_type: str, *, use_llm: bool = True) -> tuple[ReadResult, Extraction]:
    """Reading and extraction of a file, before anything about the library is applied (past
    corrections, duplicates): what the evaluation measures (scripts/evaluate.py)."""
    model = use_llm and llm.is_available()
    read = read_document(data, mime_type)
    images = _scan_pages(data, mime_type, read) if model else []
    transcribed = bool(images) and not read.text.strip()
    if transcribed:
        read.text = llm.transcribe(images)
    by_rules = rules.extract(read.text)
    by_rules.doubts = verify.check(by_rules, read.text)
    by_llm = llm.extract(read.text, images) if read.text.strip() and model else None
    if by_llm is not None:
        # On a scan the model saw the pages: what it read is checked against the OCR text.
        by_llm.doubts = verify.check(by_llm, read.text, scanned=bool(images))
        if transcribed:
            # The only text is the model's own reading: nothing independent to check against.
            by_llm.doubts.append(verify.TRANSCRIBED)
    reading = []
    if by_llm is not None and llm.truncated(read.text):
        reading.append(verify.TRUNCATED)
    if several_documents(read.pages):
        reading.append(verify.SEVERAL_DOCUMENTS)
    ext = merge(by_rules, by_llm, reading)
    ext.person = ext.person or household.detect(read.text)
    return read, ext


def analyze(session: Session, doc: Document) -> Document:
    if waits_for_ai(doc):
        return _wait(session, doc)
    previous_key = organize.series_key(doc)
    doc.duplicate_of = None
    read, ext = extract(load_file(doc), doc.mime_type)
    doc.text = read.text
    doc.page_count = read.page_count
    learned = learning.apply(session, read.text, ext)
    if not read.text.strip():
        ext.confidence = 0.0
        if ext.title == rules.T("untitled"):
            ext.title = doc.filename.rsplit(".", 1)[0]
    apply_extraction(doc, ext)
    session.add(doc)
    session.flush()
    organize.detect_duplicate(session, doc)
    refresh_status(doc)
    _log_analysis(session, doc)
    learning.log_applied(session, doc, learned)
    sync_deadline(session, doc)
    index_document(session, doc)
    embeddings.index(session, doc)
    organize.reorganize(session, doc, previous_key)
    profile.learn(session)
    session.flush()
    subscriptions.check_increase(session, doc)
    anomalies.check_new(session, doc)
    session.commit()
    session.refresh(doc)
    return doc


def _scan_pages(data: bytes, mime_type: str, read: ReadResult) -> list[bytes]:
    """Pages to show to the model: those of a scan or photo, when it has vision.

    OCR loses the layout (which amount is the total, a stamp, a ticked box) or fails on a
    skewed photo; the model reads the image itself. PDFs with text do not need it."""
    if not (read.ocr_used or not read.text.strip()) or not llm.has_vision():
        return []
    return [page_image(data, mime_type, n) for n in vision_pages(read.page_count)]


def vision_pages(page_count: int) -> list[int]:
    """Indexes of the pages shown to the model: the first ones, and the last of a long scan."""
    pages = list(range(min(page_count, VISION_PAGES)))
    if page_count > VISION_PAGES:
        pages.append(page_count - 1)
    return pages


def _log_analysis(session: Session, doc: Document) -> None:
    confidence = T.msg("confidence", n=round(doc.confidence * 100))
    msg: i18n.Msg
    if doc.status == DocumentStatus.TO_REVIEW:
        missing = json.loads(doc.missing_fields)
        doubts = json.loads(doc.doubts or "[]")
        reasons = [f for f in missing if f not in ("text", "duplicate", *doubts)]
        original = session.get(Document, doc.duplicate_of) if doc.duplicate_of else None
        why: i18n.Msg
        if original is not None:
            why = T.msg("probable_duplicate", title=original.title)
        elif "text" in missing or not doc.text.strip():
            why = T.msg("unreadable")
        elif doubts:
            why = T.msg("doubtful", ingest_doubts=doubts)
        elif reasons:
            why = T.msg("missing", ingest_missing=reasons)
        elif doc.category == Category.OTHER:
            why = T.msg("unknown_category")
        else:
            why = confidence
        msg = T.msg("to_review", title=doc.title, why=why)
    else:
        msg = T.msg("classified", title=doc.title, category=doc.category, confidence=confidence)
    activity.log(
        session,
        "analyze",
        msg,
        document=doc,
        details={
            "category": doc.category.value,
            "confidence": doc.confidence,
            "extractor": doc.extractor,
            "amount": doc.amount,
            "doubts": json.loads(doc.doubts or "[]"),
            "due_date": doc.due_date,
            "reference": doc.reference,
            "duplicate_of": doc.duplicate_of,
        },
    )


def _with_reason(key: str, title: str, reason: str | i18n.Msg) -> i18n.Msg:
    if reason:
        return T.msg(f"{key}_because", title=title, reason=reason)
    return T.msg(key, title=title)


def trash(
    session: Session, doc: Document, *, actor: str = "user", reason: str | i18n.Msg = ""
) -> None:
    """Moves the document to the trash: hidden everywhere, restorable, file kept.

    `reason`: preferably a Msg (e.g. retention.deletion_msg(doc, inline=True)).
    """
    previous_key = organize.series_key(doc)
    undo.push("trash", id=doc.id)
    doc.deleted_at = datetime.now(UTC)
    deadlines.sync(session, doc)
    if doc.id is not None:
        unindex_document(session, doc.id)
    session.add(doc)
    for freed in organize.release_duplicates(session, doc):
        refresh_status(freed)
        sync_deadline(session, freed)
    organize.reorganize(session, doc, previous_key)
    profile.learn(session)
    activity.log(
        session, "trash", _with_reason("trashed", doc.title, reason), actor=actor, document=doc
    )


def restore(
    session: Session, doc: Document, *, actor: str = "user", reason: str | i18n.Msg = ""
) -> None:
    undo.push("restore", id=doc.id)
    doc.deleted_at = None
    session.add(doc)
    session.flush()
    sync_deadline(session, doc)
    index_document(session, doc)
    organize.reorganize(session, doc, None)
    activity.log(
        session, "restore", _with_reason("restored", doc.title, reason), actor=actor, document=doc
    )


def purge(session: Session, doc: Document, *, actor: str = "user") -> None:
    """Permanent deletion (file included). Only for documents already in the trash."""
    if doc.deleted_at is None:
        raise ValueError("Only a document in the trash can be permanently deleted")
    for dl in session.exec(select(Deadline).where(Deadline.document_id == doc.id)):
        session.delete(dl)
    activity.log(session, "purge", T.msg("purged", title=doc.title), actor=actor, document=doc)
    if doc.id is not None:
        embeddings.forget(session, doc.id)
    delete_file(doc)
    session.delete(doc)


def wait_for_analysis(session: Session, doc: Document, timeout: float = 90) -> Document:
    """Waits for the background analysis of a document that has just been uploaded."""
    deadline = time.monotonic() + timeout
    while doc.status == DocumentStatus.PROCESSING and time.monotonic() < deadline:
        time.sleep(0.5)
        session.refresh(doc)
    return doc


def analyze_in_background(doc_id: int) -> None:
    with Session(get_engine()) as session:
        doc = session.get(Document, doc_id)
        if doc is None:
            return
        try:
            analyze(session, doc)
        except Exception:
            log.exception("Could not analyse document %s", doc_id)
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
                    T.msg("analysis_failed", title=doc.title),
                    document=doc,
                )
                session.commit()


def seed_demo(session: Session) -> list[tuple[Document, bool]]:
    """Imports the fictitious demo documents (dates relative to today)."""
    from binder.samples import build_samples

    results = []
    batch = new_batch(DEMO_BATCH.rstrip("-"))
    for sample in build_samples():
        doc, created = store(
            session, sample.pdf(), sample.filename, "application/pdf", actor="demo", batch=batch
        )
        if created:
            analyze(session, doc)
        results.append((doc, created))
    return results


def demo_documents(session: Session) -> list[Document]:
    """Documents imported by `seed_demo`, trashed ones included.

    Older versions did not mark them with a batch: those are recognised by their file.
    """
    docs = list(session.exec(select(Document).where(col(Document.batch).startswith(DEMO_BATCH))))
    for doc in session.exec(select(Document).where(col(Document.filename).in_(DEMO_FILENAMES))):
        if not is_demo(doc) and _is_demo_file(get_settings().files_dir / doc.stored_name):
            docs.append(doc)
    return docs


def demo_leftover_files(session: Session) -> list[Path]:
    """Demo files no document points to any more (left behind by older versions)."""
    files_dir = get_settings().files_dir
    if not files_dir.is_dir():
        return []
    known = set(session.exec(select(Document.stored_name)))
    return [
        path
        for path in files_dir.iterdir()
        if path.is_file() and path.name not in known and _is_demo_file(path)
    ]


def _is_demo_file(path: Path) -> bool:
    try:
        return is_bare_a4_pdf(security.decrypt(path.read_bytes()))
    except Exception:
        return False


def clear_demo(session: Session) -> tuple[int, list[Path]]:
    """Permanently removes the demo documents and what came from them (reminders, letters).

    Returns how many documents went and the files to delete once committed (theirs and the
    demo files older versions left behind), so a failed transaction never loses a file. The
    user asks for it explicitly; one entry in the history sums it up.
    """
    docs = demo_documents(session)
    files = demo_leftover_files(session)
    ids = {doc.id for doc in docs if doc.id is not None}
    if not ids:
        return 0, files
    for deadline in session.exec(select(Deadline).where(col(Deadline.document_id).in_(ids))):
        session.delete(deadline)
    for letter in session.exec(
        select(Correspondence).where(col(Correspondence.document_id).in_(ids))
    ):
        session.delete(letter)
    # Real documents flagged against a demo one are freed.
    for doc in session.exec(
        select(Document).where(
            or_(col(Document.duplicate_of).in_(ids), col(Document.superseded_by).in_(ids))
        )
    ):
        if doc.id in ids:
            continue
        if doc.duplicate_of in ids:
            doc.duplicate_of = None
        if doc.superseded_by in ids:
            doc.superseded_by = None
        refresh_status(doc)
        session.add(doc)
    for doc in docs:
        assert doc.id is not None
        unindex_document(session, doc.id)
        embeddings.forget(session, doc.id)
        files.append(get_settings().files_dir / doc.stored_name)
        session.delete(doc)
    activity.log(session, "purge", T.plural_msg("demo_cleared", len(docs)), actor="user")
    session.flush()
    # The details Binder took from the demo documents go with them.
    profile.learn(session)
    return len(docs), files
