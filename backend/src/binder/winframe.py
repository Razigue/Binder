"""Windows: the main window's title bar is drawn by the interface.

The window keeps its normal frame (caption and sizing border), so Aero Snap, Snap Layouts,
Win + arrows, the shadow, the animations and resizing by the borders stay native. Only the caption
is folded into the client area, by answering WM_NCCALCSIZE in a subclassed window procedure.
pywebview's frameless mode would drop the frame styles, and Snap with them; its drag region moves
the window by hand, without snapping.

Accepted limit: the top edge no longer resizes the window (the web view covers it).
"""

import ctypes
import sys
from collections.abc import Callable
from ctypes import wintypes
from typing import Any

# Imported on Windows only; mypy skips the rest of the module on other platforms.
assert sys.platform == "win32"

WM_WINDOWPOSCHANGING = 0x0046
WM_WINDOWPOSCHANGED = 0x0047
WM_NCCALCSIZE = 0x0083
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2
GWLP_WNDPROC = -4
SM_CYFRAME = 33
SM_CXPADDEDBORDER = 92
SWP_NOSIZE = 0x0001
# SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOMOVE | SWP_NOSIZE: recompute the frame only.
SWP_FRAME_ONLY = 0x0027
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
VK_LWIN = 0x5B
VK_Z = 0x5A
KEYEVENTF_KEYUP = 0x0002
WINDOWS_11_BUILD = 22000

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class NCCALCSIZE_PARAMS(ctypes.Structure):  # noqa: N801 (Win32 name)
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


class WINDOWPOS(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("hwndInsertAfter", wintypes.HWND),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("cx", ctypes.c_int),
        ("cy", ctypes.c_int),
        ("flags", wintypes.UINT),
    ]


# A private handle on user32: pywebview declares its own prototypes on `ctypes.windll.user32`.
user32 = ctypes.WinDLL("user32", use_last_error=True)


def _declare(name: str, restype: Any, *argtypes: Any) -> None:
    # HWND and pointers are 64 bits: without prototypes ctypes would truncate them to int.
    function = getattr(user32, name)
    function.argtypes = list(argtypes)
    function.restype = restype


_declare("SetWindowLongPtrW", ctypes.c_void_p, wintypes.HWND, ctypes.c_int, ctypes.c_void_p)
_declare(
    "CallWindowProcW",
    LRESULT,
    ctypes.c_void_p,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
_declare("IsZoomed", wintypes.BOOL, wintypes.HWND)
_declare("IsIconic", wintypes.BOOL, wintypes.HWND)
_declare("GetSystemMetrics", ctypes.c_int, ctypes.c_int)
_declare(
    "SetWindowPos",
    wintypes.BOOL,
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
)
_declare("ReleaseCapture", wintypes.BOOL)
_declare("GetCursorPos", wintypes.BOOL, ctypes.POINTER(wintypes.POINT))
_declare("SendMessageW", LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_declare("ShowWindow", wintypes.BOOL, wintypes.HWND, ctypes.c_int)
_declare("GetForegroundWindow", wintypes.HWND)
_declare("keybd_event", None, wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t)

# Window procedures handed to Windows: a collected callback would crash the process.
_procedures: dict[int, Any] = {}


def _on_ui_thread(window: Any, action: Callable[[], None], wait: bool = True) -> None:
    from System import Action  # pythonnet, loaded by pywebview

    native = window.native
    if wait:
        native.Invoke(Action(action))
    else:
        native.BeginInvoke(Action(action))


class CustomFrame:
    """Native frame without the caption, plus the window commands of the HTML title bar."""

    def __init__(self, window: Any) -> None:
        self.window = window
        self.hwnd = 0
        self._resized = False  # maximised or minimised
        self._restoring = False

    def install(self) -> None:
        def install() -> None:
            self.hwnd = int(self.window.native.Handle.ToInt64())
            original = 0

            def procedure(hwnd: int, message: int, wparam: int, lparam: int) -> int:
                if message == WM_NCCALCSIZE and wparam:
                    # Let Windows place the side and bottom borders, then give the caption
                    # height back to the client area.
                    params = NCCALCSIZE_PARAMS.from_address(lparam)
                    top = params.rgrc[0].top
                    user32.CallWindowProcW(original, hwnd, message, wparam, lparam)
                    if user32.IsZoomed(hwnd):
                        # A maximised window overhangs the screen by its border: keep the top
                        # of the interface on screen.
                        top += user32.GetSystemMetrics(SM_CYFRAME) + user32.GetSystemMetrics(
                            SM_CXPADDEDBORDER
                        )
                    params.rgrc[0].top = top
                    return 0
                if message == WM_WINDOWPOSCHANGING and self._restoring:
                    # WinForms restores the size it remembers as a client size plus a caption
                    # that is no longer there: the window would grow at every restore. Windows
                    # has already put back the right size.
                    WINDOWPOS.from_address(lparam).flags |= SWP_NOSIZE
                if message == WM_WINDOWPOSCHANGED:
                    resized = bool(user32.IsZoomed(hwnd) or user32.IsIconic(hwnd))
                    self._restoring = self._resized and not resized
                    self._resized = resized
                    try:
                        return int(user32.CallWindowProcW(original, hwnd, message, wparam, lparam))
                    finally:
                        self._restoring = False
                return int(user32.CallWindowProcW(original, hwnd, message, wparam, lparam))

            callback = WNDPROC(procedure)
            _procedures[self.hwnd] = callback
            original = user32.SetWindowLongPtrW(
                self.hwnd, GWLP_WNDPROC, ctypes.cast(callback, ctypes.c_void_p)
            )
            if not original:
                raise ctypes.WinError(ctypes.get_last_error())
            user32.SetWindowPos(self.hwnd, None, 0, 0, 0, 0, SWP_FRAME_ONLY)

        _on_ui_thread(self.window, install)

    def maximized(self) -> bool:
        return bool(self.hwnd and user32.IsZoomed(self.hwnd))

    def drag(self) -> None:
        """Hands the pressed mouse button to Windows' own move loop (Snap included)."""

        def drag() -> None:
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            position = ((point.y & 0xFFFF) << 16) | (point.x & 0xFFFF)
            user32.ReleaseCapture()
            user32.SendMessageW(self.hwnd, WM_NCLBUTTONDOWN, HTCAPTION, position)

        # The move loop lasts as long as the drag: do not hold the calling thread.
        _on_ui_thread(self.window, drag, wait=False)

    def minimize(self) -> None:
        _on_ui_thread(self.window, lambda: user32.ShowWindow(self.hwnd, SW_MINIMIZE))

    def toggle_maximize(self) -> None:
        def toggle() -> None:
            user32.ShowWindow(self.hwnd, SW_RESTORE if self.maximized() else SW_MAXIMIZE)

        _on_ui_thread(self.window, toggle)

    def snap_layouts(self) -> None:
        """Opens the Snap Layouts flyout (Win + Z), as hovering the native maximise button does."""
        if sys.getwindowsversion().build < WINDOWS_11_BUILD:
            return
        # The shortcut acts on the foreground window, which may not be this one.
        if user32.GetForegroundWindow() != self.hwnd:
            return
        for key in (VK_LWIN, VK_Z):
            user32.keybd_event(key, 0, 0, 0)
        for key in (VK_Z, VK_LWIN):
            user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)
