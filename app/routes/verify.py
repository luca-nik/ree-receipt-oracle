"""POST /verify — x402-protected endpoint that runs REE receipt verification."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from x402.http.constants import PAYMENT_REQUIRED_HEADER, PAYMENT_RESPONSE_HEADER, PAYMENT_SIGNATURE_HEADER
from x402.http.utils import (
    decode_payment_signature_header,
    encode_payment_required_header,
    encode_payment_response_header,
)
from x402.schemas import PaymentRequired, ResourceConfig
from x402.schemas.helpers import parse_payment_payload

from ..cache import get_quote, receipt_hash
from ..config import FACILITATOR_URL, NETWORK, PAY_TO_ADDRESS
from ..ree_runner import run_verify

from x402.server import x402ResourceServer
from x402.http import HTTPFacilitatorClient, FacilitatorConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme

router = APIRouter()

# Initialise x402 server once at module load
_facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
_x402_server = x402ResourceServer(_facilitator)
_x402_server.register(NETWORK, ExactEvmServerScheme())


class VerifyRequest(BaseModel):
    receipt: dict


def _build_402_response(r_hash: str, price_usdc: str) -> JSONResponse:
    """Build a 402 Payment Required response for the given price."""
    config = ResourceConfig(
        scheme="exact",
        network=NETWORK,
        pay_to=PAY_TO_ADDRESS,
        price=f"${price_usdc}",
    )
    requirements = _x402_server.build_payment_requirements(config)

    payment_required = PaymentRequired(
        x402_version=2,
        error="Payment required to run REE verification.",
        accepts=requirements,
    )

    headers = {PAYMENT_REQUIRED_HEADER: encode_payment_required_header(payment_required)}
    return JSONResponse(
        status_code=402,
        content={
            "error": "payment_required",
            "message": "Include a valid PAYMENT-SIGNATURE header. Call POST /quote first to get a price.",
        },
        headers=headers,
    )


@router.post("/verify")
async def verify(request: Request, body: VerifyRequest) -> JSONResponse:
    r_hash = receipt_hash(body.receipt)

    # ── Step 1: check for payment signature header ──────────────────────────
    payment_header = request.headers.get(PAYMENT_SIGNATURE_HEADER)

    if not payment_header:
        # No payment — look up the quote and return 402 with the right price
        entry = get_quote(r_hash)
        if entry is None:
            return JSONResponse(
                status_code=402,
                content={
                    "error": "quote_required",
                    "message": "No valid quote found for this receipt. Call POST /quote first.",
                },
            )
        return _build_402_response(r_hash, entry.price_usdc)

    # ── Step 2: decode and verify the payment ───────────────────────────────
    try:
        payload = decode_payment_signature_header(payment_header)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_payment_header", "message": str(exc)},
        )

    # Retrieve the quote to reconstruct the requirements
    entry = get_quote(r_hash)
    if entry is None:
        return JSONResponse(
            status_code=402,
            content={
                "error": "quote_expired",
                "message": "Quote has expired. Call POST /quote again.",
            },
        )

    config = ResourceConfig(
        scheme="exact",
        network=NETWORK,
        pay_to=PAY_TO_ADDRESS,
        price=f"${entry.price_usdc}",
    )
    requirements = _x402_server.build_payment_requirements(config)
    # Match against the first (and only) requirement we issued
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

    # ── Step 3: settle the payment ──────────────────────────────────────────
    settle_result = await _x402_server.settle_payment(payload, requirement)
    if not settle_result.success:
        return JSONResponse(
            status_code=402,
            content={
                "error": "payment_settlement_failed",
                "message": settle_result.error_reason or "Payment settlement failed.",
            },
        )

    # ── Step 4: run REE verification ────────────────────────────────────────
    ree_result = run_verify(body.receipt)

    settle_header = encode_payment_response_header(settle_result)
    headers = {PAYMENT_RESPONSE_HEADER: settle_header}

    return JSONResponse(
        status_code=200,
        content={
            "valid": ree_result.valid,
            "receipt_hash": r_hash,
            "transaction_hash": settle_result.transaction,
            "error": ree_result.error,
        },
        headers=headers,
    )
