from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def main() -> int:
    from backend.game_engine_host import GameEngineRuntime

    runtime = GameEngineRuntime()
    try:
        initial = runtime.snapshot()
        assert initial["schema"] == "gg.game-engine.runtime.v1"
        assert initial["state"] == "IDLE"
        assert initial["simulation"]["active_entities"] == 33
        assert initial["simulation"]["fixed_hz"] == 60

        runtime.set_input(json.dumps({"throttle": 1, "steer": 0.4, "boost": True}))
        runtime.start()
        time.sleep(0.08)
        running = runtime.snapshot()
        assert running["state"] == "RUNNING"
        assert running["simulation"]["tick"] > 0
        assert running["player"]["boost"] is True

        burst = runtime.burst()
        assert burst["simulation"]["active_particles"] >= 48

        runtime.pause()
        runtime.start_recording()
        runtime.set_input(json.dumps({"throttle": 0.6, "steer": -0.2}))
        runtime.start()
        time.sleep(0.08)
        recorded = runtime.stop_recording()
        assert recorded["replay"]["recorded_inputs"] > 0

        replay = runtime.play_replay()
        assert replay["replay"]["replaying"] is True
        time.sleep(0.04)
        assert runtime.snapshot()["simulation"]["tick"] > 0

        stressed = runtime.set_stress(True)
        assert stressed["stress"] is True
        assert stressed["simulation"]["active_entities"] > 400
        assert stressed["simulation"]["active_entities"] <= 2048

        runtime.reset()
        runtime.step()
        stepped = runtime.snapshot()
        assert stepped["simulation"]["tick"] == 1
        assert stepped["state"] == "PAUSED"
    finally:
        runtime.shutdown()

    print("GAME_ENGINE_HOST_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
