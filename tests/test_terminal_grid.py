#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def main() -> int:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickItem

    from backend.terminal_grid import TerminalGrid

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    host = QQuickItem()
    host.setWidth(800)
    host.setHeight(400)
    grid = TerminalGrid(host)
    grid.setWidth(800)
    grid.setHeight(400)
    grid.feed_text("\x1b[2J\x1b[Hhello")
    shown = grid.vt().display()
    if "hello" not in shown:
        raise AssertionError("grid feed missed text: " + repr(shown))
    replies: list[str] = []
    grid.dataProduced.connect(replies.append)
    grid.feed_text("\x1b[6n")
    if not any("R" in item for item in replies):
        raise AssertionError("grid did not emit cursor report")
    mapped = grid._map_key
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent, Qt

    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
    if mapped(event) != "\x1b[A":
        raise AssertionError("arrow mapping failed")
    _ = app
    print("TERMINAL_GRID_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
