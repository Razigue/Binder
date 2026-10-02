"""Desktop application: splash screen, update, internal server and native window.

The system web engine on Windows (Edge WebView2) and macOS (WebKit), Qt on Linux.
The server lives in a thread of the same process: closing the window stops everything.
"""

import base64
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
  __FONT__
  /* The app's tokens (index.css): cool paper and ink navy, graphite and paper in dark mode. */
  :root { --bg: oklch(0.985 0.003 250); --fg: oklch(0.22 0.03 260);
    --soft: oklch(0.4 0.025 260); --mute: oklch(0.52 0.02 258);
    --tile: oklch(0.28 0.07 262); --glyph: #fff; --track: oklch(0.93 0.008 255);
    --edge: oklch(0.925 0.008 255); --warn: #b45309; --out: cubic-bezier(.16,1,.3,1); }
  @media (prefers-color-scheme: dark) {
    :root { --bg: oklch(0.175 0.002 260); --fg: oklch(0.94 0.002 260);
      --soft: oklch(0.82 0.003 260); --mute: oklch(0.71 0.004 260);
      --tile: oklch(0.93 0.004 260); --glyph: oklch(0.2 0.006 260);
      --track: oklch(0.27 0.004 260); --edge: oklch(1 0 0 / 8%); --warn: #fcd34d; }
  }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--fg);
    overflow: hidden; cursor: default; user-select: none; -webkit-user-select: none;
    font: 13px/1.45 Geist, system-ui, -apple-system, "Segoe UI", sans-serif;
    -webkit-font-smoothing: antialiased; }
  /* Frameless window: a hairline keeps a light splash apart from a light desktop. */
  body::after { content: ""; position: fixed; inset: 0; pointer-events: none;
    box-shadow: inset 0 0 0 1px var(--edge); }
  /* Layout anchored at the top: a two-line status does not move the logo. */
  main { height: 100%; display: flex; flex-direction: column; align-items: center;
    padding-top: 80px; box-sizing: border-box; animation: page .22s ease-out; }
  @keyframes page { from { opacity: 0; } }
  svg { width: 60px; height: 60px; display: block; }
  .tile { fill: var(--tile); }
  .glyph { fill: var(--glyph); }
  /* The sleeves of the binder appear one after the other. */
  .sleeve { fill: var(--tile); opacity: 0; animation: sleeve .35s var(--out) .1s forwards; }
  .sleeve:nth-of-type(2) { animation-delay: .2s; }
  .sleeve:nth-of-type(3) { animation-delay: .3s; }
  .sleeve:nth-of-type(4) { animation-delay: .4s; }
  @keyframes sleeve { to { opacity: 1; } }
  h1 { margin: 16px 0 0; font-size: 20px; font-weight: 600; letter-spacing: -.025em; }
  .work { margin-top: 26px; width: 248px; display: flex; flex-direction: column;
    align-items: center; }
  #status { width: 100%; text-align: center; color: var(--soft); min-height: 19px;
    text-wrap: balance; transition: opacity .14s ease-out; }
  #status.out { opacity: 0; }
  #status.warn { color: var(--warn); }
  .bar { margin-top: 14px; width: 168px; height: 4px; border-radius: 4px;
    background: var(--track); overflow: hidden; }
  .bar div { height: 100%; border-radius: inherit; background: var(--tile);
    transform: scaleX(0); transform-origin: left; transition: transform .25s var(--out); }
  .bar.busy div { width: 32%; transition: none;
    animation: slide 1.4s cubic-bezier(.65,0,.35,1) infinite; }
  @keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(315%); } }
  #detail { margin-top: 8px; min-height: 16px; font-size: 11px; color: var(--mute);
    font-variant-numeric: tabular-nums; }
  footer { position: absolute; left: 0; right: 0; bottom: 16px; text-align: center;
    font-size: 11px; color: var(--mute); font-variant-numeric: tabular-nums; }
  @media (prefers-reduced-motion: reduce) {
    main { animation: none; }
    .sleeve { animation: none; opacity: 1; }
    .bar.busy div { width: 100%; opacity: .35; animation: none; transform: none; }
  }
</style></head><body><main>
  <svg viewBox="0 0 32 32" aria-hidden="true">
    <rect class="tile" width="32" height="32" rx="8"/>
    <rect class="glyph" x="8" y="6" width="16" height="20" rx="2.2"/>
    <rect class="tile" x="11" y="6" width="1.1" height="20"/>
    <g><rect class="sleeve" x="13.6" y="10" width="3.8" height="5.4" rx=".6"/>
      <rect class="sleeve" x="18.6" y="10" width="3.8" height="5.4" rx=".6"/>
      <rect class="sleeve" x="13.6" y="16.6" width="3.8" height="5.4" rx=".6"/>
      <rect class="sleeve" x="18.6" y="16.6" width="3.8" height="5.4" rx=".6"/></g></svg>
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


def _splash_font() -> str:
    """The app's Geist, inlined: the splash shows before the server that serves it."""
    assets = Path(__file__).parent / "static" / "assets"
    for path in sorted(assets.glob("geist-latin-wght-normal-*.woff2")):
        with contextlib.suppress(OSError):
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            return (
                "@font-face { font-family: Geist; font-weight: 100 900; "
                f'src: url(data:font/woff2;base64,{data}) format("woff2"); }}'
            )
    return ""  # interface not built: system font


def splash_html(language: i18n.Language) -> str:
    starting = T.get("starting", language)
    replacements = {
        "__FONT__": _splash_font(),
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
# On Windows the interface draws the title bar (logo, title, window buttons) on a window that
# keeps its native frame: see winframe.py. The DWM caption colours below still tint the window
# border and the system dark mode. On macOS the native title bar follows the app's light/dark
# choice; on Linux the window manager draws it.

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


def _center_windows(hwnd: int) -> None:
    """Centres the window in the work area of the screen under the mouse pointer.

    WinForms' CenterScreen places the window before its size is final under display scaling,
    so the splash screen ended up off centre.
    """
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.windll.user32
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    cursor, window = wintypes.POINT(), wintypes.RECT()
    user32.GetCursorPos(ctypes.byref(cursor))
    info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
    monitor = user32.MonitorFromPoint(cursor, 2)  # MONITOR_DEFAULTTONEAREST
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return
    user32.GetWindowRect(hwnd, ctypes.byref(window))
    work = info.rcWork
    x = work.left + (work.right - work.left - (window.right - window.left)) // 2
    y = work.top + (work.bottom - work.top - (window.bottom - window.top)) // 2
    # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
    user32.SetWindowPos(hwnd, None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)


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
        self._frame: Any = None  # winframe.CustomFrame once installed
        # Set once the frame is settled (custom or not): the interface asks before drawing.
        self._framed = threading.Event()

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

    def window_state(self) -> dict[str, bool]:
        """`custom`: the interface draws the title bar. `maximized`: for the maximise button."""
        self._framed.wait(5)
        frame = self._frame
        return {"custom": frame is not None, "maximized": bool(frame and frame.maximized())}

    def drag(self) -> None:
        """Mouse pressed on the title bar: Windows moves the window (Snap included)."""
        if self._frame:
            self._frame.drag()

    def minimize(self) -> None:
        if self._frame:
            self._frame.minimize()

    def toggle_maximize(self) -> None:
        if self._frame:
            self._frame.toggle_maximize()

    def snap_layouts(self) -> None:
        if self._frame:
            self._frame.snap_layouts()

    def close(self) -> None:
        if self._window is not None:
            self._window.destroy()

    def choose_folder(self, initial: str = "") -> str | None:
        """System folder dialog, for the watched folder. None if cancelled."""
        import webview

        if self._window is None:
            return None
        start = Path(str(initial)).expanduser() if initial else Path.home()
        chosen = self._window.create_file_dialog(
            webview.FileDialog.FOLDER, directory=str(start if start.is_dir() else Path.home())
        )
        if not chosen:
            return None
        return str(chosen[0] if isinstance(chosen, (list, tuple)) else chosen)

    def _attach(self, window: Any, dark: bool) -> None:
        """Paints the interface's colours if already sent, otherwise defaults for `dark`."""
        self._window = window
        if sys.platform == "win32":
            from binder import winframe

            try:
                frame = winframe.CustomFrame(window)
                frame.install()
                self._frame = frame
            except Exception:
                log.exception("Could not hide the native caption")
        self._framed.set()
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


def _share_qt_profile() -> None:
    """One Qt WebEngine profile for every window.

    pywebview (6.2.1) gives each Qt window its own persistent profile, all named "pywebview" and
    stored in the same folder. Two of them in one process (the splash screen, then the main
    window) make Qt WebEngine spin, its memory grows, and the main window stays blank.
    """
    import importlib

    # Untyped on purpose: QWebEngineProfile is not part of the module's public interface.
    qt: Any = importlib.import_module("webview.platforms.qt")
    original = qt.QWebEngineProfile
    profiles: dict[str, Any] = {}

    def profile(*args: Any) -> Any:
        if not args:  # private mode: one throwaway profile per window is fine
            return original()
        name = args[0]
        if name not in profiles:
            profiles[name] = original(*args)
        return profiles[name]

    qt.QWebEngineProfile = profile


class Desktop:
    def __init__(self) -> None:
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
            # Windows: shown once centred by _boot.
            hidden=sys.platform == "win32",
            background_color="#101011" if _system_dark() else "#f9fafc",  # --bg
            # pywebview blocks text selection by default: answers and documents must be copyable.
            text_select=True,
        )
        webview.settings["ALLOW_DOWNLOADS"] = True
        if sys.platform.startswith("linux"):
            _share_qt_profile()
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
        if sys.platform == "win32":
            with contextlib.suppress(Exception):  # a misplaced splash beats no splash
                _center_windows(int(window.native.Handle.ToInt64()))
            window.show()
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
            background_color="#101011" if dark else "#f9fafc",  # --background
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
        """Velopack: downloads the update, then applies it once this process has exited.

        True if an update is being applied: this process must exit.
        """
        manager = updater.installed()
        if manager is None or not get_settings().auto_update:
            return False
        splash.status(splash.t("checking"))
        try:
            info = manager.check_for_updates()
        except Exception as e:  # offline, GitHub unreachable
            log.info("Could not check for updates: %s", e)
            return False
        if info is None:
            return False
        version = str(info.TargetFullRelease.Version)
        log.info("Updating %s → %s", __version__, version)
        text = splash.t("downloading", version=version)
        splash.status(text, 0.0)
        size, report = updater.download_size(info), splash.progress(text)
        manager.download_updates(info, lambda percent: report(size * int(percent) // 100, size))
        splash.status(splash.t("installing"))
        manager.wait_exit_then_apply_updates(info, silent=True, restart=True)
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


def run() -> None:
    Desktop().run()
