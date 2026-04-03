import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from eth_account import Account

from x402 import x402Client
from x402.http import x402HTTPClient
from x402.http.constants import PAYMENT_RESPONSE_HEADER
from x402.http.utils import decode_payment_response_header, encode_payment_signature_header
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client

from ree_oracle_client.client import OracleClient
from ree_oracle_client.exceptions import OracleError

import httpx

app = typer.Typer()


def _load_env(env_file: Optional[str]) -> None:
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()  # searches cwd and parent directories


def _resolve_key(private_key: Optional[str]) -> Optional[str]:
    import os
    return private_key or os.environ.get("ORACLE_CLIENT_PRIVATE_KEY") or os.environ.get("CLIENT_PRIVATE_KEY")


def _load_receipt(receipt_file: Path) -> dict:
    with open(receipt_file) as f:
        return json.load(f)


async def _verify_with_progress(
    receipt: dict,
    oracle_url: str,
    private_key: str,
) -> dict:
    client = OracleClient(oracle_url=oracle_url, private_key=private_key)

    print("[1/4] Getting quote...", file=sys.stderr)
    quote_result = await client.quote(receipt)
    expires_dt = datetime.fromtimestamp(quote_result.expires_at).strftime("%Y-%m-%d %H:%M:%S")
    model_name = receipt.get("model", {}).get("name", "unknown") if isinstance(receipt.get("model"), dict) else receipt.get("model", "unknown")
    print(f"      Model:        {model_name}", file=sys.stderr)
    print(f"      Price:        ${quote_result.price_usdc} USDC", file=sys.stderr)
    print(f"      Receipt hash: {quote_result.receipt_hash[:8]}...", file=sys.stderr)
    print(f"      Expires at:   {expires_dt}", file=sys.stderr)
    print("", file=sys.stderr)

    print("[2/4] Requesting verification (402 expected)...", file=sys.stderr)

    try:
        resp402 = await client._http.post(
            f"{client._oracle_url}/verify",
            json={"receipt": receipt},
        )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        from ree_oracle_client.exceptions import OracleNetworkError
        raise OracleNetworkError(str(exc)) from exc

    if resp402.status_code != 402:
        from ree_oracle_client.exceptions import VerificationError
        raise VerificationError(f"expected 402, got {resp402.status_code}")

    x402_http = x402HTTPClient(x402Client())
    payment_required = x402_http.get_payment_required_response(
        lambda name: resp402.headers.get(name),
        resp402.json(),
    )

    req = payment_required.accepts[0]
    print(f"      Network:  {req.network}", file=sys.stderr)
    print(f"      Asset:    {req.asset}", file=sys.stderr)
    print(f"      Pay to:   {req.pay_to}", file=sys.stderr)
    print("", file=sys.stderr)

    print("[3/4] Signing and submitting payment...", file=sys.stderr)

    account = Account.from_key(private_key)
    x402_client = x402Client()
    register_exact_evm_client(x402_client, EthAccountSigner(account))

    payment_payload = await x402_client.create_payment_payload(payment_required)
    payment_header_value = encode_payment_signature_header(payment_payload)

    print(f"      Wallet: {account.address}", file=sys.stderr)
    print("", file=sys.stderr)

    print("[4/4] Waiting for REE verification... (this may take several minutes)", file=sys.stderr)
    print("", file=sys.stderr)

    try:
        resp_final = await client._http.post(
            f"{client._oracle_url}/verify",
            json={"receipt": receipt},
            headers={"PAYMENT-SIGNATURE": payment_header_value},
        )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        from ree_oracle_client.exceptions import OracleNetworkError
        raise OracleNetworkError(str(exc)) from exc

    if resp_final.status_code != 200:
        from ree_oracle_client.exceptions import PaymentError
        raise PaymentError(resp_final.text)

    data = resp_final.json()

    transaction_hash = ""
    payment_response_header = resp_final.headers.get(PAYMENT_RESPONSE_HEADER)
    if payment_response_header:
        settle = decode_payment_response_header(payment_response_header)
        transaction_hash = settle.transaction or ""

    valid = data["valid"]
    receipt_hash = data["receipt_hash"]

    if valid:
        print("✓ RECEIPT VALID", file=sys.stderr)
    else:
        print("✗ RECEIPT INVALID", file=sys.stderr)
    print(f"  Transaction: {transaction_hash}", file=sys.stderr)
    print(f"  Receipt hash: {receipt_hash}", file=sys.stderr)

    return {
        "valid": valid,
        "receipt_hash": receipt_hash,
        "transaction_hash": transaction_hash,
    }


@app.command()
def verify(
    receipt_file: Path = typer.Argument(..., help="Path to receipt JSON file"),
    oracle_url: str = typer.Option("http://localhost:8765", help="Oracle server URL"),
    private_key: Optional[str] = typer.Option(None, help="EVM private key for payment signing"),
    env_file: Optional[str] = typer.Option(None, help="Path to .env file"),
) -> None:
    _load_env(env_file)
    key = _resolve_key(private_key)
    if not key:
        typer.echo("Error: private key required. Use --private-key or set ORACLE_CLIENT_PRIVATE_KEY.", err=True)
        raise typer.Exit(code=1)

    receipt = _load_receipt(receipt_file)

    try:
        result = asyncio.run(_verify_with_progress(receipt, oracle_url, key))
    except OracleError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    print(json.dumps(result))


@app.command()
def quote(
    receipt_file: Path = typer.Argument(..., help="Path to receipt JSON file"),
    oracle_url: str = typer.Option("http://localhost:8765", help="Oracle server URL"),
    private_key: Optional[str] = typer.Option(None, help="EVM private key (not required for quote)"),
    env_file: Optional[str] = typer.Option(None, help="Path to .env file"),
) -> None:
    _load_env(env_file)
    key = _resolve_key(private_key)

    receipt = _load_receipt(receipt_file)
    client = OracleClient(oracle_url=oracle_url, private_key=key or "")

    try:
        result = asyncio.run(client.quote(receipt))
    except OracleError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    model_name = receipt.get("model", {}).get("name", "unknown") if isinstance(receipt.get("model"), dict) else receipt.get("model", "unknown")
    expires_dt = datetime.fromtimestamp(result.expires_at).strftime("%Y-%m-%d %H:%M:%S")
    print(f"Model:        {model_name}")
    print(f"Price:        ${result.price_usdc} USDC")
    print(f"Receipt hash: {result.receipt_hash}")
    print(f"Expires at:   {expires_dt}")
