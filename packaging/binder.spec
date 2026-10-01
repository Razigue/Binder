# -*- mode: python ; coding: utf-8 -*-
# Build: python packaging/build.py  (builds the React interface first)
# Linux: bundled Qt WebEngine. Windows: Edge WebView2. macOS: WebKit, Binder.app bundle.
import sys
from importlib.metadata import version

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

LINUX = sys.platform.startswith("linux")
MACOS = sys.platform == "darwin"

if LINUX:
    gui_imports = ["webview.platforms.qt", "qtpy"]
elif MACOS:
    gui_imports = ["webview.platforms.cocoa"]
else:
    gui_imports = ["webview.platforms.edgechromium", "webview.platforms.winforms", "clr"]

# RapidOCR loads its inference engine by name at runtime: only the ONNX Runtime one is bundled.
OTHER_OCR_ENGINES = ("openvino", "paddle", "pytorch", "torch", "mnn", "tensorrt")


def ocr_module(name):
    return not any(engine in name.split(".") for engine in OTHER_OCR_ENGINES)


hiddenimports = (
    collect_submodules("binder")
    + collect_submodules("uvicorn")
    + collect_submodules("rapidocr", filter=ocr_module)
    + ["sqlcipher3"]
    + gui_imports
)

excludes = ["tkinter", "pytest", "mypy", "ruff", "IPython", "PyQt5", "PySide6", "gi", "torch"]
if not LINUX:
    excludes += ["PyQt6", "qtpy"]

a = Analysis(
    ["binder_app.py"],
    pathex=["../backend/src"],
    # Package metadata: binder.__version__, compared with releases by the updater.
    # RapidOCR: its configuration and OCR models (bundled, never downloaded).
    datas=collect_data_files("binder", includes=["static/**/*", "mobile/*"])
    + collect_data_files("rapidocr", includes=["**/*.yaml", "**/*.onnx", "**/*.txt"])
    + copy_metadata("binder"),
    hiddenimports=hiddenimports,
    excludes=excludes,
)
# Slimming: Qt modules WebEngine does not need, and translations other than fr/en.
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
    # PyInstaller converts the PNG to .ico (Windows) or .icns (macOS) with Pillow.
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
            "CFBundleShortVersionString": version("binder"),
            "NSHighResolutionCapable": True,
        },
    )
