"""Julien-style atomic flash arb on two constant-product pools.

Borrow quote → swap cheap pool → swap rich pool → repay + fee.
If leftover quote < min profit the whole snapshot is dropped (revert).
Pools live in local state only. Not Aave, not mainnet.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.crypto_contract import ensure_state_dir

SOL_DECIMALS = 9
USD_DECIMALS = 6
SOL_SCALE = 10**SOL_DECIMALS
USD_SCALE = 10**USD_DECIMALS
SWAP_FEE_BPS = 30
FLASH_FEE_BPS = 9
POOLS_NAME = "arb-pools.json"


def pools_path() -> Path:
    return ensure_state_dir() / POOLS_NAME


def _default_pools() -> dict[str, Any]:
    return {
        "A": {
            "sol": 1000 * SOL_SCALE,
            "usd": 100_000 * USD_SCALE,
        },
        "B": {
            "sol": 1000 * SOL_SCALE,
            "usd": 102_000 * USD_SCALE,
        },
        "fee_bps": SWAP_FEE_BPS,
        "flash_bps": FLASH_FEE_BPS,
    }


def load_pools() -> dict[str, Any]:
    path = pools_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        payload = _default_pools()
        save_pools(payload)
        return payload
    if not isinstance(payload, dict) or "A" not in payload or "B" not in payload:
        payload = _default_pools()
        save_pools(payload)
    return payload


def save_pools(payload: dict[str, Any]) -> None:
    path = pools_path()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def reset_pools() -> dict[str, Any]:
    payload = _default_pools()
    save_pools(payload)
    return payload


def price_usd_per_sol(pool: dict[str, Any]) -> str:
    sol = int(pool["sol"])
    usd = int(pool["usd"])
    if sol == 0:
        return "—"
    q = (usd * SOL_SCALE) // sol
    whole, frac = divmod(q, USD_SCALE)
    return str(whole) + "." + f"{frac:06d}"


def _swap_usd_for_sol(pool: dict[str, Any], usd_in: int, fee_bps: int) -> int:
    if usd_in <= 0:
        raise ValueError("CRYPTO_ARB_SIZE")
    x = int(pool["sol"])
    y = int(pool["usd"])
    taxed = usd_in * (10_000 - fee_bps) // 10_000
    if taxed <= 0:
        raise ValueError("CRYPTO_ARB_FEE")
    sol_out = x * taxed // (y + taxed)
    if sol_out <= 0 or sol_out >= x:
        raise ValueError("CRYPTO_ARB_SWAP")
    pool["usd"] = y + usd_in
    pool["sol"] = x - sol_out
    return sol_out


def _swap_sol_for_usd(pool: dict[str, Any], sol_in: int, fee_bps: int) -> int:
    if sol_in <= 0:
        raise ValueError("CRYPTO_ARB_SIZE")
    x = int(pool["sol"])
    y = int(pool["usd"])
    taxed = sol_in * (10_000 - fee_bps) // 10_000
    if taxed <= 0:
        raise ValueError("CRYPTO_ARB_FEE")
    usd_out = y * taxed // (x + taxed)
    if usd_out <= 0 or usd_out >= y:
        raise ValueError("CRYPTO_ARB_SWAP")
    pool["sol"] = x + sol_in
    pool["usd"] = y - usd_out
    return usd_out


def quote_flash_arb(usd_borrow: int, pools: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = json.loads(json.dumps(pools or load_pools()))
    fee_bps = int(snapshot.get("fee_bps") or SWAP_FEE_BPS)
    flash_bps = int(snapshot.get("flash_bps") or FLASH_FEE_BPS)
    a = dict(snapshot["A"])
    b = dict(snapshot["B"])
    price_a = int(a["usd"]) * SOL_SCALE // int(a["sol"])
    price_b = int(b["usd"]) * SOL_SCALE // int(b["sol"])
    cheap, rich = ("A", "B") if price_a <= price_b else ("B", "A")
    buy_pool = a if cheap == "A" else b
    sell_pool = b if rich == "B" else a
    sol_bought = _swap_usd_for_sol(buy_pool, usd_borrow, fee_bps)
    usd_out = _swap_sol_for_usd(sell_pool, sol_bought, fee_bps)
    repay = usd_borrow + (usd_borrow * flash_bps + 9999) // 10_000
    profit = usd_out - repay
    return {
        "borrow_usd": usd_borrow,
        "repay_usd": repay,
        "sol_bought": sol_bought,
        "usd_out": usd_out,
        "profit_usd": profit,
        "buy_pool": cheap,
        "sell_pool": rich,
        "price_a": price_usd_per_sol(snapshot["A"]),
        "price_b": price_usd_per_sol(snapshot["B"]),
        "ok": profit > 0,
        "snapshot": {
            "A": a,
            "B": b,
            "fee_bps": fee_bps,
            "flash_bps": flash_bps,
        },
    }


def commit_flash_arb(usd_borrow: int) -> dict[str, Any]:
    current = load_pools()
    quoted = quote_flash_arb(usd_borrow, current)
    if not quoted["ok"]:
        quoted["error"] = "NO_PROFIT"
        quoted["committed"] = False
        return quoted
    save_pools(quoted["snapshot"])
    quoted["committed"] = True
    quoted["price_a_after"] = price_usd_per_sol(quoted["snapshot"]["A"])
    quoted["price_b_after"] = price_usd_per_sol(quoted["snapshot"]["B"])
    return quoted


def pool_status() -> dict[str, Any]:
    pools = load_pools()
    return {
        "price_a": price_usd_per_sol(pools["A"]),
        "price_b": price_usd_per_sol(pools["B"]),
        "sol_a": pools["A"]["sol"],
        "sol_b": pools["B"]["sol"],
        "usd_a": pools["A"]["usd"],
        "usd_b": pools["B"]["usd"],
        "fee_bps": pools.get("fee_bps", SWAP_FEE_BPS),
        "flash_bps": pools.get("flash_bps", FLASH_FEE_BPS),
    }
