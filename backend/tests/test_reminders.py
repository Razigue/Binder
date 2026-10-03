"""What to fetch and where, the rights to check, and the reminders while Binder is closed."""

import plistlib
from collections.abc import Iterator, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from binder.config import get_settings
from binder.db import get_engine
from binder.models import Category, Deadline, DocType, Document, DocumentStatus
from binder.services import (
    essentials,
    feed,
    instance,
    missing,
    notify,
    os_task,
    portals,
    preferences,
    profile,
    reminders,
    rights,
)

TODAY = date(2026, 10, 6)


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


@pytest.fixture
def france(session: Session) -> None:
    preferences.save(session, preferences.Preferences(country="FR"))
    session.commit()


_count = 0


def add(session: Session, **fields: Any) -> Document:
    global _count
    _count += 1
    doc = Document(
        filename=f"doc-{_count}.pdf",
        mime_type="application/pdf",
        size=1,
        sha256=f"{_count:064x}",
        stored_name=f"doc-{_count}",
        status=DocumentStatus.CLASSIFIED,
        **fields,
    )
    session.add(doc)
    session.commit()
    return doc


def payslip(session: Session, issued: date, amount: float = 1450.0) -> Document:
    return add(
        session,
        title="Bulletin de paie",
        category=Category.WORK,
        area="work",
        doc_type=DocType.PAYSLIP,
        issuer="Atelier SAS",
        issue_date=issued,
        amount=amount,
    )


# --- Where to fetch a paper ------------------------------------------------------------------


def test_portal_of_public_services_and_of_any_issuer(session: Session) -> None:
    assert portals.find(session, "DGFiP - Finances publiques") == portals.public("impots")
    assert portals.find(session, None, DocType.TAX_NOTICE) == portals.public("impots")
    assert portals.find(session, "CAF du Rhône") == portals.public("caf")
    # Any other issuer: the website printed on its own documents, when it names the issuer.
    add(
        session,
        title="Facture",
        issuer="Bouygues Telecom",
        text="Payez sur www.lydia.fr ou retrouvez vos factures sur bouyguestelecom.fr",
    )
    found = portals.find(session, "Bouygues Telecom")
    assert found is not None and found.url == "https://bouyguestelecom.fr"
    add(session, title="Facture", issuer="EDF", text="Espace client : https://particulier.edf.fr")
    assert portals.find(session, "EDF") == portals.Portal(
        name="particulier.edf.fr", url="https://particulier.edf.fr"
    )
    # An e-mail address is not a website, and another company's site is not the issuer's.
    add(session, title="Facture", issuer="Free", text="contact@free.fr · paiement sur paypal.com")
    assert portals.find(session, "Free") is None


def test_fetch_cards_when_papers_come_out(session: Session) -> None:
    # A first job last year: this year's tax notice is due though none was ever filed.
    payslip(session, date(2025, 11, 28))
    payslip(session, date(2026, 8, 28))
    found = {m.key.split(":")[0]: m for m in missing.detect(session, TODAY)}
    assert found["tax"].portal == portals.public("impots")
    assert found["tax"].expected == date(2026, 8, 1)
    # September's payslip is out (after the 5th) and not in Binder yet: to download, not to ask.
    out = next(m for m in missing.detect(session, TODAY) if m.key.endswith("2026-09"))
    assert "is out" in out.title and out.letter is None
    # Before it is published, nothing.
    assert not any(m.key.startswith("tax") for m in missing.detect(session, date(2026, 7, 20)))
    # An owner gets the property tax card from September.
    profile.update(session, {"housing": "owner"})
    session.commit()
    keys = [m.key for m in missing.detect(session, TODAY)]
    assert "property:2026" in keys


def test_fetch_card_opens_the_online_account(client: TestClient, session: Session) -> None:
    payslip(session, date(2025, 12, 28))
    items = feed.build(session, TODAY)
    card = next(i for i in items if i.key == "missing:tax:2026")
    assert card.actions[0].type == "link" and card.actions[0].primary
    assert card.actions[0].params == {"url": "https://www.impots.gouv.fr"}


def test_essentials_say_where_to_fetch_a_missing_paper(session: Session) -> None:
    out = {p.key: p for p in essentials.papers(session, profile.Profile())}
    assert out["tax_notice"].portal == portals.public("impots")
    assert out["identity"].portal is None


# --- Rights to check ---------------------------------------------------------------------------


def test_rights_follow_the_situation_and_the_papers(session: Session, france: None) -> None:
    assert rights.detect(session, TODAY) == []
    payslip(session, date(2026, 9, 28))
    profile.update(session, {"housing": "tenant"})
    session.commit()
    keys = {r.key.split(":")[0] for r in rights.detect(session, TODAY)}
    assert keys == {"activity_bonus", "housing_aid"}
    # Already paid by the CAF: no longer suggested.
    add(
        session,
        title="Attestation de paiement",
        issuer="CAF du Rhône",
        text="Montant de votre aide personnalisée au logement (APL) : 180 €",
    )
    keys = {r.key.split(":")[0] for r in rights.detect(session, TODAY)}
    assert keys == {"activity_bonus"}
    # A good salary: the prime d'activité is not worth a card.
    payslip(session, date(2026, 10, 2), amount=3200.0)
    assert rights.detect(session, TODAY) == []


def test_rights_only_in_france(session: Session) -> None:
    profile.update(session, {"situation": "job_seeker"})
    session.commit()
    assert rights.detect(session, TODAY) == []


def test_job_seeker_monthly_update(session: Session, france: None) -> None:
    profile.update(session, {"situation": "job_seeker"})
    session.commit()
    assert rights.update_window(date(2026, 10, 20)) is None
    assert rights.update_window(date(2026, 10, 28)) == date(2026, 11, 15)
    assert rights.update_window(date(2026, 2, 26)) == date(2026, 3, 15)
    assert rights.update_window(date(2026, 12, 30)) == date(2027, 1, 15)
    update = next(r for r in rights.detect(session, date(2026, 11, 14)) if "job_update" in r.key)
    assert update.tone == "urgent" and update.when == date(2026, 11, 15)
    assert update.link == portals.public("france_travail")


def test_first_tax_return(session: Session, france: None) -> None:
    payslip(session, date(2025, 12, 28))
    first = next(r for r in rights.detect(session, date(2026, 5, 2)) if "first_return" in r.key)
    assert "2025" in first.detail and first.link == portals.public("impots")
    assert not any("first_return" in r.key for r in rights.detect(session, date(2026, 7, 1)))


def test_right_card_links_explains_and_dismisses(
    client: TestClient, session: Session, france: None
) -> None:
    profile.update(session, {"situation": "student"})
    session.commit()
    card = next(i for i in feed.build(session, TODAY) if i.kind == "right")
    assert [a.type for a in card.actions] == ["link", "agent", "dismiss"]
    assert card.actions[0].params["url"].startswith("https://www.service-public.gouv.fr/")
    r = client.post("/api/actions", json={"type": "dismiss", "params": {"key": card.key}})
    assert r.status_code == 200, r.text
    with Session(get_engine()) as fresh:
        assert card.key not in {i.key for i in feed.build(fresh, TODAY)}


# --- Reminders while Binder is closed --------------------------------------------------------


def test_reminder_once_a_day_and_only_with_news(session: Session) -> None:
    payslip(session, date(2025, 12, 28))
    reminder = reminders.compose(session, TODAY)
    assert reminder is not None
    assert reminder.title.startswith("Binder: ") and "Tax notice 2026" in reminder.body
    reminders.mark_sent(session, reminder, TODAY)
    # Said already today, then nothing new and nothing urgent.
    assert reminders.compose(session, TODAY) is None
    assert reminders.compose(session, date(2026, 10, 7)) is None
    # Something new the next day: a reminder again.
    profile.update(session, {"housing": "owner"})
    session.commit()
    again = reminders.compose(session, date(2026, 10, 7))
    assert again is not None and again.body.startswith("Property tax 2026")


def test_remind_run_stays_silent_while_binder_is_open(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    payslip(session, date(2025, 12, 28))
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(notify, "send", lambda title, body: shown.append((title, body)) or True)
    monkeypatch.setattr(get_settings(), "notifications", True)
    # The test client runs the app: Binder is open.
    assert instance.running()
    assert reminders.remind() is False and shown == []


def test_remind_run_while_closed(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    # Due tomorrow: urgent whatever the day the test runs.
    tomorrow = date.today() + timedelta(days=1)
    session.add(Deadline(title="Pay the rent", due_date=tomorrow, amount=600.0))
    session.commit()
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(notify, "send", lambda title, body: shown.append((title, body)) or True)
    monkeypatch.setattr(get_settings(), "notifications", True)
    assert not instance.running()
    assert reminders.remind() is True
    assert shown == [("Binder: 1 thing to do", "Pay the rent. Open Binder to see it.")]
    # Once a day.
    assert reminders.remind() is False and len(shown) == 1


def test_remind_run_turned_off(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    session.add(Deadline(title="Pay the rent", due_date=date.today(), amount=600.0))
    reminders.update(session, False)
    session.commit()
    monkeypatch.setattr(notify, "send", lambda title, body: pytest.fail("notified"))
    monkeypatch.setattr(get_settings(), "notifications", True)
    assert reminders.remind() is False


def test_instance_lock() -> None:
    assert not instance.running()
    assert instance.hold()
    assert instance.running()
    instance.release()
    assert not instance.running()


def test_reminders_api(client: TestClient) -> None:
    r = client.get("/api/reminders")
    # A development run cannot be started by the system.
    assert r.json() == {"enabled": True, "available": False, "hour": os_task.HOUR}
    r = client.put("/api/reminders", json={"enabled": False})
    assert r.json()["enabled"] is False
    assert client.get("/api/reminders").json()["enabled"] is False


# --- The system task ---------------------------------------------------------------------------


CMD = ["/Applications/Binder.app/Contents/MacOS/Binder", "--remind"]


class Recorder:
    def __init__(self, ok: bool = True) -> None:
        self.calls: list[list[str]] = []
        self.ok = ok

    def __call__(self, args: Sequence[str]) -> bool:
        self.calls.append(list(args))
        return self.ok


def test_command_only_in_the_packaged_app(monkeypatch: pytest.MonkeyPatch) -> None:
    assert os_task.command() is None
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert os_task.command() is not None
    assert os_task.command()[-1] == "--remind"  # type: ignore[index]


def test_windows_task() -> None:
    xml = os_task.windows_task_xml([r"C:\Users\A & B\Binder\Binder.exe", "--remind"], r"PC\A&B")
    assert r"<Command>C:\Users\A &amp; B\Binder\Binder.exe</Command>" in xml
    assert "<UserId>PC\\A&amp;B</UserId>" in xml
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml
    run = Recorder()
    assert os_task.register(["Binder.exe", "--remind"], platform="win32", run=run)
    assert run.calls[0][:5] == ["schtasks", "/Create", "/F", "/TN", os_task.WINDOWS_TASK]
    # The definition file is removed once read.
    assert not Path(run.calls[0][-1]).exists()
    os_task.unregister(platform="win32", run=run)
    assert run.calls[-1][:2] == ["schtasks", "/Delete"]


def test_macos_launch_agent(tmp_path: Path) -> None:
    run = Recorder()
    assert os_task.register(CMD, platform="darwin", home=tmp_path, run=run)
    path = tmp_path / "Library" / "LaunchAgents" / f"{os_task.MACOS_LABEL}.plist"
    agent = plistlib.loads(path.read_bytes())
    assert agent["ProgramArguments"] == CMD and agent["RunAtLoad"] is True
    assert agent["StartCalendarInterval"] == {"Hour": os_task.HOUR, "Minute": 0}
    os_task.unregister(platform="darwin", home=tmp_path, run=run)
    assert not path.exists()


def test_linux_timer_or_autostart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    cmd = ["/home/me/Binder App.AppImage", "--remind"]
    assert os_task.register(cmd, platform="linux", home=tmp_path, run=Recorder())
    units = tmp_path / ".config" / "systemd" / "user"
    service = (units / "binder-reminders.service").read_text(encoding="utf-8")
    assert 'ExecStart="/home/me/Binder App.AppImage" --remind' in service
    assert "Persistent=true" in (units / "binder-reminders.timer").read_text(encoding="utf-8")
    # Without a systemd user session: an autostart entry, at login.
    assert os_task.register(cmd, platform="linux", home=tmp_path, run=Recorder(ok=False))
    autostart = tmp_path / ".config" / "autostart" / "binder-reminders.desktop"
    assert "--remind" in autostart.read_text(encoding="utf-8")
    os_task.unregister(platform="linux", home=tmp_path, run=Recorder())
    assert not autostart.exists() and not (units / "binder-reminders.timer").exists()
