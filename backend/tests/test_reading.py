"""Reading long, multi-page and multi-column documents."""

import json
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient

from binder.services import ingest, llm
from binder.services.text import read_document, several_documents


def _pdf(pages: list[list[tuple[float, str]]]) -> bytes:
    """A PDF whose pages hold texts at given heights, drawn in the order given."""
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=595, height=842)
        for y, line in lines:
            page.insert_text((60, y), line, fontsize=10)
    data = bytes(doc.tobytes())
    doc.close()
    return data


def test_text_is_read_in_reading_order() -> None:
    # Drawn bottom first, as some generators do: read top first.
    data = _pdf([[(700, "Total TTC a payer 94,37 EUR"), (80, "EDF Facture")]])
    text = read_document(data, "application/pdf").text
    assert text.index("EDF") < text.index("Total")


def test_long_text_keeps_its_start_and_its_end() -> None:
    text = "Facture EDF\n" + "ligne de consommation\n" * 1000 + "Total à payer 94,37 €"
    cut = llm.compact(text, 400)
    assert len(cut) == 400 and cut.startswith("Facture EDF") and cut.endswith("94,37 €")
    assert llm.CUT in cut and llm.truncated(text, 400) and not llm.truncated("court", 400)


def test_last_page_of_a_long_scan_is_shown_too() -> None:
    assert ingest.vision_pages(1) == [0]
    assert ingest.vision_pages(3) == [0, 1, 2]
    assert ingest.vision_pages(7) == [0, 1, 2, 6]


def test_several_documents_in_one_file_are_spotted() -> None:
    assert several_documents(["EDF\nPage 1/2", "suite\nPage 2/2", "Orange\nPage 1/1"])
    assert several_documents(["EDF\nVotre facture", "Orange\nFacture mobile"])
    # One bank statement: the bills it lists are not letterheads.
    statement = [
        "Crédit Agricole\nRelevé de compte\nPage 1/2",
        "Opérations\nPage 2/2\nPRLV SEPA EDF\nPRLV SEPA ORANGE",
    ]
    assert not several_documents(statement)
    assert not several_documents(["EDF\nFacture"])


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    reply: dict[str, Any] = {"category": "energy", "doc_type": "invoice", "title": "Facture EDF"}

    def chat(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return {"role": "assistant", "content": json.dumps(reply)}

    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "has_vision", lambda: False)
    monkeypatch.setattr(llm, "chat", chat)
    return reply


def _upload(client: TestClient, data: bytes) -> dict[str, Any]:
    r = client.post("/api/documents", files={"file": ("doc.pdf", data, "application/pdf")})
    assert r.status_code == 201, r.text
    doc: dict[str, Any] = client.get(f"/api/documents/{r.json()['id']}").json()
    return doc


def test_cut_document_goes_to_review(client: TestClient, model: dict[str, Any]) -> None:
    lines = [(60 + 12 * i, f"Releve de consommation ligne {i} : 12 kWh") for i in range(60)]
    data = _pdf([lines] * 12)
    doc = _upload(client, data)
    assert doc["status"] == "to_review" and "truncated" in doc["missing_fields"]


def test_file_with_several_documents_goes_to_review(
    client: TestClient, model: dict[str, Any]
) -> None:
    data = _pdf(
        [
            [(60, "EDF"), (80, "Facture du 20/09/2026"), (100, "Total TTC 94,37 EUR")],
            [(60, "Orange"), (80, "Facture du 26/09/2026"), (100, "Total 39,99 EUR")],
        ]
    )
    doc = _upload(client, data)
    assert doc["status"] == "to_review" and "several_documents" in doc["missing_fields"]
