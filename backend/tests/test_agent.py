"""Agent harness, tools, semantic search, OCR and vision (the model is simulated)."""

import io
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from binder.agent import loop, tools
from binder.db import get_engine
from binder.models import Activity, Category, Deadline, Document
from binder.samples import Sample
from binder.services import embeddings, ingest, llm
from binder.services.rules import normalize
from binder.services.text import join_lines, read_document, render_page
from tests.conftest import upload


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


@pytest.fixture
def library(client: TestClient, samples: list[Sample]) -> dict[str, int]:
    """Every demo document, by file name."""
    return {s.filename: int(str(upload(client, s)["id"])) for s in samples}


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


class FakeModel:
    """Scripted replies of the model; records what it was sent."""

    def __init__(self, *replies: dict[str, Any]) -> None:
        self.replies = list(replies)
        self.requests: list[list[dict[str, Any]]] = []
        self.kwargs: list[dict[str, Any]] = []

    def __call__(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.requests.append([dict(m) for m in messages])
        self.kwargs.append(kwargs)
        reply = self.replies.pop(0)
        if kwargs.get("on_token") and reply.get("content"):
            for word in str(reply["content"]).split(" "):
                kwargs["on_token"](word + " ")
        return {"role": "assistant", **reply}


def call(name: str, **arguments: Any) -> dict[str, Any]:
    return {"content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


def answer(text: str) -> dict[str, Any]:
    return {"content": text}


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeModel]:
    fake = FakeModel()
    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "has_vision", lambda: True)
    monkeypatch.setattr(llm, "chat", fake)
    yield fake


# --- Tools ---------------------------------------------------------------------------------


def test_arguments_are_checked_and_converted(library: dict[str, int], session: Session) -> None:
    doc_id = library["facture-edf.pdf"]
    # A number written as text, an unknown argument and a null are tolerated.
    result = tools.call(
        session, "read_document", {"document_id": str(doc_id), "colour": "red", "query": None}
    )
    assert result.payload["id"] == doc_id
    missing = tools.call(session, "read_document", {})
    assert missing.payload["error"] == "Invalid arguments: document_id is required"
    wrong = tools.call(session, "read_document", {"document_id": "the EDF bill"})
    assert "document_id: invalid value" in wrong.payload["error"]
    assert "Unknown tool" in tools.call(session, "delete_everything", {}).payload["error"]


def test_passages_keep_the_value_after_its_label() -> None:
    text = "Avis d'impôt\nNuméro fiscal : 30 12\nRevenu fiscal de référence\n32 480 €\nTotal\n1 €"
    assert tools.passages(text, ["revenu", "fiscal", "reference"], limit=1) == [
        "Revenu fiscal de référence / 32 480 €"
    ]


def test_search_returns_passages_and_total_amount(
    library: dict[str, int], session: Session
) -> None:
    result = tools.search_documents(session, "facture EDF")
    assert result.payload["total"] == 2
    assert result.payload["sum_amount"] == round(94.37 + 81.05, 2)
    assert any("EDF" in p for p in result.payload["results"][0]["passages"])
    assert tools.search_documents(session, "netflix").payload["hint"] == tools.NO_MATCH_HINT


def test_text_details_are_found_by_reading(library: dict[str, int], session: Session) -> None:
    result = tools.read_document(
        session, library["avis-imposition.pdf"], query="revenu fiscal de référence"
    )
    assert any("52 310" in p for p in result.payload["passages"])


def test_deadlines_include_overdue_ones_and_their_total(
    library: dict[str, int], session: Session
) -> None:
    session.add(Deadline(title="Old fine", due_date=date(2020, 1, 15)))
    session.commit()
    result = tools.list_deadlines(session, days=400)
    assert [d["title"] for d in result.payload["overdue"]] == ["Old fine"]
    assert result.payload["total_amount"] > 0


def test_expirations_list_every_document_with_a_validity(
    library: dict[str, int], session: Session
) -> None:
    payload = tools.list_expirations(session).payload
    ids = [d["id"] for d in payload["documents"]]
    # Even far away (the car inspection is valid for 19 more months).
    assert library["controle-technique.pdf"] in ids and library["carte-identite.pdf"] in ids
    # The replaced insurance certificate is not listed.
    assert library["attestation-maif-ancienne.pdf"] not in ids


def test_agent_actions_are_logged_and_reversible(library: dict[str, int], session: Session) -> None:
    tax = library["avis-imposition.pdf"]
    paid = tools.call(session, "mark_deadline_paid", {"document_id": tax})
    assert paid.changed and all(d["paid"] for d in paid.payload["updated"])

    quote = library["note-garage.pdf"]
    fixed = tools.call(
        session, "update_document", {"document_id": quote, "category": "Véhicule", "amount": 165}
    )
    assert fixed.payload["changed"]["category"] == {"old": "other", "new": "vehicle"}
    doc = session.get(Document, quote)
    assert doc is not None and doc.category == Category.VEHICLE and doc.amount == 165
    bad = tools.call(session, "update_document", {"document_id": quote, "category": "pets"})
    assert "Unknown category" in bad.payload["error"]

    old = library["attestation-maif-ancienne.pdf"]
    trashed = tools.call(session, "trash_document", {"document_id": old})
    assert trashed.payload["restorable"] is True
    session.commit()
    actors = {a.action: a.actor for a in session.exec(select(Activity)) if a.actor == "agent"}
    assert {"deadline", "update", "trash"} <= actors.keys()
    # In the trash, not deleted: it can be restored, and the agent no longer sees it.
    assert session.get(Document, old) is not None
    assert (
        "not found" in tools.call(session, "read_document", {"document_id": old}).payload["error"]
    )


def test_letter_and_folder(library: dict[str, int], session: Session) -> None:
    letter = tools.call(
        session,
        "write_letter",
        {
            "purpose": "cancel my subscription",
            "kind": "termination",
            "document_id": library["facture-orange.pdf"],
        },
    )
    body = letter.letters[0].body
    assert letter.letters and "Orange" in body and letter.changed
    # The sender comes from the documents: the ID card's holder, the address on the certificates.
    assert "Camille Martin" in body and "12 rue des Tilleuls" in body
    assert letter.letters[0].id is not None
    folder = tools.call(session, "prepare_folder", {"purpose": "rental"})
    assert folder.payload["export_link"] == "/api/folders/rental/export"
    assert {p["status"] for p in folder.payload["pieces"]} & {"missing", "ok"}
    # Any purpose: a pack put together from the documents, saved for its export link.
    custom = tools.call(session, "prepare_folder", {"purpose": "inscription en crèche"})
    assert custom.payload["export_link"].startswith("/api/folders/custom-")
    assert custom.packs and custom.packs[0].pieces


def test_view_document_shows_the_page(library: dict[str, int], session: Session) -> None:
    result = tools.call(session, "view_document", {"document_id": library["facture-edf.pdf"]})
    assert result.payload["pages"] == 1 and result.images[0][:2] == b"\xff\xd8"  # JPEG
    names = {t["function"]["name"] for t in tools.schemas(vision=False)}
    # Web search is off in the tests (conftest): its tools are not offered either.
    assert "view_document" not in names
    # The listings are reached through `list`.
    hidden = 1 + len(tools.WEB_TOOLS) + len(tools.LIST_KINDS)
    assert len(names) == len(tools.TOOLS) - hidden


# --- Harness -------------------------------------------------------------------------------


def test_answer_without_looking_is_refused_once(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    doc_id = library["facture-edf.pdf"]
    model.replies = [
        answer("Your EDF bill is €120."),  # invented: discarded
        call("search_documents", query="EDF"),
        answer(f"Your EDF bill is €94.37 (ID #{doc_id})."),
    ]
    events: list[dict[str, Any]] = []
    response = loop.run(session, "How much is my EDF bill?", [], emit=events.append)
    assert response.answer == f"Your EDF bill is €94.37 [#{doc_id}]."
    assert response.citations == [doc_id]
    assert model.requests[1][-1]["content"] == loop.TOOLS_FIRST
    assert "€120" not in json.dumps(model.requests[1])
    # The discarded guess never reached the screen: no text shown, then wiped.
    shown = "".join(e["text"] for e in events if e["type"] == "token")
    assert shown.strip() == f"Your EDF bill is €94.37 (ID #{doc_id})."
    assert {"type": "step"} not in events
    assert any(e["type"] == "tool" and e["name"] == "search_documents" for e in events)


def test_promise_is_not_shown_before_being_discarded(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    long_promise = "I'll create the reminder for the property tax right away, " * 3
    model.replies = [
        call("list_deadlines"),
        answer(long_promise),  # announced, not done: sent back with DO_IT
        call("create_reminder", title="Property tax", due_date="2026-10-10"),
        answer("Done: reminder on 10 October, as asked, for the property tax payment. " * 2),
    ]
    events: list[dict[str, Any]] = []
    loop.run(session, "Remind me about the property tax on 10/10", [], emit=events.append)
    shown = "".join(e["text"] for e in events if e["type"] == "token")
    assert "I'll create" not in shown and shown.startswith("Done:")
    assert {"type": "step"} not in events


def test_questions_about_the_app_use_the_guide(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    model.replies = [
        call("app_help", question="What is Gmail IMAP?"),
        answer("Create an app password at myaccount.google.com/apppasswords."),
    ]
    loop.run(session, "What is Gmail IMAP?", [])
    assert "app_help" in loop.system_prompt(session)
    guide = json.loads(model.requests[1][-1]["content"])["guide"]
    assert "myaccount.google.com/apppasswords" in guide[0]


def test_router_answers_questions_about_the_app(library: dict[str, int], session: Session) -> None:
    response = loop.run(session, "C'est quoi l'IMAP de GMAIL", [])
    assert "apppasswords" in response.answer
    assert [c.name for c in response.tool_calls] == ["app_help"]
    phone = loop.run(session, "How do I scan with my phone?", [])
    assert "QR code" in phone.answer
    # A question about a document is not a question about the app.
    edf = loop.run(session, "What should I do about the EDF bill?", [])
    assert "app_help" not in [c.name for c in edf.tool_calls]


def test_tool_timings_and_model_stats_are_reported(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    timing = {"prompt_eval_count": 1000, "prompt_eval_duration": 500_000_000}
    model.replies = [
        {
            **call("search_documents", query="EDF"),
            "stats": {**timing, "eval_count": 20, "eval_duration": 1_000_000_000},
        },
        {**call("read_document", document_id=999)},
        {
            **answer("Found it."),
            "stats": {**timing, "eval_count": 60, "eval_duration": 1_000_000_000},
        },
    ]
    events: list[dict[str, Any]] = []
    response = loop.run(session, "My EDF bill?", [], emit=events.append)
    search, read = response.tool_calls
    assert search.duration_ms is not None and not search.error
    assert read.error  # unknown document
    assert [e["type"] for e in events if e["type"].startswith("tool")] == [
        "tool",
        "tool_done",
        "tool",
        "tool_done",
    ]
    stats = response.stats
    assert stats is not None and stats.turns == 3
    assert (stats.prompt_tokens, stats.output_tokens) == (2000, 80)
    assert stats.tokens_per_second == 40.0 and stats.prompt_tokens_per_second == 2000.0
    assert sum(e["type"] == "stats" for e in events) == 3


def test_ollama_stats_are_read_from_the_last_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = [
        {"message": {"content": "Hel"}},
        {"message": {"content": "lo"}},
        {"message": {}, "done": True, "eval_count": 2, "eval_duration": 10, "load_duration": 5},
    ]

    class Response:
        is_error = False

        def raise_for_status(self) -> None: ...

        def iter_lines(self) -> Iterator[str]:
            return iter(json.dumps(line) for line in lines)

    class Client:
        def __enter__(self) -> "Client":
            return self

        def __exit__(self, *args: object) -> None: ...

        @contextmanager
        def stream(self, method: str, path: str, json: dict[str, Any]) -> Iterator[Response]:
            yield Response()

    monkeypatch.setattr(llm, "client", lambda **_: Client())
    reply = llm.chat([{"role": "user", "content": "hi"}], on_token=lambda _: None)
    assert reply["content"] == "Hello"
    assert reply["stats"] == {"eval_count": 2, "eval_duration": 10}


def test_context_size_and_library_overview_are_sent(
    library: dict[str, int], session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[dict[str, Any]] = []

    class Response:
        status_code = 200
        is_error = False

        def raise_for_status(self) -> None: ...

        def json(self) -> dict[str, Any]:
            return {"message": {"role": "assistant", "content": "Hello."}}

    class Client:
        def __enter__(self) -> "Client":
            return self

        def __exit__(self, *args: object) -> None: ...

        def post(self, path: str, json: dict[str, Any]) -> Response:
            sent.append(json)
            return Response()

    monkeypatch.setattr(llm, "client", lambda **_: Client())
    llm.chat([{"role": "user", "content": "hi"}])
    assert sent[0]["options"]["num_ctx"] >= 16384 and sent[0]["keep_alive"]
    prompt = loop.system_prompt(session, vision=True)
    assert '"documents":21' in prompt and "view_document" in prompt


def test_loose_citations_are_fixed_only_for_known_documents(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    maif = library["maif-echeance.pdf"]
    model.replies = [
        call("search_documents", query="MAIF"),
        answer(f"Contract #4521877 H (document #{maif}); see also #999."),
    ]
    response = loop.run(session, "Mon contrat MAIF ?", [])
    assert response.answer == f"Contract #4521877 H [#{maif}]; see also #999."
    assert response.citations == [maif]


def test_unnamed_source_is_cited_by_its_title(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    card = library["carte-identite.pdf"]
    model.replies = [call("list_expirations"), answer("Your identity card expires soon.")]
    response = loop.run(session, "When does my ID expire?", [])
    assert response.citations == [card]


def test_loops_and_bad_arguments_are_handled(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    bad = {"content": "", "tool_calls": [{"function": {"name": "read_document", "arguments": "{"}}]}
    # The final answer is the last of the MAX_STEPS turns.
    model.replies = [bad, *[call("list_deadlines")] * (loop.MAX_STEPS - 2), answer("Done.")]
    response = loop.run(session, "What is due?", [])
    assert response.answer == "Done."
    tool_messages = [m for m in model.requests[-1] if m["role"] == "tool"]
    assert "not valid JSON" in tool_messages[0]["content"]
    assert "Same call as before" in tool_messages[2]["content"]
    # Out of steps: a last turn without tools.
    assert model.requests[-1][-1]["content"] == loop.FINAL_NUDGE
    assert "tools" not in model.kwargs[-1]


def test_page_images_reach_the_model(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    doc_id = library["facture-orange.pdf"]
    model.replies = [call("view_document", document_id=doc_id), answer(f"€19.99 [#{doc_id}]")]
    loop.run(session, "Look at the Orange bill", [])
    tool = model.requests[1][-1]
    assert tool["role"] == "tool" and len(tool["images"]) == 1


def test_earlier_documents_stay_citable(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    orange = library["facture-orange.pdf"]
    history = [
        loop.ChatMessage(role="user", content="Find my Orange bill"),
        loop.ChatMessage(role="assistant", content="Here it is.", documents=[orange]),
    ]
    model.replies = [call("read_document", document_id=orange), answer(f"On the 20th [#{orange}].")]
    response = loop.run(session, "When is it debited?", history)
    title = session.get(Document, orange).title  # type: ignore[union-attr]
    assert f"(documents shown: #{orange} {title})" in model.requests[0][2]["content"]
    assert response.citations == [orange]


def test_stream_endpoint(client: TestClient, library: dict[str, int], model: FakeModel) -> None:
    doc_id = library["facture-orange.pdf"]
    model.replies = [
        call("write_letter", purpose="cancel", kind="termination", document_id=doc_id),
        # Written by the model too, from the termination brief.
        answer(
            json.dumps(
                {
                    "subject": "Termination",
                    "recipient": "Orange",
                    "paragraphs": ["I am ending my subscription."],
                    "registered": True,
                }
            )
        ),
        answer(f"Here is your letter [#{doc_id}]."),
    ]
    with client.stream("POST", "/api/agent/chat/stream", json={"message": "Cancel Orange"}) as r:
        assert r.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in r.iter_lines() if line]
    # The model's first turn is counted before its tool starts.
    assert events[0]["type"] == "stats" and events[0]["stats"]["turns"] == 1
    assert events[1] == {
        "type": "tool",
        "name": "write_letter",
        "arguments": {"purpose": "cancel", "kind": "termination", "document_id": doc_id},
    }
    assert "".join(e["text"] for e in events if e["type"] == "token").strip() == (
        f"Here is your letter [#{doc_id}]."
    )
    done = events[-1]["response"]
    assert done["letters"][0]["recipient"] == "Orange" and done["citations"] == [doc_id]
    missing = client.post("/api/agent/chat/stream", json={"message": "x", "attachments": [999]})
    assert missing.status_code == 404


# --- Semantic search -----------------------------------------------------------------------

TOPICS = {
    "address": ["domicile", "address", "loyer", "electricite", "edf", "quittance"],
    "car": ["voiture", "car", "controle", "vehicule", "garage"],
}


def fake_embed(texts: list[str]) -> Any:
    """Vectors by topic: a question and a document of the same topic are close."""
    rows = []
    for text in texts:
        norm = normalize(text)
        # A residual dimension apart for questions: an unrelated question matches nothing.
        question = text.startswith("Instruct:")
        row = [sum(word in norm for word in words) for words in TOPICS.values()]
        row += [0.0, 0.1] if question else [0.1, 0.0]
        rows.append(row)
    vectors = np.asarray(rows, dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def test_semantic_search_finds_documents_without_shared_words(
    library: dict[str, int], session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(embeddings, "is_available", lambda: True)
    monkeypatch.setattr(embeddings, "embed", fake_embed)
    # Existing documents are embedded on first use.
    found = tools.search_documents(session, "proof of domicile")
    ids = {d["id"] for d in found.payload["results"]}
    assert {library["quittance-loyer.pdf"], library["facture-edf.pdf"]} <= ids
    assert library["controle-technique.pdf"] not in ids
    # Unrelated question: nothing, rather than the closest noise.
    assert tools.search_documents(session, "netflix").payload["total"] == 0
    # A purged document leaves no vector behind.
    doc = session.get(Document, library["note-garage.pdf"])
    assert doc is not None
    ingest.trash(session, doc)
    ingest.purge(session, doc)
    session.commit()
    rows = session.exec(select(embeddings.Embedding.document_id)).all()
    assert library["note-garage.pdf"] not in rows


def test_words_found_still_name_documents_close_in_meaning(
    library: dict[str, int], session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(embeddings, "is_available", lambda: True)
    monkeypatch.setattr(embeddings, "embed", fake_embed)
    found = tools.search_documents(session, "quittance")
    # The results and their sum stay those of the words; the bill is named apart.
    assert [d["id"] for d in found.payload["results"]] == [library["quittance-loyer.pdf"]]
    assert found.payload["total"] == 1
    related = {d["id"] for d in found.payload["related"]}
    assert library["facture-edf.pdf"] in related and library["quittance-loyer.pdf"] not in related
    assert len(related) <= tools.RELATED
    assert {d.id for d in found.related} == related


def test_without_embedding_model_search_stays_full_text(
    library: dict[str, int], session: Session
) -> None:
    # Tests run without Ollama: the semantic part is skipped silently.
    assert embeddings.search(session, "proof of domicile") == []
    assert tools.search_documents(session, "quittance").payload["total"] == 1


# --- OCR and vision ------------------------------------------------------------------------


def test_ocr_lines_are_rebuilt_from_fragments() -> None:
    # Table cells come apart from OCR; the rules want "label value" on one line.
    fragments = [
        (300.0, 100.0, 120.0, "94,37 €"),
        (10.0, 102.0, 118.0, "Total TTC à payer"),
        (10.0, 60.0, 80.0, "EDF"),
    ]
    assert join_lines(fragments) == "EDF\nTotal TTC à payer 94,37 €"


def test_photo_is_read_by_the_bundled_ocr(samples: list[Sample]) -> None:
    png = render_page(by_name(samples, "facture-edf.pdf").pdf(), "application/pdf", 0, dpi=150)
    result = read_document(png, "image/png")
    assert result.ocr_used and "EDF" in result.text
    assert "94,37" in result.text and "Total TTC à payer 94,37 €" in result.text


def test_scans_are_shown_to_a_model_with_vision(
    client: TestClient, samples: list[Sample], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    def extract(text: str, images: list[bytes] | None = None, **_: Any) -> None:
        seen["images"] = images
        return None

    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "has_vision", lambda: True)
    monkeypatch.setattr(llm, "extract", extract)
    monkeypatch.setattr(llm, "transcribe", lambda images: "never used: OCR read the page")
    png = render_page(by_name(samples, "facture-orange.pdf").pdf(), "application/pdf", 0, dpi=150)
    r = client.post("/api/documents", files={"file": ("orange.png", png, "image/png")})
    doc = client.get(f"/api/documents/{r.json()['id']}").json()
    assert seen["images"] and seen["images"][0][:2] == b"\xff\xd8"
    assert "Orange" in doc["text"] and doc["amount"] == 39.99


def test_unreadable_scan_is_transcribed_by_the_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image

    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "has_vision", lambda: True)
    monkeypatch.setattr(llm, "extract", lambda text, images=None, **_: None)
    monkeypatch.setattr(
        llm, "transcribe", lambda images: "Facture Orange\nMontant total à payer 39,99 €"
    )
    blank = Image.new("RGB", (800, 1100), "white")
    buffer = io.BytesIO()
    blank.save(buffer, "PNG")
    r = client.post("/api/documents", files={"file": ("photo.png", buffer.getvalue(), "image/png")})
    doc = client.get(f"/api/documents/{r.json()['id']}").json()
    assert doc["text"].startswith("Facture Orange") and doc["amount"] == 39.99


def test_announced_action_is_actually_done(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    old = library["attestation-maif-ancienne.pdf"]
    model.replies = [
        call("search_documents", query="attestation MAIF"),
        answer(f"I found it [#{old}]. I'll move it to the trash now."),
        call("trash_document", document_id=old),
        answer("Done: the old certificate is in the trash."),
    ]
    response = loop.run(session, "Trash last year's MAIF certificate", [])
    assert model.requests[2][-1]["content"] == loop.DO_IT
    assert [c.name for c in response.tool_calls] == ["search_documents", "trash_document"]
    # Found by reading documents: the trash waits for the user's confirmation.
    assert not response.changed and response.confirmations[0]["tool"] == "trash_document"


def test_offline_router_acts_only_when_asked(
    client: TestClient, library: dict[str, int], session: Session
) -> None:
    def ask(message: str) -> dict[str, Any]:
        r: dict[str, Any] = client.post("/api/agent/chat", json={"message": message}).json()
        return r

    # A question about payments changes nothing.
    r = ask("How much have I paid for electricity?")
    assert "mark_deadline_paid" not in [c["name"] for c in r["tool_calls"]]
    r = ask("I paid the income tax, mark it as paid")
    assert r["changed"] and r["citations"] == [library["avis-imposition.pdf"]]
    r = ask("Write a letter to cancel my Orange subscription")
    assert r["letters"][0]["recipient"] == "Orange"
    assert "Rental application" in ask("What is missing in my rental application?")["answer"]
    assert "recurring bill" in ask("How much do my subscriptions cost?")["answer"]
    r = ask("Remind me to pay the canteen on November 12")
    assert r["deadlines"][0]["due_date"].endswith("-11-12")


def test_request_handed_back_to_the_user_is_done(
    library: dict[str, int], session: Session, model: FakeModel
) -> None:
    model.replies = [
        call("search_documents", query="cantine"),
        answer("Could you tell me the amount and the document?"),
        call("create_reminder", title="Pay the canteen", due_date="2026-11-12"),
        answer("Reminder set for 12 November."),
    ]
    response = loop.run(session, "Remind me to pay the canteen on 12 November", [])
    assert model.requests[2][-1]["content"] == loop.JUST_DO_IT
    assert response.changed and response.deadlines[0].title == "Pay the canteen"
