"""POST /quote — return a price quote for verifying a receipt."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..cache import receipt_hash, store_quote
from ..pricing import get_price

router = APIRouter()


class QuoteRequest(BaseModel):
    receipt: dict


@router.post("/quote")
async def quote(body: QuoteRequest) -> JSONResponse:
    model_name = body.receipt.get("model")
    if not model_name:
        return JSONResponse(
            status_code=400,
            content={
                "error": "missing_model",
                "message": "Receipt must contain a 'model' field.",
            },
        )

    price = get_price(model_name)
    if price is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": "unsupported_model",
                "message": f"Model '{model_name}' is not supported.",
            },
        )

    r_hash = receipt_hash(body.receipt)
    entry = store_quote(r_hash, price)

    return JSONResponse(
        status_code=200,
        content={
            "receipt_hash": r_hash,
            "price_usdc": price,
            "expires_at": int(entry.expires_at),
        },
    )
