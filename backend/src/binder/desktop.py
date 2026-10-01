"""Desktop application: splash screen, update, internal server and native window.

The system web engine on Windows (Edge WebView2) and macOS (WebKit), Qt on Linux.
The server lives in a thread of the same process: closing the window stops everything.
"""

import contextlib
import json
import logging
import re
import secrets
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from binder import __version__, guard, i18n, updater
from binder.config import get_settings

log = logging.getLogger(__name__)

T = i18n.catalog(
    "desktop",
    {
        "starting": {"en": "Starting…", "fr": "Démarrage…"},
        "opening": {"en": "Opening Binder…", "fr": "Ouverture de Binder…"},
        "update_failed": {
            "en": "The update failed, Binder is starting anyway.",
            "fr": "Mise à jour impossible, Binder démarre quand même.",
        },
        "checking": {"en": "Checking for updates…", "fr": "Recherche de mises à jour…"},
        "downloading": {
            "en": "Downloading version {version}…",
            "fr": "Téléchargement de la version {version}…",
        },
        "installing": {"en": "Installing the update…", "fr": "Installation de la mise à jour…"},
        "progress": {"en": "{done} of {total}", "fr": "{done} sur {total}"},
        "megabytes": {"en": "{value} MB", "fr": "{value} Mo"},
        "version": {"en": "Version {version}", "fr": "Version {version}"},
    },
)

# Language of the last session, written at exit: the splash screen shows before the database
# (and so the saved preferences) is open.
LANGUAGE_FILE = "language"

# Caption colours used until the interface sends its own (same as the --sidebar CSS token).
CAPTION_LIGHT = ("#f5f7f9", "#252e3d")
CAPTION_DARK = ("#0e141e", "#d1d8e2")

SPLASH = """<!doctype html>
<html lang="__LANG__"><head><meta charset="utf-8"><style>
  :root { --bg: #1c2a4f; --fg: #fff; --soft: #c7d0e6; --mute: #9aa6c4;
    --track: rgba(199,208,230,.16); --warn: #f2c879; --out: cubic-bezier(.16,1,.3,1); }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--fg);
    overflow: hidden; cursor: default; user-select: none; -webkit-user-select: none;
    font: 13px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
    -webkit-font-smoothing: antialiased; }
  /* Layout anchored at the top: a two-line status does not move the logo. */
  main { height: 100%; display: flex; flex-direction: column; align-items: center;
    padding-top: 84px; box-sizing: border-box; }
  svg { width: 64px; height: 64px; display: block; }
  .shackle { transform: translateY(-2.5px); animation: lock .7s var(--out) .15s forwards; }
  @keyframes lock { to { transform: none; } }
  h1 { margin: 14px 0 0; font-size: 20px; font-weight: 600; letter-spacing: -.01em; }
  .work { margin-top: 28px; width: 248px; display: flex; flex-direction: column;
    align-items: center; }
  #status { width: 100%; text-align: center; color: var(--soft); min-height: 18px;
    text-wrap: balance; transition: opacity .14s ease-out, transform .14s ease-out; }
  #status.out { opacity: 0; transform: translateY(2px); }
  #status.warn { color: var(--warn); }
  .bar { margin-top: 12px; width: 160px; height: 3px; border-radius: 3px;
    background: var(--track); overflow: hidden; }
  .bar div { height: 100%; border-radius: inherit; background: var(--fg);
    transform: scaleX(0); transform-origin: left; transition: transform .25s var(--out); }
  .bar.busy div { width: 32%; transition: none;
    animation: slide 1.4s cubic-bezier(.65,0,.35,1) infinite; }
  @keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(315%); } }
  #detail { margin-top: 8px; min-height: 15px; font-size: 11px; color: var(--mute);
    font-variant-numeric: tabular-nums; }
  footer { position: absolute; left: 0; right: 0; bottom: 14px; text-align: center;
    font-size: 11px; color: var(--mute); font-variant-numeric: tabular-nums; }
  @media (prefers-reduced-motion: reduce) {
    .shackle { animation: none; transform: none; }
    .bar.busy div { width: 100%; opacity: .35; animation: none; transform: none; }
  }
</style></head><body><main>
  <svg viewBox="0 0 32 32" aria-hidden="true">
    <rect width="32" height="32" rx="8" fill="#2c3d6b"/>
    <path class="shackle" d="M12 14v-3a4 4 0 0 1 8 0v3"
      stroke="#fff" stroke-width="2.4" fill="none"/>
    <rect x="9" y="14" width="14" height="11" rx="2.5" fill="#fff"/>
    <circle cx="16" cy="19.5" r="1.8" fill="#2c3d6b"/></svg>
  <h1>Binder</h1>
  <div class="work" role="status" aria-live="polite">
    <div id="status">__STARTING__</div>
    <div class="bar busy" id="bar"><div id="fill"></div></div>
    <div id="detail"></div>
  </div>
</main><footer>__VERSION__</footer>
<script>
  var $ = function (id) { return document.getElementById(id); };
  var shown = __STARTING_JSON__, pending = null;
  // ratio: null for a step of unknown duration (continuous bar), otherwise 0 to 1.
  function setStatus(text, ratio, detail, tone) {
    var status = $("status"), bar = $("bar"), fill = $("fill");
    var apply = function () {
      pending = null;
      status.textContent = text;
      status.className = tone === "warn" ? "warn" : "";
    };
    if (text !== shown) {
      // Short fade between two steps; progress updates do not flicker.
      shown = text;
      clearTimeout(pending);
      status.classList.add("out");
      pending = setTimeout(apply, 140);
    } else if (pending === null) {
      apply();
    }
    if (ratio === null || ratio === undefined) {
      bar.className = "bar busy";
      fill.style.transform = "";
    } else {
      bar.className = "bar";
      fill.style.transform = "scaleX(" + Math.max(0, Math.min(1, ratio)) + ")";
    }
    $("detail").textContent = detail || "";
  }
</script></body></html>
"""


def _splash_language() -> i18n.Language:
    """Language of the last session, otherwise the system's."""
    with contextlib.suppress(OSError):
        saved = (get_settings().data_dir / LANGUAGE_FILE).read_text(encoding="utf-8").strip()
        for language in i18n.LANGUAGES:
            if saved == language:
                return language
    return i18n.system_locale()[0]


def _remember_language() -> None:
    with contextlib.suppress(Exception):  # never prevent the app from closing
        (get_settings().data_dir / LANGUAGE_FILE).write_text(
            i18n.current_language(), encoding="utf-8"
        )


def splash_html(language: i18n.Language) -> str:
    starting = T.get("starting", language)
    replacements = {
        "__LANG__": language,
        "__STARTING_JSON__": json.dumps(starting),
        "__STARTING__": starting,
        "__VERSION__": T.get("version", language).format(version=__version__),
    }
    html = SPLASH
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)
    return html


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _setup_logging() -> None:
    """Without a console, logs go to DATA_DIR/binder.log."""
    data_dir = get_settings().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        data_dir / "binder.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler],
    )


class Splash:
    def __init__(self, window: Any, language: i18n.Language) -> None:
        self.window = window
        self.language = language
        self._last = 0.0

    def t(self, key: str, **params: Any) -> str:
        """Splash text, in the splash language (the user preferences are not readable yet)."""
        return i18n.render(f"desktop.{key}", params, self.language)

    def status(
        self, text: str, ratio: float | None = None, detail: str = "", tone: str = ""
    ) -> None:
        args = ", ".join(json.dumps(a) for a in (text, ratio, detail, tone))
        self.window.evaluate_js(f"setStatus({args})")

    def progress(self, text: str) -> updater.Progress:
        def report(done: int, total: int) -> None:
            now = time.monotonic()
            if total and (now - self._last > 0.1 or done >= total):
                self._last = now
                detail = self.t("progress", done=self.megabytes(done), total=self.megabytes(total))
                self.status(text, done / total, detail)

        return report

    def megabytes(self, size: int) -> str:
        value = f"{size / 1_000_000:.1f}"
        return self.t(
            "megabytes", value=value.replace(".", ",") if self.language == "fr" else value
        )


# --- Title bar -------------------------------------------------------------------------------
# The main window keeps its native frame: pywebview's frameless windows lose resizing, Snap and
# native dragging on Windows (the form gets no border at all, dragging is emulated in JavaScript,
# and the WebView2 control covers the client area, so hit-testing cannot be added back). Instead
# the native title bar is painted in the app's colours: caption and text colours on Windows 11
# (DWM attributes), light or dark appearance on macOS. On Linux the window manager draws it.

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_NONE = 1
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def _colorref(color: str) -> int:
    """'#rrggbb' → Win32 COLORREF (0x00bbggrr)."""
    value = int(color[1:7], 16)
    return ((value & 0xFF) << 16) | (value & 0xFF00) | ((value >> 16) & 0xFF)


def _paint_windows_caption(hwnd: int, background: str, foreground: str, dark: bool) -> None:
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
    set_attribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    set_attribute.restype = ctypes.c_long
    for attribute, value in (
        # Dark mode first: it decides the colour of the caption buttons.
        (DWMWA_USE_IMMERSIVE_DARK_MODE, int(dark)),
        # pywebview turns Mica on in dark mode, which would tint the caption.
        (DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE),
        # Windows 11 only: Windows 10 rejects these and keeps its own caption colours.
        (DWMWA_CAPTION_COLOR, _colorref(background)),
        (DWMWA_TEXT_COLOR, _colorref(foreground)),
    ):
        data = wintypes.DWORD(value)
        set_attribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))


def _set_macos_appearance(native: Any, dark: bool) -> None:
    from AppKit import NSAppearance
    from PyObjCTools import AppHelper

    name = "NSAppearanceNameDarkAqua" if dark else "NSAppearanceNameAqua"
    # AppKit must be called from the main thread.
    AppHelper.callAfter(lambda: native.setAppearance_(NSAppearance.appearanceNamed_(name)))


def _system_dark() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return int(winreg.QueryValueEx(key, "AppsUseLightTheme")[0]) == 0
    except OSError:
        return False


class WindowApi:
    """Exposed to the interface as `window.pywebview.api` (public methods only)."""

    def __init__(self) -> None:
        self._window: Any = None
        self._hwnd: int | None = None
        self._colors: tuple[str, str, bool] | None = None
        self._watching = False
        # Set once the interface has sent its colours: the window is shown already painted.
        self._styled = threading.Event()

    def set_title_bar(self, background: str, foreground: str, dark: bool) -> None:
        """Called by the interface at startup and whenever its theme changes."""
        if not (HEX_COLOR.fullmatch(str(background)) and HEX_COLOR.fullmatch(str(foreground))):
            return
        self._colors = (background, foreground, bool(dark))
        try:
            self._paint()
        except Exception:
            log.exception("Could not paint the title bar")
        finally:
            self._styled.set()

    def _attach(self, window: Any, dark: bool) -> None:
        """Paints the interface's colours if already sent, otherwise defaults for `dark`."""
        self._window = window
        if self._colors is None:
            self._colors = (*(CAPTION_DARK if dark else CAPTION_LIGHT), dark)
        try:
            self._paint()
        except Exception:
            log.exception("Could not paint the title bar")

    def _wait_styled(self, timeout: float) -> None:
        self._styled.wait(timeout)

    def _paint(self) -> None:
        if self._window is None or self._colors is None or self._window.native is None:
            return
        background, foreground, dark = self._colors
        if sys.platform == "win32":
            if self._hwnd is None:
                self._hwnd = int(self._window.native.Handle.ToInt64())
            _paint_windows_caption(self._hwnd, background, foreground, dark)
            self._watch_system_theme()
        elif sys.platform == "darwin":
            _set_macos_appearance(self._window.native, dark)

    def _watch_system_theme(self) -> None:
        """pywebview resets the caption theme when the system theme changes: paint ours again."""
        if self._watching:
            return
        self._watching = True
        from Microsoft.Win32 import SystemEvents  # pythonnet, loaded by pywebview

        def repaint() -> None:
            with contextlib.suppress(Exception):
                self._paint()

        # Shortly after pywebview's own handler, whose thread and order are not guaranteed.
        SystemEvents.UserPreferenceChanged += lambda _sender, _args: threading.Timer(
            0.3, repaint
        ).start()


class Desktop:
    def __init__(self, finish_update: Path | None) -> None:
        self.finish_update = finish_update
        self.server: uvicorn.Server | None = None
        self.language: i18n.Language = i18n.DEFAULT_LANGUAGE

    def run(self) -> None:
        import webview

        _setup_logging()
        self.language = _splash_language()
        window = webview.create_window(
            "Binder",
            html=splash_html(self.language),
            width=320,
            height=360,
            resizable=False,
            frameless=True,
            background_color="#1c2a4f",
            # pywebview blocks text selection by default: answers and documents must be copyable.
            text_select=True,
        )
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.start(
            self._boot,
            (window,),
            gui="qt" if sys.platform.startswith("linux") else None,
            private_mode=False,
        )
        if self.server:
            _remember_language()
            self.server.should_exit = True

    def _boot(self, window: Any) -> None:
        window.events.loaded.wait(10)
        splash = Splash(window, self.language)
        try:
            if self._update(splash):
                window.destroy()
                return
        except Exception:
            log.exception("Update failed")
            splash.status(splash.t("update_failed"), tone="warn")
            time.sleep(1.5)  # time to read the warning
        splash.status(splash.t("opening"))
        url = self._start_server()

        import webview

        # The main window loads hidden: the splash screen stays until it is ready, without a
        # blank page in between.
        dark = _system_dark()
        api = WindowApi()
        main = webview.create_window(
            "Binder",
            url,
            width=1320,
            height=860,
            min_size=(960, 640),
            hidden=True,
            background_color="#0a1018" if dark else "#f9fafc",  # --background
            js_api=api,
        )
        assert main is not None  # None only when called before webview.start()
        main.events.loaded.wait(15)
        api._attach(main, dark)
        # The interface sends its title bar colours as soon as it starts (it knows the theme).
        api._wait_styled(2)
        main.show()
        window.destroy()

    def _update(self, splash: Splash) -> bool:
        """True if a new version was installed and started: this one must exit."""
        root = updater.install_root()
        if root is None:
            return False
        if self.finish_update is not None:
            splash.status(splash.t("installing"))
            updater.finish(self.finish_update, root)
            updater.launch(self.finish_update)
            return True
        threading.Thread(target=updater.cleanup, args=(root,), daemon=True).start()
        if not get_settings().auto_update:
            return False

        splash.status(splash.t("checking"))
        try:
            release = updater.check()
        except (httpx.HTTPError, ValueError, KeyError) as e:
            log.info("Could not check for updates: %s", e)
            return False
        if release is None:
            return False
        log.info("Updating %s → %s", __version__, release.version)
        text = splash.t("downloading", version=release.version)
        splash.status(text, 0.0)
        new_root = updater.prepare(root, release, splash.progress(text))
        splash.status(splash.t("installing"))
        updater.install(root, new_root)
        return True

    def _start_server(self) -> str:
        from binder.main import app

        port = _free_port()
        url = f"http://127.0.0.1:{port}"
        # Token specific to this launch: other accounts on the machine cannot reach the API.
        token = secrets.token_urlsafe(32)
        get_settings().access_token = token
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        threading.Thread(target=self.server.run, daemon=True).start()
        for _ in range(200):
            try:
                httpx.get(f"{url}/api/status", timeout=0.5)
                break
            except httpx.HTTPError:
                time.sleep(0.05)
        return f"{url}/?{guard.TOKEN_PARAM}={token}"


def run(finish_update: Path | None = None) -> None:
    Desktop(finish_update).run()
