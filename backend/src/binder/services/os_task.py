"""A daily task of the operating system that runs `Binder --remind` while Binder is closed.

Each system's own scheduler, no resident process: Binder takes no memory when it is closed.

- Windows: a Task Scheduler task of the current user (every day at 09:00 and a few minutes after
  logging in; a missed run is made up as soon as the computer is on).
- macOS: a LaunchAgent (every day at 09:00 and at login).
- Linux: a systemd user timer (Persistent: made up after the computer was off), or an XDG
  autostart entry (at login) without systemd.

Only the packaged application registers it (`command`): a development run never leaves a task
pointing to a temporary interpreter. Registering again replaces the task, so the path stays right
after the application moves.
"""

import logging
import os
import plistlib
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from xml.sax.saxutils import escape

from binder.services import process

log = logging.getLogger(__name__)

ARGUMENT = "--remind"
HOUR = 9
# After logging in: the desktop settles before a notification shows.
LOGON_DELAY = "PT3M"
WINDOWS_TASK = "Binder reminders"
MACOS_LABEL = "app.binder.reminders"
LINUX_UNIT = "binder-reminders"

Runner = Callable[[Sequence[str]], bool]


def _run(args: Sequence[str]) -> bool:
    try:
        process.run_hidden(args, timeout=30)
        return True
    except (OSError, subprocess.SubprocessError):
        log.warning("System task command failed: %s", args[0], exc_info=True)
        return False


def command() -> list[str] | None:
    """How the system starts the reminder run; None outside the packaged application."""
    if not getattr(sys, "frozen", False):
        return None
    # An AppImage runs from a temporary mount: the system must start the AppImage itself.
    appimage = os.environ.get("APPIMAGE")
    if sys.platform.startswith("linux") and appimage:
        return [appimage, ARGUMENT]
    return [sys.executable, ARGUMENT]


# --- Windows ---------------------------------------------------------------------------------


def windows_task_xml(cmd: Sequence[str], user: str) -> str:
    program, *args = cmd
    arguments = " ".join(f'"{a}"' if " " in a else a for a in args)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Binder: deadlines and papers to fetch, while Binder is closed.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T{HOUR:02d}:00:00</StartBoundary>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
    <LogonTrigger>
      <UserId>{escape(user)}</UserId>
      <Delay>{LOGON_DELAY}</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(program)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _windows_user() -> str:
    user = os.environ.get("USERNAME", "")
    domain = os.environ.get("USERDOMAIN", "")
    return f"{domain}\\{user}" if domain else user


def _register_windows(cmd: Sequence[str], run: Runner) -> bool:
    # schtasks reads the definition from a file; it holds no personal data.
    fd, name = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(fd, "w", encoding="utf-16") as f:
            f.write(windows_task_xml(cmd, _windows_user()))
        return run(["schtasks", "/Create", "/F", "/TN", WINDOWS_TASK, "/XML", name])
    finally:
        Path(name).unlink(missing_ok=True)


def _unregister_windows(run: Runner) -> bool:
    return run(["schtasks", "/Delete", "/F", "/TN", WINDOWS_TASK])


# --- macOS -----------------------------------------------------------------------------------


def launchd_plist(cmd: Sequence[str]) -> bytes:
    return plistlib.dumps(
        {
            "Label": MACOS_LABEL,
            "ProgramArguments": list(cmd),
            "StartCalendarInterval": {"Hour": HOUR, "Minute": 0},
            "RunAtLoad": True,
            "ProcessType": "Background",
        }
    )


def _plist_path(home: Path) -> Path:
    return home / "Library" / "LaunchAgents" / f"{MACOS_LABEL}.plist"


def _register_macos(cmd: Sequence[str], home: Path, run: Runner) -> bool:
    path = _plist_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(launchd_plist(cmd))
    domain = f"gui/{os.getuid()}" if hasattr(os, "getuid") else "gui"
    run(["launchctl", "bootout", domain, str(path)])  # the previous version, if loaded
    # Loaded at the next login anyway if this fails.
    run(["launchctl", "bootstrap", domain, str(path)])
    return True


def _unregister_macos(home: Path, run: Runner) -> bool:
    path = _plist_path(home)
    if path.exists():
        domain = f"gui/{os.getuid()}" if hasattr(os, "getuid") else "gui"
        run(["launchctl", "bootout", domain, str(path)])
        path.unlink()
    return True


# --- Linux -----------------------------------------------------------------------------------


def _quote(arg: str) -> str:
    """Quoting understood by both systemd's ExecStart and XDG's Exec."""
    if arg and not any(c in arg for c in " \t\"\\$`'"):
        return arg
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def systemd_units(cmd: Sequence[str]) -> tuple[str, str]:
    service = (
        "[Unit]\nDescription=Binder reminders\n\n"
        f"[Service]\nType=oneshot\nExecStart={' '.join(_quote(a) for a in cmd)}\n"
    )
    timer = (
        "[Unit]\nDescription=Binder reminders, every day and after login\n\n"
        f"[Timer]\nOnCalendar=*-*-* {HOUR:02d}:00:00\nOnStartupSec=3min\nPersistent=true\n\n"
        "[Install]\nWantedBy=timers.target\n"
    )
    return service, timer


def desktop_entry(cmd: Sequence[str]) -> str:
    return (
        "[Desktop Entry]\nType=Application\nName=Binder reminders\n"
        f"Exec={' '.join(_quote(a) for a in cmd)}\nNoDisplay=true\nX-GNOME-Autostart-Delay=180\n"
    )


def _config(home: Path) -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base) if base else home / ".config"


def _register_linux(cmd: Sequence[str], home: Path, run: Runner) -> bool:
    units = _config(home) / "systemd" / "user"
    autostart = _config(home) / "autostart" / f"{LINUX_UNIT}.desktop"
    service, timer = systemd_units(cmd)
    units.mkdir(parents=True, exist_ok=True)
    (units / f"{LINUX_UNIT}.service").write_text(service, encoding="utf-8")
    (units / f"{LINUX_UNIT}.timer").write_text(timer, encoding="utf-8")
    if run(["systemctl", "--user", "daemon-reload"]) and run(
        ["systemctl", "--user", "enable", "--now", f"{LINUX_UNIT}.timer"]
    ):
        autostart.unlink(missing_ok=True)
        return True
    # No systemd user session: at login only.
    autostart.parent.mkdir(parents=True, exist_ok=True)
    autostart.write_text(desktop_entry(cmd), encoding="utf-8")
    return True


def _unregister_linux(home: Path, run: Runner) -> bool:
    units = _config(home) / "systemd" / "user"
    if (units / f"{LINUX_UNIT}.timer").exists():
        run(["systemctl", "--user", "disable", "--now", f"{LINUX_UNIT}.timer"])
    for path in (
        units / f"{LINUX_UNIT}.timer",
        units / f"{LINUX_UNIT}.service",
        _config(home) / "autostart" / f"{LINUX_UNIT}.desktop",
    ):
        path.unlink(missing_ok=True)
    return True


# --- Entry points ----------------------------------------------------------------------------


def register(
    cmd: Sequence[str],
    *,
    platform: str = sys.platform,
    home: Path | None = None,
    run: Runner = _run,
) -> bool:
    home = home or Path.home()
    try:
        if platform == "win32":
            return _register_windows(cmd, run)
        if platform == "darwin":
            return _register_macos(cmd, home, run)
        return _register_linux(cmd, home, run)
    except OSError:
        log.warning("Could not register the reminder task", exc_info=True)
        return False


def unregister(
    *, platform: str = sys.platform, home: Path | None = None, run: Runner = _run
) -> bool:
    home = home or Path.home()
    try:
        if platform == "win32":
            return _unregister_windows(run)
        if platform == "darwin":
            return _unregister_macos(home, run)
        return _unregister_linux(home, run)
    except OSError:
        log.warning("Could not remove the reminder task", exc_info=True)
        return False
