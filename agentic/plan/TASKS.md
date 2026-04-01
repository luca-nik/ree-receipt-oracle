# REE Receipt Oracle — Tasks

## T-01 · Project scaffolding
**Status:** pending

Create the base project structure with no logic.

- `app/__init__.py` (empty)
- `app/routes/__init__.py` (empty)
- `requirements.txt` with `fastapi>=0.111.0`, `uvicorn>=0.29.0`, `python-dotenv>=1.0.0`, `x402>=0.1.0`
- `.env.example` with all config keys documented (see blueprint §3 Config)
- `.gitignore` excluding `.env`, `__pycache__`, `*.pyc`, `.venv/`, `tmp/`

---

## T-02 · app/config.py
**Status:** pending  
**Depends on:** T-01

Load env vars via `python-dotenv`. Expose module-level constants:
- `PAY_TO_ADDRESS` — required, raise `ValueError` if missing
- `REE_SH_PATH` — required, raise `ValueError` if missing
- `NETWORK` — default `"eip155:84532"`
- `FACILITATOR_URL` — default `"https://x402.org/facilitator"`
- `QUOTE_TTL_SECONDS` — default `300` (int)

---

## T-03 · app/pricing.py
**Status:** pending  
**Depends on:** T-02

- `MODEL_PRICES_USDC: dict[str, str]` — flat fee lookup table per blueprint §3
- `get_price(model_name: str) -> str | None` — return price string or None if unsupported

---

## T-04 · app/cache.py
**Status:** pending  
**Depends on:** T-02

- `QuoteEntry` dataclass: `receipt_hash: str`, `price_usdc: str`, `expires_at: float`
- `receipt_hash(receipt: dict) -> str` — SHA256 of `json.dumps(receipt, sort_keys=True)`
- `store_quote(r_hash: str, price_usdc: str) -> QuoteEntry` — stores with TTL from config
- `get_quote(r_hash: str) -> QuoteEntry | None` — returns entry if not expired, else deletes and returns None
- Module-level `_cache: dict[str, QuoteEntry]`

---

## T-05 · app/ree_runner.py
**Status:** pending  
**Depends on:** T-02

- `ReeResult` dataclass: `valid: bool`, `error: str | None`
- `run_verify(receipt: dict) -> ReeResult`:
  - Write receipt to `tempfile.NamedTemporaryFile(suffix=".json")`
  - Run `["bash", REE_SH_PATH, "verify", "--receipt-path", <tmp_path>]`
  - `timeout=600`
  - Return `ReeResult(valid=True)` on exit code 0
  - Return `ReeResult(valid=False, error=stderr)` on non-zero exit
  - Delete temp file in `finally` block (`Path.unlink(missing_ok=True)`)

---

## T-06 · app/routes/quote.py
**Status:** pending  
**Depends on:** T-03, T-04

`POST /quote`:
- Parse `{"receipt": {...}}` body via Pydantic `QuoteRequest` model
- Extract `receipt["model"]` — return 400 `missing_model` if absent
- Call `get_price(model)` — return 400 `unsupported_model` if None
- Call `receipt_hash()` and `store_quote()`
- Return 200 `{"receipt_hash", "price_usdc", "expires_at"}`

---

## T-07 · app/routes/verify.py
**Status:** pending  
**Depends on:** T-04, T-05

Module-level x402 setup (instantiated once):
```python
_facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
_x402_server = x402ResourceServer(_facilitator)
_x402_server.register(NETWORK, ExactEvmServerScheme())
```

`POST /verify`:
1. Compute `r_hash = receipt_hash(body.receipt)`
2. Read `PAYMENT-SIGNATURE` header
3. **No header path:**
   - `get_quote(r_hash)` — if None, return 402 `quote_required` (no `PAYMENT-REQUIRED` header)
   - Build `PaymentRequirements` via `_x402_server.build_payment_requirements(ResourceConfig(...))`
   - Return 402 with `PAYMENT-REQUIRED: <base64(PaymentRequired)>` header
4. **Header present path:**
   - Decode header via `decode_payment_signature_header()`; return 400 on decode error
   - `get_quote(r_hash)` — if None, return 402 `quote_expired`
   - Build `PaymentRequirements` with cached price
   - `await _x402_server.verify_payment(payload, requirement)` — return 402 `payment_invalid` if not valid
   - `await _x402_server.settle_payment(payload, requirement)` — return 402 `payment_settlement_failed` if not success
   - `run_verify(body.receipt)` — blocking
   - Return 200 `{"valid", "receipt_hash", "transaction_hash", "error"}` with `PAYMENT-RESPONSE` header

Imports needed:
- `x402.http.constants`: `PAYMENT_REQUIRED_HEADER`, `PAYMENT_RESPONSE_HEADER`, `PAYMENT_SIGNATURE_HEADER`
- `x402.http.utils`: `decode_payment_signature_header`, `encode_payment_required_header`, `encode_payment_response_header`
- `x402.schemas`: `PaymentRequired`, `ResourceConfig`
- `x402.server`: `x402ResourceServer`
- `x402.http`: `HTTPFacilitatorClient`, `FacilitatorConfig`
- `x402.mechanisms.evm.exact`: `ExactEvmServerScheme`

---

## T-08 · app/main.py
**Status:** pending  
**Depends on:** T-06, T-07

- Create `FastAPI` app with title/description/version
- `app.include_router(quote_router)`
- `app.include_router(verify_router)`
- `GET /health` → `{"status": "ok"}`
- `if __name__ == "__main__": uvicorn.run(...)` on port 8000

---

## T-09 · Smoke test
**Status:** pending  
**Depends on:** T-08

Manual local test to verify the full flow works end-to-end:

1. Start server: `python -m uvicorn app.main:app --reload`
2. `POST /health` → expect 200
3. `POST /quote` with a valid receipt (model in lookup table) → expect 200 with hash + price
4. `POST /quote` with unknown model → expect 400 `unsupported_model`
5. `POST /verify` with valid receipt, no payment header → expect 402 with `PAYMENT-REQUIRED` header
6. `POST /verify` with valid receipt, expired/missing quote → expect 402 `quote_required`

Document results in `agentic/logs/SMOKE_TEST.md`.
