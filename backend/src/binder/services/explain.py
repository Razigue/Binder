""" "What is this, and do I need to do anything?" in plain language.

The local model writes the explanation when it is available; otherwise, rules describe the
document from its type, its extracted information and a few phrasings of the letter (reminder,
documents to send back, summons). The result is cached on the document, with the language it
was written in, and recomputed when its information or the user's language changes.
"""

import json
import logging
import re
from datetime import date

import httpx
from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from binder import i18n
from binder.models import DocType, Document
from binder.services import deadlines, llm
from binder.services.rules import find_dates, normalize

log = logging.getLogger(__name__)

T = i18n.catalog(
    "explain",
    {
        "from_issuer": {"en": " from {issuer}", "fr": " de {issuer}"},
        "from_issuer_elided": {"en": " from {issuer}", "fr": " d'{issuer}"},
        "income_tax": {
            "en": "This is an income tax notice from the tax authorities.",
            "fr": "C'est un avis d'impôt sur le revenu envoyé par l'administration fiscale.",
        },
        "local_tax": {
            "en": "This is a tax notice ({kind}) from the tax authorities.",
            "fr": "C'est un avis d'impôt ({kind}) envoyé par l'administration fiscale.",
        },
        "amount_to_pay": {
            "en": " The amount to pay is {amount:money}.",
            "fr": " Le montant à payer est de {amount:money}.",
        },
        "invoice": {"en": "This is an invoice{who}.", "fr": "C'est une facture{who}."},
        "invoice_amount": {
            "en": "This is an invoice{who} for {amount:money}.",
            "fr": "C'est une facture{who} d'un montant de {amount:money}.",
        },
        "payment_notice": {
            "en": "This is the renewal notice for your contract{who}: it renews automatically "
            "and the premium for the new period is {amount}.",
            "fr": "C'est l'avis de renouvellement de votre contrat{who} : il se reconduit et la "
            "cotisation de la nouvelle période est de {amount}.",
        },
        "amount_unread": {"en": "an amount we could not read", "fr": "montant non lu"},
        "rent_receipt": {
            "en": "This is a rent receipt: proof that your rent has been paid.",
            "fr": "C'est une quittance : la preuve que votre loyer a bien été payé.",
        },
        "certificate": {
            "en": "This is a certificate{who}. It proves your situation (entitlements, cover, "
            "payment) and may be asked for in an application.",
            "fr": "C'est une attestation{who}. Elle prouve votre situation (droits, couverture, "
            "paiement) et peut vous être demandée pour une démarche.",
        },
        "bank_statement": {
            "en": "This is an account statement{who} listing your transactions for the period.",
            "fr": "C'est un relevé de compte{who} qui liste vos opérations de la période.",
        },
        "check_transactions": {
            "en": "Check that you recognise every transaction.",
            "fr": "Vérifiez qu'aucune opération ne vous est inconnue.",
        },
        "payslip": {"en": "This is your payslip.", "fr": "C'est votre fiche de paie."},
        "payslip_amount": {
            "en": "This is your payslip: {amount:money} net paid.",
            "fr": "C'est votre fiche de paie : {amount:money} net versé.",
        },
        "keep_payslip": {
            "en": "Keep it until you retire: it is used to calculate your pension rights.",
            "fr": "À conserver jusqu'à la retraite : elle sert au calcul de vos droits.",
        },
        "reimbursement": {
            "en": "This is the breakdown of a healthcare reimbursement.",
            "fr": "C'est le détail d'un remboursement de soins.",
        },
        "reimbursement_amount": {
            "en": "This is the breakdown of a healthcare reimbursement: {amount:money} has been "
            "paid to you.",
            "fr": "C'est le détail d'un remboursement de soins : {amount:money} vous ont été "
            "versés.",
        },
        "quote": {
            "en": "This is a quote{who}: a price proposal. Nothing is owed until you accept it.",
            "fr": "C'est un devis{who} : une proposition de prix. Rien n'est dû tant que vous ne "
            "l'avez pas accepté.",
        },
        "quote_amount": {
            "en": "This is a quote{who} for {amount:money}: a price proposal. Nothing is owed "
            "until you accept it.",
            "fr": "C'est un devis{who} de {amount:money} : une proposition de prix. Rien n'est "
            "dû tant que vous ne l'avez pas accepté.",
        },
        "your_document": {"en": "This is your {kind}.", "fr": "C'est votre {kind}."},
        "your_document_until": {
            "en": "This is your {kind}, valid until {expiry:date}.",
            "fr": "C'est votre {kind}, valable jusqu'au {expiry:date}.",
        },
        "document": {"en": "document", "fr": "document"},
        "generic": {
            "en": "Document “{title}”{who}, filed under {category:category}.",
            "fr": "Document « {title} »{who}, classé dans {category:category}.",
        },
        "direct_debit": {
            "en": "The amount will be debited automatically on {date:date}: just make sure "
            "your account has enough funds.",
            "fr": "Le montant sera prélevé automatiquement le {date:date} : vérifiez simplement "
            "que votre compte est approvisionné.",
        },
        "pay": {"en": "Pay {amount:money}", "fr": "Payer {amount:money}"},
        "settle": {
            "en": "Settle this quickly: it is a reminder",
            "fr": "Régulariser rapidement : c'est une relance",
        },
        "fees": {
            "en": "Without a reply, fees or surcharges may be added.",
            "fr": "Sans réponse, des frais ou majorations peuvent s'ajouter.",
        },
        "send_back": {
            "en": "Send back the requested documents or information",
            "fr": "Renvoyer les documents ou informations demandés",
        },
        "attend": {"en": "Attend the appointment", "fr": "Se présenter au rendez-vous"},
        "renew_identity_card": {
            "en": "Book an appointment at the town hall to renew it",
            "fr": "Prendre rendez-vous en mairie pour la renouveler",
        },
        "renew_passport": {
            "en": "Book an appointment at the town hall to renew it",
            "fr": "Prendre rendez-vous en mairie pour le renouveler",
        },
        "renew_residence_permit": {
            "en": "Apply for renewal at the prefecture",
            "fr": "Demander le renouvellement à la préfecture",
        },
        "renew_driving_licence": {
            "en": "Apply for renewal on the ANTS website",
            "fr": "Demander le renouvellement sur le site de l'ANTS",
        },
        "renew_roadworthiness_test": {
            "en": "Book your next roadworthiness test",
            "fr": "Prendre rendez-vous pour le prochain contrôle technique",
        },
        "renew_certificate": {
            "en": "Request the new certificate",
            "fr": "Demander la nouvelle attestation",
        },
        "renew": {"en": "Renew", "fr": "Renouveler"},
        "reference": {
            "en": "Reference to quote in your correspondence: {reference}.",
            "fr": "Référence à rappeler dans vos échanges : {reference}.",
        },
        "nothing_to_do": {
            "en": " You have nothing to do except keep it.",
            "fr": " Vous n'avez rien à faire, à part le conserver.",
        },
    },
)


class Action(BaseModel):
    label: str
    due_date: date | None = None


class Explanation(BaseModel):
    summary: str
    action_required: bool
    actions: list[Action] = []
    key_points: list[str] = []
    engine: str = "rules"
    # Language the explanation is written in (None: cached by an older version).
    language: str | None = None


PROMPT = """Explain this administrative letter (often French) to someone who dislikes \
paperwork. User country: {country}, currency {currency}. Today: {today}. Write all text in \
{language}, plainly, using only what the letter says.
summary: 2-3 simple sentences: who writes, why, what it means for the user
action_required: true only if the user must act (pay, reply, send a document, attend, renew); \
false for a direct debit or a mere proof
actions: what to do, with due_date YYYY-MM-DD or null; empty if nothing to do
key_points: 0-3 useful facts (amount, reference to quote, risk of not acting)
Known: {facts}
Letter:
\"\"\"
{text}
\"\"\"
"""

# Output constraint given to Ollama (types only).
SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "action_required": {"type": "boolean"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "due_date": {"type": ["string", "null"]},
                },
                "required": ["label", "due_date"],
            },
        },
        "key_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "action_required", "actions", "key_points"],
}

# Phrasings of French letters (normalized text: lowercase, no accents).
REMINDER = r"mise en demeure|relance|impaye|dernier rappel|majoration|penalite|retard de paiement"
SEND_BACK = (
    r"a (?:nous )?(?:retourner|renvoyer)|merci de (?:nous )?(?:retourner|renvoyer|transmettre)"
    r"|a completer|signer et (?:retourner|renvoyer)|pieces? justificatives?|nous faire parvenir"
)
SUMMONS = r"convocation|vous etes convoque|rendez-vous (?:le|fixe)"
DIRECT_DEBIT = r"prelev|mensualis"

TAX_NOTICES = {DocType.PROPERTY_TAX, DocType.HOUSING_TAX, DocType.TAX_NOTICE}
# "Attestation…" documents: both kinds of certificate.
CERTIFICATES = {DocType.CERTIFICATE, DocType.INSURANCE_CERTIFICATE}
# Documents that do not call for a payment even with an amount and a date.
NO_PAYMENT = {DocType.RENT_RECEIPT, DocType.PAYSLIP}


def _who(issuer: str | None) -> str:
    """ " from EDF", « d'EDF », « de MAIF »: French elides before a vowel."""
    if not issuer:
        return ""
    elided = normalize(issuer[:1]) in "aeiouyh"
    return T("from_issuer_elided" if elided else "from_issuer", issuer=issuer)


def _kind_label(kind: str) -> str:
    """Document type label inside a sentence: "identity card", « carte d'identité »."""
    label = i18n.doc_type_label(kind) if kind else T("document")
    # Lowercase the first letter, but not acronyms ("RIB").
    return label[:1].lower() + label[1:] if label[1:2].islower() else label


def _first_date_after(norm: str, pattern: str) -> date | None:
    m = re.search(pattern, norm)
    if not m:
        return None
    dates = find_dates(norm[m.start() : m.start() + 160])
    return dates[0] if dates else None


def _summary(doc: Document, kind: str, who: str) -> tuple[str, list[str]]:
    amount = doc.amount
    points: list[str] = []
    if kind in TAX_NOTICES:
        if kind == DocType.TAX_NOTICE:
            summary = T("income_tax")
        else:
            summary = T("local_tax", kind=_kind_label(kind))
        if amount:
            summary += T("amount_to_pay", amount=amount)
    elif kind == DocType.INVOICE:
        summary = T("invoice_amount", who=who, amount=amount) if amount else T("invoice", who=who)
    elif kind == DocType.PAYMENT_NOTICE:
        shown = i18n.format_money(amount) if amount else T("amount_unread")
        summary = T("payment_notice", who=who, amount=shown)
    elif kind == DocType.RENT_RECEIPT:
        summary = T("rent_receipt")
    elif kind in CERTIFICATES:
        summary = T("certificate", who=who)
    elif kind == DocType.BANK_STATEMENT:
        summary = T("bank_statement", who=who)
        points.append(T("check_transactions"))
    elif kind == DocType.PAYSLIP:
        summary = T("payslip_amount", amount=amount) if amount else T("payslip")
        points.append(T("keep_payslip"))
    elif kind == DocType.REIMBURSEMENT_STATEMENT:
        summary = T("reimbursement_amount", amount=amount) if amount else T("reimbursement")
    elif kind == DocType.QUOTE:
        summary = T("quote_amount", who=who, amount=amount) if amount else T("quote", who=who)
    elif kind in deadlines.NOTICE_DAYS or doc.expiry_date:
        if doc.expiry_date:
            summary = T("your_document_until", kind=_kind_label(kind), expiry=doc.expiry_date)
        else:
            summary = T("your_document", kind=_kind_label(kind))
    else:
        summary = T("generic", title=doc.title, who=who, category=doc.category.value)
    return summary, points


def explain_rules(doc: Document, today: date | None = None) -> Explanation:
    today = today or date.today()
    norm = normalize(doc.text)
    kind = doc.doc_type or ""
    summary, points = _summary(doc, kind, _who(doc.issuer))
    actions: list[Action] = []
    auto_debit = bool(re.search(DIRECT_DEBIT, norm))

    if doc.due_date and doc.amount and kind not in NO_PAYMENT:
        if auto_debit:
            points.append(T("direct_debit", date=doc.due_date))
        else:
            actions.append(Action(label=T("pay", amount=doc.amount), due_date=doc.due_date))
    if re.search(REMINDER, norm):
        actions.insert(0, Action(label=T("settle")))
        points.append(T("fees"))
    if re.search(SEND_BACK, norm):
        actions.append(Action(label=T("send_back"), due_date=_first_date_after(norm, SEND_BACK)))
    if re.search(SUMMONS, norm):
        actions.append(Action(label=T("attend"), due_date=_first_date_after(norm, SUMMONS)))
    renew = deadlines.renew_from(doc)
    if renew and renew <= today and doc.superseded_by is None:
        if f"renew_{kind}" in T.keys:
            label = T(f"renew_{kind}")
        else:
            label = T("renew_certificate") if kind in CERTIFICATES else T("renew")
        actions.append(Action(label=label, due_date=doc.expiry_date))
    if doc.reference:
        points.append(T("reference", reference=doc.reference))
    if not actions:
        summary += T("nothing_to_do")
    return Explanation(
        summary=summary,
        action_required=bool(actions),
        actions=actions,
        key_points=points[:3],
        language=i18n.current_language(),
    )


def explain_llm(doc: Document) -> Explanation | None:
    facts = {
        "title": doc.title,
        "issuer": doc.issuer,
        "amount": doc.amount,
        "due_date": doc.due_date and doc.due_date.isoformat(),
        "expiry_date": doc.expiry_date and doc.expiry_date.isoformat(),
    }
    prompt = PROMPT.format(
        today=date.today().isoformat(),
        facts=llm.dumps(facts),
        text=llm.compact(doc.text),
        **llm.user_context(),
    )
    try:
        message = llm.chat([{"role": "user", "content": prompt}], fmt=SCHEMA)
        data = json.loads(message.get("content") or "{}")
        explanation = Explanation.model_validate(
            {**data, "engine": "llm", "language": i18n.current_language()}
        )
        explanation.action_required = explanation.action_required or bool(explanation.actions)
        return explanation
    except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError):
        log.exception("Explanation by the model failed, falling back to rules")
        return None


def explain(doc: Document) -> Explanation:
    if doc.text.strip() and llm.is_available():
        explanation = explain_llm(doc)
        if explanation:
            return explanation
    return explain_rules(doc)


def cached(doc: Document) -> Explanation | None:
    """The cached explanation, if it is written in the current language."""
    if not doc.explanation:
        return None
    try:
        explanation = Explanation.model_validate_json(doc.explanation)
    except ValidationError:
        return None
    return explanation if explanation.language == i18n.current_language() else None


def get(session: Session, doc: Document, *, refresh: bool = False) -> Explanation:
    """Cached explanation, recomputed (and cached) when missing, stale or in another language.

    Adds the document to the session without committing.
    """
    explanation = None if refresh else cached(doc)
    if explanation is None:
        explanation = explain(doc)
        doc.explanation = explanation.model_dump_json()
        session.add(doc)
    return explanation
