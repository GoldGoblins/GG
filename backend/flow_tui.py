"""FLOW TUI — joint chat for GROK TUI and GPTUI in one house.

Additive layer. The Universal Operational Stream, GROK TUI PTY, and GPTUI
PTY stay as they are. This board sends one user ask to both motors and
shows their real replies in one stream. It does not spawn extra brains.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any

from backend import agent_flow


SCHEMA = "gg.flow-tui.v1"
ENGINE = "FLOW_TUI"
ACTION_AUTHORITY = "NONE"
PARALLEL_AGENT_BRAIN = "FORBIDDEN"
MAX_TRANSCRIPT = 64
WAITING = "…"

_GROK_MARK = (
    "qml",
    "desktop",
    "kaspa",
    "memory",
    "house",
    "workspace",
    "flow",
    "node",
)
_GPT_MARK = ("test_", "pytest", "codex", ".py")

_STATE: dict[str, Any] | None = None


def empty() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "engine": ENGINE,
        "ask": "",
        "graph": agent_flow.empty(),
        "grok": {
            "motor": "GROK_TUI",
            "title": "GROK TUI",
            "packet": "house · qml · memory · plan",
            "jobs": [],
        },
        "gpt": {
            "motor": "GPT_TUI",
            "title": "GPTUI",
            "packet": "tests · isolated files · build",
            "jobs": [],
        },
        "merge": {
            "status": "IDLE",
            "note": "Both motors meet here before anything is called done.",
            "ready": False,
        },
        "reflect": {
            "after": "reconverge",
            "body": "",
            "author": "CRITIC",
        },
        "transcript": [],
        "baselines": {"GROK TUI": "", "GPTUI": ""},
        "dispatched": {"grok": False, "gpt": False},
        "parallel_agent_brain": PARALLEL_AGENT_BRAIN,
        "action_authority": ACTION_AUTHORITY,
        "hint": "One stream. GROK TUI and GPTUI answer in the same chat. Gold is GROK. Green is GPTUI.",
    }


def _jobs_for(text: str, graph: dict[str, Any], motor: str) -> list[str]:
    packets = list(graph.get("packets") or [])
    by_kind = {
        str(row.get("kind") or ""): str(row.get("body") or "")
        for row in packets
        if isinstance(row, dict)
    }
    lower = text.lower()
    jobs: list[str] = []
    if motor == "GROK_TUI":
        jobs.append(by_kind.get("PLAN") or "plan the house path")
        if any(mark in lower for mark in _GROK_MARK):
            jobs.append("keep desktop, memory, and Kaspa on this motor")
        jobs.append("hold original intent")
    else:
        jobs.append(by_kind.get("BUILD") or "bounded build steps")
        if any(mark in lower for mark in _GPT_MARK):
            jobs.append("own tests and isolated python files")
        jobs.append("do not rewrite the house layer")
    out: list[str] = []
    for item in jobs:
        bit = " ".join(str(item).split())
        if bit and bit not in out:
            out.append(bit[:160])
        if len(out) >= 3:
            break
    return out


def _packet_text(title: str, ask: str, jobs: list[str]) -> str:
    lines = [
        "[FLOW TUI] " + title,
        "Shared ask: " + ask,
        "Your jobs:",
    ]
    for job in jobs:
        lines.append("- " + job)
    lines.append("Meet at merge when done. Critic is not the author.")
    return "\n".join(lines)


def _chrome_char(ch: str) -> bool:
    if ch.isspace():
        return False
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return False
    return name.startswith(
        ("BOX DRAWINGS", "BLOCK", "SHADE", "BRAILLE", "LIGHT SHADE", "FULL BLOCK")
    )


def clean_plain(text: str) -> str:
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        body = "".join(ch for ch in raw if not _chrome_char(ch))
        body = " ".join(body.split())
        if not body:
            continue
        if set(body) <= set(".:-_/\\|•·+=~*"):
            continue
        lines.append(body)
    return "\n".join(lines)


def delta_plain(before: str, after: str) -> str:
    after_text = str(after or "")
    before_text = str(before or "")
    if not after_text or after_text == before_text:
        return ""
    if before_text and after_text.startswith(before_text):
        return after_text[len(before_text) :].lstrip("\n")
    old_lines = before_text.splitlines()
    new_lines = after_text.splitlines()
    index = 0
    limit = min(len(old_lines), len(new_lines))
    while index < limit and old_lines[index] == new_lines[index]:
        index += 1
    return "\n".join(new_lines[index:]).strip()


def reply_from_dump(baseline: str, dump: str, ask: str) -> str:
    body = delta_plain(clean_plain(baseline), clean_plain(dump))
    needle = " ".join(str(ask or "").split())
    if not body:
        return ""
    lines = body.splitlines()
    if needle:
        last_ask = -1
        for index, line in enumerate(lines):
            if needle in line:
                last_ask = index
        if last_ask >= 0:
            lines = lines[last_ask + 1 :]
    out: list[str] = []
    for line in lines:
        bit = " ".join(line.split())
        if not bit or bit == needle:
            continue
        out.append(bit)
    return "\n".join(out).strip()


def is_chrome_reply(text: str) -> bool:
    compact = " ".join(str(text or "").split())
    if not compact:
        return True
    lower = compact.lower()
    if "enter:send" in lower or "alt+enter:newline" in lower:
        return True
    if "shift+tab:mode" in lower or "ctrl+x:" in lower:
        return True
    if "max fast" in lower and "goldgoblins" in lower:
        return True
    return False


def extract_assistant_jsonl(blob: str, *, role: str) -> str:
    """Take only new assistant text from a jsonl tail. Never a TUI screen dump."""
    parts: list[str] = []
    motor = str(role or "")
    for raw in str(blob or "").splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if motor == "GROK TUI":
            params = row.get("params")
            update = params.get("update") if isinstance(params, dict) else None
            if not isinstance(update, dict):
                continue
            if update.get("sessionUpdate") != "agent_message_chunk":
                continue
            content = update.get("content")
            text = content.get("text") if isinstance(content, dict) else None
            if text:
                parts.append(str(text))
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        if not isinstance(payload, dict):
            continue
        if payload.get("type") == "message" and payload.get("role") == "assistant":
            for item in payload.get("content") or []:
                if isinstance(item, dict) and item.get("type") in ("output_text", "text"):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
        elif payload.get("type") == "task_complete":
            text = payload.get("last_agent_message")
            if text:
                parts.append(str(text))
    body = "".join(parts) if motor == "GROK TUI" else "\n".join(parts)
    body = body.strip()
    if not body or is_chrome_reply(body):
        return ""
    return body[:2000]


def _motor_row(role: str, kind: str, text: str) -> dict[str, str]:
    return {
        "role": role,
        "kind": kind,
        "text": text[:2000],
    }


def _replace_motor(transcript: list[dict[str, Any]], role: str, kind: str, text: str) -> None:
    index = None
    for pos in range(len(transcript) - 1, -1, -1):
        row = transcript[pos]
        if not isinstance(row, dict):
            continue
        if str(row.get("role") or "") == "YOU":
            break
        if str(row.get("role") or "") == role:
            index = pos
            break
    body = str(text or "").strip()
    if index is None:
        if body:
            transcript.append(_motor_row(role, kind, body))
        return
    if body:
        transcript[index] = _motor_row(role, kind, body)
    elif kind == "REPLY" and str(transcript[index].get("text") or "") == WAITING:
        transcript[index] = _motor_row(role, "REPLY", "no reply yet")


def submit(text: str) -> dict[str, Any]:
    global _STATE
    ask = " ".join(str(text or "").split())
    if not ask:
        return snapshot()
    graph = agent_flow.run(ask)
    grok_jobs = _jobs_for(ask, graph, "GROK_TUI")
    gpt_jobs = _jobs_for(ask, graph, "GPT_TUI")
    reflect_row = next(
        (
            row
            for row in (graph.get("packets") or [])
            if isinstance(row, dict) and row.get("kind") == "REFLECT"
        ),
        {},
    )
    man = graph.get("front_man") or {}
    merge_ready = str(man.get("light") or "") == "GO"
    state = empty()
    prev = _STATE or empty()
    transcript = list(prev.get("transcript") or [])
    transcript.append({"role": "YOU", "kind": "REQUEST", "text": ask})
    transcript.append(_motor_row("GROK TUI", "STREAM", WAITING))
    transcript.append(_motor_row("GPTUI", "STREAM", WAITING))
    state.update(
        {
            "ask": ask[:240],
            "graph": graph,
            "grok": {
                "motor": "GROK_TUI",
                "title": "GROK TUI",
                "packet": _packet_text("GROK TUI", ask[:180], grok_jobs),
                "jobs": grok_jobs,
            },
            "gpt": {
                "motor": "GPT_TUI",
                "title": "GPTUI",
                "packet": _packet_text("GPTUI", ask[:180], gpt_jobs),
                "jobs": gpt_jobs,
            },
            "merge": {
                "status": "READY" if merge_ready else str(man.get("light") or "HOLD"),
                "note": "Reconverge: both packets present. Front Man "
                + str(man.get("light") or "HOLD")
                + ". "
                + ", ".join(str(item) for item in (man.get("reasons") or [])[:3]),
                "ready": merge_ready,
                "light": str(man.get("light") or "HOLD"),
            },
            "reflect": {
                "after": "reconverge",
                "body": str(reflect_row.get("body") or "What would make this split wrong?"),
                "author": "CRITIC",
            },
            "transcript": transcript[-MAX_TRANSCRIPT:],
            "baselines": {"GROK TUI": "", "GPTUI": ""},
            "dispatched": {"grok": True, "gpt": True},
            "front_man": man,
            "reviewer_is_author": False,
        }
    )
    _STATE = state
    return snapshot()


def arm(dumps: dict[str, str] | None = None) -> dict[str, Any]:
    global _STATE
    state = dict(_STATE) if _STATE is not None else empty()
    baselines = dict(state.get("baselines") or {})
    for role, dump in (dumps or {}).items():
        baselines[str(role)] = clean_plain(dump)
    state["baselines"] = baselines
    _STATE = state
    return snapshot()


def ingest_dump(role: str, dump: str) -> dict[str, Any]:
    global _STATE
    name = str(role or "").strip() or "GROK TUI"
    state = dict(_STATE) if _STATE is not None else empty()
    baselines = dict(state.get("baselines") or {})
    body = reply_from_dump(
        str(baselines.get(name) or ""),
        dump,
        str(state.get("ask") or ""),
    )
    if not body or is_chrome_reply(body):
        return snapshot()
    transcript = list(state.get("transcript") or [])
    _replace_motor(transcript, name, "STREAM", body)
    state["transcript"] = transcript[-MAX_TRANSCRIPT:]
    _STATE = state
    return snapshot()


def set_motor_stream(role: str, text: str, *, done: bool = False) -> dict[str, Any]:
    global _STATE
    state = dict(_STATE) if _STATE is not None else empty()
    transcript = list(state.get("transcript") or [])
    _replace_motor(
        transcript,
        str(role or "").strip() or "GROK TUI",
        "REPLY" if done else "STREAM",
        text,
    )
    state["transcript"] = transcript[-MAX_TRANSCRIPT:]
    _STATE = state
    return snapshot()


def snapshot() -> dict[str, Any]:
    return dict(_STATE) if _STATE is not None else empty()


def reset() -> dict[str, Any]:
    global _STATE
    _STATE = None
    agent_flow.reset()
    return empty()


def dispatch_texts() -> dict[str, str]:
    state = snapshot()
    ask = str(state.get("ask") or "").strip()
    if ask:
        return {"grok": ask, "gpt": ask}
    return {
        "grok": str((state.get("grok") or {}).get("packet") or ""),
        "gpt": str((state.get("gpt") or {}).get("packet") or ""),
    }
