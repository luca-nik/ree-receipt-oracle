"""Subprocess wrapper for ree.sh verify."""

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import REE_SH_PATH


@dataclass
class ReeResult:
    valid: bool
    error: str | None = None


def run_verify(receipt: dict) -> ReeResult:
    """Write receipt to a temp file and invoke ree.sh verify.

    Returns ReeResult with valid=True if verification passed.
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        prefix="ree_receipt_",
    ) as f:
        json.dump(receipt, f)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["bash", REE_SH_PATH, "verify", "--receipt-path", tmp_path],
            capture_output=True,
            text=True,
            timeout=600,  # 10 min max — model re-run can be slow
        )
        if result.returncode == 0:
            return ReeResult(valid=True)
        else:
            stderr = (result.stderr or result.stdout or "").strip()
            return ReeResult(valid=False, error=stderr or "REE verification failed")
    except subprocess.TimeoutExpired:
        return ReeResult(valid=False, error="REE verification timed out")
    except Exception as exc:
        return ReeResult(valid=False, error=str(exc))
    finally:
        Path(tmp_path).unlink(missing_ok=True)
