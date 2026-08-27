#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from backend import crypto_contract, crypto_flash_arb


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="gg-arb-"))
    crypto_contract.STATE_DIR = tmp
    crypto_flash_arb.reset_pools()
    first = crypto_flash_arb.commit_flash_arb(10 * 1_000_000)
    if not first.get("ok") or not first.get("committed"):
        raise AssertionError("seeded arb must profit: " + json.dumps(first)[:400])
    if int(first["profit_usd"]) <= 0:
        raise AssertionError("profit")
    equal = {
        "A": {"sol": 1000 * 10**9, "usd": 100_000 * 10**6},
        "B": {"sol": 1000 * 10**9, "usd": 100_000 * 10**6},
        "fee_bps": 30,
        "flash_bps": 9,
    }
    crypto_flash_arb.save_pools(equal)
    dead = crypto_flash_arb.commit_flash_arb(10 * 1_000_000)
    if dead.get("ok") or dead.get("committed"):
        raise AssertionError("equal pools must revert")
    if dead.get("error") != "NO_PROFIT":
        raise AssertionError("error tag " + str(dead.get("error")))
    print("CRYPTO_FLASH_ARB_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
