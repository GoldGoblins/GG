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
    if not isinstance(payload.get("processes"), list):
        raise AssertionError("process list missing")
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
        break
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
    if host.startTmog():
        raise AssertionError("startTmog without qml root must fail closed")

    qml = (PROJECT / "qml" / "components" / "TmogSurface.qml").read_text(encoding="utf-8")
    if 'objectName: "workspaceTmogPane"' not in qml:
        raise AssertionError("tmog pane objectName")
    if 'objectName: "workspaceTmogHole"' not in qml:
        raise AssertionError("tmog hole missing")
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

    print("TMOG_CONTRACT_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
