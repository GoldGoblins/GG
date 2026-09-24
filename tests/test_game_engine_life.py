"""Regression tests for bounded schedules and ambient player stimuli."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def main() -> int:
    from backend import game_engine_life as life

    spawns = life.spawns_from_content({"ambient_life": life.starter_spawns()})
    assert len(spawns) == 4
    assert len({row["id"] for row in spawns}) == 4
    assert life.world_clock(0)["phase"] == "DAWN"
    assert life.world_clock(105)["phase"] == "NIGHT"
    assert life.world_clock(120)["day"] == 2

    first = life.proxy_rows(spawns, 0.0, player_x=100.0, player_z=100.0)
    second = life.proxy_rows(spawns, 0.0, player_x=100.0, player_z=100.0)
    assert first == second
    assert all(row["kind"] == "ACTOR" for row in first)
    assert all(
        row["animation"]["schema"] == "gg.game-engine.animation.v1"
        for row in first
    )
    assert {row["life"]["activity"] for row in first} == {
        "FISHING",
        "TRAVELING",
        "SCOUTING",
        "HAULING",
    }

    noticed = life.proxy_rows(spawns, 0.0, player_x=-4.4, player_z=-4.6)
    fisher = next(row for row in noticed if row["id"] == "ambient-fisher-01")
    assert fisher["life"]["activity"] == "NOTICE_PLAYER"
    assert fisher["life"]["stimulus"] == "PLAYER_NEAR"
    assert fisher["speed"] == 0.0

    night = life.proxy_rows(spawns, 110.0)
    assert all(row["life"]["activity"] == "RESTING" for row in night)
    assert all(row["motion_state"] == "IDLE" for row in night)
    view = life.build_view(night, 110.0)
    assert view["population"] == 4
    assert view["activities"] == {"RESTING": 4}
    assert view["clock"]["phase"] == "NIGHT"

    print("GAME_ENGINE_LIFE_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
