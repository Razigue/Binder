"""Proactive agent: Today feed, one-tap questions, undo, import reports, learning, household,
anomalies, missing documents, letters with follow-up, packs, sources, briefing, notifications,
backups and the local AI setup."""

import io
import sys
import tarfile
import zipfile
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import zstandard
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from binder import updater
from binder.config import get_settings
from binder.db import get_engine, reset_engine
from binder.models import Category, Correspondence, Deadline, Document, DocumentStatus
from binder.samples import Sample, _fr, _money
from binder.services import (
    anomalies,
    areas,
    backup,
    briefing,
    feed,
    household,
    missing,
    notify,
    setup,
)
from tests.conftest import upload


def sample(name: str, html: str) -> Sample:
    return Sample(name, html, {})


def bill(name: str, issuer: str, issued: date, amount: float, extra: str = "") -> Sample:
    return sample(
        name,
        f"""<h1>{issuer}</h1><h2>Facture d'électricité</h2>
        <p>Facture du {_fr(issued)} — N° client : 778 412</p>
        <table><tr><td>Total TTC à payer</td><td>{_money(amount)}</td></tr></table>
        <p>Prélevé le {_fr(issued + timedelta(days=15))}</p>{extra}""",
    )


@pytest.fixture
def demo(client: TestClient) -> dict[str, Any]:
    r = client.post("/api/demo")
    assert r.status_code == 200
    data: dict[str, Any] = r.json()
    return data


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


def feed_items(client: TestClient) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = client.get("/api/feed").json()["items"]
    return items


# --- Today feed, questions and undo ---------------------------------------------------------


def test_feed_lists_what_needs_the_user(client: TestClient, demo: dict[str, Any]) -> None:
    items = feed_items(client)
    kinds = {i["kind"] for i in items}
    # The demo's report comes first; the recovery code lives in Settings.
    assert items[0]["kind"] == "report" and "recovery" not in kinds
    assert {"report", "deadline", "expiry", "question"} <= kinds
    report = next(i for i in items if i["kind"] == "report")
    assert report["actions"][0] == {
        "type": "report",
        "label": "See what Binder did",
        "primary": True,
        "params": {"batch": demo["batch"]},
    }
    # Urgent cards before the rest.
    tones = [i["tone"] for i in items if i["kind"] not in ("report", "briefing")]
    assert tones == sorted(tones, key=feed.TONE_RANK.__getitem__)


def test_question_answered_in_one_tap(client: TestClient, demo: dict[str, Any]) -> None:
    question = next(i for i in feed_items(client) if i["kind"] == "question")
    # The garage quote: Binder does not know where it goes.
    assert question["title"].startswith("Where does")
    housing = next(a for a in question["actions"] if a["params"].get("choice") == "area:vehicle")
    r = client.post("/api/actions", json={"type": "answer", "params": housing["params"]})
    assert r.status_code == 200 and r.headers["X-Undo"]
    doc = client.get(f"/api/documents/{housing['params']['document_id']}").json()
    assert doc["category"] == "vehicle" and doc["area"] == "vehicle"
    assert doc["status"] == "classified"
    assert question["key"] not in {i["key"] for i in feed_items(client)}
    # Undo puts it back in question.
    assert client.post(f"/api/undo/{r.headers['X-Undo']}").status_code == 204
    doc = client.get(f"/api/documents/{doc['id']}").json()
    assert doc["category"] == "other" and doc["status"] == "to_review"
    # A token works once.
    assert client.post(f"/api/undo/{r.headers['X-Undo']}").status_code == 410


def test_amount_question_offers_the_amounts_of_the_document(client: TestClient) -> None:
    doc = upload(
        client,
        sample(
            "plombier.pdf",
            """<h1>Facture d'électricité</h1><p>EDF</p><p>Acompte 40,00</p>
            <p>Reste : 128,50</p>""",
        ),
    )
    item = next(
        i for i in feed_items(client) if i["kind"] == "question" and doc["id"] in i["document_ids"]
    )
    labels = [a["label"] for a in item["actions"]]
    assert "$128.50" in labels and "$40.00" in labels and "No amount" in labels


def test_every_change_can_be_undone(client: TestClient, demo: dict[str, Any]) -> None:
    docs = client.get("/api/documents").json()
    edf = next(d for d in docs if d["filename"] == "facture-edf.pdf")
    r = client.patch(f"/api/documents/{edf['id']}", json={"amount": 99.0})
    client.post(f"/api/undo/{r.headers['X-Undo']}")
    assert client.get(f"/api/documents/{edf['id']}").json()["amount"] == 94.37
    r = client.delete(f"/api/documents/{edf['id']}")
    assert client.get(f"/api/documents/{edf['id']}").status_code == 404
    client.post(f"/api/undo/{r.headers['X-Undo']}")
    assert client.get(f"/api/documents/{edf['id']}").status_code == 200
    deadline = next(i for i in feed_items(client) if i["kind"] == "deadline")
    pay = deadline["actions"][0]
    r = client.post("/api/actions", json={"type": pay["type"], "params": pay["params"]})
    assert deadline["key"] not in {i["key"] for i in feed_items(client)}
    client.post(f"/api/undo/{r.headers['X-Undo']}")
    assert deadline["key"] in {i["key"] for i in feed_items(client)}


def test_dismissed_cards_stay_hidden(client: TestClient, demo: dict[str, Any]) -> None:
    report = next(i for i in feed_items(client) if i["kind"] == "report")
    seen = report["actions"][1]
    client.post("/api/actions", json={"type": seen["type"], "params": seen["params"]})
    assert "report" not in {i["kind"] for i in feed_items(client)}
    assert client.post("/api/actions", json={"type": "explode"}).status_code == 400


# --- Import report --------------------------------------------------------------------------


def test_import_report_groups_a_drop_of_files(client: TestClient, samples: list[Sample]) -> None:
    for s in samples[:3]:
        r = client.post(
            "/api/documents?batch=drop1",
            files={"file": (s.filename, s.pdf(), "application/pdf")},
        )
        assert r.status_code == 201
    report = client.get("/api/reports/upload-drop1").json()
    assert report["source"] == "upload" and report["processing"] == 0
    assert len(report["items"]) == 3
    tax = report["items"][0]
    assert "Filed under Money" in tax["facts"]
    assert any(f.startswith("$1,240.00 to pay by") for f in tax["facts"])
    assert "documents filed" in report["summary"] and "to pay" in report["summary"]
    assert client.get("/api/reports/nothing").status_code == 404


# --- Life areas and household ---------------------------------------------------------------


def test_areas_and_household(client: TestClient, demo: dict[str, Any]) -> None:
    summary = {a["area"]: a for a in client.get("/api/areas").json()}
    assert list(summary) == list(areas.AREAS)
    assert summary["money"]["label"] == "Money" and summary["money"]["documents"] >= 2
    housing = client.get("/api/areas/housing").json()
    titles = {d["filename"] for d in housing["documents"]}
    # Home insurance lives with the home, not with money.
    assert {"facture-edf.pdf", "quittance-loyer.pdf", "maif-echeance.pdf"} <= titles
    assert any(s["label"] == "EDF" for s in housing["subscriptions"])
    assert client.get("/api/areas/garden").status_code == 404
    members = client.get("/api/household").json()
    assert members[0]["name"] == "Camille Martin" and members[0]["documents"] >= 3


def test_person_detection() -> None:
    assert household.detect("Nom : MARTIN — Prénom : Camille") == "Camille Martin"
    assert household.detect("Salarié : Paul DURAND\nPoste : technicien") == "Paul Durand"
    assert household.detect("Madame, Monsieur,\nM. Bernard est assuré") == "Bernard"
    assert household.same_person("Martin", "Camille Martin")
    assert household.addresses_in("situé 12 rue des Tilleuls, 69003 Lyon.") == [
        ("12 rue des Tilleuls", "69003 Lyon")
    ]


# --- Invisible learning ---------------------------------------------------------------------


def test_corrections_apply_to_the_next_documents_of_the_sender(client: TestClient) -> None:
    def note(name: str, issued: date, paid: float, rest: float) -> Sample:
        return sample(
            name,
            f"""<h1>Plomberie Dupuis</h1><p>Facture du {_fr(issued)}</p>
            <table><tr><td>Total des travaux</td><td>{_money(paid + rest)}</td></tr>
            <tr><td>Acompte versé</td><td>{_money(paid)}</td></tr>
            <tr><td>Reste à régler</td><td>{_money(rest)}</td></tr></table>""",
        )

    first = upload(client, note("dupuis-1.pdf", date(2026, 9, 1), 100, 150))
    assert first["amount"] == 250.0
    client.patch(
        f"/api/documents/{first['id']}",
        json={"category": "housing", "amount": 150.0, "issuer": "Plomberie Dupuis"},
    )
    second = upload(client, note("dupuis-2.pdf", date(2026, 9, 20), 60, 90))
    # Same sender: filed where the user put the first one, amount read after "reste à régler".
    assert second["category"] == "housing" and second["amount"] == 90.0
    assert second["issuer"] == "Plomberie Dupuis"
    history = client.get(f"/api/activity?document_id={second['id']}").json()
    assert any(a["action"] == "learned" for a in history)


# --- Anomalies and missing documents -------------------------------------------------------


def test_anomalies(client: TestClient, session: Session) -> None:
    upload(client, bill("edf-a.pdf", "EDF", date.today() - timedelta(days=12), 87.20))
    upload(client, bill("edf-b.pdf", "EDF", date.today() - timedelta(days=5), 87.20, "<p>.</p>"))
    upload(
        client,
        sample(
            "caf.pdf",
            f"""<h1>Caisse d'allocations familiales</h1><p>Fait le {_fr(date.today())}</p>
            <p>Numéro allocataire : 7788123</p>
            <p>Après examen de vos ressources, nous constatons un trop-perçu de 320,00 € d'aide
            au logement.</p>""",
        ),
    )
    upload(
        client,
        bill(
            "regul.pdf",
            "Engie",
            date.today() - timedelta(days=2),
            412.0,
            "<p>Facture de régularisation annuelle</p>",
        ),
    )
    found = {a.kind: a for a in anomalies.detect(session)}
    assert found["double_payment"].amount == 87.20
    assert found["overpayment_claim"].amount == 320.0
    assert found["catch_up"].amount == 412.0
    assert "instalments" in (found["overpayment_claim"].letter or "")
    cards = [i for i in feed_items(client) if i["kind"] == "anomaly"]
    claim = next(c for c in cards if c["key"].startswith("anomaly:claim"))
    assert claim["tone"] == "urgent" and claim["actions"][0]["type"] == "letter"


def test_missing_documents(client: TestClient, session: Session) -> None:
    today = date.today()
    for n in (150, 120, 90):
        upload(client, bill(f"sfr-{n}.pdf", "SFR", today - timedelta(days=n), 25.0))
    found = {m.key.split(":")[0]: m for m in missing.detect(session)}
    late = found["late"]
    assert "SFR" in late.title and late.area == "housing"
    for n, month in ((1, 5), (2, 7)):
        upload(
            client,
            sample(
                f"paie-{n}.pdf",
                f"""<h1>Bulletin de paie</h1><p>Employeur : Atelier SAS</p>
                <p>Édité le {_fr(date(2026, month, 28))}</p>
                <table><tr><td>Net à payer</td><td>{_money(2000)}</td></tr></table>""",
            ),
        )
    gaps = [m for m in missing.detect(session) if m.key.startswith("payslip")]
    assert [m.expected for m in gaps] == [date(2026, 6, 1)]


def test_demo_tells_a_french_household_story(
    client: TestClient, demo: dict[str, Any], session: Session
) -> None:
    # Each part of the agent has something to show on the demo documents.
    kinds = {(a.kind, a.title) for a in anomalies.detect(session)}
    assert ("overpayment_claim", "CAF claims an overpayment") in kinds
    assert ("double_payment", "Debited twice: ORANGE") in kinds
    assert any(kind == "price_increase" and "EDF" in title for kind, title in kinds)
    assert [m.key for m in missing.detect(session)] == ["essential:rib"]
    names = {m.name for m in household.members(session)}
    assert {"Camille Martin", "Thomas Martin", "Hugo Martin"} <= names
    assert household.main_person(session) == "Camille Martin"
    assert household.home_address(session) == ("12 rue des Tilleuls", "69003 Lyon")
    deadlines = client.get("/api/deadlines").json()
    assert deadlines[0]["amount"] == 1240.0


# --- Letters --------------------------------------------------------------------------------


def test_letter_in_words_pdf_and_follow_up(client: TestClient, demo: dict[str, Any]) -> None:
    edf = next(d for d in client.get("/api/documents").json() if d["filename"] == "facture-edf.pdf")
    r = client.post(
        "/api/letters",
        json={"purpose": "Ask why the meter reading was estimated", "document_id": edf["id"]},
    )
    letter = r.json()
    assert letter["id"] and letter["recipient"] == "EDF" and letter["kind"] == "custom"
    assert "in order to ask why the meter reading was estimated" in letter["body"]
    assert "Camille Martin" in letter["body"]
    pdf = client.get(f"/api/letters/{letter['id']}/pdf")
    assert pdf.content[:4] == b"%PDF" and "attachment" in pdf.headers["content-disposition"]
    assert client.post(f"/api/letters/{letter['id']}/follow-up").status_code == 409
    sent = client.post(f"/api/letters/{letter['id']}/sent").json()
    assert sent["follow_up_on"] == (date.today() + timedelta(days=21)).isoformat()
    deadlines = client.get("/api/deadlines?end=2099-01-01").json()
    assert any(d["source"] == "followup" for d in deadlines)
    followup = client.post(f"/api/letters/{letter['id']}/follow-up").json()
    assert followup["subject"].startswith("Reminder:") and followup["registered"]
    client.post(f"/api/letters/{letter['id']}/answered")
    assert not any(
        d["source"] == "followup" for d in client.get("/api/deadlines?end=2099-01-01").json()
    )
    assert client.post("/api/letters", json={}).status_code == 400


def test_reimported_letter_is_flagged_not_received(
    client: TestClient, demo: dict[str, Any]
) -> None:
    letter = client.post("/api/letters", json={"purpose": "Ask for a duplicate certificate"}).json()
    pdf = client.get(f"/api/letters/{letter['id']}/pdf").content
    r = client.post("/api/documents", files={"file": ("lettre.pdf", pdf, "application/pdf")})
    assert r.status_code == 201
    doc = client.get(f"/api/documents/{r.json()['id']}").json()
    assert doc["source_letter_id"] == letter["id"]


def test_delete_letter_is_undoable(client: TestClient, demo: dict[str, Any]) -> None:
    letter = client.post("/api/letters", json={"purpose": "Ask for a duplicate certificate"}).json()
    r = client.delete(f"/api/letters/{letter['id']}")
    assert r.status_code == 204 and r.headers["X-Undo"]
    assert client.get(f"/api/letters/{letter['id']}").status_code == 404
    assert client.post(f"/api/undo/{r.headers['X-Undo']}").status_code == 204
    restored = client.get(f"/api/letters/{letter['id']}").json()
    assert restored["subject"] == letter["subject"]


def test_follow_up_and_reply_cards(
    client: TestClient, demo: dict[str, Any], session: Session
) -> None:
    r = client.post("/api/letters", json={"kind": "complaint", "purpose": "x"})
    row = session.get(Correspondence, r.json()["id"])
    assert row is not None
    row.sent_on = date.today() - timedelta(days=30)
    row.follow_up_on = date.today() - timedelta(days=2)
    session.add(row)
    session.commit()
    card = next(i for i in feed_items(client) if i["key"] == f"followup:{row.id}")
    assert card["actions"][0]["type"] == "follow_up"
    r = client.post("/api/actions", json={"type": "follow_up", "params": {"letter_id": row.id}})
    assert r.json()["letter"]["kind"] == "followup"


# --- Packs ----------------------------------------------------------------------------------


def test_pack_for_any_purpose_is_exported(client: TestClient, demo: dict[str, Any]) -> None:
    standard = client.post("/api/folders/prepare", json={"purpose": "dossier de location"}).json()
    assert standard["key"] == "rental"
    custom = client.post("/api/folders/prepare", json={"purpose": "contrôle technique"}).json()
    assert custom["key"].startswith("custom-")
    labels = [p["label"] for p in custom["pieces"]]
    assert labels[0] == "Valid identity document" and "Roadworthiness test" in labels
    archive = client.get(f"/api/folders/{custom['key']}/export")
    names = zipfile.ZipFile(io.BytesIO(archive.content)).namelist()
    assert any("controle" in n.lower() or "test" in n.lower() for n in names)
    assert client.get("/api/folders/custom-unknown").status_code == 404


# --- Sources --------------------------------------------------------------------------------


def test_sources_of_each_figure(client: TestClient, demo: dict[str, Any]) -> None:
    tax = next(
        d for d in client.get("/api/documents").json() if d["filename"] == "avis-imposition.pdf"
    )
    found = {
        s["field"]: s["boxes"] for s in client.get(f"/api/documents/{tax['id']}/sources").json()
    }
    assert {"amount", "due_date", "issue_date", "reference"} <= found.keys()
    box = found["amount"][0]
    assert box["page"] == 0 and 0 < box["x0"] < box["x1"] <= 1 and 0 < box["y0"] < box["y1"] <= 1


# --- Briefing and notifications --------------------------------------------------------------


def test_weekly_briefing(demo: dict[str, Any], session: Session) -> None:
    new = briefing.ensure(session)
    assert new is not None and new.title.startswith("Your week of")
    assert "this week" in new.text or "Nothing to pay" in new.text
    assert briefing.ensure(session) is None
    assert briefing.current(session) is not None


def test_notifications_are_sent_once(
    demo: dict[str, Any], session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from binder.services import background

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(notify, "send", lambda title, body: sent.append((title, body)) or True)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    session.add(Deadline(title="Pay the canteen", due_date=date.fromisoformat(tomorrow)))
    session.commit()
    first = background.alerts(session)
    assert first and len(sent) == first
    assert any(title == "Pay the canteen" for title, _ in sent)
    assert background.alerts(session) == 0


def test_notification_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notify.sys, "platform", "darwin")
    command = notify._command("Title", 'Body "quoted"')
    assert command is not None and command[0][-2:] == ["Title", 'Body "quoted"']


# --- Backups --------------------------------------------------------------------------------


def test_backup_and_restore_with_the_recovery_code(
    client: TestClient, demo: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BINDER_BACKUP_DIR", str(tmp_path / "backups"))
    get_settings.cache_clear()
    code = client.get("/api/backup").json()["code"]
    info = client.post("/api/backup/now").json()
    archives = list((tmp_path / "backups").glob("*.binderbackup"))
    assert len(archives) == 1 and info["last_backup"]
    names = zipfile.ZipFile(archives[0]).namelist()
    assert "binder.db" in names and "recovery.json" in names
    # Nothing readable in the archive: the database is SQLCipher, the files Fernet.
    assert b"SQLite format 3" not in zipfile.ZipFile(archives[0]).read("binder.db")[:16]

    # A new computer: empty data folder, another key.
    monkeypatch.setenv("BINDER_DATA_DIR", str(tmp_path / "new"))
    get_settings.cache_clear()
    reset_engine()
    from binder.main import create_app

    with TestClient(create_app(), base_url="http://127.0.0.1") as fresh:
        bad = fresh.post(
            "/api/backup/restore",
            files={"file": ("b.binderbackup", archives[0].read_bytes())},
            data={"code": "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF"},
        )
        assert bad.status_code == 400
        ok = fresh.post(
            "/api/backup/restore",
            files={"file": ("b.binderbackup", archives[0].read_bytes())},
            data={"code": code.lower()},
        )
        assert ok.status_code == 204, ok.text
        docs = fresh.get("/api/documents").json()
        assert len(docs) == demo["imported"]
        edf = next(d for d in docs if d["filename"] == "facture-edf.pdf")
        assert fresh.get(f"/api/documents/{edf['id']}/file").content[:4] == b"%PDF"
        # The library is no longer empty: a second restore is refused.
        again = fresh.post(
            "/api/backup/restore",
            files={"file": ("b.binderbackup", archives[0].read_bytes())},
            data={"code": code},
        )
        assert again.status_code == 409


def test_backup_runs_once_a_day_when_something_changed(
    demo: dict[str, Any], session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BINDER_BACKUP_DIR", str(tmp_path / "b"))
    get_settings.cache_clear()
    assert backup.due(session)
    assert backup.run_if_due(session) is not None
    assert not backup.due(session)
    code = backup.new_code()
    assert len(code) == 29 and set(code.replace("-", "")) <= set(backup.ALPHABET)


# --- Local AI setup -------------------------------------------------------------------------


def test_model_suits_the_machine() -> None:
    gb = setup.GB
    assert setup.pick_model(8 * gb, 0, 500 * gb) == "qwen3.5:2b"
    assert setup.pick_model(12 * gb, 0, 500 * gb) == "qwen3.5:4b"
    assert setup.pick_model(16 * gb, 0, 500 * gb) == "qwen3.5:9b"
    assert setup.pick_model(32 * gb, 24 * gb, 500 * gb) == "qwen3.5:27b"
    # Not enough room for the 9B: the next smaller one.
    assert setup.pick_model(16 * gb, 0, 5 * gb) == "qwen3.5:4b"
    assert setup.pick_model(16 * gb, 0, 1 * gb) is None
    assert setup.asset_name("linux", "x86_64") == "ollama-linux-amd64.tar.zst"
    assert setup.asset_name("win32", "amd64") == "ollama-windows-amd64.zip"
    assert setup.asset_name("darwin", "arm64") == "ollama-darwin.tgz"


def fake_ollama(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Serves a tiny Ollama release archive; returns the URLs asked for."""
    import hashlib

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        script = b"#!/bin/sh\necho ollama\n"
        info = tarfile.TarInfo("bin/ollama")
        info.size, info.mode = len(script), 0o755
        tar.addfile(info, io.BytesIO(script))
    archive = zstandard.ZstdCompressor().compress(raw.getvalue())
    asked: list[str] = []

    def serve(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(200, content=archive)

    updater.transport = httpx.MockTransport(serve)
    setup._state.stop.clear()
    sha = hashlib.sha256(archive).hexdigest()
    monkeypatch.setattr(setup, "_asset", lambda: ("ollama-linux-amd64.tar.zst", sha))
    monkeypatch.setattr(setup, "_executable_name", lambda: "ollama")
    return asked


def test_ollama_is_installed_from_its_pinned_release(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = fake_ollama(monkeypatch)
    binary = setup._install(setup.managed_dir(), foreground=True)
    assert binary == setup.managed_dir() / "bin" / "ollama"
    assert asked == [
        f"https://github.com/ollama/ollama/releases/download/{setup.OLLAMA_VERSION}/"
        "ollama-linux-amd64.tar.zst"
    ]
    assert setup.installed_version(setup.managed_dir()) == setup.OLLAMA_VERSION
    # Windows has no executable bit: it goes by the file extension.
    assert sys.platform == "win32" or binary.stat().st_mode & 0o100


def test_corrupted_ollama_download_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_ollama(monkeypatch)
    monkeypatch.setattr(setup, "_asset", lambda: ("ollama-linux-amd64.tar.zst", "0" * 64))
    with pytest.raises(RuntimeError):
        setup._install(setup.managed_dir(), foreground=True)
    assert not setup.managed_dir().exists()
    assert not setup.managed_dir().with_name("ollama.partial").exists()


def test_pinned_ollama_takes_over_at_next_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_ollama(monkeypatch)
    old = setup.managed_dir() / "ollama"
    old.parent.mkdir(parents=True)
    old.write_text("old")
    # In use this session: the pinned version is fetched next to it, not over it.
    setup._upgrade()
    assert old.read_text() == "old"
    assert setup.installed_version(setup._next_dir()) == setup.OLLAMA_VERSION
    setup._apply_upgrade()
    assert setup.installed_version(setup.managed_dir()) == setup.OLLAMA_VERSION
    assert setup.find_ollama() == setup.managed_dir() / "bin" / "ollama"
    assert not setup._next_dir().exists()
    assert not setup.managed_dir().with_name("ollama.old").exists()


def test_models_of_the_users_ollama_are_linked(tmp_path: Path) -> None:
    source, target = tmp_path / "user-models", tmp_path / "binder-models"
    manifest = source / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5" / "9b"
    blob = source / "blobs" / "sha256-abc"
    for path, text in ((manifest, "{}"), (blob, "weights")):
        path.parent.mkdir(parents=True)
        path.write_text(text)
    assert setup.adopt_models(source, target)
    linked = target / "blobs" / "sha256-abc"
    assert linked.read_text() == "weights"
    assert linked.stat().st_nlink == 2  # the same file: no disk space used
    assert blob.read_text() == "weights"
    assert (target / manifest.relative_to(source)).is_file()


def test_binder_runs_its_own_ollama(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-user-models"))
    monkeypatch.setenv("BINDER_LLM_ENABLED", "true")
    monkeypatch.setenv("BINDER_AUTO_SETUP", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(setup, "_state", setup._State())
    monkeypatch.setattr(setup, "_run", lambda: None)
    setup.start()
    url = httpx.URL(get_settings().ollama_url)
    assert url.host == "127.0.0.1" and url.port != 11434
    assert setup._owned()
    assert setup._models_dir() == get_settings().data_dir / "models"


def test_an_ollama_chosen_by_the_user_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINDER_LLM_ENABLED", "true")
    monkeypatch.setenv("BINDER_AUTO_SETUP", "true")
    monkeypatch.setenv("BINDER_OLLAMA_URL", "http://localhost:11434")
    get_settings.cache_clear()
    monkeypatch.setattr(setup, "_state", setup._State())
    monkeypatch.setattr(setup, "_run", lambda: None)
    setup.start()
    assert get_settings().ollama_url == "http://localhost:11434"
    assert not setup._owned()


def test_setup_status_without_ai() -> None:
    assert setup.status().phase == "disabled"


# --- Agent without a model ------------------------------------------------------------------


def ask(client: TestClient, message: str) -> dict[str, Any]:
    data: dict[str, Any] = client.post("/api/agent/chat", json={"message": message}).json()
    return data


def test_agent_alerts_letters_folders_and_undo(client: TestClient, demo: dict[str, Any]) -> None:
    letter = ask(client, "Écris un courrier à EDF pour demander un échéancier")
    assert letter["letters"] and letter["undo"] and letter["changed"]
    assert "write_letter" in {c["name"] for c in letter["tool_calls"]}
    pack = ask(client, "Prépare le dossier pour la crèche")
    assert pack["folders"] and pack["tool_calls"][-1]["name"] == "prepare_folder"
    alerts = ask(client, "Y a-t-il des anomalies ?")
    assert alerts["tool_calls"][-1]["name"] == "list_alerts"
    reminder = ask(client, "Rappelle-moi d'appeler le garage le 12/11/2027")
    assert reminder["undo"]
    undone = ask(client, "Annule ça")
    assert undone["tool_calls"][-1]["name"] == "undo_last_action"
    assert not any(
        d["title"].startswith("D'appeler") or "garage" in d["title"].lower()
        for d in client.get("/api/deadlines?end=2099-01-01").json()
    )


def test_areas_of_insurance() -> None:
    doc = Document(
        filename="a.pdf",
        mime_type="application/pdf",
        size=1,
        sha256="x",
        stored_name="x",
        title="Avis d'échéance",
        category=Category.INSURANCE,
        text="Assurance auto — véhicule AB-123-CD",
    )
    assert areas.area_of(doc) == "vehicle"
    doc.text = "Contrat santé"
    assert areas.area_of(doc) == "money"


def test_deadline_and_document_states(session: Session, demo: dict[str, Any]) -> None:
    open_deadlines = session.exec(select(Deadline).where(Deadline.done == False)).all()  # noqa: E712
    assert open_deadlines
    reviewed = session.exec(select(Document).where(Document.status == DocumentStatus.TO_REVIEW))
    assert all(d.area is None or d.category != Category.OTHER for d in reviewed)


def test_recovery_code_is_shown_in_settings_until_noted(client: TestClient) -> None:
    info = client.get("/api/backup").json()
    assert len(info["code"]) == 29 and not info["confirmed"]
    noted = client.post("/api/backup/confirm").json()
    assert noted["code"] is None and noted["confirmed"]
    renewed = client.post("/api/backup/code").json()
    assert renewed["code"] and renewed["code"] != info["code"] and not renewed["confirmed"]


def test_demo_data_can_be_cleared(client: TestClient, demo: dict[str, Any]) -> None:
    assert client.get("/api/demo").json()["documents"] == demo["imported"]
    assert client.delete("/api/demo").json()["removed"] == demo["imported"]
    assert client.get("/api/demo").json()["documents"] == 0
    assert not client.get("/api/documents").json()
    assert not client.get("/api/deadlines").json()
    assert client.get("/api/activity").json()[0]["summary"] == (
        f"Demo data cleared ({demo['imported']} documents)"
    )


def test_profile_notes_reach_the_agent(client: TestClient, session: Session) -> None:
    from binder.agent import tools

    body = {"name": "Camille Martin", "notes": "Tenant, two children, self-employed."}
    assert client.put("/api/profile", json=body).json()["notes"] == body["notes"]
    user = tools.overview(session)["user"]
    assert user["about"] == body["notes"] and user["name"] == "Camille Martin"


def test_profile_is_completed_from_the_documents(client: TestClient, demo: dict[str, Any]) -> None:
    learned = client.get("/api/profile").json()
    assert learned["name"] == "Camille Martin" and learned["city"] == "Lyon"
    assert learned["address"].startswith("12 rue des Tilleuls")
    assert set(learned["auto"]) == {"name", "address", "city"}
    # What the user types is theirs: Binder no longer touches it.
    mine = client.put("/api/profile", json={**learned, "name": "Camille Martin-Durand"}).json()
    assert "name" not in mine["auto"] and "address" in mine["auto"]
    client.delete("/api/demo")
    after = client.get("/api/profile").json()
    assert after["name"] == "Camille Martin-Durand"
    assert after["address"] == "" and after["auto"] == []


def test_own_contact_details_appear_with_several_issuers(session: Session) -> None:
    from binder.models import Document
    from binder.services import household

    def doc(n: int, issuer: str, text: str) -> Document:
        return Document(
            filename=f"{n}.pdf", mime_type="application/pdf", size=1, sha256=str(n),
            stored_name=str(n), issuer=issuer, text=text,
        )  # fmt: skip

    session.add(
        doc(1, "EDF", "Client : camille@example.org, 06 12 34 56 78. service-client@edf.fr")
    )
    session.add(doc(2, "Orange", "camille@example.org - tél. 06.12.34.56.78 - 01 40 00 00 00"))
    session.add(doc(3, "EDF", "Contact : 07 99 99 99 99, contact@edf.fr"))
    session.flush()
    assert household.contact_details(session) == {
        "email": "camille@example.org",
        "phone": "06 12 34 56 78",
    }


def test_agent_saves_what_the_user_tells_about_themselves(session: Session) -> None:
    from binder.agent import tools

    result = tools.call(session, "update_profile", {"phone": "06 11 22 33 44", "note": "Tenant."})
    assert result.changed and result.payload["phone"] == "06 11 22 33 44"
    tools.call(session, "update_profile", {"note": "Two children."})
    user = tools.overview(session)["user"]
    assert user["about"].splitlines() == ["Tenant.", "Two children."]
    assert "phone" not in user["unknown"]
