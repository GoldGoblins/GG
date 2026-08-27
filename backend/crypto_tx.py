from __future__ import annotations

import base64
from typing import Any

from backend.crypto_keys import b58decode, b58encode, load_test_pubkey, sign_message

SYSTEM_PROGRAM = b"\x00" * 32


def compact_u16(value: int) -> bytes:
    n = int(value)
    if n < 0 or n > 0xFFFF:
        raise ValueError("CRYPTO_COMPACT")
    out = bytearray()
    while True:
        elem = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(elem)
            break
        out.append(elem | 0x80)
    return bytes(out)


def transfer_data(lamports: int) -> bytes:
    return (2).to_bytes(4, "little") + int(lamports).to_bytes(8, "little")


def build_transfer_message(
    from_pub: bytes,
    to_pub: bytes,
    lamports: int,
    recent_blockhash: bytes,
) -> bytes:
    if len(from_pub) != 32 or len(to_pub) != 32 or len(recent_blockhash) != 32:
        raise ValueError("CRYPTO_KEYS")
    same = from_pub == to_pub
    if same:
        keys = from_pub + SYSTEM_PROGRAM
        header = bytes([1, 0, 1])
        accounts = bytes([0, 0])
        program_index = 1
    else:
        keys = from_pub + to_pub + SYSTEM_PROGRAM
        header = bytes([1, 0, 1])
        accounts = bytes([0, 1])
        program_index = 2
    data = transfer_data(lamports)
    ix = bytes([program_index]) + compact_u16(len(accounts)) + accounts + compact_u16(len(data)) + data
    nkeys = 2 if same else 3
    return header + compact_u16(nkeys) + keys + recent_blockhash + compact_u16(1) + ix


def signed_transfer_bytes(
    from_pub: bytes,
    to_pub: bytes,
    lamports: int,
    recent_blockhash: bytes,
) -> bytes:
    message = build_transfer_message(from_pub, to_pub, lamports, recent_blockhash)
    sig = sign_message(message)
    return compact_u16(1) + sig + message


def send_self_transfer(rpc_call, lamports: int) -> dict[str, Any]:
    pubkey = load_test_pubkey()
    if not pubkey:
        raise RuntimeError("CRYPTO_NO_SIGNER")
    from_pub = b58decode(pubkey)
    if len(from_pub) != 32:
        from_pub = from_pub[-32:]
    payload = rpc_call(
        "getLatestBlockhash",
        [{"commitment": "finalized"}],
    )
    result = payload.get("result") if isinstance(payload, dict) else None
    value = result.get("value") if isinstance(result, dict) else None
    blockhash = str((value or {}).get("blockhash") or "")
    if not blockhash:
        raise RuntimeError("CRYPTO_BLOCKHASH")
    raw_hash = b58decode(blockhash)
    if len(raw_hash) != 32:
        raw_hash = raw_hash[-32:]
    tx = signed_transfer_bytes(from_pub, from_pub, int(lamports), raw_hash)
    encoded = base64.b64encode(tx).decode("ascii")
    sent = rpc_call(
        "sendTransaction",
        [encoded, {"encoding": "base64", "skipPreflight": False}],
    )
    if not isinstance(sent, dict):
        raise RuntimeError("CRYPTO_RPC")
    if sent.get("error"):
        fault = sent["error"]
        msg = str(fault.get("message") if isinstance(fault, dict) else fault)
        raise RuntimeError(msg)
    sig = str(sent.get("result") or "")
    return {
        "txid": sig,
        "wallet": pubkey,
        "blockhash": blockhash,
        "lamports": int(lamports),
    }
