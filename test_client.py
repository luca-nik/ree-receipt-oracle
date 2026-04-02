"""Test client for REE Receipt Oracle — exercises the full quote → pay → verify flow."""

import asyncio
import json
import os

import httpx
from dotenv import load_dotenv
from eth_account import Account

from x402 import x402Client
from x402.http.clients import x402HttpxClient
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client

load_dotenv()

BASE_URL = "http://localhost:8765"

# Sample receipt — replace with a real one from ~/.cache/gensyn/ for full REE verification
SAMPLE_RECEIPT = {
    "model": "Qwen/Qwen3-0.6B",
    "prompt": "What is the capital of France?",
    "output": "Paris",
    "max_new_tokens": 50,
}


async def main() -> None:
    private_key = os.getenv("CLIENT_PRIVATE_KEY")
    if not private_key:
        raise ValueError("CLIENT_PRIVATE_KEY not set in .env")

    account = Account.from_key(private_key)
    print(f"Client wallet: {account.address}\n")

    # ── Step 1: get a quote ──────────────────────────────────────────────────
    print("=== Step 1: POST /quote ===")
    async with httpx.AsyncClient() as http:
        resp = await http.post(f"{BASE_URL}/quote", json={"receipt": SAMPLE_RECEIPT})
    print(f"Status: {resp.status_code}")
    quote = resp.json()
    print(json.dumps(quote, indent=2))

    if resp.status_code != 200:
        print("Quote failed — stopping.")
        return

    print(f"\nPrice: ${quote['price_usdc']} USDC")
    print(f"Receipt hash: {quote['receipt_hash'][:16]}...")

    # ── Step 2: verify with x402 payment ────────────────────────────────────
    print("\n=== Step 2: POST /verify (x402 payment flow) ===")

    client = x402Client()
    register_exact_evm_client(client, EthAccountSigner(account))

    async with x402HttpxClient(client) as http:
        resp = await http.post(
            f"{BASE_URL}/verify",
            json={"receipt": SAMPLE_RECEIPT},
        )
        await resp.aread()

    print(f"Status: {resp.status_code}")
    print(json.dumps(resp.json(), indent=2))

    if resp.status_code == 200:
        result = resp.json()
        print(f"\n{'✓ VALID' if result['valid'] else '✗ INVALID'}")
        print(f"Transaction: {result.get('transaction_hash', 'n/a')}")


if __name__ == "__main__":
    asyncio.run(main())
