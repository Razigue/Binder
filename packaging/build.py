"""Builds the desktop application on the current system (Linux, Windows or macOS).

    python packaging/build.py
    python packaging/build.py --version 1.2.0   # release: sets the version (pyproject.toml)
    python packaging/build.py --version 1.2.0 --installer

Output: packaging/dist/Binder/ (Linux, Windows) or packaging/dist/Binder.app (macOS).
With --installer, Velopack packages in packaging/releases/: Setup.exe (Windows), .pkg (macOS),
AppImage (Linux), plus the update packages and feed. Signing comes from VPK_* variables.
Requirements: uv and Node 20 or later in the PATH; vpk (`dotnet tool install -g vpk`) for
--installer.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent
ROOT = PACKAGING.parent
RELEASES = PACKAGING / "releases"
# Not "Binder": on Windows the installer uses %LocalAppData%\<id>, which is already Binder's
# data folder, and uninstalling removes that folder.
PACK_ID = "BinderApp"
# Velopack channel per system: explicit names put it in every file name, so the three systems'
# packages sit side by side in one GitHub release (release.yml downloads them by channel).
CHANNELS = {"win32": "windows", "darwin": "macos", "linux": "linux"}


def run(*cmd: str, cwd: Path) -> None:
    # On Windows, npm is a .cmd script: shutil.which finds it, subprocess alone does not.
    exe = shutil.which(cmd[0])
    if exe is None:
        sys.exit(f"Not found in PATH: {cmd[0]}")
    subprocess.run([exe, *cmd[1:]], cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", help="application version (e.g. 1.2.0, from the tag)")
    parser.add_argument("--installer", action="store_true", help="Velopack installer")
    args = parser.parse_args()
    if args.installer and not args.version:
        sys.exit("--installer needs --version")
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
    if args.installer:
        installer(args.version)


def installer(version: str) -> None:
    print("==> Installer")
    if sys.platform == "darwin":
        pack_dir, main_exe, icon = PACKAGING / "dist" / "Binder.app", "Binder", None
    elif sys.platform == "win32":
        pack_dir, main_exe = PACKAGING / "dist" / "Binder", "Binder.exe"
        icon = PACKAGING / "build" / "binder.ico"
        # Pillow comes with the backend environment, not with this script's.
        convert = "import sys; from PIL import Image; Image.open(sys.argv[1]).save(sys.argv[2])"
        run("uv", "run", "python", "-c", convert, str(PACKAGING / "binder.png"), str(icon),
            cwd=ROOT / "backend")
    else:
        pack_dir, main_exe, icon = PACKAGING / "dist" / "Binder", "Binder", PACKAGING / "binder.png"
    system = "linux" if sys.platform.startswith("linux") else sys.platform
    arm = platform.machine().lower() in ("arm64", "aarch64")
    runtime = {"win32": "win", "darwin": "osx", "linux": "linux"}[system]
    runtime += "-arm64" if arm else "-x64"
    cmd = [
        "vpk", "pack", "--channel", CHANNELS[system], "--runtime", runtime,
        "--packId", PACK_ID, "--packVersion", version, "--packTitle", "Binder",
        "--packAuthors", "Binder", "--packDir", str(pack_dir), "--mainExe", main_exe,
        "--outputDir", str(RELEASES),
    ]
    # Linux's AppImage is the portable package; its CLI rejects --noPortable.
    # Windows/macOS portable archives are built separately by the release workflow.
    if system != "linux":
        cmd += ["--noPortable"]
    if icon is not None:
        cmd += ["--icon", str(icon)]
    if sys.platform == "win32":
        cmd += ["--splashImage", str(PACKAGING / "binder.png")]
    if os.environ.get("RELEASE_NOTES"):
        cmd += ["--releaseNotes", os.environ["RELEASE_NOTES"]]
    run(*cmd, cwd=ROOT)
    print(f"OK: {RELEASES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
