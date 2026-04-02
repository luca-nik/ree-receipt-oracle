"""Flat-fee pricing lookup table by HuggingFace model ID."""

MODEL_PRICES_USDC: dict[str, str] = {
    "Qwen/Qwen3-0.6B": "0.01",
    "Qwen/Qwen3-1.7B": "0.02",
    "Qwen/Qwen3-4B":   "0.05",
    "Qwen/Qwen3-8B":   "0.10",
    "Qwen/Qwen3-14B":  "0.20",
    "Qwen/Qwen3-32B":  "0.50",
}


def get_price(model_name: str) -> str | None:
    """Return the USDC price string for a model, or None if unsupported."""
    return MODEL_PRICES_USDC.get(model_name)
