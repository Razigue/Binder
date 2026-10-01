"""System notifications, sent by the operating system's own mechanism (no extra dependency).

- Linux: `notify-send` (libnotify) when available.
- macOS: `osascript`'s `display notification`.
- Windows 10/11: a toast through PowerShell and the Windows Runtime.

Best effort: a notification that cannot be shown is logged and skipped. Each alert is sent once
(keys remembered in the encrypted database).
"""

import logging
import shutil
import subprocess
import sys
from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlmodel import Session

from binder.services import settings_store

log = logging.getLogger(__name__)

SENT_KEY = "notifications.sent"
# Forget sent keys after this many entries (oldest first).
REMEMBER = 500

WINDOWS_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$template = '<toast><visual><binding template="ToastGeneric"><text></text><text></text></binding></visual></toast>'
$xml.LoadXml($template)
$texts = $xml.GetElementsByTagName('text')
$texts.Item(0).AppendChild($xml.CreateTextNode($env:BINDER_TITLE)) > $null
$texts.Item(1).AppendChild($xml.CreateTextNode($env:BINDER_BODY)) > $null
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""  # noqa: E501


class Sent(BaseModel):
    keys: dict[str, date] = {}


def _command(title: str, body: str) -> tuple[list[str], dict[str, str]] | None:
    import os

    env = dict(os.environ)
    if sys.platform == "win32":
        powershell = shutil.which("powershell") or shutil.which("powershell.exe")
        if powershell is None:
            return None
        env.update(BINDER_TITLE=title, BINDER_BODY=body)
        return [powershell, "-NoProfile", "-NonInteractive", "-Command", WINDOWS_TOAST], env
    if sys.platform == "darwin":
        # Values passed as AppleScript arguments: no quoting of the text itself.
        script = (
            "on run argv\n"
            "display notification (item 2 of argv) with title (item 1 of argv)\n"
            "end run"
        )
        return ["osascript", "-e", script, title, body], env
    tool = shutil.which("notify-send")
    if tool is None:
        return None
    return [tool, "--app-name=Binder", title, body], env


def send(title: str, body: str) -> bool:
    command = _command(title, body)
    if command is None:
        return False
    args, env = command
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        subprocess.run(args, env=env, timeout=15, check=True, capture_output=True, **kwargs)
        return True
    except (OSError, subprocess.SubprocessError):
        log.warning("Notification not shown", exc_info=True)
        return False


def once(session: Session, key: str, title: str, body: str) -> bool:
    """Sends the notification unless it was already sent. Does not commit."""
    sent = settings_store.load(session, SENT_KEY, Sent)
    if key in sent.keys:
        return False
    if not send(title, body):
        return False
    sent.keys[key] = date.today()
    if len(sent.keys) > REMEMBER:
        sent.keys = dict(sorted(sent.keys.items(), key=lambda kv: kv[1])[-REMEMBER:])
    settings_store.save(session, SENT_KEY, sent)
    return True
