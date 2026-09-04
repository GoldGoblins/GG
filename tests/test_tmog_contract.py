#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def main() -> int:
    from backend.tmog_contract import (
        APPIMAGE_NAMES,
        SCHEMA,
        format_kib,
        pulse,
        resolve_appimage,
        snapshot,
    )
    from backend.surface_intent import parse_surface_intent

    folder = Path(tempfile.mkdtemp(prefix="gg-tmog-"))
    fake = folder / "TMOG-Task-Manager-Linux-x86_64.AppImage"
    fake.write_bytes(b"x" * 1_000_001)
    os.chmod(fake, 0o700)
    found = resolve_appimage(search_dirs=(folder,))
    if found != fake:
        raise AssertionError("allowlisted appimage missed")

    alias = folder / "not-tmog.AppImage"
    alias.write_bytes(b"x" * 1_000_001)
    os.chmod(alias, 0o700)
    if resolve_appimage(search_dirs=(folder,)) != fake:
        raise AssertionError("wrong name accepted")

    link_dir = Path(tempfile.mkdtemp(prefix="gg-tmog-link-"))
    linked = link_dir / "TMOG-Task-Manager-Linux-x86_64.AppImage"
    linked.symlink_to(fake)
    if resolve_appimage(search_dirs=(link_dir,)) is not None:
        raise AssertionError("symlink appimage accepted")

    payload = snapshot()
    if payload.get("schema") != SCHEMA:
        raise AssertionError("snapshot schema")
    json.dumps(payload, separators=(",", ":"))
    if not isinstance(payload.get("processes"), list):
        raise AssertionError("process list missing")
    if not any(str(row.get("comm") or "") for row in payload["processes"]):
        raise AssertionError("process comm still empty after two-pass fill")
    light = snapshot("PERFORMANCE")
    if light.get("processes"):
        raise AssertionError("performance page still walks the process table")
    if light.get("connections"):
        raise AssertionError("performance page still parses tcp tables")
    if not light.get("core_hist"):
        raise AssertionError("performance dropped per-core history")
    if not light.get("cores"):
        raise AssertionError("performance dropped per-core rows")
    summary = snapshot("SUMMARY")
    if not summary.get("processes"):
        raise AssertionError("summary page dropped top processes")
    if summary.get("core_hist"):
        raise AssertionError("summary still ships per-core history")
    if summary.get("cores"):
        raise AssertionError("summary still ships per-core rows")
    if any(
        str(row.get("chip") or "").lower().startswith("nvme")
        for row in (summary.get("temps") or [])
    ):
        raise AssertionError("summary still reads slow nvme hwmon")
    if int(payload.get("process_count") or 0) < 1:
        raise AssertionError("host process count empty")
    if int(payload.get("mem_total_kb") or 0) < 1:
        raise AssertionError("meminfo missing")
    if not isinstance(payload.get("cores"), list):
        raise AssertionError("cpu cores missing")
    if not isinstance(payload.get("cpu_hist"), list):
        raise AssertionError("cpu history missing")
    if not isinstance(payload.get("mounts"), list):
        raise AssertionError("mounts missing")
    for row in payload["processes"]:
        if "pid" not in row or "comm" not in row or "user" not in row:
            raise AssertionError("process row incomplete")
        if "tombstone" not in row:
            raise AssertionError("process tombstone flag missing")
        break
    if "disk_led" not in payload:
        raise AssertionError("blinkendisk missing")
    beat = pulse()
    if beat.get("schema") != SCHEMA:
        raise AssertionError("pulse schema")
    if beat.get("processes"):
        raise AssertionError("60Hz pulse still walks the process table")
    if "cpu_busy" not in beat or "mem_used_kb" not in beat:
        raise AssertionError("pulse dropped live meters")
    if "GiB" not in format_kib(2_097_152) and "MiB" not in format_kib(2048):
        raise AssertionError("kib format")

    if parse_surface_intent("tmog") != "TMOG":
        raise AssertionError("bare tmog intent")
    if parse_surface_intent("öppna tmog") != "TMOG":
        raise AssertionError("open tmog intent")
    if parse_surface_intent("visa task manager") != "TMOG":
        raise AssertionError("task manager intent")

    from backend.chat_surface_host import ChatSurfaceHost

    src = (PROJECT / "backend" / "chat_surface_host.py").read_text(encoding="utf-8")
    if "tmogSnapshot" not in src or "startTmog" not in src:
        raise AssertionError("host tmog slots missing")
    if "tmogPulse" not in src:
        raise AssertionError("host tmog 60Hz pulse missing")
    embed_src = (PROJECT / "backend" / "tmog_embed.py").read_text(encoding="utf-8")
    if "bash -c" in embed_src or "/bin/sh" in embed_src:
        raise AssertionError("generic shell in tmog embed")
    if "QT_QPA_PLATFORM" not in embed_src:
        raise AssertionError("xcb force missing")
    if any(name not in APPIMAGE_NAMES for name in ("TMOG-Task-Manager-Linux-x86_64.AppImage",)):
        raise AssertionError("expected appimage name missing")

    host = ChatSurfaceHost()
    blob = json.loads(host.tmogSnapshot())
    if blob.get("schema") != SCHEMA:
        raise AssertionError("host snapshot schema")
    live = json.loads(host.tmogPulse())
    if live.get("schema") != SCHEMA or "cpu_busy" not in live:
        raise AssertionError("host pulse schema")
    if host.startTmog():
        raise AssertionError("startTmog without qml root must fail closed")

    qml = (PROJECT / "qml" / "components" / "TmogSurface.qml").read_text(encoding="utf-8")
    if 'objectName: "workspaceTmogPane"' not in qml:
        raise AssertionError("tmog pane objectName")
    if 'objectName: "workspaceTmogHole"' not in qml:
        raise AssertionError("tmog hole missing")
    if "interval: 1000" in qml:
        raise AssertionError("tmog still snapshots every second")
    if "interval: 2000" in qml:
        raise AssertionError("tmog meters still jump every two seconds")
    if "interval: 16" not in qml:
        raise AssertionError("tmog dropped 60Hz live meters")
    if "tmogPulse" not in qml:
        raise AssertionError("tmog UI is not driven by the 60Hz pulse")
    if "tmogSnapshot(root.page)" not in qml:
        raise AssertionError("tmog still dumps every page on each tick")
    if "sourceComponent: summaryPage" not in qml:
        raise AssertionError("summary page is still kept alive off-screen")
    if "sourceComponent: performancePage" not in qml:
        raise AssertionError("performance page is still kept alive off-screen")
    if "sourceComponent: listPage" not in qml:
        raise AssertionError("list pages are still kept alive off-screen")
    if 'leftLegend: "TMOG"' in qml:
        raise AssertionError("tmog pane still nests a TMOG GgFrame inside the workspace frame")
    for page in (
        '"SUMMARY"',
        '"PERFORMANCE"',
        '"PROCESSES"',
        '"SYSTEM"',
        '"CONNECTIONS"',
        '"DISK"',
        "TmogSpark",
        "TmogCard",
        "TmogMeter",
        "CPU OVERVIEW",
        "THERMALS",
    ):
        if page not in qml:
            raise AssertionError("tmog page missing: " + page)

    card = (PROJECT / "qml" / "components" / "TmogCard.qml").read_text(encoding="utf-8")
    if "property var tabs" not in card or "signal tabChosen" not in card:
        raise AssertionError("tmog card tabs missing")
    spark = (PROJECT / "qml" / "components" / "TmogSpark.qml").read_text(encoding="utf-8")
    if "property var marks" not in spark:
        raise AssertionError("spark marks missing")
    if "property bool fromZero: true" not in spark:
        raise AssertionError("spark fromZero default must stay true for meters")
    if "renderStrategy: Canvas.Immediate" not in spark:
        raise AssertionError("spark still waits on the scene-graph buffer")
    if "function redraw" not in spark:
        raise AssertionError("spark still paints while hidden")
    if "antialiasing: false" in spark:
        raise AssertionError("spark lines are still aliased dots")
    if 'lineJoin = "round"' not in spark:
        raise AssertionError("spark stroke is still unjoined")

    print("TMOG_CONTRACT_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
