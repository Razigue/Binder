"""« Qu'est-ce que c'est, et dois-je faire quelque chose ? » en langage simple.

Le modèle local rédige l'explication quand il est disponible ; sinon, des règles décrivent
le document à partir de son type, de ses informations extraites et de quelques tournures
du courrier (relance, pièces à renvoyer, convocation). Le résultat est mis en cache sur le
document et recalculé quand ses informations changent.
"""

import json
import logging
import re
from datetime import date

import httpx
from pydantic import BaseModel, ValidationError

from binder.models import Document
from binder.services import activity, deadlines, llm
from binder.services.rules import find_dates, normalize

log = logging.getLogger(__name__)


class Action(BaseModel):
    label: str
    due_date: date | None = None


class Explanation(BaseModel):
    summary: str
    action_required: bool
    actions: list[Action] = []
    key_points: list[str] = []
    engine: str = "rules"


PROMPT = """Tu expliques un courrier administratif français à quelqu'un qui n'aime pas la
paperasse. Réponds uniquement en JSON avec :
- summary : 2 ou 3 phrases simples, sans jargon : qui écrit, pourquoi, ce que ça implique
- action_required : true seulement si la personne doit faire quelque chose (payer, répondre,
  renvoyer un document, se présenter, renouveler). Un prélèvement automatique ou un simple
  justificatif ne demande pas d'action.
- actions : liste de {{"label": "...", "due_date": "AAAA-MM-JJ" ou null}}, vide si rien à faire
- key_points : 0 à 3 informations utiles (montant, référence à rappeler, conséquence d'un oubli)
N'invente rien qui ne soit pas dans le courrier. Nous sommes le {today}.

Informations déjà extraites : {facts}

Courrier :
\"\"\"
{text}
\"\"\"
"""

REMINDER = r"mise en demeure|relance|impaye|dernier rappel|majoration|penalite|retard de paiement"
SEND_BACK = (
    r"a (?:nous )?(?:retourner|renvoyer)|merci de (?:nous )?(?:retourner|renvoyer|transmettre)"
    r"|a completer|signer et (?:retourner|renvoyer)|pieces? justificatives?|nous faire parvenir"
)
SUMMONS = r"convocation|vous etes convoque|rendez-vous (?:le|fixe)"
DIRECT_DEBIT = r"prelev|mensualis"


RENEWAL = {
    "Carte d'identité": "Prendre rendez-vous en mairie pour la renouveler",
    "Passeport": "Prendre rendez-vous en mairie pour le renouveler",
    "Titre de séjour": "Demander le renouvellement à la préfecture",
    "Permis de conduire": "Demander le renouvellement sur le site de l'ANTS",
    "Contrôle technique": "Prendre rendez-vous pour le prochain contrôle technique",
}


def _of(name: str) -> str:
    """« d'EDF », « de MAIF » : élision devant une voyelle."""
    return f" d'{name}" if normalize(name[:1]) in "aeiouyh" else f" de {name}"


def _amount(value: float | None) -> str:
    return activity.display(value) if value is not None else ""


def _when(d: date | None) -> str:
    return f"le {d.strftime('%d/%m/%Y')}" if d else ""


def _first_date_after(norm: str, pattern: str) -> date | None:
    m = re.search(pattern, norm)
    if not m:
        return None
    dates = find_dates(norm[m.start() : m.start() + 160])
    return dates[0] if dates else None


def explain_rules(doc: Document, today: date | None = None) -> Explanation:
    today = today or date.today()
    norm = normalize(doc.text)
    kind = doc.doc_type or ""
    who = _of(doc.issuer) if doc.issuer else ""
    amount = _amount(doc.amount)
    actions: list[Action] = []
    points: list[str] = []
    auto_debit = bool(re.search(DIRECT_DEBIT, norm))

    if kind in {"Taxe foncière", "Taxe d'habitation", "Avis d'imposition"}:
        subject = "sur le revenu" if kind == "Avis d'imposition" else f"({kind.lower()})"
        summary = f"C'est un avis d'impôt {subject} envoyé par l'administration fiscale."
        if amount:
            summary += f" Le montant à payer est de {amount}."
    elif kind == "Facture":
        summary = f"C'est une facture{who}" + (f" d'un montant de {amount}." if amount else ".")
    elif kind == "Avis d'échéance":
        summary = (
            f"C'est l'avis de renouvellement de votre contrat{who} : il se reconduit et la "
            f"cotisation de la nouvelle période est de {amount or 'montant non lu'}."
        )
    elif kind == "Quittance de loyer":
        summary = "C'est une quittance : la preuve que votre loyer a bien été payé."
    elif kind.startswith("Attestation"):
        summary = (
            f"C'est une attestation{who}. Elle prouve votre situation (droits, couverture, "
            "paiement) et peut vous être demandée pour une démarche."
        )
    elif kind == "Relevé bancaire":
        summary = f"C'est un relevé de compte{who} qui liste vos opérations de la période."
        points.append("Vérifiez qu'aucune opération ne vous est inconnue.")
    elif kind == "Bulletin de paie":
        summary = "C'est votre fiche de paie" + (f" : {amount} net versé." if amount else ".")
        points.append("À conserver jusqu'à la retraite : elle sert au calcul de vos droits.")
    elif kind == "Décompte de remboursement":
        summary = "C'est le détail d'un remboursement de soins" + (
            f" : {amount} vous ont été versés." if amount else "."
        )
    elif kind == "Devis":
        summary = (
            f"C'est un devis{who}" + (f" de {amount}" if amount else "") + " : une proposition "
            "de prix. Rien n'est dû tant que vous ne l'avez pas accepté."
        )
    elif kind in deadlines.NOTICE_DAYS or doc.expiry_date:
        summary = f"C'est votre {kind.lower() or 'document'}" + (
            f", valable jusqu'au {doc.expiry_date:%d/%m/%Y}." if doc.expiry_date else "."
        )
    else:
        summary = f"Document « {doc.title} »{who}, classé dans {doc.category.value}."

    if doc.due_date and doc.amount and kind not in {"Quittance de loyer", "Bulletin de paie"}:
        if auto_debit:
            points.append(
                f"Le montant sera prélevé automatiquement {_when(doc.due_date)} : "
                "vérifiez simplement que votre compte est approvisionné."
            )
        else:
            actions.append(Action(label=f"Payer {amount}", due_date=doc.due_date))
    if re.search(REMINDER, norm):
        actions.insert(0, Action(label="Régulariser rapidement : c'est une relance"))
        points.append("Sans réponse, des frais ou majorations peuvent s'ajouter.")
    if re.search(SEND_BACK, norm):
        actions.append(
            Action(
                label="Renvoyer les documents ou informations demandés",
                due_date=_first_date_after(norm, SEND_BACK),
            )
        )
    if re.search(SUMMONS, norm):
        actions.append(
            Action(label="Se présenter au rendez-vous", due_date=_first_date_after(norm, SUMMONS))
        )
    renew = deadlines.renew_from(doc)
    if renew and renew <= today and doc.superseded_by is None:
        label = RENEWAL.get(kind) or (
            "Demander la nouvelle attestation" if kind.startswith("Attestation") else "Renouveler"
        )
        actions.append(Action(label=label, due_date=doc.expiry_date))
    if doc.reference:
        points.append(f"Référence à rappeler dans vos échanges : {doc.reference}.")
    if not actions:
        summary += " Vous n'avez rien à faire, à part le conserver."
    return Explanation(
        summary=summary, action_required=bool(actions), actions=actions, key_points=points[:3]
    )


def explain_llm(doc: Document) -> Explanation | None:
    facts = {
        "titre": doc.title,
        "emetteur": doc.issuer,
        "montant": doc.amount,
        "echeance": doc.due_date and doc.due_date.isoformat(),
        "fin_de_validite": doc.expiry_date and doc.expiry_date.isoformat(),
    }
    schema = Explanation.model_json_schema()
    schema["properties"].pop("engine", None)
    prompt = PROMPT.format(
        today=date.today().isoformat(),
        facts=json.dumps(facts, ensure_ascii=False),
        text=doc.text[: llm.MAX_CHARS],
    )
    try:
        message = llm.chat([{"role": "user", "content": prompt}], fmt=schema)
        data = json.loads(message.get("content") or "{}")
        explanation = Explanation.model_validate({**data, "engine": "llm"})
        explanation.action_required = explanation.action_required or bool(explanation.actions)
        return explanation
    except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError):
        log.exception("Explication par le modèle impossible, repli sur les règles")
        return None


def explain(doc: Document) -> Explanation:
    if doc.text.strip() and llm.is_available():
        explanation = explain_llm(doc)
        if explanation:
            return explanation
    return explain_rules(doc)
