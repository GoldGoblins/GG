#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from backend import crypto_contract, crypto_trader


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="gg-trader-"))
    crypto_contract.STATE_DIR = tmp
    crypto_trader.reset_book()
    crypto_trader.set_armed(True)
    sig_buy = {"super": "buy"}
    sig_sell = {"super": "sell"}
    t0 = 1_700_000_000
    book = crypto_trader.tick(100.0, sig_buy, "range", 0.02, now=t0)
    if book["trades_today"] != 1:
        raise AssertionError("buy not counted")
    if book["sol"] in ("0.000000000", "—"):
        raise AssertionError("no sol after buy " + book["sol"])
    book = crypto_trader.tick(110.0, sig_sell, "range", 0.02, now=t0 + 8 * 60)
    if int(book["trades_today"]) != 2:
        raise AssertionError("sell not counted " + str(book))
    if book["banked_sol"] in ("0.000000000", "0", "—"):
        raise AssertionError("80 percent not banked " + book["banked_sol"])
    blocked = crypto_trader.tick(90.0, sig_buy, "trend_down", 0.02, now=t0 + 16 * 60)
    if blocked["last"].get("action") == "buy":
        raise AssertionError("buy in trend_down")
    print("CRYPTO_TRADER_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
