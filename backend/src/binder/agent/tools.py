"""Outils de l'agent. Chaque outil renvoie un résultat sérialisable pour le modèle,
ainsi que les documents et échéances à afficher dans l'interface."""

import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, col, select

from binder.models import Category, Deadline, Document, DocumentStatus
from binder.services import activity, explain
from binder.services.rules import MONTHS, normalize

STOP_WORDS = {
    "trouve",
    "trouver",
    "cherche",
    "chercher",
    "montre",
    "affiche",
    "liste",
    "donne",
    "moi",
    "mes",
    "mon",
    "ma",
    "les",
    "le",
    "la",
    "des",
    "de",
    "du",
    "un",
    "une",
    "tous",
    "toutes",
    "tout",
    "depuis",
    "avant",
    "apres",
    "pour",
    "dans",
    "et",
    "ou",
    "en",
    "sur",
    "avec",
    "quels",
    "quel",
    "quelle",
    "quelles",
    "documents",
    "document",
    "dernier",
    "derniere",
    "derniers",
    "classe",
    "range",
    "arrivent",
    "bientot",
    "je",
    "j",
    "ai",
    "a",
    "est",
    "sont",
    "qui",
    "que",
    "annee",
    "mois",
    "cette",
    "ce",
    "ces",
    "moins",
}


@dataclass
class ToolResult:
    payload: Any
    documents: list[Document] = field(default_factory=list)
    deadlines: list[Deadline] = field(default_factory=list)


def _doc_summary(d: Document) -> dict[str, Any]:
    return {
        "id": d.id,
        "titre": d.title,
        "categorie": d.category.value,
        "emetteur": d.issuer,
        "montant": d.amount,
        "date_emission": d.issue_date and d.issue_date.isoformat(),
        "echeance": d.due_date and d.due_date.isoformat(),
        "reference": d.reference,
    }


def _deadline_summary(d: Deadline) -> dict[str, Any]:
    return {
        "id": d.id,
        "titre": d.title,
        "categorie": d.category.value,
        "date": d.due_date.isoformat(),
        "montant": d.amount,
        "document_id": d.document_id,
    }


def _stem(term: str) -> str:
    return term[:-1] if len(term) > 3 and term[-1] in "sx" else term


def keywords(query: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", normalize(query))
    return [_stem(w) for w in words if w not in STOP_WORDS and w not in MONTHS and len(w) > 1]


def _fts(session: Session, terms: list[str], operator: str, limit: int) -> list[int]:
    match = f" {operator} ".join(f'"{t}"*' for t in terms)
    rows = session.execute(
        text(
            "SELECT rowid FROM document_fts WHERE document_fts MATCH :q "
            "ORDER BY bm25(document_fts, 10.0, 5.0, 5.0, 3.0, 1.0) LIMIT :limit"
        ),
        {"q": match, "limit": limit},
    )
    return [int(r[0]) for r in rows]


def search_documents(
    session: Session,
    query: str = "",
    category: str | None = None,
    since: str | None = None,
    limit: int = 20,
) -> ToolResult:
    """Recherche plein texte (tous les mots, sinon au moins un), filtrable par catégorie et date."""
    terms = keywords(query)
    stmt = select(Document).where(col(Document.deleted_at).is_(None))
    if terms:
        ids = _fts(session, terms, "AND", 200) or _fts(session, terms, "OR", 200)
        if not ids:
            return ToolResult(payload={"resultats": [], "total": 0})
        stmt = stmt.where(col(Document.id).in_(ids))
    if category:
        cat = next((c for c in Category if normalize(c.value) == normalize(category)), None)
        if cat:
            stmt = stmt.where(Document.category == cat)
    if since:
        with suppress(ValueError):
            stmt = stmt.where(col(Document.issue_date) >= date.fromisoformat(since))
    docs = list(
        session.exec(stmt.order_by(col(Document.issue_date).desc(), col(Document.id).desc()))
    )
    shown = docs[:limit]
    return ToolResult(
        payload={"resultats": [_doc_summary(d) for d in shown], "total": len(docs)},
        documents=shown,
    )


def read_document(session: Session, document_id: int) -> ToolResult:
    doc = session.get(Document, document_id)
    if doc is None or doc.deleted_at is not None:
        return ToolResult(payload={"erreur": f"Document {document_id} introuvable"})
    return ToolResult(payload={**_doc_summary(doc), "texte": doc.text[:4000]}, documents=[doc])


def list_deadlines(
    session: Session, days: int = 30, start: str | None = None, end: str | None = None
) -> ToolResult:
    today = date.today()
    first = date.fromisoformat(start) if start else today
    last = date.fromisoformat(end) if end else first + timedelta(days=days)
    rows = list(
        session.exec(
            select(Deadline)
            .where(Deadline.due_date >= first, Deadline.due_date <= last, Deadline.done == False)  # noqa: E712
            .order_by(col(Deadline.due_date))
        )
    )
    return ToolResult(
        payload={
            "periode": [first.isoformat(), last.isoformat()],
            "echeances": [_deadline_summary(d) for d in rows],
        },
        deadlines=rows,
    )


def create_reminder(
    session: Session, title: str, due_date: str, amount: float | None = None
) -> ToolResult:
    try:
        when = date.fromisoformat(due_date)
    except ValueError:
        return ToolResult(payload={"erreur": "Date invalide, format attendu AAAA-MM-JJ"})
    reminder = Deadline(title=title, due_date=when, amount=amount, source="manual")
    session.add(reminder)
    activity.log(
        session,
        "reminder",
        f"Rappel « {title} » créé pour le {activity.display(when)} à votre demande",
        actor="agent",
    )
    # Pas de commit ici : il expirerait les documents déjà trouvés dans ce tour.
    session.flush()
    return ToolResult(payload={"cree": _deadline_summary(reminder)}, deadlines=[reminder])


def documents_to_review(session: Session) -> ToolResult:
    docs = list(
        session.exec(
            select(Document)
            .where(Document.status == DocumentStatus.TO_REVIEW)
            .where(col(Document.deleted_at).is_(None))
            .order_by(col(Document.created_at).desc())
        )
    )
    return ToolResult(
        payload={"a_verifier": [{**_doc_summary(d), "manquant": d.missing_fields} for d in docs]},
        documents=docs,
    )


def explain_document(session: Session, document_id: int) -> ToolResult:
    doc = session.get(Document, document_id)
    if doc is None or doc.deleted_at is not None:
        return ToolResult(payload={"erreur": f"Document {document_id} introuvable"})
    if doc.explanation:
        result = explain.Explanation.model_validate_json(doc.explanation)
    else:
        result = explain.explain(doc)
        doc.explanation = result.model_dump_json()
        session.add(doc)
        session.flush()
    return ToolResult(payload={"id": doc.id, **result.model_dump(mode="json")}, documents=[doc])


def export_folder(session: Session, category: str | None = None) -> ToolResult:
    result = search_documents(session, category=category, limit=500)
    suffix = f"?category={category}" if category else ""
    return ToolResult(
        payload={"lien": f"/api/export{suffix}", "nombre": result.payload["total"]},
        documents=result.documents[:10],
    )


TOOLS: dict[str, Any] = {
    "search_documents": search_documents,
    "read_document": read_document,
    "list_deadlines": list_deadlines,
    "create_reminder": create_reminder,
    "documents_to_review": documents_to_review,
    "explain_document": explain_document,
    "export_folder": export_folder,
}

_CATEGORIES = [c.value for c in Category]

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Recherche des documents par mots-clés, catégorie et date d'émission.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Mots-clés (ex. « facture EDF »)"},
                    "category": {"type": "string", "enum": _CATEGORIES},
                    "since": {"type": "string", "description": "Date minimale AAAA-MM-JJ"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": "Lit le contenu et les informations d'un document.",
            "parameters": {
                "type": "object",
                "properties": {"document_id": {"type": "integer"}},
                "required": ["document_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_deadlines",
            "description": "Liste les échéances non réglées sur une période.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Nombre de jours à partir d'aujourd'hui",
                    },
                    "start": {"type": "string", "description": "Début AAAA-MM-JJ"},
                    "end": {"type": "string", "description": "Fin AAAA-MM-JJ"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Crée un rappel à une date donnée.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due_date": {"type": "string", "description": "AAAA-MM-JJ"},
                    "amount": {"type": "number"},
                },
                "required": ["title", "due_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "documents_to_review",
            "description": "Liste les documents incomplets ou à vérifier.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_document",
            "description": "Explique un courrier en langage simple et dit s'il demande une action.",
            "parameters": {
                "type": "object",
                "properties": {"document_id": {"type": "integer"}},
                "required": ["document_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_folder",
            "description": "Prépare un export ZIP des documents, éventuellement d'une catégorie.",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string", "enum": _CATEGORIES}},
            },
        },
    },
]
