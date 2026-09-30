"""Rangement : nom de fichier normalisé, doublons probables, versions successives.

Rien n'est supprimé ici : un doublon part en vérification, une ancienne version est
simplement marquée comme remplacée. C'est l'utilisateur qui décide ensuite.
"""

import mimetypes
import re
from difflib import SequenceMatcher

from sqlmodel import Session, col, select

from binder.models import Document
from binder.services import activity
from binder.services.rules import normalize

# Documents dont seule la dernière version compte : la nouvelle remplace l'ancienne.
# Les bulletins de paie n'en font pas partie : chacun est à conserver.
VERSIONED_TYPES = {"Attestation", "Attestation d'assurance"}

SIMILARITY_THRESHOLD = 0.92
SIMILARITY_CHARS = 4000

_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def standard_name(doc: Document) -> str:
    """« 2026-09-18 Facture EDF.pdf » : date, émetteur, type. Trié chronologiquement."""
    label = doc.title or doc.filename.rsplit(".", 1)[0]
    if doc.issuer and normalize(doc.issuer) not in normalize(label):
        label = f"{label} {doc.issuer}"
    when = doc.issue_date or doc.due_date or doc.created_at.date()
    ext = mimetypes.guess_extension(doc.mime_type) or ""
    if ext == ".jpe":
        ext = ".jpg"
    name = _FORBIDDEN.sub(" ", f"{when.isoformat()} {label}")
    return re.sub(r"\s+", " ", name).strip()[:120] + ext


def _active(session: Session, doc: Document) -> list[Document]:
    return list(
        session.exec(
            select(Document)
            .where(col(Document.deleted_at).is_(None), Document.id != doc.id)
            .where(Document.category == doc.category)
            .order_by(col(Document.id))
        )
    )


def _compatible(a: object, b: object) -> bool:
    return a is None or b is None or a == b


def _similar(a: str, b: str) -> bool:
    a, b = normalize(a)[:SIMILARITY_CHARS], normalize(b)[:SIMILARITY_CHARS]
    if not a.strip() or not b.strip():
        return False
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    return matcher.real_quick_ratio() >= SIMILARITY_THRESHOLD and (
        matcher.quick_ratio() >= SIMILARITY_THRESHOLD and matcher.ratio() >= SIMILARITY_THRESHOLD
    )


def find_duplicate(session: Session, doc: Document) -> Document | None:
    """Document déjà présent au contenu quasi identique (autre scan, autre téléchargement).

    Deux documents aux dates ou montants différents ne sont jamais des doublons : c'est le cas
    des factures mensuelles d'un même fournisseur, dont le texte se ressemble beaucoup.
    """
    for other in _active(session, doc):
        if other.duplicate_of is not None:
            continue
        if not (
            _compatible(doc.issue_date, other.issue_date)
            and _compatible(doc.amount, other.amount)
            and _compatible(doc.due_date, other.due_date)
        ):
            continue
        same_keys = (
            doc.reference is not None
            and doc.reference == other.reference
            and doc.issue_date is not None
            and doc.issue_date == other.issue_date
            and doc.amount == other.amount
        )
        if same_keys or _similar(doc.text, other.text):
            return other
    return None


def detect_duplicate(session: Session, doc: Document) -> None:
    if doc.duplicate_dismissed:
        doc.duplicate_of = None
        return
    original = find_duplicate(session, doc)
    doc.duplicate_of = original.id if original else None
    if original:
        activity.log(
            session,
            "duplicate",
            f"« {doc.title} » ressemble à « {original.title} » déjà présent : doublon probable",
            document=doc,
            details={"original": original.id},
        )


def release_duplicates(session: Session, original: Document) -> list[Document]:
    """L'original part à la corbeille : ses doublons ne sont plus des doublons."""
    freed = list(session.exec(select(Document).where(Document.duplicate_of == original.id)))
    for doc in freed:
        doc.duplicate_of = None
        session.add(doc)
    return freed


def series_key(doc: Document) -> tuple[str, str] | None:
    """Série de versions : même type (versionné) et même émetteur. Hors série : None."""
    if doc.doc_type not in VERSIONED_TYPES or doc.duplicate_of is not None:
        return None
    if doc.deleted_at is not None:
        return None
    return doc.doc_type, normalize(doc.issuer or "")


def update_series(session: Session, *keys: tuple[str, str] | None) -> None:
    """Marque, dans chaque série, les versions remplacées par la plus récente."""
    for key in {k for k in keys if k is not None}:
        candidates = session.exec(
            select(Document).where(
                col(Document.deleted_at).is_(None),
                Document.doc_type == key[0],
                col(Document.duplicate_of).is_(None),
            )
        )
        series = [d for d in candidates if series_key(d) == key]
        if not series:
            continue
        latest = max(series, key=lambda d: (d.issue_date or d.created_at.date(), d.id or 0))
        for d in series:
            target = None if d is latest else latest.id
            if d.superseded_by == target:
                continue
            d.superseded_by = target
            session.add(d)
            if target is not None:
                activity.log(
                    session,
                    "supersede",
                    f"« {d.title} » remplacé par une version plus récente "
                    f"(du {activity.display(latest.issue_date)})",
                    document=d,
                    details={"remplace_par": latest.id},
                )


def reorganize(session: Session, doc: Document, previous_key: tuple[str, str] | None) -> None:
    """Après un changement (analyse, correction, corbeille) : séries d'avant et d'après."""
    key = series_key(doc)
    if key is None and doc.superseded_by is not None:
        doc.superseded_by = None
        session.add(doc)
    session.flush()
    update_series(session, previous_key, key)
