"""Construit l'application de bureau sur le système courant (Linux, Windows ou macOS).

    python packaging/build.py

Résultat : packaging/dist/Binder/ (Linux, Windows) ou packaging/dist/Binder.app (macOS).
Prérequis : uv et Node 20 ou plus dans le PATH.
"""

import shutil
import subprocess
import sys
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent
ROOT = PACKAGING.parent


def run(*cmd: str, cwd: Path) -> None:
    # Sous Windows, npm est un script .cmd : shutil.which le retrouve, pas subprocess seul.
    exe = shutil.which(cmd[0])
    if exe is None:
        sys.exit(f"Introuvable dans le PATH : {cmd[0]}")
    subprocess.run([exe, *cmd[1:]], cwd=cwd, check=True)


def main() -> None:
    print("==> Interface")
    run("npm", "ci", "--silent", cwd=ROOT / "frontend")
    run("npm", "run", "build", cwd=ROOT / "frontend")

    print("==> Exécutable")
    backend = ROOT / "backend"
    run("uv", "sync", "--extra", "desktop", "--quiet", cwd=backend)
    run(
        "uv", "run", "pyinstaller", str(PACKAGING / "binder.spec"), "--noconfirm",
        "--distpath", str(PACKAGING / "dist"), "--workpath", str(PACKAGING / "build"),
        cwd=backend,
    )

    if sys.platform == "darwin":
        out = PACKAGING / "dist" / "Binder.app"
    elif sys.platform == "win32":
        out = PACKAGING / "dist" / "Binder" / "Binder.exe"
    else:
        out = PACKAGING / "dist" / "Binder" / "Binder"
    print(f"OK : {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
