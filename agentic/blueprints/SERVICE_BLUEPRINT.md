# REE Receipt Oracle — Service Blueprint

## 1. Scope

**Does:**
- Expose `POST /quote` — accepts a REE receipt JSON, returns a USDC price quote for verification
- Expose `POST /verify` — x402-protected endpoint that runs `ree.sh verify` and returns the result
- Price verification based on a flat fee per model (lookup table)
- Cache quotes short-term (5 min TTL) keyed by receipt hash
- Settle payments on Base Sepolia via x402 protocol

**Does NOT:**
- Run inference (only verification)
- Persist quotes beyond TTL or store receipts permanently
- Support multiple chains in V1
- Expose any admin or management API
- Handle authentication beyond x402 payment

---

## 2. API / Interface

### `POST /quote`

**Request body:**
```json
{
  "receipt": { ...REE receipt JSON... }
}
```

**Response 200:**
```json
{
  "receipt_hash": "sha256-hex-string",
  "price_usdc": "0.01",
  "expires_at": 1234567890
}
```

**Response 400 — model not supported:**
```json
{
  "error": "unsupported_model",
  "message": "Model 'X' is not in the supported model list."
}
```

---

### `POST /verify`

**Request body:**
```json
{
  "receipt": { ...REE receipt JSON... }
}
```

**Response 402 — no payment (x402 flow):**
```
HTTP 402 Payment Required
PAYMENT-REQUIRED: <base64-encoded PaymentRequired>
```
Body:
```json
{
  "error": "payment_required",
  "message": "Call POST /quote first to get a price, then retry with PAYMENT-SIGNATURE header."
}
```

**Response 402 — quote expired:**
```json
{
  "error": "quote_expired",
  "message": "Quote has expired. Call POST /quote again."
}
```

**Response 200 — verification complete:**
```json
{
  "valid": true,
  "receipt_hash": "sha256-hex-string",
  "transaction_hash": "0x...",
  "error": null
}
```

**Response 200 — verification failed:**
```json
{
  "valid": false,
  "receipt_hash": "sha256-hex-string",
  "transaction_hash": "0x...",
  "error": "REE verification failed: <stderr>"
}
```

**Response 400 — payment settled but REE error:**
```json
{
  "error": "ree_error",
  "message": "Payment settled but REE execution failed: <details>"
}
```

---

## 3. Data Structures

### QuoteCache entry
```python
@dataclass
class QuoteEntry:
    receipt_hash: str    # SHA256 hex of canonical receipt JSON
    price_usdc: str      # e.g. "0.01"
    expires_at: float    # unix timestamp (time.time() + 300)
```

### Model pricing lookup table
```python
MODEL_PRICES_USDC: dict[str, str] = {
    "Qwen/Qwen3-0.6B": "0.01",
    "Qwen/Qwen3-1.7B": "0.02",
    "Qwen/Qwen3-4B":   "0.05",
    "Qwen/Qwen3-8B":   "0.10",
    "Qwen/Qwen3-14B":  "0.20",
    "Qwen/Qwen3-32B":  "0.50",
}
```

### Config (from environment)
```python
PAY_TO_ADDRESS: str       # Wallet address receiving USDC payments
NETWORK: str              # "eip155:84532" (Base Sepolia)
FACILITATOR_URL: str      # "https://x402.org/facilitator"
REE_SH_PATH: str          # Absolute path to ree.sh
QUOTE_TTL_SECONDS: int    # Default 300
```

### Receipt (input, minimum required fields)
```python
{
  "model": str,           # HuggingFace model ID — used for pricing
  ...                     # All other fields passed through to ree.sh verify
}
```

---

## 4. Architectural Decisions

1. **Manual x402 handling (no middleware)** — The standard `PaymentMiddlewareASGI` uses static per-route prices. Since `/verify` needs dynamic pricing from the quote cache, we handle the x402 flow manually inside the route handler using `build_payment_requirements`, `verify_payment`, and `settle_payment` directly. This gives full control without fighting the library.

2. **Two-endpoint design (`/quote` + `/verify`)** — The 402 response IS the quote in pure x402, but dynamic pricing requires custom middleware. The two-endpoint design avoids this, uses standard x402 primitives on `/verify`, and makes the agent flow explicit and debuggable.

3. **In-memory quote cache** — No external dependency (Redis etc.) for V1. The TTL is short (5 min) and quotes are cheap to recompute. A dict with expiry timestamps is sufficient.

4. **SHA256 of canonical receipt JSON as cache key** — The receipt is hashed deterministically (keys sorted) so the same receipt always produces the same key, regardless of field ordering in the client request.

5. **`ree.sh` invoked as subprocess** — The service wraps `ree.sh verify` directly as a subprocess. This keeps REE's Docker/ACL logic intact and avoids reimplementing it. The receipt is written to a temp file, path passed to `ree.sh`, temp file cleaned up after.

6. **Base Sepolia only (V1)** — Low gas fees fit micropayments. Network is a config variable so adding chains later requires no code changes.

7. **Reject unknown models** — Rather than using a default price, unknown models return 400. This prevents silent mispricing and forces the lookup table to be kept up to date explicitly.

---

## 5. Dependencies

### External
- `x402` Python SDK — payment verification and settlement
- `fastapi` + `uvicorn` — HTTP server
- `pydantic` — request/response validation
- `python-dotenv` — config from `.env`

### System
- `ree.sh` (and Docker) — must be present and runnable on the host
- Base Sepolia RPC — via x402 facilitator at `x402.org/facilitator`

### Internal
- None (single-service, no other components)

---

## 6. Out of Scope for V1

- Persistence of quotes or verification results
- Multi-chain support (Ethereum mainnet, other EVMs)
- Authentication / API keys
- Rate limiting
- Webhook callbacks when verification completes
- Async / queued verification for long-running models
- A client SDK or agent library
- On-chain recording of verification results
- Automatic model price discovery
