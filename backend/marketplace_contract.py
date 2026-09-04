from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.crypto_contract import (
    format_sol,
    load_network,
    load_wallet,
    short_pubkey,
    validate_pubkey,
)
from backend.domain_merkle import (
    MerkleChild,
    build_domain_root,
    digest_json,
    leaf,
    subtree,
)


SCHEMA = "gg.ai-desktop.marketplace-status.v1"
LISTING_SCHEMA = "gg.ai-desktop.marketplace-listing.v1"
LEDGER_SCHEMA = "gg.ai-desktop.marketplace-ledger.v1"
STATE_DIR = Path("/home/GG/.local/state/goldgoblins/gg-ai-desktop/marketplace")
CATALOG_NAME = "catalog.json"
LEDGER_NAME = "ledger.jsonl"
PREFS_NAME = "prefs.json"
MERKLE_NAME = "merkle.json"
MAX_LISTINGS = 2000
MAX_TITLE = 96
MAX_DESCRIPTION = 480
MAX_LEDGER = 400
DOMAIN = "MARKETPLACE"
SCOPE = "solana.catalog"
CATEGORIES = (
    "MATERIAL",
    "ITEM",
    "ART",
    "COLLECTIBLE",
    "DOCUMENT",
    "TOOL",
    "COMPONENT",
)
MATERIALS = (
    "GOLD",
    "SILVER",
    "COPPER",
    "WOOD",
    "STONE",
    "FABRIC",
    "METAL",
    "DIGITAL",
    "MIXED",
    "UNKNOWN",
)
STATUSES = ("DRAFT", "LISTED", "DELISTED", "SOLD")
FILTERS = ("ALL",) + CATEGORIES
SOL_LAMPORTS = 1_000_000_000
MAX_PRICE_SOL = 1_000_000


def ensure_state_dir() -> Path:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return STATE_DIR


def catalog_path() -> Path:
    return ensure_state_dir() / CATALOG_NAME


def ledger_path() -> Path:
    return ensure_state_dir() / LEDGER_NAME


def prefs_path() -> Path:
    return ensure_state_dir() / PREFS_NAME


def merkle_path() -> Path:
    return ensure_state_dir() / MERKLE_NAME


def parse_sol_price(raw: str | int | float | None) -> int:
    if isinstance(raw, int):
        if raw < 0 or raw > MAX_PRICE_SOL * SOL_LAMPORTS:
            raise ValueError("MARKETPLACE_PRICE")
        return raw
    if isinstance(raw, float):
        if raw < 0 or raw > MAX_PRICE_SOL:
            raise ValueError("MARKETPLACE_PRICE")
        return int(round(raw * SOL_LAMPORTS))
    text = str(raw or "0").strip()
    if not text:
        return 0
    if text.startswith("-"):
        raise ValueError("MARKETPLACE_PRICE")
    if "." in text:
        whole, frac = text.split(".", 1)
        if not whole:
            whole = "0"
        frac = (frac + "000000000")[:9]
        if not whole.isdigit() or not frac.isdigit():
            raise ValueError("MARKETPLACE_PRICE")
        lamports = int(whole) * SOL_LAMPORTS + int(frac)
    else:
        if not text.isdigit():
            raise ValueError("MARKETPLACE_PRICE")
        lamports = int(text) * SOL_LAMPORTS
    if lamports > MAX_PRICE_SOL * SOL_LAMPORTS:
        raise ValueError("MARKETPLACE_PRICE")
    return lamports


def _clip(value: str, maximum: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > maximum:
        return text[:maximum]
    return text


def identity_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": LISTING_SCHEMA,
        "title": str(row.get("title") or ""),
        "category": str(row.get("category") or ""),
        "material": str(row.get("material") or ""),
        "description": str(row.get("description") or ""),
        "mint": str(row.get("mint") or ""),
        "price_lamports": int(row.get("price_lamports") or 0),
        "listed_at": int(row.get("listed_at") or 0),
    }


def state_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = identity_payload(row)
    payload["id"] = str(row.get("id") or "")
    payload["owner"] = str(row.get("owner") or "")
    payload["status"] = str(row.get("status") or "")
    payload["network"] = str(row.get("network") or "testnet")
    payload["mode"] = str(row.get("mode") or "TESTNET")
    payload["identity_sha256"] = str(row.get("identity_sha256") or "")
    return payload


def hash_identity(row: dict[str, Any]) -> str:
    return digest_json(identity_payload(row))


def hash_state(row: dict[str, Any]) -> str:
    return digest_json(state_payload(row))


def empty_merkle_leaf() -> MerkleChild:
    return leaf(
        "catalog/empty",
        digest_json({"schema": SCHEMA, "listings": []}),
    )


def catalog_merkle(
    listings: list[dict[str, Any]],
    persist: bool = False,
) -> dict[str, Any]:
    grouped: dict[str, list[MerkleChild]] = {}
    for row in listings:
        listing_id = str(row.get("id") or "")
        state_sha = str(row.get("state_sha256") or "")
        category = str(row.get("category") or "")
        if not listing_id or not state_sha or category not in CATEGORIES:
            continue
        grouped.setdefault(category, []).append(
            leaf("listing/" + listing_id, state_sha)
        )
    children: list[MerkleChild] = []
    category_roots: dict[str, str] = {}
    for category in CATEGORIES:
        rows = grouped.get(category)
        if not rows:
            continue
        cat_root = build_domain_root(
            DOMAIN,
            SCOPE + "/" + category,
            tuple(rows),
        )
        category_roots[category] = cat_root.root_sha256()
        children.append(subtree("category/" + category, cat_root))
    if not children:
        children = [empty_merkle_leaf()]
    root = build_domain_root(DOMAIN, SCOPE, tuple(children))
    payload = {
        "schema": "gg.domain-merkle-root.v1",
        "domain": DOMAIN,
        "scope": SCOPE,
        "root_sha256": root.root_sha256(),
        "category_roots": category_roots,
        "listing_count": sum(len(rows) for rows in grouped.values()),
    }
    if persist:
        path = merkle_path()
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
    return payload


def listing_proof(
    listings: list[dict[str, Any]],
    listing_id: str,
    merkle: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    wanted = str(listing_id or "").strip()
    row = next((item for item in listings if item.get("id") == wanted), None)
    if row is None:
        return None
    tree = merkle or catalog_merkle(listings)
    category = str(row.get("category") or "")
    return {
        "listing_id": wanted,
        "identity_sha256": str(row.get("identity_sha256") or ""),
        "state_sha256": str(row.get("state_sha256") or ""),
        "category": category,
        "category_root": str((tree.get("category_roots") or {}).get(category) or ""),
        "catalog_root": str(tree.get("root_sha256") or ""),
        "leaf_namespace": "listing/" + wanted,
        "mint": str(row.get("mint") or ""),
        "network": str(row.get("network") or "testnet"),
        "mode": str(row.get("mode") or "TESTNET"),
    }


def load_catalog() -> list[dict[str, Any]]:
    path = catalog_path()
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return []
    rows = payload.get("listings") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for item in rows[:MAX_LISTINGS]:
        if isinstance(item, dict) and item.get("id"):
            out.append(item)
    return out


def save_catalog(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = listings[:MAX_LISTINGS]
    merkle = catalog_merkle(rows, persist=True)
    payload = {
        "schema": SCHEMA,
        "listings": rows,
        "merkle_root": merkle.get("root_sha256") or "",
    }
    path = catalog_path()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return rows


def load_prefs() -> dict[str, Any]:
    path = prefs_path()
    if not path.is_file():
        return {"filter": "ALL", "selected": ""}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {"filter": "ALL", "selected": ""}
    if not isinstance(payload, dict):
        return {"filter": "ALL", "selected": ""}
    filt = str(payload.get("filter") or "ALL").strip().upper()
    if filt not in FILTERS:
        filt = "ALL"
    return {
        "filter": filt,
        "selected": str(payload.get("selected") or "")[:80],
    }


def save_prefs(filter_name: str = "", selected: str = "") -> dict[str, Any]:
    current = load_prefs()
    filt = str(filter_name or current.get("filter") or "ALL").strip().upper()
    if filt not in FILTERS:
        filt = "ALL"
    selected_id = str(selected if selected != "" else current.get("selected") or "")[:80]
    payload = {"filter": filt, "selected": selected_id}
    path = prefs_path()
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return payload


def read_ledger() -> list[dict[str, Any]]:
    path = ledger_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows[-MAX_LEDGER:]


def append_ledger(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["schema"] = LEDGER_SCHEMA
    payload["ts"] = int(payload.get("ts") or time.time())
    path = ledger_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    path.chmod(0o600)
    return payload


def parse_listing(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        payload = raw
    else:
        try:
            payload = json.loads(str(raw or ""))
        except json.JSONDecodeError as exc:
            raise ValueError("MARKETPLACE_JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("MARKETPLACE_JSON")
    title = _clip(str(payload.get("title") or ""), MAX_TITLE)
    if not title:
        raise ValueError("MARKETPLACE_TITLE")
    category = str(payload.get("category") or "").strip().upper()
    if category not in CATEGORIES:
        raise ValueError("MARKETPLACE_CATEGORY")
    material = str(payload.get("material") or "UNKNOWN").strip().upper()
    if material not in MATERIALS:
        raise ValueError("MARKETPLACE_MATERIAL")
    description = _clip(str(payload.get("description") or ""), MAX_DESCRIPTION)
    mint_raw = str(payload.get("mint") or "").strip()
    mint = validate_pubkey(mint_raw) if mint_raw else ""
    price = parse_sol_price(
        payload.get("price_lamports", payload.get("price_sol"))
    )
    return {
        "title": title,
        "category": category,
        "material": material,
        "description": description,
        "mint": mint,
        "price_lamports": price,
    }


def decorate_listing(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["price_sol"] = format_sol(int(out.get("price_lamports") or 0))
    out["owner_short"] = short_pubkey(str(out.get("owner") or ""))
    out["mint_short"] = short_pubkey(str(out.get("mint") or "")) or "UNBOUND"
    out["identity_short"] = str(out.get("identity_sha256") or "")[:12]
    out["state_short"] = str(out.get("state_sha256") or "")[:12]
    return out


def category_rows(
    listings: list[dict[str, Any]],
    merkle: dict[str, Any],
) -> list[dict[str, Any]]:
    counts = {name: 0 for name in CATEGORIES}
    for row in listings:
        category = str(row.get("category") or "")
        if category in counts:
            counts[category] += 1
    roots = merkle.get("category_roots") or {}
    return [
        {
            "id": name,
            "label": name,
            "count": counts[name],
            "root_sha256": str(roots.get(name) or ""),
            "root_short": str(roots.get(name) or "")[:12],
        }
        for name in CATEGORIES
    ]


def list_item(raw: str | dict[str, Any]) -> dict[str, Any]:
    parsed = parse_listing(raw)
    wallet = load_wallet()
    owner = str(wallet.get("pubkey") or "")
    chain = load_network()
    listed_at = int(time.time())
    seed = {
        **parsed,
        "listed_at": listed_at,
    }
    identity = hash_identity(seed)
    listing_id = "lst-" + identity[:16]
    catalog = load_catalog()
    if any(row.get("id") == listing_id for row in catalog):
        raise ValueError("MARKETPLACE_DUPLICATE")
    if len(catalog) >= MAX_LISTINGS:
        raise ValueError("MARKETPLACE_FULL")
    row = {
        **seed,
        "id": listing_id,
        "owner": owner,
        "status": "LISTED",
        "network": chain,
        "mode": "TESTNET",
        "identity_sha256": identity,
        "state_sha256": "",
    }
    row["state_sha256"] = hash_state(row)
    catalog.append(row)
    save_catalog(catalog)
    save_prefs(selected=listing_id)
    append_ledger(
        {
            "kind": "LIST",
            "listing_id": listing_id,
            "category": row["category"],
            "material": row["material"],
            "owner": owner,
            "identity_sha256": identity,
            "state_sha256": row["state_sha256"],
            "txid": "PAPER",
            "mode": "TESTNET",
        }
    )
    return decorate_listing(row)


def _mutate(listing_id: str, status: str, owner: str | None = None) -> dict[str, Any]:
    wanted = str(listing_id or "").strip()
    catalog = load_catalog()
    found: dict[str, Any] | None = None
    for row in catalog:
        if row.get("id") == wanted:
            found = row
            break
    if found is None:
        raise ValueError("MARKETPLACE_MISSING")
    if owner is not None:
        found["owner"] = owner
    found["status"] = status
    found["state_sha256"] = hash_state(found)
    save_catalog(catalog)
    save_prefs(selected=wanted)
    return decorate_listing(found)


def delist_item(listing_id: str) -> dict[str, Any]:
    catalog = load_catalog()
    wanted = str(listing_id or "").strip()
    row = next((item for item in catalog if item.get("id") == wanted), None)
    if row is None:
        raise ValueError("MARKETPLACE_MISSING")
    if str(row.get("status") or "") != "LISTED":
        raise ValueError("MARKETPLACE_STATUS")
    updated = _mutate(wanted, "DELISTED")
    append_ledger(
        {
            "kind": "DELIST",
            "listing_id": wanted,
            "category": updated.get("category"),
            "owner": updated.get("owner"),
            "identity_sha256": updated.get("identity_sha256"),
            "state_sha256": updated.get("state_sha256"),
            "txid": "PAPER",
            "mode": "TESTNET",
        }
    )
    return updated


def paper_buy(listing_id: str) -> dict[str, Any]:
    wallet = load_wallet()
    buyer = str(wallet.get("pubkey") or "")
    if not buyer:
        raise ValueError("MARKETPLACE_WALLET")
    catalog = load_catalog()
    wanted = str(listing_id or "").strip()
    row = next((item for item in catalog if item.get("id") == wanted), None)
    if row is None:
        raise ValueError("MARKETPLACE_MISSING")
    if str(row.get("status") or "") != "LISTED":
        raise ValueError("MARKETPLACE_STATUS")
    seller = str(row.get("owner") or "")
    if seller and seller == buyer:
        raise ValueError("MARKETPLACE_SELF")
    identity = str(row.get("identity_sha256") or "")
    updated = _mutate(wanted, "SOLD", owner=buyer)
    append_ledger(
        {
            "kind": "BUY",
            "listing_id": wanted,
            "category": updated.get("category"),
            "from": seller,
            "to": buyer,
            "owner": buyer,
            "identity_sha256": identity,
            "state_sha256": updated.get("state_sha256"),
            "txid": "PAPER",
            "mode": "TESTNET",
        }
    )
    return updated


def set_filter(category: str) -> dict[str, Any]:
    return save_prefs(filter_name=category)


def select_listing(listing_id: str) -> dict[str, Any]:
    return save_prefs(selected=listing_id)


def status_payload() -> dict[str, Any]:
    wallet = load_wallet()
    chain = load_network()
    listings = load_catalog()
    prefs = load_prefs()
    filt = str(prefs.get("filter") or "ALL")
    selected_id = str(prefs.get("selected") or "")
    merkle = catalog_merkle(listings)
    visible = [
        decorate_listing(row)
        for row in listings
        if filt == "ALL" or str(row.get("category") or "") == filt
    ]
    selected = next(
        (row for row in visible if row.get("id") == selected_id),
        None,
    )
    if selected is None and selected_id:
        selected = next(
            (decorate_listing(row) for row in listings if row.get("id") == selected_id),
            None,
        )
    proof = listing_proof(listings, selected_id, merkle) if selected_id else None
    pubkey = str(wallet.get("pubkey") or "")
    legend = "MAINNET" if chain == "mainnet" else "TESTNET"
    return {
        "schema": SCHEMA,
        "legend": legend,
        "network": chain,
        "mode": "TESTNET",
        "chain": "solana",
        "filter": filt,
        "filters": list(FILTERS),
        "categories": category_rows(listings, merkle),
        "materials": list(MATERIALS),
        "listings": visible,
        "listing_count": len(listings),
        "visible_count": len(visible),
        "selected": selected,
        "proof": proof,
        "merkle": {
            "root_sha256": merkle.get("root_sha256") or "",
            "root_short": str(merkle.get("root_sha256") or "")[:12],
            "listing_count": merkle.get("listing_count") or 0,
            "domain": DOMAIN,
            "scope": SCOPE,
        },
        "wallet": {
            "pubkey": pubkey,
            "label": wallet.get("label") or "WALLET · DISCONNECTED",
            "short": short_pubkey(pubkey),
            "connected": bool(pubkey),
            "network": chain,
        },
        "ledger": read_ledger()[-80:],
        "authority": "NONE",
        "note": "Paper catalog on Solana identities. Mainnet trade stays locked.",
    }
