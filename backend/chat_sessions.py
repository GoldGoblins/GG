from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.grok_worker_contract import ENGINE_GROK_TUI, GROK_CWD

CATALOG_PATH = Path(
    "/home/GG/.local/state/goldgoblins/gg-ai-desktop/chat-sessions.json"
)
SCHEMA = "gg.ai-desktop.chat-sessions.v1"
MEMORY = "GoldGoblins"

# Long GoldGoblins work chat (Konsole) — same memory, openable from CHATS.
PROJECT_SESSIONS = (
    ("01a01c8b-5b86-7150-bd01-be262a34eb0d", "GROK_TUI"),
)

ENGINE_LABEL = {
    "GROK_TUI": "GROK TUI",
    "GROK_WORKER": "GROK",
    "LOCAL_QWEN": "QWEN",
    "GPT_TUI": "GPTUI",
}


def _empty() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "memory": MEMORY,
        "cwd": str(GROK_CWD),
        "sessions": [],
    }


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    target = path or CATALOG_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return _empty()
    if not isinstance(payload, dict):
        return _empty()
    rows = payload.get("sessions")
    if not isinstance(rows, list):
        rows = []
    payload["schema"] = SCHEMA
    payload["memory"] = MEMORY
    payload["cwd"] = str(GROK_CWD)
    payload["sessions"] = [row for row in rows if isinstance(row, dict)]
    if target == CATALOG_PATH and _ensure_project_sessions(payload):
        save_catalog(payload, target)
    return payload


def _ensure_project_sessions(catalog: dict[str, Any]) -> bool:
    original_count = len(catalog.get("sessions") or [])
    catalog["sessions"] = [
        row
        for row in catalog.get("sessions") or []
        if str(row.get("session_id") or "").strip() != "ws.tui.gpt"
    ]
    have = {
        str(row.get("session_id") or "").strip()
        for row in catalog.get("sessions") or []
    }
    next_n = 1
    for row in catalog.get("sessions") or []:
        try:
            n = int(row.get("n") or 0)
        except (TypeError, ValueError):
            n = 0
        if n >= next_n:
            next_n = n + 1
    changed = len(catalog["sessions"]) != original_count
    for sid, engine in PROJECT_SESSIONS:
        if sid in have:
            continue
        catalog.setdefault("sessions", []).append(
            {
                "n": next_n,
                "session_id": sid,
                "engine": engine,
            }
        )
        next_n += 1
        changed = True
    return changed


def save_catalog(payload: dict[str, Any], path: Path | None = None) -> None:
    target = path or CATALOG_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return


def remember_session(
    session_id: str,
    engine: str = ENGINE_GROK_TUI,
    path: Path | None = None,
) -> dict[str, Any]:
    sid = str(session_id or "").strip()
    motor = str(engine or ENGINE_GROK_TUI).strip() or ENGINE_GROK_TUI
    catalog = load_catalog(path)
    if not sid:
        return catalog
    for row in catalog["sessions"]:
        if str(row.get("session_id") or "") == sid:
            if not row.get("engine"):
                row["engine"] = motor
            save_catalog(catalog, path)
            return catalog
    next_n = 1
    for row in catalog["sessions"]:
        try:
            n = int(row.get("n") or 0)
        except (TypeError, ValueError):
            n = 0
        if n >= next_n:
            next_n = n + 1
    catalog["sessions"].append(
        {
            "n": next_n,
            "session_id": sid,
            "engine": motor,
        }
    )
    save_catalog(catalog, path)
    return catalog


def sync_owned(
    session_ids: set[str] | list[str],
    engine: str = ENGINE_GROK_TUI,
    path: Path | None = None,
) -> dict[str, Any]:
    catalog = load_catalog(path)
    for sid in session_ids:
        catalog = remember_session(str(sid), engine=engine, path=path)
    return catalog


def list_for_ui(
    current_id: str = "",
    path: Path | None = None,
) -> list[dict[str, Any]]:
    catalog = load_catalog(path)
    current = str(current_id or "").strip()
    rows: list[dict[str, Any]] = []
    for row in catalog.get("sessions") or []:
        sid = str(row.get("session_id") or "").strip()
        if not sid:
            continue
        try:
            n = int(row.get("n") or 0)
        except (TypeError, ValueError):
            n = 0
        engine = str(row.get("engine") or ENGINE_GROK_TUI)
        label = ENGINE_LABEL.get(engine, engine.replace("_", " "))
        rows.append(
            {
                "n": n,
                "session_id": sid,
                "engine": engine,
                "label": "session " + str(n) + "  ·  " + label,
                "current": sid == current,
                "memory": MEMORY,
            }
        )
    rows.sort(key=lambda item: int(item["n"]), reverse=True)
    return rows
