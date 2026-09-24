"""Bounded, deterministic ambient-life data for the GAME ENGINE.

The first living-world layer is intentionally smaller than a full AI
simulation. It gives render-only population proxies authored roles, day-cycle
schedules and a tiny stimulus contract. A later scheduler can promote
selected proxies into the existing physics/NPC pools without changing the row
shape consumed by QML.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Callable, Iterable

from backend import game_engine_animation as animation_contract


SCHEMA = "gg.game-engine.life.v1"
VERSION = 1
DAY_LENGTH_S = 120.0
MAX_PROXIES = 8
PLAYER_SENSE_RADIUS_M = 5.5
PHASES = ("DAWN", "DAY", "DUSK", "NIGHT")
ACTIVITIES = (
    "FISHING",
    "TRAVELING",
    "SCOUTING",
    "HAULING",
    "RESTING",
    "NOTICE_PLAYER",
)


DEFAULT_SPAWNS: tuple[dict[str, Any], ...] = (
    {
        "id": "ambient-fisher-01",
        "role": "FISHER",
        "route": "SHORE_ORBIT",
        "activity_day": "FISHING",
        "x": -4.4,
        "z": -4.6,
        "radius": 1.8,
        "speed": 0.52,
        "phase": 0.4,
        "sense_radius": PLAYER_SENSE_RADIUS_M,
        "color": "#d7a36f",
        "scale": (0.82, 0.98, 0.82),
    },
    {
        "id": "ambient-traveler-01",
        "role": "TRAVELER",
        "route": "ROAD_LOOP",
        "activity_day": "TRAVELING",
        "x": 5.1,
        "z": -3.7,
        "radius": 2.2,
        "speed": 0.43,
        "phase": 1.8,
        "sense_radius": PLAYER_SENSE_RADIUS_M,
        "color": "#b6a6c8",
        "scale": (0.76, 0.92, 0.76),
    },
    {
        "id": "ambient-scout-01",
        "role": "SCOUT",
        "route": "RIDGE_SWEEP",
        "activity_day": "SCOUTING",
        "x": -6.1,
        "z": 5.0,
        "radius": 2.0,
        "speed": 0.61,
        "phase": 3.0,
        "sense_radius": PLAYER_SENSE_RADIUS_M,
        "color": "#7fa9c4",
        "scale": (0.88, 1.08, 0.88),
    },
    {
        "id": "ambient-carrier-01",
        "role": "CARRIER",
        "route": "CRATE_RUN",
        "activity_day": "HAULING",
        "x": 6.8,
        "z": 5.5,
        "radius": 1.5,
        "speed": 0.36,
        "phase": 4.6,
        "sense_radius": PLAYER_SENSE_RADIUS_M,
        "color": "#8db89a",
        "scale": (0.92, 1.02, 0.92),
    },
)


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clamp(value: Any, low: float, high: float, default: float = 0.0) -> float:
    return max(low, min(high, _finite(value, default)))


def starter_spawns() -> list[dict[str, Any]]:
    """Return isolated authored spawn data for the starter island."""
    return copy.deepcopy(list(DEFAULT_SPAWNS))


def spawns_from_content(content: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Accept bounded ambient authoring while preserving safe defaults."""
    source = content.get("ambient_life") if isinstance(content, dict) else None
    raw_rows = source if isinstance(source, list) else starter_spawns()
    defaults = {str(row["id"]): row for row in DEFAULT_SPAWNS}
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_rows[:MAX_PROXIES]:
        if not isinstance(raw, dict):
            continue
        identity = str(raw.get("id", "")).strip()[:64]
        if not identity or identity in seen:
            continue
        base = copy.deepcopy(defaults.get(identity, {}))
        base.update(copy.deepcopy(raw))
        base["id"] = identity
        base["role"] = str(base.get("role", "WANDERER")).upper()[:32]
        base["route"] = str(base.get("route", "ROAD_LOOP")).upper()[:32]
        base["activity_day"] = str(
            base.get("activity_day", "TRAVELING")
        ).upper()[:32]
        base["x"] = _clamp(base.get("x"), -128.0, 128.0)
        base["z"] = _clamp(base.get("z"), -128.0, 128.0)
        base["radius"] = _clamp(base.get("radius"), 0.5, 32.0, 1.5)
        base["speed"] = _clamp(base.get("speed"), 0.05, 4.0, 0.4)
        base["phase"] = _finite(base.get("phase"))
        base["sense_radius"] = _clamp(
            base.get("sense_radius"), 1.0, 16.0, PLAYER_SENSE_RADIUS_M
        )
        base["color"] = str(base.get("color", "#8db89a"))[:16]
        scale = base.get("scale", (0.8, 1.0, 0.8))
        if not isinstance(scale, (list, tuple)) or len(scale) < 3:
            scale = (0.8, 1.0, 0.8)
        base["scale"] = tuple(
            _clamp(component, 0.35, 1.8, 0.8) for component in scale[:3]
        )
        result.append(base)
        seen.add(identity)
    return result


def world_clock(sim_time: Any) -> dict[str, Any]:
    """Map fixed-step seconds to a compact deterministic world clock."""
    safe_time = max(0.0, _finite(sim_time))
    day_index = int(safe_time // DAY_LENGTH_S) + 1
    cycle_s = safe_time % DAY_LENGTH_S
    cycle = cycle_s / DAY_LENGTH_S
    if cycle < 0.15:
        phase = "DAWN"
    elif cycle < 0.68:
        phase = "DAY"
    elif cycle < 0.83:
        phase = "DUSK"
    else:
        phase = "NIGHT"
    hour = cycle * 24.0
    minute = int((hour - int(hour)) * 60.0)
    return {
        "day": day_index,
        "time_s": round(safe_time, 3),
        "cycle_s": round(cycle_s, 3),
        "hour": round(hour, 3),
        "label": f"{int(hour):02d}:{minute:02d}",
        "phase": phase,
        "day_length_s": DAY_LENGTH_S,
    }


def _route_position(
    spawn: dict[str, Any],
    sim_time: float,
    *,
    active: bool,
) -> tuple[float, float, float, float]:
    """Return x/z and velocity for one small authored route."""
    home_x = _finite(spawn.get("x"))
    home_z = _finite(spawn.get("z"))
    if not active:
        return home_x, home_z, 0.0, 0.0
    radius = _clamp(spawn.get("radius"), 0.5, 32.0, 1.5)
    speed = _clamp(spawn.get("speed"), 0.05, 4.0, 0.4)
    phase = _finite(spawn.get("phase"))
    angle = sim_time * speed + phase
    route = str(spawn.get("route", "ROAD_LOOP")).upper()
    if route == "SHORE_ORBIT":
        x = home_x + math.sin(angle) * radius
        z = home_z + math.cos(angle * 0.81) * radius * 0.72
        vx = math.cos(angle) * radius * speed
        vz = -math.sin(angle * 0.81) * radius * speed * 0.81 * 0.72
    elif route == "RIDGE_SWEEP":
        x = home_x + math.sin(angle) * radius * 1.15
        z = home_z + math.sin(angle * 0.52) * radius * 0.68
        vx = math.cos(angle) * radius * 1.15 * speed
        vz = math.cos(angle * 0.52) * radius * 0.68 * speed * 0.52
    elif route == "CRATE_RUN":
        x = home_x + math.sin(angle) * radius
        z = home_z + math.sin(angle * 0.5) * radius * 0.42
        vx = math.cos(angle) * radius * speed
        vz = math.cos(angle * 0.5) * radius * 0.42 * speed * 0.5
    else:
        x = home_x + math.sin(angle) * radius
        z = home_z + math.cos(angle * 0.83) * radius * 0.82
        vx = math.cos(angle) * radius * speed
        vz = -math.sin(angle * 0.83) * radius * speed * 0.83 * 0.82
    return x, z, vx, vz


def _height_at(
    terrain_height: Callable[[float, float], Any] | None,
    x: float,
    z: float,
) -> float:
    if terrain_height is None:
        return 0.0
    try:
        return _finite(terrain_height(x, z))
    except (TypeError, ValueError):
        return 0.0


def proxy_rows(
    spawns: Iterable[dict[str, Any]],
    sim_time: Any,
    *,
    player_x: Any = 0.0,
    player_z: Any = 0.0,
    terrain_height: Callable[[float, float], Any] | None = None,
) -> list[dict[str, Any]]:
    """Build stable render rows and apply one bounded player stimulus pass."""
    safe_time = max(0.0, _finite(sim_time))
    clock = world_clock(safe_time)
    px = _finite(player_x)
    pz = _finite(player_z)
    rows: list[dict[str, Any]] = []
    for raw_spawn in list(spawns)[:MAX_PROXIES]:
        if not isinstance(raw_spawn, dict):
            continue
        spawn = raw_spawn
        role = str(spawn.get("role", "WANDERER"))[:32]
        day_activity = str(spawn.get("activity_day", "TRAVELING")).upper()
        active = clock["phase"] != "NIGHT"
        x, z, velocity_x, velocity_z = _route_position(
            spawn,
            safe_time,
            active=active,
        )
        distance = math.hypot(x - px, z - pz)
        sense_radius = _clamp(
            spawn.get("sense_radius"), 1.0, 16.0, PLAYER_SENSE_RADIUS_M
        )
        notices_player = distance <= sense_radius
        if notices_player:
            activity = "NOTICE_PLAYER"
            yaw = math.atan2(-(px - x), -(pz - z)) if distance > 0.0001 else 0.0
            velocity_x = 0.0
            velocity_z = 0.0
        elif active:
            activity = day_activity if day_activity in ACTIVITIES else "TRAVELING"
            yaw = math.atan2(-velocity_x, -velocity_z) if math.hypot(velocity_x, velocity_z) > 0.001 else 0.0
        else:
            activity = "RESTING"
            yaw = 0.0
        horizontal_speed = math.hypot(velocity_x, velocity_z)
        pose = animation_contract.build_pose(
            sim_time=safe_time + _finite(spawn.get("phase")),
            horizontal_speed=horizontal_speed,
            grounded=True,
            sprinting=False,
            vertical_velocity=0.0,
        )
        scale = spawn.get("scale", (0.8, 1.0, 0.8))
        if not isinstance(scale, (list, tuple)) or len(scale) < 3:
            scale = (0.8, 1.0, 0.8)
        rows.append(
            {
                "id": str(spawn.get("id", "ambient-life")),
                "kind": "ACTOR",
                "x": round(x, 3),
                "y": round(_height_at(terrain_height, x, z) + 0.65, 3),
                "z": round(z, 3),
                "yaw": round(yaw, 4),
                "sx": round(_clamp(scale[0], 0.35, 1.8, 0.8), 3),
                "sy": round(_clamp(scale[1], 0.35, 1.8, 1.0), 3),
                "sz": round(_clamp(scale[2], 0.35, 1.8, 0.8), 3),
                "color": str(spawn.get("color", "#8db89a")),
                "speed": round(horizontal_speed, 3),
                "motion_state": str(pose.get("state", "IDLE")),
                "animation": pose,
                "asset": None,
                "equipment": [],
                "item": None,
                "life": {
                    "role": role,
                    "activity": activity,
                    "stimulus": "PLAYER_NEAR" if notices_player else "NONE",
                    "attention": notices_player,
                    "schedule_phase": clock["phase"],
                    "home_x": round(_finite(spawn.get("x")), 3),
                    "home_z": round(_finite(spawn.get("z")), 3),
                    "distance_to_player_m": round(distance, 3),
                },
            }
        )
    return rows


def build_view(rows: Iterable[dict[str, Any]], sim_time: Any) -> dict[str, Any]:
    """Return compact inspector/network data for the ambient population."""
    safe_rows = [row for row in rows if isinstance(row, dict)][:MAX_PROXIES]
    activities: dict[str, int] = {}
    stimuli: dict[str, int] = {}
    proxies: list[dict[str, Any]] = []
    for row in safe_rows:
        life = row.get("life", {}) if isinstance(row.get("life"), dict) else {}
        activity = str(life.get("activity", "TRAVELING"))
        stimulus = str(life.get("stimulus", "NONE"))
        activities[activity] = activities.get(activity, 0) + 1
        stimuli[stimulus] = stimuli.get(stimulus, 0) + 1
        proxies.append(
            {
                "id": str(row.get("id", "ambient-life")),
                "role": str(life.get("role", "WANDERER")),
                "activity": activity,
                "stimulus": stimulus,
                "attention": bool(life.get("attention", False)),
                "motion_state": str(row.get("motion_state", "IDLE")),
                "x": row.get("x", 0.0),
                "z": row.get("z", 0.0),
                "individual": copy.deepcopy(row.get("individual", {})),
            }
        )
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "clock": world_clock(sim_time),
        "population": len(safe_rows),
        "budget": MAX_PROXIES,
        "visible": len(safe_rows),
        "simulation": "RENDER_ONLY_DETERMINISTIC_SCHEDULES",
        "activities": dict(sorted(activities.items())),
        "stimuli": dict(sorted(stimuli.items())),
        "proxies": proxies,
    }
