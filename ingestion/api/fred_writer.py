"""Write raw FRED observations and quarantine payloads to S3."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable

import boto3

SOURCE_SYSTEM = "fred"
MAX_ERROR_TOKEN_LENGTH = 64

_SAFE_TOKEN_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def generate_batch_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"fred_{timestamp}_{uuid.uuid4().hex[:12]}"


def get_ingest_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _require_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _safe_token(value: str, *, lowercase: bool = False) -> str:
    token = _SAFE_TOKEN_PATTERN.sub("_", value.strip())
    token = token.strip("._-")
    token = token.lower() if lowercase else token
    return token or "unknown"


def _validate_ingest_date(ingest_date: str) -> str:
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


@dataclass(frozen=True)
class FredWriterConfig:
    raw_bucket: str
    raw_prefix: str = "api/fred_economic_series"
    quarantine_prefix: str = "quarantine/api/fred_economic_series"

    def __post_init__(self) -> None:
        for name in ("raw_bucket", "raw_prefix", "quarantine_prefix"):
            _require_text(getattr(self, name), name)


@dataclass(frozen=True)
class FredWriteResult:
    bucket: str
    key: str
    size_bytes: int
    etag: str
    written_at: datetime
    record_count: int | None = None


class FredWriter:
    def __init__(self, config: FredWriterConfig, s3_client: Any | None = None) -> None:
        self.config = config
        self._s3_client = s3_client

    def _client(self) -> Any:
        if self._s3_client is None:
            self._s3_client = boto3.client("s3")
        return self._s3_client

    def _build_raw_key(
        self,
        ingest_date: str,
        batch_id: str,
        series_id: str,
    ) -> str:
        _validate_ingest_date(ingest_date)
        _require_text(batch_id, "batch_id")
        _require_text(series_id, "series_id")
        prefix = self.config.raw_prefix.rstrip("/")
        return (
            f"{prefix}/ingest_date={ingest_date}/"
            f"{_safe_token(batch_id)}/{_safe_token(series_id)}.ndjson"
        )

    def _build_quarantine_key(
        self,
        ingest_date: str,
        batch_id: str,
        series_id: str,
        error_type: str,
    ) -> str:
        _validate_ingest_date(ingest_date)
        _require_text(batch_id, "batch_id")
        _require_text(series_id, "series_id")
        _require_text(error_type, "error_type")
        prefix = self.config.quarantine_prefix.rstrip("/")
        error_token = _safe_token(error_type, lowercase=True)[:MAX_ERROR_TOKEN_LENGTH]
        return (
            f"{prefix}/ingest_date={ingest_date}/"
            f"{_safe_token(batch_id)}/{_safe_token(series_id)}_{error_token}.json"
        )

    def write_series(
        self,
        ingest_date: str,
        batch_id: str,
        series_id: str,
        observations: Iterable[dict[str, Any]],
    ) -> FredWriteResult:
        records = list(observations)
        if not records:
            raise ValueError(f"No observations to write for FRED series {series_id!r}")

        key = self._build_raw_key(ingest_date, batch_id, series_id)
        body = "".join(
            json.dumps(record, ensure_ascii=False) + "\n" for record in records
        ).encode("utf-8")
        response = self._client().put_object(
            Bucket=self.config.raw_bucket,
            Key=key,
            Body=body,
            ContentType="application/x-ndjson",
            Metadata={
                "source-system": SOURCE_SYSTEM,
                "batch-id": batch_id,
                "series-id": series_id,
                "record-count": str(len(records)),
            },
        )
        return FredWriteResult(
            bucket=self.config.raw_bucket,
            key=key,
            size_bytes=len(body),
            etag=str(response.get("ETag", "")).strip('"'),
            written_at=datetime.now(timezone.utc),
            record_count=len(records),
        )

    def write_quarantine(
        self,
        ingest_date: str,
        batch_id: str,
        series_id: str,
        error_type: str,
        error_message: str,
        raw_data: Any | None = None,
        response_metadata: dict[str, Any] | None = None,
    ) -> FredWriteResult:
        _require_text(error_type, "error_type")
        key = self._build_quarantine_key(ingest_date, batch_id, series_id, error_type)
        payload: dict[str, Any] = {
            "source_system": SOURCE_SYSTEM,
            "series_id": series_id,
            "batch_id": batch_id,
            "ingest_date": _validate_ingest_date(ingest_date),
            "error_type": error_type,
            "error_message": error_message,
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
        }
        if raw_data is not None:
            payload["raw_data"] = raw_data
        if response_metadata is not None:
            payload["response_metadata"] = response_metadata

        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        response = self._client().put_object(
            Bucket=self.config.raw_bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata={
                "source-system": SOURCE_SYSTEM,
                "batch-id": batch_id,
                "series-id": series_id,
                "error-type": _safe_token(error_type, lowercase=True)[
                    :MAX_ERROR_TOKEN_LENGTH
                ],
            },
        )
        return FredWriteResult(
            bucket=self.config.raw_bucket,
            key=key,
            size_bytes=len(body),
            etag=str(response.get("ETag", "")).strip('"'),
            written_at=datetime.now(timezone.utc),
        )
