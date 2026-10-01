"""Protection du serveur local : rebinding DNS, requêtes intersites, jeton, IMAP."""

import ssl
from typing import Any

import pytest
from fastapi.testclient import TestClient

from binder.config import get_settings
from binder.services import importers


def test_rejects_foreign_host(client: TestClient) -> None:
    # Rebinding DNS : un domaine piégé résolu en 127.0.0.1.
    r = client.get("/api/stats", headers={"Host": "evil.example:8765"})
    assert r.status_code == 400
    for host in ("localhost:8765", "127.0.0.1", "[::1]:8765"):
        assert client.get("/api/stats", headers={"Host": host}).status_code == 200


def test_rejects_cross_origin_writes(client: TestClient) -> None:
    r = client.post("/api/demo", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/api/demo", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    # Lecture déclenchée par un autre site (lien, image) : refusée aussi.
    r = client.get("/api/export", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert client.get("/api/stats", headers={"Origin": "http://127.0.0.1"}).status_code == 200


def test_accepts_same_origin_writes(client: TestClient) -> None:
    r = client.post(
        "/api/import/run",
        headers={"Origin": "http://127.0.0.1", "Sec-Fetch-Site": "same-origin"},
    )
    assert r.status_code == 200
    # Proxy de Vite : Host et Origin désignent tous deux le serveur de dev.
    r = client.post(
        "/api/import/run",
        headers={"Host": "localhost:5173", "Origin": "http://localhost:5173"},
    )
    assert r.status_code == 200


def test_security_headers(client: TestClient) -> None:
    r = client.get("/api/stats")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "sandbox" in r.headers["Content-Security-Policy"]


def test_access_token(client: TestClient) -> None:
    get_settings().access_token = "s3cret"
    assert client.get("/api/stats").status_code == 401
    assert client.get("/?token=wrong", follow_redirects=False).status_code == 403
    r = client.get("/?token=s3cret&x=1", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/?x=1"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert client.get("/api/stats").status_code == 200


def test_imap_verifies_certificate(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake(host: str, port: int, ssl_context: ssl.SSLContext | None = None) -> Any:
        seen["context"] = ssl_context
        raise OSError("stop")

    monkeypatch.setattr(importers.imaplib, "IMAP4_SSL", fake)
    with pytest.raises(OSError):
        importers.fetch_mail(None, importers.MailConfig(host="imap.test"))  # type: ignore[arg-type]
    context = seen["context"]
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


def test_rejects_imap_injection(client: TestClient) -> None:
    for field, value in (("folder", 'INBOX" x'), ("user", "me\r\nA1 LOGOUT"), ("host", "a b")):
        mail = {"enabled": False, "host": "imap.test", "user": "me", field: value}
        assert client.put("/api/import/settings", json={"mail": mail}).status_code == 422
