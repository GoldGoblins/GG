"""Regression for the presentation-only rich 3D to DOS fallback seam."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def main() -> int:
    from backend import game_engine_fallback as fallback
    from backend import game_engine_render as render
    from backend.game_engine_host import GameEngineRuntime

    rich = render.presentation_view(render.RICH_3D)
    assert rich["mode"] == render.RICH_3D
    assert rich["rich_3d"] is True
    assert rich["fallback_available"] is True
    assert rich["simulation_unchanged"] is True
    assert render.normalize_presentation_mode("dos_2d") == render.DOS_2D
    assert render.normalize_presentation_mode("invalid", "") == ""

    view = fallback.build_view(
        [{"id": "e-0000", "kind": "PLAYER", "x": 0, "z": 0}],
        [{"key": "0:0:0", "center_m": {"x": 0, "z": 0}, "surface": "LAND"}],
        state="RUNNING",
        tick=12,
        active_entities=1,
        active_particles=0,
    )
    assert view["schema"] == fallback.SCHEMA
    assert view["mode"] == "DOS_2D"
    assert view["entities"][0]["glyph"] == "@"
    assert view["terrain"][0]["glyph"] == ","
    assert view["shared_contract"].startswith("AUTHORITATIVE_")

    runtime = GameEngineRuntime()
    try:
        initial = runtime.snapshot()
        state_fields = ("simulation", "player", "items", "people", "gear")
        baseline = {
            key: json.dumps(initial[key], sort_keys=True)
            for key in state_fields
        }

        dos = runtime.set_presentation_mode("DOS_2D")
        assert dos["render"]["presentation"]["mode"] == "DOS_2D"
        assert dos["render"]["presentation"]["reason"] == "MANUAL_DOS_MODE"
        assert dos["render"]["draw_calls"] == 0
        assert dos["render"]["fallback"]["schema"] == fallback.SCHEMA
        assert len(dos["render"]["fallback"]["entities"]) == 47
        assert any(
            line.startswith("GEAR ")
            for line in dos["render"]["fallback"]["terminal"]["lines"]
        )
        player = next(
            row
            for row in dos["render"]["fallback"]["entities"]
            if row["kind"] == "PLAYER"
        )
        assert {row["slot"] for row in player["equipment"]} == {
            "MAIN_HAND",
            "OFF_HAND",
            "BACK",
            "FEET",
        }
        for key in state_fields:
            assert json.dumps(dos[key], sort_keys=True) == baseline[key], key

        failed = runtime.report_graphics_failure("GPU_CONTEXT_LOST")
        assert failed["render"]["presentation"]["mode"] == "DOS_2D"
        assert failed["render"]["presentation"]["reason"] == "GPU_CONTEXT_LOST"
        restored = runtime.set_presentation_mode("RICH_3D")
        assert restored["render"]["presentation"]["mode"] == "RICH_3D"
        assert restored["render"]["presentation"]["reason"] == "NONE"
        assert restored["render"]["draw_calls"] == 3
    finally:
        runtime.shutdown()

    print("GAME_ENGINE_FALLBACK_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
