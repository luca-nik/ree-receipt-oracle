"""
Agent pipeline example — REE Receipt Oracle

Shows how an autonomous agent verifies a REE receipt and routes on the result.

Usage:
    uv run python examples/agent_pipeline.py test-receipts/receipt_20260402_173254.json

Requires ORACLE_CLIENT_PRIVATE_KEY in .env (or environment).
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from ree_oracle_client import OracleClient, VerifyResult
from ree_oracle_client.exceptions import (
    OracleNetworkError,
    PaymentError,
    QuoteError,
    VerificationError,
)


async def verify_receipt(receipt: dict, oracle_url: str, private_key: str) -> VerifyResult:
    client = OracleClient(oracle_url=oracle_url, private_key=private_key)
    return await client.verify(receipt)


def handle_result(result: VerifyResult) -> None:
    if result.valid:
        print("RECEIPT VALID")
        print(f"  receipt_hash:     {result.receipt_hash}")
        print(f"  transaction_hash: {result.transaction_hash}")
    else:
        print("RECEIPT INVALID")
        print(f"  receipt_hash: {result.receipt_hash}")
        print(f"  error:        {result.error}")


async def main() -> int:
    load_dotenv()

    receipt_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not receipt_path or not receipt_path.exists():
        print(f"Usage: python examples/agent_pipeline.py <receipt.json>", file=sys.stderr)
        return 1

    oracle_url = os.environ.get("ORACLE_URL", "http://localhost:8765")
    private_key = os.environ.get("ORACLE_CLIENT_PRIVATE_KEY") or os.environ.get("CLIENT_PRIVATE_KEY")
    if not private_key:
        print("Error: ORACLE_CLIENT_PRIVATE_KEY not set", file=sys.stderr)
        return 1

    receipt = json.loads(receipt_path.read_text())

    try:
        result = await verify_receipt(receipt, oracle_url, private_key)
    except QuoteError as exc:
        print(f"Quote failed (unsupported model or server error): {exc}", file=sys.stderr)
        return 1
    except PaymentError as exc:
        print(f"Payment failed: {exc}", file=sys.stderr)
        return 1
    except VerificationError as exc:
        print(f"Verification error: {exc}", file=sys.stderr)
        return 1
    except OracleNetworkError as exc:
        print(f"Oracle unreachable: {exc}", file=sys.stderr)
        return 1

    handle_result(result)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
