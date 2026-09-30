from datetime import date

import pytest

from binder.models import Category
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
    assert category == Category.SANTE


def test_unknown_document_has_low_confidence() -> None:
    result = rules.extract("Liste de courses : pain, lait")
    assert result.category == Category.AUTRE
    assert result.confidence < 0.5


def test_normalize_keeps_length() -> None:
    text = "Échéance réglée à l’avance"
    assert len(rules.normalize(text)) == len(text)
