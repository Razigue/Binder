"""Point d'entrée de l'application empaquetée (PyInstaller)."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from binder.cli import main, run_desktop

    # Double-clic : application de bureau. Avec arguments (--seed, …) : CLI habituelle.
    if len(sys.argv) == 1:
        run_desktop()
    else:
        main()
