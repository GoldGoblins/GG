"""Switchable paper books on the CRYPTO surface.

GG = house swing. STOCH+RSI = werkkrew StochRSITEMA on our tape.
DCA = hold SOL, harvest 80% of cycle profit at highs, buy it back at lows.
DCA+SWING = DCA bag rules with a many-oscillator swing vote for timing.
Not a Freqtrade process. MAINNET not used.
"""
from __future__ import annotations

from typing import Any

from backend import crypto_trader

BOOKS = (
    {
        "id": "gg",
        "name": "GG",
        "source": "house swing book",
    },
    {
        "id": "stoch_rsi",
        "name": "STOCH+RSI",
        "source": "werkkrew StochRSITEMA (freqtrade strategy, GG runner)",
    },
    {
        "id": "dca",
        "name": "DCA",
        "source": "harvest 80% of cycle profit at highs, buy it back at lows",
    },
    {
        "id": "dca_swing",
        "name": "DCA+SWING",
        "source": "DCA harvest + swing K/D/TEMA/MACD + 20 osc vote",
    },
)


def catalog() -> list[dict[str, str]]:
    return [dict(row) for row in BOOKS]


def selected() -> str:
    bid = str(crypto_trader.load_state().get("book") or "gg")
    if bid not in {row["id"] for row in BOOKS}:
        return "gg"
    return bid


def set_book(book_id: str) -> str:
    bid = str(book_id or "gg")
    if bid not in {row["id"] for row in BOOKS}:
        bid = "gg"
    state = crypto_trader.load_state()
    state["book"] = bid
    crypto_trader.save_state(state)
    return bid


def run_backtest(frames: dict[str, dict[str, Any]]) -> dict[str, Any]:
    bid = selected()
    if bid == "stoch_rsi":
        from backend import crypto_bot_stoch_rsi

        report = crypto_bot_stoch_rsi.run_backtest(frames)
    elif bid == "dca":
        from backend import crypto_bot_dca

        report = crypto_bot_dca.run_backtest(frames)
    elif bid == "dca_swing":
        from backend import crypto_bot_dca_swing

        report = crypto_bot_dca_swing.run_backtest(frames)
    else:
        report = crypto_trader.run_flow_backtest(frames)
    report["book"] = bid
    return report
