# REE Receipt Oracle

A pay-per-verification service for [Gensyn REE](https://github.com/gensyn-ai/ree) receipts, built on the [x402](https://github.com/coinbase/x402) payment protocol.

## What it does

Agents submit a REE receipt and pay a small USDC fee to have it independently verified. The oracle re-runs the inference via REE and confirms whether the receipt is valid — providing neutral, trustless liability attribution in an AI agent economy.

## How it works

1. **`POST /quote`** — Agent submits a receipt, receives a price quote (flat fee by model) and a receipt hash.
2. **`POST /verify`** — Agent retries with an x402 payment signature. Oracle settles payment on Base Sepolia, runs `ree.sh verify`, and returns the result.

See [`agentic/blueprints/SERVICE_BLUEPRINT.md`](agentic/blueprints/SERVICE_BLUEPRINT.md) for the full design.

## Stack

- Python + FastAPI
- [x402](https://github.com/coinbase/x402) Python SDK
- Base Sepolia (`eip155:84532`)
- [Gensyn REE](https://github.com/gensyn-ai/ree) (Docker-based)

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — required by REE for inference verification
- A wallet on Base Sepolia funded with test ETH and USDC
  - ETH (gas): [Coinbase Base Sepolia faucet](https://www.coinbase.com/faucets/base-ethereum-goerli-faucet)
  - USDC: [Circle faucet](https://faucet.circle.com) — select Base Sepolia
- The [Gensyn REE repo](https://github.com/gensyn-ai/ree) cloned locally

## Setup

**1. Clone and install:**
```bash
git clone https://github.com/luca-nik/ree-receipt-oracle.git
cd ree-receipt-oracle
uv sync
```

**2. Configure `.env`:**
```bash
cp .env.example .env
```

Edit `.env`:
```env
# Wallet address that receives USDC payments (Base Sepolia)
PAY_TO_ADDRESS=0xYourWalletAddress

# Network (Base Sepolia)
NETWORK=eip155:84532

# x402 facilitator
FACILITATOR_URL=https://x402.org/facilitator

# Absolute path to ree.sh in your local gensyn/ree clone
REE_SH_PATH=/path/to/ree/ree.sh

# Quote TTL in seconds
QUOTE_TTL_SECONDS=300
```

## Running the server

```bash
uv run uvicorn app.main:app --port 8765
```

The server starts at `http://localhost:8765`. On startup it contacts the x402 facilitator to fetch supported payment kinds — requires internet access.

## API

### `POST /quote`
Returns a price quote for verifying a receipt. Free, no payment required.

```bash
curl -X POST http://localhost:8765/quote \
  -H "Content-Type: application/json" \
  -d '{"receipt": <receipt-json>}'
```

Response:
```json
{
  "receipt_hash": "sha256-hex",
  "price_usdc": "0.01",
  "expires_at": 1234567890
}
```

### `POST /verify`
x402-protected. Returns 402 with payment requirements on first call; submit again with `PAYMENT-SIGNATURE` header to settle and run verification.

```bash
curl -X POST http://localhost:8765/verify \
  -H "Content-Type: application/json" \
  -d '{"receipt": <receipt-json>}'
```

### `GET /health`
```bash
curl http://localhost:8765/health
```

## Pricing

Flat fee per model (USDC on Base Sepolia):

| Model | Price |
|---|---|
| Qwen/Qwen3-0.6B | $0.01 |
| Qwen/Qwen3-1.7B | $0.02 |
| Qwen/Qwen3-4B | $0.05 |
| Qwen/Qwen3-8B | $0.10 |
| Qwen/Qwen3-14B | $0.20 |
| Qwen/Qwen3-32B | $0.50 |

## Testing

### 1. Generate a REE receipt

```bash
cd /path/to/ree
./ree.sh --model-name Qwen/Qwen3-0.6B --prompt-text "2+2?" --max-new-tokens 50
```

> Use the TUI (`python3 ree.py`) and set **Operation Set** to `reproducible` — this ensures the receipt can be verified.

The receipt is saved to `~/.cache/gensyn/`.

### 2. Confirm the receipt verifies with REE directly

```bash
RECEIPT=$(find ~/.cache/gensyn -name "receipt_*.json" | sort | tail -1)
./ree.sh verify --receipt-path $RECEIPT
# should print: VERIFICATION PASSED
```

### 3. Run the test client

In Terminal 1:
```bash
cd /path/to/ree-receipt-oracle
uv run uvicorn app.main:app --port 8765
```

In Terminal 2:
```bash
cd /path/to/ree-receipt-oracle

# add your wallet private key to .env first:
# CLIENT_PRIVATE_KEY=0x...

RECEIPT=$(find ~/.cache/gensyn -name "receipt_*.json" | sort | tail -1)
uv run python test_client.py $RECEIPT
```

The client walks through all 5 steps verbosely:
1. Get quote
2. Send verify (expects 402)
3. Sign payment with wallet
4. Retry with payment — settles on-chain, runs REE verify
5. Print result + transaction hash

## License

MIT
