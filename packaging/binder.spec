# -*- mode: python ; coding: utf-8 -*-
# Build : ./packaging/build-app.sh  (compile d'abord l'interface React)
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = (
    collect_submodules("binder")
    + collect_submodules("uvicorn")
    + ["sqlcipher3", "webview.platforms.qt", "qtpy"]
)

a = Analysis(
    ["binder_app.py"],
    pathex=["../backend/src"],
    datas=collect_data_files("binder", includes=["static/**/*"]),
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "mypy", "ruff", "IPython", "PyQt5", "PySide6", "gi"],
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
    icon="binder.png",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Binder")
