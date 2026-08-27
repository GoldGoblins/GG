from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

STATE_DIR = Path("/home/GG/.local/state/goldgoblins/gg-ai-desktop/crypto")
LEDGER_NAME = "ledger.jsonl"
WALLET_NAME = "wallet.json"
NETWORK_DEFAULT = "testnet"
PUBLIC_DEVNET = "https://api.devnet.solana.com"
RPC_ALLOWLIST = {
    "testnet": "http://127.0.0.1:8899",
    "mainnet": "https://api.mainnet-beta.solana.com",
}
_PUBKEY = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_SIDES = ("buy", "sell")


def ensure_state_dir() -> Path:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return STATE_DIR


def wallet_path() -> Path:
    return ensure_state_dir() / WALLET_NAME


def ledger_path() -> Path:
    return ensure_state_dir() / LEDGER_NAME


def validate_pubkey(value: str) -> str:
    key = str(value or "").strip()
    if not _PUBKEY.fullmatch(key):
        raise ValueError("CRYPTO_PUBKEY_INVALID")
    return key


def parse_signal(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        payload = raw
    else:
        try:
            payload = json.loads(str(raw or ""))
        except json.JSONDecodeError as exc:
            raise ValueError("CRYPTO_SIGNAL_JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("CRYPTO_SIGNAL_JSON")
    side = str(payload.get("side") or "").strip().lower()
    if side not in _SIDES:
        raise ValueError("CRYPTO_SIGNAL_SIDE")
    try:
        size = float(payload.get("size_sol"))
    except (TypeError, ValueError) as exc:
        raise ValueError("CRYPTO_SIGNAL_SIZE") from exc
    if size <= 0 or size > 1000:
        raise ValueError("CRYPTO_SIGNAL_SIZE")
    symbol = str(payload.get("symbol") or "SOL").strip()[:24] or "SOL"
    source = str(payload.get("source") or "manual").strip()[:40] or "manual"
    return {
        "side": side,
        "size_sol": size,
        "symbol": symbol,
        "source": source,
        "network": NETWORK_DEFAULT,
        "mode": "TESTNET",
    }


SOL_DECIMALS = 9


def format_units(amount: int | str | None, decimals: int) -> str:
    if amount is None:
        return "—"
    try:
        n = int(amount)
        places = int(decimals)
    except (TypeError, ValueError):
        return "—"
    if places < 0 or places > 18:
        return "—"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if places == 0:
        return sign + str(n)
    scale = 10 ** places
    whole, frac = divmod(n, scale)
    return sign + str(whole) + "." + f"{frac:0{places}d}"


def format_sol(lamports: int | None) -> str:
    return format_units(lamports, SOL_DECIMALS)


def short_pubkey(value: str) -> str:
    key = str(value or "")
    if len(key) < 8:
        return key or "DISCONNECTED"
    return key[:4] + "…" + key[-4:]


def load_network() -> str:
    path = ensure_state_dir() / "network.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        chain = str(payload.get("network") or NETWORK_DEFAULT)
    except (OSError, json.JSONDecodeError, UnicodeError):
        return NETWORK_DEFAULT
    if chain in ("paper", "devnet", "localnet"):
        chain = "testnet"
    if chain not in RPC_ALLOWLIST:
        return NETWORK_DEFAULT
    return chain


def save_network(network: str) -> str:
    chain = str(network or "").strip().lower()
    if chain in ("paper", "devnet", "localnet"):
        chain = "testnet"
    if chain not in RPC_ALLOWLIST:
        raise ValueError("CRYPTO_NETWORK_INVALID")
    path = ensure_state_dir() / "network.json"
    path.write_text(json.dumps({"network": chain}) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return chain


def load_wallet() -> dict[str, Any]:
    path = wallet_path()
    if not path.is_file():
        return {
            "connected": False,
            "pubkey": "",
            "label": "WALLET · DISCONNECTED",
            "network": NETWORK_DEFAULT,
            "mode": "TESTNET",
            "balance_lamports": None,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    pubkey = str(payload.get("pubkey") or "")
    connected = bool(pubkey)
    return {
        "connected": connected,
        "pubkey": pubkey,
        "label": (
            "WALLET · " + short_pubkey(pubkey)
            if connected
            else "WALLET · DISCONNECTED"
        ),
        "network": str(payload.get("network") or NETWORK_DEFAULT),
        "mode": "TESTNET" if (payload.get("network") or NETWORK_DEFAULT) != "mainnet" else "LIVE",
        "balance_lamports": payload.get("balance_lamports"),
    }


def save_wallet(
    pubkey: str,
    balance_lamports: int | None = None,
    network: str | None = None,
) -> dict[str, Any]:
    key = validate_pubkey(pubkey)
    current = load_wallet()
    chain = str(network or current.get("network") or load_network() or NETWORK_DEFAULT)
    if chain in ("paper", "devnet", "localnet"):
        chain = "testnet"
    if chain not in RPC_ALLOWLIST:
        chain = NETWORK_DEFAULT
    payload = {
        "pubkey": key,
        "network": chain,
        "mode": "TESTNET" if chain != "mainnet" else "LIVE",
        "balance_lamports": balance_lamports,
    }
    path = wallet_path()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return load_wallet()


def clear_wallet() -> dict[str, Any]:
    path = wallet_path()
    try:
        path.unlink()
    except OSError:
        pass
    return load_wallet()


def append_ledger(row: dict[str, Any]) -> dict[str, Any]:
    ensure_state_dir()
    path = ledger_path()
    line = json.dumps(row, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return row


def read_ledger(limit: int = 20) -> list[dict[str, Any]]:
    path = ledger_path()
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-max(1, int(limit)) :]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows
