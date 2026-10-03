"""The To do feed: everything that needs the user, as cards with one-tap actions.

Sources: import reports, the weekly briefing, questions about uncertain documents, deadlines,
renewals, anomalies, missing documents, letters to send or follow up, the next steps of the
journeys under way, documents waiting for the local AI, and proactive suggestions (archive old
papers, compare an insurance before it renews). Every action runs through `act`, which the
routes wrap in an undo capture.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT, in_use
from binder.models import (
    Category,
    Correspondence,
    Deadline,
    DocType,
    Document,
    DocumentStatus,
    Journey,
)
from binder.services import (
    activity,
    anomalies,
    archive,
    areas,
    backup,
    briefing,
    deadlines,
    editing,
    household,
    journeys,
    letters,
    missing,
    questions,
    reports,
    rights,
    settings_store,
    undo,
)
from binder.services.rules import normalize

T = i18n.catalog(
    "feed",
    {
        "report_upload_one": {"en": "{n} document added", "fr": "{n} document ajouté"},
        "report_upload_other": {"en": "{n} documents added", "fr": "{n} documents ajoutés"},
        "report_mail_one": {
            "en": "{n} document received by email",
            "fr": "{n} document reçu par e-mail",
        },
        "report_mail_other": {
            "en": "{n} documents received by email",
            "fr": "{n} documents reçus par e-mail",
        },
        "report_folder_one": {
            "en": "{n} document from the watched folder",
            "fr": "{n} document du dossier surveillé",
        },
        "report_folder_other": {
            "en": "{n} documents from the watched folder",
            "fr": "{n} documents du dossier surveillé",
        },
        "report_scan_one": {"en": "{n} document scanned", "fr": "{n} document scanné"},
        "report_scan_other": {"en": "{n} documents scanned", "fr": "{n} documents scannés"},
        "report_demo_one": {"en": "{n} demo document", "fr": "{n} document de démonstration"},
        "report_demo_other": {
            "en": "{n} demo documents",
            "fr": "{n} documents de démonstration",
        },
        "see_report": {"en": "See what Binder did", "fr": "Voir ce que Binder a fait"},
        "ok": {"en": "OK", "fr": "OK"},
        "overdue": {
            "en": "{days} days late",
            "fr": "En retard de {days} jours",
        },
        "overdue_one": {"en": "1 day late", "fr": "En retard d'un jour"},
        "due_today": {"en": "Due today", "fr": "À payer aujourd'hui"},
        "due_in": {"en": "Due {date:date}", "fr": "À payer avant le {date:date}"},
        "reminder_on": {"en": "On {date:date}", "fr": "Le {date:date}"},
        "paid": {"en": "It's paid", "fr": "C'est payé"},
        "done": {"en": "Done", "fr": "C'est fait"},
        "open": {"en": "Open", "fr": "Ouvrir"},
        "renew_title": {"en": "{title}: renew it", "fr": "{title} : à renouveler"},
        "expired_title": {"en": "{title}: expired", "fr": "{title} : expiré"},
        "renew_detail": {
            "en": "Valid until {date:date}. Start now: appointments can take weeks.",
            "fr": "Valable jusqu'au {date:date}. Commencez maintenant : les rendez-vous "
            "prennent parfois des semaines.",
        },
        "expired_detail": {
            "en": "Ended on {date:date}.",
            "fr": "A pris fin le {date:date}.",
        },
        "how_to_renew": {"en": "How do I renew it?", "fr": "Comment le renouveler ?"},
        "how_to_renew_prompt": {
            "en": "How do I renew “{title}” [#{id}]?",
            "fr": "Comment renouveler « {title} » [#{id}] ?",
        },
        "remind_later": {"en": "Remind me in 2 weeks", "fr": "Me le rappeler dans 2 semaines"},
        "remind_title": {"en": "Renew: {title}", "fr": "Renouveler : {title}"},
        "write_letter": {"en": "Write the letter", "fr": "Écrire le courrier"},
        "all_good": {"en": "All good", "fr": "Tout va bien"},
        "add_it": {"en": "Add it", "fr": "L'ajouter"},
        "fetch_on": {"en": "Get it on {site}", "fr": "Le récupérer sur {site}"},
        "explain": {"en": "Explain", "fr": "M'expliquer"},
        "ask_for_it": {"en": "Ask for it", "fr": "Le demander"},
        "not_needed": {"en": "Not needed", "fr": "Pas besoin"},
        "sort_title_one": {
            "en": "{n} old document can go to the archives",
            "fr": "{n} ancien document peut aller aux archives",
        },
        "sort_title_other": {
            "en": "{n} old documents can go to the archives",
            "fr": "{n} anciens documents peuvent aller aux archives",
        },
        "sort_detail": {
            "en": "Past their retention period, or replaced by a newer version: {titles}. "
            "Nothing is deleted: they stay readable in the archives.",
            "fr": "Durée de conservation dépassée, ou remplacés par une version plus récente : "
            "{titles}. Rien n'est supprimé : ils restent consultables dans les archives.",
        },
        "sort_action": {"en": "Archive them", "fr": "Les archiver"},
        "renewal_title": {
            "en": "{issuer} contract renews on {date:date}",
            "fr": "Le contrat {issuer} se renouvelle le {date:date}",
        },
        "renewal_detail": {
            "en": "{amount} for the new year. Compare before: after one year, you can end it "
            "at any time.",
            "fr": "{amount} pour la nouvelle année. Comparez avant : après un an, vous pouvez le "
            "résilier à tout moment.",
        },
        "renewal_action": {"en": "Write a termination", "fr": "Écrire une résiliation"},
        "draft_title": {
            "en": "Letter to {recipient} ready",
            "fr": "Courrier à {recipient} prêt",
        },
        "draft_detail": {
            "en": "“{subject}”. Download it, sign it, send it, then tell Binder: it will follow "
            "it up.",
            "fr": "« {subject} ». Téléchargez-le, signez-le, envoyez-le, puis dites-le à Binder : "
            "il en assurera le suivi.",
        },
        "download_pdf": {"en": "Download (PDF)", "fr": "Télécharger (PDF)"},
        "sent": {"en": "I sent it", "fr": "Je l'ai envoyé"},
        "followup_title": {
            "en": "No answer from {recipient}?",
            "fr": "Pas de réponse de {recipient} ?",
        },
        "followup_detail": {
            "en": "Your letter “{subject}” was sent on {date:date}.",
            "fr": "Votre courrier « {subject} » est parti le {date:date}.",
        },
        "write_followup": {"en": "Write a reminder", "fr": "Écrire une relance"},
        "answered": {"en": "I got an answer", "fr": "J'ai eu une réponse"},
        "reply_title": {
            "en": "Is this {recipient}'s answer?",
            "fr": "Est-ce la réponse de {recipient} ?",
        },
        "reply_detail": {
            "en": "“{title}” arrived after your letter of {date:date}.",
            "fr": "« {title} » est arrivé après votre courrier du {date:date}.",
        },
        "yes_answer": {"en": "Yes", "fr": "Oui"},
        "household_title": {
            "en": "Binder recognised your household",
            "fr": "Binder a reconnu votre foyer",
        },
        "household_detail": {
            "en": "{names}. Each document is linked to the person it concerns.",
            "fr": "{names}. Chaque document est rattaché à la personne qu'il concerne.",
        },
        "household_fix": {"en": "Correct", "fr": "Corriger"},
        "act_paid": {"en": "“{title}” marked as paid", "fr": "« {title} » marqué comme payé"},
        "act_answered": {"en": "Answer saved", "fr": "Réponse enregistrée"},
        "act_archived_one": {"en": "{n} document archived", "fr": "{n} document archivé"},
        "act_archived_other": {"en": "{n} documents archived", "fr": "{n} documents archivés"},
        "act_dismissed": {"en": "Hidden", "fr": "Masqué"},
        "act_letter": {"en": "Letter ready", "fr": "Courrier prêt"},
        "act_sent": {
            "en": "Noted: Binder will remind you to follow it up on {date:date}",
            "fr": "C'est noté : Binder vous proposera une relance le {date:date}",
        },
        "act_reminder": {
            "en": "Reminder set for {date:date}",
            "fr": "Rappel prévu le {date:date}",
        },
        "act_recovery": {
            "en": "Code noted. Binder no longer shows it.",
            "fr": "Code noté. Binder ne l'affiche plus.",
        },
        "list_separator": {"en": ", ", "fr": ", "},
        "step_due_in": {"en": "By {date:date}", "fr": "Avant le {date:date}"},
        "step_today": {"en": "Today", "fr": "Aujourd'hui"},
        "journey_detail": {"en": "{journey} · {when}", "fr": "{journey} · {when}"},
        "see_steps": {"en": "See the steps", "fr": "Voir les étapes"},
        "act_step": {"en": "Done: {title}", "fr": "C'est fait : {title}"},
        "more_questions_one": {
            "en": "{n} more question, whenever you like",
            "fr": "{n} autre question, quand vous voulez",
        },
        "more_questions_other": {
            "en": "{n} more questions, whenever you like",
            "fr": "{n} autres questions, quand vous voulez",
        },
        "more_questions_detail_one": {
            "en": "About {n} document. Nothing urgent: Binder has filed it meanwhile.",
            "fr": "Sur {n} document. Rien d'urgent : Binder l'a rangé en attendant.",
        },
        "more_questions_detail_other": {
            "en": "About {n} documents. Nothing urgent: Binder has filed them meanwhile.",
            "fr": "Sur {n} documents. Rien d'urgent : Binder les a rangés en attendant.",
        },
        "sort_now": {"en": "Answer them", "fr": "Y répondre"},
        "act_answered_many_one": {
            "en": "Answer saved for {n} document",
            "fr": "Réponse enregistrée pour {n} document",
        },
        "act_answered_many_other": {
            "en": "Answer saved for {n} documents",
            "fr": "Réponse enregistrée pour {n} documents",
        },
        "waiting_title_one": {
            "en": "{n} document is waiting for the local AI",
            "fr": "{n} document attend l'IA locale",
        },
        "waiting_title_other": {
            "en": "{n} documents are waiting for the local AI",
            "fr": "{n} documents attendent l'IA locale",
        },
        "waiting_detail": {
            "en": "They are kept safe. Binder reads and files them as soon as the AI is ready.",
            "fr": "Ils sont en sécurité. Binder les lira et les rangera dès que l'IA sera prête.",
        },
    },
)

Tone = Literal["urgent", "soon", "info"]
DISMISSED_KEY = "feed.dismissed"
SOON = 7
RENEWAL_WINDOW = 45
DRAFT_WINDOW = 14
TONE_RANK = {"urgent": 0, "soon": 1, "info": 2}


class Action(BaseModel):
    type: str
    label: str
    primary: bool = False
    params: dict[str, Any] = {}


class FeedItem(BaseModel):
    key: str
    kind: str
    tone: Tone
    title: str
    detail: str = ""
    area: str | None = None
    category: Category | None = None
    amount: float | None = None
    when: date | None = None
    document_ids: list[int] = []
    actions: list[Action] = []
    # Kind-specific data: import batch, briefing figures…
    extra: dict[str, Any] = {}


class Dismissed(BaseModel):
    keys: list[str] = []


def _dismiss_action(key: str, label: str | None = None) -> Action:
    return Action(type="dismiss", label=label or T("ok"), params={"key": key})


def _open(doc_id: int, label: str | None = None) -> Action:
    return Action(type="open", label=label or T("open"), params={"url": f"/documents/{doc_id}"})


def _reports(session: Session) -> list[FeedItem]:
    items = []
    for batch in reports.latest_unseen(session):
        report = reports.build(session, batch)
        if report is None or report.processing == len(report.items):
            continue
        source = report.source if report.source in ("mail", "folder", "scan", "demo") else "upload"
        items.append(
            FeedItem(
                key=f"report:{batch}",
                kind="report",
                tone="info",
                title=T.plural(f"report_{source}", len(report.items)),
                detail=report.summary,
                document_ids=[i.document.id for i in report.items],
                actions=[
                    Action(
                        type="report", label=T("see_report"), primary=True, params={"batch": batch}
                    ),
                    Action(type="mark_seen", label=T("ok"), params={"batch": batch}),
                ],
                extra={"batch": batch},
            )
        )
    return items


def _briefing(session: Session) -> list[FeedItem]:
    current = briefing.current(session)
    if current is None:
        return []
    return [
        FeedItem(
            key=f"briefing:{current.week}",
            kind="briefing",
            tone="info",
            title=current.title,
            detail=current.text,
            amount=current.to_pay or None,
            actions=[_dismiss_action(f"briefing:{current.week}")],
            extra={"figures": current.figures},
        )
    ]


def question_item(q: questions.Question) -> FeedItem:
    """A question as a card: its answers as buttons; "open" and "detail" show the documents
    next to the question (the interface's question panel)."""
    actions = []
    for choice in q.choices:
        if choice.id in ("open", "detail"):
            actions.append(
                Action(
                    type="ask",
                    label=choice.label,
                    primary=choice.primary,
                    params={"document_ids": q.document_ids, "key": q.key},
                )
            )
        else:
            actions.append(
                Action(
                    type="answer",
                    label=choice.label,
                    primary=choice.primary,
                    params={"document_ids": q.document_ids, "choice": choice.id},
                )
            )
    return FeedItem(
        key=q.key,
        kind="question",
        tone="soon",
        title=q.title,
        detail=q.detail,
        category=q.category,
        area=areas.BY_CATEGORY.get(q.category),
        when=q.when,
        document_ids=q.document_ids,
        actions=actions,
        extra={"field": q.field, "question": q.kind},
    )


def _questions(session: Session) -> list[FeedItem]:
    """A few questions, the most useful first; the others wait for a sorting session."""
    shown, rest = questions.visible(session)
    items = [question_item(q) for q in shown]
    if rest:
        count = sum(len(q.document_ids) for q in rest)
        items.append(
            FeedItem(
                key="questions:more",
                kind="questions",
                tone="info",
                title=T.plural("more_questions", len(rest)),
                detail=T.plural("more_questions_detail", count),
                document_ids=[],
                actions=[Action(type="triage", label=T("sort_now"), primary=True)],
                extra={"count": len(rest)},
            )
        )
    return items


def _overdue(days: int) -> str:
    return T("overdue_one") if days == 1 else T("overdue", days=days)


def _when_label(d: Deadline, today: date) -> str:
    days = (d.due_date - today).days
    if days < 0:
        return _overdue(-days)
    if d.source == "manual":
        return T("reminder_on", date=d.due_date)
    return T("due_today") if days == 0 else T("due_in", date=d.due_date)


def _deadlines(session: Session, today: date) -> list[FeedItem]:
    rows = session.exec(
        select(Deadline)
        .where(Deadline.done == False, Deadline.due_date <= today + timedelta(days=SOON))  # noqa: E712
        .where(col(Deadline.source).in_(["extracted", "manual"]))
        .order_by(col(Deadline.due_date))
    ).all()
    linked = {d.document_id for d in rows if d.document_id is not None}
    docs = {
        doc.id: doc
        for doc in session.exec(
            select(Document).options(*WITHOUT_TEXT).where(col(Document.id).in_(linked))
        )
    }
    items = []
    for d in rows:
        assert d.id is not None
        doc = docs.get(d.document_id) if d.document_id else None
        actions = [
            Action(
                type="mark_paid",
                label=T("paid") if d.amount else T("done"),
                primary=True,
                params={"deadline_id": d.id},
            )
        ]
        if doc is not None and doc.id is not None:
            actions.append(_open(doc.id))
        items.append(
            FeedItem(
                key=f"deadline:{d.id}",
                kind="deadline",
                tone="urgent" if d.due_date <= today + timedelta(days=2) else "soon",
                title=d.title,
                detail=_when_label(d, today),
                category=d.category,
                area=(doc.area if doc else None) or areas.BY_CATEGORY.get(d.category),
                amount=d.amount,
                when=d.due_date,
                document_ids=[doc.id] if doc and doc.id else [],
                actions=actions,
            )
        )
    return items


def _expirations(session: Session, today: date) -> list[FeedItem]:
    docs = session.exec(
        select(Document)
        .options(*WITHOUT_TEXT)
        .where(in_use(), col(Document.expiry_date).is_not(None))
        .where(col(Document.superseded_by).is_(None), col(Document.duplicate_of).is_(None))
    ).all()
    items = []
    for doc in docs:
        assert doc.expiry_date is not None and doc.id is not None
        renew = deadlines.renew_from(doc) or doc.expiry_date
        if renew > today:
            continue
        # Certificates past their date are "missing documents" (a new one is to get).
        if doc.doc_type == DocType.INSURANCE_CERTIFICATE:
            continue
        expired = doc.expiry_date < today
        items.append(
            FeedItem(
                key=f"expiry:{doc.id}:{doc.expiry_date.isoformat()}",
                kind="expiry",
                tone="urgent" if expired or (doc.expiry_date - today).days <= 30 else "soon",
                title=T("expired_title" if expired else "renew_title", title=doc.title),
                detail=T("expired_detail" if expired else "renew_detail", date=doc.expiry_date),
                category=doc.category,
                area=doc.area,
                when=doc.expiry_date,
                document_ids=[doc.id],
                actions=[
                    Action(
                        type="agent",
                        label=T("how_to_renew"),
                        primary=True,
                        params={"prompt": T("how_to_renew_prompt", title=doc.title, id=doc.id)},
                    ),
                    Action(
                        type="remind",
                        label=T("remind_later"),
                        params={
                            "title": T("remind_title", title=doc.title),
                            "due_date": (today + timedelta(days=14)).isoformat(),
                            "document_id": doc.id,
                        },
                    ),
                ],
            )
        )
    return items


def _anomalies(session: Session) -> list[FeedItem]:
    items = []
    for a in anomalies.detect(session):
        # The paper the card is about: the latest one, or for a payment made twice the bill
        # (first), whose sender the letter goes to, rather than the bank statement.
        lead = (
            None
            if not a.document_ids
            else a.document_ids[0]
            if a.kind == "double_payment"
            else a.document_ids[-1]
        )
        doc = session.get(Document, lead) if lead else None
        actions = []
        if a.letter:
            actions.append(
                Action(
                    type="letter",
                    label=T("write_letter"),
                    primary=True,
                    params={"purpose": a.letter, "document_id": lead},
                )
            )
        if lead:
            actions.append(_open(lead))
        actions.append(_dismiss_action(f"anomaly:{a.key}", T("all_good")))
        items.append(
            FeedItem(
                key=f"anomaly:{a.key}",
                kind="anomaly",
                tone="urgent" if a.kind == "overpayment_claim" else "soon",
                title=a.title,
                detail=a.detail,
                category=doc.category if doc else None,
                area=doc.area if doc else None,
                amount=a.amount,
                document_ids=a.document_ids,
                actions=actions,
            )
        )
    return items


def _link(url: str, label: str, primary: bool = True) -> Action:
    """Opens an official or customer website in the user's browser."""
    return Action(type="link", label=label, primary=primary, params={"url": url})


def _missing(session: Session) -> list[FeedItem]:
    items = []
    for m in missing.detect(session):
        # Downloading it from the online account comes first when Binder knows where it is.
        fetch = m.portal is not None
        actions = [Action(type="upload", label=T("add_it"), primary=not m.letter and not fetch)]
        if m.letter:
            actions.insert(
                0,
                Action(
                    type="letter",
                    label=T("ask_for_it"),
                    primary=not fetch,
                    params={
                        "purpose": m.letter,
                        "document_id": m.document_ids[-1] if m.document_ids else None,
                    },
                ),
            )
        if m.portal is not None:
            actions.insert(0, _link(m.portal.url, T("fetch_on", site=m.portal.name)))
        actions.append(_dismiss_action(f"missing:{m.key}", T("not_needed")))
        items.append(
            FeedItem(
                key=f"missing:{m.key}",
                kind="missing",
                tone="info",
                title=m.title,
                detail=m.detail,
                area=m.area,
                when=m.expected,
                document_ids=m.document_ids,
                actions=actions,
                extra={"portal": m.portal.model_dump()} if m.portal else {},
            )
        )
    return items


def _rights(session: Session, today: date) -> list[FeedItem]:
    """Rights to check and duties without a letter (prime d'activité, monthly update…)."""
    items = []
    for r in rights.detect(session, today):
        key = f"right:{r.key}"
        items.append(
            FeedItem(
                key=key,
                kind="right",
                tone=r.tone,
                title=r.title,
                detail=r.detail,
                area=r.area,
                when=r.when,
                actions=[
                    _link(r.link.url, r.link_label),
                    Action(type="agent", label=T("explain"), params={"prompt": r.prompt}),
                    _dismiss_action(key, r.dismiss_label),
                ],
                extra={"portal": r.link.model_dump()},
            )
        )
    return items


def _sort_out(session: Session) -> list[FeedItem]:
    """Old documents to archive: suggested, the user confirms."""
    docs = [d for d, _ in archive.suggestions(session)]
    if not docs:
        return []
    ids = sorted(d.id for d in docs if d.id is not None)
    titles = T("list_separator").join(d.title for d in docs[:3])
    if len(docs) > 3:
        titles += "…"
    key = f"sort:{'-'.join(map(str, ids))}"
    return [
        FeedItem(
            key=key,
            kind="suggestion",
            tone="info",
            title=T.plural("sort_title", len(docs)),
            detail=T("sort_detail", titles=titles),
            document_ids=ids,
            actions=[
                Action(
                    type="archive_many", label=T("sort_action"), primary=True, params={"ids": ids}
                ),
                _dismiss_action(key, T("not_needed")),
            ],
        )
    ]


def _renewals(session: Session, today: date) -> list[FeedItem]:
    docs = session.exec(
        select(Document)
        .options(*WITHOUT_TEXT)
        .where(in_use(), Document.category == Category.INSURANCE)
        .where(Document.doc_type == DocType.PAYMENT_NOTICE, col(Document.due_date).is_not(None))
    ).all()
    items = []
    for doc in docs:
        assert doc.due_date is not None and doc.id is not None
        if not today <= doc.due_date <= today + timedelta(days=RENEWAL_WINDOW):
            continue
        key = f"renewal:{doc.id}"
        items.append(
            FeedItem(
                key=key,
                kind="suggestion",
                tone="info",
                title=T("renewal_title", issuer=doc.issuer or doc.title, date=doc.due_date),
                detail=T(
                    "renewal_detail",
                    amount=i18n.format_money(doc.amount) if doc.amount else "—",
                ),
                category=doc.category,
                area=doc.area,
                amount=doc.amount,
                when=doc.due_date,
                document_ids=[doc.id],
                actions=[
                    Action(
                        type="letter",
                        label=T("renewal_action"),
                        params={"kind": "termination", "document_id": doc.id},
                    ),
                    _open(doc.id),
                    _dismiss_action(key, T("all_good")),
                ],
            )
        )
    return items


def _letters(session: Session, today: date) -> list[FeedItem]:
    items = []
    rows = session.exec(
        select(Correspondence)
        .where(Correspondence.answered == False)  # noqa: E712
        .order_by(col(Correspondence.created_at).desc())
        .limit(30)
    ).all()
    arrivals = _arrivals(session, [r.sent_on for r in rows if r.sent_on is not None])
    for row in rows:
        assert row.id is not None
        if row.sent_on is None:
            if (today - row.created_at.date()).days > DRAFT_WINDOW:
                continue
            key = f"draft:{row.id}"
            items.append(
                FeedItem(
                    key=key,
                    kind="letter",
                    tone="info",
                    title=T("draft_title", recipient=row.recipient),
                    detail=T("draft_detail", subject=row.subject),
                    document_ids=[row.document_id] if row.document_id else [],
                    actions=[
                        Action(
                            type="pdf",
                            label=T("download_pdf"),
                            primary=True,
                            params={"url": f"/api/letters/{row.id}/pdf"},
                        ),
                        Action(type="letter_sent", label=T("sent"), params={"letter_id": row.id}),
                        _dismiss_action(key, T("not_needed")),
                    ],
                    extra={"letter_id": row.id},
                )
            )
            continue
        reply = _reply(row, arrivals)
        if reply is not None and reply.id is not None:
            key = f"reply:{row.id}:{reply.id}"
            items.append(
                FeedItem(
                    key=key,
                    kind="letter",
                    tone="soon",
                    title=T("reply_title", recipient=row.recipient),
                    detail=T("reply_detail", title=reply.title, date=row.sent_on),
                    document_ids=[reply.id],
                    actions=[
                        Action(
                            type="letter_answered",
                            label=T("yes_answer"),
                            primary=True,
                            params={"letter_id": row.id},
                        ),
                        _open(reply.id),
                        _dismiss_action(key, T("not_needed")),
                    ],
                )
            )
        elif row.follow_up_on is not None and row.follow_up_on <= today:
            items.append(
                FeedItem(
                    key=f"followup:{row.id}",
                    kind="letter",
                    tone="soon",
                    title=T("followup_title", recipient=row.recipient),
                    detail=T("followup_detail", subject=row.subject, date=row.sent_on),
                    when=row.follow_up_on,
                    document_ids=[row.document_id] if row.document_id else [],
                    actions=[
                        Action(
                            type="follow_up",
                            label=T("write_followup"),
                            primary=True,
                            params={"letter_id": row.id},
                        ),
                        Action(
                            type="letter_answered",
                            label=T("answered"),
                            params={"letter_id": row.id},
                        ),
                    ],
                )
            )
    return items


def _arrivals(session: Session, sent: list[date]) -> list[Document]:
    """Documents with a sender added since the oldest letter sent, oldest first: read once for
    all the letters waiting for an answer."""
    if not sent:
        return []
    return list(
        session.exec(
            select(Document)
            .options(*WITHOUT_TEXT)
            .where(in_use(), col(Document.issuer).is_not(None))
            .where(col(Document.created_at) >= datetime.combine(min(sent), time.min, UTC))
            .order_by(col(Document.created_at))
        )
    )


def _reply(row: Correspondence, arrivals: list[Document]) -> Document | None:
    """A document from the letter's recipient that arrived after it was sent."""
    if row.sent_on is None:
        return None
    who = normalize(row.recipient)
    since = datetime.combine(row.sent_on, time.min)
    return next(
        (
            d
            for d in arrivals
            if d.created_at.replace(tzinfo=None) >= since and normalize(d.issuer or "") == who
        ),
        None,
    )


def _step_when(due: date, today: date) -> str:
    days = (due - today).days
    if days < 0:
        return _overdue(-days)
    return T("step_today") if days == 0 else T("step_due_in", date=due)


def _journeys(session: Session, today: date) -> list[FeedItem]:
    """The next steps of each journey under way, due within a week (or late): two at most per
    journey, the journey itself holds the rest."""
    items = []
    shown: dict[int, int] = {}
    for row, step in journeys.due_steps(session, today, SOON):
        assert row.id is not None and step.due is not None
        if shown.get(row.id, 0) >= 2:
            continue
        shown[row.id] = shown.get(row.id, 0) + 1
        items.append(
            FeedItem(
                key=f"journey:{row.id}:{step.key}:{row.event_date}",
                kind="journey",
                tone="urgent" if step.due <= today + timedelta(days=2) else "soon",
                title=step.title,
                detail=T(
                    "journey_detail",
                    journey=journeys.title(row),
                    when=_step_when(step.due, today),
                ),
                when=step.due,
                document_ids=step.document_ids,
                actions=[
                    Action(
                        type="journey",
                        label=T("see_steps"),
                        primary=True,
                        params={"journey_id": row.id},
                    ),
                    Action(
                        type="journey_step",
                        label=T("done"),
                        params={"journey_id": row.id, "step": step.key},
                    ),
                ],
                extra={"journey_id": row.id, "step": step.key},
            )
        )
    return items


def _waiting(session: Session) -> list[FeedItem]:
    ids = session.exec(
        select(Document.id).where(
            Document.status == DocumentStatus.WAITING, col(Document.deleted_at).is_(None)
        )
    ).all()
    if not ids:
        return []
    return [
        FeedItem(
            key=f"waiting:{len(ids)}",
            kind="waiting",
            tone="info",
            title=T.plural("waiting_title", len(ids)),
            detail=T("waiting_detail"),
            document_ids=[i for i in ids if i is not None],
        )
    ]


def _household(session: Session) -> list[FeedItem]:
    members = household.members(session)
    full = [m for m in members if len(m.name.split()) >= 2]
    # Once the user corrected the household, they have seen it: no card each time it changes.
    if len(full) < 2 or household.load_edits(session) != household.Edits():
        return []
    names = T("list_separator").join(m.name for m in full[:4])
    key = f"household:{'|'.join(sorted(m.name for m in full))}"
    return [
        FeedItem(
            key=key,
            kind="household",
            tone="info",
            title=T("household_title"),
            detail=T("household_detail", names=names),
            actions=[
                Action(
                    type="open",
                    label=T("household_fix"),
                    params={"url": "/settings?tab=you#household"},
                ),
                _dismiss_action(key),
            ],
            extra={"members": [m.model_dump() for m in members]},
        )
    ]


def build(session: Session, today: date | None = None) -> list[FeedItem]:
    today = today or date.today()
    dismissed = set(settings_store.load(session, DISMISSED_KEY, Dismissed).keys)
    lead = _reports(session) + _briefing(session) + _waiting(session)
    rest = (
        _questions(session)
        + _deadlines(session, today)
        + _journeys(session, today)
        + _expirations(session, today)
        + _anomalies(session)
        + _letters(session, today)
        + _missing(session)
        + _rights(session, today)
        + _renewals(session, today)
        + _sort_out(session)
        + _household(session)
    )
    rest.sort(key=lambda i: TONE_RANK[i.tone])
    return [i for i in lead + rest if i.key not in dismissed]


# --- Actions ---------------------------------------------------------------------------------


class ActResult(BaseModel):
    message: str
    letter: letters.Letter | None = None


class BadAction(ValueError):
    pass


type Params = dict[str, Any]


def _int(params: Params, name: str) -> int:
    try:
        return int(params[name])
    except (KeyError, TypeError, ValueError) as e:
        raise BadAction(name) from e


def _doc(session: Session, doc_id: int) -> Document:
    doc = session.get(Document, doc_id)
    if doc is None or doc.deleted_at is not None or doc.archived_at is not None:
        raise BadAction("document")
    return doc


def _related(session: Session, params: Params) -> Document | None:
    """The document an action is about, when it names one."""
    return _doc(session, _int(params, "document_id")) if params.get("document_id") else None


def _letter_row(session: Session, params: Params) -> Correspondence:
    row = session.get(Correspondence, _int(params, "letter_id"))
    if row is None:
        raise BadAction("letter")
    return row


def dismiss(session: Session, key: str) -> None:
    undo.setting_changed(session, DISMISSED_KEY)
    current = settings_store.load(session, DISMISSED_KEY, Dismissed)
    if key not in current.keys:
        current.keys = [*current.keys[-499:], key]
        settings_store.save(session, DISMISSED_KEY, current)


def _answer(session: Session, params: Params, actor: str) -> ActResult:
    raw = params.get("document_ids") or [params.get("document_id")]
    try:
        docs = [_doc(session, int(i)) for i in raw]
    except (TypeError, ValueError) as e:
        raise BadAction("document_ids") from e
    try:
        questions.answer_all(session, docs, str(params.get("choice", "")))
    except questions.UnknownChoice as e:
        raise BadAction("choice") from e
    if len(docs) > 1:
        return ActResult(message=T.plural("act_answered_many", len(docs)))
    return ActResult(message=T("act_answered"))


def _mark_paid(session: Session, params: Params, actor: str) -> ActResult:
    deadline = session.get(Deadline, _int(params, "deadline_id"))
    if deadline is None:
        raise BadAction("deadline")
    editing.update_deadline(session, deadline, {"done": True}, actor=actor)
    return ActResult(message=T("act_paid", title=deadline.title))


def _archive_many(session: Session, params: Params, actor: str) -> ActResult:
    try:
        ids = [int(raw) for raw in params.get("ids") or []]
    except (TypeError, ValueError) as e:
        raise BadAction("ids") from e
    count = 0
    for doc_id in ids:
        old = session.get(Document, doc_id)
        reason = archive.archivable(old) if old else None
        if old is not None and reason is not None:
            count += archive.archive(session, old, reason, actor=actor)
    return ActResult(message=T.plural("act_archived", count))


def _letter(session: Session, params: Params, actor: str) -> ActResult:
    related = _related(session, params)
    letter_kind = params.get("kind")
    if letter_kind is not None and letter_kind not in letters.KINDS:
        raise BadAction("kind")
    letter = letters.compose(
        session, str(params.get("purpose") or ""), related, kind=letter_kind, actor=actor
    )
    return ActResult(message=T("act_letter"), letter=letter)


def _letter_sent(session: Session, params: Params, actor: str) -> ActResult:
    row = _letter_row(session, params)
    letters.mark_sent(session, row, actor=actor)
    assert row.follow_up_on is not None
    return ActResult(message=T("act_sent", date=row.follow_up_on))


def _letter_answered(session: Session, params: Params, actor: str) -> ActResult:
    letters.mark_answered(session, _letter_row(session, params), actor=actor)
    return ActResult(message=T("act_answered"))


def _follow_up(session: Session, params: Params, actor: str) -> ActResult:
    letter = letters.follow_up(session, _letter_row(session, params), actor=actor)
    return ActResult(message=T("act_letter"), letter=letter)


def _dismiss(session: Session, params: Params, actor: str) -> ActResult:
    dismiss(session, str(params.get("key") or ""))
    return ActResult(message=T("act_dismissed"))


def _journey_step(session: Session, params: Params, actor: str) -> ActResult:
    journey = session.get(Journey, _int(params, "journey_id"))
    if journey is None:
        raise BadAction("journey")
    key = str(params.get("step") or "")
    try:
        step = journeys.set_step(session, journey, key, True, actor=actor)
    except journeys.UnknownStep as e:
        raise BadAction("step") from e
    return ActResult(message=T("act_step", title=step.title))


def _mark_seen(session: Session, params: Params, actor: str) -> ActResult:
    reports.mark_seen(session, str(params.get("batch") or ""))
    return ActResult(message=T("act_dismissed"))


def _confirm_recovery(session: Session, params: Params, actor: str) -> ActResult:
    backup.confirm(session)
    return ActResult(message=T("act_recovery"))


def _remind(session: Session, params: Params, actor: str) -> ActResult:
    try:
        when = date.fromisoformat(str(params.get("due_date")))
    except ValueError as e:
        raise BadAction("due_date") from e
    related = _related(session, params)
    reminder = Deadline(
        title=str(params.get("title") or "")[:200],
        due_date=when,
        source="manual",
        document_id=related.id if related else None,
        category=related.category if related else Category.OTHER,
    )
    session.add(reminder)
    session.flush()
    undo.push("deadline_created", id=reminder.id)
    activity.log(
        session,
        "reminder",
        T.msg("act_reminder", date=when),
        actor=actor,
        document_id=reminder.document_id,
    )
    return ActResult(message=T("act_reminder", date=when))


type Handler = Callable[[Session, Params, str], ActResult]

HANDLERS: dict[str, Handler] = {
    "answer": _answer,
    "mark_paid": _mark_paid,
    "archive_many": _archive_many,
    "letter": _letter,
    "letter_sent": _letter_sent,
    "letter_answered": _letter_answered,
    "follow_up": _follow_up,
    "dismiss": _dismiss,
    "journey_step": _journey_step,
    "mark_seen": _mark_seen,
    "confirm_recovery": _confirm_recovery,
    "remind": _remind,
}
# Actions run by the server; the others are handled by the interface (open, agent, upload…).
SERVER_ACTIONS = frozenset(HANDLERS)


def act(session: Session, kind: str, params: Params, *, actor: str = "user") -> ActResult:
    """Runs a server action of a feed card. Does not commit."""
    handler = HANDLERS.get(kind)
    if handler is None:
        raise BadAction(kind)
    return handler(session, params, actor)
