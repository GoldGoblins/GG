"""FLOW TUI — joint board for GROK TUI and GPTUI in one house.

Additive layer. The Universal Operational Stream, GROK TUI PTY, and GPTUI
PTY stay as they are. This board splits one user ask into two motor packets,
merges them, then reflects. It does not spawn extra brains.
"""

from __future__ import annotations

from typing import Any

from backend import agent_flow


SCHEMA = "gg.flow-tui.v1"
ENGINE = "FLOW_TUI"
ACTION_AUTHORITY = "NONE"
PARALLEL_AGENT_BRAIN = "FORBIDDEN"
MAX_TRANSCRIPT = 24

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
        "dispatched": {"grok": False, "gpt": False},
        "parallel_agent_brain": PARALLEL_AGENT_BRAIN,
        "action_authority": ACTION_AUTHORITY,
        "hint": "Shared input for both motors. GROK TUI and GPTUI tabs stay independent.",
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
    transcript.append({"role": "YOU", "text": ask})
    transcript.append(
        {
            "role": "FLOW",
            "text": "split · GROK "
            + str(len(grok_jobs))
            + " · GPTUI "
            + str(len(gpt_jobs)),
        }
    )
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
            "front_man": man,
            "reviewer_is_author": False,
        }
    )
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
    return {
        "grok": str((state.get("grok") or {}).get("packet") or ""),
        "gpt": str((state.get("gpt") or {}).get("packet") or ""),
    }
