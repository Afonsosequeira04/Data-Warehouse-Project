"""Shared batch identifiers, ingestion dates and S3-safe tokens."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime

SAFE_TOKEN_UNKNOWN = "unknown"

_SAFE_TOKEN_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def require_text(value: str, name: str) -> str:
    """Return ``value`` when it is a non-empty string, else raise."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def safe_token(value: str, *, lowercase: bool = False) -> str:
    """Turn arbitrary text into a filename-safe S3 path token."""
    token = _SAFE_TOKEN_PATTERN.sub("_", value.strip())
    token = token.strip("._-")
    token = token.lower() if lowercase else token
    return token or SAFE_TOKEN_UNKNOWN


def generate_batch_id(source: str) -> str:
    """Generate a unique batch identifier for one ingestion run."""
    source_token = safe_token(require_text(source, "source"), lowercase=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{source_token}_{timestamp}_{uuid.uuid4().hex[:12]}"


def get_ingest_date() -> str:
    """Return the current UTC ingestion date as ``YYYY-MM-DD``."""
    return datetime.now(UTC).date().isoformat()


def validate_ingest_date(ingest_date: str) -> str:
    """Validate a ``YYYY-MM-DD`` ingestion date and return it unchanged."""
    try:
        parsed = date.fromisoformat(ingest_date)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"ingest_date must be ISO-8601 (YYYY-MM-DD): {ingest_date!r}"
        ) from exc
    if parsed.isoformat() != ingest_date:
        raise ValueError(
            f"ingest_date must be ISO-8601 (YYYY-MM-DD): {ingest_date!r}"
        )
    return ingest_date
