from __future__ import annotations

import json
import threading
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
from backend import crypto_bots, crypto_flash_arb, crypto_trader
from backend.crypto_lab import (
    current_slot,
    has_blockhash,
    lab_status,
    start_lab,
    stop_lab,
    wait_ready,
)
from backend.crypto_tx import confirm_signature, send_self_transfer
from backend.crypto_contract import (
    NETWORK_DEFAULT,
    RPC_ALLOWLIST,
    append_ledger,
    clear_wallet,
    decorate_ledger_row,
    format_sol,
    format_units,
    human_error,
    load_network,
    load_proven,
    load_wallet,
    mark_proven,
    parse_signal,
    read_ledger,
    save_network,
    save_wallet,
    short_error,
    validate_pubkey,
)


LAB_AIRDROP_LAMPORTS = 100 * 1_000_000_000
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
KNOWN_MINTS = {
    "CXk2AMBfi3TwaEL2468s6zP8xq9NxTXjp9gjMgzeUynM": "PYUSD",
}
_RPC_TTL = 20.0
_rpc_bundle: dict[tuple[str, str], tuple[float, int | None, list[dict[str, Any]]]] = {}
_rpc_lock = threading.Lock()
_rpc_inflight: set[tuple[str, str]] = set()


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
            "params": [pubkey, {"commitment": "confirmed"}],
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


def _refresh_bundle(pubkey: str, network: str) -> None:
    key = (pubkey, network)
    try:
        lamports = fetch_balance(pubkey, network)
        tokens = fetch_tokens(pubkey, network)
        _rpc_bundle[key] = (time.monotonic(), lamports, tokens)
    except Exception:
        return
    finally:
        with _rpc_lock:
            _rpc_inflight.discard(key)


def _bundle(pubkey: str, network: str, force: bool = False) -> tuple[int | None, list[dict[str, Any]]]:
    """UI path never waits on RPC. force=True is for an explicit user action."""
    key = (pubkey, network)
    now = time.monotonic()
    hit = _rpc_bundle.get(key)
    if not force and hit is not None and now - hit[0] < _RPC_TTL:
        return hit[1], hit[2]
    if force:
        lamports = fetch_balance(pubkey, network)
        tokens = fetch_tokens(pubkey, network)
        _rpc_bundle[key] = (now, lamports, tokens)
        return lamports, tokens
    with _rpc_lock:
        if key not in _rpc_inflight:
            _rpc_inflight.add(key)
            threading.Thread(
                target=_refresh_bundle,
                args=(pubkey, network),
                daemon=True,
            ).start()
    if hit is not None:
        return hit[1], hit[2]
    return None, []


def invalidate_rpc_cache() -> None:
    _rpc_bundle.clear()


def _lab_gate(wait_s: float = 0.0) -> tuple[bool, str]:
    status = lab_status()
    if status.get("healthy") and (current_slot() or 0) > 0 and has_blockhash():
        return True, ""
    if status.get("running") and wait_s > 0:
        status = wait_ready(wait_s)
        if status.get("healthy") and (current_slot() or 0) > 0 and has_blockhash():
            return True, ""
        return False, "LAB_STARTING"
    if status.get("running"):
        return False, "LAB_STARTING"
    return False, "LAB_OFF"


def _wait_balance_at_least(
    pubkey: str, target: int, timeout_s: float = 8.0
) -> int | None:
    deadline = time.monotonic() + max(0.2, float(timeout_s))
    last: int | None = None
    while time.monotonic() < deadline:
        last = fetch_balance(pubkey, "testnet")
        if last is not None and last >= int(target):
            return last
        time.sleep(0.25)
    return last


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
    ok, _code = _lab_gate(wait_s=8.0)
    if ok and (lamports is None or lamports < 10 * 1_000_000_000):
        funded = airdrop_testnet(LAB_AIRDROP_LAMPORTS)
        funded["created"] = True
        funded["signer"] = True
        return funded
    return wallet


def airdrop_testnet(lamports: int = LAB_AIRDROP_LAMPORTS) -> dict[str, Any]:
    invalidate_rpc_cache()
    save_network("testnet")
    pubkey = load_test_pubkey() or str(load_wallet().get("pubkey") or "")
    if not pubkey:
        pubkey = ensure_test_wallet()
        save_wallet(pubkey, None, "testnet")
    amount = int(lamports)
    row: dict[str, Any] = {
        "ts": int(time.time()),
        "mode": "TESTNET",
        "network": "testnet",
        "side": "airdrop",
        "size_sol": amount / 1_000_000_000,
        "symbol": "SOL",
        "source": "lab-airdrop",
        "txid": "NONE",
        "wallet": pubkey,
    }
    ok, code = _lab_gate(wait_s=20.0)
    if not ok:
        row["error"] = code
        row["hint"] = human_error(code)
        append_ledger(row)
        wallet = load_wallet()
        wallet["airdrop"] = decorate_ledger_row(row)
        wallet["signer"] = has_signer()
        return wallet
    before = fetch_balance(pubkey, "testnet")
    if before is None:
        before = 0
    payload = rpc_call(
        "requestAirdrop",
        [pubkey, amount, {"commitment": "confirmed"}],
        "testnet",
    )
    sig = None
    err = None
    if not payload:
        err = "RPC_UNREACHABLE"
    elif payload.get("result"):
        sig = str(payload.get("result") or "")
    else:
        fault = payload.get("error")
        if isinstance(fault, dict):
            msg = str(fault.get("message") or fault)
            if fault.get("code") == -32603 or "internal" in msg.lower():
                err = "AIRDROP_FAIL"
            else:
                err = short_error(msg) or "AIRDROP_FAIL"
        else:
            err = short_error(str(fault or "")) or "AIRDROP_FAIL"
    wallet = load_wallet()
    if sig:
        landed = confirm_signature(
            lambda method, params: rpc_call(method, params, "testnet"),
            sig,
        )
        target = before + max(1, amount // 2)
        bal = _wait_balance_at_least(pubkey, target, timeout_s=10.0)
        if bal is None:
            bal = fetch_balance(pubkey, "testnet")
        wallet = save_wallet(pubkey, bal, "testnet")
        row["txid"] = sig
        if bal is not None and bal > before:
            row["hint"] = (
                "Lab airdrop landed. "
                + format_sol(before)
                + " → "
                + format_sol(bal)
                + " SOL"
            )
            mark_proven("airdrop", sig)
        else:
            row["error"] = "AIRDROP_FAIL"
            row["hint"] = (
                "Airdrop did not raise the balance. "
                + ("Signature not confirmed. " if not landed else "")
                + "Toggle LAB OFF/ON if the chain is stuck."
            )
        if bal is not None:
            row["balance_lamports"] = bal
            row["balance_sol"] = format_sol(bal)
    else:
        row["error"] = err or "AIRDROP_FAIL"
        row["hint"] = human_error(row["error"])
        bal = fetch_balance(pubkey, "testnet")
        wallet = save_wallet(pubkey, bal, "testnet")
    append_ledger(row)
    wallet["airdrop"] = decorate_ledger_row(row)
    wallet["signer"] = has_signer()
    wallet["balance_sol"] = format_sol(wallet.get("balance_lamports"))
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
        row["hint"] = human_error("MAINNET_NOT_ARMED")
        append_ledger(row)
        return decorate_ledger_row(row)
    if not has_signer():
        row["error"] = "NO_SIGNER"
        row["hint"] = human_error("NO_SIGNER")
        append_ledger(row)
        return decorate_ledger_row(row)
    ok, code = _lab_gate(wait_s=12.0)
    if not ok:
        row["error"] = code
        row["txid"] = "NONE"
        row["hint"] = human_error(code)
        append_ledger(row)
        return decorate_ledger_row(row)
    lamports = fetch_balance(pubkey, "testnet") if pubkey else None
    if lamports is None:
        row["error"] = "RPC_UNREACHABLE"
        row["txid"] = "NONE"
        row["hint"] = human_error("RPC_UNREACHABLE")
        append_ledger(row)
        return decorate_ledger_row(row)
    tokens = fetch_tokens(pubkey, "testnet") if pubkey else []
    pyusd = next((t for t in tokens if t.get("symbol") == "PYUSD"), None)
    if pyusd:
        row["symbol"] = "PYUSD"
        row["size_display"] = str(pyusd.get("display") or pyusd.get("amount") or "")
    if lamports < 5000:
        row["error"] = "NEED_FEE_SOL"
        row["txid"] = "NONE"
        row["hint"] = human_error("NEED_FEE_SOL")
        append_ledger(row)
        return decorate_ledger_row(row)
    send_lamports = min(int(signal["size_sol"] * 1_000_000_000), max(1, lamports - 5000))
    if send_lamports > lamports - 5000:
        send_lamports = 1
    try:
        sent = send_self_transfer(rpc_call, send_lamports)
        row["txid"] = sent["txid"]
        row["size_sol"] = send_lamports / 1_000_000_000
        row["source"] = "onchain-self-transfer"
        row["hint"] = (
            "Signed lab fill. Self-transfer "
            + format_sol(send_lamports)
            + " SOL."
        )
        invalidate_rpc_cache()
        fresh = fetch_balance(pubkey, "testnet")
        if fresh is not None:
            save_wallet(pubkey, fresh, "testnet")
            row["balance_lamports"] = fresh
            row["balance_sol"] = format_sol(fresh)
        mark_proven("buy", sent["txid"])
    except Exception as exc:
        row["error"] = short_error(str(exc)[:240]) or "CRYPTO_RPC"
        row["hint"] = human_error(str(exc)[:240])
        row["txid"] = "NONE"
    append_ledger(row)
    return decorate_ledger_row(row)


def status_payload(rail: bool = False) -> dict[str, Any]:
    wallet = load_wallet()
    pubkey = str(wallet.get("pubkey") or "")
    chain = load_network()
    wallet["network"] = chain
    tokens: list[dict[str, Any]] = []
    if pubkey and chain in RPC_ALLOWLIST:
        lamports, tokens = _bundle(pubkey, chain, force=False)
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
    if rail:
        from backend.crypto_lab import running_pid

        pid = running_pid()
        return {
            "wallet": {
                "pubkey": pubkey,
                "label": wallet.get("label") or "",
                "balance_sol": wallet.get("balance_sol"),
                "network": chain,
            },
            "legend": legend,
            "signer": has_signer(),
            "holdings": holdings[:8],
            "lab": {
                "running": pid is not None,
                "healthy": False,
                "pid": pid,
                "label": "LAB STARTING" if pid is not None else "LAB OFF",
            },
        }
    ledger = [decorate_ledger_row(item) for item in read_ledger(16)]
    for lot in crypto_trader.read_lots(16):
        side = str(lot.get("side") or "")
        if side not in ("buy", "sell"):
            continue
        hint = str(lot.get("venue") or "vault")
        if side == "buy":
            hint = "Vault float buy " + format_sol(lot.get("sol"))
        else:
            hint = "Vault sell, profit " + format_units(lot.get("profit_usd"), 6)
        ledger.append(
            decorate_ledger_row(
                {
                    "ts": lot.get("ts"),
                    "side": side,
                    "txid": str(lot.get("id") or "LOT"),
                    "hint": hint,
                    "source": "trader-80-20",
                    "mode": "TESTNET",
                    "error": None,
                }
            )
        )
    ledger.sort(key=lambda item: int(item.get("ts") or 0))
    if chain != "mainnet":
        ledger = [
            item
            for item in ledger
            if str(item.get("error") or "") != "MAINNET_NOT_ARMED"
            and "Mainnet stays locked" not in str(item.get("hint") or "")
        ]
    ledger = ledger[-16:]
    last = ledger[-1] if ledger else {}
    chart = chart_snapshot()
    bot = load_bot()
    if not bot.get("closes") and chart.get("closes"):
        bot = dict(bot)
        bot["closes"] = list(chart["closes"])
    quote = quote_for_wallet(wallet)
    if holdings and quote.get("usd"):
        holdings[0]["usd"] = quote.get("usd")
        holdings[0]["sek"] = quote.get("sek")
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
        "bot": bot,
        "chart": chart,
        "quote": quote,
        "arb": crypto_flash_arb.pool_status(),
        "trader": dict(crypto_trader.snapshot(), books=crypto_bots.catalog()),
        "backtest_job": backtest_job(),
        "proven": load_proven(),
        "bots": [
            {
                "id": "signal-swap-1",
                "title": "signal → swap",
                "state": "TESTNET",
            },
            {
                "id": "trader-80-20",
                "title": "cycle + day/week/month swings",
                "state": "ARMED" if crypto_trader.load_state().get("armed") else "IDLE",
            },
            {
                "id": "flash-cpmm",
                "title": "lab CPMM",
                "state": "LAB",
            },
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
    status = start_lab()
    if status.get("healthy"):
        mark_proven("lab")
        crypto_trader.set_armed(True)
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
            "hint": human_error("MAINNET_NOT_ARMED"),
        }
        append_ledger(row)
        payload = status_payload()
        payload["arb_last"] = decorate_ledger_row(row)
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
        row["hint"] = human_error(row["error"])
        append_ledger(row)
        payload = status_payload()
        payload["arb_last"] = decorate_ledger_row(row)
        return payload
    mark_proven("arb")
    lab = lab_status()
    if lab.get("healthy") and has_signer():
        try:
            sent = send_self_transfer(rpc_call, 10_000)
            row["txid"] = sent["txid"]
            row["hint"] = "Arb committed. 10000 lamports settlement on lab."
            invalidate_rpc_cache()
        except Exception as exc:
            row["txid"] = "POOLS_ONLY"
            row["hint"] = "Pools committed. Settlement: " + human_error(str(exc)[:160])
    else:
        row["txid"] = "POOLS_ONLY"
        row["hint"] = "Pools committed on lab CPMM. Chain settlement needs LAB ON."
    append_ledger(row)
    payload = status_payload()
    payload["arb_last"] = decorate_ledger_row(row)
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
_CHART_HOSTS = frozenset(
    {"api.binance.com", "api.coingecko.com", "api.frankfurter.app"}
)
_CHART_TTL = 15.0
_chart_cache: dict[str, Any] = {
    "ts": 0.0,
    "closes": [],
    "times": [],
    "price": "",
    "source": "",
    "interval": "",
    "usd_sek": 0.0,
}
_kline_times: dict[str, list[int]] = {}
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
    closes = payload.get("closes")
    if not isinstance(closes, list):
        closes = []
    out_closes: list[float] = []
    for item in closes[-80:]:
        try:
            out_closes.append(float(item))
        except (TypeError, ValueError):
            continue
    return {
        "armed": bool(payload.get("armed")),
        "symbol": str(payload.get("symbol") or "SOLUSDT"),
        "size_sol": float(payload.get("size_sol") or 0.01),
        "last": payload.get("last") if isinstance(payload.get("last"), dict) else {},
        "closes": out_closes,
    }


def save_bot(payload: dict[str, Any]) -> dict[str, Any]:
    path = _bot_path()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return load_bot()


def fetch_klines(
    interval: str,
    limit: int,
    timeout: float = 12.0,
    start_time: int | None = None,
) -> tuple[list[float], list[float], list[float], list[float]]:
    url = (
        "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval="
        + str(interval)
        + "&limit="
        + str(int(limit))
    )
    if start_time is not None:
        url += "&startTime=" + str(int(start_time))
    host = urlparse(url).hostname or ""
    if host not in _KLINE_HOSTS:
        raise RuntimeError("CRYPTO_KLINE_HOST")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "gg-ai-desktop-crypto/1"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=float(timeout)) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if start_time is not None:
        need = 1
    else:
        need = min(40, max(8, int(limit)))
    if not isinstance(payload, list) or len(payload) < need:
        raise RuntimeError("CRYPTO_KLINE")
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    volumes: list[float] = []
    times: list[int] = []
    for row in payload:
        highs.append(float(row[2]))
        lows.append(float(row[3]))
        closes.append(float(row[4]))
        volumes.append(float(row[5]))
        times.append(int(row[0]) // 1000)
    _kline_times[str(interval)] = times
    return highs, lows, closes, volumes


SOL_LISTED_MS = 1597104000000
_HISTORY_NAME = "sol-klines-1h.json"


def _history_path(interval: str = "1h"):
    from backend.crypto_contract import ensure_state_dir

    name = "sol-klines-" + str(interval).replace("/", "") + ".json"
    return ensure_state_dir() / name


def fetch_klines_history(
    interval: str = "1h",
    start_ms: int = SOL_LISTED_MS,
    timeout: float = 12.0,
) -> tuple[list[float], list[float], list[float], list[float], list[int]]:
    path = _history_path(interval)
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        cached = {}
    if str(cached.get("interval") or interval) != str(interval):
        cached = {}
    highs = [float(x) for x in (cached.get("highs") or [])]
    lows = [float(x) for x in (cached.get("lows") or [])]
    closes = [float(x) for x in (cached.get("closes") or [])]
    volumes = [float(x) for x in (cached.get("volumes") or [])]
    times = [int(x) for x in (cached.get("times") or [])]
    cursor = start_ms
    if times:
        cursor = max(cursor, times[-1] * 1000 + 1)
    now_ms = int(time.time() * 1000)
    pages = 0
    # Full SOLUSDT listing: ~6y. 1m ≈ 3150 pages, 5m ≈ 640.
    page_cap = {
        "1m": 3400,
        "5m": 720,
        "15m": 250,
        "1h": 80,
        "4h": 40,
        "8h": 20,
        "1d": 10,
    }.get(str(interval), 80)
    checkpoint_every = 250 if str(interval) == "1m" else (80 if str(interval) == "5m" else 0)

    def _persist() -> None:
        if not closes:
            return
        blob = json.dumps(
            {
                "interval": interval,
                "highs": highs,
                "lows": lows,
                "closes": closes,
                "volumes": volumes,
                "times": times,
            },
            separators=(",", ":"),
        )
        path.write_text(blob + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    while cursor < now_ms and pages < page_cap:
        url = (
            "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval="
            + str(interval)
            + "&limit=1000&startTime="
            + str(int(cursor))
        )
        host = urlparse(url).hostname or ""
        if host not in _KLINE_HOSTS:
            raise RuntimeError("CRYPTO_KLINE_HOST")
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "gg-ai-desktop-crypto/1"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=float(timeout)) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if int(getattr(exc, "code", 0) or 0) in (418, 429):
                time.sleep(20.0)
                continue
            break
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
            break
        if not isinstance(payload, list) or not payload:
            break
        last_open = None
        for row in payload:
            try:
                open_ms = int(row[0])
                high = float(row[2])
                low = float(row[3])
                close = float(row[4])
                vol = float(row[5])
            except (TypeError, ValueError, IndexError):
                continue
            ts = open_ms // 1000
            if times and ts <= times[-1]:
                continue
            highs.append(high)
            lows.append(low)
            closes.append(close)
            volumes.append(vol)
            times.append(ts)
            last_open = open_ms
        pages += 1
        if checkpoint_every and pages % checkpoint_every == 0:
            _persist()
        if last_open is None or len(payload) < 1000:
            break
        cursor = last_open + 1
        time.sleep(0.08)
    _persist()
    if len(closes) < 80:
        raise RuntimeError("CRYPTO_HISTORY")
    return highs, lows, closes, volumes, times


def fetch_sol_ohlcv() -> tuple[list[float], list[float], list[float], list[float]]:
    return fetch_klines("5m", 200)


def _coingecko_sol_chart() -> tuple[list[float], list[int]]:
    url = (
        "https://api.coingecko.com/api/v3/coins/solana/market_chart"
        "?vs_currency=usd&days=3"
    )
    host = urlparse(url).hostname or ""
    if host not in _CHART_HOSTS:
        raise RuntimeError("CRYPTO_CHART_HOST")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "gg-ai-desktop-crypto/1"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=3.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = payload.get("prices") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) < 8:
        raise RuntimeError("CRYPTO_CHART")
    closes: list[float] = []
    times: list[int] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        try:
            times.append(int(float(row[0]) / 1000.0))
            closes.append(round(float(row[1]), 4))
        except (TypeError, ValueError):
            continue
    if len(closes) < 8:
        raise RuntimeError("CRYPTO_CHART")
    return closes[-80:], times[-80:]


def _coingecko_sol_closes() -> list[float]:
    return _coingecko_sol_chart()[0]


def _usd_sek_rate() -> float:
    url = "https://api.frankfurter.app/latest?from=USD&to=SEK"
    host = urlparse(url).hostname or ""
    if host not in _CHART_HOSTS:
        raise RuntimeError("CRYPTO_FX_HOST")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "gg-ai-desktop-crypto/1"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=3.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rates = payload.get("rates") if isinstance(payload, dict) else None
    if not isinstance(rates, dict):
        raise RuntimeError("CRYPTO_FX")
    rate = float(rates.get("SEK") or 0)
    if rate <= 0:
        raise RuntimeError("CRYPTO_FX")
    return round(rate, 4)


def format_usd(value: float) -> str:
    return "$" + f"{max(0.0, float(value)):,.2f}"


def format_sek(value: float) -> str:
    n = int(round(max(0.0, float(value))))
    grouped = f"{n:,}".replace(",", " ")
    return grouped + " kr"


def _sol_float(wallet: dict[str, Any]) -> float:
    raw = str(wallet.get("balance_sol") or "").replace(" ", "").replace(",", "")
    try:
        if raw:
            return float(raw)
    except (TypeError, ValueError):
        pass
    try:
        return int(wallet.get("balance_lamports") or 0) / 1_000_000_000
    except (TypeError, ValueError):
        return 0.0


def quote_for_wallet(wallet: dict[str, Any]) -> dict[str, Any]:
    snap = chart_snapshot()
    try:
        px = float(snap.get("price") or 0)
    except (TypeError, ValueError):
        px = 0.0
    try:
        usd_sek = float(snap.get("usd_sek") or _chart_cache.get("usd_sek") or 0)
    except (TypeError, ValueError):
        usd_sek = 0.0
    sol = _sol_float(wallet)
    usd = sol * px
    sek = usd * usd_sek if usd_sek > 0 else 0.0
    return {
        "sol_usd": px,
        "usd_sek": usd_sek,
        "sol": sol,
        "value_usd": round(usd, 2),
        "value_sek": round(sek, 0),
        "usd": format_usd(usd) if px > 0 else "",
        "sek": format_sek(sek) if px > 0 and usd_sek > 0 else "",
        "source": str(snap.get("source") or ""),
    }


def _chart_path():
    from backend.crypto_contract import ensure_state_dir

    return ensure_state_dir() / "sol-chart.json"


def _load_chart_disk() -> None:
    path = _chart_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return
    if not isinstance(payload, dict):
        return
    rows = payload.get("closes")
    if not isinstance(rows, list) or len(rows) < 2:
        return
    stamps = payload.get("times")
    if not isinstance(stamps, list) or len(stamps) != len(rows):
        stamps = [0] * len(rows)
    closes: list[float] = []
    times: list[int] = []
    for item, stamp in list(zip(rows, stamps))[-80:]:
        try:
            closes.append(float(item))
            times.append(int(stamp or 0))
        except (TypeError, ValueError):
            continue
    if len(closes) < 2:
        return
    if any(stamp <= 0 for stamp in times):
        times = []
    _chart_cache["closes"] = closes
    _chart_cache["times"] = times
    _chart_cache["price"] = str(payload.get("price") or closes[-1])
    _chart_cache["source"] = str(payload.get("source") or "")
    _chart_cache["interval"] = str(payload.get("interval") or "")
    try:
        _chart_cache["usd_sek"] = float(payload.get("usd_sek") or 0)
    except (TypeError, ValueError):
        _chart_cache["usd_sek"] = 0.0
    _chart_cache["ts"] = 0.0


def _save_chart_disk() -> None:
    path = _chart_path()
    blob = json.dumps(
        {
            "closes": _chart_cache.get("closes") or [],
            "times": _chart_cache.get("times") or [],
            "price": _chart_cache.get("price") or "",
            "source": _chart_cache.get("source") or "",
            "interval": _chart_cache.get("interval") or "",
            "usd_sek": _chart_cache.get("usd_sek") or 0,
        },
        separators=(",", ":"),
    )
    path.write_text(blob + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def chart_snapshot() -> dict[str, Any]:
    if not _chart_cache.get("closes"):
        _load_chart_disk()
    return {
        "closes": list(_chart_cache.get("closes") or []),
        "times": list(_chart_cache.get("times") or []),
        "price": str(_chart_cache.get("price") or ""),
        "source": str(_chart_cache.get("source") or ""),
        "interval": str(_chart_cache.get("interval") or ""),
        "usd_sek": float(_chart_cache.get("usd_sek") or 0),
    }


def _set_live_chart(
    closes: list[float],
    times: list[int],
    source: str,
    interval: str = "15m",
    live: float | None = None,
) -> None:
    if len(closes) < 2:
        return
    out = [round(float(item), 4) for item in closes[-80:]]
    stamps = [int(item) for item in times[-len(out):]] if times else []
    if stamps and len(stamps) != len(out):
        stamps = []
    if live is not None:
        try:
            px = round(float(live), 4)
            if px > 0:
                out[-1] = px
        except (TypeError, ValueError):
            pass
    _chart_cache["closes"] = out
    _chart_cache["times"] = stamps
    _chart_cache["price"] = str(out[-1])
    _chart_cache["source"] = source
    _chart_cache["interval"] = interval
    _chart_cache["ts"] = time.monotonic()
    _save_chart_disk()


def _ingest_spark(
    frames: dict[str, tuple[list[float], list[float], list[float], list[float]]],
    live: float | None = None,
) -> None:
    for tf in ("15m", "5m", "1h"):
        got = frames.get(tf)
        if got is None or len(got[2]) < 8:
            continue
        closes = [round(float(item), 4) for item in got[2][-80:]]
        stamps = [int(item) for item in (_kline_times.get(tf) or [])[-len(closes):]]
        _set_live_chart(closes, stamps, "binance", interval=tf, live=live)
        return


def cached_sol_chart() -> dict[str, Any]:
    now = time.monotonic()
    cached = _chart_cache["closes"]
    stamps = list(_chart_cache.get("times") or [])
    if (
        isinstance(cached, list)
        and cached
        and len(stamps) == len(cached)
        and now - float(_chart_cache["ts"] or 0) < _CHART_TTL
    ):
        return chart_snapshot()
    if not cached:
        _load_chart_disk()
        cached = _chart_cache["closes"]
    closes: list[float] = []
    times: list[int] = []
    source = ""
    interval = "15m"
    try:
        _highs, _lows, raw, _vols = fetch_klines("15m", 80, timeout=3.0)
        closes = [round(float(item), 4) for item in raw[-80:]]
        times = [int(item) for item in (_kline_times.get("15m") or [])[-len(closes):]]
        source = "binance"
    except (OSError, RuntimeError, TypeError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        try:
            closes, times = _coingecko_sol_chart()
            source = "coingecko"
            interval = "cg"
        except (OSError, RuntimeError, TypeError, ValueError, urllib.error.URLError, json.JSONDecodeError):
            closes = list(cached) if isinstance(cached, list) else []
            times = list(_chart_cache.get("times") or [])
            source = str(_chart_cache.get("source") or "")
            interval = str(_chart_cache.get("interval") or "")
    if closes:
        _set_live_chart(closes, times, source, interval=interval)
        try:
            rate = _usd_sek_rate()
            if rate > 0:
                _chart_cache["usd_sek"] = rate
        except (OSError, RuntimeError, TypeError, ValueError, urllib.error.URLError, json.JSONDecodeError):
            pass
        _save_chart_disk()
    return chart_snapshot()


def _ohlcv_from_closes(closes: list[float]) -> tuple[list[float], list[float], list[float], list[float]]:
    rows = [float(item) for item in closes]
    if len(rows) < 8:
        raise RuntimeError("NO_MARKET_DATA")
    if len(rows) < 80:
        rows = [rows[0]] * (80 - len(rows)) + rows
    highs = [item * 1.002 for item in rows]
    lows = [item * 0.998 for item in rows]
    vols = [1.0] * len(rows)
    return highs, lows, rows, vols


def _ohlcv_for_eval() -> tuple[list[float], list[float], list[float], list[float]]:
    try:
        return fetch_sol_ohlcv()
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        urllib.error.URLError,
        json.JSONDecodeError,
    ):
        snap = chart_snapshot()
        raw = snap.get("closes") or []
        closes: list[float] = []
        for item in raw:
            try:
                closes.append(float(item))
            except (TypeError, ValueError):
                continue
        return _ohlcv_from_closes(closes)


def evaluate_signals(
    ohlcv: tuple[list[float], list[float], list[float], list[float]] | None = None
) -> dict[str, Any]:
    closes: list[float] = []
    try:
        if ohlcv is None:
            highs, lows, closes, volumes = _ohlcv_for_eval()
        else:
            highs, lows, closes, volumes = ohlcv
        report = crypto_strategy004.evaluate(highs, lows, closes, volumes)
        mark_proven("bot")
    except Exception as exc:
        token = short_error(str(exc)[:120]) or "NO_MARKET_DATA"
        if "KLINE" in str(exc) or "CANDLES" in str(exc) or "CHART" in str(exc):
            token = "NO_MARKET_DATA"
        report = {
            "strategy": "Strategy004",
            "super": "none",
            "buy_votes": 0,
            "sell_votes": 0,
            "notes": [human_error(token)],
            "error": token,
        }
    bot = load_bot()
    bot["last"] = report
    if closes:
        bot["closes"] = [round(float(item), 4) for item in closes[-80:]]
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
    if (
        bot["armed"]
        and report.get("super") in ("buy", "sell")
        and not report.get("error")
    ):
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


def set_trader_book(book_id: str) -> dict[str, Any]:
    crypto_bots.set_book(book_id)
    payload = status_payload()
    payload["trader"] = dict(crypto_trader.snapshot(), books=crypto_bots.catalog())
    return payload


def _trader_ohlcv() -> tuple[list[float], list[float], list[float], list[float]]:
    try:
        return fetch_klines("5m", 200, timeout=8.0)
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        urllib.error.URLError,
        json.JSONDecodeError,
    ):
        return _ohlcv_for_eval()


def _fetch_tf(interval: str, limit: int = 240) -> tuple[list[float], list[float], list[float], list[float]] | None:
    try:
        return fetch_klines(interval, limit, timeout=6.0)
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        urllib.error.URLError,
        json.JSONDecodeError,
    ):
        return None


def tick_trader() -> dict[str, Any]:
    try:
        tf_osc: dict[str, dict[str, Any]] = {}
        frames: dict[str, tuple[list[float], list[float], list[float], list[float]]] = {}
        votes: dict[str, str] = {}
        tf_flow: dict[str, str] = {}
        for tf in crypto_trader.TIMEFRAMES:
            got = _fetch_tf(tf)
            if got is None:
                votes[tf] = "none"
                continue
            frames[tf] = got
            snap = crypto_trader.osc_last(got[0], got[1], got[2], got[3])
            tf_osc[tf] = snap
            try:
                series = crypto_trader.signal_series(got[0], got[1], got[2], got[3])
                votes[tf] = series[-1] if series else "none"
            except (ValueError, TypeError, IndexError):
                rsi_v = snap.get("rsi")
                if crypto_trader.in_buy_band(rsi_v):
                    votes[tf] = "buy"
                elif crypto_trader.in_sell_band(rsi_v):
                    votes[tf] = "sell"
                else:
                    votes[tf] = "none"
            if len(got[2]) >= 40:
                tf_flow[tf] = crypto_trader.regime_from_4h(got[0], got[1], got[2])
            else:
                tf_flow[tf] = "range"
        h1 = frames.get("1h")
        h5 = frames.get("5m") or frames.get("15m") or frames.get("1m") or h1
        if h1 is not None and len(h1[2]) >= 40:
            regime = crypto_trader.regime_from_4h(h1[0], h1[1], h1[2])
        elif h5 is not None:
            rh, rl, rc = crypto_trader.resample_ohlc(h5[0], h5[1], h5[2], 12)
            regime = crypto_trader.regime_from_4h(rh or h5[0], rl or h5[1], rc or h5[2])
        else:
            raise RuntimeError("NO_MARKET_DATA")
        px_tf = frames.get("1m") or frames.get("5m") or h1
        if px_tf is None:
            raise RuntimeError("NO_MARKET_DATA")
        atr = crypto_trader.atr_pct(px_tf[0], px_tf[1], px_tf[2])
        sig = {
            "super": votes.get("1m") or votes.get("5m") or "none",
            "mtf": votes,
            "flow": tf_flow,
            "notes": [tf + " rsi " + str((tf_osc.get(tf) or {}).get("rsi")) for tf in crypto_trader.TIMEFRAMES],
            "strategy": "weighted-mtf-flow",
        }
        book = crypto_trader.tick(
            px_tf[2][-1],
            sig,
            regime,
            atr,
            execute_contracts=True,
            tf_osc=tf_osc,
            tf_super=votes,
            tf_flow=tf_flow,
        )
        try:
            _ingest_spark(frames, live=float(px_tf[2][-1]))
        except (TypeError, ValueError, IndexError):
            _ingest_spark(frames)
        last = dict(book.get("last") if isinstance(book.get("last"), dict) else {})
        last["mtf"] = votes
        book["last"] = last
        book["mtf"] = votes
        if last.get("action") in ("buy", "sell"):
            row = {
                "ts": int(time.time()),
                "mode": "TESTNET",
                "network": "testnet",
                "side": last.get("action"),
                "source": "trader-80-20",
                "txid": "VAULT",
                "hint": str(last.get("note") or ""),
            }
            if lab_status().get("healthy") and has_signer():
                try:
                    sent = send_self_transfer(rpc_call, 5_000)
                    last = dict(last)
                    last["txid"] = sent.get("txid")
                    book["last"] = last
                    row["txid"] = sent.get("txid")
                except Exception:
                    pass
            append_ledger(row)
    except Exception as exc:
        token = short_error(str(exc)[:120]) or "NO_MARKET_DATA"
        if "KLINE" in str(exc) or "CANDLES" in str(exc) or "CHART" in str(exc):
            token = "NO_MARKET_DATA"
        sig = {
            "strategy": "Strategy004",
            "super": "none",
            "error": token,
            "notes": [human_error(token)],
        }
        book = dict(crypto_trader.snapshot())
        last = dict(book.get("last") or {})
        last["action"] = "none"
        last["note"] = human_error(token)
        book["last"] = last
    payload = status_payload()
    payload["signal"] = sig
    payload["trader"] = book
    return payload


_backtest_lock = threading.Lock()
_backtest_job: dict[str, Any] = {
    "state": "idle",
    "note": "",
    "started": 0.0,
}
_UI_BACKTEST_TF = crypto_trader.TIMEFRAMES


def backtest_job() -> dict[str, Any]:
    with _backtest_lock:
        return dict(_backtest_job)


def start_backtest_trader() -> dict[str, Any]:
    launch = False
    with _backtest_lock:
        already = str(_backtest_job.get("state") or "") == "running"
        if not already:
            _backtest_job["state"] = "running"
            _backtest_job["note"] = (
                crypto_bots.selected() + " · 1h clock, off the UI thread"
            )
            _backtest_job["started"] = time.time()
            launch = True
    if launch:
        threading.Thread(
            target=_run_backtest_job, name="gg-crypto-backtest", daemon=True
        ).start()
    payload = status_payload()
    payload["backtest_job"] = backtest_job()
    return payload


def _run_backtest_job() -> None:
    try:
        backtest_trader(tfs=_UI_BACKTEST_TF)
        with _backtest_lock:
            _backtest_job["state"] = "done"
            _backtest_job["note"] = ""
    except Exception as exc:
        token = short_error(str(exc)[:120]) or "NO_MARKET_DATA"
        with _backtest_lock:
            _backtest_job["state"] = "error"
            _backtest_job["note"] = human_error(token)


def backtest_trader(tfs: tuple[str, ...] | None = None) -> dict[str, Any]:
    frames: dict[str, dict[str, Any]] = {}
    names = tfs or ("1m", "5m", "15m", "1h", "4h", "8h", "1d")
    if names == crypto_trader.TIMEFRAMES:
        names = tuple(tf for tf in names if tf not in ("1m", "5m"))
    for tf in names:
        try:
            h, l, c, v, times = fetch_klines_history(tf)
            frames[tf] = {
                "highs": h,
                "lows": l,
                "closes": c,
                "volumes": v,
                "times": times,
            }
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ):
            continue
    try:
        if len(frames) >= 1:
            report = crypto_bots.run_backtest(frames)
            report["range"] = "2020-2026 " + "+".join(
                tf for tf in crypto_trader.TIMEFRAMES if tf in frames
            )
        else:
            raise RuntimeError("CRYPTO_HISTORY")
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        urllib.error.URLError,
        json.JSONDecodeError,
    ) as exc:
        if crypto_bots.selected() == "hybrid":
            raise RuntimeError("HYBRID_BACKTEST:" + (str(exc)[:180] or "FAILED")) from exc
        h5, l5, c5, v5 = _ohlcv_for_eval()
        report = crypto_trader.run_backtest(h5, l5, c5, v5)
        report["range"] = "cache-5m"
    payload = status_payload()
    payload["backtest"] = report
    trader = dict(payload.get("trader") or {})
    trader["backtest"] = report
    trader["books"] = crypto_bots.catalog()
    trader["book"] = crypto_bots.selected()
    payload["trader"] = trader
    return payload
