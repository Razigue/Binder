"""Is Binder open? A lock file held for as long as the server runs.

The reminder run (`binder --remind`, started by the system while Binder is closed) checks it:
an open Binder already notifies on its own. The operating system releases the lock when the
process ends, even after a crash, so a stale file never blocks anything.
"""

import contextlib
import sys
from pathlib import Path
from typing import IO

from binder.config import get_settings

LOCK_FILE = "binder.lock"

_held: IO[bytes] | None = None


def _path() -> Path:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / LOCK_FILE


def _lock(handle: IO[bytes]) -> bool:
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(handle: IO[bytes]) -> None:
    with contextlib.suppress(OSError):
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def hold() -> bool:
    """Marks Binder as open. False if another Binder already holds the lock."""
    global _held
    if _held is not None:
        return True
    handle = _path().open("a+b")
    if not _lock(handle):
        handle.close()
        return False
    _held = handle
    return True


def release() -> None:
    global _held
    if _held is None:
        return
    _unlock(_held)
    _held.close()
    _held = None


def running() -> bool:
    """Another process (or this one) holds the lock: Binder is open."""
    if _held is not None:
        return True
    path = _path()
    with path.open("a+b") as handle:
        if not _lock(handle):
            return True
        _unlock(handle)
    return False
