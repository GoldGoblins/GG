#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from backend import flow_tui
from backend.grok_worker_contract import ENGINE_FLOW_TUI, ENGINE_TARGETS, normalize_engine_target


def main() -> int:
    if ENGINE_FLOW_TUI not in ENGINE_TARGETS:
        raise AssertionError("FLOW_TUI must be a first-class engine")
    if normalize_engine_target("FLOW_TUI") != ENGINE_FLOW_TUI:
        raise AssertionError("normalize FLOW_TUI")
    if flow_tui.PARALLEL_AGENT_BRAIN != "FORBIDDEN":
        raise AssertionError("flow tui must not spawn extra brains")

    empty = flow_tui.reset()
    if empty["engine"] != "FLOW_TUI":
        raise AssertionError("engine id")
    if empty["grok"]["motor"] != "GROK_TUI" or empty["gpt"]["motor"] != "GPT_TUI":
        raise AssertionError("two house motors")

    board = flow_tui.submit("koda FlowTuiHole.qml och testa test_flow_tui.py")
    if "qml" not in " ".join(board["grok"]["jobs"]).lower() and "house" not in " ".join(
        board["grok"]["jobs"]
    ).lower():
        raise AssertionError("GROK should keep house/qml work")
    if not board["gpt"]["jobs"]:
        raise AssertionError("GPTUI packet missing")
    if board["reflect"]["after"] != "reconverge":
        raise AssertionError("reflect must follow merge")
    if board["reflect"]["author"] == "DEV":
        raise AssertionError("critic must not be the author")
    if board["transcript"][0]["role"] != "YOU":
        raise AssertionError("transcript starts with the user")

    main_qml = (PROJECT / "qml/Main.qml").read_text(encoding="utf-8")
    if 'leftLegend: "CHAT · UNIVERSAL OPERATIONAL STREAM"' not in main_qml:
        raise AssertionError("UOS chrome was changed")
    if 'objectName: "grokTuiHost"' not in main_qml or 'objectName: "gptTuiHost"' not in main_qml:
        raise AssertionError("existing TUI holes must remain")
    if 'objectName: "flowTuiHost"' not in main_qml:
        raise AssertionError("FLOW TUI hole missing")
    hole = (PROJECT / "qml/components/FlowTuiHole.qml").read_text(encoding="utf-8")
    if 'objectName: "flowTuiInputBar"' not in hole or 'anchors.bottom: parent.bottom' not in hole:
        raise AssertionError("FLOW TUI prompt must stay pinned to the bottom")
    workspace = (PROJECT / "qml/components/WorkspaceSurface.qml").read_text(
        encoding="utf-8"
    )
    hide = workspace[
        workspace.index("id: authoringSurface") : workspace.index("id: codeHost")
    ]
    if 'hostKind !== "FLOW"' not in hide:
        raise AssertionError("CODE editor still shows under FLOW")
    grok_at = main_qml.index('objectName: "grokTuiHost"')
    gpt_at = main_qml.index('objectName: "gptTuiHost"')
    flow_at = main_qml.index('objectName: "flowTuiHost"')
    if not (grok_at < gpt_at < flow_at):
        raise AssertionError("FLOW TUI must sit after GPTUI")

    composer = (PROJECT / "qml/components/ContextComposer.qml").read_text(encoding="utf-8")
    gpt_tab = composer.index('text: "GPTUI"')
    flow_tab = composer.index('text: "FLOW TUI"')
    if flow_tab < gpt_tab:
        raise AssertionError("composer FLOW TUI tab must follow GPTUI")

    settings = (PROJECT / "qml/components/SettingsChatModule.qml").read_text(
        encoding="utf-8"
    )
    if 'text: "FLOW TUI"' not in settings:
        raise AssertionError("settings chat missing FLOW TUI")

    host = (PROJECT / "backend/chat_surface_host.py").read_text(encoding="utf-8")
    for marker in ("def flowTuiSubmit", "def flowTuiStatus", "def flowTuiReset"):
        if marker not in host:
            raise AssertionError("host slot missing: " + marker)
    print("test_flow_tui: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
