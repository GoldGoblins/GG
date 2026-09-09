"""Small, deterministic GAME ENGINE runtime for the desktop preview.

This is deliberately a playable vertical slice rather than a pretend MMO
server.  The simulation uses fixed steps, bounded pools and a spatial grid;
the QML surface only observes a compact render snapshot.  That keeps the
editor responsive and gives us a measurable foundation for a later native
runtime without importing a large engine or any proprietary game assets.
"""

from __future__ import annotations

import json
import math
import threading
import time
from typing import Any


SCHEMA = "gg.game-engine.runtime.v1"
FIXED_HZ = 60
FIXED_DT = 1.0 / FIXED_HZ
MAX_CATCH_UP_STEPS = 4
MAX_ENTITIES = 2048
MAX_PARTICLES = 4096
MAX_CHUNKS = 64
RENDER_ENTITY_LIMIT = 96
RENDER_PARTICLE_LIMIT = 128
MAX_REPLAY_INPUTS = 1800
CHUNK_SIZE = 16.0


def _clamp(value: Any, low: float, high: float, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(low, min(high, number))


def _round(value: float, places: int = 3) -> float:
    return round(float(value), places)


class GameEngineRuntime:
    """Threaded local simulation with bounded, inspectable state."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._stress = False
        self._recording = False
        self._replaying = False
        self._replay_inputs: list[dict[str, Any]] = []
        self._replay_index = 0
        self._recorded_inputs: list[dict[str, Any]] = []
        self._input = self._default_input()
        self._tick = 0
        self._sim_time = 0.0
        self._last_tick_ms = 0.0
        self._max_tick_ms = 0.0
        self._network_seq = 0
        self._collision_cooldown = 0.0
        self._particle_cursor = 0
        self._events: list[dict[str, Any]] = []
        self._entity_count = 0
        self._particle_count = 0
        self._alive: list[bool] = []
        self._kind: list[str] = []
        self._color: list[str] = []
        self._x: list[float] = []
        self._y: list[float] = []
        self._z: list[float] = []
        self._vx: list[float] = []
        self._vy: list[float] = []
        self._vz: list[float] = []
        self._yaw: list[float] = []
        self._sx: list[float] = []
        self._sy: list[float] = []
        self._sz: list[float] = []
        self._radius: list[float] = []
        self._static: list[bool] = []
        self._plife: list[float] = []
        self._px: list[float] = []
        self._py: list[float] = []
        self._pz: list[float] = []
        self._pvx: list[float] = []
        self._pvy: list[float] = []
        self._pvz: list[float] = []
        self._pcolor: list[str] = []
        self._reset_world_locked()

    @staticmethod
    def _default_input() -> dict[str, Any]:
        return {
            "throttle": 0.0,
            "steer": 0.0,
            "brake": 0.0,
            "boost": False,
        }

    def _reset_arrays_locked(self) -> None:
        self._alive = [False] * MAX_ENTITIES
        self._kind = [""] * MAX_ENTITIES
        self._color = ["#8db89a"] * MAX_ENTITIES
        self._x = [0.0] * MAX_ENTITIES
        self._y = [0.0] * MAX_ENTITIES
        self._z = [0.0] * MAX_ENTITIES
        self._vx = [0.0] * MAX_ENTITIES
        self._vy = [0.0] * MAX_ENTITIES
        self._vz = [0.0] * MAX_ENTITIES
        self._yaw = [0.0] * MAX_ENTITIES
        self._sx = [1.0] * MAX_ENTITIES
        self._sy = [1.0] * MAX_ENTITIES
        self._sz = [1.0] * MAX_ENTITIES
        self._radius = [0.5] * MAX_ENTITIES
        self._static = [True] * MAX_ENTITIES
        self._plife = [0.0] * MAX_PARTICLES
        self._px = [0.0] * MAX_PARTICLES
        self._py = [0.0] * MAX_PARTICLES
        self._pz = [0.0] * MAX_PARTICLES
        self._pvx = [0.0] * MAX_PARTICLES
        self._pvy = [0.0] * MAX_PARTICLES
        self._pvz = [0.0] * MAX_PARTICLES
        self._pcolor = ["#c8a97e"] * MAX_PARTICLES

    def _free_entity_locked(self) -> int | None:
        for index in range(1, MAX_ENTITIES):
            if not self._alive[index]:
                return index
        return None

    def _spawn_entity_locked(
        self,
        kind: str,
        x: float,
        y: float,
        z: float,
        scale: tuple[float, float, float],
        color: str,
        radius: float,
        *,
        static: bool = True,
        index: int | None = None,
    ) -> int | None:
        slot = index if index is not None else self._free_entity_locked()
        if slot is None or slot < 0 or slot >= MAX_ENTITIES:
            return None
        if self._alive[slot]:
            return None
        self._alive[slot] = True
        self._kind[slot] = str(kind)
        self._color[slot] = str(color)
        self._x[slot] = float(x)
        self._y[slot] = float(y)
        self._z[slot] = float(z)
        self._vx[slot] = 0.0
        self._vy[slot] = 0.0
        self._vz[slot] = 0.0
        self._yaw[slot] = 0.0
        self._sx[slot], self._sy[slot], self._sz[slot] = scale
        self._radius[slot] = float(radius)
        self._static[slot] = bool(static)
        self._entity_count += 1
        return slot

    def _reset_world_locked(self) -> None:
        self._reset_arrays_locked()
        self._entity_count = 0
        self._particle_count = 0
        self._particle_cursor = 0
        self._collision_cooldown = 0.0
        self._tick = 0
        self._sim_time = 0.0
        self._network_seq = 0
        self._events = []
        self._input = self._default_input()

        self._spawn_entity_locked(
            "PLAYER",
            0.0,
            0.65,
            0.0,
            (1.0, 0.45, 1.65),
            "#d4a85a",
            1.1,
            static=False,
            index=0,
        )
        for index in range(1, 33):
            angle = index * 0.91
            radius = 7.0 + float(index % 5) * 2.1
            kind = "RAMP" if index % 9 == 0 else "PROP"
            height = 1.2 if kind == "RAMP" else 0.8 + (index % 3) * 0.25
            scale = (
                1.5 if kind == "RAMP" else 0.7 + (index % 2) * 0.25,
                height,
                2.2 if kind == "RAMP" else 0.7 + (index % 4) * 0.15,
            )
            self._spawn_entity_locked(
                kind,
                math.sin(angle) * radius,
                scale[1],
                math.cos(angle) * radius,
                scale,
                "#6aa8c8" if kind == "RAMP" else "#8fa8a0",
                1.2 if kind == "RAMP" else 0.8,
            )

        if self._stress:
            for index in range(32, 480):
                angle = index * 0.37
                radius = 12.0 + float(index % 23) * 0.42
                scale = (
                    0.18 + (index % 3) * 0.04,
                    0.18 + (index % 4) * 0.03,
                    0.18 + (index % 2) * 0.05,
                )
                self._spawn_entity_locked(
                    "STRESS_PROP",
                    math.sin(angle) * radius,
                    scale[1],
                    math.cos(angle) * radius,
                    scale,
                    "#b6a6c8" if index % 2 else "#c98989",
                    0.25,
                )

        self._events.append(
            {
                "tick": 0,
                "kind": "WORLD_RESET",
                "text": "Scene rebuilt from deterministic seed.",
            }
        )

    def _append_event_locked(self, kind: str, text: str) -> None:
        self._events.append(
            {
                "tick": int(self._tick),
                "kind": str(kind),
                "text": str(text),
            }
        )
        self._events = self._events[-24:]

    def _spawn_particle_locked(
        self,
        x: float,
        y: float,
        z: float,
        vx: float,
        vy: float,
        vz: float,
        life: float,
        color: str,
    ) -> None:
        slot = None
        for offset in range(MAX_PARTICLES):
            candidate = (self._particle_cursor + offset) % MAX_PARTICLES
            if self._plife[candidate] <= 0.0:
                slot = candidate
                break
        if slot is None:
            slot = self._particle_cursor
        else:
            self._particle_count += 1
        self._particle_cursor = (slot + 1) % MAX_PARTICLES
        self._plife[slot] = float(life)
        self._px[slot] = float(x)
        self._py[slot] = float(y)
        self._pz[slot] = float(z)
        self._pvx[slot] = float(vx)
        self._pvy[slot] = float(vy)
        self._pvz[slot] = float(vz)
        self._pcolor[slot] = str(color)

    def _burst_locked(self, x: float, y: float, z: float, count: int = 32) -> None:
        count = max(1, min(96, int(count)))
        for index in range(count):
            phase = (index / float(count)) * math.tau
            speed = 3.5 + float(index % 7) * 0.55
            self._spawn_particle_locked(
                x,
                y,
                z,
                math.cos(phase) * speed,
                3.0 + float(index % 5) * 0.7,
                math.sin(phase) * speed,
                0.55 + float(index % 4) * 0.11,
                "#c8a97e" if index % 3 else "#c98989",
            )
        self._append_event_locked("PARTICLE_BURST", f"{count} pooled debris particles emitted.")

    def _set_replay_input_locked(self) -> None:
        if not self._replaying:
            return
        if self._replay_index >= len(self._replay_inputs):
            self._replaying = False
            self._running = False
            self._append_event_locked("REPLAY_DONE", "Deterministic replay reached its end.")
            return
        row = self._replay_inputs[self._replay_index]
        self._replay_index += 1
        self._input = {
            "throttle": _clamp(row.get("throttle"), -1.0, 1.0),
            "steer": _clamp(row.get("steer"), -1.0, 1.0),
            "brake": _clamp(row.get("brake"), 0.0, 1.0),
            "boost": bool(row.get("boost")),
        }

    def _build_spatial_grid_locked(self) -> dict[tuple[int, int], list[int]]:
        grid: dict[tuple[int, int], list[int]] = {}
        for index in range(1, MAX_ENTITIES):
            if not self._alive[index] or not self._static[index]:
                continue
            cell = (
                math.floor(self._x[index] / 2.0),
                math.floor(self._z[index] / 2.0),
            )
            grid.setdefault(cell, []).append(index)
        return grid

    def _tick_locked(self, dt: float) -> None:
        started = time.perf_counter()
        self._set_replay_input_locked()
        if self._replaying is False and self._running is False:
            return
        self._tick += 1
        self._sim_time += dt
        self._collision_cooldown = max(0.0, self._collision_cooldown - dt)

        current_input = dict(self._input)
        if self._recording and len(self._recorded_inputs) < MAX_REPLAY_INPUTS:
            self._recorded_inputs.append({"tick": self._tick, **current_input})

        throttle = _clamp(current_input.get("throttle"), -1.0, 1.0)
        steer = _clamp(current_input.get("steer"), -1.0, 1.0)
        brake = _clamp(current_input.get("brake"), 0.0, 1.0)
        boost = bool(current_input.get("boost"))

        speed = math.hypot(self._vx[0], self._vz[0])
        self._yaw[0] += steer * (1.3 + min(speed, 35.0) * 0.035) * dt
        acceleration = 25.0 * throttle * (1.65 if boost else 1.0)
        self._vx[0] += math.sin(self._yaw[0]) * acceleration * dt
        self._vz[0] += math.cos(self._yaw[0]) * acceleration * dt
        drag = max(0.0, 1.0 - (3.0 + brake * 8.0) * dt)
        self._vx[0] *= drag
        self._vz[0] *= drag
        max_speed = 42.0 if boost else 30.0
        speed = math.hypot(self._vx[0], self._vz[0])
        if speed > max_speed:
            scale = max_speed / speed
            self._vx[0] *= scale
            self._vz[0] *= scale
            speed = max_speed
        self._x[0] += self._vx[0] * dt
        self._z[0] += self._vz[0] * dt

        boundary = 28.0
        if abs(self._x[0]) > boundary:
            self._x[0] = max(-boundary, min(boundary, self._x[0]))
            self._vx[0] *= -0.55
            self._burst_locked(self._x[0], 0.65, self._z[0], 12)
        if abs(self._z[0]) > boundary:
            self._z[0] = max(-boundary, min(boundary, self._z[0]))
            self._vz[0] *= -0.55
            self._burst_locked(self._x[0], 0.65, self._z[0], 12)

        grid = self._build_spatial_grid_locked()
        player_cell = (
            math.floor(self._x[0] / 2.0),
            math.floor(self._z[0] / 2.0),
        )
        for cell_x in range(player_cell[0] - 1, player_cell[0] + 2):
            for cell_z in range(player_cell[1] - 1, player_cell[1] + 2):
                for other in grid.get((cell_x, cell_z), []):
                    dx = self._x[other] - self._x[0]
                    dz = self._z[other] - self._z[0]
                    distance = math.hypot(dx, dz)
                    minimum = self._radius[other] + self._radius[0]
                    if distance >= minimum:
                        continue
                    if distance < 0.0001:
                        dx, dz, distance = 1.0, 0.0, 1.0
                    nx, nz = dx / distance, dz / distance
                    overlap = minimum - distance
                    self._x[0] -= nx * overlap
                    self._z[0] -= nz * overlap
                    normal_velocity = self._vx[0] * nx + self._vz[0] * nz
                    if normal_velocity > 0.0:
                        self._vx[0] -= normal_velocity * 1.7 * nx
                        self._vz[0] -= normal_velocity * 1.7 * nz
                    if speed > 5.0 and self._collision_cooldown <= 0.0:
                        self._collision_cooldown = 0.28
                        self._burst_locked(self._x[0], 0.9, self._z[0], 28)
                        self._append_event_locked("COLLISION", f"Player hit {self._kind[other].lower()}.")

        for index in range(MAX_PARTICLES):
            if self._plife[index] <= 0.0:
                continue
            self._plife[index] -= dt
            if self._plife[index] <= 0.0:
                self._plife[index] = 0.0
                self._particle_count = max(0, self._particle_count - 1)
                continue
            self._pvy[index] -= 13.0 * dt
            self._px[index] += self._pvx[index] * dt
            self._py[index] = max(0.08, self._py[index] + self._pvy[index] * dt)
            self._pz[index] += self._pvz[index] * dt
            self._pvx[index] *= 0.985
            self._pvz[index] *= 0.985

        if self._tick % 3 == 0:
            self._network_seq += 1

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._last_tick_ms = elapsed_ms
        self._max_tick_ms = max(self._max_tick_ms, elapsed_ms)

    def _run_loop(self) -> None:
        deadline = time.perf_counter()
        while not self._stop.is_set():
            with self._lock:
                running = self._running
            if not running:
                deadline = time.perf_counter() + FIXED_DT
                self._stop.wait(0.04)
                continue
            now = time.perf_counter()
            if now < deadline:
                self._stop.wait(min(deadline - now, 0.01))
                continue
            steps = 0
            while now >= deadline and steps < MAX_CATCH_UP_STEPS:
                with self._lock:
                    if not self._running:
                        break
                    self._tick_locked(FIXED_DT)
                deadline += FIXED_DT
                steps += 1
                now = time.perf_counter()
            if steps == MAX_CATCH_UP_STEPS and now >= deadline:
                deadline = now + FIXED_DT

    def _ensure_thread_locked(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="gg-game-engine-runtime",
            daemon=True,
        )
        self._thread.start()

    def start(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_thread_locked()
            self._running = True
            self._append_event_locked("PLAY", "Fixed-step simulation running at 60 Hz.")
            return self.snapshot_locked()

    def pause(self) -> dict[str, Any]:
        with self._lock:
            self._running = False
            self._append_event_locked("PAUSE", "Simulation paused; render state retained.")
            return self.snapshot_locked()

    def reset(self) -> dict[str, Any]:
        with self._lock:
            self._running = False
            self._recording = False
            self._replaying = False
            self._recorded_inputs = []
            self._replay_inputs = []
            self._replay_index = 0
            self._reset_world_locked()
            return self.snapshot_locked()

    def step(self) -> dict[str, Any]:
        with self._lock:
            if not self._running:
                self._running = True
                self._tick_locked(FIXED_DT)
                self._running = False
            return self.snapshot_locked()

    def set_input(self, raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(str(raw or "{}"))
        except (TypeError, ValueError):
            return {"schema": SCHEMA, "error": "GAME_ENGINE_INPUT_INVALID"}
        if not isinstance(payload, dict):
            return {"schema": SCHEMA, "error": "GAME_ENGINE_INPUT_INVALID"}
        with self._lock:
            self._input = {
                "throttle": _clamp(payload.get("throttle"), -1.0, 1.0),
                "steer": _clamp(payload.get("steer"), -1.0, 1.0),
                "brake": _clamp(payload.get("brake"), 0.0, 1.0),
                "boost": bool(payload.get("boost")),
            }
            return self.snapshot_locked()

    def burst(self) -> dict[str, Any]:
        with self._lock:
            self._burst_locked(self._x[0], 0.9, self._z[0], 48)
            return self.snapshot_locked()

    def set_stress(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            was_running = self._running
            self._stress = bool(enabled)
            self._running = False
            self._reset_world_locked()
            if was_running:
                self._running = True
            self._append_event_locked(
                "STRESS",
                "Stress scene enabled." if self._stress else "Stress scene disabled.",
            )
            return self.snapshot_locked()

    def start_recording(self) -> dict[str, Any]:
        with self._lock:
            self._recorded_inputs = []
            self._recording = True
            self._append_event_locked("RECORD", "Input recording armed; maximum 30 seconds.")
            return self.snapshot_locked()

    def stop_recording(self) -> dict[str, Any]:
        with self._lock:
            self._recording = False
            self._append_event_locked(
                "RECORD_STOP",
                f"Recorded {len(self._recorded_inputs)} fixed-step inputs.",
            )
            return self.snapshot_locked()

    def play_replay(self) -> dict[str, Any]:
        with self._lock:
            if not self._recorded_inputs:
                self._append_event_locked("REPLAY_EMPTY", "Record a run before replaying it.")
                return self.snapshot_locked()
            self._replay_inputs = list(self._recorded_inputs)
            self._replay_index = 0
            self._replaying = True
            self._running = True
            self._reset_world_locked()
            self._append_event_locked("REPLAY", "Replaying the recorded fixed-step input stream.")
            return self.snapshot_locked()

    def snapshot_locked(self) -> dict[str, Any]:
        if self._running:
            state = "RUNNING"
        elif self._tick > 0:
            state = "PAUSED"
        else:
            state = "IDLE"

        entity_rows: list[dict[str, Any]] = []
        for index in range(MAX_ENTITIES):
            if not self._alive[index]:
                continue
            entity_rows.append(
                {
                    "id": f"e-{index:04d}",
                    "kind": self._kind[index],
                    "x": _round(self._x[index]),
                    "y": _round(self._y[index]),
                    "z": _round(self._z[index]),
                    "yaw": _round(self._yaw[index], 4),
                    "sx": _round(self._sx[index]),
                    "sy": _round(self._sy[index]),
                    "sz": _round(self._sz[index]),
                    "color": self._color[index],
                }
            )
            if len(entity_rows) >= RENDER_ENTITY_LIMIT:
                break

        particle_rows: list[dict[str, Any]] = []
        for index in range(MAX_PARTICLES):
            if self._plife[index] <= 0.0:
                continue
            particle_rows.append(
                {
                    "x": _round(self._px[index]),
                    "y": _round(self._py[index]),
                    "z": _round(self._pz[index]),
                    "life": _round(self._plife[index]),
                    "color": self._pcolor[index],
                }
            )
            if len(particle_rows) >= RENDER_PARTICLE_LIMIT:
                break

        speed = math.hypot(self._vx[0], self._vz[0])
        lateral = abs(
            -math.sin(self._yaw[0]) * self._vx[0]
            + math.cos(self._yaw[0]) * self._vz[0]
        )
        chunk_x = math.floor(self._x[0] / CHUNK_SIZE)
        chunk_z = math.floor(self._z[0] / CHUNK_SIZE)
        chunks = [
            {"x": chunk_x + dx, "z": chunk_z + dz, "key": f"{chunk_x + dx}:{chunk_z + dz}"}
            for dz in range(-2, 3)
            for dx in range(-2, 3)
        ][:MAX_CHUNKS]

        return {
            "schema": SCHEMA,
            "state": state,
            "mode": "LOCAL_PLAYGROUND",
            "stress": self._stress,
            "simulation": {
                "fixed_hz": FIXED_HZ,
                "dt_ms": round(FIXED_DT * 1000.0, 4),
                "tick": self._tick,
                "time_s": _round(self._sim_time, 2),
                "last_tick_ms": _round(self._last_tick_ms, 4),
                "max_tick_ms": _round(self._max_tick_ms, 4),
                "active_entities": self._entity_count,
                "entity_capacity": MAX_ENTITIES,
                "active_particles": self._particle_count,
                "particle_capacity": MAX_PARTICLES,
                "render_entity_count": len(entity_rows),
                "render_particle_count": len(particle_rows),
            },
            "player": {
                "x": _round(self._x[0]),
                "y": _round(self._y[0]),
                "z": _round(self._z[0]),
                "yaw": _round(self._yaw[0], 4),
                "speed": _round(speed, 2),
                "drift": _round(lateral, 2),
                "boost": bool(self._input.get("boost")),
            },
            "input": dict(self._input),
            "render": {
                "entities": entity_rows,
                "particles": particle_rows,
                "draw_calls": 3,
                "renderer": "QTQUICK3D_PRIMITIVES",
            },
            "chunks": {
                "loaded": chunks,
                "loaded_count": len(chunks),
                "capacity": MAX_CHUNKS,
                "interest_radius": 2,
            },
            "network": {
                "mode": "LOCAL_LOOPBACK",
                "transport": "NOT_CONNECTED",
                "authoritative_server": False,
                "snapshot_hz": 20,
                "sequence": self._network_seq,
                "estimated_bytes": 96 + self._entity_count * 12,
                "interest_entities": min(self._entity_count, 128),
            },
            "replay": {
                "recording": self._recording,
                "replaying": self._replaying,
                "recorded_inputs": len(self._recorded_inputs),
                "max_inputs": MAX_REPLAY_INPUTS,
                "replay_index": self._replay_index,
            },
            "events": list(reversed(self._events[-12:])),
            "capabilities": [
                "FIXED_STEP",
                "DATA_ORIENTED_POOLS",
                "SPATIAL_GRID_BROADPHASE",
                "PARTICLE_POOL",
                "CHUNK_INTEREST",
                "DETERMINISTIC_REPLAY",
                "LOCAL_SNAPSHOT_SEAM",
            ],
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self.snapshot_locked()

    def shutdown(self) -> None:
        with self._lock:
            self._running = False
            self._stop.set()
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        with self._lock:
            self._thread = None


_RUNTIME = GameEngineRuntime()


def status_payload() -> dict[str, Any]:
    return _RUNTIME.snapshot()


def start() -> dict[str, Any]:
    return _RUNTIME.start()


def pause() -> dict[str, Any]:
    return _RUNTIME.pause()


def reset() -> dict[str, Any]:
    return _RUNTIME.reset()


def step() -> dict[str, Any]:
    return _RUNTIME.step()


def set_input(raw: str) -> dict[str, Any]:
    return _RUNTIME.set_input(raw)


def burst() -> dict[str, Any]:
    return _RUNTIME.burst()


def set_stress(enabled: bool) -> dict[str, Any]:
    return _RUNTIME.set_stress(enabled)


def start_recording() -> dict[str, Any]:
    return _RUNTIME.start_recording()


def stop_recording() -> dict[str, Any]:
    return _RUNTIME.stop_recording()


def play_replay() -> dict[str, Any]:
    return _RUNTIME.play_replay()


def shutdown() -> None:
    _RUNTIME.shutdown()
