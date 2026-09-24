"""Deterministic, low-cost third-person movement primitives.

The controller keeps the useful feel of a WoW/Jak-style avatar separate from
the host's entity pool.  Ground movement uses the classic WoW grammar:
forward/back are resolved against the character's facing, A/D rotate in
place, and strafe is an independent axis.  The camera is an observation
system, not a hidden steering wheel.  No physics engine or per-frame object
graph is needed; the fixed-step host owns integration and terrain contact.
"""

from __future__ import annotations

import math
from typing import Any

from backend import game_engine_world as world


SCHEMA = "gg.game-engine.controller.v1"
GROUND_SPEED_MPS = 7.0
SPRINT_SPEED_MPS = 10.5
GROUND_ACCEL_MPS2 = 34.0
GROUND_DECEL_MPS2 = 42.0
TURN_SPEED_RADPS = 2.8
JUMP_SPEED_MPS = 8.5
GRAVITY_MPS2 = 22.0


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clamp(value: Any, low: float, high: float, default: float = 0.0) -> float:
    return max(low, min(high, _finite(value, default)))


def camera_basis(yaw_degrees: Any = 0.0) -> dict[str, tuple[float, float]]:
    """Return forward/right axes for the scene's yaw convention.

    At yaw zero the avatar faces -Z, matching the QtQuick3D scene.  Keeping
    this function as a named compatibility helper also lets old camera-space
    replays be decoded without changing the compact X/Z representation.
    """
    radians = math.radians(_finite(yaw_degrees))
    sine = math.sin(radians)
    cosine = math.cos(radians)
    return {
        "forward": (-sine, -cosine),
        "right": (cosine, -sine),
    }


def character_basis(yaw_radians: Any = 0.0) -> dict[str, tuple[float, float]]:
    """Return the character-facing axes used by ground locomotion."""
    radians = _finite(yaw_radians)
    sine = math.sin(radians)
    cosine = math.cos(radians)
    return {
        "forward": (-sine, -cosine),
        "right": (cosine, -sine),
    }


def movement_direction(
    camera_yaw: Any,
    forward: Any,
    strafe: Any,
) -> tuple[float, float, float]:
    """Resolve normalized facing-relative input to world X/Z direction.

    The historical parameter name is kept for callers that already use this
    small helper.  It now represents character yaw for ground input.
    """
    axes = character_basis(math.radians(_finite(camera_yaw)))
    forward_input = _clamp(forward, -1.0, 1.0)
    strafe_input = _clamp(strafe, -1.0, 1.0)
    x = (
        axes["forward"][0] * forward_input
        + axes["right"][0] * strafe_input
    )
    z = (
        axes["forward"][1] * forward_input
        + axes["right"][1] * strafe_input
    )
    length = math.hypot(x, z)
    if length <= 0.0001:
        return 0.0, 0.0, 0.0
    # Diagonal input must not be faster than cardinal input.
    return x / length, z / length, min(1.0, length)


def _approach(current: float, target: float, maximum_delta: float) -> float:
    delta = target - current
    if abs(delta) <= maximum_delta:
        return target
    return current + math.copysign(maximum_delta, delta)


def ground_step(
    *,
    camera_yaw: Any = 0.0,
    character_yaw: Any | None = None,
    forward: Any = 0.0,
    strafe: Any = 0.0,
    turn_input: Any | None = None,
    legacy_steer: Any = 0.0,
    boost: Any = False,
    current_vx: Any = 0.0,
    current_vz: Any = 0.0,
    current_yaw: Any = 0.0,
    dt: Any = 1.0 / 60.0,
) -> dict[str, Any]:
    """Advance horizontal WoW-style control by one fixed step.

    ``turn_input`` is an in-place yaw axis: negative is left, positive is
    right.  ``legacy_steer`` remains as a compatibility alias for old input
    rows, but it is a turn axis now.  Strafe is never inferred from turn, so
    A/D can rotate without making the player slide sideways.
    """
    safe_dt = _clamp(dt, 0.0, 0.25, 1.0 / 60.0)
    safe_forward = _clamp(forward, -1.0, 1.0)
    safe_strafe = _clamp(strafe, -1.0, 1.0)
    safe_turn = _clamp(
        legacy_steer if turn_input is None else turn_input,
        -1.0,
        1.0,
    )
    safe_character_yaw = (
        math.radians(_finite(camera_yaw))
        if character_yaw is None
        else _finite(character_yaw)
    )
    direction_x, direction_z, input_strength = movement_direction(
        math.degrees(safe_character_yaw),
        safe_forward,
        safe_strafe,
    )
    maximum_speed = SPRINT_SPEED_MPS if bool(boost) else GROUND_SPEED_MPS
    target_vx = direction_x * maximum_speed * input_strength
    target_vz = direction_z * maximum_speed * input_strength
    current_x = _finite(current_vx)
    current_z = _finite(current_vz)
    accelerating = input_strength > 0.0001
    response = GROUND_ACCEL_MPS2 if accelerating else GROUND_DECEL_MPS2
    delta = response * safe_dt
    next_vx = _approach(current_x, target_vx, delta)
    next_vz = _approach(current_z, target_vz, delta)
    next_yaw = _finite(current_yaw)
    next_yaw += safe_turn * TURN_SPEED_RADPS * safe_dt
    next_yaw = (next_yaw + math.pi) % math.tau - math.pi
    next_speed = math.hypot(next_vx, next_vz)
    return {
        "schema": SCHEMA,
        "vx": next_vx,
        "vz": next_vz,
        "yaw": next_yaw,
        "speed": next_speed,
        "direction_x": direction_x,
        "direction_z": direction_z,
        "input_strength": input_strength,
        "turn_input": safe_turn,
        "turning": abs(safe_turn) > 0.0001,
        "ground_speed_mps": maximum_speed,
        "sprinting": bool(boost) and accelerating,
    }


def vertical_step(
    *,
    y: Any,
    vertical_velocity: Any,
    ground_y: Any,
    jump_pressed: Any,
    jump_was_pressed: Any,
    dt: Any,
) -> dict[str, Any]:
    """Advance a cheap grounded jump and return contact state."""
    safe_dt = _clamp(dt, 0.0, 0.25, 1.0 / 60.0)
    safe_ground = _finite(ground_y)
    next_y = _finite(y, safe_ground)
    next_velocity = _finite(vertical_velocity)
    grounded = next_y <= safe_ground + 0.025 and next_velocity <= 0.25
    jumped = bool(jump_pressed) and not bool(jump_was_pressed) and grounded
    if jumped:
        next_velocity = JUMP_SPEED_MPS
        grounded = False
    next_velocity -= GRAVITY_MPS2 * safe_dt
    next_y += next_velocity * safe_dt
    if next_y <= safe_ground:
        next_y = safe_ground
        next_velocity = 0.0
        grounded = True
    else:
        grounded = False
    return {
        "y": next_y,
        "vertical_velocity": next_velocity,
        "grounded": grounded,
        "jumped": jumped,
    }


def build_view(
    *,
    camera_yaw: Any,
    camera_pitch: Any,
    camera_distance: Any,
    grounded: Any,
    sprinting: Any,
) -> dict[str, Any]:
    """Expose controller facts without leaking implementation details."""
    return {
        "schema": SCHEMA,
        "model": "WOW_CLASSIC_THIRD_PERSON",
        "input_space": "CHARACTER_FORWARD_RIGHT",
        "movement_grammar": "W_S_MOVE_A_D_TURN_Q_E_STRAFE",
        "camera_control": "RIGHT_MOUSE_ORBIT_INDEPENDENT_OF_FACING",
        "grounded": bool(grounded),
        "sprinting": bool(sprinting),
        "camera": {
            "yaw": round(_finite(camera_yaw), 4),
            "pitch": round(_clamp(camera_pitch, -89.0, 20.0, -27.0), 4),
            "distance_m": round(
                _clamp(
                    camera_distance,
                    4.0,
                    160.0,
                    world.DEFAULT_CAMERA_DISTANCE_M,
                ),
                3,
            ),
        },
        "limits": {
            "walk_speed_mps": GROUND_SPEED_MPS,
            "sprint_speed_mps": SPRINT_SPEED_MPS,
            "jump_speed_mps": JUMP_SPEED_MPS,
            "gravity_mps2": GRAVITY_MPS2,
        },
    }
