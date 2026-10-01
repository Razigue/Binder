"""Point d'entrée de l'application empaquetée (PyInstaller)."""

import multiprocessing
import os
import sys

# Application fenêtrée (sans console) : sous Windows, sys.stdout et sys.stderr valent None,
# ce qui fait planter la configuration des journaux d'uvicorn.
for name in ("stdout", "stderr"):
    if getattr(sys, name) is None:
        setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from binder.cli import main, run_desktop

    # Double-clic : application de bureau. Avec arguments (--seed, …) : CLI habituelle.
    if len(sys.argv) == 1:
        run_desktop()
    else:
        main()
