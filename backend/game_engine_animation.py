"""Cheap deterministic locomotion poses for the GAME ENGINE preview.

This is deliberately a pose contract, not a skeleton runtime.  It gives the
shared low-poly figure a readable idle, walk, sprint and air response while
the project is still validating camera, movement and silhouette.  A future
authored/skinned asset can consume the same motion state and phase without
changing the simulation contract.
"""

from __future__ import annotations

import math
from typing import Any


SCHEMA = "gg.game-engine.animation.v1"
MOTION_STATES = ("IDLE", "WALK", "SPRINT", "AIR")
WALK_SPEED_MPS = 7.0
SPRINT_SPEED_MPS = 10.5
MAX_SPEED_MPS = 64.0


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clamp(value: Any, low: float, high: float, default: float = 0.0) -> float:
    return max(low, min(high, _finite(value, default)))


def motion_state(
    horizontal_speed: Any,
    *,
    grounded: Any = True,
    sprinting: Any = False,
) -> str:
    """Classify motion with stable thresholds shared by UI and future assets."""
    if not bool(grounded):
        return "AIR"
    speed = max(0.0, _clamp(horizontal_speed, 0.0, MAX_SPEED_MPS))
    if speed <= 0.08:
        return "IDLE"
    if bool(sprinting) or speed >= WALK_SPEED_MPS * 1.12:
        return "SPRINT"
    return "WALK"


def build_pose(
    *,
    sim_time: Any,
    horizontal_speed: Any,
    grounded: Any = True,
    sprinting: Any = False,
    vertical_velocity: Any = 0.0,
) -> dict[str, Any]:
    """Return one bounded, render-friendly pose driven only by fixed-step data.

    ``bob_m`` and the small rotations are root-level accents for the current
    combined body mesh.  ``phase`` is intentionally exposed so a later
    skinned importer can drive feet, arms and additive animation from the same
    deterministic clock.
    """
    safe_time = max(0.0, _finite(sim_time))
    safe_speed = max(0.0, _clamp(horizontal_speed, 0.0, MAX_SPEED_MPS))
    safe_vertical = _clamp(vertical_velocity, -64.0, 64.0)
    state = motion_state(
        safe_speed,
        grounded=grounded,
        sprinting=sprinting,
    )

    if state == "AIR":
        cadence_hz = 0.0
        phase = 0.0
        bob_m = 0.0
        # A modest pitch makes a jump readable, while the clamp prevents a
        # malformed velocity from turning the avatar upside down.
        lean_deg = _clamp(-safe_vertical * 0.32, -8.0, 8.0)
        sway_deg = 0.0
        stride = 0.0
        squash = 0.0
    elif state == "IDLE":
        cadence_hz = 1.25
        phase = math.fmod(safe_time * cadence_hz * math.tau, math.tau)
        bob_m = 0.012 * math.sin(phase)
        lean_deg = 0.0
        sway_deg = 0.65 * math.sin(phase * 0.5)
        stride = 0.0
        squash = 0.004 * math.sin(phase * 2.0)
    else:
        sprint = state == "SPRINT"
        speed_ratio = _clamp(
            safe_speed / (SPRINT_SPEED_MPS if sprint else WALK_SPEED_MPS),
            0.0,
            1.0,
        )
        cadence_hz = (1.65 if not sprint else 2.15) + 0.35 * speed_ratio
        phase = math.fmod(safe_time * cadence_hz * math.tau, math.tau)
        stride = math.sin(phase)
        # Keep the feet near the ground: the offset is positive and bounded,
        # unlike a full sine wave that would sink the mesh below the patch.
        bob_m = (0.010 if sprint else 0.006) + (
            0.026 if sprint else 0.018
        ) * abs(stride)
        lean_deg = -5.0 * speed_ratio if sprint else -2.5 * speed_ratio
        sway_deg = (2.2 if sprint else 1.6) * stride
        squash = (-0.014 if sprint else -0.008) * abs(stride)

    return {
        "schema": SCHEMA,
        "state": state,
        "phase": round(phase, 5),
        "cadence_hz": round(cadence_hz, 4),
        "speed_mps": round(safe_speed, 3),
        "bob_m": round(bob_m, 4),
        "lean_deg": round(lean_deg, 3),
        "sway_deg": round(sway_deg, 3),
        "stride": round(stride, 4),
        "squash": round(squash, 4),
        "source": "FIXED_STEP_ROOT_POSE",
    }
