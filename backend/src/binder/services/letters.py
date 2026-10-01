"""Courriers types préremplis : résiliation, réclamation, demande de document.

Le texte est construit par modèles (pas par le LLM) : un courrier qui engage doit dire
exactement ce que l'on veut. Ce qui n'est pas connu reste entre crochets, à compléter.
"""

from datetime import date

from pydantic import BaseModel

from binder.models import Category, Document
from binder.services import activity
from binder.services.rules import normalize

KINDS = {
    "resiliation": "Résiliation d'un contrat ou d'un abonnement",
    "reclamation": "Réclamation ou contestation d'une facture",
    "demande": "Demande de document (attestation, duplicata…)",
}


class Profile(BaseModel):
    name: str = ""
    address: str = ""
    city: str = ""
    email: str = ""
    phone: str = ""


class Letter(BaseModel):
    kind: str
    subject: str
    recipient: str
    body: str
    # Envoi conseillé en recommandé avec accusé de réception.
    registered: bool


def _sender(profile: Profile) -> list[str]:
    lines = [profile.name or "[Prénom Nom]"]
    lines += (profile.address or "[Adresse]\n[Code postal Ville]").splitlines()
    lines += [x for x in (profile.email, profile.phone) if x]
    return lines


def _references(doc: Document | None) -> list[str]:
    if doc is None:
        return ["Référence client / contrat : [à compléter]"]
    refs = [f"Référence : {doc.reference}" if doc.reference else "Référence : [à compléter]"]
    if doc.issue_date:
        refs.append(f"Document du {doc.issue_date:%d/%m/%Y} ({doc.title})")
    return refs


def _cancellation(doc: Document | None, details: str) -> tuple[str, list[str], bool]:
    what = "mon contrat" if doc is None or doc.category == Category.ASSURANCE else "mon abonnement"
    paragraphs = [
        f"Par la présente, je vous informe de ma décision de résilier {what} référencé ci-dessus.",
    ]
    # Résiliation infra-annuelle (loi Hamon) : assurances habitation et automobile seulement.
    insured = doc is not None and doc.category == Category.ASSURANCE
    if (
        insured
        and doc is not None
        and any(w in normalize(doc.text) for w in ("habitation", "assurance auto", "vehicule"))
    ):
        paragraphs.append(
            "Mon contrat ayant plus d'un an, je fais usage de la faculté de résiliation à tout "
            "moment prévue par l'article L113-15-2 du Code des assurances ; la résiliation "
            "prendra effet un mois après réception de ce courrier."
        )
    else:
        paragraphs.append(
            "Je vous remercie de bien vouloir en prendre acte dans les meilleurs délais, ou à "
            "l'issue du préavis prévu par mes conditions générales."
        )
    if details:
        paragraphs.append(details)
    paragraphs.append(
        "Je vous prie de m'adresser une confirmation écrite de cette résiliation, ainsi que, le "
        "cas échéant, le remboursement des sommes versées pour la période non couverte."
    )
    return f"Résiliation de {what}", paragraphs, True


def _complaint(doc: Document | None, details: str) -> tuple[str, list[str], bool]:
    target = "la facture référencée ci-dessus"
    if doc is not None and doc.amount is not None:
        target += f", d'un montant de {activity.display(doc.amount)}"
    paragraphs = [
        f"Je me permets de vous contacter au sujet de {target}, que je conteste.",
        details
        or "[Expliquez ici ce qui ne va pas : montant inattendu, prestation non "
        "fournie, double facturation…]",
        "Je vous remercie de bien vouloir examiner ma réclamation et de procéder à la "
        "rectification nécessaire.",
        "À défaut de réponse satisfaisante sous un mois, je me réserve la possibilité de saisir "
        "le médiateur compétent.",
    ]
    return "Réclamation concernant une facture", paragraphs, False


def _request(doc: Document | None, details: str) -> tuple[str, list[str], bool]:
    wanted = details or "[précisez le document : attestation, duplicata de facture, relevé…]"
    paragraphs = [
        f"Je vous serais reconnaissant(e) de bien vouloir me transmettre le document suivant : "
        f"{wanted}.",
        "Vous pouvez me l'adresser par courrier ou par e-mail aux coordonnées ci-dessus.",
    ]
    return "Demande de document", paragraphs, False


BUILDERS = {"resiliation": _cancellation, "reclamation": _complaint, "demande": _request}


def write(kind: str, doc: Document | None, profile: Profile, details: str = "") -> Letter:
    subject, paragraphs, registered = BUILDERS[kind](doc, details.strip())
    recipient = doc.issuer if doc and doc.issuer else "[Nom de l'organisme]"
    place = profile.city or "[Ville]"
    lines = [
        *_sender(profile),
        "",
        recipient,
        "Service clients",
        "[Adresse de l'organisme]",
        "",
        f"À {place}, le {date.today():%d/%m/%Y}",
        "",
        f"Objet : {subject}",
        *_references(doc),
    ]
    if registered:
        lines.append("Lettre recommandée avec accusé de réception")
    lines += ["", "Madame, Monsieur,", ""]
    for p in paragraphs:
        lines += [p, ""]
    lines += [
        "Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.",
        "",
        profile.name or "[Prénom Nom]",
    ]
    return Letter(
        kind=kind,
        subject=subject,
        recipient=recipient,
        body="\n".join(lines),
        registered=registered,
    )
