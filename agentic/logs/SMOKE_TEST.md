# Smoke Test Results

**Date:** 2026-04-02  
**Environment:** local, Base Sepolia, fake PAY_TO_ADDRESS, fake REE_SH_PATH

## Fixes applied during T-09

1. **`x402[evm]` extra missing** — `eth_abi` not installed. Fixed by changing `requirements.txt` to `x402[evm]>=0.1.0`.
2. **`initialize()` is sync, not async** — `await _x402_server.initialize()` raised `TypeError`. Fixed by wrapping with `asyncio.to_thread(_x402_server.initialize)` in `main.py`.

## Results

| # | Test | Expected | Result |
|---|------|----------|--------|
| 1 | `GET /health` | 200 `{"status":"ok"}` | PASS |
| 2 | `POST /quote` valid model | 200 with hash + price | PASS |
| 3 | `POST /quote` unknown model | 400 `unsupported_model` | PASS |
| 4 | `POST /verify` no quote in cache | 402 `quote_required` | PASS |
| 5 | `POST /verify` with prior quote, no payment header | 402 + `PAYMENT-REQUIRED` header (base64) | PASS |

## Not tested (requires live wallet + Base Sepolia USDC)

- Full payment flow: sign → `PAYMENT-SIGNATURE` → settle → REE verify
- REE verify subprocess (requires Docker + `ree.sh`)
