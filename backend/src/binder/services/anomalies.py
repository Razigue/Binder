"""Anomalies worth the user's attention: paid twice, catch-up bill, overpayment, price rise,
lower pay.

Each anomaly carries the documents it comes from and, when a letter would help, what that
letter should ask for: the user gets it written in one tap. Detection is deterministic (amounts,
dates and the words administrations use); the patterns match French documents.
"""

import re
from datetime import date, timedelta
from statistics import median
from typing import Literal

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.db import in_use
from binder.models import Category, DocType, Document
from binder.services import activity, subscriptions
from binder.services.deadlines import document_date
from binder.services.rules import normalize, parse_amount

T = i18n.catalog(
    "anomalies",
    {
        "double_title": {
            "en": "{issuer}: billed twice?",
            "fr": "{issuer} : facturé deux fois ?",
        },
        "double_detail": {
            "en": "Two bills of {amount:money}, of {first:date} and {second:date}. Check you did "
            "not pay twice.",
            "fr": "Deux factures de {amount:money}, du {first:date} et du {second:date}. "
            "Vérifiez que vous n'avez pas payé deux fois.",
        },
        "double_debit_title": {
            "en": "Debited twice: {label}",
            "fr": "Prélevé deux fois : {label}",
        },
        "double_debit_detail": {
            "en": "{amount:money} appears twice on your statement of {date:date}.",
            "fr": "{amount:money} apparaît deux fois sur votre relevé du {date:date}.",
        },
        "double_debit_bill": {
            "en": "{amount:money} appears twice on your statement of {date:date}, for one bill: "
            "“{bill}” of {bill_date:date}.",
            "fr": "{amount:money} apparaît deux fois sur votre relevé du {date:date}, pour une "
            "seule facture : « {bill} » du {bill_date:date}.",
        },
        "double_letter": {
            "en": "Ask for the refund of an amount of {amount:money} charged twice",
            "fr": "Demander le remboursement d'un montant de {amount:money} prélevé deux fois",
        },
        "double_letter_bills": {
            "en": "Ask for the refund of an amount of {amount:money} charged twice ({bills})",
            "fr": "Demander le remboursement d'un montant de {amount:money} prélevé deux fois "
            "({bills})",
        },
        "bill_ref": {"en": "bill {ref} of {date:date}", "fr": "facture {ref} du {date:date}"},
        "bill_of": {"en": "bill of {date:date}", "fr": "facture du {date:date}"},
        "and": {"en": " and ", "fr": " et "},
        "catch_up_title": {
            "en": "{issuer} catch-up bill: {amount:money}",
            "fr": "Régularisation {issuer} : {amount:money}",
        },
        "catch_up_detail": {
            "en": "Much higher than your usual {usual:money}. Check the meter reading; you can "
            "ask to pay it in instalments.",
            "fr": "Bien plus que vos {usual:money} habituels. Vérifiez le relevé de compteur ; "
            "vous pouvez demander à payer en plusieurs fois.",
        },
        "catch_up_detail_alone": {
            "en": "Check the meter reading; you can ask to pay it in instalments.",
            "fr": "Vérifiez le relevé de compteur ; vous pouvez demander à payer en plusieurs "
            "fois.",
        },
        "catch_up_letter": {
            "en": "Ask to pay the catch-up bill of {amount:money} in instalments",
            "fr": "Demander un échelonnement de la facture de régularisation de {amount:money}",
        },
        "claim_title": {
            "en": "{issuer} claims an overpayment",
            "fr": "{issuer} réclame un trop-perçu",
        },
        "claim_detail": {
            "en": "{amount:money} to pay back. You can dispute it within two months, or ask for "
            "instalments or a write-off.",
            "fr": "{amount:money} à rembourser. Vous pouvez le contester sous deux mois, ou "
            "demander un échelonnement ou une remise de dette.",
        },
        "claim_letter": {
            "en": "Dispute the overpayment of {amount:money}, or ask for instalments",
            "fr": "Contester le trop-perçu de {amount:money} ou demander un échelonnement",
        },
        "credit_title": {
            "en": "{issuer} owes you {amount:money}",
            "fr": "{issuer} vous doit {amount:money}",
        },
        "credit_detail": {
            "en": "A credit in your favour. If it is not refunded soon, ask for it.",
            "fr": "Un solde en votre faveur. S'il n'est pas remboursé rapidement, réclamez-le.",
        },
        "credit_letter": {
            "en": "Ask for the refund of the credit of {amount:money} in my favour",
            "fr": "Demander le remboursement du solde de {amount:money} en ma faveur",
        },
        "increase_title": {
            "en": "{label}: up {pct:.0f}%",
            "fr": "{label} : +{pct:.0f} %",
        },
        "increase_detail": {
            "en": "{last:money} instead of {previous:money}, about {yearly:money} more a year.",
            "fr": "{last:money} au lieu de {previous:money}, environ {yearly:money} de plus par "
            "an.",
        },
        "increase_letter": {
            "en": "Ask why the price rose from {previous:money} to {last:money}, and for a "
            "better offer",
            "fr": "Demander la raison de la hausse de {previous:money} à {last:money}, et une "
            "meilleure offre",
        },
        "pay_drop_title": {
            "en": "Lower pay: {amount:money}",
            "fr": "Salaire en baisse : {amount:money}",
        },
        "pay_drop_detail": {
            "en": "{pct:.0f}% below your usual {usual:money}. Check the absences or deductions "
            "on the payslip.",
            "fr": "{pct:.0f} % de moins que vos {usual:money} habituels. Vérifiez les absences "
            "ou retenues sur le bulletin.",
        },
        "logged": {"en": "Anomaly spotted: {title}", "fr": "Anomalie repérée : {title}"},
        "logged_with": {
            "en": "Anomaly spotted: {title} (with “{other}” of {date:date})",
            "fr": "Anomalie repérée : {title} (avec « {other} » du {date:date})",
        },
    },
)

Kind = Literal[
    "double_payment", "catch_up", "overpayment_claim", "credit", "price_increase", "pay_drop"
]
# Two bills of the same amount closer than this are suspicious (monthly bills are ~30 days).
DOUBLE_DAYS = 20
CATCH_UP_RATIO = 1.8
PAY_DROP = 0.15
LOOKBACK = timedelta(days=550)

_CATCH_UP = re.compile(r"regularisation|facture de solde|rattrapage")
_CLAIM = re.compile(r"trop[ -]percu|(?<![a-z])indu(?![a-z])|somme indument|a rembourser a la caf")
_CREDIT = re.compile(
    r"en votre faveur|a votre credit|nous vous rembourserons|vous sera rembourse|avoir de"
)
_AMOUNT = re.compile(r"(\d{1,3}(?:[  .]\d{3})+|\d+)[,.](\d{2})\s*(?:€|eur)")
_DEBIT = re.compile(
    r"(?:prlv|prelevement|cb|carte|paiement)\s+(?:sepa\s+)?([a-z][a-z0-9 .'&-]{1,30}?)\s*"
    r"-\s*(\d{1,3}(?:[  .]\d{3})+|\d+)[,.](\d{2})"
)
SUPPLIER_CATEGORIES = {Category.ENERGY, Category.TELECOM, Category.INSURANCE, Category.HOUSING}
CLAIM_CATEGORIES = {Category.SOCIAL, Category.HEALTH, Category.WORK, Category.TAXES}


class Anomaly(BaseModel):
    key: str
    kind: Kind
    title: str
    detail: str
    amount: float | None = None
    document_ids: list[int]
    # What a letter should ask for, written in one tap (None when a letter would not help).
    letter: str | None = None


def _amount_near(norm: str, match: re.Match[str], fallback: float | None) -> float | None:
    line_end = norm.find("\n", match.end())
    window = norm[match.start() : line_end if line_end > 0 else None]
    found = _AMOUNT.search(window) or _AMOUNT.search(norm[match.end() : match.end() + 200])
    return parse_amount(found[1], found[2]) if found else fallback


def _active(session: Session, today: date) -> list[Document]:
    """Documents in force dated within the look-back period."""
    docs = session.exec(select(Document).where(in_use(), col(Document.duplicate_of).is_(None)))
    return [d for d in docs if document_date(d) >= today - LOOKBACK]


def _bills(docs: list[Document]) -> list[Document]:
    return sorted(
        (
            d
            for d in docs
            if d.amount
            and d.issuer
            and d.doc_type in (DocType.INVOICE, DocType.PAYMENT_NOTICE)
            and d.superseded_by is None
        ),
        key=lambda d: (document_date(d), d.id or 0),
    )


def _letter_for(amount: float, bills: list[Document]) -> str:
    """The refund letter names the bills, so that the supplier finds the payments."""
    named = [
        T("bill_ref", ref=b.reference, date=document_date(b))
        if b.reference
        else T("bill_of", date=document_date(b))
        for b in bills
    ]
    return T("double_letter_bills", amount=amount, bills=T("and").join(named))


def _double_bills(docs: list[Document]) -> list[Anomaly]:
    found = []
    bills = _bills(docs)
    for i, a in enumerate(bills):
        for b in bills[i + 1 :]:
            gap = (document_date(b) - document_date(a)).days
            if gap > DOUBLE_DAYS:
                break
            if normalize(a.issuer or "") != normalize(b.issuer or "") or a.amount != b.amount:
                continue
            assert a.id is not None and b.id is not None and a.amount is not None
            found.append(
                Anomaly(
                    key=f"double:{a.id}:{b.id}",
                    kind="double_payment",
                    title=T("double_title", issuer=a.issuer),
                    detail=T(
                        "double_detail",
                        amount=a.amount,
                        first=document_date(a),
                        second=document_date(b),
                    ),
                    amount=a.amount,
                    document_ids=[a.id, b.id],
                    letter=_letter_for(a.amount, [a, b]),
                )
            )
    return found


def _bill_debited(
    bills: list[Document], label: str, amount: float, doc: Document
) -> Document | None:
    """The bill a debit line pays: same sender and amount, the closest in time to the
    statement."""
    words = set(label.split())
    matching = [
        b for b in bills if b.amount == amount and words & set(normalize(b.issuer or "").split())
    ]
    return min(
        matching, key=lambda b: abs((document_date(b) - document_date(doc)).days), default=None
    )


def _double_debits(doc: Document, bills: list[Document]) -> list[Anomaly]:
    flat = re.sub(r"\s+", " ", normalize(doc.text))
    seen: dict[tuple[str, float], int] = {}
    for m in _DEBIT.finditer(flat):
        key = (m[1].strip(), parse_amount(m[2], m[3]))
        seen[key] = seen.get(key, 0) + 1
    found = []
    for (label, amount), n in seen.items():
        if n < 2:
            continue
        assert doc.id is not None
        # The bill debited twice comes with the statement: both papers are at hand.
        bill = _bill_debited(bills, label, amount, doc)
        if bill is not None and bill.id is not None:
            detail = T(
                "double_debit_bill",
                amount=amount,
                date=document_date(doc),
                bill=bill.title,
                bill_date=document_date(bill),
            )
            ids, letter = [bill.id, doc.id], _letter_for(amount, [bill])
        else:
            detail = T("double_debit_detail", amount=amount, date=document_date(doc))
            ids, letter = [doc.id], T("double_letter", amount=amount)
        found.append(
            Anomaly(
                key=f"debit:{doc.id}:{label}:{amount}",
                kind="double_payment",
                title=T("double_debit_title", label=label.upper()),
                detail=detail,
                amount=amount,
                document_ids=ids,
                letter=letter,
            )
        )
    return found


def _usual(docs: list[Document], doc: Document) -> float | None:
    """Median amount of the earlier bills of the same sender."""
    earlier = [
        d.amount
        for d in docs
        if d.id != doc.id
        and d.amount
        and d.category == doc.category
        and normalize(d.issuer or "") == normalize(doc.issuer or "")
        and document_date(d) <= document_date(doc)
    ]
    return median(earlier) if earlier else None


def _text_anomalies(docs: list[Document]) -> list[Anomaly]:
    found = []
    bills = _bills(docs)
    for doc in docs:
        assert doc.id is not None
        norm = normalize(doc.text)
        issuer = doc.issuer or doc.title
        if doc.category in SUPPLIER_CATEGORIES and (m := _CATCH_UP.search(norm)):
            amount = doc.amount or _amount_near(norm, m, None)
            usual = _usual(docs, doc)
            if amount and (usual is None or amount >= usual * CATCH_UP_RATIO):
                found.append(
                    Anomaly(
                        key=f"catch_up:{doc.id}",
                        kind="catch_up",
                        title=T("catch_up_title", issuer=issuer, amount=amount),
                        detail=T("catch_up_detail", usual=usual)
                        if usual
                        else T("catch_up_detail_alone"),
                        amount=amount,
                        document_ids=[doc.id],
                        letter=T("catch_up_letter", amount=amount),
                    )
                )
        if doc.category in CLAIM_CATEGORIES and (m := _CLAIM.search(norm)):
            amount = _amount_near(norm, m, doc.amount)
            if amount:
                found.append(
                    Anomaly(
                        key=f"claim:{doc.id}",
                        kind="overpayment_claim",
                        title=T("claim_title", issuer=issuer),
                        detail=T("claim_detail", amount=amount),
                        amount=amount,
                        document_ids=[doc.id],
                        letter=T("claim_letter", amount=amount),
                    )
                )
        if doc.category in SUPPLIER_CATEGORIES and (m := _CREDIT.search(norm)):
            amount = _amount_near(norm, m, doc.amount)
            if amount:
                found.append(
                    Anomaly(
                        key=f"credit:{doc.id}",
                        kind="credit",
                        title=T("credit_title", issuer=issuer, amount=amount),
                        detail=T("credit_detail"),
                        amount=amount,
                        document_ids=[doc.id],
                        letter=T("credit_letter", amount=amount),
                    )
                )
        if doc.doc_type == DocType.BANK_STATEMENT:
            found += _double_debits(doc, bills)
    return found


def _increases(session: Session) -> list[Anomaly]:
    found = []
    for sub in subscriptions.detect(session):
        if not sub.increase or not sub.history:
            continue
        last = sub.history[-1]
        yearly = (
            (sub.last_amount - sub.previous_amount) * 365 / sub.interval_days
            if sub.interval_days
            else sub.last_amount - sub.previous_amount
        )
        found.append(
            Anomaly(
                key=f"increase:{last.document_id}",
                kind="price_increase",
                title=T("increase_title", label=sub.label, pct=sub.change_pct),
                detail=T(
                    "increase_detail",
                    last=sub.last_amount,
                    previous=sub.previous_amount,
                    yearly=round(yearly, 2),
                ),
                amount=sub.last_amount,
                document_ids=[p.document_id for p in sub.history[-2:]],
                letter=T("increase_letter", previous=sub.previous_amount, last=sub.last_amount),
            )
        )
    return found


def _pay_drops(docs: list[Document]) -> list[Anomaly]:
    slips = sorted(
        (d for d in docs if d.doc_type == DocType.PAYSLIP and d.amount),
        key=lambda d: (document_date(d), d.id or 0),
    )
    if len(slips) < 3:
        return []
    last = slips[-1]
    assert last.amount is not None and last.id is not None
    usual = median(d.amount for d in slips[:-1] if d.amount)
    if last.amount >= usual * (1 - PAY_DROP):
        return []
    pct = (usual - last.amount) / usual * 100
    return [
        Anomaly(
            key=f"pay_drop:{last.id}",
            kind="pay_drop",
            title=T("pay_drop_title", amount=last.amount),
            detail=T("pay_drop_detail", pct=pct, usual=usual),
            amount=last.amount,
            document_ids=[last.id],
        )
    ]


def detect(session: Session, today: date | None = None) -> list[Anomaly]:
    docs = _active(session, today or date.today())
    return _double_bills(docs) + _text_anomalies(docs) + _increases(session) + _pay_drops(docs)


def check_new(session: Session, doc: Document) -> list[Anomaly]:
    """After a document is analysed: logs the anomalies it is part of."""
    # Price rises are already logged by subscriptions.check_increase.
    found = [a for a in detect(session) if doc.id in a.document_ids and a.kind != "price_increase"]
    for anomaly in found:
        # The import report shows only the new paper: the message names the other one.
        others = [
            d for i in anomaly.document_ids if i != doc.id and (d := session.get(Document, i))
        ]
        msg = (
            T.msg(
                "logged_with",
                title=anomaly.title,
                other=others[0].title,
                date=document_date(others[0]),
            )
            if others
            else T.msg("logged", title=anomaly.title)
        )
        activity.log(
            session,
            "anomaly",
            msg,
            document=doc,
            details={"key": anomaly.key, "kind": anomaly.kind},
        )
    return found
