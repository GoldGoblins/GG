"""Read the local Codex session usage records for the telemetry rail."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

CODEX_SESSIONS = Path("/home/GG/.codex/sessions")
CODEX_SESSION_STATE = Path(
    "/home/GG/.local/state/goldgoblins/gg-ai-desktop/codex-tui-session.json"
)
_SESSION_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def _fmt(value: int | None) -> str:
    if value is None or value < 0:
        return "—"
    if value >= 1_000_000:
        text = f"{value / 1_000_000:.2f}M"
        return text.replace(".00M", "M")
    if value >= 1000:
        return f"{value // 1000}K"
    return str(value)


def _reset_label(value: Any) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return "—"
    if timestamp <= 0:
        return "—"
    try:
        return datetime.fromtimestamp(timestamp).astimezone().strftime("%H:%M")
    except (OverflowError, OSError, ValueError):
        return "—"


def _latest_session() -> Path | None:
    try:
        rows = list(CODEX_SESSIONS.rglob("*.jsonl"))
    except OSError:
        return None
    if not rows:
        return None
    return max(rows, key=lambda path: path.stat().st_mtime)


def _session_meta(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            row = json.loads(stream.readline())
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    payload = row.get("payload") if isinstance(row, dict) else None
    return payload if isinstance(payload, dict) else {}


def session_id_from_file(path: Path) -> str:
    meta = _session_meta(path)
    sid = str(meta.get("session_id") or meta.get("id") or "").strip()
    return sid if _SESSION_ID_RE.fullmatch(sid) else ""


def discover_sessions(cwd: str = "/home/GG/GoldGoblins") -> list[str]:
    """Return real saved Codex sessions for this workspace, newest first."""
    rows: list[tuple[float, str]] = []
    try:
        paths = CODEX_SESSIONS.rglob("*.jsonl")
    except OSError:
        return []
    for path in paths:
        meta = _session_meta(path)
        if str(meta.get("cwd") or "") != cwd:
            continue
        sid = session_id_from_file(path)
        if sid:
            try:
                rows.append((path.stat().st_mtime, sid))
            except OSError:
                pass
    rows.sort(reverse=True)
    return list(dict.fromkeys(sid for _mtime, sid in rows))


def load_session_id(path: Path = CODEX_SESSION_STATE) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ""
    sid = str(payload.get("session_id") or "") if isinstance(payload, dict) else ""
    return sid if _SESSION_ID_RE.fullmatch(sid) else ""


def save_session_id(session_id: str, path: Path = CODEX_SESSION_STATE) -> str:
    sid = str(session_id or "").strip()
    if not _SESSION_ID_RE.fullmatch(sid):
        return ""
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(json.dumps({"session_id": sid}) + "\n", encoding="utf-8")
    except OSError:
        return ""
    return sid


def snapshot(session: Path | None = None) -> dict[str, Any]:
    path = session or _latest_session()
    latest_tokens: dict[str, Any] = {}
    latest_turn: dict[str, Any] = {}
    latest_limits: dict[str, Any] = {}
    if path is not None:
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    payload = row.get("payload") if isinstance(row, dict) else None
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("type") == "token_count":
                        info = payload.get("info") or {}
                        usage = info.get("total_token_usage")
                        if isinstance(usage, dict):
                            latest_tokens = usage
                        turn_usage = info.get("last_token_usage")
                        if isinstance(turn_usage, dict):
                            latest_turn = turn_usage
                        window = info.get("model_context_window")
                        if window is not None:
                            latest_tokens["model_context_window"] = window
                    limits = payload.get("rate_limits")
                    if isinstance(limits, dict):
                        latest_limits = limits
        except OSError:
            pass

    total = latest_tokens.get("total_tokens")
    context_used = latest_turn.get("input_tokens")
    context_window = latest_tokens.get("model_context_window")
    turn = latest_turn.get("total_tokens")
    primary = latest_limits.get("primary") or {}
    secondary = latest_limits.get("secondary") or {}
    try:
        total_n = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_n = None
    try:
        context_n = int(context_used) if context_used is not None else None
    except (TypeError, ValueError):
        context_n = None
    try:
        window_n = int(context_window) if context_window is not None else None
    except (TypeError, ValueError):
        window_n = None
    try:
        turn_n = int(turn) if turn is not None else None
    except (TypeError, ValueError):
        turn_n = None
    try:
        weekly = float(secondary.get("used_percent"))
        weekly_n = int(round(weekly)) if 0 <= weekly <= 100 else None
    except (TypeError, ValueError):
        weekly_n = None
    try:
        live = float(primary.get("used_percent"))
        live_n = int(round(live)) if 0 <= live <= 100 else 0
    except (TypeError, ValueError):
        live_n = 0
    live_reset_at = primary.get("resets_at")
    return {
        "session": str(path) if path else "",
        "context_label": _fmt(context_n) + "/" + _fmt(window_n) if context_n is not None and window_n is not None else "—",
        "session_total_label": _fmt(total_n),
        "turn_label": _fmt(turn_n),
        "live_tokens": live_n,
        "live_label": str(live_n) + "%",
        "live_reset_at": live_reset_at,
        "live_reset_label": _reset_label(live_reset_at),
        "weekly_percent": weekly_n,
        "context_used": context_n,
        "context_window": window_n,
        "session_total": total_n,
        "turn_tokens": turn_n,
    }
