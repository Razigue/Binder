"""Prefilled letter templates: termination, complaint, document request.

The text is built from templates (not by the LLM): a binding letter must say exactly what the
user means. Whatever is unknown stays between square brackets, to be completed.

A letter is written in the language of the administration it is sent to, which is not
necessarily the interface language: French for France, Belgium, Luxembourg and Monaco
(`i18n.letter_language`), otherwise the interface language.
"""

from datetime import date

from pydantic import BaseModel

from binder import i18n
from binder.models import Category, Document
from binder.schemas import Letter as Letter  # re-exported: letters.Letter
from binder.services.rules import normalize

T = i18n.catalog(
    "letters",
    {
        # Kind titles, shown in the interface (interface language).
        "kind_termination": {
            "en": "Termination of a contract or subscription",
            "fr": "Résiliation d'un contrat ou d'un abonnement",
        },
        "kind_complaint": {
            "en": "Complaint or invoice dispute",
            "fr": "Réclamation ou contestation d'une facture",
        },
        "kind_request": {
            "en": "Document request (certificate, duplicate…)",
            "fr": "Demande de document (attestation, duplicata…)",
        },
        "written": {
            "en": "Letter drafted: {subject} ({recipient})",
            "fr": "Courrier rédigé : {subject} ({recipient})",
        },
        # Letter layout.
        "placeholder_name": {"en": "[First and last name]", "fr": "[Prénom Nom]"},
        "placeholder_address": {
            "en": "[Address]\n[Postcode and town]",
            "fr": "[Adresse]\n[Code postal Ville]",
        },
        "placeholder_recipient": {"en": "[Organisation name]", "fr": "[Nom de l'organisme]"},
        "placeholder_recipient_address": {
            "en": "[Organisation address]",
            "fr": "[Adresse de l'organisme]",
        },
        "placeholder_city": {"en": "[Town]", "fr": "[Ville]"},
        "customer_service": {"en": "Customer Service", "fr": "Service clients"},
        "place_date": {"en": "{place}, {today:date}", "fr": "À {place}, le {today:date}"},
        "subject_line": {"en": "Subject: {subject}", "fr": "Objet : {subject}"},
        "reference_unknown": {
            "en": "Customer / contract reference: [to be completed]",
            "fr": "Référence client / contrat : [à compléter]",
        },
        "reference": {"en": "Reference: {reference}", "fr": "Référence : {reference}"},
        "reference_missing": {
            "en": "Reference: [to be completed]",
            "fr": "Référence : [à compléter]",
        },
        "document_of": {
            "en": "Document dated {issued:date} ({title})",
            "fr": "Document du {issued:date} ({title})",
        },
        "registered": {
            "en": "Sent by registered mail with acknowledgement of receipt",
            "fr": "Lettre recommandée avec accusé de réception",
        },
        "salutation": {"en": "Dear Sir or Madam,", "fr": "Madame, Monsieur,"},
        "closing": {
            "en": "Yours faithfully,",
            "fr": "Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations "
            "distinguées.",
        },
        # Termination.
        "my_contract": {"en": "my contract", "fr": "mon contrat"},
        "my_subscription": {"en": "my subscription", "fr": "mon abonnement"},
        "termination_subject": {"en": "Termination of {what}", "fr": "Résiliation de {what}"},
        "termination_notice": {
            "en": "I hereby notify you of my decision to terminate {what} referenced above.",
            "fr": "Par la présente, je vous informe de ma décision de résilier {what} référencé "
            "ci-dessus.",
        },
        # Only written in French letters to France: it cites French insurance law.
        "termination_hamon": {
            "en": "As my contract has been in force for more than one year, I am exercising the "
            "right to terminate it at any time provided by article L113-15-2 of the French "
            "Insurance Code; the termination will take effect one month after receipt of this "
            "letter.",
            "fr": "Mon contrat ayant plus d'un an, je fais usage de la faculté de résiliation à "
            "tout moment prévue par l'article L113-15-2 du Code des assurances ; la résiliation "
            "prendra effet un mois après réception de ce courrier.",
        },
        "termination_notice_period": {
            "en": "Please acknowledge this as soon as possible, or at the end of the notice "
            "period set out in my terms and conditions.",
            "fr": "Je vous remercie de bien vouloir en prendre acte dans les meilleurs délais, ou "
            "à l'issue du préavis prévu par mes conditions générales.",
        },
        "termination_confirmation": {
            "en": "Please send me written confirmation of this termination and, where "
            "applicable, a refund of any amounts paid for the period not covered.",
            "fr": "Je vous prie de m'adresser une confirmation écrite de cette résiliation, ainsi "
            "que, le cas échéant, le remboursement des sommes versées pour la période non "
            "couverte.",
        },
        # Complaint.
        "complaint_subject": {
            "en": "Complaint regarding an invoice",
            "fr": "Réclamation concernant une facture",
        },
        "complaint_target": {
            "en": "the invoice referenced above",
            "fr": "la facture référencée ci-dessus",
        },
        "complaint_target_amount": {
            "en": "the invoice referenced above, for an amount of {amount:money}",
            "fr": "la facture référencée ci-dessus, d'un montant de {amount:money}",
        },
        "complaint_intro": {
            "en": "I am writing to you regarding {target}, which I dispute.",
            "fr": "Je me permets de vous contacter au sujet de {target}, que je conteste.",
        },
        "complaint_details": {
            "en": "[Explain here what is wrong: unexpected amount, service not provided, "
            "double billing…]",
            "fr": "[Expliquez ici ce qui ne va pas : montant inattendu, prestation non fournie, "
            "double facturation…]",
        },
        "complaint_review": {
            "en": "I would be grateful if you could look into my complaint and make the "
            "necessary correction.",
            "fr": "Je vous remercie de bien vouloir examiner ma réclamation et de procéder à la "
            "rectification nécessaire.",
        },
        "complaint_mediator": {
            "en": "Should I not receive a satisfactory reply within one month, I reserve the "
            "right to refer the matter to the relevant ombudsman.",
            "fr": "À défaut de réponse satisfaisante sous un mois, je me réserve la possibilité "
            "de saisir le médiateur compétent.",
        },
        # Document request.
        "request_subject": {"en": "Request for a document", "fr": "Demande de document"},
        "request_placeholder": {
            "en": "[specify the document: certificate, duplicate invoice, statement…]",
            "fr": "[précisez le document : attestation, duplicata de facture, relevé…]",
        },
        "request_intro": {
            "en": "I would be grateful if you could send me the following document: {wanted}.",
            "fr": "Je vous serais reconnaissant(e) de bien vouloir me transmettre le document "
            "suivant : {wanted}.",
        },
        "request_delivery": {
            "en": "You may send it to me by post or by email using the contact details above.",
            "fr": "Vous pouvez me l'adresser par courrier ou par e-mail aux coordonnées ci-dessus.",
        },
    },
)

# Setting holding the sender's details.
PROFILE_KEY = "profile"
# Stable identifiers of the letter kinds (API values).
KINDS = ("termination", "complaint", "request")


def kind_titles() -> dict[str, str]:
    """{kind: title} in the interface language."""
    return {kind: T(f"kind_{kind}") for kind in KINDS}


class Profile(BaseModel):
    name: str = ""
    address: str = ""
    city: str = ""
    email: str = ""
    phone: str = ""


def _sender(profile: Profile) -> list[str]:
    lines = [profile.name or T("placeholder_name")]
    lines += (profile.address or T("placeholder_address")).splitlines()
    lines += [x for x in (profile.email, profile.phone) if x]
    return lines


def _references(doc: Document | None) -> list[str]:
    if doc is None:
        return [T("reference_unknown")]
    refs = [T("reference", reference=doc.reference) if doc.reference else T("reference_missing")]
    if doc.issue_date:
        refs.append(T("document_of", issued=doc.issue_date, title=doc.title))
    return refs


def _cancellation(doc: Document | None, details: str) -> tuple[str, list[str], bool]:
    insured = doc is not None and doc.category == Category.INSURANCE
    what = T("my_contract") if doc is None or insured else T("my_subscription")
    paragraphs = [T("termination_notice", what=what)]
    # Termination at any time after one year (French "loi Hamon"): home and car insurance only,
    # and only meaningful for a French insurer.
    hamon = (
        insured
        and doc is not None
        and i18n.current_language() == "fr"
        and (i18n.current_country() or "FR").upper() == "FR"
        and any(w in normalize(doc.text) for w in ("habitation", "assurance auto", "vehicule"))
    )
    paragraphs.append(T("termination_hamon") if hamon else T("termination_notice_period"))
    if details:
        paragraphs.append(details)
    paragraphs.append(T("termination_confirmation"))
    return T("termination_subject", what=what), paragraphs, True


def _complaint(doc: Document | None, details: str) -> tuple[str, list[str], bool]:
    if doc is not None and doc.amount is not None:
        target = T("complaint_target_amount", amount=doc.amount)
    else:
        target = T("complaint_target")
    paragraphs = [
        T("complaint_intro", target=target),
        details or T("complaint_details"),
        T("complaint_review"),
        T("complaint_mediator"),
    ]
    return T("complaint_subject"), paragraphs, False


def _request(doc: Document | None, details: str) -> tuple[str, list[str], bool]:
    wanted = details or T("request_placeholder")
    paragraphs = [T("request_intro", wanted=wanted), T("request_delivery")]
    return T("request_subject"), paragraphs, False


BUILDERS = {"termination": _cancellation, "complaint": _complaint, "request": _request}


def write(kind: str, doc: Document | None, profile: Profile, details: str = "") -> Letter:
    language = i18n.letter_language(i18n.current_country(), i18n.current_language())
    with i18n.using(language):
        return _write(kind, doc, profile, details.strip(), language)


def _write(
    kind: str, doc: Document | None, profile: Profile, details: str, language: i18n.Language
) -> Letter:
    subject, paragraphs, registered = BUILDERS[kind](doc, details)
    recipient = doc.issuer if doc and doc.issuer else T("placeholder_recipient")
    lines = [
        *_sender(profile),
        "",
        recipient,
        T("customer_service"),
        T("placeholder_recipient_address"),
        "",
        T("place_date", place=profile.city or T("placeholder_city"), today=date.today()),
        "",
        T("subject_line", subject=subject),
        *_references(doc),
    ]
    if registered:
        lines.append(T("registered"))
    lines += ["", T("salutation"), ""]
    for p in paragraphs:
        lines += [p, ""]
    lines += [T("closing"), "", profile.name or T("placeholder_name")]
    return Letter(
        kind=kind,
        subject=subject,
        recipient=recipient,
        body="\n".join(lines),
        registered=registered,
        language=language,
    )


def written_msg(letter: Letter) -> i18n.Msg:
    """Activity log entry for a drafted letter (the subject stays in the letter's language)."""
    return T.msg("written", subject=letter.subject.lower(), recipient=letter.recipient)
