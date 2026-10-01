import os
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from binder.db import get_engine
from binder.samples import Sample
from binder.services import importers


@pytest.fixture(autouse=True)
def forget_seen_files() -> None:
    importers._seen.clear()


def by_name(samples: list[Sample], name: str) -> Sample:
    return next(s for s in samples if s.filename == name)


def drop(folder: Path, name: str, data: bytes) -> Path:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    old = time.time() - 60
    os.utime(path, (old, old))
    return path


def test_watched_folder_imports_once_and_leaves_files(
    client: TestClient, samples: list[Sample], tmp_path: Path
) -> None:
    inbox = tmp_path / "scans"
    inbox.mkdir()
    r = client.put("/api/import/settings", json={"folder": {"enabled": True, "path": str(inbox)}})
    assert r.status_code == 200
    drop(inbox, "taxe.pdf", by_name(samples, "taxe-fonciere.pdf").pdf())
    drop(inbox, "2026/orange.pdf", by_name(samples, "facture-orange.pdf").pdf())
    drop(inbox, ".cache/ignore.pdf", by_name(samples, "facture-edf.pdf").pdf())
    drop(inbox, "notes.txt", b"not a document")
    fresh = drop(inbox, "en-cours.pdf", by_name(samples, "attestation-caf.pdf").pdf())
    os.utime(fresh)  # just arrived: may still be being copied

    assert client.post("/api/import/run").json()["folder"] == {"imported": 2, "error": None}
    docs = client.get("/api/documents").json()
    assert {d["category"] for d in docs} == {"taxes", "telecom"}
    assert all(d["status"] != "processing" for d in docs)
    assert (inbox / "taxe.pdf").exists()

    # Second pass: nothing new, except the file that is now stable.
    os.utime(fresh, (time.time() - 60, time.time() - 60))
    assert client.post("/api/import/run").json()["folder"]["imported"] == 1

    log = client.get("/api/activity").json()
    imports = [e for e in log if e["action"] == "import"]
    assert all(e["actor"] == "watcher" for e in imports)
    assert any("watched folder (2026/orange.pdf)" in e["summary"] for e in imports)


def test_trashed_document_is_not_reimported_from_folder(
    client: TestClient, samples: list[Sample], tmp_path: Path
) -> None:
    drop(tmp_path / "in", "taxe.pdf", by_name(samples, "taxe-fonciere.pdf").pdf())
    client.put(
        "/api/import/settings", json={"folder": {"enabled": True, "path": str(tmp_path / "in")}}
    )
    client.post("/api/import/run")
    [doc] = client.get("/api/documents").json()
    client.delete(f"/api/documents/{doc['id']}")
    importers._seen.clear()  # application restart
    assert client.post("/api/import/run").json()["folder"]["imported"] == 0
    assert client.get("/api/documents").json() == []


def test_folder_must_exist_to_be_enabled(client: TestClient, tmp_path: Path) -> None:
    r = client.put(
        "/api/import/settings", json={"folder": {"enabled": True, "path": str(tmp_path / "nope")}}
    )
    assert r.status_code == 400


def mail_with(pdf: bytes, *, logo: bytes = b"\x89PNG small") -> bytes:
    msg = EmailMessage()
    msg["From"] = "EDF <facture@edf.fr>"
    msg["Subject"] = "Votre facture est disponible"
    msg.set_content("Bonjour, votre facture est jointe.")
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename="facture.pdf")
    msg.add_attachment(logo, maintype="image", subtype="png", filename="logo.png")
    return msg.as_bytes()


class FakeImap:
    """Minimal IMAP server: messages {uid: bytes}, checks read-only access."""

    def __init__(self, messages: dict[int, bytes], uidvalidity: int = 7) -> None:
        self.messages = messages
        self.uidvalidity = uidvalidity
        self.searches: list[str] = []
        self.readonly: bool | None = None

    def __call__(self, host: str, port: int) -> "FakeImap":
        return self

    def login(self, user: str, password: str) -> None:
        assert password == "secret"

    def select(self, folder: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.readonly = readonly
        return "OK", [str(len(self.messages)).encode()]

    def response(self, code: str) -> tuple[str, list[bytes]]:
        return code, [str(self.uidvalidity).encode()]

    def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
        if command == "SEARCH":
            criteria = args[1]
            self.searches.append(criteria)
            if criteria.startswith("(UID"):
                first = int(criteria[5:].split(":")[0])
                uids = [u for u in self.messages if u >= first]
            else:
                uids = list(self.messages)
            return "OK", [" ".join(map(str, uids)).encode()]
        assert command == "FETCH" and "PEEK" in args[1]
        return "OK", [(b"1 (BODY[] {n})", self.messages[int(args[0])]), b")"]

    def logout(self) -> None:
        pass


def test_mail_attachments_are_imported_without_marking_read(
    client: TestClient, samples: list[Sample]
) -> None:
    fake = FakeImap({41: mail_with(by_name(samples, "facture-edf.pdf").pdf())})
    r = client.put(
        "/api/import/settings",
        json={"mail": {"enabled": True, "host": "imap.test", "user": "me", "password": "secret"}},
    )
    settings = r.json()["mail"]
    assert settings["password_set"] is True
    assert "password" not in settings

    with Session(get_engine()) as session:
        cfg = importers.MailConfig(
            enabled=True, host="imap.test", user="me", password="secret", folder="INBOX"
        )
        [doc] = importers.fetch_mail(session, cfg, factory=fake)
        assert fake.readonly is True
        assert fake.searches[0].startswith("(SINCE ")
        assert doc.issuer == "EDF"
        assert cfg.last_uid == 41

        # New message: only the following UIDs are requested; the logo is ignored.
        fake.messages[42] = mail_with(by_name(samples, "facture-orange.pdf").pdf())
        [second] = importers.fetch_mail(session, cfg, factory=fake)
        assert fake.searches[-1] == "(UID 42:*)"
        assert second.issuer == "Orange"

    log = client.get("/api/activity").json()
    assert any(
        e["actor"] == "mail" and "the email “Votre facture est disponible”" in e["summary"]
        for e in log
    )


def test_mail_error_is_reported_once(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(host: str, port: int, **_: Any) -> Any:
        raise OSError("connection refused")

    monkeypatch.setattr(importers.imaplib, "IMAP4_SSL", refuse)
    client.put(
        "/api/import/settings",
        json={"mail": {"enabled": True, "host": "imap.test", "user": "me", "password": "x"}},
    )
    for _ in range(2):
        assert client.post("/api/import/run").json()["mail"]["error"] == "connection refused"
    assert client.get("/api/import/settings").json()["mail"]["last_error"] == "connection refused"
    errors = [e for e in client.get("/api/activity").json() if e["action"] == "import_error"]
    assert len(errors) == 1


def test_import_origin_follows_display_language(
    client: TestClient, samples: list[Sample], tmp_path: Path
) -> None:
    drop(tmp_path / "in", "taxe.pdf", by_name(samples, "taxe-fonciere.pdf").pdf())
    client.put(
        "/api/import/settings", json={"folder": {"enabled": True, "path": str(tmp_path / "in")}}
    )
    client.post("/api/import/run")
    # The entry was written in English; it is displayed in French once the user switches.
    client.put("/api/preferences", json={"language": "fr", "country": "FR", "theme": "system"})
    imports = [e for e in client.get("/api/activity").json() if e["action"] == "import"]
    assert any("depuis le dossier surveillé (taxe.pdf)" in e["summary"] for e in imports)
