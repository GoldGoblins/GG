from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

XPROP = Path("/usr/bin/xprop")
WMCTRL = Path("/usr/bin/wmctrl")


def apply_desktop_shell_window(window: object, enabled: bool) -> None:
    if window is None:
        return
    on = bool(enabled)
    flags = getattr(window, "setFlag", None)
    if callable(flags):
        flags(Qt.WindowType.FramelessWindowHint, on)
        flags(Qt.WindowType.WindowStaysOnBottomHint, on)
    screen = None
    getter = getattr(window, "screen", None)
    if callable(getter):
        try:
            screen = getter()
        except RuntimeError:
            screen = None
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if on and screen is not None:
        geo = screen.availableGeometry()
        setter = getattr(window, "setGeometry", None)
        if callable(setter):
            setter(geo)
        show = getattr(window, "show", None)
        if callable(show):
            show()
    elif not on:
        maximize = getattr(window, "showMaximized", None)
        if callable(maximize):
            maximize()
    _apply_x11_stack(window, on)


def _window_xid(window: object) -> int:
    if str(QGuiApplication.platformName() or "") != "xcb":
        return 0
    win_id = getattr(window, "winId", None)
    if not callable(win_id):
        return 0
    try:
        return int(win_id())
    except (TypeError, ValueError, RuntimeError):
        return 0


def _apply_x11_stack(window: object, enabled: bool) -> None:
    xid = _window_xid(window)
    if xid <= 0:
        return
    hex_id = hex(xid)
    if WMCTRL.is_file() and os.access(WMCTRL, os.X_OK):
        action = "add" if enabled else "remove"
        _run(
            [
                str(WMCTRL),
                "-i",
                "-r",
                hex_id,
                "-b",
                action + ",below,skip_taskbar,skip_pager",
            ]
        )
        return
    if not XPROP.is_file() or not os.access(XPROP, os.X_OK):
        return
    value = (
        "_NET_WM_STATE_BELOW,_NET_WM_STATE_SKIP_TASKBAR,_NET_WM_STATE_SKIP_PAGER"
        if enabled
        else ""
    )
    _run(
        [
            str(XPROP),
            "-id",
            hex_id,
            "-f",
            "_NET_WM_STATE",
            "32a",
            "-set",
            "_NET_WM_STATE",
            value,
        ]
    )


def _run(argv: list[str]) -> None:
    try:
        subprocess.run(
            argv,
            timeout=1.0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
