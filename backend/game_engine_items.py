"""Bounded, data-driven item instances for the GAME ENGINE vertical slice.

An item definition is authored content.  An item instance is the living
runtime fact: it can be on the ground, inside a container, in a pocket, in a
player inventory or equipped without changing the definition or renderer
contract.  The visual binding is deliberately small and can later point at a
validated authored mesh instead of the current native QtQuick3D primitive.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Iterable

from backend import game_engine_assets as assets_catalog
from backend import game_engine_gear as gear_catalog

SCHEMA = "gg.game-engine.items.v1"
VERSION = 1

RARITIES = (
    "TRASH",
    "COMMON",
    "UNCOMMON",
    "RARE",
    "EPIC",
    "LEGENDARY",
    "ARTIFACT",
)
LOCATIONS = ("GROUND", "CONTAINER", "INVENTORY", "EQUIPPED", "POCKET", "DESTROYED")
PLAYER_OWNED_LOCATIONS = frozenset({"INVENTORY", "EQUIPPED"})
MAX_WORLD_INSTANCES = 96
MAX_INVENTORY_SLOTS = 64
MAX_CONTAINER_ITEMS = 16
MAX_EQUIPPED_ITEMS = 8
MAX_POCKET_ITEMS = 64
INTERACTION_RADIUS_M = 3.75

RARITY_STYLES: dict[str, dict[str, Any]] = {
    "TRASH": {"color": "#7f8993", "glow": 0.0, "rank": 0},
    "COMMON": {"color": "#d6d6d6", "glow": 0.0, "rank": 1},
    "UNCOMMON": {"color": "#76c47d", "glow": 0.03, "rank": 2},
    "RARE": {"color": "#70a9e8", "glow": 0.08, "rank": 3},
    "EPIC": {"color": "#b88cff", "glow": 0.13, "rank": 4},
    "LEGENDARY": {"color": "#ee9949", "glow": 0.18, "rank": 5},
    "ARTIFACT": {"color": "#f0d26f", "glow": 0.24, "rank": 6},
}
QUALITY_SURFACE: dict[str, dict[str, float]] = {
    "STANDARD": {"metalness": 0.22, "roughness": 0.48, "glow": 0.0},
    "FINE": {"metalness": 0.34, "roughness": 0.38, "glow": 0.04},
    "MASTERWORK": {"metalness": 0.48, "roughness": 0.28, "glow": 0.10},
    "ARTIFACT": {"metalness": 0.58, "roughness": 0.20, "glow": 0.18},
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _safe_position(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        value = {}
    return {
        "x": _safe_float(value.get("x")),
        "y": _safe_float(value.get("y")),
        "z": _safe_float(value.get("z")),
    }


def normalize_rarity(value: Any, default: str = "COMMON") -> str:
    candidate = str(value or default).upper()
    return candidate if candidate in RARITIES else str(default).upper()


def rarity_style(value: Any) -> dict[str, Any]:
    rarity = normalize_rarity(value)
    return copy.deepcopy(RARITY_STYLES[rarity])


def normalize_quality(value: Any, default: str = "STANDARD") -> str:
    candidate = str(value or default).upper()
    return candidate if candidate in QUALITY_SURFACE else str(default).upper()


def tint_variant_for(
    rarity: Any,
    quality: Any = "STANDARD",
    palette: Any = None,
) -> dict[str, Any]:
    """Combine rarity, craft quality and an optional gear palette into one tint."""
    style = rarity_style(rarity)
    quality_id = normalize_quality(quality)
    surface = QUALITY_SURFACE[quality_id]
    color = str(palette or style["color"])
    if not color.startswith("#"):
        color = style["color"]
    return {
        "tint_variant": f"{normalize_rarity(rarity)}_{quality_id}",
        "base_color": color[:16],
        "rarity_color": style["color"],
        "metalness": surface["metalness"],
        "roughness": surface["roughness"],
        "glow": round(style["glow"] + surface["glow"], 3),
    }


def _palette_for_definition(
    catalog: dict[str, Any],
    definition_id: Any,
    quality: Any,
    location: Any,
) -> str | None:
    if str(location or "").upper() != "EQUIPPED":
        return None
    spec = gear_catalog.gear_spec_for_definition(
        definition_id,
        catalog.get("gear") if isinstance(catalog.get("gear"), dict) else None,
    )
    if not isinstance(spec, dict):
        return None
    variants = spec.get("palette_variants")
    if isinstance(variants, dict):
        color = variants.get(normalize_quality(quality)) or variants.get("STANDARD")
        if color:
            return str(color)[:16]
    palette = spec.get("palette")
    return str(palette)[:16] if palette else None


def _visual_states(
    asset_id: str,
    model: str,
    scale: tuple[float, float, float],
    rotation: tuple[float, float, float],
    *,
    ground_offset: float,
    ground_float: float,
    spin_deg_s: float,
    equipped_scale: tuple[float, float, float] | None = None,
) -> dict[str, Any]:
    """Build explicit context states for one item mesh placeholder."""
    equipped = equipped_scale or scale
    states: dict[str, dict[str, Any]] = {}
    for context in ("GROUND", "CONTAINER", "INVENTORY", "EQUIPPED", "POCKET"):
        context_scale = scale
        offset_y = 0.0
        float_m = 0.0
        context_spin = 0.0
        if context == "GROUND":
            offset_y = ground_offset
            float_m = ground_float
            context_spin = spin_deg_s
        elif context == "CONTAINER":
            context_scale = tuple(component * 0.72 for component in scale)
        elif context == "EQUIPPED":
            context_scale = equipped
        states[context] = {
            "asset_id": asset_id,
            "renderer": "NATIVE_ASSET_KIT",
            "model": model,
            "scale": list(context_scale),
            "rotation": list(rotation),
            "offset_y": offset_y,
            "float_m": float_m,
            "spin_deg_s": context_spin,
        }
    return {"asset_id": asset_id, "states": states}


def starter_definitions() -> dict[str, dict[str, Any]]:
    """Return the first rich item catalogue as fresh authoring data."""
    return {
        "item.island_compass": {
            "id": "item.island_compass",
            "name": "Island Compass",
            "kind": "QUEST",
            "rarity": "COMMON",
            "level": 1,
            "stack_limit": 1,
            "equip_slot": "OFF_HAND",
            "tags": ["NAVIGATION", "STARTER", "EQUIPMENT"],
            "asset_id": "itemmesh.island_compass",
            "visual": _visual_states(
                "itemmesh.island_compass",
                "#Sphere",
                (0.16, 0.16, 0.16),
                (0.0, 0.0, 0.0),
                ground_offset=0.18,
                ground_float=0.08,
                spin_deg_s=22.0,
                equipped_scale=(0.11, 0.11, 0.11),
            ),
        },
        "item.sea_salt": {
            "id": "item.sea_salt",
            "name": "Sea Salt",
            "kind": "MATERIAL",
            "rarity": "COMMON",
            "level": 1,
            "stack_limit": 99,
            "tags": ["CRAFTING", "WATER"],
            "asset_id": "itemmesh.sea_salt",
            "visual": _visual_states(
                "itemmesh.sea_salt",
                "#Sphere",
                (0.13, 0.13, 0.13),
                (0.0, 0.0, 0.0),
                ground_offset=0.14,
                ground_float=0.04,
                spin_deg_s=8.0,
            ),
        },
        "item.sun_herb": {
            "id": "item.sun_herb",
            "name": "Sun Herb",
            "kind": "MATERIAL",
            "rarity": "UNCOMMON",
            "level": 1,
            "stack_limit": 99,
            "tags": ["CRAFTING", "NATURE"],
            "asset_id": "itemmesh.sun_herb",
            "visual": _visual_states(
                "itemmesh.sun_herb",
                "#Sphere",
                (0.12, 0.24, 0.12),
                (0.0, 0.0, 28.0),
                ground_offset=0.2,
                ground_float=0.07,
                spin_deg_s=14.0,
            ),
        },
        "item.field_ration": {
            "id": "item.field_ration",
            "name": "Field Ration",
            "kind": "CONSUMABLE",
            "rarity": "COMMON",
            "level": 1,
            "stack_limit": 20,
            "tags": ["FOOD", "RECOVERY"],
            "asset_id": "itemmesh.field_ration",
            "visual": _visual_states(
                "itemmesh.field_ration",
                "#Cube",
                (0.22, 0.14, 0.22),
                (0.0, 18.0, 0.0),
                ground_offset=0.14,
                ground_float=0.03,
                spin_deg_s=5.0,
            ),
        },
        "item.old_boot": {
            "id": "item.old_boot",
            "name": "Old Boot",
            "kind": "TRASH",
            "rarity": "TRASH",
            "level": 1,
            "stack_limit": 1,
            "tags": ["JUNK", "SHORE"],
            "asset_id": "itemmesh.old_boot",
            "visual": _visual_states(
                "itemmesh.old_boot",
                "#Cube",
                (0.2, 0.3, 0.16),
                (8.0, 25.0, -18.0),
                ground_offset=0.18,
                ground_float=0.02,
                spin_deg_s=3.0,
            ),
        },
        "item.iron_saber": {
            "id": "item.iron_saber",
            "name": "Iron Saber",
            "kind": "WEAPON",
            "rarity": "UNCOMMON",
            "level": 2,
            "stack_limit": 1,
            "equip_slot": "MAIN_HAND",
            "tags": ["WEAPON", "MELEE", "STARTER"],
            "asset_id": "itemmesh.iron_saber",
            "visual": _visual_states(
                "itemmesh.iron_saber",
                "#Cube",
                (0.09, 0.72, 0.09),
                (0.0, 0.0, 42.0),
                ground_offset=0.38,
                ground_float=0.1,
                spin_deg_s=34.0,
                equipped_scale=(0.07, 0.55, 0.07),
            ),
        },
        "item.tideguard_jacket": {
            "id": "item.tideguard_jacket",
            "name": "Tideguard Jacket",
            "kind": "ARMOR",
            "rarity": "RARE",
            "level": 3,
            "stack_limit": 1,
            "equip_slot": "CHEST",
            "tags": ["ARMOR", "WATER", "GUARDIAN"],
            "asset_id": "itemmesh.tideguard_jacket",
            "visual": _visual_states(
                "itemmesh.tideguard_jacket",
                "#Cube",
                (0.38, 0.38, 0.22),
                (0.0, 0.0, 0.0),
                ground_offset=0.34,
                ground_float=0.06,
                spin_deg_s=12.0,
                equipped_scale=(0.31, 0.31, 0.18),
            ),
        },
        "item.moon_shard": {
            "id": "item.moon_shard",
            "name": "Moon Shard",
            "kind": "MATERIAL",
            "rarity": "EPIC",
            "level": 5,
            "stack_limit": 12,
            "tags": ["CRAFTING", "ARCANE", "NIGHT"],
            "asset_id": "itemmesh.moon_shard",
            "visual": _visual_states(
                "itemmesh.moon_shard",
                "#Sphere",
                (0.2, 0.28, 0.2),
                (0.0, 0.0, 32.0),
                ground_offset=0.28,
                ground_float=0.13,
                spin_deg_s=46.0,
            ),
        },
        "item.sunken_crown": {
            "id": "item.sunken_crown",
            "name": "Sunken Crown",
            "kind": "ARMOR",
            "rarity": "LEGENDARY",
            "level": 8,
            "stack_limit": 1,
            "equip_slot": "HEAD",
            "tags": ["ARMOR", "LEGENDARY", "TIDE"],
            "asset_id": "itemmesh.sunken_crown",
            "visual": _visual_states(
                "itemmesh.sunken_crown",
                "#Cube",
                (0.28, 0.18, 0.28),
                (0.0, 0.0, 0.0),
                ground_offset=0.3,
                ground_float=0.12,
                spin_deg_s=26.0,
                equipped_scale=(0.2, 0.13, 0.2),
            ),
        },
        "item.drift_cloak": {
            "id": "item.drift_cloak",
            "name": "Drift Cloak",
            "kind": "ARMOR",
            "rarity": "UNCOMMON",
            "level": 2,
            "stack_limit": 1,
            "equip_slot": "BACK",
            "tags": ["ARMOR", "CLOAK", "STARTER", "WATER"],
            "asset_id": "itemmesh.drift_cloak",
            "visual": _visual_states(
                "itemmesh.drift_cloak",
                "#Cube",
                (0.42, 0.58, 0.12),
                (8.0, 0.0, 0.0),
                ground_offset=0.32,
                ground_float=0.07,
                spin_deg_s=10.0,
                equipped_scale=(0.34, 0.48, 0.08),
            ),
        },
        "item.saltpath_boots": {
            "id": "item.saltpath_boots",
            "name": "Saltpath Boots",
            "kind": "ARMOR",
            "rarity": "COMMON",
            "level": 1,
            "stack_limit": 1,
            "equip_slot": "FEET",
            "tags": ["ARMOR", "BOOTS", "STARTER", "TRAVEL"],
            "asset_id": "itemmesh.saltpath_boots",
            "visual": _visual_states(
                "itemmesh.saltpath_boots",
                "#Cube",
                (0.22, 0.16, 0.28),
                (0.0, 12.0, 0.0),
                ground_offset=0.16,
                ground_float=0.03,
                spin_deg_s=6.0,
                equipped_scale=(0.18, 0.12, 0.22),
            ),
        },
        "item.goblin_totem": {
            "id": "item.goblin_totem",
            "name": "Goblin Totem",
            "kind": "QUEST",
            "rarity": "ARTIFACT",
            "level": 7,
            "stack_limit": 1,
            "tags": ["QUEST", "TOTEM", "LIFE"],
            "asset_id": "itemmesh.goblin_totem",
            "visual": _visual_states(
                "itemmesh.goblin_totem",
                "#Cube",
                (0.2, 0.5, 0.2),
                (0.0, 0.0, 0.0),
                ground_offset=0.3,
                ground_float=0.1,
                spin_deg_s=18.0,
            ),
        },
    }


def starter_containers() -> dict[str, dict[str, Any]]:
    return {
        "container.supply_crate": {
            "id": "container.supply_crate",
            "name": "Tide Supply Crate",
            "kind": "CONTAINER",
            "rarity": "COMMON",
            "level": 1,
            "stack_limit": 1,
            "tags": ["CONTAINER", "LOOT", "SHORE"],
            "asset_id": "container.supply_crate",
            "visual": _visual_states(
                "container.supply_crate",
                "#Cube",
                (0.9, 0.62, 0.9),
                (0.0, 0.0, 0.0),
                ground_offset=0.44,
                ground_float=0.015,
                spin_deg_s=0.0,
            ),
        },
    }


def starter_loot_tables() -> dict[str, dict[str, Any]]:
    return {
        "loot.coastal_cache": {
            "id": "loot.coastal_cache",
            "name": "Coastal Cache",
            "entries": [
                {"item_id": "item.sea_salt", "weight": 28, "min": 1, "max": 3},
                {"item_id": "item.sun_herb", "weight": 23, "min": 1, "max": 3},
                {"item_id": "item.iron_saber", "weight": 17, "min": 1, "max": 1},
                {"item_id": "item.tideguard_jacket", "weight": 11, "min": 1, "max": 1},
                {"item_id": "item.drift_cloak", "weight": 9, "min": 1, "max": 1},
                {"item_id": "item.saltpath_boots", "weight": 10, "min": 1, "max": 1},
                {"item_id": "item.moon_shard", "weight": 5, "min": 1, "max": 2},
                {"item_id": "item.sunken_crown", "weight": 3, "min": 1, "max": 1},
                {"item_id": "item.goblin_totem", "weight": 1, "min": 1, "max": 1},
            ],
        },
        "loot.goblin_pocket": {
            "id": "loot.goblin_pocket",
            "name": "Goblin Pocket",
            "entries": [
                {"item_id": "item.old_boot", "weight": 35, "min": 1, "max": 1},
                {"item_id": "item.sea_salt", "weight": 23, "min": 1, "max": 2},
                {"item_id": "item.moon_shard", "weight": 2, "min": 1, "max": 1},
            ],
        },
    }


def catalog_from_content(content: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a fresh item catalogue while allowing authored content overrides."""
    source = content if isinstance(content, dict) else {}
    defaults = starter_definitions()
    source_items = source.get("items", {})
    items: dict[str, dict[str, Any]] = {}
    for item_id, default in defaults.items():
        override = source_items.get(item_id) if isinstance(source_items, dict) else None
        merged = copy.deepcopy(default)
        if isinstance(override, dict):
            merged.update(copy.deepcopy(override))
            # A partial authored row cannot remove the safe visual contract.
            if not isinstance(override.get("visual"), dict):
                merged["visual"] = copy.deepcopy(default["visual"])
        items[item_id] = merged
    if isinstance(source_items, dict):
        for item_id, value in source_items.items():
            if str(item_id) not in items and isinstance(value, dict):
                items[str(item_id)] = copy.deepcopy(value)
    gear_tables = gear_catalog.tables_from_content(source)
    for item_id, merged in items.items():
        spec = gear_catalog.gear_spec_for_definition(item_id, gear_tables)
        if spec is not None:
            merged["gear"] = spec
    insertables = copy.deepcopy(gear_tables.get("insertables", {}))
    materials = copy.deepcopy(gear_tables.get("materials", {}))
    containers = starter_containers()
    source_containers = source.get("containers")
    if isinstance(source_containers, dict):
        for container_id, value in list(source_containers.items())[:MAX_WORLD_INSTANCES]:
            if isinstance(value, dict):
                containers[str(container_id)] = copy.deepcopy(value)
    source_tables = source.get("loot_tables")
    loot_tables = (
        copy.deepcopy(source_tables)
        if isinstance(source_tables, dict)
        else starter_loot_tables()
    )
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "items": items,
        "containers": containers,
        "insertables": insertables,
        "materials": materials,
        "gear": gear_tables,
        "loot_tables": loot_tables,
        "asset_table": gear_catalog.asset_table_for_definitions(
            items,
            containers,
            insertables,
            materials,
            tables=gear_tables,
        ),
        "limits": {
            "max_world_instances": MAX_WORLD_INSTANCES,
            "max_inventory_slots": MAX_INVENTORY_SLOTS,
            "max_container_items": MAX_CONTAINER_ITEMS,
            "max_equipped_items": MAX_EQUIPPED_ITEMS,
            "max_pocket_items": MAX_POCKET_ITEMS,
        },
        "policy": "DEFINITION_INSTANCE_CONTEXT_VISUAL_BOUNDED",
    }


def definition(catalog: dict[str, Any], definition_id: Any) -> dict[str, Any] | None:
    wanted = str(definition_id or "")
    for group_name in ("items", "containers", "insertables", "materials"):
        group = catalog.get(group_name, {})
        if isinstance(group, dict) and isinstance(group.get(wanted), dict):
            return group[wanted]
    return None


def catalog_summary(catalog: dict[str, Any]) -> dict[str, Any]:
    items = catalog.get("items", {})
    containers = catalog.get("containers", {})
    insertables = catalog.get("insertables", {})
    materials = catalog.get("materials", {})
    tables = catalog.get("loot_tables", {})
    assets = catalog.get("asset_table", {})
    return {
        "schema": str(catalog.get("schema", SCHEMA)),
        "version": _safe_int(catalog.get("version"), VERSION),
        "definitions": len(items) if isinstance(items, dict) else 0,
        "containers": len(containers) if isinstance(containers, dict) else 0,
        "insertables": len(insertables) if isinstance(insertables, dict) else 0,
        "materials": len(materials) if isinstance(materials, dict) else 0,
        "loot_tables": len(tables) if isinstance(tables, dict) else 0,
        "asset_rows": len(assets) if isinstance(assets, dict) else 0,
        "gear": gear_catalog.table_summary(catalog.get("gear", {})),
        "rarities": list(RARITIES),
        "policy": str(catalog.get("policy", "")),
    }


def _visual_context(location: Any) -> str:
    candidate = str(location or "INVENTORY").upper()
    return candidate if candidate in {"GROUND", "CONTAINER", "INVENTORY", "EQUIPPED", "POCKET"} else "INVENTORY"


def visual_for(
    catalog: dict[str, Any],
    definition_id: Any,
    location: Any,
    *,
    sim_time: float = 0.0,
    phase: float = 0.0,
) -> dict[str, Any]:
    """Return one context-specific visual binding with deterministic motion."""
    item = definition(catalog, definition_id) or {}
    visual = item.get("visual", {}) if isinstance(item, dict) else {}
    states = visual.get("states", {}) if isinstance(visual, dict) else {}
    context = _visual_context(location)
    state = states.get(context) if isinstance(states, dict) else None
    if not isinstance(state, dict) and isinstance(states, dict):
        state = states.get("INVENTORY") or states.get("GROUND")
    binding = copy.deepcopy(state) if isinstance(state, dict) else {
        "asset_id": str(item.get("asset_id", definition_id)),
        "renderer": "NATIVE_ASSET_KIT",
        "model": "#Sphere",
        "scale": [0.16, 0.16, 0.16],
        "rotation": [0.0, 0.0, 0.0],
        "offset_y": 0.16,
        "float_m": 0.0,
        "spin_deg_s": 0.0,
    }
    safe_phase = _safe_float(phase)
    safe_time = _safe_float(sim_time)
    binding["state"] = context
    binding["asset_id"] = str(binding.get("asset_id", item.get("asset_id", definition_id)))
    binding["base_color"] = rarity_style(item.get("rarity"))["color"]
    binding["bob_m"] = round(
        math.sin(safe_time * 1.7 + safe_phase) * _safe_float(binding.get("float_m")),
        4,
    )
    binding["rotation_y"] = round(
        _safe_float((binding.get("rotation") or [0.0, 0.0, 0.0])[1])
        + safe_time * _safe_float(binding.get("spin_deg_s")),
        3,
    )
    return binding


def make_instance(
    catalog: dict[str, Any],
    instance_id: Any,
    definition_id: Any,
    *,
    location: str = "INVENTORY",
    quantity: int = 1,
    owner_id: str = "player",
    container_id: str = "",
    equipped_slot: str = "",
    position: dict[str, Any] | None = None,
    visual_phase: float = 0.0,
) -> dict[str, Any]:
    item = definition(catalog, definition_id) or {}
    normalized_location = str(location or "INVENTORY").upper()
    if normalized_location not in LOCATIONS:
        normalized_location = "INVENTORY"
    stack_limit = max(1, _safe_int(item.get("stack_limit"), 1))
    safe_quantity = max(1, min(stack_limit, _safe_int(quantity, 1)))
    slot = str(equipped_slot or item.get("equip_slot", ""))
    owner = str(owner_id or "")
    if normalized_location in {"GROUND", "CONTAINER"}:
        owner = ""
    if normalized_location == "POCKET" and not owner:
        owner = "npc-unknown"
    if normalized_location == "EQUIPPED" and not slot:
        slot = "UTILITY"
    return {
        "instance_id": str(instance_id or "item-0000")[:64],
        "definition_id": str(definition_id or "item.unknown")[:96],
        "name": str(item.get("name", definition_id or "Unknown Item"))[:96],
        "kind": str(item.get("kind", "ITEM"))[:32],
        "rarity": normalize_rarity(item.get("rarity")),
        "rarity_color": rarity_style(item.get("rarity"))["color"],
        "level": max(1, _safe_int(item.get("level"), 1)),
        "quantity": safe_quantity,
        "location": normalized_location,
        "owner_id": owner[:64],
        "container_id": str(container_id or "")[:64],
        "equipped_slot": slot[:32],
        "condition": 1.0,
        "craft_quality": "STANDARD",
        "position": _safe_position(position),
        "visual_phase": safe_phase if (safe_phase := _safe_float(visual_phase)) else 0.0,
        "affixes": [],
        "enchantments": [],
        "gear": gear_catalog.new_gear_state(
            str(definition_id or ""),
            item.get("gear") if isinstance(item, dict) else None,
            catalog.get("gear") if isinstance(catalog.get("gear"), dict) else None,
        ),
        "container_state": "CLOSED" if str(item.get("kind")) == "CONTAINER" else "",
        "contents": [],
    }


def normalize_instance(catalog: dict[str, Any], raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not raw.get("instance_id"):
        return None
    result = make_instance(
        catalog,
        raw.get("instance_id"),
        raw.get("definition_id", raw.get("base_item_id", "item.island_compass")),
        location=str(raw.get("location", "INVENTORY")),
        quantity=_safe_int(raw.get("quantity"), 1),
        owner_id=str(raw.get("owner_id", "player")),
        container_id=str(raw.get("container_id", "")),
        equipped_slot=str(raw.get("equipped_slot", "")),
        position=raw.get("position"),
        visual_phase=_safe_float(raw.get("visual_phase")),
    )
    for key in (
        "seed",
        "base_item_id",
        "roll_table_id",
        "roll",
        "origin",
        "craft_quality",
    ):
        if key in raw:
            if key == "craft_quality":
                quality = str(raw.get(key, "STANDARD")).upper()
                result[key] = quality if quality in gear_catalog.QUALITY_LADDER else "STANDARD"
            elif key in {"seed", "roll"}:
                result[key] = _safe_int(raw.get(key))
            else:
                result[key] = str(raw.get(key, ""))[:96]
    for key in ("affixes", "enchantments", "contents"):
        value = raw.get(key)
        if isinstance(value, list):
            result[key] = copy.deepcopy(value[:MAX_CONTAINER_ITEMS if key == "contents" else 2])
    if isinstance(raw.get("gear"), dict) or result.get("gear") is not None:
        result["gear"] = gear_catalog.normalize_gear(
            raw.get("gear"),
            result.get("definition_id"),
            catalog.get("gear") if isinstance(catalog.get("gear"), dict) else None,
        )
    if str(result.get("kind")) == "CONTAINER":
        result["container_state"] = str(raw.get("container_state", "CLOSED")).upper()
    return result


def transition_instance(
    instance: dict[str, Any],
    location: str,
    *,
    owner_id: str | None = None,
    container_id: str | None = None,
    equipped_slot: str | None = None,
    position: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any]]:
    if not isinstance(instance, dict) or not instance.get("instance_id"):
        return False, {"error": "ITEM_INSTANCE_REQUIRED"}
    destination = str(location or "").upper()
    if destination not in LOCATIONS:
        return False, {"error": "ITEM_LOCATION_INVALID", "allowed": list(LOCATIONS)}
    if destination == "CONTAINER" and not str(container_id or instance.get("container_id", "")):
        return False, {"error": "ITEM_CONTAINER_REQUIRED"}
    if destination == "EQUIPPED" and not str(equipped_slot or instance.get("equipped_slot", "")):
        return False, {"error": "ITEM_EQUIP_SLOT_REQUIRED"}
    instance["location"] = destination
    if owner_id is not None:
        instance["owner_id"] = str(owner_id)[:64]
    if container_id is not None:
        instance["container_id"] = str(container_id)[:64]
    if equipped_slot is not None:
        instance["equipped_slot"] = str(equipped_slot)[:32]
    if position is not None:
        instance["position"] = _safe_position(position)
    if destination in {"GROUND", "CONTAINER"}:
        instance["owner_id"] = ""
    if destination != "CONTAINER":
        instance["container_id"] = ""
    if destination != "EQUIPPED":
        instance["equipped_slot"] = ""
    return True, {
        "instance_id": str(instance["instance_id"]),
        "location": destination,
        "owner_id": str(instance.get("owner_id", "")),
        "container_id": str(instance.get("container_id", "")),
        "equipped_slot": str(instance.get("equipped_slot", "")),
    }


def instance_view(
    catalog: dict[str, Any],
    instance: dict[str, Any],
    *,
    sim_time: float = 0.0,
    include_visual: bool = True,
) -> dict[str, Any]:
    result = {
        "instance_id": str(instance.get("instance_id", "")),
        "definition_id": str(instance.get("definition_id", "")),
        "name": str(instance.get("name", "Unknown Item")),
        "kind": str(instance.get("kind", "ITEM")),
        "rarity": normalize_rarity(instance.get("rarity")),
        "rarity_color": str(instance.get("rarity_color", rarity_style(instance.get("rarity"))["color"])),
        "level": max(1, _safe_int(instance.get("level"), 1)),
        "quantity": max(1, _safe_int(instance.get("quantity"), 1)),
        "location": str(instance.get("location", "INVENTORY")),
        "owner_id": str(instance.get("owner_id", "")),
        "container_id": str(instance.get("container_id", "")),
        "equipped_slot": str(instance.get("equipped_slot", "")),
        "condition": round(max(0.0, min(1.0, _safe_float(instance.get("condition"), 1.0))), 3),
        "craft_quality": str(instance.get("craft_quality", "STANDARD"))[:16].upper(),
        "position": _safe_position(instance.get("position")),
        "affixes": copy.deepcopy(instance.get("affixes", [])[:2]) if isinstance(instance.get("affixes"), list) else [],
        "enchantments": copy.deepcopy(instance.get("enchantments", [])[:2]) if isinstance(instance.get("enchantments"), list) else [],
        "gear": gear_catalog.gear_view(instance.get("gear")),
        "attachment": assets_catalog.attachment_for_slot(
            instance.get("equipped_slot")
            or (definition(catalog, instance.get("definition_id")) or {}).get("equip_slot")
        ),
    }
    for key in ("seed", "base_item_id", "roll_table_id", "roll", "origin"):
        if key in instance:
            result[key] = (
                _safe_int(instance.get(key))
                if key in {"seed", "roll"}
                else str(instance.get(key, ""))[:96]
            )
    if result["kind"] == "CONTAINER":
        result["container_state"] = str(instance.get("container_state", "CLOSED"))
        result["contents"] = list(instance.get("contents", []))[:MAX_CONTAINER_ITEMS]
    if include_visual:
        result["visual"] = visual_for(
            catalog,
            instance.get("definition_id"),
            instance.get("location"),
            sim_time=sim_time,
            phase=_safe_float(instance.get("visual_phase")),
        )
        result["visual"].update(
            tint_variant_for(
                result.get("rarity"),
                result.get("craft_quality"),
                _palette_for_definition(
                    catalog,
                    result.get("definition_id"),
                    result.get("craft_quality"),
                    result.get("location"),
                ),
            )
        )
        result["visual"]["attachment"] = copy.deepcopy(result["attachment"])
        result["visual"]["state"] = str(result.get("location") or "INVENTORY")
    return result


def starter_instances(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Seed a small but visibly stateful world without adding entity-pool cost."""
    rows = [
        make_instance(
            catalog,
            "starter-iron-saber",
            "item.iron_saber",
            location="EQUIPPED",
            owner_id="player",
            equipped_slot="MAIN_HAND",
            visual_phase=0.4,
        ),
        make_instance(
            catalog,
            "starter-island-compass",
            "item.island_compass",
            location="EQUIPPED",
            owner_id="player",
            equipped_slot="OFF_HAND",
            visual_phase=1.1,
        ),
        make_instance(
            catalog,
            "starter-drift-cloak",
            "item.drift_cloak",
            location="EQUIPPED",
            owner_id="player",
            equipped_slot="BACK",
            visual_phase=0.7,
        ),
        make_instance(
            catalog,
            "starter-saltpath-boots",
            "item.saltpath_boots",
            location="EQUIPPED",
            owner_id="player",
            equipped_slot="FEET",
            visual_phase=1.6,
        ),
        make_instance(catalog, "starter-sea-salt", "item.sea_salt", quantity=1),
        make_instance(catalog, "starter-sun-herb", "item.sun_herb", quantity=2),
        make_instance(catalog, "starter-rune-tir", "rune.tir", quantity=1),
        make_instance(catalog, "starter-rune-ort", "rune.ort", quantity=1),
        make_instance(catalog, "starter-rune-tal", "rune.tal", quantity=1),
        make_instance(catalog, "starter-gem-ruby", "gem.ruby", quantity=1),
        make_instance(catalog, "starter-material-fiber", "material.fiber", quantity=6),
        make_instance(catalog, "starter-material-wood", "material.wood", quantity=3),
        make_instance(catalog, "starter-material-flint", "material.flint", quantity=2),
        make_instance(catalog, "starter-material-iron-ore", "material.iron_ore", quantity=6),
        make_instance(catalog, "starter-material-hide", "material.hide", quantity=4),
        make_instance(catalog, "starter-material-fresh-water", "material.fresh_water", quantity=2),
        make_instance(catalog, "starter-material-resin", "material.resin", quantity=2),
        make_instance(
            catalog,
            "ground-iron-saber-01",
            "item.iron_saber",
            location="GROUND",
            position={"x": 1.8, "y": 0.0, "z": -1.35},
            visual_phase=0.8,
        ),
        make_instance(
            catalog,
            "ground-moon-shard-01",
            "item.moon_shard",
            location="GROUND",
            position={"x": -2.45, "y": 0.0, "z": -1.55},
            visual_phase=2.4,
        ),
        make_instance(
            catalog,
            "ground-old-boot-01",
            "item.old_boot",
            location="GROUND",
            position={"x": -1.7, "y": 0.0, "z": 1.9},
            visual_phase=4.2,
        ),
        make_instance(
            catalog,
            "container-supply-crate-01",
            "container.supply_crate",
            location="GROUND",
            position={"x": 2.75, "y": 0.0, "z": 1.35},
            visual_phase=0.0,
        ),
        make_instance(
            catalog,
            "crate-tideguard-jacket-01",
            "item.tideguard_jacket",
            location="CONTAINER",
            container_id="container-supply-crate-01",
            visual_phase=0.2,
        ),
        make_instance(
            catalog,
            "crate-sunken-crown-01",
            "item.sunken_crown",
            location="CONTAINER",
            container_id="container-supply-crate-01",
            visual_phase=1.7,
        ),
        make_instance(
            catalog,
            "npc-pocket-totem-01",
            "item.goblin_totem",
            location="POCKET",
            owner_id="npc-wanderer-01",
            visual_phase=3.5,
        ),
    ]
    container = next(row for row in rows if row["instance_id"] == "container-supply-crate-01")
    container["contents"] = [
        row["instance_id"]
        for row in rows
        if row.get("container_id") == container["instance_id"]
    ][:MAX_CONTAINER_ITEMS]
    return rows


def inventory_counts(instances: Iterable[dict[str, Any]], owner_id: str = "player") -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in instances:
        if not isinstance(row, dict):
            continue
        if str(row.get("owner_id", "")) != str(owner_id):
            continue
        if str(row.get("location", "")) not in PLAYER_OWNED_LOCATIONS:
            continue
        definition_id = str(row.get("definition_id", ""))
        if not definition_id:
            continue
        counts[definition_id] = counts.get(definition_id, 0) + max(1, _safe_int(row.get("quantity"), 1))
    return counts


def roll_loot(catalog: dict[str, Any], seed: int, table_id: str = "loot.coastal_cache") -> dict[str, Any]:
    """Roll one weighted entry with no global RNG or allocation-heavy state."""
    tables = catalog.get("loot_tables", {})
    table = tables.get(str(table_id)) if isinstance(tables, dict) else None
    entries = table.get("entries", []) if isinstance(table, dict) else []
    safe_entries = [row for row in entries if isinstance(row, dict) and definition(catalog, row.get("item_id"))]
    if not safe_entries:
        return {"table_id": str(table_id), "item_id": "item.island_compass", "quantity": 1, "roll": 0}
    state = _safe_int(seed, 1) & 0xFFFFFFFF or 1

    def next_u32() -> int:
        nonlocal state
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= (state >> 17) & 0xFFFFFFFF
        state ^= (state << 5) & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        return state

    weights = [max(1, _safe_int(row.get("weight"), 1)) for row in safe_entries]
    total = sum(weights)
    roll = next_u32() % total
    selected = safe_entries[-1]
    for row, weight in zip(safe_entries, weights):
        if roll < weight:
            selected = row
            break
        roll -= weight
    low = max(1, _safe_int(selected.get("min"), 1))
    high = max(low, _safe_int(selected.get("max"), low))
    quantity = low + (next_u32() % (high - low + 1))
    return {
        "table_id": str(table_id),
        "item_id": str(selected.get("item_id")),
        "quantity": quantity,
        "roll": int(roll),
    }


def item_definition_summaries(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for group_name in ("items", "insertables", "materials", "containers"):
        group = catalog.get(group_name, {})
        if not isinstance(group, dict):
            continue
        for item_id, row in group.items():
            if not isinstance(row, dict):
                continue
            gear = row.get("gear") if isinstance(row.get("gear"), dict) else {}
            summaries.append(
                {
                    "id": str(item_id),
                    "name": str(row.get("name", item_id)),
                    "kind": str(row.get("kind", "ITEM")),
                    "rarity": normalize_rarity(row.get("rarity")),
                    "equip_slot": str(row.get("equip_slot", gear.get("slot", ""))),
                    "asset_id": str(row.get("asset_id", "")),
                    "socketable": bool(gear.get("max_sockets", 0)),
                    "socket_capacity": max(0, _safe_int(gear.get("max_sockets"), 0)),
                }
            )
    return summaries[:MAX_WORLD_INSTANCES]


def build_state_view(
    catalog: dict[str, Any],
    instances: Iterable[dict[str, Any]],
    *,
    player_x: float = 0.0,
    player_z: float = 0.0,
    sim_time: float = 0.0,
    last_interaction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = [row for row in instances if isinstance(row, dict)]
    views = [instance_view(catalog, row, sim_time=sim_time) for row in rows]
    by_id = {str(row.get("instance_id")): row for row in views}
    ground = [row for row in views if row.get("location") == "GROUND"]
    containers = [row for row in ground if row.get("kind") == "CONTAINER"]
    for container in containers:
        contents = []
        for child in views:
            if child.get("container_id") == container.get("instance_id"):
                contents.append(child)
        container["contents"] = contents[:MAX_CONTAINER_ITEMS]
    inventory = [
        row for row in views
        if row.get("location") == "INVENTORY" and row.get("owner_id") == "player"
    ][:MAX_INVENTORY_SLOTS]
    equipment = [
        row for row in views
        if row.get("location") == "EQUIPPED" and row.get("owner_id") == "player"
    ][:MAX_EQUIPPED_ITEMS]
    pockets = [row for row in views if row.get("location") == "POCKET"][:MAX_POCKET_ITEMS]
    by_location: dict[str, int] = {}
    by_rarity: dict[str, int] = {}
    for row in views:
        location = str(row.get("location", "UNKNOWN"))
        by_location[location] = by_location.get(location, 0) + 1
        rarity = normalize_rarity(row.get("rarity"))
        by_rarity[rarity] = by_rarity.get(rarity, 0) + 1

    target: dict[str, Any] | None = None
    best_distance = float("inf")
    for row in ground:
        position = row.get("position", {})
        distance = math.hypot(
            _safe_float(position.get("x")) - _safe_float(player_x),
            _safe_float(position.get("z")) - _safe_float(player_z),
        )
        if distance > INTERACTION_RADIUS_M:
            continue
        if distance > best_distance or (
            abs(distance - best_distance) <= 0.0001
            and target is not None
            and str(row.get("instance_id")) >= str(target.get("instance_id"))
        ):
            continue
        target = {
            "instance_id": row.get("instance_id"),
            "name": row.get("name"),
            "kind": row.get("kind"),
            "rarity": row.get("rarity"),
            "distance_m": round(distance, 3),
            "action": "OPEN" if row.get("kind") == "CONTAINER" and row.get("container_state") == "CLOSED" else (
                "LOOT" if row.get("kind") == "CONTAINER" else "PICKUP"
            ),
        }
        best_distance = distance

    return {
        "schema": SCHEMA,
        "version": VERSION,
        "catalog": catalog_summary(catalog),
        "definitions": item_definition_summaries(catalog),
        "limits": copy.deepcopy(catalog.get("limits", {})),
        "instances": len(views),
        "counts": {
            "by_location": by_location,
            "by_rarity": by_rarity,
            "player_owned": sum(1 for row in views if row.get("owner_id") == "player"),
        },
        "ground": ground,
        "containers": containers,
        "inventory": inventory,
        "equipment": equipment,
        "pockets": pockets,
        "interaction_target": target,
        "last_interaction": copy.deepcopy(last_interaction or {}),
        "instance_index": {key: {"location": value.get("location"), "kind": value.get("kind")} for key, value in by_id.items()},
    }


def render_binding(catalog: dict[str, Any], instance: dict[str, Any], *, sim_time: float = 0.0) -> dict[str, Any]:
    result = instance_view(catalog, instance, sim_time=sim_time, include_visual=True)
    result["render_role"] = "CONTAINER" if result.get("kind") == "CONTAINER" else "WORLD_ITEM"
    return result
