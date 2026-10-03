"""Record a devnet memo that a public building stays open."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import requests
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction

from api.explain import load_env

ROOT = Path(__file__).resolve().parents[1]
KEY_PATH = ROOT / "data" / "raw" / "solana-devnet.json"
MEMO_PROGRAM = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
DEFAULT_RPC = "https://api.devnet.solana.com"


def rpc_url() -> str:
    load_env()
    import os

    return os.environ.get("SOLANA_RPC_URL", "").strip() or DEFAULT_RPC


def keypair() -> Keypair:
    if KEY_PATH.exists():
        secret = bytes(json.loads(KEY_PATH.read_text()))
        return Keypair.from_bytes(secret)
    pair = Keypair()
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_text(json.dumps(list(bytes(pair))))
    return pair


def rpc(method: str, params: list) -> dict | list | str:
    response = requests.post(
        rpc_url(),
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        message = body["error"].get("message", str(body["error"]))
        raise RuntimeError(message)
    return body["result"]


def confirm(signature: str) -> None:
    for _ in range(40):
        status = rpc("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])["value"][0]
        if status and status.get("err"):
            raise RuntimeError(f"devnet transaction failed: {status['err']}")
        if status and status.get("confirmationStatus") in {"confirmed", "finalized"}:
            return
        time.sleep(1)
    raise RuntimeError("devnet transaction was not confirmed")


def fund(pair: Keypair) -> None:
    balance = rpc("getBalance", [str(pair.pubkey())])["value"]
    if balance >= 5000:
        return
    signature = rpc("requestAirdrop", [str(pair.pubkey()), 100_000_000])
    confirm(signature)


_READY: bool | None = None


def wallet_ready() -> bool:
    global _READY
    if _READY is not None:
        return _READY
    try:
        fund(keypair())
    except (RuntimeError, requests.RequestException) as error:
        print(f"devnet wallet is not funded: {error}", flush=True)
        _READY = False
        return False
    _READY = True
    return True


def send_memo(text: str) -> str:
    pair = keypair()
    fund(pair)
    blockhash = Hash.from_string(rpc("getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"])
    instruction = Instruction(
        MEMO_PROGRAM,
        text.encode(),
        [AccountMeta(pair.pubkey(), True, True)],
    )
    message = Message.new_with_blockhash([instruction], pair.pubkey(), blockhash)
    transaction = Transaction.new_unsigned(message)
    transaction.sign([pair], transaction.message.recent_blockhash)
    raw = base64.b64encode(bytes(transaction)).decode()
    signature = rpc("sendTransaction", [raw, {"encoding": "base64", "preflightCommitment": "confirmed"}])
    confirm(signature)
    return signature
