"""Offline-first MMO and persistence seams for the GAME ENGINE preview."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


SCHEMA = "gg.game-engine.mmo.v1"
PERSISTENCE_SCHEMA = "gg.game-engine.persistence.memory.v1"


class MemoryStateStore:
    """A deterministic persistence seam with no filesystem or account access."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}
        self._revision = 0

    def save(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._revision += 1
        safe_key = str(key or "local-player")[:96]
        self._rows[safe_key] = deepcopy(payload)
        encoded = json.dumps(self._rows[safe_key], separators=(",", ":"))
        return {
            "schema": PERSISTENCE_SCHEMA,
            "key": safe_key,
            "revision": self._revision,
            "bytes": len(encoded.encode("utf-8")),
            "mode": "MEMORY_ONLY",
        }

    def load(self, key: str) -> dict[str, Any] | None:
        return deepcopy(self._rows.get(str(key or "local-player")[:96]))

    def clear(self) -> None:
        self._rows.clear()
        self._revision = 0

    @property
    def revision(self) -> int:
        return self._revision


def build_network_view(
    world_view: dict[str, Any],
    *,
    sequence: int,
    active_entities: int,
    snapshot_hz: int = 20,
    persistence_revision: int = 0,
) -> dict[str, Any]:
    cells = world_view.get("streaming", {}).get("loaded_cells", [])
    return {
        "schema": SCHEMA,
        "mode": "LOCAL_LOOPBACK",
        "transport": "NOT_CONNECTED",
        "authoritative_server": False,
        "prediction": "CLIENT_FIXED_STEP_LOCAL",
        "snapshot_hz": max(1, min(60, int(snapshot_hz))),
        "sequence": max(0, int(sequence)),
        "interest": {
            "policy": "CELL_INTEREST_WITH_ENTITY_CAP",
            "cell_count": len(cells) if isinstance(cells, list) else 0,
            "entity_cap": 128,
            "active_entities": max(0, int(active_entities)),
        },
        "replication": {
            "fields": ["position", "velocity", "movement_mode", "ability_events", "loot_events"],
            "compression": "QUANTIZED_CELL_RELATIVE_OPTIONAL",
            "reconciliation": "SEQUENCE_NUMBER_SEAM",
        },
        "persistence": {
            "schema": PERSISTENCE_SCHEMA,
            "mode": "MEMORY_ONLY",
            "revision": max(0, int(persistence_revision)),
            "filesystem": "NOT_CONNECTED",
            "accounts": "NOT_CONNECTED",
        },
        "estimated_bytes": 96 + min(max(0, int(active_entities)), 128) * 12,
        "interest_entities": min(max(0, int(active_entities)), 128),
    }


def persistent_payload(
    *,
    player: dict[str, Any],
    movement_mode: str,
    inventory: dict[str, int],
    loot_items: list[dict[str, Any]],
    progression: dict[str, Any],
    editor_document: dict[str, Any],
    terrain_overrides: dict[str, Any] | None = None,
    keybindings: dict[str, Any] | None = None,
    addons: dict[str, Any] | None = None,
    item_instances: list[dict[str, Any]] | None = None,
    profession_state: dict[str, Any] | None = None,
    npc_individuals: dict[str, Any] | None = None,
    event_journal: dict[str, Any] | None = None,
    trade_state: dict[str, Any] | None = None,
    economy_state: dict[str, Any] | None = None,
    combat_state: dict[str, Any] | None = None,
    quest_state: dict[str, Any] | None = None,
    faction_state: dict[str, Any] | None = None,
    dialogue_state: dict[str, Any] | None = None,
    social_state: dict[str, Any] | None = None,
    living_world_state: dict[str, Any] | None = None,
    world_event_state: dict[str, Any] | None = None,
    content_state: dict[str, Any] | None = None,
    simulation_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": PERSISTENCE_SCHEMA,
        "version": 1,
        "player": deepcopy(player),
        "movement_mode": str(movement_mode),
        "inventory": deepcopy(inventory),
        "loot_items": deepcopy(loot_items[-64:]),
        "progression": deepcopy(progression),
        "editor": deepcopy(editor_document),
        "terrain_overrides": deepcopy(terrain_overrides or {}),
        "keybindings": deepcopy(keybindings or {}),
        "addons": deepcopy(addons or {}),
        "item_instances": deepcopy((item_instances or [])[-96:]),
        "profession_state": deepcopy(profession_state or {}),
        "npc_individuals": deepcopy(npc_individuals or {}),
        "event_journal": deepcopy(event_journal or {}),
        "trade_state": deepcopy(trade_state or {}),
        "economy_state": deepcopy(economy_state or {}),
        "combat_state": deepcopy(combat_state or {}),
        "quest_state": deepcopy(quest_state or {}),
        "faction_state": deepcopy(faction_state or {}),
        "dialogue_state": deepcopy(dialogue_state or {}),
        "social_state": deepcopy(social_state or {}),
        "living_world_state": deepcopy(living_world_state or {}),
        "world_event_state": deepcopy(world_event_state or {}),
        "content_state": deepcopy(content_state or {}),
        "simulation": deepcopy(simulation_state or {}),
    }
