"""The Today feed: everything that needs the user, as cards with one-tap actions.

Sources: the recovery code to write down, import reports, the weekly briefing, questions about
uncertain documents, deadlines, renewals, anomalies, missing documents, letters to send or
follow up, and proactive suggestions (sort out old papers, compare an insurance before it
renews). Every action runs through `act`, which the routes wrap in an undo capture.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import WITHOUT_TEXT
from binder.models import Category, Correspondence, Deadline, DocType, Document
from binder.services import (
    activity,
    anomalies,
    areas,
    backup,
    briefing,
    deadlines,
    editing,
    household,
    ingest,
    letters,
    missing,
    questions,
    reports,
    retention,
    settings_store,
    undo,
)

T = i18n.catalog(
    "feed",
    {
        "recovery_title": {
            "en": "Write down your recovery code",
            "fr": "Notez votre code de récupération",
        },
        "recovery_detail": {
            "en": "Binder backs up your documents every day, encrypted. With this code, a backup "
            "opens on any computer. Keep it on paper, away from this computer.",
            "fr": "Binder sauvegarde vos documents chaque jour, chiffrés. Avec ce code, une "
            "sauvegarde s'ouvre sur n'importe quel ordinateur. Gardez-le sur papier, loin de cet "
            "ordinateur.",
        },
        "recovery_done": {"en": "I wrote it down", "fr": "Je l'ai noté"},
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
        "ask_for_it": {"en": "Ask for it", "fr": "Le demander"},
        "not_needed": {"en": "Not needed", "fr": "Pas besoin"},
        "sort_title_one": {
            "en": "{n} document can go",
            "fr": "{n} document peut partir",
        },
        "sort_title_other": {
            "en": "{n} documents can go",
            "fr": "{n} documents peuvent partir",
        },
        "sort_detail": {
            "en": "Past their retention period, or replaced by a newer version: {titles}.",
            "fr": "Durée de conservation dépassée, ou remplacés par une version plus récente : "
            "{titles}.",
        },
        "sort_action": {"en": "Move to the trash", "fr": "Mettre à la corbeille"},
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
        "act_paid": {"en": "“{title}” marked as paid", "fr": "« {title} » marqué comme payé"},
        "act_answered": {"en": "Answer saved", "fr": "Réponse enregistrée"},
        "act_trashed_one": {
            "en": "{n} document moved to the trash",
            "fr": "{n} document mis à la corbeille",
        },
        "act_trashed_other": {
            "en": "{n} documents moved to the trash",
            "fr": "{n} documents mis à la corbeille",
        },
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
    },
)

Tone = Literal["urgent", "soon", "info"]
DISMISSED_KEY = "feed.dismissed"
SOON = 7
RENEWAL_WINDOW = 45
DRAFT_WINDOW = 14
TONE_RANK = {"urgent": 0, "soon": 1, "info": 2}
# Actions run by the server; the others are handled by the interface (open, agent, upload…).
SERVER_ACTIONS = {
    "answer", "mark_paid", "trash_many", "letter", "letter_sent", "letter_answered",
    "follow_up", "dismiss", "confirm_recovery", "remind", "mark_seen",
}  # fmt: skip


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
    # Kind-specific data: recovery code, import batch, briefing figures…
    extra: dict[str, Any] = {}


class Dismissed(BaseModel):
    keys: list[str] = []


def _dismiss_action(key: str, label: str | None = None) -> Action:
    return Action(type="dismiss", label=label or T("ok"), params={"key": key})


def _open(doc_id: int, label: str | None = None) -> Action:
    return Action(type="open", label=label or T("open"), params={"url": f"/documents/{doc_id}"})


def _recovery(session: Session) -> list[FeedItem]:
    state = backup.state(session)
    if state.confirmed or not state.code:
        return []
    return [
        FeedItem(
            key="recovery",
            kind="recovery",
            tone="info",
            title=T("recovery_title"),
            detail=T("recovery_detail"),
            actions=[Action(type="confirm_recovery", label=T("recovery_done"), primary=True)],
            extra={"code": state.code},
        )
    ]


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


def _questions(session: Session) -> list[FeedItem]:
    items = []
    for q in questions.pending(session):
        actions = []
        for choice in q.choices:
            if choice.id == "open":
                opened = _open(q.document_id, choice.label)
                actions.append(opened.model_copy(update={"primary": choice.primary}))
            else:
                actions.append(
                    Action(
                        type="answer",
                        label=choice.label,
                        primary=choice.primary,
                        params={"document_id": q.document_id, "choice": choice.id},
                    )
                )
        items.append(
            FeedItem(
                key=q.key,
                kind="question",
                tone="soon",
                title=q.title,
                detail=q.detail,
                category=q.category,
                area=areas.BY_CATEGORY.get(q.category),
                document_ids=[q.document_id],
                actions=actions,
            )
        )
    return items


def _when_label(d: Deadline, today: date) -> str:
    days = (d.due_date - today).days
    if days < 0:
        return T("overdue_one") if days == -1 else T("overdue", days=-days)
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
    items = []
    for d in rows:
        assert d.id is not None
        doc = session.get(Document, d.document_id) if d.document_id else None
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
        .where(col(Document.deleted_at).is_(None), col(Document.expiry_date).is_not(None))
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
        doc = session.get(Document, a.document_ids[-1]) if a.document_ids else None
        actions = []
        if a.letter:
            actions.append(
                Action(
                    type="letter",
                    label=T("write_letter"),
                    primary=True,
                    params={"purpose": a.letter, "document_id": a.document_ids[-1]},
                )
            )
        if a.document_ids:
            actions.append(_open(a.document_ids[-1]))
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


def _missing(session: Session) -> list[FeedItem]:
    items = []
    for m in missing.detect(session):
        actions = [Action(type="upload", label=T("add_it"), primary=not m.letter)]
        if m.letter:
            actions.insert(
                0,
                Action(
                    type="letter",
                    label=T("ask_for_it"),
                    primary=True,
                    params={
                        "purpose": m.letter,
                        "document_id": m.document_ids[-1] if m.document_ids else None,
                    },
                ),
            )
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
            )
        )
    return items


def _sort_out(session: Session) -> list[FeedItem]:
    docs = [
        d
        for d in session.exec(
            select(Document).options(*WITHOUT_TEXT).where(col(Document.deleted_at).is_(None))
        )
        if retention.deletion_reason(d)
    ]
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
                    type="trash_many", label=T("sort_action"), primary=True, params={"ids": ids}
                ),
                _dismiss_action(key, T("not_needed")),
            ],
        )
    ]


def _renewals(session: Session, today: date) -> list[FeedItem]:
    docs = session.exec(
        select(Document)
        .options(*WITHOUT_TEXT)
        .where(col(Document.deleted_at).is_(None), Document.category == Category.INSURANCE)
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
        reply = _reply(session, row)
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


def _reply(session: Session, row: Correspondence) -> Document | None:
    """A document from the letter's recipient that arrived after it was sent."""
    if row.sent_on is None:
        return None
    from binder.services.rules import normalize

    who = normalize(row.recipient)
    docs = session.exec(
        select(Document)
        .options(*WITHOUT_TEXT)
        .where(col(Document.deleted_at).is_(None), col(Document.issuer).is_not(None))
        .where(col(Document.created_at) >= datetime.combine(row.sent_on, time.min, UTC))
        .order_by(col(Document.created_at))
    ).all()
    return next((d for d in docs if normalize(d.issuer or "") == who), None)


def _household(session: Session) -> list[FeedItem]:
    members = household.members(session)
    full = [m for m in members if len(m.name.split()) >= 2]
    if len(full) < 2:
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
            actions=[_dismiss_action(key)],
            extra={"members": [m.model_dump() for m in members]},
        )
    ]


def build(session: Session, today: date | None = None) -> list[FeedItem]:
    today = today or date.today()
    dismissed = set(settings_store.load(session, DISMISSED_KEY, Dismissed).keys)
    lead = _recovery(session) + _reports(session) + _briefing(session)
    rest = (
        _questions(session)
        + _deadlines(session, today)
        + _expirations(session, today)
        + _anomalies(session)
        + _letters(session, today)
        + _missing(session)
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


def _int(params: dict[str, Any], name: str) -> int:
    try:
        return int(params[name])
    except (KeyError, TypeError, ValueError) as e:
        raise BadAction(name) from e


def _doc(session: Session, doc_id: int) -> Document:
    doc = session.get(Document, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise BadAction("document")
    return doc


def _letter_row(session: Session, params: dict[str, Any]) -> Correspondence:
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


def act(session: Session, kind: str, params: dict[str, Any], *, actor: str = "user") -> ActResult:
    """Runs a server action of a feed card. Does not commit."""
    if kind == "answer":
        doc = _doc(session, _int(params, "document_id"))
        try:
            questions.answer(session, doc, str(params.get("choice", "")))
        except questions.UnknownChoice as e:
            raise BadAction("choice") from e
        return ActResult(message=T("act_answered"))
    if kind == "mark_paid":
        deadline = session.get(Deadline, _int(params, "deadline_id"))
        if deadline is None:
            raise BadAction("deadline")
        editing.update_deadline(session, deadline, {"done": True}, actor=actor)
        return ActResult(message=T("act_paid", title=deadline.title))
    if kind == "trash_many":
        count = 0
        for raw in params.get("ids") or []:
            old = session.get(Document, int(raw))
            reason = retention.deletion_msg(old, inline=True) if old else None
            if old is None or old.deleted_at is not None or reason is None:
                continue
            ingest.trash(session, old, actor=actor, reason=reason)
            count += 1
        return ActResult(message=T.plural("act_trashed", count))
    if kind == "letter":
        doc_id = params.get("document_id")
        related = _doc(session, int(doc_id)) if doc_id else None
        letter_kind = params.get("kind")
        if letter_kind is not None and letter_kind not in letters.KINDS:
            raise BadAction("kind")
        letter = letters.compose(
            session, str(params.get("purpose") or ""), related, kind=letter_kind, actor=actor
        )
        return ActResult(message=T("act_letter"), letter=letter)
    if kind == "letter_sent":
        row = _letter_row(session, params)
        letters.mark_sent(session, row, actor=actor)
        assert row.follow_up_on is not None
        return ActResult(message=T("act_sent", date=row.follow_up_on))
    if kind == "letter_answered":
        letters.mark_answered(session, _letter_row(session, params), actor=actor)
        return ActResult(message=T("act_answered"))
    if kind == "follow_up":
        letter = letters.follow_up(session, _letter_row(session, params), actor=actor)
        return ActResult(message=T("act_letter"), letter=letter)
    if kind == "dismiss":
        dismiss(session, str(params.get("key") or ""))
        return ActResult(message=T("act_dismissed"))
    if kind == "mark_seen":
        reports.mark_seen(session, str(params.get("batch") or ""))
        return ActResult(message=T("act_dismissed"))
    if kind == "confirm_recovery":
        backup.confirm(session)
        return ActResult(message=T("act_recovery"))
    if kind == "remind":
        try:
            when = date.fromisoformat(str(params.get("due_date")))
        except ValueError as e:
            raise BadAction("due_date") from e
        doc_id = params.get("document_id")
        related = _doc(session, int(doc_id)) if doc_id else None
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
    raise BadAction(kind)
