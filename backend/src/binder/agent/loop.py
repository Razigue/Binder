"""Home-made agent loop.

With Ollama: the model picks tools (tool calling) until it produces an answer. Each step can be
followed live (`emit`): tool calls as they start, then the answer as it is written.
Without a model (demos, tests): a fallback intent router calls the right tool directly.
Both answer in the user's language; the router understands French and English.
"""

import json
import logging
import re
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx
from sqlmodel import Session, col, select

from binder import i18n
from binder.agent import tools
from binder.config import get_settings
from binder.db import WITHOUT_TEXT
from binder.models import Category, Deadline, Document
from binder.schemas import ChatMessage, ChatResponse, DeadlineOut, DocumentOut, ToolCallTrace
from binder.services import letters, llm
from binder.services.rules import find_dates, normalize

log = logging.getLogger(__name__)

# Model turns per request: search, read, act, answer, with room for a correction.
MAX_STEPS = 8

SYSTEM_PROMPT = """You are Binder, a meticulous assistant for the user's household paperwork. \
The app already holds their administrative documents (bills, tax notices, payslips, IDs, \
insurance, scans…) and you work on them with tools.
Today: {today}. User country: {country}, currency {currency}. Library: {overview}.
How to work:
- Get every fact from tools; never ask the user for a file, an id or details you can look up. \
Never invent a document, amount, date or reference.
- What to do about a document (pay, reply, keep): explain_document.
- search_documents finds documents and their ids (short keywords as written in the documents, \
mostly French: "taxe foncière", "EDF", "carte identité"; or a category). The fields and \
passages often answer; otherwise read_document{vision}.
- Chain tools when needed (find the document, then act on it). Compute totals and dates \
yourself from tool figures only.
- Change data (reminder, paid, correction, validation, trash) only when the user asks, then \
say what you did. A reminder needs no document: create it with the date given (next \
occurrence of that date). For a letter, call draft_letter: the app shows it, do not rewrite it.
- Ask the user a question only when the request itself is ambiguous, never for what a tool \
can find.
- French paperwork: net salary is "net à payer" (not "net imposable"); a document's `amount` \
field is its main figure.
Reply in {language}: short and precise (1-4 sentences, a short list when comparing), exact \
figures, dates written out, plain text (**bold** allowed, no headings or tables). Do not \
repeat lists the app already shows (results, deadlines). Cite each fact from a document \
right after it, exactly as [#id]: "Property tax: €1,240, due 6 October [#3]." (never \
"ID #3" or "document #3"). Only cite ids returned by tools or shown earlier; never write \
other ids (deadlines, reminders)."""
VISION_HINT = ", or view_document to look at the page itself (scans, photos, tables)"
ATTACHED_NOTE = "\nAttached documents are already filed; their content is in the message."
# Asked when the model answered without looking at anything: its facts would be invented.
TOOLS_FIRST = (
    "You have not checked the user's documents yet: call the tools first, then answer from "
    "what they return."
)
# Asked when the model says it will act but called no tool to do it.
DO_IT = "You said you would do it, but no tool was called: call the tool now, then confirm."
# "I'll move it to the trash", "je la mets à la corbeille", "je vais créer un rappel"…
PROMISE = re.compile(
    r"\b(?:je vais|laissez-moi|je dois (?:v[ée]rifier|regarder|examiner|chercher)|"
    r"je m'en (?:occupe|charge)|je (?:la |le |les |vous )?(?:mets|marque|corrige|"
    r"supprime|valide|déplace|range|crée|rédige|programme|ajoute|enregistre)\b|i(?:'ll| will| am "
    r"going to)\b|let me\b|i'm (?:now )?(?:moving|marking|creating|updating|deleting))",
    re.IGNORECASE,
)
# Asked when the model hands the request back to the user instead of doing it.
JUST_DO_IT = (
    "Do not ask the user for what the tools can give or what the request does not need (a "
    "reminder only needs a title and a date): do what was asked now, or say plainly what is "
    "missing."
)
ASKS_USER = re.compile(
    r"pourriez-vous|pouvez-vous (?:me )?(?:pr[ée]ciser|indiquer|confirmer|donner)|"
    r"j'aurais besoin|merci de (?:pr[ée]ciser|confirmer|m'indiquer)|could you (?:tell|confirm|"
    r"specify|provide|give)|please (?:provide|confirm|specify)|i (?:would )?need (?:you|more)",
    re.IGNORECASE,
)
# Asked when the model ran out of steps or answered nothing.
FINAL_NUDGE = "Answer the user now with what you found, without calling tools."

# Earlier turns kept, and their length: older context rarely helps and costs tokens.
HISTORY_MESSAGES = 8
HISTORY_CHARS = 1500
# Text of the attached documents sent with the message, shared between them.
ATTACHMENT_CHARS = 6000

CITATION = re.compile(r"\s?\[#(\d+)\]")
# A document reference not written [#id]: "(ID #12)", "(document #6)", "doc #3", "#5".
LOOSE_CITATION = re.compile(
    r"\s*(?<!\[)(?:\b(?:ID|id|Id|documents?|Documents?|doc|n°)\s*)?#(?P<id>\d+)\b(?!\])"
)
# Citations left alone in brackets once normalized: "( [#5] et [#4])".
BRACKETED = re.compile(r"\s*\(\s*((?:\[#\d+\][\s,]*(?:et|and|&)?[\s,]*)+)\)")

Emit = Callable[[dict[str, Any]], None]


def _money_pattern(amount: float) -> str:
    """An amount as an answer may write it: 1240, 1 240, 1,240.00, 94,37…"""
    units, cents = f"{amount:.2f}".split(".")
    grouped = units if len(units) <= 3 else rf"{units[:-3]}[\s.,]?{units[-3:]}"
    tail = r"(?:[.,]00)?" if cents == "00" else rf"[.,]{cents}"
    return rf"(?<![\d.,]){grouped}{tail}(?![\d])"


T = i18n.catalog(
    "agent",
    {
        "unfinished": {
            "en": "I couldn't finish this request.",
            "fr": "Je n'ai pas pu terminer cette demande.",
        },
        "reminder_needs_date": {
            "en": "To create a reminder, give a date (e.g. “remind me to pay the school canteen "
            "on 12/11/2026”).",
            "fr": "Pour créer un rappel, indiquez une date (ex. « rappelle-moi de payer la "
            "cantine le 12/11/2026 »).",
        },
        "reminder": {"en": "Reminder", "fr": "Rappel"},
        "reminder_created": {
            "en": "Done: reminder “{title}” on {date:date}.",
            "fr": "C'est noté : rappel « {title} » le {date:date}.",
        },
        "period_month": {"en": "in this period", "fr": "sur cette période"},
        "period_30_days": {"en": "in the next 30 days", "fr": "dans les 30 prochains jours"},
        "no_deadlines": {"en": "No deadlines {period}.", "fr": "Aucune échéance {period}."},
        "deadlines_one": {
            "en": "You have {n} deadline {period}{total}.",
            "fr": "Vous avez {n} échéance {period}{total}.",
        },
        "deadlines_other": {
            "en": "You have {n} deadlines {period}{total}.",
            "fr": "Vous avez {n} échéances {period}{total}.",
        },
        "deadlines_total": {
            "en": ", for a total of {amount:money}",
            "fr": ", pour un total de {amount:money}",
        },
        "to_review_one": {"en": "{n} document to review.", "fr": "{n} document à vérifier."},
        "to_review_other": {"en": "{n} documents to review.", "fr": "{n} documents à vérifier."},
        "nothing_to_review": {
            "en": "Nothing to review, everything is in order.",
            "fr": "Rien à vérifier, tout est en ordre.",
        },
        "export_one": {
            "en": "Export ready ({n} document): [download the folder]({link}).",
            "fr": "Export prêt ({n} document) : [télécharger le dossier]({link}).",
        },
        "export_other": {
            "en": "Export ready ({n} documents): [download the folder]({link}).",
            "fr": "Export prêt ({n} documents) : [télécharger le dossier]({link}).",
        },
        "no_match": {
            "en": "I couldn't find any matching document.",
            "fr": "Je n'ai trouvé aucun document correspondant.",
        },
        "latest": {
            "en": "Here is your most recent document: {title}.",
            "fr": "Voici votre document le plus récent : {title}.",
        },
        "found_one": {"en": "I found {n} document.", "fr": "J'ai trouvé {n} document."},
        "found_other": {
            "en": "I found {n} documents. Here is the list.",
            "fr": "J'ai trouvé {n} documents. Voici la liste.",
        },
        "label_expiry_date": {"en": "Expiry date", "fr": "Fin de validité"},
        "label_amount": {"en": "Amount", "fr": "Montant"},
        "label_due_date": {"en": "Due date", "fr": "Échéance"},
        "label_reference": {"en": "Reference", "fr": "Référence"},
        "field_missing": {
            "en": "{label}: I couldn't find it in “{title}” [#{id}].",
            "fr": "{label} : je ne l'ai pas trouvé dans « {title} » [#{id}].",
        },
        "field_value": {
            "en": "{label} for “{title}”: {value} [#{id}].",
            "fr": "{label} de « {title} » : {value} [#{id}].",
        },
        "action_by": {"en": "{label} by {date:date}", "fr": "{label} avant le {date:date}"},
        "actions_separator": {"en": "; ", "fr": " ; "},
        "to_do": {"en": " To do: {actions}.", "fr": " À faire : {actions}."},
        "explain_attachment": {
            "en": "Explain this document to me.",
            "fr": "Explique-moi ce document.",
        },
        "attachments": {
            "en": "Attached documents:",
            "fr": "Documents joints :",
        },
        "folder_status": {
            "en": "{title}: {ready} of {total} pieces ready.",
            "fr": "{title} : {ready} pièces prêtes sur {total}.",
        },
        "folder_missing": {"en": " Missing: {pieces}.", "fr": " Il manque : {pieces}."},
        "folder_renew": {"en": " To renew: {pieces}.", "fr": " À renouveler : {pieces}."},
        "folder_link": {
            "en": " [Download the pack]({link})",
            "fr": " [Télécharger le dossier]({link})",
        },
        "list_separator": {"en": ", ", "fr": ", "},
        "subscriptions_none": {
            "en": "I haven't found any recurring bill yet.",
            "fr": "Je n'ai pas encore repéré de facture récurrente.",
        },
        "subscriptions_one": {
            "en": "{n} recurring bill, about {amount:money} a year.",
            "fr": "{n} facture récurrente, environ {amount:money} par an.",
        },
        "subscriptions_other": {
            "en": "{n} recurring bills, about {amount:money} a year.",
            "fr": "{n} factures récurrentes, environ {amount:money} par an.",
        },
        "price_rise": {"en": " Price rise: {names}.", "fr": " Hausse de prix : {names}."},
        "nothing_to_renew": {
            "en": "No document to renew for now.",
            "fr": "Aucun document à renouveler pour l'instant.",
        },
        "to_renew": {"en": "To renew: {items}.", "fr": "À renouveler : {items}."},
        "renew_item": {"en": "{title} ({date:date})", "fr": "{title} ({date:date})"},
        "nothing_to_sort": {
            "en": "Nothing to throw away for now: every document is still within its "
            "retention period.",
            "fr": "Rien à jeter pour l'instant : tous vos documents sont encore dans leur durée "
            "de conservation.",
        },
        "to_sort_one": {
            "en": "{n} document can be thrown away: {titles}.",
            "fr": "{n} document peut être jeté : {titles}.",
        },
        "to_sort_other": {
            "en": "{n} documents can be thrown away: {titles}.",
            "fr": "{n} documents peuvent être jetés : {titles}.",
        },
        "letter_ready": {
            "en": "Here is a draft: “{subject}”, to {recipient}.",
            "fr": "Voici un brouillon : « {subject} », adressé à {recipient}.",
        },
        "paid_done": {"en": "Marked as paid: {title}.", "fr": "Marqué comme réglé : {title}."},
        "paid_not_found": {
            "en": "I couldn't find an unpaid deadline for that document.",
            "fr": "Je n'ai pas trouvé d'échéance à régler pour ce document.",
        },
    },
)


class _Collector:
    def __init__(self, emit: Emit | None = None) -> None:
        self.documents: dict[int, Document] = {}
        # Documents of earlier turns: citable again, shown only if cited.
        self.earlier: dict[int, Document] = {}
        self.deadlines: dict[int, Deadline] = {}
        self.letters: list[letters.Letter] = []
        self.calls: list[ToolCallTrace] = []
        self.changed = False
        self.emit = emit or (lambda _: None)

    def run(self, session: Session, name: str, arguments: dict[str, Any]) -> tools.ToolResult:
        self.calls.append(ToolCallTrace(name=name, arguments=arguments))
        self.emit({"type": "tool", "name": name, "arguments": arguments})
        try:
            result = tools.call(session, name, arguments)
        except (TypeError, ValueError, LookupError) as exc:
            log.exception("Tool %s failed", name)
            result = tools.ToolResult(payload={"error": f"{name} failed: {exc}"})
        for d in result.documents:
            if d.id is not None:
                self.documents[d.id] = d
        for dl in result.deadlines:
            if dl.id is not None:
                self.deadlines[dl.id] = dl
        self.letters += result.letters
        self.changed = self.changed or result.changed
        return result

    def _normalize_citations(self, answer: str) -> str:
        """Small models write "(ID #12)", "document #6" or "#5" instead of [#12]: those that
        name a document the tools returned become citations, others (a contract number
        "#4521877") are left as they are."""

        def fix(m: re.Match[str]) -> str:
            doc_id = int(m["id"])
            if doc_id not in self.documents and doc_id not in self.earlier:
                return m[0]
            return f" [#{doc_id}]"

        answer = LOOSE_CITATION.sub(fix, answer)
        return BRACKETED.sub(lambda m: " " + m[1].strip(), answer)

    def _cite_by_title(self, answer: str) -> str:
        """An answer without any citation: each document of this turn it names without
        ambiguity (its title, reference or amount, shared with no other document of the turn)
        is cited at the end of the first sentence naming it, so the user can open the source."""
        owners: dict[str, set[int]] = {}
        markers: dict[int, list[re.Pattern[str]]] = {}
        for doc_id, doc in self.documents.items():
            found = []
            title = normalize(doc.title).replace("’", "'").strip()
            if len(title) >= 6:
                found.append(re.escape(title))
            if doc.reference and len(doc.reference) >= 5:
                found.append(re.escape(normalize(doc.reference)))
            if doc.amount:
                found.append(_money_pattern(doc.amount))
            for marker in found:
                owners.setdefault(marker, set()).add(doc_id)
            markers[doc_id] = [re.compile(m) for m in found]
        sentences = re.split(r"(?<=[.!?])(\s+)", answer)
        flat = [normalize(re.sub(r"[\u00a0\u202f]", " ", x)).replace("’", "'") for x in sentences]
        for doc_id, patterns in markers.items():
            unique = [p for p in patterns if owners[p.pattern] == {doc_id}]
            for i, sentence in enumerate(sentences):
                if any(p.search(flat[i]) for p in unique):
                    end = re.search(r"[.!?:]?\s*$", sentence)
                    cut = end.start() if end else len(sentence)
                    sentences[i] = f"{sentence[:cut]} [#{doc_id}]{sentence[cut:]}"
                    break
        return "".join(sentences)

    def response(self, answer: str, engine: str) -> ChatResponse:
        today = date.today()
        # A citation of a document the tools did not return is removed.
        cited: list[int] = []

        def keep(m: re.Match[str]) -> str:
            doc_id = int(m[1])
            if doc_id not in self.documents and doc_id not in self.earlier:
                return ""
            if doc_id not in cited:
                cited.append(doc_id)
            return m[0]

        answer = self._normalize_citations(answer)
        if not CITATION.search(answer):
            answer = self._cite_by_title(answer)
        answer = CITATION.sub(keep, answer)
        shown = dict(self.documents)
        for doc_id in cited:
            if doc_id not in shown:
                shown[doc_id] = self.earlier[doc_id]
        return ChatResponse(
            answer=answer,
            citations=cited,
            documents=[DocumentOut.from_model(d) for d in shown.values()],
            deadlines=[DeadlineOut.from_model(d, today) for d in self.deadlines.values()],
            letters=self.letters,
            tool_calls=self.calls,
            changed=self.changed,
            engine=engine,
        )


def run(
    session: Session,
    message: str,
    history: list[ChatMessage],
    attachments: list[Document] | None = None,
    emit: Emit | None = None,
) -> ChatResponse:
    """Answers a message; `attachments` are documents the user joined to it (already filed).

    `emit` receives the progress: {"type": "tool", "name", "arguments"} when a tool starts,
    {"type": "token", "text"} as the answer is written, {"type": "step"} when the text written
    so far was only a preamble to tool calls (to discard)."""
    attached = attachments or []
    if not message.strip() and attached:
        message = T("explain_attachment")
    if llm.is_available():
        try:
            return _run_llm(session, message, history, attached, emit)
        except (httpx.HTTPError, KeyError, ValueError):
            log.exception("LLM agent unavailable, falling back to the router")
            session.rollback()
    return _run_rules(session, message, attached, emit)


def system_prompt(session: Session | None = None, *, vision: bool = False) -> str:
    snapshot = llm.dumps(tools.overview(session)) if session is not None else "unknown"
    return SYSTEM_PROMPT.format(
        today=date.today().isoformat(),
        overview=snapshot,
        vision=VISION_HINT if vision else "",
        **llm.user_context(),
    )


def _with_attachments(collector: _Collector, message: str, attached: list[Document]) -> str:
    """The message followed by the content of the attached documents, which can be cited."""
    if not attached:
        return message
    share = ATTACHMENT_CHARS // len(attached)
    parts = [message, "", T("attachments")]
    for doc in attached:
        assert doc.id is not None
        collector.documents[doc.id] = doc
        summary = {**tools.doc_summary(doc), "text": llm.compact(doc.text, share)}
        parts.append(llm.dumps(summary))
    return "\n".join(parts)


def _history(
    session: Session, collector: _Collector, history: list[ChatMessage]
) -> list[dict[str, Any]]:
    """Earlier turns, each answer followed by the documents it showed: "and when is it due?"
    then refers to a known id instead of a new search."""
    turns = history[-HISTORY_MESSAGES:]
    ids = {i for m in turns for i in m.documents}
    if ids:
        docs = session.exec(
            select(Document).options(*WITHOUT_TEXT).where(col(Document.id).in_(ids))
        )
        collector.earlier.update({d.id: d for d in docs if d.id is not None and not d.deleted_at})
    messages = []
    for m in turns:
        content = m.content[:HISTORY_CHARS]
        known = [collector.earlier[i] for i in m.documents[:10] if i in collector.earlier]
        if m.role == "assistant" and known:
            listed = "; ".join(f"#{d.id} {d.title}" for d in known)
            content += f"\n(documents shown: {listed})"
        messages.append({"role": m.role, "content": content})
    return messages


def _arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    parsed = json.loads(raw or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("arguments must be an object")
    return parsed


def _run_llm(
    session: Session,
    message: str,
    history: list[ChatMessage],
    attached: list[Document],
    emit: Emit | None,
) -> ChatResponse:
    collector = _Collector(emit)
    vision = llm.has_vision()
    schemas = tools.schemas(vision)
    think = get_settings().llm_think
    system = system_prompt(session, vision=vision) + (ATTACHED_NOTE if attached else "")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        *_history(session, collector, history),
        {"role": "user", "content": _with_attachments(collector, message, attached)},
    ]
    on_token = (lambda text: emit({"type": "token", "text": text})) if emit else None
    # Same call, same arguments: the model is looping, it gets the result again with a nudge.
    seen: set[str] = set()
    checked = bool(attached)
    reminded = pushed = False
    for _ in range(MAX_STEPS):
        reply = llm.chat(messages, tools=schemas, think=think, on_token=on_token)
        calls = reply.get("tool_calls") or []
        content = str(reply.get("content") or "").strip()
        if not calls and not checked:
            # An answer before any tool call is the model's guess: asked once to look first.
            checked = True
            if emit:
                emit({"type": "step"})
            messages.append({"role": "user", "content": TOOLS_FIRST})
            continue
        checked = True
        messages.append({"role": "assistant", "content": content, "tool_calls": calls})
        if not calls:
            if content and not reminded and not collector.changed and PROMISE.search(content):
                # Announced an action without doing it: asked once to actually do it.
                reminded = True
                if emit:
                    emit({"type": "step"})
                messages.append({"role": "user", "content": DO_IT})
                continue
            if content and not pushed and not collector.changed and ASKS_USER.search(content):
                # Handed the request back: asked once to do it with what it has.
                pushed = True
                if emit:
                    emit({"type": "step"})
                messages.append({"role": "user", "content": JUST_DO_IT})
                continue
            if content:
                return collector.response(content, "llm")
            break
        if content and emit:
            emit({"type": "step"})
        for call in calls:
            fn = call.get("function") or {}
            name = str(fn.get("name") or "")
            try:
                args = _arguments(fn.get("arguments"))
            except ValueError:
                payload: Any = {"error": "Arguments are not valid JSON: call the tool again."}
                messages.append({"role": "tool", "tool_name": name, "content": llm.dumps(payload)})
                continue
            key = f"{name}:{json.dumps(args, sort_keys=True)}"
            result = collector.run(session, name, args)
            payload = result.payload
            if key in seen:
                payload = {"note": "Same call as before, same result: answer now.", **payload}
            seen.add(key)
            tool_message: dict[str, Any] = {
                "role": "tool",
                "tool_name": name,
                "content": llm.dumps(payload),
            }
            if result.images:
                tool_message["images"] = [llm.image(i) for i in result.images]
            messages.append(tool_message)
    # Out of steps, or an empty answer: one last turn without tools.
    if emit:
        emit({"type": "step"})
    messages.append({"role": "user", "content": FINAL_NUDGE})
    reply = llm.chat(messages, think=think, on_token=on_token)
    answer = str(reply.get("content") or "").strip()
    return collector.response(answer or T("unfinished"), "llm")


# --- Router without a model ---------------------------------------------------------------
# Patterns apply to normalized text (lowercase, no accents), in French and in English.

_MONTH_NAMES = "|".join(tools.ALL_MONTHS)


def _month_range(norm: str, today: date) -> tuple[date, date] | None:
    for name, month in tools.ALL_MONTHS.items():
        if re.search(rf"\b{name}\b", norm):
            year = today.year
            start = date(year, month, 1)
            end = date(year + (month == 12), month % 12 + 1, 1)
            return start, date.fromordinal(end.toordinal() - 1)
    return None


def _since(norm: str, today: date) -> date | None:
    m = re.search(
        rf"(?:depuis (?:le mois de |d')?|since (?:the beginning of )?)({_MONTH_NAMES})\b", norm
    )
    if not m:
        return None
    month = tools.ALL_MONTHS[m[1]]
    year = today.year if month <= today.month else today.year - 1
    return date(year, month, 1)


def _category_in(norm: str) -> tuple[Category, str] | None:
    """Category named in the request (slug or label in any language) and the matched words."""
    for c in Category:
        if c == Category.OTHER:
            continue
        names = {
            c.value,
            *(normalize(i18n.category_label(c.value, lang)) for lang in i18n.LANGUAGES),
        }
        # Singular forms too: "tax" for "taxes", "impot" for "impots".
        names |= {n[:-2] for n in names if n.endswith("es")}
        names |= {n[:-1] for n in names if n.endswith("s")}
        for name in sorted(names, key=len, reverse=True):
            if re.search(rf"\b{re.escape(name)}\b", norm):
                return c, name
    return None


# (question pattern, document field)
QUESTION_FIELDS: list[tuple[str, str]] = [
    (r"\bexpir|valable|validite|valid until|\bvalid\b", "expiry_date"),
    (r"\bcombien|montant|\bprix\b|\bcout|how much|\bamount\b|\bprice\b|\bcost", "amount"),
    (
        r"\bquand\b|date limite|avant quand|payer avant|\bwhen\b|due date|pay (?:it )?by"
        r"|pay (?:it )?before",
        "due_date",
    ),
    (r"reference|\bnumero\b|\bnumber\b", "reference"),
]
EXPLAIN = (
    r"expliqu|que dois-je faire|dois-je (?:faire|payer|repondre|agir)|c'est quoi"
    r"|qu'est-ce que|ca veut dire|je dois faire|faut-il"
    r"|explain|what should i do|what do i (?:need|have) to do|do i (?:need|have) to"
    r"|should i (?:do|pay|reply|answer|act)|what does (?:it|this|that) mean|what is this"
)
# Words of a question that are not search terms (after tools.keywords: normalized, stemmed).
QUESTION_WORDS = {
    # French
    "combien", "montant", "prix", "cout", "coute", "quand", "date", "limite", "payer",
    "paye", "reference", "numero", "expire", "valable", "validite", "fin", "explique",
    "expliquer", "explication", "dois", "doi", "faire", "faut", "il", "quoi", "est", "veut",
    "dire", "courrier", "lettre", "ca", "c", "qu", "agir", "repondre", "ai", "mon", "ma",
    "quelque", "chose", "rien",
    # English
    "how", "much", "amount", "price", "cost", "when", "due", "deadline", "pay", "paid",
    "number", "expiry", "expiring", "valid", "until", "explain", "explanation",
    "should", "need", "mean", "doe", "thi", "letter", "mail", "anything", "something",
    "nothing", "reply", "answer", "act", "will", "be", "going", "next", "there",
}  # fmt: skip


def _answer_question(
    session: Session, collector: _Collector, message: str, doc: Document | None = None
) -> str | None:
    """Question about one document: answers with the requested field and cites the source.

    Without `doc`, the document is searched from the words of the question; with an attached
    `doc`, a message that asks for no particular field is a request to explain it."""
    norm = normalize(message)
    explain = bool(re.search(EXPLAIN, norm))
    field = next((f for f in QUESTION_FIELDS if re.search(f[0], norm)), None)
    if doc is not None:
        assert doc.id is not None
        collector.documents[doc.id] = doc
        explain = explain or not field
    else:
        if not explain and not field:
            return None
        terms = [t for t in tools.keywords(message) if t not in QUESTION_WORDS]
        if not terms:
            return None
        found = collector.run(session, "search_documents", {"query": " ".join(terms), "limit": 3})
        if not found.documents:
            return None
        doc = found.documents[0]
    if explain:
        payload = collector.run(session, "explain_document", {"document_id": doc.id}).payload
        todo = T.get("actions_separator").join(
            T("action_by", label=a["label"], date=a["due_date"]) if a["due_date"] else a["label"]
            for a in payload["actions"]
        )
        return f"{payload['summary']} [#{doc.id}]" + (T("to_do", actions=todo) if todo else "")
    assert field is not None
    _, name = field
    if name == "due_date" and doc.due_date is None and doc.expiry_date is not None:
        # "When is my car inspection due?": for an expiring document, the date asked is its end
        # of validity.
        name = "expiry_date"
    label = T(f"label_{name}")
    value = getattr(doc, name)
    if value in (None, ""):
        answer = T("field_missing", label=label, title=doc.title, id=doc.id)
    else:
        shown = i18n.format_field_value(name, value)
        answer = T("field_value", label=label, title=doc.title, value=shown, id=doc.id)
    return answer


REMINDER = r"rappel|rappelle|previens|remind|reminder"
REMINDER_WORDS = (
    r"(?i)rappelle[- ]moi( de)?|cr[ée]e un rappel( pour)?|remind me( to| about| of)?"
    r"|(?:create|set|add) a reminder( to| for)?|\b(?:le|on|dans|in) \d.*$"
)
FOLDER_KINDS = [
    (r"location|louer|bailleur|proprietaire|rental|rent a|landlord", "rental"),
    (r"pret immobilier|credit immobilier|emprunt|mortgage|home loan", "mortgage"),
    (r"\bcaf\b|aide au logement|\bapl\b|housing benefit", "caf"),
]
FOLDER = r"dossier|pieces?|manque|application|documents? (?:do i )?need|what do i need"
SUBSCRIPTIONS = r"abonnement|recurrent|subscription|recurring|hausse|augment|price rise|increase"
RENEW = r"renouvel|perime|plus valable|papiers|renew|expired|still valid"
SORT_OUT = r"jeter|trier|faire le tri|me debarrasser|throw (?:away|out)|sort out|get rid"
LETTER = r"lettre|courrier|resili|reclamation|contester|letter|cancel my|complaint|dispute"
LETTER_KINDS = [
    (r"resili|mettre fin|cancel|terminat", "termination"),
    (r"reclam|contest|litige|complain|dispute|overcharg", "complaint"),
]
LETTER_WORDS = {
    "lettre", "courrier", "ecri", "ecrire", "ecris", "redige", "rediger", "resilier", "resilie",
    "resiliation", "reclamation", "contester", "pour", "abonnement", "contrat", "write", "letter",
    "draft", "cancel", "cancellation", "complaint", "dispute", "subscription", "contract",
}  # fmt: skip
PAID = r"j'ai (?:paye|regle)|deja (?:paye|regle)|marque.{0,30}(?:paye|regle)|i(?:'ve| have)? paid"
QUESTION = r"\bcombien|\bquand\b|\bquel|\?|how much|\bwhen\b|\bwhat\b|\bwhich\b"
PAID_WORDS = {"paye", "regle", "marque", "comme", "deja", "ce", "matin", "hier", "paid", "mark",
              "as", "already", "today", "yesterday", "la", "le", "it"}  # fmt: skip


def _loose_dates(norm: str, today: date) -> list[date]:
    """Dates of a request without a year ("le 12 novembre", "12/11") or relative ("dans 2
    semaines", "in 3 days"): the next occurrence."""
    m = re.search(
        rf"\b(\d{{1,2}})(?:er)? ({_MONTH_NAMES})\b|\b({_MONTH_NAMES}) (\d{{1,2}})\b", norm
    )
    numeric = re.search(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", norm)
    day_month: tuple[int, int] | None = None
    if m:
        day = int(m[1] or m[4])
        day_month = (day, tools.ALL_MONTHS[m[2] or m[3]])
    elif numeric:
        day_month = (int(numeric[1]), int(numeric[2]))
    if day_month:
        for year in (today.year, today.year + 1):
            try:
                found = date(year, day_month[1], day_month[0])
            except ValueError:
                return []
            if found >= today:
                return [found]
    rel = re.search(r"(?:dans|in) (\d{1,3}) (jours?|days?|semaines?|weeks?|mois|months?)", norm)
    if rel:
        n = int(rel[1])
        unit = rel[2]
        days = n * 7 if unit[0] in "sw" else n * 30 if unit[0] == "m" else n
        return [date.fromordinal(today.toordinal() + days)]
    return []


def _document_named(
    session: Session, collector: _Collector, message: str, skip: set[str]
) -> Document | None:
    """The document a request is about, found from its remaining words."""
    terms = [t for t in tools.keywords(message) if t not in skip and t not in QUESTION_WORDS]
    if not terms:
        return None
    found = collector.run(session, "search_documents", {"query": " ".join(terms), "limit": 3})
    return found.documents[0] if found.documents else None


def _router_intents(session: Session, collector: _Collector, message: str, norm: str) -> str | None:
    """Requests about packs, letters, payments, subscriptions, renewals and sorting."""
    sep = T.get("list_separator")
    # "How much have I paid…" is a question, not a payment to record.
    if re.search(PAID, norm) and not re.search(QUESTION, norm):
        doc = _document_named(session, collector, message, PAID_WORDS)
        if doc is None:
            return T("no_match")
        result = collector.run(session, "mark_deadline_paid", {"document_id": doc.id})
        if "error" in result.payload:
            return T("paid_not_found")
        return T("paid_done", title=doc.title) + f" [#{doc.id}]"
    if re.search(LETTER, norm):
        kind = next((k for pattern, k in LETTER_KINDS if re.search(pattern, norm)), "request")
        doc = _document_named(session, collector, message, LETTER_WORDS)
        args: dict[str, Any] = {"kind": kind}
        if doc is not None:
            args["document_id"] = doc.id
        letter = collector.run(session, "draft_letter", args).letters[0]
        cite = f" [#{doc.id}]" if doc is not None else ""
        return T("letter_ready", subject=letter.subject, recipient=letter.recipient) + cite
    pack = next((k for pattern, k in FOLDER_KINDS if re.search(pattern, norm)), None)
    if pack and re.search(FOLDER, norm):
        payload = collector.run(session, "check_folder", {"kind": pack}).payload
        answer = T(
            "folder_status",
            title=payload["title"],
            ready=payload["ready"].split("/")[0],
            total=payload["ready"].split("/")[1],
        )
        missing = [
            p["piece"]
            for p in payload["pieces"]
            if p["status"] == "missing" and not p.get("optional")
        ]
        renew = [p["piece"] for p in payload["pieces"] if p["status"] == "outdated"]
        if missing:
            answer += T("folder_missing", pieces=sep.join(missing))
        if renew:
            answer += T("folder_renew", pieces=sep.join(renew))
        return answer + T("folder_link", link=payload["export_link"])
    if re.search(SORT_OUT, norm):
        payload = collector.run(session, "documents_to_sort_out", {}).payload
        found = payload["can_be_thrown_away"]
        if not found:
            return T("nothing_to_sort")
        titles = sep.join(f"{d['title']} [#{d['id']}]" for d in found[:5])
        return T.plural("to_sort", len(found), titles=titles)
    if re.search(SUBSCRIPTIONS, norm):
        payload = collector.run(session, "list_subscriptions", {}).payload
        subs = payload["subscriptions"]
        if not subs:
            return T("subscriptions_none")
        answer = T.plural("subscriptions", len(subs), amount=payload["yearly_total"])
        rises = [s["name"] for s in subs if s.get("price_increase")]
        return answer + (T("price_rise", names=sep.join(rises)) if rises else "")
    if re.search(RENEW, norm):
        payload = collector.run(session, "list_expirations", {}).payload
        due = [d for d in payload["documents"] if d["state"] != "valid"]
        if not due:
            return T("nothing_to_renew")
        items = sep.join(
            T("renew_item", title=d["title"], date=date.fromisoformat(d["expiry_date"]))
            + f" [#{d['id']}]"
            for d in due
        )
        return T("to_renew", items=items)
    return None


DEADLINES = (
    r"echeance|a payer|arrive|bientot|expir|date limite"
    r"|deadline|\bdue\b|to pay|coming up|upcoming|\bsoon\b"
)
REVIEW = r"verifier|manquant|incomplet|a completer|review|missing|incomplete|to check|to complete"
LATEST = r"\bdernier|\bderniere|\bplus recent|\blatest\b|\blast\b|most recent|\bnewest\b"


def _run_rules(
    session: Session, message: str, attached: list[Document], emit: Emit | None = None
) -> ChatResponse:
    collector = _Collector(emit)
    norm = normalize(message)
    today = date.today()

    if re.search(REMINDER, norm):
        dates = find_dates(norm) or _loose_dates(norm, today)
        if not dates:
            return collector.response(T("reminder_needs_date"), "rules")
        title = re.sub(REMINDER_WORDS, "", message).strip(" :,.") or T("reminder")
        title = title[:1].upper() + title[1:]
        collector.run(
            session, "create_reminder", {"title": title, "due_date": dates[0].isoformat()}
        )
        return collector.response(T("reminder_created", title=title, date=dates[0]), "rules")

    if attached:
        answers = [_answer_question(session, collector, message, doc) for doc in attached]
        return collector.response(" ".join(a for a in answers if a), "rules")

    intent = _router_intents(session, collector, message, norm)
    if intent:
        return collector.response(intent, "rules")

    answered = _answer_question(session, collector, message)
    if answered:
        return collector.response(answered, "rules")

    if re.search(DEADLINES, norm):
        month = _month_range(norm, today)
        period_args: dict[str, Any] = (
            {"start": month[0].isoformat(), "end": month[1].isoformat()} if month else {"days": 30}
        )
        result = collector.run(session, "list_deadlines", period_args)
        n = len(result.deadlines)
        period = T("period_month") if month else T("period_30_days")
        if not n:
            return collector.response(T("no_deadlines", period=period), "rules")
        amount = sum(d.amount or 0 for d in result.deadlines)
        total = T("deadlines_total", amount=amount) if amount else ""
        return collector.response(T.plural("deadlines", n, period=period, total=total), "rules")

    if re.search(REVIEW, norm):
        result = collector.run(session, "documents_to_review", {})
        n = len(result.documents)
        answer = T.plural("to_review", n) if n else T("nothing_to_review")
        return collector.response(answer, "rules")

    if re.search(r"export", norm):
        named = _category_in(norm)
        result = collector.run(
            session, "export_folder", {"category": named[0].value} if named else {}
        )
        count, link = result.payload["count"], result.payload["link"]
        return collector.response(T.plural("export", count, link=link), "rules")

    since = _since(norm, today)
    named = _category_in(norm)
    args: dict[str, Any] = {"query": message}
    if since:
        args["since"] = since.isoformat()
    # The category alone ("my tax documents"): filter on it rather than searching its name.
    if named and not tools.keywords(re.sub(rf"\b{re.escape(named[1])}\b", " ", norm)):
        args = {"category": named[0].value, **({"since": args["since"]} if since else {})}
    latest = bool(re.search(LATEST, norm))
    if latest:
        args["limit"] = 1
    result = collector.run(session, "search_documents", args)
    total = result.payload["total"]
    if not total:
        return collector.response(T("no_match"), "rules")
    if latest:
        return collector.response(T("latest", title=result.documents[0].title), "rules")
    return collector.response(T.plural("found", total), "rules")
