#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from backend import marketplace_contract
from backend.surface_intent import parse_surface_intent


def main() -> int:
    src = (PROJECT / "backend" / "marketplace_contract.py").read_text(encoding="utf-8")
    host_src = (PROJECT / "backend" / "marketplace_host.py").read_text(encoding="utf-8")
    qml = (PROJECT / "qml" / "components" / "MarketplaceSurface.qml").read_text(
        encoding="utf-8"
    )
    ws = (PROJECT / "qml" / "components" / "WorkspaceSurface.qml").read_text(
        encoding="utf-8"
    )
    if "solana.catalog" not in src:
        raise AssertionError("solana catalog scope missing")
    if "build_domain_root" not in src or "identity_sha256" not in src:
        raise AssertionError("merkle identity missing")
    if "PAPER" not in src or '"mode": "TESTNET"' not in src:
        raise AssertionError("paper/testnet lock missing")
    if "marketplaceStatus" not in host_src and "status_payload" not in host_src:
        raise AssertionError("host status missing")
    if "leftLegend: \"MARKETPLACE\"" in qml:
        raise AssertionError("marketplace pane still nests a MARKETPLACE GgFrame")
    crypto_at = ws.index('text: "CRYPTO"')
    market_at = ws.index('text: "MARKETPLACE"')
    tmog_at = ws.index('text: "TMOG"')
    if not (crypto_at < market_at < tmog_at):
        raise AssertionError("MARKETPLACE tab not between CRYPTO and TMOG")
    if 'hostKind === "MARKETPLACE"' not in ws:
        raise AssertionError("workspace host kind missing MARKETPLACE")
    if parse_surface_intent("marketplace") != "MARKETPLACE":
        raise AssertionError("bare marketplace intent")
    if parse_surface_intent("öppna marketplace") != "MARKETPLACE":
        raise AssertionError("open marketplace intent")
    if parse_surface_intent("nft") != "MARKETPLACE":
        raise AssertionError("nft intent")

    tmp = Path(tempfile.mkdtemp(prefix="gg-market-"))
    marketplace_contract.STATE_DIR = tmp
    crypto_tmp = Path(tempfile.mkdtemp(prefix="gg-crypto-"))
    from backend import crypto_contract

    crypto_contract.STATE_DIR = crypto_tmp

    empty = marketplace_contract.status_payload()
    if empty["merkle"]["domain"] != "MARKETPLACE":
        raise AssertionError("empty domain")
    if not empty["merkle"]["root_sha256"]:
        raise AssertionError("empty merkle root")
    if empty["listing_count"] != 0:
        raise AssertionError("empty catalog not empty")

    try:
        marketplace_contract.parse_listing({"title": "x", "category": "NOPE"})
        raise AssertionError("bad category accepted")
    except ValueError:
        pass
    try:
        marketplace_contract.parse_listing(
            {"title": "x", "category": "MATERIAL", "mint": "bad"}
        )
        raise AssertionError("bad mint accepted")
    except ValueError:
        pass
    if marketplace_contract.parse_sol_price("1.5") != 1_500_000_000:
        raise AssertionError("sol price 1.5")
    if marketplace_contract.parse_sol_price("0.000000001") != 1:
        raise AssertionError("sol price 1 lamport")

    listed = marketplace_contract.list_item(
        {
            "title": "Gold ore sample",
            "category": "MATERIAL",
            "material": "GOLD",
            "description": "lab sample",
            "price_sol": "0.25",
        }
    )
    if listed["status"] != "LISTED":
        raise AssertionError("list status")
    if not listed["identity_sha256"] or not listed["state_sha256"]:
        raise AssertionError("listing hashes")
    if listed["id"] != "lst-" + listed["identity_sha256"][:16]:
        raise AssertionError("listing id")
    identity = listed["identity_sha256"]
    catalog = marketplace_contract.load_catalog()
    merkle = marketplace_contract.catalog_merkle(catalog)
    if "MATERIAL" not in merkle["category_roots"]:
        raise AssertionError("material subtree missing")
    proof = marketplace_contract.listing_proof(catalog, listed["id"], merkle)
    if proof is None or proof["identity_sha256"] != identity:
        raise AssertionError("proof identity")
    if proof["catalog_root"] != merkle["root_sha256"]:
        raise AssertionError("proof catalog root")

    wallet = crypto_contract.save_wallet("11111111111111111111111111111111", 0)
    if not wallet["connected"]:
        raise AssertionError("buyer wallet")
    bought = marketplace_contract.paper_buy(listed["id"])
    if bought["status"] != "SOLD":
        raise AssertionError("paper buy status")
    if bought["owner"] != "11111111111111111111111111111111":
        raise AssertionError("paper buy owner")
    if bought["identity_sha256"] != identity:
        raise AssertionError("identity drifted on buy")
    if bought["state_sha256"] == listed["state_sha256"]:
        raise AssertionError("state hash did not move on buy")

    other = marketplace_contract.list_item(
        {
            "title": "Carved oak token",
            "category": "ITEM",
            "material": "WOOD",
            "price_sol": "1",
        }
    )
    dropped = marketplace_contract.delist_item(other["id"])
    if dropped["status"] != "DELISTED":
        raise AssertionError("delist")
    try:
        marketplace_contract.paper_buy(other["id"])
        raise AssertionError("buy delisted")
    except ValueError:
        pass

    status = marketplace_contract.status_payload()
    if status["listing_count"] != 2:
        raise AssertionError("count " + str(status["listing_count"]))
    if status["chain"] != "solana":
        raise AssertionError("chain")
    if status["authority"] != "NONE":
        raise AssertionError("authority leaked")
    ledger = marketplace_contract.read_ledger()
    kinds = [row.get("kind") for row in ledger]
    if kinds != ["LIST", "BUY", "LIST", "DELIST"]:
        raise AssertionError("ledger kinds " + json.dumps(kinds))

    from backend import marketplace_host

    filtered = marketplace_host.set_filter("ITEM")
    if filtered["filter"] != "ITEM":
        raise AssertionError("filter")
    if filtered["visible_count"] != 1:
        raise AssertionError("visible filter")
    failed = marketplace_host.list_item("{}")
    if failed.get("error") != "MARKETPLACE_TITLE":
        raise AssertionError("host error " + str(failed.get("error")))
    if failed.get("listing_count") != 2:
        raise AssertionError("host error wiped catalog")

    print("MARKETPLACE_CONTRACT_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
