from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from backend.crypto_keys import (
    ensure_test_wallet,
    has_signer,
    import_solana_keypair,
    load_test_pubkey,
)
from backend import crypto_strategy004
from backend import crypto_flash_arb, crypto_trader
from backend.crypto_lab import lab_status, start_lab, stop_lab
from backend.crypto_tx import send_self_transfer
from backend.crypto_contract import (
    NETWORK_DEFAULT,
    RPC_ALLOWLIST,
    append_ledger,
    clear_wallet,
    format_sol,
    format_units,
    load_network,
    load_wallet,
    parse_signal,
    read_ledger,
    save_network,
    save_wallet,
    validate_pubkey,
)


TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
KNOWN_MINTS = {
    "CXk2AMBfi3TwaEL2468s6zP8xq9NxTXjp9gjMgzeUynM": "PYUSD",
}
_RPC_TTL = 20.0
_rpc_bundle: dict[tuple[str, str], tuple[float, int | None, list[dict[str, Any]]]] = {}


def _rpc_url(network: str) -> str:
    return RPC_ALLOWLIST.get(network, RPC_ALLOWLIST[NETWORK_DEFAULT])


def fetch_balance(pubkey: str, network: str = NETWORK_DEFAULT) -> int | None:
    url = _rpc_url(network)
    host = urlparse(url).hostname or ""
    allowed = {urlparse(item).hostname for item in RPC_ALLOWLIST.values()}
    if host not in allowed:
        return None
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBalance",
            "params": [pubkey],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        timeout = 5
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    result = payload.get("result") if isinstance(payload, dict) else None
    value = result.get("value") if isinstance(result, dict) else None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bundle(pubkey: str, network: str, force: bool = False) -> tuple[int | None, list[dict[str, Any]]]:
    key = (pubkey, network)
    now = time.monotonic()
    hit = _rpc_bundle.get(key)
    if not force and hit is not None and now - hit[0] < _RPC_TTL:
        return hit[1], hit[2]
    lamports = fetch_balance(pubkey, network)
    tokens = fetch_tokens(pubkey, network)
    _rpc_bundle[key] = (now, lamports, tokens)
    return lamports, tokens


def invalidate_rpc_cache() -> None:
    _rpc_bundle.clear()


def fetch_tokens(pubkey: str, network: str = NETWORK_DEFAULT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for program in (TOKEN_PROGRAM, TOKEN_2022_PROGRAM):
        payload = rpc_call(
            "getTokenAccountsByOwner",
            [
                pubkey,
                {"programId": program},
                {"encoding": "jsonParsed"},
            ],
            network,
        )
        if not payload or not isinstance(payload.get("result"), dict):
            continue
        for item in payload["result"].get("value") or []:
            if not isinstance(item, dict):
                continue
            account = item.get("account") or {}
            data = (account.get("data") or {}).get("parsed") or {}
            info = data.get("info") or {}
            amount = (info.get("tokenAmount") or {})
            mint = str(info.get("mint") or "")
            raw = str(amount.get("amount") or "0")
            try:
                atomic = int(raw)
                decimals = int(amount.get("decimals") or 0)
            except (TypeError, ValueError):
                continue
            if not mint or atomic <= 0:
                continue
            symbol = KNOWN_MINTS.get(mint, mint[:4] + "…" + mint[-4:])
            display = format_units(atomic, decimals)
            rows.append(
                {
                    "mint": mint,
                    "symbol": symbol,
                    "amount": raw,
                    "decimals": decimals,
                    "display": display,
                    "ata": str(item.get("pubkey") or ""),
                    "program": "token-2022" if program == TOKEN_2022_PROGRAM else "token",
                }
            )
    return rows


def set_network(network: str) -> dict[str, Any]:
    chain = save_network(network)
    wallet = load_wallet()
    pubkey = str(wallet.get("pubkey") or "")
    if pubkey and chain in RPC_ALLOWLIST:
        lamports = fetch_balance(pubkey, chain)
        return save_wallet(pubkey, lamports, chain)
    wallet["network"] = chain
    return wallet


def rpc_call(method: str, params: list[Any], network: str | None = None) -> dict[str, Any] | None:
    chain = network or load_network()
    url = _rpc_url(chain)
    host = urlparse(url).hostname or ""
    allowed = {urlparse(item).hostname for item in RPC_ALLOWLIST.values()}
    if host not in allowed:
        return None
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeError, OSError):
            return {
                "error": {
                    "code": exc.code,
                    "message": "HTTP " + str(exc.code),
                }
            }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def create_test_wallet() -> dict[str, Any]:
    invalidate_rpc_cache()
    save_network("testnet")
    pubkey = ensure_test_wallet()
    lamports = fetch_balance(pubkey, "testnet")
    wallet = save_wallet(pubkey, lamports, "testnet")
    wallet["signer"] = True
    wallet["created"] = True
    return wallet


def airdrop_testnet(lamports: int = 1_000_000_000) -> dict[str, Any]:
    invalidate_rpc_cache()
    save_network("testnet")
    pubkey = load_test_pubkey() or str(load_wallet().get("pubkey") or "")
    if not pubkey:
        pubkey = ensure_test_wallet()
        save_wallet(pubkey, None, "testnet")
    sig = None
    err = None
    used = 0
    for amount in (int(lamports), 100_000_000, 50_000_000):
        payload = rpc_call("requestAirdrop", [pubkey, amount], "testnet")
        used = amount
        if not payload:
            err = "RPC_UNREACHABLE"
            continue
        if payload.get("result"):
            sig = payload.get("result")
            err = None
            break
        fault = payload.get("error")
        if isinstance(fault, dict):
            err = str(fault.get("message") or fault)
        else:
            err = str(fault or "AIRDROP_FAIL")
        if "429" in err or "limit" in err.lower() or "dry" in err.lower():
            break
    time.sleep(1)
    bal = fetch_balance(pubkey, "testnet")
    wallet = save_wallet(pubkey, bal, "testnet")
    note = ""
    if err:
        note = (
            "Public RPC airdrop is dry from this machine. GitHub faucet "
            "rejects new accounts. Open as you (no GitHub): "
            "https://solfaucet.com  or  "
            "https://faucet.quicknode.com/solana/devnet  — paste "
            + pubkey
            + "  Phantom Devnet airdrop also works, then send here."
        )
    row = {
        "ts": int(time.time()),
        "mode": "TESTNET",
        "network": "testnet",
        "side": "airdrop",
        "size_sol": used / 1_000_000_000,
        "symbol": "SOL",
        "source": "devnet-airdrop",
        "txid": str(sig or "NONE"),
        "error": err,
        "hint": note,
        "wallet": pubkey,
    }
    append_ledger(row)
    wallet["airdrop"] = row
    wallet["signer"] = has_signer()
    return wallet


def connect_watch(pubkey: str) -> dict[str, Any]:
    key = validate_pubkey(pubkey)
    chain = load_network()
    lamports = fetch_balance(key, chain) if chain in RPC_ALLOWLIST else None
    return save_wallet(key, lamports, chain)


def ingest_paper_signal(raw: str) -> dict[str, Any]:
    signal = parse_signal(raw)
    wallet = load_wallet()
    chain = load_network()
    live = chain == "mainnet"
    pubkey = str(wallet.get("pubkey") or "")
    row: dict[str, Any] = {
        "ts": int(time.time()),
        "mode": "LIVE" if live else "TESTNET",
        "network": chain,
        "side": signal["side"],
        "size_sol": signal["size_sol"],
        "symbol": signal["symbol"],
        "source": signal["source"],
        "txid": "UNSENT",
        "wallet": pubkey,
    }
    if live:
        row["error"] = "MAINNET_NOT_ARMED"
        row["hint"] = "Import a live keypair after testnet is proven."
        append_ledger(row)
        return row
    if not has_signer():
        row["error"] = "NO_SIGNER"
        row["hint"] = "CREATE TEST WALLET first."
        append_ledger(row)
        return row
    lamports = fetch_balance(pubkey, "testnet") if pubkey else None
    if lamports is None:
        lamports = 0
    tokens = fetch_tokens(pubkey, "testnet") if pubkey else []
    pyusd = next((t for t in tokens if t.get("symbol") == "PYUSD"), None)
    if pyusd:
        row["symbol"] = "PYUSD"
        row["size_display"] = str(pyusd.get("display") or pyusd.get("amount") or "")
    if lamports < 5000:
        row["error"] = "NEED_FEE_SOL"
        row["txid"] = "NONE"
        held = ""
        if pyusd:
            held = (
                str(pyusd.get("ui_amount"))
                + " PYUSD is on-chain. "
            )
        row["hint"] = (
            held
            + "Fee payer still has 0 SOL. Need a few thousand lamports. "
            "Same pubkey: " + pubkey
        )
        append_ledger(row)
        return row
    send_lamports = min(int(signal["size_sol"] * 1_000_000_000), max(1, lamports - 5000))
    if send_lamports > lamports - 5000:
        send_lamports = 1
    try:
        sent = send_self_transfer(rpc_call, send_lamports)
        row["txid"] = sent["txid"]
        row["size_sol"] = send_lamports / 1_000_000_000
        row["source"] = "onchain-self-transfer"
        row["hint"] = "Signed TESTNET transfer. Swap path next."
        invalidate_rpc_cache()
        fresh = fetch_balance(pubkey, "testnet")
        if fresh is not None:
            save_wallet(pubkey, fresh, "testnet")
            row["balance_lamports"] = fresh
            row["balance_sol"] = format_sol(fresh)
    except Exception as exc:
        row["error"] = str(exc)[:240]
        row["txid"] = "NONE"
    append_ledger(row)
    return row


def status_payload() -> dict[str, Any]:
    wallet = load_wallet()
    pubkey = str(wallet.get("pubkey") or "")
    chain = load_network()
    wallet["network"] = chain
    tokens: list[dict[str, Any]] = []
    if pubkey and chain in RPC_ALLOWLIST:
        lamports, tokens = _bundle(pubkey, chain)
        if lamports is not None and lamports != wallet.get("balance_lamports"):
            wallet = save_wallet(pubkey, lamports, chain)
        if lamports is not None:
            wallet["balance_lamports"] = lamports
    wallet["balance_sol"] = format_sol(wallet.get("balance_lamports"))
    wallet["tokens"] = tokens
    pyusd = next((t for t in tokens if t.get("symbol") == "PYUSD"), None)
    if pyusd:
        wallet["pyusd"] = pyusd.get("display")
        wallet["pyusd_decimals"] = pyusd.get("decimals")
    ledger = read_ledger(12)
    last = ledger[-1] if ledger else {}
    legend = "MAINNET" if chain == "mainnet" else "TESTNET"
    rpc = str(RPC_ALLOWLIST.get(chain) or "")
    holdings: list[dict[str, Any]] = []
    if pubkey:
        holdings.append(
            {
                "symbol": "SOL",
                "display": wallet.get("balance_sol") or "—",
                "decimals": 9,
                "mint": "native",
                "program": "system",
            }
        )
        holdings.extend(tokens)
    return {
        "wallet": wallet,
        "legend": legend,
        "rpc": rpc,
        "signer": has_signer(),
        "tokens": tokens,
        "holdings": holdings,
        "last_signal": last,
        "ledger": ledger,
        "lab": lab_status(),
        "bot": load_bot(),
        "arb": crypto_flash_arb.pool_status(),
        "trader": crypto_trader.snapshot(),
        "bots": [
            {
                "id": "signal-swap-1",
                "title": "signal → swap",
                "state": "TESTNET",
            }
        ],
    }


def import_keypair_file(path: str) -> dict[str, Any]:
    pubkey = import_solana_keypair(path)
    chain = load_network()
    lamports = fetch_balance(pubkey, chain) if chain in RPC_ALLOWLIST else None
    wallet = save_wallet(pubkey, lamports, chain)
    wallet["signer"] = True
    wallet["imported"] = True
    return wallet


def disconnect() -> dict[str, Any]:
    return clear_wallet()


def lab_on() -> dict[str, Any]:
    invalidate_rpc_cache()
    start_lab()
    return status_payload()


def lab_off() -> dict[str, Any]:
    stop_lab()
    invalidate_rpc_cache()
    return status_payload()


def run_flash_arb(usd_units: str | None = None) -> dict[str, Any]:
    chain = load_network()
    if chain == "mainnet":
        row = {
            "side": "arb",
            "txid": "UNSENT",
            "error": "MAINNET_NOT_ARMED",
            "hint": "Flash arb stays on lab until you arm mainnet.",
        }
        append_ledger(row)
        payload = status_payload()
        payload["arb_last"] = row
        return payload
    try:
        borrow = int(usd_units) if usd_units not in (None, "") else 10 * 1_000_000
    except (TypeError, ValueError):
        borrow = 10 * 1_000_000
    if borrow <= 0 or borrow > 1_000_000 * 1_000_000:
        raise ValueError("CRYPTO_ARB_SIZE")
    result = crypto_flash_arb.commit_flash_arb(borrow)
    row: dict[str, Any] = {
        "ts": int(time.time()),
        "mode": "TESTNET",
        "network": chain,
        "side": "arb",
        "source": "flash-cpmm",
        "size_sol": 0,
        "symbol": "USDC",
        "txid": "REVERT",
        "profit": format_units(result.get("profit_usd"), 6),
        "buy_pool": result.get("buy_pool"),
        "sell_pool": result.get("sell_pool"),
    }
    if not result.get("ok"):
        row["error"] = str(result.get("error") or "NO_PROFIT")
        row["hint"] = "Atomic revert. Pools unchanged."
        append_ledger(row)
        payload = status_payload()
        payload["arb_last"] = row
        return payload
    lab = lab_status()
    if lab.get("healthy") and has_signer():
        try:
            sent = send_self_transfer(rpc_call, 10_000)
            row["txid"] = sent["txid"]
            row["hint"] = "Arb committed. 10000 lamports settlement on lab."
            invalidate_rpc_cache()
        except Exception as exc:
            row["txid"] = "POOLS_ONLY"
            row["hint"] = "Pools committed. Chain settlement failed: " + str(exc)[:160]
    else:
        row["txid"] = "POOLS_ONLY"
        row["hint"] = "Pools committed. LAB OFF — no chain settlement."
    append_ledger(row)
    payload = status_payload()
    payload["arb_last"] = row
    payload["arb_quote"] = {
        "profit": format_units(result.get("profit_usd"), 6),
        "ok": True,
        "price_a": result.get("price_a_after") or result.get("price_a"),
        "price_b": result.get("price_b_after") or result.get("price_b"),
    }
    return payload


def reset_flash_arb() -> dict[str, Any]:
    crypto_flash_arb.reset_pools()
    payload = status_payload()
    payload["arb_last"] = {"side": "arb", "txid": "RESET"}
    return payload


_KLINE_HOSTS = {"api.binance.com"}
_BOT_NAME = "bot.json"


def _bot_path():
    from backend.crypto_contract import ensure_state_dir

    return ensure_state_dir() / _BOT_NAME


def load_bot() -> dict[str, Any]:
    path = _bot_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "armed": bool(payload.get("armed")),
        "symbol": str(payload.get("symbol") or "SOLUSDT"),
        "size_sol": float(payload.get("size_sol") or 0.01),
        "last": payload.get("last") if isinstance(payload.get("last"), dict) else {},
    }


def save_bot(payload: dict[str, Any]) -> dict[str, Any]:
    path = _bot_path()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return load_bot()


def fetch_klines(interval: str, limit: int) -> tuple[list[float], list[float], list[float], list[float]]:
    url = (
        "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval="
        + interval
        + "&limit="
        + str(int(limit))
    )
    host = urlparse(url).hostname or ""
    if host not in _KLINE_HOSTS:
        raise RuntimeError("CRYPTO_KLINE_HOST")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "gg-ai-desktop-crypto/1"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list) or len(payload) < 40:
        raise RuntimeError("CRYPTO_KLINE")
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    volumes: list[float] = []
    for row in payload:
        highs.append(float(row[2]))
        lows.append(float(row[3]))
        closes.append(float(row[4]))
        volumes.append(float(row[5]))
    return highs, lows, closes, volumes


def fetch_sol_ohlcv() -> tuple[list[float], list[float], list[float], list[float]]:
    return fetch_klines("5m", 200)


def evaluate_signals(
    ohlcv: tuple[list[float], list[float], list[float], list[float]] | None = None
) -> dict[str, Any]:
    if ohlcv is None:
        highs, lows, closes, volumes = fetch_sol_ohlcv()
    else:
        highs, lows, closes, volumes = ohlcv
    report = crypto_strategy004.evaluate(highs, lows, closes, volumes)
    bot = load_bot()
    bot["last"] = report
    save_bot(bot)
    report["armed"] = bot["armed"]
    return report


def set_bot_armed(armed: bool) -> dict[str, Any]:
    bot = load_bot()
    bot["armed"] = bool(armed)
    save_bot(bot)
    payload = status_payload()
    payload["bot"] = load_bot()
    return payload


def tick_bot() -> dict[str, Any]:
    bot = load_bot()
    report = evaluate_signals()
    fired = None
    if bot["armed"] and report.get("super") in ("buy", "sell"):
        fired = ingest_paper_signal(
            json.dumps(
                {
                    "side": report["super"],
                    "size_sol": bot["size_sol"],
                    "symbol": "SOL",
                    "source": "strategy004",
                }
            )
        )
    payload = status_payload()
    payload["signal"] = report
    payload["fired"] = fired
    payload["bot"] = load_bot()
    return payload


def set_trader_armed(armed: bool) -> dict[str, Any]:
    crypto_trader.set_armed(bool(armed))
    payload = status_payload()
    payload["trader"] = crypto_trader.snapshot()
    return payload


def reset_trader() -> dict[str, Any]:
    crypto_trader.reset_book()
    payload = status_payload()
    payload["trader"] = crypto_trader.snapshot()
    return payload


def tick_trader() -> dict[str, Any]:
    h5, l5, c5, v5 = fetch_klines("5m", 200)
    h4, l4, c4, _v4 = fetch_klines("4h", 80)
    sig = crypto_strategy004.evaluate(h5, l5, c5, v5)
    regime = crypto_trader.regime_from_4h(h4, l4, c4)
    atr = crypto_trader.atr_pct(h5, l5, c5)
    book = crypto_trader.tick(c5[-1], sig, regime, atr)
    payload = status_payload()
    payload["signal"] = sig
    payload["trader"] = book
    return payload


def set_trader_armed(armed: bool) -> dict[str, Any]:
    crypto_trader.set_armed(bool(armed))
    payload = status_payload()
    payload["trader"] = crypto_trader.snapshot()
    return payload


def reset_trader() -> dict[str, Any]:
    crypto_trader.reset_book()
    payload = status_payload()
    payload["trader"] = crypto_trader.snapshot()
    return payload


def tick_trader() -> dict[str, Any]:
    h5, l5, c5, v5 = fetch_klines("5m", 200)
    h4, l4, c4, _v4 = fetch_klines("4h", 80)
    sig = crypto_strategy004.evaluate(h5, l5, c5, v5)
    regime = crypto_trader.regime_from_4h(h4, l4, c4)
    atr = crypto_trader.atr_pct(h5, l5, c5)
    book = crypto_trader.tick(c5[-1], sig, regime, atr)
    payload = status_payload()
    payload["signal"] = sig
    payload["trader"] = book
    return payload
