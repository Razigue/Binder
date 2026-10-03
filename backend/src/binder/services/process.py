"""Running the system's own tools (notifications, scheduler, Ollama) in the background."""

import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Any


def no_window() -> dict[str, Any]:
    """Process options that keep a console window from flashing up on Windows."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def run_hidden(
    args: Sequence[str], *, timeout: float, env: Mapping[str, str] | None = None
) -> None:
    """Runs a command to its end, output captured, no window. Raises OSError or
    subprocess.SubprocessError (failure, non-zero exit, timeout)."""
    subprocess.run(
        list(args), env=env, timeout=timeout, check=True, capture_output=True, **no_window()
    )
