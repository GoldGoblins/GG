#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def main() -> int:
    from backend import desktop_settings

    saved_path = desktop_settings.SETTINGS_PATH
    scratch = Path(tempfile.mkdtemp(prefix="gg-desktop-settings-"))
    desktop_settings.SETTINGS_PATH = scratch / "settings-v1.json"
    try:
        loaded = desktop_settings.load_settings()
        if loaded["engineTarget"] != "LOCAL_QWEN":
            raise AssertionError("missing defaults")
        path = desktop_settings.save_settings(
            {
                "engineTarget": "GROK_WORKER",
                "chatWidthRatio": 0.9,
                "telemetryWidth": 10,
                "utilityHeight": 999,
                "accentColor": "#FF112233",
                "frameBorder": "not-a-color",
                "frameRadius": -3,
                "showInnerEditorChrome": 0,
                "showProductSourceTabs": 1,
            }
        )
        if not Path(path).is_file():
            raise AssertionError("settings file missing")
        again = desktop_settings.load_settings()
        if again["engineTarget"] != "GROK_WORKER":
            raise AssertionError("engine did not persist")
        desktop_settings.save_settings({"engineTarget": "GROK_TUI"})
        tui = desktop_settings.load_settings()
        if tui["engineTarget"] != "GROK_TUI":
            raise AssertionError("GROK_TUI did not persist")
        if again["chatWidthRatio"] != 0.5:
            raise AssertionError("chat width was not clamped")
        if again["telemetryWidth"] != 120:
            raise AssertionError("telemetry width was not clamped")
        if again["utilityHeight"] != 220:
            raise AssertionError("utility height was not clamped")
        if again["accentColor"] != "#112233":
            raise AssertionError("accent color not normalized")
        if again["frameBorder"] != "#6a6a6a":
            raise AssertionError("bad border color was accepted")
        if again["frameRadius"] != 0:
            raise AssertionError("frame radius was not clamped")
        if again["showInnerEditorChrome"] is not False:
            raise AssertionError("bool inner chrome mismatch")
        if again["showProductSourceTabs"] is not True:
            raise AssertionError("bool product tabs mismatch")
        rejected = desktop_settings.normalize_settings(
            {"engineTarget": "OPEN_INTERNET"}
        )
        if rejected["engineTarget"] != "LOCAL_QWEN":
            raise AssertionError("unknown engine was accepted")
        class Root:
            def __init__(self) -> None:
                self.props = {}

            def setProperty(self, name, value) -> None:
                self.props[name] = value

        root = Root()
        desktop_settings.apply_to_root(root, again)
        if root.props.get("engineTarget") != "GROK_WORKER":
            raise AssertionError("apply_to_root missed engine")
        if root.props.get("cyan") != "#112233":
            raise AssertionError("apply_to_root missed accent")
    finally:
        desktop_settings.SETTINGS_PATH = saved_path
    print("DESKTOP_SETTINGS_TEST=PASS")
    print("SETTINGS=LOCAL_JSON_CLAMPED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
