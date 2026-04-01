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

## Status

Blueprint complete. Implementation pending.

## License

MIT
