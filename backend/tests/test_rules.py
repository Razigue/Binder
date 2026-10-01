from datetime import date

import pytest

from binder import i18n
from binder.models import Category, DocType
from binder.samples import Sample
from binder.services import rules
from binder.services.text import read_document


def test_every_sample_is_extracted_correctly(samples: list[Sample]) -> None:
    for sample in samples:
        text = read_document(sample.pdf(), "application/pdf").text
        result = rules.extract(text)
        for field, expected in sample.expected.items():
            assert getattr(result, field) == expected, f"{sample.filename}: {field}"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Total à payer : 1 842,00 €", 1842.0),
        ("Montant 94,37 EUR", 94.37),
        ("Montant dû 1.240 €", 1240.0),
        ("Loyer 850 euros", 850.0),
        ("Total 1842.5 €", 1842.5),
    ],
)
def test_amount_formats(raw: str, expected: float) -> None:
    assert rules.extract_amount([rules.normalize(raw)]) == expected


def test_prefers_amount_next_to_total() -> None:
    lines = ["Abonnement 14,12 €", "Consommation 80,25 €", "Total TTC à payer 94,37 €"]
    assert rules.extract_amount([rules.normalize(line) for line in lines]) == 94.37


def test_dates_numeric_and_text() -> None:
    assert rules.find_dates("le 15 octobre 2026 puis 02/11/26") == [
        date(2026, 10, 15),
        date(2026, 11, 2),
    ]
    assert rules.find_dates("31/02/2026") == []


def test_health_insurance_is_not_home_insurance() -> None:
    category, _ = rules.classify(
        rules.normalize("Assurance Maladie - CPAM - décompte de remboursement")
    )
    assert category == Category.HEALTH


def test_unknown_document_has_low_confidence() -> None:
    result = rules.extract("Liste de courses : pain, lait")
    assert result.category == Category.OTHER
    assert result.confidence < 0.5


def test_normalize_keeps_length() -> None:
    text = "Échéance réglée à l’avance"
    assert len(rules.normalize(text)) == len(text)


def test_document_type_uses_stable_identifiers() -> None:
    assert rules.detect_doc_type(rules.normalize("Attestation d'assurance habitation")) == (
        DocType.INSURANCE_CERTIFICATE
    )
    assert rules.detect_doc_type(rules.normalize("Liste de courses")) is None
    # Certificates and contracts need no amount: only their date is expected.
    assert rules.required_fields(Category.SOCIAL, DocType.CERTIFICATE) == ["issue_date"]
    assert rules.required_fields(Category.WORK, DocType.EMPLOYMENT_CONTRACT) == ["issue_date"]
    assert rules.required_fields(Category.IDENTITY, DocType.PASSPORT) == ["expiry_date"]
    assert rules.required_fields(Category.ENERGY, DocType.INVOICE) == ["amount", "due_date"]


def test_titles_follow_the_language() -> None:
    bill = "EDF\nVotre facture d'électricité\nFacture du 21/07/2026 — Total TTC 94,37 €"
    tax = "Avis d'impôt 2026 — Taxe foncière\nDate d'établissement : 10/09/2026"
    quote = "Garage du Centre\nDevis réparation du 28/09/2026"
    assert rules.extract(bill).title == "EDF invoice"
    assert rules.extract(tax).title == "Property tax 2026"
    assert rules.extract(quote).title == "Quote from Garage du Centre"

    with i18n.using("fr"):
        assert rules.extract(bill).title == "Facture EDF"
        assert rules.extract(tax).title == "Taxe foncière 2026"
        assert rules.extract(quote).title == "Devis Garage du Centre"
        # Unknown type: the category label.
        assert rules.extract("Assurance Maladie\nCPAM").title == "Santé"
