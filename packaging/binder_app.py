"""Entry point of the packaged application (PyInstaller)."""

import multiprocessing
import os
import sys

# Windowed application (no console): on Windows, sys.stdout and sys.stderr are None,
# which crashes uvicorn's logging configuration.
for name in ("stdout", "stderr"):
    if getattr(sys, name) is None:
        setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # Installer hooks (install, update, uninstall): Velopack handles them and exits. Started
    # normally, or from the portable archive, it returns at once.
    import velopack

    velopack.App().run()
    from binder import desktop
    from binder.cli import main

    # Double-click: desktop application. With arguments (--seed, …): the usual CLI.
    if len(sys.argv) == 1:
        desktop.run()
    else:
        main()
