#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from backend.crypto_indicators import rsi, sma
from backend.crypto_strategy004 import evaluate


def main() -> int:
    if sma([1, 2, 3, 4], 2)[-1] != 3.5:
        raise AssertionError("sma")
    series = [float(i) for i in range(1, 120)]
    r = rsi(series, 14)
    if r[-1] is None or r[-1] < 70:
        raise AssertionError("rsi uptrend " + str(r[-1]))
    highs = [x + 1 for x in series]
    lows = [max(0.1, x - 1) for x in series]
    vols = [100.0] * len(series)
    report = evaluate(highs, lows, series, vols)
    if report.get("strategy") != "Strategy004":
        raise AssertionError("strategy tag")
    if report["super"] not in ("buy", "sell", "none"):
        raise AssertionError("super " + str(report["super"]))
    print("CRYPTO_INDICATORS_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
