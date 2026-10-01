# -*- mode: python ; coding: utf-8 -*-
# Build : python packaging/build.py  (compile d'abord l'interface React)
# Linux : Qt WebEngine embarqué. Windows : Edge WebView2. macOS : WebKit, paquet Binder.app.
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

LINUX = sys.platform.startswith("linux")
MACOS = sys.platform == "darwin"

if LINUX:
    gui_imports = ["webview.platforms.qt", "qtpy"]
elif MACOS:
    gui_imports = ["webview.platforms.cocoa"]
else:
    gui_imports = ["webview.platforms.edgechromium", "webview.platforms.winforms", "clr"]

hiddenimports = (
    collect_submodules("binder")
    + collect_submodules("uvicorn")
    + ["sqlcipher3"]
    + gui_imports
)

excludes = ["tkinter", "pytest", "mypy", "ruff", "IPython", "PyQt5", "PySide6", "gi"]
if not LINUX:
    excludes += ["PyQt6", "qtpy"]

a = Analysis(
    ["binder_app.py"],
    pathex=["../backend/src"],
    datas=collect_data_files("binder", includes=["static/**/*"]),
    hiddenimports=hiddenimports,
    excludes=excludes,
)
# Allègement : modules Qt inutiles à WebEngine et traductions autres que fr/en.
UNUSED_QT = ("Quick3D", "Multimedia", "Pdf", "Sensors", "ShaderTools", "SpatialAudio")


def keep(entry):
    dest = entry[0].replace("\\", "/")
    if "PyQt6/Qt6/" not in dest:
        return True
    if any(f"Qt6{m}" in dest or f"/{m}" in dest for m in UNUSED_QT):
        return False
    if "/translations/" in dest:
        name = dest.rsplit("/", 1)[-1]
        return name.startswith(("fr", "en")) or "_fr" in name or "_en" in name
    return True


a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Binder",
    console=False,
    # PyInstaller convertit le PNG en .ico (Windows) ou .icns (macOS) grâce à Pillow.
    icon="binder.png",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Binder")

if MACOS:
    app = BUNDLE(
        coll,
        name="Binder.app",
        icon="binder.png",
        bundle_identifier="fr.binder.app",
        info_plist={
            "CFBundleDisplayName": "Binder",
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
        },
    )
