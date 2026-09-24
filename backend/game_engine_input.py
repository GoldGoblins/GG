"""Data-only input and keybinding contract for the GAME ENGINE.

The default grammar intentionally follows the classic World of Warcraft
third-person convention: W/S move forward and backward, A/D turn in place,
and Q/E strafe.  Bindings are kept as compact data so the same action names
can be consumed by QML, replays, a future native client and an in-game editor.
There is no arbitrary script execution in this layer.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA = "gg.game-engine.input.v1"
VERSION = 1
MODEL = "WOW_CLASSIC_THIRD_PERSON"


ACTION_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "MOVE_FORWARD",
        "label": "Move forward",
        "group": "MOVEMENT",
        "default": ["W", "UP"],
    },
    {
        "id": "MOVE_BACK",
        "label": "Move backward",
        "group": "MOVEMENT",
        "default": ["S", "DOWN"],
    },
    {
        "id": "TURN_LEFT",
        "label": "Turn left",
        "group": "MOVEMENT",
        "default": ["A", "LEFT"],
    },
    {
        "id": "TURN_RIGHT",
        "label": "Turn right",
        "group": "MOVEMENT",
        "default": ["D", "RIGHT"],
    },
    {
        "id": "STRAFE_LEFT",
        "label": "Strafe left",
        "group": "MOVEMENT",
        "default": ["Q"],
    },
    {
        "id": "STRAFE_RIGHT",
        "label": "Strafe right",
        "group": "MOVEMENT",
        "default": ["E"],
    },
    {
        "id": "JUMP",
        "label": "Jump",
        "group": "MOVEMENT",
        "default": ["SPACE"],
    },
    {
        "id": "SPRINT",
        "label": "Sprint",
        "group": "MOVEMENT",
        "default": ["SHIFT"],
    },
    {
        "id": "VERTICAL_UP",
        "label": "Swim / fly up",
        "group": "MOVEMENT",
        "default": ["R"],
    },
    {
        "id": "VERTICAL_DOWN",
        "label": "Swim / fly down",
        "group": "MOVEMENT",
        "default": ["F"],
    },
    {
        "id": "ABILITY_SURGE",
        "label": "Ability: Surge",
        "group": "ABILITIES",
        "default": ["Z"],
    },
    {
        "id": "ABILITY_UNDERTOW",
        "label": "Ability: Undertow",
        "group": "ABILITIES",
        "default": ["X"],
    },
    {
        "id": "ABILITY_SKY_LEAP",
        "label": "Ability: Sky Leap",
        "group": "ABILITIES",
        "default": ["C"],
    },
)

ACTION_IDS = tuple(row["id"] for row in ACTION_DEFINITIONS)
DEFAULT_BINDINGS = {
    row["id"]: tuple(row["default"])
    for row in ACTION_DEFINITIONS
}

_KEY_ALIASES = {
    "SPACEBAR": "SPACE",
    "RETURN": "ENTER",
    "ESC": "ESCAPE",
    "CTRL": "CONTROL",
    "OPTION": "ALT",
}
_SPECIAL_KEYS = {
    "SPACE",
    "SHIFT",
    "CONTROL",
    "ALT",
    "META",
    "TAB",
    "ENTER",
    "ESCAPE",
    "BACKSPACE",
    "DELETE",
    "UP",
    "DOWN",
    "LEFT",
    "RIGHT",
}


def normalize_key(value: Any) -> str | None:
    """Normalize a QML/native key token without accepting executable data."""
    token = str(value or "").strip().upper()
    token = _KEY_ALIASES.get(token, token)
    if token in _SPECIAL_KEYS:
        return token
    if len(token) == 1 and (token.isalpha() or token.isdigit()):
        return token
    if token.startswith("F") and token[1:].isdigit():
        number = int(token[1:])
        if 1 <= number <= 24:
            return token
    return None


def _definition(action: Any) -> dict[str, Any] | None:
    wanted = str(action or "").strip().upper()
    for row in ACTION_DEFINITIONS:
        if row["id"] == wanted:
            return row
    return None


def new_bindings() -> dict[str, Any]:
    """Return a fresh default binding state."""
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "model": MODEL,
        "bindings": {
            action: list(keys) for action, keys in DEFAULT_BINDINGS.items()
        },
        "actions": [
            {
                "id": row["id"],
                "label": row["label"],
                "group": row["group"],
            }
            for row in ACTION_DEFINITIONS
        ],
        "policy": "UNIQUE_PRIMARY_KEYS_DATA_ONLY",
    }


def normalize_bindings(state: Any) -> dict[str, Any]:
    """Return a bounded, valid copy while preserving known custom bindings."""
    normalized = new_bindings()
    if not isinstance(state, dict):
        return normalized
    source = state.get("bindings", state)
    if not isinstance(source, dict):
        return normalized
    for action in ACTION_IDS:
        raw_keys = source.get(action)
        if isinstance(raw_keys, str):
            raw_keys = [raw_keys]
        if not isinstance(raw_keys, (list, tuple)):
            continue
        keys: list[str] = []
        for raw_key in raw_keys[:3]:
            key = normalize_key(raw_key)
            if key and key not in keys:
                keys.append(key)
        if keys:
            normalized["bindings"][action] = keys
    return normalized


def set_binding(
    state: Any,
    action: Any,
    key: Any,
    *,
    slot: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Assign one key and move it out of another action if necessary.

    Moving a key instead of allowing silent duplicate axes makes the editor
    predictable.  The previous alternate key remains when a primary binding
    is replaced, which keeps the arrow-key convenience intact.
    """
    normalized = normalize_bindings(state)
    definition = _definition(action)
    normalized_key = normalize_key(key)
    if definition is None:
        return normalized, {
            "ok": False,
            "error": "GAME_ENGINE_BINDING_ACTION_INVALID",
            "action": str(action or ""),
        }
    if normalized_key is None:
        return normalized, {
            "ok": False,
            "error": "GAME_ENGINE_BINDING_KEY_INVALID",
            "key": str(key or ""),
        }
    try:
        safe_slot = max(0, min(2, int(slot)))
    except (TypeError, ValueError):
        safe_slot = 0

    action_id = definition["id"]
    for other_action, keys in normalized["bindings"].items():
        if other_action != action_id and normalized_key in keys:
            normalized["bindings"][other_action] = [
                other_key for other_key in keys if other_key != normalized_key
            ]
    keys = [
        existing for existing in normalized["bindings"][action_id]
        if existing != normalized_key
    ]
    safe_slot = min(safe_slot, len(keys))
    keys.insert(safe_slot, normalized_key)
    normalized["bindings"][action_id] = keys[:3]
    return normalized, {
        "ok": True,
        "action": action_id,
        "key": normalized_key,
        "slot": safe_slot,
    }


def action_for_key(state: Any, key: Any) -> list[str]:
    """Return matching actions for diagnostics and future input backends."""
    normalized_key = normalize_key(key)
    if not normalized_key:
        return []
    normalized = normalize_bindings(state)
    return [
        action
        for action, keys in normalized["bindings"].items()
        if normalized_key in keys
    ]


def summary(state: Any) -> dict[str, Any]:
    """Return a compact copy safe to expose in a render snapshot."""
    normalized = normalize_bindings(state)
    result = deepcopy(normalized)
    result["primary"] = {
        action: keys[0] if keys else ""
        for action, keys in normalized["bindings"].items()
    }
    return result
