from dataclasses import dataclass

import httpx
from eth_account import Account

from x402 import x402Client
from x402.http import x402HTTPClient
from x402.http.constants import PAYMENT_RESPONSE_HEADER
from x402.http.utils import decode_payment_response_header, encode_payment_signature_header
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client

from ree_oracle_client.exceptions import (
    OracleNetworkError,
    PaymentError,
    QuoteError,
    VerificationError,
)


@dataclass
class QuoteResult:
    receipt_hash: str
    price_usdc: str
    expires_at: int


@dataclass
class VerifyResult:
    valid: bool
    receipt_hash: str
    transaction_hash: str
    error: str | None


class OracleClient:
    def __init__(self, oracle_url: str, private_key: str) -> None:
        self._oracle_url = oracle_url.rstrip("/")
        self._private_key = private_key
        self._http = httpx.AsyncClient(timeout=660.0)

    async def quote(self, receipt: dict) -> QuoteResult:
        try:
            resp = await self._http.post(
                f"{self._oracle_url}/quote",
                json={"receipt": receipt},
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise OracleNetworkError(str(exc)) from exc

        if resp.status_code != 200:
            raise QuoteError(resp.text)

        data = resp.json()
        return QuoteResult(
            receipt_hash=data["receipt_hash"],
            price_usdc=data["price_usdc"],
            expires_at=data["expires_at"],
        )

    async def verify(self, receipt: dict) -> VerifyResult:
        await self.quote(receipt)

        try:
            resp402 = await self._http.post(
                f"{self._oracle_url}/verify",
                json={"receipt": receipt},
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise OracleNetworkError(str(exc)) from exc

        if resp402.status_code != 402:
            raise VerificationError(f"expected 402, got {resp402.status_code}")

        x402_http = x402HTTPClient(x402Client())
        payment_required = x402_http.get_payment_required_response(
            lambda name: resp402.headers.get(name),
            resp402.json(),
        )

        account = Account.from_key(self._private_key)
        x402_client = x402Client()
        register_exact_evm_client(x402_client, EthAccountSigner(account))

        payment_payload = await x402_client.create_payment_payload(payment_required)
        payment_header_value = encode_payment_signature_header(payment_payload)

        try:
            resp_final = await self._http.post(
                f"{self._oracle_url}/verify",
                json={"receipt": receipt},
                headers={"PAYMENT-SIGNATURE": payment_header_value},
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise OracleNetworkError(str(exc)) from exc

        if resp_final.status_code != 200:
            raise PaymentError(resp_final.text)

        data = resp_final.json()

        transaction_hash = ""
        payment_response_header = resp_final.headers.get(PAYMENT_RESPONSE_HEADER)
        if payment_response_header:
            settle = decode_payment_response_header(payment_response_header)
            transaction_hash = settle.transaction or ""

        return VerifyResult(
            valid=data["valid"],
            receipt_hash=data["receipt_hash"],
            transaction_hash=transaction_hash,
            error=data.get("error"),
        )
