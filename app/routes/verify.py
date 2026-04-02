"""POST /verify — x402-protected endpoint that runs REE receipt verification."""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from x402.http import FacilitatorConfig, HTTPFacilitatorClient
from x402.http.constants import (
    PAYMENT_REQUIRED_HEADER,
    PAYMENT_RESPONSE_HEADER,
    PAYMENT_SIGNATURE_HEADER,
)
from x402.http.utils import (
    decode_payment_signature_header,
    encode_payment_required_header,
    encode_payment_response_header,
)
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.schemas import PaymentRequired, ResourceConfig
from x402.server import x402ResourceServer

from ..cache import get_quote, receipt_hash
from ..config import FACILITATOR_URL, NETWORK, PAY_TO_ADDRESS
from ..ree_runner import run_verify

router = APIRouter()

# Instantiated once at module load; initialized at app startup via main.py
_facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
_x402_server = x402ResourceServer(_facilitator)
_x402_server.register(NETWORK, ExactEvmServerScheme())


class VerifyRequest(BaseModel):
    receipt: dict


def _payment_requirements(price_usdc: str):
    config = ResourceConfig(
        scheme="exact",
        network=NETWORK,
        pay_to=PAY_TO_ADDRESS,
        price=f"${price_usdc}",
    )
    return _x402_server.build_payment_requirements(config)


@router.post("/verify")
async def verify(request: Request, body: VerifyRequest) -> JSONResponse:
    r_hash = receipt_hash(body.receipt)

    payment_header = request.headers.get(PAYMENT_SIGNATURE_HEADER)

    # ── No payment header: return 402 with PaymentRequired ──────────────────
    if not payment_header:
        entry = get_quote(r_hash)
        if entry is None:
            return JSONResponse(
                status_code=402,
                content={
                    "error": "quote_required",
                    "message": "No valid quote found. Call POST /quote first.",
                },
            )

        requirements = _payment_requirements(entry.price_usdc)
        payment_required = PaymentRequired(
            x402_version=2,
            error="Payment required to run REE verification.",
            accepts=requirements,
        )
        return JSONResponse(
            status_code=402,
            content={
                "error": "payment_required",
                "message": "Retry with PAYMENT-SIGNATURE header.",
            },
            headers={PAYMENT_REQUIRED_HEADER: encode_payment_required_header(payment_required)},
        )

    # ── Payment header present: verify → settle → run REE ───────────────────
    try:
        payload = decode_payment_signature_header(payment_header)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_payment_header", "message": str(exc)},
        )

    entry = get_quote(r_hash)
    if entry is None:
        return JSONResponse(
            status_code=402,
            content={
                "error": "quote_expired",
                "message": "Quote has expired. Call POST /quote again.",
            },
        )

    requirements = _payment_requirements(entry.price_usdc)
    requirement = requirements[0]

    verify_result = await _x402_server.verify_payment(payload, requirement)
    if not verify_result.is_valid:
        return JSONResponse(
            status_code=402,
            content={
                "error": "payment_invalid",
                "message": verify_result.invalid_reason or "Payment verification failed.",
            },
        )

    settle_result = await _x402_server.settle_payment(payload, requirement)
    if not settle_result.success:
        return JSONResponse(
            status_code=402,
            content={
                "error": "payment_settlement_failed",
                "message": settle_result.error_reason or "Payment settlement failed.",
            },
        )

    ree_result = await asyncio.to_thread(run_verify, body.receipt)

    return JSONResponse(
        status_code=200,
        content={
            "valid": ree_result.valid,
            "receipt_hash": r_hash,
            "transaction_hash": settle_result.transaction,
            "error": ree_result.error,
        },
        headers={PAYMENT_RESPONSE_HEADER: encode_payment_response_header(settle_result)},
    )
