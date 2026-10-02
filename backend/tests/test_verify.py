"""Checked extraction: every value the model gives must be in the document's text."""

import json
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from binder.db import get_engine, migrate
from binder.models import Category, DocType, Document
from binder.samples import Sample
from binder.schemas import Extraction
from binder.services import ingest, llm, rules, verify
from tests.conftest import upload

EDF = """EDF
Votre facture d'électricité
Facture du 20/09/2026 · N° client : 6012 3456 78
Total HT 78,64 €   TVA 15,73 €
Total TTC à payer
94,37 €
Montant prélevé le 14/10/2026 sur votre compte.
Période : du 1er août 2026 au 31/08/2026"""


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


def test_numbers_are_read_in_every_usual_format() -> None:
    found = verify.numbers("1 240,50 € · 1.240,50 · 1,240.50 · 94,37 € · 2 134,56 · 7 500")
    assert {1240.5, 94.37, 2134.56, 7500.0} <= found
    # Separate figures of a table row stay separate.
    assert {312.0, 14.12} <= verify.numbers("Consommation 312 14,12 €")


def test_dates_are_read_day_first_and_in_words() -> None:
    found = verify.dates("le 03/04/2026, 15.10.26, 1er octobre 2026, October 15, 2026, 2026-12-01")
    assert found == {
        date(2026, 4, 3),
        date(2026, 10, 15),
        date(2026, 10, 1),
        date(2026, 12, 1),
    }
    assert verify.months("Période : septembre 2026 · échéance 11/2026") == {(2026, 9), (2026, 11)}


def test_invented_values_are_dropped_and_doubted() -> None:
    ext = Extraction(
        amount_ttc=94.37,
        amount_due=120.0,
        due_date=date(2026, 10, 14),
        expiry_date=date(2027, 1, 1),
        reference="6012345678",
    )
    doubts = verify.check(ext, EDF)
    assert ext.amount_due is None and ext.expiry_date is None
    assert ext.amount_ttc == 94.37 and ext.reference == "6012345678"
    assert ext.amount == 94.37  # the main figure is derived from what remains
    assert doubts == ["unverified:amount_due", "unverified:expiry_date"]


def test_month_first_date_is_put_back_day_first() -> None:
    ext = Extraction(issue_date=date(2026, 3, 4))
    doubts = verify.check(ext, "Édité le 03/04/2026")
    assert ext.issue_date == date(2026, 4, 3) and doubts == ["date_swapped:issue_date"]


def test_periods_may_be_written_as_a_month() -> None:
    ext = Extraction(period_start=date(2026, 9, 1), period_end=date(2026, 9, 30))
    assert verify.check(ext, "Bulletin de paie · Période : septembre 2026") == []


def test_on_a_scan_values_not_in_the_ocr_text_are_kept_but_doubted() -> None:
    ext = Extraction(amount_ttc=94.37)
    doubts = verify.check(ext, "Total TTC à payer 94,31 €", scanned=True)
    assert ext.amount_ttc == 94.37 and doubts == ["ocr_mismatch:amount_ttc"]


def test_sign_is_not_part_of_an_amount() -> None:
    ext = Extraction(amount_due=-423.48)
    assert verify.check(ext, "Montant du trop-perçu 423,48 €") == []
    assert ext.amount == 423.48


def test_iban_and_siret_need_valid_check_digits() -> None:
    page = "IBAN : FR76 3000 6000 0112 3456 7890 189 · SIRET 732 829 320 00074"
    good = Extraction(iban="FR7630006000011234567890189", siret="73282932000074")
    assert verify.check(good, page) == []
    bad = Extraction(iban="FR7630006000011234567890188", siret="73282932000075")
    assert verify.check(bad, page) == ["invalid:iban", "invalid:siret"]
    assert bad.iban is None and bad.siret is None
    assert verify.siret_valid("35600000000010")  # La Poste: sum of digits


def test_amounts_must_add_up_and_dates_be_plausible() -> None:
    ext = Extraction(
        amount_ht=78.64,
        amount_tva=15.73,
        amount_ttc=96.0,
        issue_date=date(2026, 9, 20),
        due_date=date(2026, 9, 1),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 8, 1),
    )
    today = date(2026, 9, 30)
    assert verify.consistency(ext, today) == [
        "inconsistent_amounts",
        "implausible_dates:due_date",
        "implausible_dates:period_end",
    ]
    ext.amount_ttc, ext.due_date, ext.period_end = 94.37, date(2026, 10, 14), date(2026, 9, 30)
    assert verify.consistency(ext, today) == []
    assert verify.consistency(Extraction(issue_date=date(2027, 6, 1)), today) == [
        "implausible_dates:issue_date"
    ]


def test_merge_doubts_any_disagreement_and_computes_its_confidence() -> None:
    by_rules = rules.extract(EDF)
    by_llm = Extraction(
        category=Category.ENERGY,
        doc_type="invoice",
        title="Facture EDF",
        amount_ttc=94.37,
        amount_due=78.64,
        issue_date=date(2026, 9, 20),
        due_date=date(2026, 8, 31),
        confidence=0.99,
        extractor="llm",
    )
    by_llm.doubts = verify.check(by_llm, EDF)
    merged = ingest.merge(by_rules, by_llm)
    assert "disagreement:amount" in merged.doubts and "disagreement:due_date" in merged.doubts
    # The model said 0.99: only the checks count.
    assert merged.confidence < ingest.REVIEW_THRESHOLD
    agreeing = Extraction(
        category=Category.ENERGY,
        doc_type="invoice",
        amount_ttc=94.37,
        issue_date=date(2026, 9, 20),
        due_date=date(2026, 10, 14),
        extractor="llm",
    )
    agreeing.doubts = verify.check(agreeing, EDF)
    merged = ingest.merge(by_rules, agreeing)
    assert merged.doubts == [] and merged.confidence == 1.0


@pytest.fixture
def model_reads(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """What the simulated model answers to the extraction prompt."""
    reply: dict[str, Any] = {}

    def chat(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return {"role": "assistant", "content": json.dumps(reply)}

    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "has_vision", lambda: False)
    monkeypatch.setattr(llm, "chat", chat)
    yield reply


def test_model_confidence_is_ignored(model_reads: dict[str, Any]) -> None:
    model_reads.update(category="energy", title="Facture EDF", amount_ttc=94.37, confidence=1)
    ext = llm.extract(EDF)
    assert ext is not None and ext.confidence == 0.0 and ext.amount_ttc == 94.37


def test_invented_amount_sends_the_document_to_review(
    client: TestClient, samples: list[Sample], model_reads: dict[str, Any]
) -> None:
    model_reads.update(
        category="energy",
        doc_type="invoice",
        title="Facture EDF",
        issuer="EDF",
        amount_ttc=99.99,
        issue_date="2026-09-20",
        due_date="2026-10-14",
        reference="6012 3456 78",
    )
    doc = upload(client, by_name(samples, "facture-edf.pdf"))
    assert doc["status"] == "to_review"
    assert "unverified:amount_ttc" in doc["missing_fields"]
    # The invented figure is gone; the one read in the text stands in for it.
    assert doc["amount_ttc"] is None and doc["amount"] == 94.37
    r = client.patch(f"/api/documents/{doc['id']}", json={"validated": True})
    assert r.status_code == 200
    validated = client.get(f"/api/documents/{doc['id']}").json()
    assert validated["status"] == "classified" and validated["missing_fields"] == []


def test_former_amount_becomes_the_total_including_tax() -> None:
    engine = get_engine()
    with Session(engine) as session:
        session.add(Document(filename="a.pdf", mime_type="application/pdf", size=1,
                             sha256="x", stored_name="a.bin", amount=278.0))  # fmt: skip
        session.commit()
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE document DROP COLUMN "amount_ttc"'))
    migrate(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT amount_ttc FROM document")).scalar() == 278.0


def test_reminder_notice_and_invoice_are_told_apart() -> None:
    assert rules.detect_doc_type("relance : votre facture n° 12 reste impayee") == (
        DocType.PAYMENT_REMINDER
    )
    assert rules.detect_doc_type("mise en demeure de payer la facture") == DocType.PAYMENT_REMINDER
    assert rules.detect_doc_type("avis d'echeance - cotisation annuelle") == DocType.PAYMENT_NOTICE
    assert rules.detect_doc_type("facture d'electricite") == DocType.INVOICE
    assert "payment_reminder" in llm.doc_types()


def test_periods_may_be_written_as_months_or_years() -> None:
    garde = "Garderie du matin et du soir, janvier à septembre 2026"
    assert verify.months(garde) == {(2026, 1), (2026, 9)}
    ext = Extraction(period_start=date(2026, 1, 1), period_end=date(2026, 9, 30))
    assert verify.check(ext, garde) == []
    charges = Extraction(period_start=date(2025, 1, 1), period_end=date(2025, 12, 31))
    assert verify.check(charges, "Régularisation des charges locatives 2025") == []
    # A day inside the period is not a boundary: it must be written.
    inside = Extraction(period_start=date(2025, 3, 14))
    assert verify.check(inside, "Charges 2025") == ["unverified:period_start"]


def test_demo_bank_statement_has_a_valid_iban(samples: list[Sample]) -> None:
    from binder.services.text import read_document

    statement = read_document(by_name(samples, "releve-bancaire.pdf").pdf(), "application/pdf")
    assert verify.iban_valid("FR89 1780 6000 1234 5678 9012 345")
    assert "FR89 1780" in statement.text
