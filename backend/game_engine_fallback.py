"""Terminal-style fallback view built from the authoritative game snapshot.

The DOS presentation is intentionally a renderer, not a second game mode.
It receives the same bounded entity, terrain and player rows as the rich 3D
surface.  A graphics-stage failure can therefore hide QtQuick3D while fixed
step movement, inventory, NPC identity, loot, economy, progression and persistence continue to use
exactly the same data.
"""

from __future__ import annotations

import math
from typing import Any, Iterable


SCHEMA = "gg.game-engine.fallback.v1"
MODE = "DOS_2D"
MAX_ENTITIES = 96
MAX_TERRAIN_CELLS = 64
MAX_TERMINAL_LINES = 16


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _text(value: Any, default: str = "", limit: int = 64) -> str:
    return str(value or default).strip()[:limit]


def _equip_glyph(slot: Any) -> str:
    wanted = _text(slot, "", 16).upper()
    return {
        "HEAD": "*",
        "CHEST": "[",
        "BACK": "b",
        "FEET": "f",
        "MAIN_HAND": "/",
        "OFF_HAND": "o",
        "RANGED": "}",
    }.get(wanted, "+")


def _glyph(row: dict[str, Any]) -> str:
    kind = _text(row.get("kind"), "PROP", 32).upper()
    if kind == "PLAYER":
        return "@"
    if kind == "NPC" or "NPC" in kind:
        return "G"
    if kind == "GROUND_ITEM":
        return "!"
    if kind == "CHEST":
        return "C"
    if kind == "RAMP":
        return "^"
    if kind == "PALM" or "TREE" in kind:
        return "Y"
    if kind == "HOUSE" or "HUT" in kind:
        return "A"
    if kind == "DOCK" or "PIER" in kind:
        return "="
    if kind == "TOTEM" or "SHRINE" in kind:
        return "T"
    if kind == "LIGHT" or "LANTERN" in kind:
        return "i"
    if kind == "PROP":
        return "*"
    return "."


def _terrain_glyph(row: dict[str, Any]) -> str:
    surface = _text(row.get("surface"), "LAND", 24).upper()
    biome = _text(row.get("biome"), "LAND", 32).upper()
    if surface == "WATER" or "WATER" in biome or "REEF" in biome:
        return "~"
    if "CLIFF" in biome:
        return "#"
    if "DEEP" in biome:
        return "~"
    return ","


def _position(row: dict[str, Any]) -> tuple[float, float]:
    return _safe_float(row.get("x")), _safe_float(row.get("z"))


def build_view(
    entity_rows: Iterable[dict[str, Any]] = (),
    terrain_rows: Iterable[dict[str, Any]] = (),
    *,
    player_x: Any = 0.0,
    player_z: Any = 0.0,
    state: Any = "IDLE",
    tick: Any = 0,
    active_entities: Any = 0,
    active_particles: Any = 0,
    event_rows: Iterable[dict[str, Any]] = (),
    command: dict[str, Any] | None = None,
    equipment_rows: Iterable[dict[str, Any]] = (),
    economy: dict[str, Any] | None = None,
    combat: dict[str, Any] | None = None,
    quests: dict[str, Any] | None = None,
    factions: dict[str, Any] | None = None,
    dialogue: dict[str, Any] | None = None,
    social: dict[str, Any] | None = None,
    world_events: dict[str, Any] | None = None,
    radius_m: Any = 18.0,
) -> dict[str, Any]:
    """Build a bounded terminal map without inventing gameplay state."""
    safe_player_x = _safe_float(player_x)
    safe_player_z = _safe_float(player_z)
    safe_radius = max(6.0, min(256.0, _safe_float(radius_m, 18.0)))

    entities: list[dict[str, Any]] = []
    for row in list(entity_rows)[:MAX_ENTITIES]:
        if not isinstance(row, dict):
            continue
        x, z = _position(row)
        individual = row.get("individual")
        if not isinstance(individual, dict):
            individual = {}
        kind = _text(row.get("kind"), "PROP", 32).upper()
        name = _text(individual.get("name"), row.get("id"), 64)
        raw_progression = individual.get("progression")
        progression = raw_progression if isinstance(raw_progression, dict) else {}
        npc_progression = {
            "level": max(1, int(_safe_float(progression.get("level"), 1))),
            "spec": _text(progression.get("spec"), "EXPLORER", 24).upper(),
            "ascension": max(0, int(_safe_float(progression.get("ascension"), 0))),
            "gear_score": round(max(0.0, _safe_float(progression.get("gear_score"))), 3),
            "power_score": round(max(0.0, _safe_float(progression.get("power_score"))), 3),
        }
        label = name
        if kind == "NPC" or "NPC" in kind:
            label = (
                f"{name} L{npc_progression['level']} "
                f"P{npc_progression['power_score']:.0f}"
            )[:64]
        equipment = row.get("equipment") if isinstance(row.get("equipment"), list) else []
        compact_equipment: list[dict[str, Any]] = []
        for item in equipment[:8]:
            if not isinstance(item, dict):
                continue
            slot = _text(item.get("equipped_slot"), "", 16).upper()
            attachment = item.get("attachment") if isinstance(item.get("attachment"), dict) else {}
            compact_equipment.append(
                {
                    "slot": slot,
                    "name": _text(item.get("name"), "", 32),
                    "socket": _text(attachment.get("socket"), slot, 16).upper(),
                    "glyph": _equip_glyph(slot),
                    "color": _text(
                        (item.get("visual") or {}).get("base_color")
                        if isinstance(item.get("visual"), dict)
                        else item.get("rarity_color"),
                        "#d6d6d6",
                        16,
                    ),
                }
            )
        entities.append(
            {
                "id": _text(row.get("id"), "entity-unknown", 96),
                "kind": kind,
                "x": round(x, 3),
                "z": round(z, 3),
                "glyph": _glyph(row),
                "color": _text(row.get("color"), "#8db89a", 16),
                "label": label,
                "equipment": compact_equipment,
                "state": _text(row.get("motion_state"), "STATIC", 32).upper(),
                "action": _text(
                    individual.get("action"),
                    row.get("world_action"),
                    32,
                ).upper(),
                "target_id": _text(
                    (individual.get("target") or {}).get("id")
                    if isinstance(individual.get("target"), dict)
                    else "",
                    "",
                    96,
                ),
                "progression": npc_progression,
            }
        )

    terrain: list[dict[str, Any]] = []
    for row in list(terrain_rows)[:MAX_TERRAIN_CELLS]:
        if not isinstance(row, dict):
            continue
        center = row.get("center_m")
        center = center if isinstance(center, dict) else row
        terrain.append(
            {
                "key": _text(row.get("key"), "cell-unknown", 64),
                "x": round(_safe_float(center.get("x")), 3),
                "z": round(_safe_float(center.get("z")), 3),
                "glyph": _terrain_glyph(row),
                "surface": _text(row.get("surface"), "LAND", 24).upper(),
            }
        )

    safe_state = _text(state, "IDLE", 24).upper()
    safe_tick = max(0, int(_safe_float(tick)))
    safe_active_entities = max(0, int(_safe_float(active_entities)))
    safe_active_particles = max(0, int(_safe_float(active_particles)))
    economy_view = economy if isinstance(economy, dict) else {}
    wallet = economy_view.get("wallet", {})
    wallet_gold = max(0, int(_safe_float(wallet.get("gold"), 0))) if isinstance(wallet, dict) else 0
    vendors = economy_view.get("vendors", [])
    first_vendor = vendors[0] if isinstance(vendors, list) and vendors else {}
    vendor_name = _text(first_vendor.get("name"), "NONE", 24) if isinstance(first_vendor, dict) else "NONE"
    vendor_presence = first_vendor.get("presence", {}) if isinstance(first_vendor, dict) else {}
    vendor_status = (
        "READY"
        if isinstance(vendor_presence, dict) and vendor_presence.get("available")
        else "OUT"
    )
    combat_view = combat if isinstance(combat, dict) else {}
    combat_actors = combat_view.get("actors", [])
    player_actor = next(
        (
            row
            for row in combat_actors
            if isinstance(row, dict) and str(row.get("id")) == "player"
        ),
        {},
    ) if isinstance(combat_actors, list) else {}
    quests_view = quests if isinstance(quests, dict) else {}
    factions_view = factions if isinstance(factions, dict) else {}
    dialogue_view = dialogue if isinstance(dialogue, dict) else {}
    social_view = social if isinstance(social, dict) else {}
    world_events_view = world_events if isinstance(world_events, dict) else {}
    faction_rows = factions_view.get("factions", [])
    player_faction = next(
        (
            row
            for row in faction_rows
            if isinstance(row, dict) and row.get("player_standing")
        ),
        faction_rows[0] if isinstance(faction_rows, list) and faction_rows else {},
    ) if isinstance(faction_rows, list) else {}
    health = max(0, int(_safe_float(player_actor.get("health"), 0)))
    max_health = max(0, int(_safe_float(player_actor.get("max_health"), 0)))
    quest_active = max(0, int(_safe_float(quests_view.get("active_count"), 0)))
    quest_ready = max(0, int(_safe_float(quests_view.get("ready"), 0)))
    faction_id = _text(player_faction.get("id"), "NONE", 24).upper()
    faction_standing = int(_safe_float(player_faction.get("player_standing"), 0))
    lines = [
        "GG//DOS FRONTIER",
        f"STATE {safe_state}  TICK {safe_tick}",
        f"ENT {safe_active_entities}  FX {safe_active_particles}",
        f"POS {safe_player_x:.1f},{safe_player_z:.1f}",
    ]
    gear_bits: list[str] = []
    for item in list(equipment_rows)[:6]:
        if not isinstance(item, dict):
            continue
        slot = _text(item.get("equipped_slot"), "", 8).upper()
        name = _text(item.get("name"), "", 18)
        if not slot and not name:
            continue
        gear_bits.append(f"{slot[:2] or _equip_glyph(slot)}:{name or slot}")
    if not gear_bits:
        player_row = next(
            (
                row
                for row in entities
                if isinstance(row, dict) and row.get("kind") == "PLAYER"
            ),
            {},
        )
        for item in (player_row.get("equipment") or [])[:6]:
            if not isinstance(item, dict):
                continue
            slot = _text(item.get("slot"), "", 8)
            name = _text(item.get("name"), "", 18)
            if slot or name:
                gear_bits.append(f"{slot[:2] or '+'}:{name or slot}")
    if gear_bits:
        lines.append("GEAR " + " ".join(gear_bits))
    lines.extend(
        [
            "@ YOU  G NPC  ! LOOT  C CACHE",
            "WASD MOVE  E INTERACT  I BAG",
            f"GOLD {wallet_gold}  SHOP {vendor_name} {vendor_status}",
            f"HP {health}/{max_health}  QUEST {quest_active} ACTIVE {quest_ready} READY",
            f"REP {faction_id} {faction_standing:+d}  COMBAT {str(player_actor.get('alive', True)).upper()}",
        ]
    )
    active_events = world_events_view.get("active", [])
    if isinstance(active_events, list) and active_events:
        first_event = active_events[0] if isinstance(active_events[0], dict) else {}
        lines.append(
            f"EVENT {_text(first_event.get('name'), 'WORLD EVENT', 28)} "
            f"{int(_safe_float((first_event.get('state') or {}).get('progress'), 0.0) * 100):02d}%"
        )
    dialogue_node = dialogue_view.get("node", {})
    dialogue_active = dialogue_view.get("active", {})
    if dialogue_view.get("open") and isinstance(dialogue_node, dict):
        speaker = _text(dialogue_node.get("speaker"), "NPC", 24)
        spoken = _text(dialogue_node.get("text"), "", 72)
        choices = dialogue_node.get("choices", [])
        choice_ids = "/".join(
            _text(choice.get("id"), limit=20)
            for choice in choices[:3]
            if isinstance(choice, dict) and choice.get("id")
        ) if isinstance(choices, list) else ""
        lines.append(
            f"TALK {_text(dialogue_active.get('npc_id'), 'NPC', 20)} "
            f"{speaker}: {spoken} {choice_ids}".strip()
        )
    recent_events: list[str] = []
    for raw_event in list(event_rows)[-3:]:
        if not isinstance(raw_event, dict):
            continue
        sequence = max(0, int(_safe_float(raw_event.get("sequence"), 0)))
        kind = _text(raw_event.get("kind"), "EVENT", 16).upper()
        text = _text(raw_event.get("text"), kind, 72)
        recent_events.append(f"{sequence:04d} {kind} {text}")
    last_command = command if isinstance(command, dict) else {}
    command_input = _text(last_command.get("input"), limit=48)
    command_message = _text(last_command.get("message"), limit=72)
    command_lines: list[str] = []
    if command_input:
        command_lines = [
            f"> {command_input}",
            f"{'OK' if last_command.get('ok') else 'ERR'} {command_message}",
        ]
    event_capacity = max(0, MAX_TERMINAL_LINES - len(lines) - len(command_lines))
    lines.extend(recent_events[-event_capacity:])
    lines.extend(command_lines)
    lines = lines[:MAX_TERMINAL_LINES]
    return {
        "schema": SCHEMA,
        "version": 1,
        "mode": MODE,
        "renderer": "QTQUICK_CANVAS_TERMINAL",
        "palette": {
            "background": "#030604",
            "grid": "#173117",
            "text": "#9fe3a4",
            "muted": "#5d9b66",
            "player": "#e3bd63",
            "water": "#4c9ca0",
        },
        "camera": {
            "center_x": round(safe_player_x, 3),
            "center_z": round(safe_player_z, 3),
            "radius_m": round(safe_radius, 3),
        },
        "entities": entities,
        "terrain": terrain,
        "combat": dict(combat_view),
        "quests": dict(quests_view),
        "factions": dict(factions_view),
        "dialogue": dict(dialogue_view),
        "social": dict(social_view),
        "world_events": dict(world_events_view),
        "terminal": {
            "title": "GG//DOS FRONTIER",
            "prompt": ">",
            "lines": lines,
        },
        "command": dict(last_command),
        "shared_contract": "AUTHORITATIVE_FIXED_STEP_ENTITY_ITEM_NPC_DATA",
        "policy": "BOUNDED_2D_FALLBACK_RENDERER_NO_SIMULATION_MUTATION",
    }
