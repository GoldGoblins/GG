"""Deterministic combat state for the GAME ENGINE.

Combat is an authoritative simulation layer.  It does not know anything
about QtQuick3D or the DOS renderer: actors have bounded health, cooldown and
engagement state, while the host supplies the progression-derived profile and
commits item/XP/event side effects.
"""

from __future__ import annotations

import copy
import math
from typing import Any


SCHEMA = "gg.game-engine.combat.v1"
VERSION = 1
MAX_ACTORS = 128
MAX_HEALTH = 1_000_000.0
MAX_DAMAGE = 100_000.0
MAX_ARMOR = 100_000.0
MAX_COOLDOWN_S = 30.0
PLAYER_RESPAWN_S = 8.0
NPC_RESPAWN_S = 20.0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _clamp(value: Any, low: float, high: float, default: float = 0.0) -> float:
    return max(low, min(high, _safe_float(value, default)))


def _text(value: Any, default: str = "", limit: int = 64) -> str:
    return str(value or default).strip()[:limit]


def profile(
    state: Any,
    *,
    kind: str = "NPC",
    actor_id: str = "",
    role: str = "",
) -> dict[str, Any]:
    """Derive one bounded combat profile from a progression state.

    NPC progression already contains gear-aware derived stats.  The player
    progression uses the same base-stat contract; when the host supplies a
    temporary ``gear_stats`` map, those real equipped item stats are included
    without mutating the progression document.
    """
    source = state if isinstance(state, dict) else {}
    base = source.get("base_stats", {}) if isinstance(source.get("base_stats"), dict) else {}
    derived = source.get("derived_stats", {}) if isinstance(source.get("derived_stats"), dict) else {}
    gear = source.get("gear_stats", {}) if isinstance(source.get("gear_stats"), dict) else {}
    level = max(1, min(60, _safe_int(source.get("level"), 1)))
    ascension = max(0, _safe_int(source.get("ascension"), 0))
    paragon = max(0, _safe_int(source.get("paragon"), 0))
    might = _safe_float(base.get("might"), 5.0)
    finesse = _safe_float(base.get("finesse"), 5.0)
    spirit = _safe_float(base.get("spirit"), 5.0)
    grit = _safe_float(base.get("grit"), 5.0)
    gear_value = lambda key: _safe_float(gear.get(key), 0.0)
    has_derived = any(key in derived for key in ("health", "damage", "armor"))
    max_health = _safe_float(derived.get("health"), 50.0 + grit * 12.0)
    damage = _safe_float(derived.get("damage"), might * 2.0 + finesse)
    armor = _safe_float(derived.get("armor"), grit)
    if not has_derived:
        max_health += gear_value("health") + gear_value("stamina") * 2.0
        damage += gear_value("damage") + gear_value("spell_power") * 0.35
        armor += gear_value("armor")
    crit = 0.04 + finesse * 0.004 + gear_value("crit") * 0.01
    crit += ascension * 0.006 + paragon * 0.0005
    attack_speed = 0.95 - min(0.35, finesse * 0.012)
    attack_speed -= min(0.18, gear_value("attack_speed") * 0.01)
    return {
        "id": _text(actor_id, "actor", 64),
        "kind": _text(kind, "NPC", 16).upper(),
        "role": _text(role, "", 32).upper(),
        "level": level,
        "ascension": ascension,
        "power_score": round(max(0.0, _safe_float(source.get("power_score"))), 3),
        "max_health": round(_clamp(max_health, 1.0, MAX_HEALTH, 100.0), 3),
        "damage": round(_clamp(damage, 1.0, MAX_DAMAGE, 10.0), 3),
        "armor": round(_clamp(armor, 0.0, MAX_ARMOR), 3),
        "crit_chance": round(_clamp(crit, 0.0, 0.75), 4),
        "attack_cooldown_s": round(_clamp(attack_speed, 0.2, MAX_COOLDOWN_S, 0.95), 3),
        "attack_range_m": round(
            _clamp(2.4 + finesse * 0.025 + gear_value("attack_range"), 1.25, 8.0, 2.5),
            3,
        ),
    }


def new_state() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "actors": {},
        "last_event": {},
        "revision": 0,
    }


def _normalize_actor(raw: Any, actor_id: str) -> dict[str, Any]:
    row = raw if isinstance(raw, dict) else {}
    maximum = _clamp(row.get("max_health"), 1.0, MAX_HEALTH, 100.0)
    health = _clamp(row.get("health"), 0.0, maximum, maximum)
    return {
        "id": _text(row.get("id"), actor_id, 64),
        "kind": _text(row.get("kind"), "NPC", 16).upper(),
        "alive": bool(row.get("alive", health > 0.0)),
        "health": round(health, 3),
        "max_health": round(maximum, 3),
        "cooldown_until": round(max(0.0, _safe_float(row.get("cooldown_until"))), 3),
        "engaged_target": _text(row.get("engaged_target"), limit=64),
        "respawn_at": round(max(0.0, _safe_float(row.get("respawn_at"))), 3),
        "defeated_count": max(0, min(1_000_000, _safe_int(row.get("defeated_count")))),
        "last_damage": round(_clamp(row.get("last_damage"), 0.0, MAX_DAMAGE), 3),
        "last_hit_by": _text(row.get("last_hit_by"), limit=64),
    }


def normalize_state(raw: Any) -> dict[str, Any]:
    base = new_state()
    source = raw if isinstance(raw, dict) else {}
    actors = source.get("actors", {})
    if isinstance(actors, dict):
        for actor_id, value in list(actors.items())[:MAX_ACTORS]:
            wanted = _text(actor_id, limit=64)
            if wanted:
                base["actors"][wanted] = _normalize_actor(value, wanted)
    last_event = source.get("last_event")
    if isinstance(last_event, dict):
        base["last_event"] = {
            key: copy.deepcopy(last_event[key])
            for key in (
                "kind",
                "attacker_id",
                "defender_id",
                "action_id",
                "damage",
                "critical",
                "defeated",
                "time_s",
            )
            if key in last_event
        }
    base["revision"] = max(0, _safe_int(source.get("revision")))
    return base


def ensure_actor(
    state: dict[str, Any],
    actor_id: Any,
    profile_row: dict[str, Any],
) -> dict[str, Any]:
    actors = state.setdefault("actors", {})
    wanted = _text(actor_id, "actor", 64)
    profile_max = _clamp(profile_row.get("max_health"), 1.0, MAX_HEALTH, 100.0)
    current = actors.get(wanted)
    if not isinstance(current, dict):
        current = _normalize_actor(
            {
                "id": wanted,
                "kind": profile_row.get("kind", "NPC"),
                "max_health": profile_max,
                "health": profile_max,
                "alive": True,
            },
            wanted,
        )
        actors[wanted] = current
        return current
    old_max = _clamp(current.get("max_health"), 1.0, MAX_HEALTH, profile_max)
    old_health = _clamp(current.get("health"), 0.0, old_max, old_max)
    if bool(current.get("alive", True)):
        ratio = old_health / old_max if old_max > 0.0 else 1.0
        current["health"] = round(_clamp(profile_max * ratio, 0.0, profile_max), 3)
    current["max_health"] = round(profile_max, 3)
    current["kind"] = _text(profile_row.get("kind"), current.get("kind", "NPC"), 16).upper()
    current["id"] = wanted
    return current


def respawn_actor(
    state: dict[str, Any],
    actor_id: Any,
    profile_row: dict[str, Any],
    sim_time: Any,
) -> dict[str, Any] | None:
    actor = ensure_actor(state, actor_id, profile_row)
    now = max(0.0, _safe_float(sim_time))
    if actor.get("alive") or now < _safe_float(actor.get("respawn_at")):
        return None
    actor["alive"] = True
    actor["health"] = actor["max_health"]
    actor["respawn_at"] = 0.0
    actor["cooldown_until"] = 0.0
    actor["engaged_target"] = ""
    actor["last_damage"] = 0.0
    state["revision"] = max(0, _safe_int(state.get("revision"))) + 1
    return copy.deepcopy(actor)


def resolve_attack(
    state: dict[str, Any],
    *,
    attacker_id: Any,
    defender_id: Any,
    attacker_profile: dict[str, Any],
    defender_profile: dict[str, Any],
    sim_time: Any,
    seed: Any = 1,
    action_id: Any = "basic_attack",
) -> dict[str, Any]:
    """Resolve one deterministic attack and mutate only combat state."""
    attacker_key = _text(attacker_id, limit=64)
    defender_key = _text(defender_id, limit=64)
    now = max(0.0, _safe_float(sim_time))
    attacker = ensure_actor(state, attacker_key, attacker_profile)
    defender = ensure_actor(state, defender_key, defender_profile)
    common = {
        "schema": SCHEMA,
        "version": VERSION,
        "attacker_id": attacker_key,
        "defender_id": defender_key,
        "action_id": _text(action_id, "basic_attack", 48),
        "time_s": round(now, 3),
    }
    if not attacker.get("alive"):
        return {**common, "ok": False, "status": "ATTACKER_DEFEATED", "damage": 0.0}
    if not defender.get("alive"):
        return {**common, "ok": False, "status": "TARGET_DEFEATED", "damage": 0.0}
    cooldown_until = _safe_float(attacker.get("cooldown_until"))
    if now + 0.0001 < cooldown_until:
        return {
            **common,
            "ok": False,
            "status": "COOLDOWN",
            "damage": 0.0,
            "cooldown_remaining_s": round(cooldown_until - now, 3),
        }
    raw_seed = _safe_int(seed, 1) & 0xFFFFFFFF
    roll = ((raw_seed * 1664525 + 1013904223) & 0xFFFFFFFF) / 4294967296.0
    critical = roll < _clamp(attacker_profile.get("crit_chance"), 0.0, 0.75)
    base_damage = _clamp(attacker_profile.get("damage"), 1.0, MAX_DAMAGE, 1.0)
    armor = _clamp(defender_profile.get("armor"), 0.0, MAX_ARMOR)
    damage = max(1.0, base_damage * (1.5 if critical else 1.0) - armor * 0.35)
    damage = round(_clamp(damage, 1.0, MAX_DAMAGE, 1.0), 3)
    attacker["cooldown_until"] = round(
        now + _clamp(attacker_profile.get("attack_cooldown_s"), 0.2, MAX_COOLDOWN_S, 0.95),
        3,
    )
    defender["health"] = round(max(0.0, _safe_float(defender.get("health")) - damage), 3)
    defender["last_damage"] = damage
    defender["last_hit_by"] = attacker_key
    defeated = defender["health"] <= 0.0
    if defeated:
        defender["alive"] = False
        defender["defeated_count"] = max(0, _safe_int(defender.get("defeated_count"))) + 1
        defender["engaged_target"] = ""
        defender["respawn_at"] = round(
            now + (PLAYER_RESPAWN_S if defender_key == "player" else NPC_RESPAWN_S),
            3,
        )
    else:
        defender["engaged_target"] = attacker_key
    attacker["engaged_target"] = defender_key
    result = {
        **common,
        "ok": True,
        "status": "DEFEATED" if defeated else "HIT",
        "damage": damage,
        "critical": bool(critical),
        "defeated": bool(defeated),
        "defender_health": defender["health"],
        "defender_max_health": defender["max_health"],
        "cooldown_s": round(attacker["cooldown_until"] - now, 3),
    }
    state["last_event"] = copy.deepcopy(result)
    state["revision"] = max(0, _safe_int(state.get("revision"))) + 1
    return result


def view(state: Any) -> dict[str, Any]:
    source = normalize_state(state)
    actors = source.get("actors", {})
    rows: list[dict[str, Any]] = []
    if isinstance(actors, dict):
        for actor_id in sorted(actors)[:MAX_ACTORS]:
            row = actors.get(actor_id)
            if isinstance(row, dict):
                rows.append(copy.deepcopy(row))
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "actors": rows,
        "active": sum(1 for row in rows if row.get("alive")),
        "defeated": sum(1 for row in rows if not row.get("alive")),
        "last_event": copy.deepcopy(source.get("last_event", {})),
        "revision": max(0, _safe_int(source.get("revision"))),
        "policy": "FIXED_STEP_DETERMINISTIC_DAMAGE_WITH_REAL_ACTOR_STATE",
    }
