"""Letters written for the user, complete and ready to send, then followed until answered.

Any letter can be asked for in plain words ("ask the CAF to pay the overpayment in
instalments"): the local model writes the body from the related document; without a model, the
closest template (termination, complaint, request, or a generic letter) is used. The sender
(name, address) and the recipient's address come from the documents themselves; only what
Binder really cannot know stays between square brackets.

A letter is saved (Correspondence) as soon as it is written: it can be downloaded as a PDF,
marked as sent, and Binder then suggests a follow-up letter if no answer came in time.

A letter is written in the language of the administration it is sent to, which is not
necessarily the interface language: French for France, Belgium, Luxembourg and Monaco
(`i18n.letter_language`), otherwise the interface language.
"""

import html
import json
import logging
import re
from datetime import date, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from binder import i18n
from binder.models import Category, Correspondence, Deadline, Document
from binder.schemas import Letter as Letter  # re-exported: letters.Letter
from binder.services import activity, household, llm, settings_store, undo
from binder.services.rules import normalize
from binder.services.text import html_to_pdf

log = logging.getLogger(__name__)

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
        # Letter described in words, without a model.
        "custom_intro": {
            "en": "I am writing to you in order to {purpose}.",
            "fr": "Je me permets de vous écrire afin de {purpose}.",
        },
        "custom_documents": {
            "en": "Please find enclosed the relevant supporting documents.",
            "fr": "Vous trouverez ci-joint les justificatifs utiles.",
        },
        "custom_reply": {
            "en": "I look forward to your reply.",
            "fr": "Dans l'attente de votre réponse,",
        },
        # Follow-up.
        "followup_subject": {"en": "Reminder: {subject}", "fr": "Relance : {subject}"},
        "followup_intro": {
            "en": "On {sent:date}, I sent you a letter regarding “{subject}”, to which I have "
            "not yet received a reply.",
            "fr": "Le {sent:date}, je vous ai adressé un courrier concernant « {subject} », "
            "resté à ce jour sans réponse.",
        },
        "followup_ask": {
            "en": "I would be grateful if you could deal with my request as soon as possible. "
            "Please find a copy of my letter enclosed.",
            "fr": "Je vous remercie de bien vouloir traiter ma demande dans les meilleurs délais. "
            "Vous trouverez ci-joint une copie de mon courrier.",
        },
        "followup_deadline": {
            "en": "Follow up {recipient} if no answer",
            "fr": "Relancer {recipient} sans réponse",
        },
        "sent": {
            "en": "Letter to {recipient} marked as sent",
            "fr": "Courrier à {recipient} marqué comme envoyé",
        },
        "answered": {
            "en": "Letter to {recipient} answered",
            "fr": "Courrier à {recipient} : réponse reçue",
        },
        "to_complete": {"en": "[to be completed]", "fr": "[à compléter]"},
        "enclosures": {"en": "Enclosure: {what}", "fr": "Pièce jointe : {what}"},
    },
)

# Days before suggesting a follow-up: registered letters get a month.
FOLLOW_UP_DAYS = 21
FOLLOW_UP_REGISTERED = 30
BLANK = re.compile(r"\[[^\]\n]{2,80}\]")

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


def profile_for(session: Session) -> Profile:
    """The sender: what the user saved, completed with what the documents say (the member
    named on most documents, the address written on most of them)."""
    profile = settings_store.load(session, PROFILE_KEY, Profile)
    if not profile.name:
        profile.name = household.main_person(session) or ""
    if not profile.address:
        home = household.home_address(session)
        if home:
            profile.address = f"{home[0]}\n{home[1]}"
            profile.city = profile.city or home[1].split(" ", 1)[-1]
    return profile


def recipient_address(doc: Document | None, profile: Profile) -> str:
    """The issuer's address, as written in its document (not the household's)."""
    if doc is None:
        return ""
    own = normalize(profile.address)
    for street, town in household.addresses_in(doc.text):
        if normalize(street) not in own:
            return f"{street}\n{town}"
    return ""


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


def _custom(doc: Document | None, details: str) -> tuple[str, list[str], bool]:
    purpose = details or T("request_placeholder")
    purpose = purpose[:1].lower() + purpose[1:]
    subject = details[:1].upper() + details[1:80] if details else T("request_subject")
    paragraphs = [T("custom_intro", purpose=purpose.rstrip(".")), T("custom_documents")]
    paragraphs.append(T("custom_reply"))
    return subject.rstrip("."), paragraphs, False


BUILDERS = {
    "termination": _cancellation,
    "complaint": _complaint,
    "request": _request,
    "custom": _custom,
}


def letter_language() -> i18n.Language:
    return i18n.letter_language(i18n.current_country(), i18n.current_language())


def write(
    kind: str,
    doc: Document | None,
    profile: Profile,
    details: str = "",
    address: str = "",
) -> Letter:
    language = letter_language()
    with i18n.using(language):
        subject, paragraphs, registered = BUILDERS[kind](doc, details.strip())
        return layout(kind, doc, profile, subject, paragraphs, registered, language, address)


def layout(
    kind: str,
    doc: Document | None,
    profile: Profile,
    subject: str,
    paragraphs: list[str],
    registered: bool,
    language: i18n.Language,
    address: str = "",
    recipient: str | None = None,
) -> Letter:
    """The whole letter around its body: sender, recipient, place and date, subject, greeting,
    closing and signature."""
    with i18n.using(language):
        return _layout(
            kind, doc, profile, subject, paragraphs, registered, language, address, recipient
        )


def _layout(
    kind: str,
    doc: Document | None,
    profile: Profile,
    subject: str,
    paragraphs: list[str],
    registered: bool,
    language: i18n.Language,
    address: str,
    recipient: str | None,
) -> Letter:
    recipient = recipient or (doc.issuer if doc and doc.issuer else T("placeholder_recipient"))
    lines = [
        *_sender(profile),
        "",
        recipient,
        *(address.splitlines() or [T("customer_service"), T("placeholder_recipient_address")]),
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
    body = "\n".join(lines)
    return Letter(
        kind=kind,
        subject=subject,
        recipient=recipient,
        recipient_address=address,
        body=body,
        registered=registered,
        language=language,
        document_id=doc.id if doc else None,
        blanks=len(BLANK.findall(body)),
    )


def written_msg(letter: Letter) -> i18n.Msg:
    """Activity log entry for a drafted letter (the subject stays in the letter's language)."""
    return T.msg("written", subject=letter.subject.lower(), recipient=letter.recipient)


# --- Letters described in words ----------------------------------------------------------

COMPOSE_PROMPT = """Write the body of a formal letter, in {language}, from a private person to \
an organisation. Today: {today}. Country: {country}.
What the letter must do: {purpose}
{document}
Return JSON: subject (short, no "Subject:"), recipient (organisation name), paragraphs (2 to 5 \
paragraphs of the body only: no address, date, greeting, closing formula or signature), \
registered (true for a termination, a dispute or a formal notice).
Use only the facts given; for a fact you do not have (a date, a figure), write \
{blank}. Plain, firm and polite; cite references and amounts exactly."""
COMPOSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "recipient": {"type": "string"},
        "paragraphs": {"type": "array", "items": {"type": "string"}},
        "registered": {"type": "boolean"},
    },
    "required": ["subject", "recipient", "paragraphs", "registered"],
}


class _Composed(BaseModel):
    subject: str
    recipient: str
    paragraphs: list[str]
    registered: bool = False


# Template chosen without a model, from the words of the request.
_KIND_WORDS = [
    ("termination", r"resili|mettre fin|arreter mon|cancel|terminat|end my"),
    ("complaint", r"contest|reclam|dispute|complain|erreur|error|double|trop[ -]percu"),
]


def guess_kind(purpose: str) -> str:
    norm = normalize(purpose)
    return next((kind for kind, words in _KIND_WORDS if re.search(words, norm)), "custom")


def _compose_llm(purpose: str, doc: Document | None, language: i18n.Language) -> _Composed | None:
    facts = ""
    if doc is not None:
        fields = {
            "title": doc.title,
            "issuer": doc.issuer,
            "reference": doc.reference,
            "amount": doc.amount,
            "issue_date": doc.issue_date,
            "due_date": doc.due_date,
        }
        facts = f'Related document: {llm.dumps(i18n.jsonable(fields))}\n"""\n'
        facts += llm.compact(doc.text, 2500) + '\n"""'
    with i18n.using(language):
        blank = T("to_complete")
    prompt = COMPOSE_PROMPT.format(
        language=i18n.language_name(language),
        today=date.today().isoformat(),
        country=llm.user_context()["country"],
        purpose=purpose,
        document=facts,
        blank=blank,
    )
    try:
        message = llm.chat([{"role": "user", "content": prompt}], fmt=COMPOSE_SCHEMA)
        composed = _Composed.model_validate(json.loads(message.get("content") or "{}"))
    except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError):
        log.exception("Letter by the model failed, falling back to a template")
        return None
    composed.paragraphs = [p.strip() for p in composed.paragraphs if p.strip()]
    return composed if composed.paragraphs and composed.subject.strip() else None


def compose(
    session: Session,
    purpose: str = "",
    doc: Document | None = None,
    *,
    kind: str | None = None,
    actor: str = "user",
) -> Letter:
    """Writes, saves and logs a complete letter. `kind`: a template; otherwise the letter is
    written from `purpose` (by the model when available)."""
    profile = profile_for(session)
    address = recipient_address(doc, profile)
    language = letter_language()
    composed = None
    if kind is None and purpose.strip() and llm.is_available():
        composed = _compose_llm(purpose.strip(), doc, language)
    if composed is not None:
        letter = layout(
            "custom",
            doc,
            profile,
            composed.subject.strip(),
            composed.paragraphs,
            composed.registered,
            language,
            address,
            recipient=(doc.issuer if doc and doc.issuer else composed.recipient.strip()) or None,
        )
    else:
        kind = kind or guess_kind(purpose)
        details = purpose if kind in ("custom", "complaint") else ""
        letter = write(kind, doc, profile, details, address)
    return save(session, letter, actor=actor)


def save(session: Session, letter: Letter, *, actor: str = "user") -> Letter:
    row = Correspondence(
        document_id=letter.document_id,
        kind=letter.kind,
        subject=letter.subject,
        recipient=letter.recipient,
        recipient_address=letter.recipient_address,
        body=letter.body,
        language=letter.language,
        registered=letter.registered,
    )
    session.add(row)
    session.flush()
    undo.push("row_created", model="Correspondence", id=row.id)
    activity.log(
        session, "letter", written_msg(letter), actor=actor, document_id=letter.document_id
    )
    return out(row)


def out(row: Correspondence) -> Letter:
    return Letter(
        id=row.id,
        kind=row.kind,
        subject=row.subject,
        recipient=row.recipient,
        recipient_address=row.recipient_address,
        body=row.body,
        registered=row.registered,
        language="fr" if row.language == "fr" else "en",
        document_id=row.document_id,
        sent_on=row.sent_on,
        follow_up_on=row.follow_up_on,
        answered=row.answered,
        blanks=len(BLANK.findall(row.body)),
    )


def mark_sent(session: Session, row: Correspondence, *, actor: str = "user") -> None:
    """Sent today: a follow-up reminder is planned in case no answer comes."""
    undo.row_changed(row)
    row.sent_on = date.today()
    days = FOLLOW_UP_REGISTERED if row.registered else FOLLOW_UP_DAYS
    row.follow_up_on = row.sent_on + timedelta(days=days)
    session.add(row)
    deadline = Deadline(
        document_id=row.document_id,
        title=T("followup_deadline", recipient=row.recipient),
        due_date=row.follow_up_on,
        source="followup",
    )
    session.add(deadline)
    session.flush()
    undo.push("deadline_created", id=deadline.id)
    activity.log(
        session,
        "letter",
        T.msg("sent", recipient=row.recipient),
        actor=actor,
        document_id=row.document_id,
    )


def mark_answered(session: Session, row: Correspondence, *, actor: str = "user") -> None:
    undo.row_changed(row)
    row.answered = True
    session.add(row)
    for deadline in _followup_deadlines(session, row):
        undo.push("deadline", id=deadline.id, state=undo.deadline_state(deadline))
        deadline.done = True
        session.add(deadline)
    activity.log(
        session,
        "letter",
        T.msg("answered", recipient=row.recipient),
        actor=actor,
        document_id=row.document_id,
    )


def _followup_deadlines(session: Session, row: Correspondence) -> list[Deadline]:
    from sqlmodel import select

    title = T("followup_deadline", recipient=row.recipient)
    return list(
        session.exec(
            select(Deadline).where(
                Deadline.source == "followup",
                Deadline.done == False,  # noqa: E712
                Deadline.title == title,
                Deadline.due_date == row.follow_up_on,
            )
        )
    )


def follow_up(session: Session, row: Correspondence, *, actor: str = "user") -> Letter:
    """A reminder letter for a letter that got no answer."""
    assert row.sent_on is not None
    profile = profile_for(session)
    doc = session.get(Document, row.document_id) if row.document_id else None
    language: i18n.Language = "fr" if row.language == "fr" else "en"
    with i18n.using(language):
        subject = T("followup_subject", subject=row.subject)
        paragraphs = [T("followup_intro", sent=row.sent_on, subject=row.subject)]
        paragraphs.append(T("followup_ask"))
    letter = layout(
        "followup",
        doc,
        profile,
        subject,
        paragraphs,
        True,
        language,
        row.recipient_address,
        recipient=row.recipient,
    )
    saved = save(session, letter, actor=actor)
    if saved.id is not None:
        followup = session.get(Correspondence, saved.id)
        if followup is not None:
            followup.follows = row.id
            session.add(followup)
    return saved


# --- PDF -------------------------------------------------------------------------------------

PDF_CSS = """
* { font-family: sans-serif; font-size: 10.5pt; line-height: 1.45; color: #111827; }
p { margin: 0 0 9pt 0; }
.right { margin-left: 52%; }
.subject { font-weight: bold; }
.blank { background-color: #fef3c7; }
"""


def pdf(row: Correspondence) -> bytes:
    """The letter as an A4 PDF: sender top left, recipient and date on the right."""
    blocks = row.body.split("\n\n")
    parts = []
    for i, block in enumerate(blocks):
        text = "<br>".join(html.escape(line) for line in block.splitlines())
        text = BLANK.sub(lambda m: f'<span class="blank">{m[0]}</span>', text)
        css = "right" if i in (1, 2) else ""
        if block.startswith(("Objet", "Subject")):
            css = "subject"
        parts.append(f'<p class="{css}">{text}</p>')
    return html_to_pdf("".join(parts), PDF_CSS)


def file_name(row: Correspondence) -> str:
    when = (row.sent_on or row.created_at.date()).isoformat()
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", f"{when} {row.subject} {row.recipient}")
    return re.sub(r"\s+", " ", name).strip()[:120] + ".pdf"
