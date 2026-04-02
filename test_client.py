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
  "version": "1.1.0",
  "ree_version": "0.1.0",
  "model": {
    "name": "Qwen/Qwen3-0.6B",
    "commit_hash": "c1899de289a04d12100db370d81485cdf75e47ca",
    "config_hash": "sha256:01a2cd6eaa6ffadcfbf29bf5de383834dde68122b10edc73873d4a06b6758723"
  },
  "input": {
    "prompt": "What is 2 + 2? Show your reasoning step by step.",
    "prompt_hash": "sha256:5ab273c7b490ad51a15ef7b604cbcb98b8c3187cd677010f318e23c1a44bb0df",
    "parameters": {
      "max_new_tokens": 50,
      "temperature": 1.0,
      "top_k": 50,
      "top_p": 1.0,
      "min_p": None,
      "repetition_penalty": 1.0,
      "seed": 12345,
      "operation_set": "default",
      "rand_algorithm": "default",
      "do_sample": True,
      "eos_token": 151645,
      "short_circuit_length": None,
      "short_circuit_token": None,
      "use_kv_cache": True,
      "pad_token": 151645,
      "vocab_size": 151936
    },
    "parameters_hash": "sha256:7da18a8599a9f93b28e02ddd267444cc7ba2409ce4fb3ed23c5ee9ac4d866ffe"
  },
  "output": {
    "tokens_hash": "sha256:ae9504c4fb847718b35a8d2749e7390dc4d43ba865506c0326b7b338ced278d3",
    "token_count": 50,
    "finish_reason": "max_length",
    "text_output": " Are there other ways to calculate this? Explain what other operations could be used?\n\nThe problem is presented in a math lesson in a class that has a lot of students. I cannot take it as an exercise, but I can say that I know it"
  },
  "execution": {
    "device_type": "cpu",
    "device_name": "aarch64"
  },
  "hashes": {
    "receipt_hash": "sha256:655f0416b585aee52b306de1cf320cafc4f5a2f103fc8d5764386e62d73ac94e"
  }
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
        print(f"\n  REE error:\n{result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
