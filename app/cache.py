"""In-memory quote cache with TTL expiry and thread safety."""

import hashlib
import json
import threading
import time
from dataclasses import dataclass

from .config import QUOTE_TTL_SECONDS


@dataclass
class QuoteEntry:
    receipt_hash: str
    price_usdc: str
    expires_at: float


_cache: dict[str, QuoteEntry] = {}
_lock = threading.Lock()


def receipt_hash(receipt: dict) -> str:
    """Compute a stable SHA256 hex digest of a receipt (keys sorted)."""
    canonical = json.dumps(receipt, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def store_quote(r_hash: str, price_usdc: str) -> QuoteEntry:
    """Store a quote and return the entry."""
    entry = QuoteEntry(
        receipt_hash=r_hash,
        price_usdc=price_usdc,
        expires_at=time.time() + QUOTE_TTL_SECONDS,
    )
    with _lock:
        _cache[r_hash] = entry
    return entry


def get_quote(r_hash: str) -> QuoteEntry | None:
    """Return a valid (non-expired) quote entry, or None."""
    with _lock:
        entry = _cache.get(r_hash)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            del _cache[r_hash]
            return None
        return entry
