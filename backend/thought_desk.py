"""Same-task specialist panel for the existing thought stream.

This is not a second agent brain.  PARALLEL_AGENT_BRAIN stays FORBIDDEN.
The useful idea from the public swarm writeups is: several small seats look
at one task at the same time, they do not wait for each other, and a Front
Man in code merges them.  Extra loops spend more compute on the same seats
when they disagree — Astra-style depth, not more parameters.

The panel compiles into the OmniGPT/chat prompt so the motor hammers one
task from every live seat in the same turn instead of walking A then B.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import re
from typing import Any

from backend.chat_context_compiler import work_intent


SCHEMA = "gg.thought-desk.v1"
MAX_SEATS = 6
MAX_LOOPS = 3
MAX_WORKERS = 6
PARALLEL_AGENT_BRAIN = "FORBIDDEN"
FLAT_MODEL_COMMAND_LOOP = "FORBIDDEN"

_RED_RE = re.compile(
    r"\b(wp-admin|one\.com|password|lösenord|sudo|credential|secret|2fa)\b",
    re.IGNORECASE,
)
_YELLOW_RE = re.compile(
    r"\b(live|sftp|deploy|nätverk|network|skriv|write|push|production|"
    r"produktion|mainnet)\b",
    re.IGNORECASE,
)
_LINEAR_RE = re.compile(
    r"\b(först|sedan|sen|därefter|efter det|steg för steg|"
    r"one by one|then|after that|step by step)\b",
    re.IGNORECASE,
)
_SPLIT_RE = re.compile(r"\s+(?:och|and|,|;)\s+", re.IGNORECASE)
_FILE_RE = re.compile(
    r"\b[\w./-]+\.(?:py|qml|js|json|php|md|txt)\b",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _risk(text: str) -> dict[str, Any]:
    red = sorted({item.group(0).lower() for item in _RED_RE.finditer(text)})
    yellow = sorted({item.group(0).lower() for item in _YELLOW_RE.finditer(text)})
    if red:
        light = "RED"
    elif yellow:
        light = "YELLOW"
    else:
        light = "GREEN"
    return {
        "id": "RISK",
        "light": light,
        "red": red,
        "yellow": yellow,
        "note": "Approval stays ja/nej in this chat. Profile text never grants authority.",
    }


def _intent(text: str) -> dict[str, Any]:
    compact = " ".join(text.split())
    if len(compact) > 180:
        compact = compact[:177] + "…"
    return {
        "id": "INTENT",
        "ask": compact or "(empty)",
        "preserve": True,
        "work": work_intent(text),
    }


def _evidence(text: str) -> dict[str, Any]:
    from backend.omni_gpt_profiles import select_profiles

    slugs = [record.spec.slug for record in select_profiles(text)]
    files = _FILE_RE.findall(text)[:6]
    return {
        "id": "EVIDENCE",
        "profiles": slugs,
        "named_files": files,
        "work": work_intent(text),
    }


def _memory(text: str) -> dict[str, Any]:
    try:
        from backend.long_memory import density, recall

        hits = recall(text, limit=3)
        fill = density()
    except Exception:
        hits = []
        fill = 0.0
    statements = [
        str(item.get("statement") or "")
        for item in hits
        if str(item.get("statement") or "").strip()
    ][:3]
    return {
        "id": "MEMORY",
        "hits": statements,
        "count": len(statements),
        "density": fill,
        "retrieval": "LASER_IDENTITY",
    }


def _critic(text: str, builder: dict[str, Any] | None = None) -> dict[str, Any]:
    flags: list[str] = []
    if _LINEAR_RE.search(text):
        flags.append("LINEAR_TRAP")
    if work_intent(text) and not _FILE_RE.search(text):
        flags.append("MISSING_TARGET")
    moves = list((builder or {}).get("moves") or [])
    if len(moves) > 1 and _LINEAR_RE.search(text):
        flags.append("SERIALIZED_PARALLEL_WORK")
    return {
        "id": "CRITIC",
        "flags": flags,
        "falsify": "What evidence would make the current plan wrong?",
    }


def _builder(text: str) -> dict[str, Any]:
    if not work_intent(text):
        return {"id": "BUILDER", "moves": [], "mode": "TALK"}
    parts = [item.strip(" .") for item in _SPLIT_RE.split(text) if item.strip()]
    moves: list[str] = []
    for part in parts:
        if work_intent(part) or _FILE_RE.search(part):
            snippet = " ".join(part.split())
            if len(snippet) > 80:
                snippet = snippet[:77] + "…"
            moves.append(snippet)
        if len(moves) >= 3:
            break
    if not moves:
        moves = ["same-task next bounded step"]
    return {
        "id": "BUILDER",
        "moves": moves,
        "mode": "PARALLEL" if len(moves) > 1 else "ONE",
    }


def _front_man(
    intent: dict[str, Any],
    risk: dict[str, Any],
    evidence: dict[str, Any],
    critic: dict[str, Any],
    builder: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    light = "GO"
    if str(risk.get("light") or "") == "RED":
        light = "HOLD"
        reasons.append("RED_EFFECT")
    flags = list(critic.get("flags") or [])
    if "LINEAR_TRAP" in flags or "SERIALIZED_PARALLEL_WORK" in flags:
        light = "SPLIT"
        reasons.append("HAMMER_SAME_TASK_IN_PARALLEL")
    if str(builder.get("mode") or "") != "TALK" and "MISSING_TARGET" in flags:
        if light == "GO":
            light = "HOLD"
        reasons.append("NEED_TARGET")
    if str(intent.get("work") or False) is False and light == "GO":
        reasons.append("CONVERSE")
    conflict = light in {"HOLD", "SPLIT"} and str(builder.get("mode") or "") != "TALK"
    return {
        "id": "FRONT_MAN",
        "light": light,
        "reasons": reasons or ["SAME_TASK"],
        "conflict": conflict,
        "in_code": True,
        "parallel_agent_brain": PARALLEL_AGENT_BRAIN,
        "kill_switch": "CODE",
    }


def _compile_seats(text: str, builder_hint: dict[str, Any] | None = None) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="gg-thought") as pool:
        intent_f = pool.submit(_intent, text)
        risk_f = pool.submit(_risk, text)
        evidence_f = pool.submit(_evidence, text)
        memory_f = pool.submit(_memory, text)
        builder_f = pool.submit(_builder, text)
        intent = intent_f.result()
        risk = risk_f.result()
        evidence = evidence_f.result()
        memory = memory_f.result()
        builder = builder_hint or builder_f.result()
        critic = _critic(text, builder)
    return {
        "intent": intent,
        "risk": risk,
        "evidence": evidence,
        "memory": memory,
        "critic": critic,
        "builder": builder,
    }


def sit(text: str, *, compact: bool = False) -> dict[str, Any]:
    raw = _text(text)
    seats = _compile_seats(raw)
    loops = 1
    man = _front_man(
        seats["intent"],
        seats["risk"],
        seats["evidence"],
        seats["critic"],
        seats["builder"],
    )
    graveyard: list[str] = []
    while man.get("conflict") and loops < MAX_LOOPS:
        if "LINEAR_TRAP" in (seats["critic"].get("flags") or []):
            graveyard.append("sequential A-then-B plan")
            seats["builder"] = {
                **seats["builder"],
                "mode": "PARALLEL",
                "moves": seats["builder"].get("moves") or ["same-task parallel pass"],
            }
        seats["critic"] = _critic(raw, seats["builder"])
        loops += 1
        man = _front_man(
            seats["intent"],
            seats["risk"],
            seats["evidence"],
            seats["critic"],
            seats["builder"],
        )
    board = {
        "schema": SCHEMA,
        "mode": "SAME_TASK_PANEL",
        "parallel_agent_brain": PARALLEL_AGENT_BRAIN,
        "flat_model_command_loop": FLAT_MODEL_COMMAND_LOOP,
        "model_agents": False,
        "cross_talk_during_inference": False,
        "loops": loops,
        "max_loops": MAX_LOOPS,
        "compact": compact,
        "seats": seats,
        "front_man": man,
        "graveyard": graveyard,
    }
    board["text"] = render(board, compact=compact)
    return board


def render(board: dict[str, Any], *, compact: bool = False) -> str:
    seats = board.get("seats") or {}
    man = board.get("front_man") or {}
    intent = seats.get("intent") or {}
    risk = seats.get("risk") or {}
    evidence = seats.get("evidence") or {}
    memory = seats.get("memory") or {}
    critic = seats.get("critic") or {}
    builder = seats.get("builder") or {}
    moves = " | ".join(str(item) for item in (builder.get("moves") or [])[:3])
    flags = ",".join(str(item) for item in (critic.get("flags") or [])[:4]) or "none"
    profiles = ",".join(str(item) for item in (evidence.get("profiles") or [])[:4])
    reasons = ",".join(str(item) for item in (man.get("reasons") or [])[:4])
    lines = [
        "[SAME_TASK_DESK]",
        "schema=" + SCHEMA,
        "mode=SAME_TASK_PANEL",
        "parallel_agent_brain=" + PARALLEL_AGENT_BRAIN,
        "loops=" + str(board.get("loops") or 1) + "/" + str(MAX_LOOPS),
        "light=" + str(man.get("light") or "HOLD"),
        "INTENT " + str(intent.get("ask") or ""),
        "RISK " + str(risk.get("light") or "GREEN"),
        "MEMORY hits="
        + str(memory.get("count") or 0)
        + " density="
        + str(memory.get("density") or 0),
        "EVIDENCE profiles=" + profiles,
        "CRITIC " + flags,
        "BUILDER " + str(builder.get("mode") or "TALK") + ((" · " + moves) if moves else ""),
        "FRONT_MAN " + str(man.get("light") or "HOLD") + " · " + reasons,
        "Rule: all live seats attack this same task now. Do not serialize. "
        "No extra agent brain. Front Man merges. Extra loops spend compute, not new weights.",
        "[/SAME_TASK_DESK]",
    ]
    text = "\n".join(lines)
    if compact and len(text) > 720:
        return text[:696].rstrip() + "\n[/SAME_TASK_DESK]"
    return text
