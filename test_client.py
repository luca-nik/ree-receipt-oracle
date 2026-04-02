"""Test client for REE Receipt Oracle — verbose, step-by-step flow."""

import asyncio
import json
import os

import httpx
from dotenv import load_dotenv
from eth_account import Account

from x402 import x402Client
from x402.http import x402HTTPClient
from x402.http.constants import PAYMENT_REQUIRED_HEADER, PAYMENT_RESPONSE_HEADER
from x402.http.utils import decode_payment_response_header, encode_payment_signature_header
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client

load_dotenv()

BASE_URL = "http://localhost:8765"

SAMPLE_RECEIPT = {
    "model": "Qwen/Qwen3-0.6B",
    "prompt": "What is the capital of France?",
    "output": "Paris",
    "max_new_tokens": 50,
}


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def step(msg: str) -> None:
    print(f"\n→ {msg}")


async def main() -> None:
    private_key = os.getenv("CLIENT_PRIVATE_KEY")
    if not private_key:
        raise ValueError("CLIENT_PRIVATE_KEY not set in .env")

    account = Account.from_key(private_key)
    print(f"\nClient wallet: {account.address}")

    # ── Step 1: GET A QUOTE ──────────────────────────────────────────────────
    section("STEP 1 — Get a quote")
    step("POST /quote with receipt...")

    async with httpx.AsyncClient() as http:
        resp = await http.post(f"{BASE_URL}/quote", json={"receipt": SAMPLE_RECEIPT})

    print(f"  Status: {resp.status_code}")
    quote = resp.json()
    print(f"  Receipt hash: {quote.get('receipt_hash', 'n/a')}")
    print(f"  Price:        ${quote.get('price_usdc', 'n/a')} USDC")
    print(f"  Expires at:   {quote.get('expires_at', 'n/a')} (unix)")

    if resp.status_code != 200:
        print("\n✗ Quote failed. Stopping.")
        return

    # ── Step 2: FIRST /verify → EXPECT 402 ──────────────────────────────────
    section("STEP 2 — Send verify request (expecting 402)")
    step("POST /verify without payment header...")

    async with httpx.AsyncClient() as http:
        resp402 = await http.post(f"{BASE_URL}/verify", json={"receipt": SAMPLE_RECEIPT})

    print(f"  Status: {resp402.status_code}")

    if resp402.status_code != 402:
        print(f"  Unexpected status. Body: {resp402.text}")
        return

    payment_required_header = resp402.headers.get(PAYMENT_REQUIRED_HEADER)
    if not payment_required_header:
        print("  ✗ No PAYMENT-REQUIRED header in 402 response.")
        return

    print(f"  ✓ Got 402 with PAYMENT-REQUIRED header ({len(payment_required_header)} chars base64)")

    # Decode and show payment requirements
    x402_http = x402HTTPClient(x402Client())
    payment_required = x402_http.get_payment_required_response(
        lambda name: resp402.headers.get(name),
        resp402.json(),
    )
    req = payment_required.accepts[0]
    print(f"  Network:  {req.network}")
    print(f"  Asset:    {req.asset}")
    print(f"  Amount:   {req.amount} (atomic units)")
    print(f"  Pay to:   {req.pay_to}")

    # ── Step 3: SIGN PAYMENT ────────────────────────────────────────────────
    section("STEP 3 — Sign payment")
    step("Creating payment payload with wallet...")

    x402_client = x402Client()
    register_exact_evm_client(x402_client, EthAccountSigner(account))

    payment_payload = await x402_client.create_payment_payload(payment_required)
    payment_header_value = encode_payment_signature_header(payment_payload)

    print(f"  ✓ Payment signed by {account.address}")
    print(f"  Authorization from: {payment_payload.payload.get('authorization', {}).get('from', 'n/a')}")
    print(f"  Authorization to:   {payment_payload.payload.get('authorization', {}).get('to', 'n/a')}")
    print(f"  Valid before:       {payment_payload.payload.get('authorization', {}).get('validBefore', 'n/a')}")

    # ── Step 4: RETRY /verify WITH PAYMENT ──────────────────────────────────
    section("STEP 4 — Retry verify with payment (settlement + REE)")
    step("POST /verify with PAYMENT-SIGNATURE header...")
    print("  (This settles on-chain, then runs REE verify — may take several minutes)")

    async with httpx.AsyncClient(timeout=660.0) as http:
        resp_final = await http.post(
            f"{BASE_URL}/verify",
            json={"receipt": SAMPLE_RECEIPT},
            headers={"PAYMENT-SIGNATURE": payment_header_value},
        )

    print(f"  Status: {resp_final.status_code}")

    # ── Step 5: SHOW RESULT ──────────────────────────────────────────────────
    section("STEP 5 — Result")

    if resp_final.status_code != 200:
        print(f"  ✗ Error: {resp_final.json()}")
        return

    result = resp_final.json()

    # Show settlement details from PAYMENT-RESPONSE header
    payment_response_header = resp_final.headers.get(PAYMENT_RESPONSE_HEADER)
    if payment_response_header:
        settle = decode_payment_response_header(payment_response_header)
        print(f"  Payment settled: {settle.success}")
        print(f"  Transaction:     {settle.transaction}")
        print(f"  Network:         {settle.network}")
        print(f"  Payer:           {settle.payer}")

    print(f"\n  {'✓ RECEIPT VALID' if result['valid'] else '✗ RECEIPT INVALID'}")
    print(f"  Receipt hash: {result.get('receipt_hash', 'n/a')}")
    if result.get("error"):
        print(f"\n  REE error:\n  {result['error'][:400]}")


if __name__ == "__main__":
    asyncio.run(main())
