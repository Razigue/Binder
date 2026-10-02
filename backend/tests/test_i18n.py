"""Internationalisation: locale parsing, formatting, catalogs, preferences and DB migration."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from binder import db, i18n
from binder.models import Category, Deadline, Document

T = i18n.catalog(
    "test_i18n",
    {
        "files_one": {"en": "{n} file", "fr": "{n} fichier"},
        "files_other": {"en": "{n} files", "fr": "{n} fichiers"},
        "due": {
            "en": "{amount:money} due on {when:date} ({category:category})",
            "fr": "{amount:money} à régler le {when:date} ({category:category})",
        },
    },
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("fr_FR.UTF-8", ("fr", "FR")),
        ("fr-FR", ("fr", "FR")),
        ("en_US", ("en", "US")),
        ("fr", ("fr", None)),
        ("zh-Hant-TW", ("zh", "TW")),
        ("C", (None, None)),
        ("POSIX", (None, None)),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_locale(value: str | None, expected: tuple[str | None, str | None]) -> None:
    assert i18n.parse_locale(value) == expected


def test_system_locale_follows_override(monkeypatch: pytest.MonkeyPatch) -> None:
    assert i18n.system_locale() == ("en", "US")
    monkeypatch.setenv("BINDER_LOCALE", "fr_BE")
    from binder.config import get_settings

    get_settings.cache_clear()
    i18n.system_locale.cache_clear()
    assert i18n.system_locale() == ("fr", "BE")


def test_unsupported_language_falls_back_to_english(monkeypatch: pytest.MonkeyPatch) -> None:
    from binder.config import get_settings

    monkeypatch.setenv("BINDER_LOCALE", "de_DE")
    get_settings.cache_clear()
    i18n.system_locale.cache_clear()
    assert i18n.system_locale() == ("en", "DE")


def test_format_money() -> None:
    assert i18n.format_money(1240, "en", "EUR") == "€1,240.00"
    assert i18n.format_money(1240, "fr", "EUR") == f"1{i18n.NBSP}240,00 €"
    assert i18n.format_money(-5.5, "en", "USD") == "-$5.50"
    assert i18n.format_money(12, "en", "CHF") == "CHF 12.00"
    assert i18n.format_money(None, "en") == "—"


def test_format_date() -> None:
    assert i18n.format_date(date(2026, 10, 15), "en") == "15 Oct 2026"
    assert i18n.format_date(date(2026, 10, 15), "fr") == "15/10/2026"
    assert i18n.format_date("2026-10-15", "fr") == "15/10/2026"
    assert i18n.format_date(None, "en") == "—"


def test_currency_follows_country() -> None:
    assert i18n.currency_for("FR") == "EUR"
    assert i18n.currency_for("us") == "USD"
    assert i18n.currency_for(None) == i18n.DEFAULT_CURRENCY


def test_letter_language() -> None:
    assert i18n.letter_language("FR", "en") == "fr"
    assert i18n.letter_language("GB", "en") == "en"
    assert i18n.letter_language(None, "fr") == "fr"


def test_catalog_plural() -> None:
    assert T.plural("files", 1) == "1 file"
    assert T.plural("files", 0) == "0 files"
    assert T.plural("files", 3) == "3 files"
    with i18n.using("fr"):
        # French: 0 and 1 are singular.
        assert T.plural("files", 0) == "0 fichier"
        assert T.plural("files", 1) == "1 fichier"
        assert T.plural("files", 2) == "2 fichiers"


def test_catalog_requires_every_language() -> None:
    with pytest.raises(ValueError, match="missing"):
        i18n.catalog("test_i18n_incomplete", {"x": {"en": "only English"}})  # type: ignore[dict-item]


def test_msg_json_round_trip_renders_in_another_language(monkeypatch: pytest.MonkeyPatch) -> None:
    from binder.config import get_settings

    # English speaker living in France: amounts in euros.
    monkeypatch.setenv("BINDER_LOCALE", "en_FR")
    get_settings.cache_clear()
    i18n.system_locale.cache_clear()
    msg = T.msg("due", amount=1240, when=date(2026, 10, 15), category=Category.TAXES)
    stored = json.loads(json.dumps(msg.to_json()))
    restored = i18n.Msg(stored["key"], stored["params"])
    assert restored.render("en") == "€1,240.00 due on 15 Oct 2026 (Taxes)"
    assert restored.render("fr") == (f"1{i18n.NBSP}240,00 € à régler le 15/10/2026 (Impôts)")


def test_labels() -> None:
    assert i18n.category_label("taxes", "fr") == "Impôts"
    assert i18n.doc_type_label("invoice", "en") == "Invoice"
    assert i18n.doc_type_label("invoice", "fr") == "Facture"
    assert i18n.field_label("amount", "fr") == "le montant"
    # Unknown values from a newer version stay readable.
    assert i18n.doc_type_label("something_new", "en") == "something_new"


def test_preferences_api(client: TestClient) -> None:
    prefs = client.get("/api/preferences").json()
    assert prefs["language"] == "auto"
    assert prefs["system_language"] == "en"
    assert prefs["system_country"] == "US"
    assert prefs["effective_language"] == "en"
    assert prefs["currency"] == "USD"

    r = client.put("/api/preferences", json={"language": "fr", "country": "fr", "theme": "dark"})
    assert r.status_code == 200, r.text
    prefs = r.json()
    assert prefs["effective_language"] == "fr"
    assert prefs["effective_country"] == "FR"
    assert prefs["currency"] == "EUR"
    assert client.get("/api/preferences").json()["theme"] == "dark"
    # Saved without a text size: the default one.
    assert prefs["text_size"] == "normal"
    assert i18n.current_language() == "fr"

    # HTTP errors follow the chosen language.
    assert client.get("/api/documents/999").json()["detail"] == "Document introuvable"

    r = client.put("/api/preferences", json={"language": "fr", "country": "FRA"})
    assert r.status_code == 422


def test_activity_summary_in_current_language(client: TestClient) -> None:
    r = client.post("/api/deadlines", json={"title": "Water bill", "due_date": "2026-10-15"})
    assert r.status_code == 201, r.text
    entry = client.get("/api/activity").json()[0]
    assert entry["summary"] == "Reminder “Water bill” created for 15 Oct 2026"

    client.put("/api/preferences", json={"language": "fr"})
    entry = client.get("/api/activity").json()[0]
    assert entry["summary"] == "Rappel « Water bill » créé pour le 15/10/2026"


def test_migrates_legacy_identifiers() -> None:
    engine = db.get_engine()
    with Session(engine) as session:
        doc = Document(
            filename="notice.pdf",
            mime_type="application/pdf",
            size=1,
            sha256="0" * 64,
            stored_name="notice",
            title="Notice 2026",
            text="Montant à payer",
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id
        session.add(Deadline(document_id=doc_id, title="Notice", due_date=date(2026, 10, 15)))
        session.commit()
    # Values written by former versions: French enum member names and doc_type labels.
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE document SET category = 'IMPOTS', doc_type = 'Facture' WHERE id = :id"),
            {"id": doc_id},
        )
        conn.execute(text("UPDATE deadline SET category = 'IMPOTS'"))
        conn.execute(text("DELETE FROM document_fts"))

    db.reset_engine()
    engine = db.get_engine()  # runs init_db: migration and reindexing
    with Session(engine) as session:
        row = session.execute(
            text("SELECT category, doc_type FROM document WHERE id = :id"), {"id": doc_id}
        ).one()
        assert tuple(row) == ("TAXES", "invoice")
        assert session.execute(text("SELECT category FROM deadline")).scalar_one() == "TAXES"
        migrated = session.get(Document, doc_id)
        assert migrated is not None and migrated.category == Category.TAXES

        def search(word: str) -> list[int]:
            rows = session.execute(
                text("SELECT rowid FROM document_fts WHERE document_fts MATCH :q"), {"q": word}
            )
            return [r[0] for r in rows]

        # Category labels are indexed in both languages, without accents.
        assert search("impots") == [doc_id]
        assert search("taxes") == [doc_id]

    # Idempotent: nothing left to migrate.
    assert db.migrate_identifiers(engine) is False


def test_text_size_preference(client: TestClient) -> None:
    prefs = {"language": "auto", "country": None, "theme": "system"}
    r = client.put("/api/preferences", json={**prefs, "text_size": "larger"})
    assert r.status_code == 200, r.text
    assert client.get("/api/preferences").json()["text_size"] == "larger"
    assert client.put("/api/preferences", json={**prefs, "text_size": "huge"}).status_code == 422
