"""Boucle d'agent maison.

Avec Ollama : le modèle choisit les outils (tool calling) jusqu'à produire une réponse.
Sans modèle : un routeur par intentions appelle directement le bon outil, pour que
l'application reste utilisable hors ligne.
"""

import json
import logging
import re
from datetime import date
from typing import Any

import httpx
from sqlmodel import Session

from binder.agent import tools
from binder.models import Category, Deadline, Document
from binder.schemas import ChatMessage, ChatResponse, DeadlineOut, DocumentOut, ToolCallTrace
from binder.services import llm
from binder.services.rules import MONTHS, find_dates, normalize

log = logging.getLogger(__name__)

MAX_STEPS = 5

SYSTEM_PROMPT = """Tu es l'agent de Binder, un coffre-fort administratif 100 % local.
Tu aides l'utilisateur à retrouver ses documents, suivre ses échéances et créer des rappels.
Nous sommes le {today}. Utilise toujours les outils pour obtenir des faits ; n'invente jamais
un document, un montant ou une date. Réponds en français, en une à trois phrases, sans répéter
la liste détaillée : l'interface affiche déjà les documents et échéances trouvés."""


class _Collector:
    def __init__(self) -> None:
        self.documents: dict[int, Document] = {}
        self.deadlines: dict[int, Deadline] = {}
        self.calls: list[ToolCallTrace] = []

    def run(self, session: Session, name: str, arguments: dict[str, Any]) -> tools.ToolResult:
        self.calls.append(ToolCallTrace(name=name, arguments=arguments))
        fn = tools.TOOLS.get(name)
        if fn is None:
            return tools.ToolResult(payload={"erreur": f"Outil inconnu : {name}"})
        try:
            result: tools.ToolResult = fn(session, **arguments)
        except TypeError as exc:
            return tools.ToolResult(payload={"erreur": f"Arguments invalides : {exc}"})
        for d in result.documents:
            if d.id is not None:
                self.documents[d.id] = d
        for dl in result.deadlines:
            if dl.id is not None:
                self.deadlines[dl.id] = dl
        return result

    def response(self, answer: str, engine: str) -> ChatResponse:
        today = date.today()
        return ChatResponse(
            answer=answer,
            documents=[DocumentOut.from_model(d) for d in self.documents.values()],
            deadlines=[DeadlineOut.from_model(d, today) for d in self.deadlines.values()],
            tool_calls=self.calls,
            engine=engine,
        )


def run(session: Session, message: str, history: list[ChatMessage]) -> ChatResponse:
    if llm.is_available():
        try:
            return _run_llm(session, message, history)
        except (httpx.HTTPError, KeyError, ValueError):
            log.exception("Agent LLM indisponible, repli sur le routeur")
    return _run_rules(session, message)


def _run_llm(session: Session, message: str, history: list[ChatMessage]) -> ChatResponse:
    collector = _Collector()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(today=date.today().isoformat())},
        *({"role": m.role, "content": m.content} for m in history[-6:]),
        {"role": "user", "content": message},
    ]
    for _ in range(MAX_STEPS):
        reply = llm.chat(messages, tools=tools.TOOL_SCHEMAS)
        calls = reply.get("tool_calls") or []
        messages.append(reply)
        if not calls:
            return collector.response(reply.get("content", "").strip(), "llm")
        for call in calls:
            fn = call["function"]
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            result = collector.run(session, fn["name"], args)
            messages.append(
                {"role": "tool", "content": json.dumps(result.payload, ensure_ascii=False)}
            )
    return collector.response("Je n'ai pas pu terminer cette demande.", "llm")


# --- Routeur sans modèle -----------------------------------------------------------------


def _month_range(norm: str, today: date) -> tuple[date, date] | None:
    for name, month in MONTHS.items():
        if re.search(rf"\b{name}\b", norm):
            year = today.year
            start = date(year, month, 1)
            end = date(year + (month == 12), month % 12 + 1, 1)
            return start, date.fromordinal(end.toordinal() - 1)
    return None


def _since(norm: str, today: date) -> date | None:
    m = re.search(r"depuis (?:le mois de |d')?(" + "|".join(MONTHS) + r")", norm)
    if not m:
        return None
    month = MONTHS[m[1]]
    year = today.year if month <= today.month else today.year - 1
    return date(year, month, 1)


def _category_in(norm: str) -> Category | None:
    for c in Category:
        if c != Category.AUTRE and re.search(rf"\b{normalize(c.value)}\b", norm):
            return c
    return None


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"


def _run_rules(session: Session, message: str) -> ChatResponse:
    collector = _Collector()
    norm = normalize(message)
    today = date.today()

    if re.search(r"rappel|rappelle|previens", norm):
        dates = find_dates(norm)
        if not dates:
            return collector.response(
                "Pour créer un rappel, indiquez une date (ex. « rappelle-moi de payer la cantine "
                "le 12/11/2026 »).",
                "rules",
            )
        title = re.sub(r"(?i)rappelle[- ]moi( de)?|cr[ée]e un rappel( pour)?|le \d.*$", "", message)
        title = title.strip(" :,.") or "Rappel"
        collector.run(
            session,
            "create_reminder",
            {"title": title[:1].upper() + title[1:], "due_date": dates[0].isoformat()},
        )
        return collector.response(
            f"C'est noté : rappel « {title} » le {dates[0].strftime('%d/%m/%Y')}.", "rules"
        )

    if re.search(r"echeance|a payer|arrive|bientot|expire|date limite", norm):
        month = _month_range(norm, today)
        period_args: dict[str, Any] = (
            {"start": month[0].isoformat(), "end": month[1].isoformat()} if month else {"days": 30}
        )
        result = collector.run(session, "list_deadlines", period_args)
        n = len(result.deadlines)
        period = "sur cette période" if month else "dans les 30 prochains jours"
        if not n:
            return collector.response(f"Aucune échéance {period}.", "rules")
        total = sum(d.amount or 0 for d in result.deadlines)
        amount = f", pour un total de {total:,.2f} €".replace(",", " ").replace(".", ",")
        return collector.response(
            f"Vous avez {_plural(n, 'échéance')} {period}{amount if total else ''}.", "rules"
        )

    if re.search(r"verifier|manquant|incomplet|a completer", norm):
        result = collector.run(session, "documents_to_review", {})
        n = len(result.documents)
        return collector.response(
            f"{_plural(n, 'document')} à vérifier." if n else "Rien à vérifier, tout est en ordre.",
            "rules",
        )

    if re.search(r"export", norm):
        category = _category_in(norm)
        result = collector.run(
            session, "export_folder", {"category": category.value} if category else {}
        )
        return collector.response(
            f"Export prêt ({_plural(result.payload['nombre'], 'document')}) : "
            f"[télécharger le dossier]({result.payload['lien']}).",
            "rules",
        )

    since = _since(norm, today)
    category = _category_in(norm)
    args: dict[str, Any] = {"query": message}
    if since:
        args["since"] = since.isoformat()
    if category and not tools.keywords(message.replace(category.value, "")):
        args = {"category": category.value, **({"since": args["since"]} if since else {})}
    latest = bool(re.search(r"\bdernier|\bderniere|\bplus recent", norm))
    if latest:
        args["limit"] = 1
    result = collector.run(session, "search_documents", args)
    total = result.payload["total"]
    if not total:
        return collector.response("Je n'ai trouvé aucun document correspondant.", "rules")
    if latest:
        doc = result.documents[0]
        return collector.response(f"Voici votre document le plus récent : {doc.title}.", "rules")
    suffix = " Voici la liste." if total > 1 else ""
    return collector.response(f"J'ai trouvé {_plural(total, 'document')}.{suffix}", "rules")
