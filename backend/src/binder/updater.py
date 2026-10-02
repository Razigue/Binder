"""Desktop application update from GitHub releases, at launch.

Binder is distributed only through its installers (Velopack: Setup.exe, .pkg, AppImage), and
Velopack updates it: delta packages, verified, applied while Binder restarts. See `installed()`.
A failed update (offline, GitHub unreachable) never prevents Binder from starting.
"""

import logging
import sys
from collections.abc import Callable
from typing import Any

import httpx

from binder.config import get_settings

log = logging.getLogger(__name__)

# Replaceable in tests by an httpx.MockTransport (also used by the Ollama download).
transport: httpx.BaseTransport | None = None

Progress = Callable[[int, int], None]


def installed() -> Any | None:
    """Velopack's update manager when Binder runs from its installer, otherwise None.

    Velopack refuses to create one outside an installation (sources, a bare PyInstaller build).
    """
    if not getattr(sys, "frozen", False):
        return None
    try:
        import velopack

        return velopack.UpdateManager(velopack.GithubSource(get_settings().update_repo))
    except Exception as e:
        log.info("Not installed by the installer: %s", e)
        return None


def download_size(info: Any) -> int:
    """Bytes Velopack downloads for an update: the deltas when it can, else the full package."""
    deltas = sum(int(d.Size) for d in info.DeltasToTarget)
    return deltas or int(info.TargetFullRelease.Size)
