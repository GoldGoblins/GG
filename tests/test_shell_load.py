#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def main() -> int:
    from backend.shell_load import queue

    rows = queue()
    if "qml/components/WorkspaceSurface.qml" not in rows:
        raise AssertionError("workspace entry missing")
    if rows[-1] != "qml/components/WorkspaceSurface.qml":
        raise AssertionError("workspace must load last")
    for name in (
        "qml/components/GgFrame.qml",
        "qml/components/TmogSurface.qml",
        "qml/components/CryptoSurface.qml",
        "qml/components/MediaSurface.qml",
        "qml/components/WebPane.qml",
        "qml/components/WorkObject.qml",
        "qml/components/SettingsSurface.qml",
    ):
        if name not in rows:
            raise AssertionError("missing real dependency: " + name)
    if "qml/terminal-hole/xterm.min.js" in rows:
        raise AssertionError("unrelated shell dump leaked into queue")
    if len(rows) < 8:
        raise AssertionError("queue too small to be a real graph")
    if len(rows) != len(set(rows)):
        raise AssertionError("duplicate load paths")
    print("SHELL_LOAD_QUEUE=" + str(len(rows)))
    print("SHELL_LOAD_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
