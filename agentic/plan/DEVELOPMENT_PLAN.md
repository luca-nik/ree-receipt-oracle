# REE Receipt Oracle — Development Plan

## Overview

Single Python/FastAPI service with two endpoints. No database, no external state. All complexity lives in the x402 manual payment flow in `/verify`.

## Project Structure

```
ree-receipt-oracle/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, route wiring, /health
│   ├── config.py            # Env var loading, fail-fast on missing required
│   ├── pricing.py           # MODEL_PRICES_USDC lookup table + get_price()
│   ├── cache.py             # QuoteEntry, receipt_hash(), store_quote(), get_quote()
│   ├── ree_runner.py        # Subprocess wrapper for ree.sh verify
│   └── routes/
│       ├── __init__.py
│       ├── quote.py         # POST /quote
│       └── verify.py        # POST /verify — manual x402 flow
├── .env.example
├── .gitignore
└── requirements.txt
```

## Build Order

Tasks are ordered so each module is complete before it is imported by the next.

```
T-01  Project scaffolding
  └── T-02  config.py
        └── T-03  pricing.py
              └── T-04  cache.py
                    └── T-05  ree_runner.py
                          ├── T-06  routes/quote.py   (uses pricing + cache)
                          └── T-07  routes/verify.py  (uses cache + ree_runner + x402)
                                └── T-08  main.py     (wires all routes)
                                      └── T-09  smoke test
```

## Key Implementation Notes for Developer

### T-07 (verify.py) — x402 manual flow

This is the most complex task. The handler must:

1. Compute `receipt_hash` from the body
2. If `PAYMENT-SIGNATURE` header is absent:
   - Look up quote in cache by hash
   - If not found → 402 with `quote_required` (no PaymentRequired header needed)
   - If found → build `PaymentRequirements` via `x402ResourceServer.build_payment_requirements(ResourceConfig(...))`
   - Return 402 with `PAYMENT-REQUIRED: <base64(PaymentRequired)>` header
3. If `PAYMENT-SIGNATURE` header is present:
   - Decode via `decode_payment_signature_header()`
   - Look up quote in cache (if expired → 402 `quote_expired`)
   - Build `PaymentRequirements` with cached price
   - Call `await x402_server.verify_payment(payload, requirement)`
   - If invalid → 402 `payment_invalid`
   - Call `await x402_server.settle_payment(payload, requirement)`
   - If failed → 402 `payment_settlement_failed`
   - Call `run_verify(receipt)` — blocking subprocess
   - Return 200 with `PAYMENT-RESPONSE` header and `{valid, receipt_hash, transaction_hash, error}`

### x402 server initialisation

The `x402ResourceServer` and `HTTPFacilitatorClient` must be instantiated once at module level in `verify.py` (not per-request). Register `ExactEvmServerScheme` for the configured network.

### ree_runner.py — temp file lifecycle

Write receipt JSON to a `tempfile.NamedTemporaryFile`, pass its path to `ree.sh verify --receipt-path <path>`, delete the file in a `finally` block regardless of outcome. Timeout: 600 seconds.

### config.py — fail fast

`PAY_TO_ADDRESS` and `REE_SH_PATH` are required. Raise `ValueError` at import time if missing so the server never starts misconfigured.

## Dependencies

```
fastapi>=0.111.0
uvicorn>=0.29.0
python-dotenv>=1.0.0
x402>=0.1.0
```

Install x402 with FastAPI extras if needed: `x402[fastapi]`

## Running Locally

```bash
cp .env.example .env   # fill in PAY_TO_ADDRESS and REE_SH_PATH
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```
