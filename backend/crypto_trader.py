"""Spot swing/day trader: 4H regime + 5m Strategy004, 80/20 bank, 4–12 fills/day.

Paper inventory. Goal: grow banked SOL when range flux > fees.
Does not guarantee profit. MAINNET not used here.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.crypto_contract import ensure_state_dir, format_units
from backend.crypto_indicators import ema, last
from backend.crypto_strategy004 import adx, evaluate as evaluate_004

SOL_SCALE = 10**9
USD_SCALE = 10**6
START_USD = 200 * USD_SCALE
FEE_BPS = 30
PROFIT_BANK_BPS = 8000
PROFIT_ROLL_BPS = 2000
MAX_TRADES_DAY = 12
MIN_TRADES_DAY = 4
STATE_NAME = "trader.json"
LOTS_NAME = "trader-lots.jsonl"


def _state_path() -> Path:
    return ensure_state_dir() / STATE_NAME


def _lots_path() -> Path:
    return ensure_state_dir() / LOTS_NAME


def default_state() -> dict[str, Any]:
    return {
        "armed": False,
        "usd": START_USD,
        "sol": 0,
        "banked_sol": 0,
        "day": "",
        "trades_today": 0,
        "last_ts": 0,
        "regime": "range",
        "last": {},
    }


def load_state() -> dict[str, Any]:
    path = _state_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        payload = default_state()
        save_state(payload)
        return payload
    if not isinstance(payload, dict):
        payload = default_state()
    base = default_state()
    base.update(payload)
    return base


def save_state(payload: dict[str, Any]) -> dict[str, Any]:
    path = _state_path()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return load_state()


def append_lot(row: dict[str, Any]) -> None:
    path = _lots_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def read_lots(limit: int = 24) -> list[dict[str, Any]]:
    path = _lots_path()
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


def _utc_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _price_atoms(close: float) -> int:
    return max(1, int(round(float(close) * USD_SCALE)))


def _apply_fee(amount: int) -> int:
    return amount * (10_000 - FEE_BPS) // 10_000


def regime_from_4h(highs: list[float], lows: list[float], closes: list[float]) -> str:
    if len(closes) < 40:
        return "range"
    a = last(adx(highs, lows, closes, 14))
    e5 = last(ema(closes, 5))
    e20 = last(ema(closes, 20))
    if a is None or e5 is None or e20 is None:
        return "range"
    if a > 25 and e5 > e20:
        return "trend_up"
    if a > 25 and e5 < e20:
        return "trend_down"
    return "range"


def atr_pct(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.01
    trs: list[float] = []
    for i in range(1, len(closes)):
        trs.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        )
    window = trs[-period:]
    atr = sum(window) / len(window)
    px = closes[-1] if closes[-1] else 1.0
    return max(0.001, atr / px)


def cooldown_sec(atr_fraction: float) -> int:
    if atr_fraction >= 0.02:
        return 8 * 60
    if atr_fraction >= 0.012:
        return 15 * 60
    if atr_fraction >= 0.007:
        return 25 * 60
    return 40 * 60


def lot_usd(state: dict[str, Any], price: int) -> int:
    usd = int(state["usd"])
    if usd <= 0:
        return 0
    chunk = usd // 5
    floor = 2 * USD_SCALE
    cap = 40 * USD_SCALE
    size = max(floor, min(cap, chunk))
    return min(size, usd)


def set_armed(armed: bool) -> dict[str, Any]:
    state = load_state()
    state["armed"] = bool(armed)
    return save_state(state)


def reset_book() -> dict[str, Any]:
    state = default_state()
    save_state(state)
    path = _lots_path()
    try:
        path.unlink()
    except OSError:
        pass
    return state


def snapshot() -> dict[str, Any]:
    state = load_state()
    sol = int(state.get("sol") or 0)
    banked = int(state.get("banked_sol") or 0)
    usd = int(state.get("usd") or 0)
    return {
        "armed": bool(state.get("armed")),
        "regime": str(state.get("regime") or "range"),
        "trades_today": int(state.get("trades_today") or 0),
        "max_day": MAX_TRADES_DAY,
        "usd": format_units(usd, 6),
        "sol": format_units(sol, 9),
        "banked_sol": format_units(banked, 9),
        "tokens": format_units(sol + banked, 9),
        "last": state.get("last") if isinstance(state.get("last"), dict) else {},
        "lots": read_lots(16),
    }


def _open_lots() -> list[dict[str, Any]]:
    open_rows: list[dict[str, Any]] = []
    for row in read_lots(200):
        if row.get("side") == "buy" and not row.get("closed"):
            open_rows.append(row)
        if row.get("side") == "sell" and row.get("closes"):
            cid = row.get("closes")
            open_rows = [x for x in open_rows if x.get("id") != cid]
    return open_rows


def tick(
    close: float,
    sig: dict[str, Any],
    regime: str,
    atr_fraction: float,
    now: int | None = None,
) -> dict[str, Any]:
    state = load_state()
    ts = int(now if now is not None else time.time())
    day = _utc_day()
    if state.get("day") != day:
        state["day"] = day
        state["trades_today"] = 0
    state["regime"] = regime
    price = _price_atoms(close)
    action = "hold"
    note = regime
    cooldown = cooldown_sec(atr_fraction)
    if not state.get("armed"):
        note = "disarmed"
    elif int(state.get("trades_today") or 0) >= MAX_TRADES_DAY:
        note = "day cap"
    elif ts - int(state.get("last_ts") or 0) < cooldown:
        note = "cooldown " + str(cooldown) + "s"
    else:
        super_sig = str(sig.get("super") or "none")
        opens = _open_lots()
        if super_sig == "buy" and regime != "trend_down" and not opens:
            usd_in = lot_usd(state, price)
            if usd_in > 0:
                usd_net = _apply_fee(usd_in)
                sol_got = usd_net * SOL_SCALE // price
                if sol_got > 0:
                    state["usd"] = int(state["usd"]) - usd_in
                    state["sol"] = int(state["sol"]) + sol_got
                    lot_id = "lot-" + str(ts)
                    row = {
                        "id": lot_id,
                        "ts": ts,
                        "side": "buy",
                        "sol": sol_got,
                        "usd": usd_in,
                        "price": price,
                        "regime": regime,
                        "closed": False,
                    }
                    append_lot(row)
                    state["trades_today"] = int(state["trades_today"]) + 1
                    state["last_ts"] = ts
                    action = "buy"
                    note = "buy " + format_units(sol_got, 9)
        elif super_sig == "sell" and int(state.get("sol") or 0) > 0:
            opens = _open_lots()
            lot = opens[0] if opens else None
            sol_sell = int(lot["sol"]) if lot else int(state["sol"])
            sol_sell = min(sol_sell, int(state["sol"]))
            usd_gross = sol_sell * price // SOL_SCALE
            usd_net = _apply_fee(usd_gross)
            cost = int(lot["usd"]) if lot else usd_net
            profit = usd_net - cost
            state["sol"] = int(state["sol"]) - sol_sell
            if profit > 0:
                bank_usd = profit * PROFIT_BANK_BPS // 10_000
                roll_usd = profit - bank_usd
                bank_sol = bank_usd * SOL_SCALE // price
                state["banked_sol"] = int(state["banked_sol"]) + bank_sol
                state["usd"] = int(state["usd"]) + cost + roll_usd
            else:
                state["usd"] = int(state["usd"]) + usd_net
            row = {
                "id": "sell-" + str(ts),
                "ts": ts,
                "side": "sell",
                "sol": sol_sell,
                "usd": usd_net,
                "price": price,
                "profit_usd": profit,
                "regime": regime,
                "closes": (lot or {}).get("id"),
                "bank_bps": PROFIT_BANK_BPS if profit > 0 else 0,
            }
            append_lot(row)
            state["trades_today"] = int(state["trades_today"]) + 1
            state["last_ts"] = ts
            action = "sell"
            note = "sell profit " + format_units(profit, 6)
    state["last"] = {
        "action": action,
        "note": note,
        "regime": regime,
        "atr_pct": atr_fraction,
        "super": sig.get("super"),
        "close": close,
        "cooldown": cooldown,
    }
    save_state(state)
    return snapshot()
