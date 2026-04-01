import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


PAY_TO_ADDRESS: str = _require("PAY_TO_ADDRESS")
NETWORK: str = os.getenv("NETWORK", "eip155:84532")
FACILITATOR_URL: str = os.getenv("FACILITATOR_URL", "https://x402.org/facilitator")
REE_SH_PATH: str = _require("REE_SH_PATH")
QUOTE_TTL_SECONDS: int = int(os.getenv("QUOTE_TTL_SECONDS", "300"))
