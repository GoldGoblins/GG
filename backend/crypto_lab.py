from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

from backend.crypto_contract import STATE_DIR, ensure_state_dir

VALIDATOR_BIN = Path("/home/GG/.local/opt/solana-cli/bin/solana-test-validator")
LEDGER_DIR = STATE_DIR / "local-ledger"
LOG_PATH = STATE_DIR / "local-validator.log"
PID_PATH = STATE_DIR / "local-validator.pid"
RPC_URL = "http://127.0.0.1:8899"


def _pid_alive(pid: int) -> bool:
    comm = Path("/proc") / str(pid) / "comm"
    try:
        name = comm.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return name.startswith("solana-test-val")


def running_pid() -> int | None:
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if not _pid_alive(pid):
        return None
    return pid


def lab_status() -> dict[str, Any]:
    pid = running_pid()
    healthy = False
    if pid is not None:
        try:
            body = json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
            ).encode("utf-8")
            req = urllib.request.Request(
                RPC_URL,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            payload = json.loads(
                urllib.request.urlopen(req, timeout=2).read().decode("utf-8")
            )
            healthy = payload.get("result") == "ok"
        except (OSError, TimeoutError, json.JSONDecodeError, urllib.error.URLError):
            healthy = False
    return {
        "running": pid is not None,
        "healthy": healthy,
        "pid": pid,
        "rpc": RPC_URL,
        "label": "LAB ON" if pid is not None and healthy else (
            "LAB STARTING" if pid is not None else "LAB OFF"
        ),
    }


def start_lab() -> dict[str, Any]:
    current = running_pid()
    if current is not None:
        return lab_status()
    if not VALIDATOR_BIN.is_file():
        raise RuntimeError("CRYPTO_VALIDATOR_MISSING")
    ensure_state_dir()
    LEDGER_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    log = LOG_PATH.open("ab")
    env = os.environ.copy()
    env["RAYON_NUM_THREADS"] = "2"
    env["TOKIO_WORKER_THREADS"] = "2"
    proc = subprocess.Popen(
        [
            "nice",
            "-n",
            "15",
            "taskset",
            "-c",
            "8-11",
            str(VALIDATOR_BIN),
            "--ledger",
            str(LEDGER_DIR),
            "--rpc-port",
            "8899",
            "--bind-address",
            "127.0.0.1",
            "--rpc-pubsub-notification-threads",
            "0",
            "--rpc-pubsub-worker-threads",
            "1",
            "--limit-ledger-size",
            "10000",
            "--quiet",
        ],
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
        close_fds=True,
    )
    PID_PATH.write_text(str(proc.pid) + "\n", encoding="utf-8")
    PID_PATH.chmod(0o600)
    for _ in range(8):
        status = lab_status()
        if status["healthy"]:
            return status
        time.sleep(0.25)
    return lab_status()


def stop_lab() -> dict[str, Any]:
    pid = running_pid()
    if pid is None:
        try:
            PID_PATH.unlink()
        except OSError:
            pass
        return lab_status()
    os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not _pid_alive(pid):
            break
        time.sleep(0.2)
    if _pid_alive(pid):
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.2)
    try:
        PID_PATH.unlink()
    except OSError:
        pass
    return lab_status()
