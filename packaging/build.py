"""Builds the desktop application on the current system (Linux, Windows or macOS).

    python packaging/build.py
    python packaging/build.py --version 1.2.0   # release: sets the version (pyproject.toml)

Output: packaging/dist/Binder/ (Linux, Windows) or packaging/dist/Binder.app (macOS).
Requirements: uv and Node 20 or later in the PATH.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent
ROOT = PACKAGING.parent


def run(*cmd: str, cwd: Path) -> None:
    # On Windows, npm is a .cmd script: shutil.which finds it, subprocess alone does not.
    exe = shutil.which(cmd[0])
    if exe is None:
        sys.exit(f"Not found in PATH: {cmd[0]}")
    subprocess.run([exe, *cmd[1:]], cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", help="application version (e.g. 1.2.0, from the tag)")
    args = parser.parse_args()
    backend = ROOT / "backend"
    if args.version:
        # The embedded version is compared with releases by the automatic update.
        run("uv", "version", args.version, "--no-sync", cwd=backend)

    print("==> Interface")
    run("npm", "ci", "--silent", cwd=ROOT / "frontend")
    run("npm", "run", "build", cwd=ROOT / "frontend")

    print("==> Executable")
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
    print(f"OK: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
