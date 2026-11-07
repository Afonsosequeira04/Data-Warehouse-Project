"""Immutable raw storage and quarantine writer.

Raw payloads are written once per ingestion under an ingestion-date path and
are never overwritten (see the raw path convention in AGENTS.md). Structurally
invalid payloads go to quarantine with enough metadata to diagnose why they
were rejected. The writer is deliberately source-agnostic: the caller supplies
the prefixes and the object name, so batch sources can use
``api/<source>/`` and streaming sources can use ``quarantine/stream/<source>/``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from ingestion.core.ids import require_text, safe_token, validate_ingest_date

logger = logging.getLogger(__name__)

MAX_ERROR_TOKEN_LENGTH = 64

RAW_CONTENT_TYPE = "application/x-ndjson"
QUARANTINE_CONTENT_TYPE = "application/json"


@dataclass(frozen=True)
class RawS3WriterConfig:
    """S3 locations and source identity for :class:`RawS3Writer`."""

    raw_bucket: str
    raw_prefix: str
    quarantine_prefix: str
    source_system: str

    def __post_init__(self) -> None:
        for name in ("raw_bucket", "raw_prefix", "quarantine_prefix", "source_system"):
            require_text(getattr(self, name), name)


@dataclass(frozen=True)
class WriteResult:
    """Result of one S3 write."""

    bucket: str
    key: str
    size_bytes: int
    etag: str
    written_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    record_count: int | None = None


class RawS3Writer:
    """Write raw payloads as NDJSON and rejected payloads to quarantine."""

    def __init__(self, config: RawS3WriterConfig, s3_client: Any | None = None):
        self.config = config
        self._s3 = s3_client

    @property
    def s3(self) -> Any:
        """Create the boto3 client lazily so importing costs nothing."""
        if self._s3 is None:
            self._s3 = boto3.client("s3")
        return self._s3

    def _build_raw_key(
        self,
        ingest_date: str,
        batch_id: str,
        name: str,
        page: int | None = None,
        extension: str = "ndjson",
    ) -> str:
        """Build ``{raw_prefix}/ingest_date=.../<batch>/<name>[_page_n].ext``."""
        validate_ingest_date(ingest_date)
        require_text(batch_id, "batch_id")
        safe_name = safe_token(require_text(name, "name"))
        parts = [
            self.config.raw_prefix,
            f"ingest_date={ingest_date}",
            batch_id,
            f"{safe_name}{self._page_suffix(page)}.{safe_token(extension, lowercase=True)}",
        ]
        return "/".join(parts)

    def _build_quarantine_key(
        self,
        ingest_date: str,
        batch_id: str,
        name: str,
        error_type: str,
        page: int | None = None,
    ) -> str:
        """Build the quarantine key for one rejected payload."""
        validate_ingest_date(ingest_date)
        require_text(batch_id, "batch_id")
        safe_name = safe_token(require_text(name, "name"))
        safe_error = safe_token(require_text(error_type, "error_type"), lowercase=True)
        safe_error = safe_error[:MAX_ERROR_TOKEN_LENGTH]
        parts = [
            self.config.quarantine_prefix,
            f"ingest_date={ingest_date}",
            batch_id,
            f"{safe_name}{self._page_suffix(page)}_{safe_error}.json",
        ]
        return "/".join(parts)

    @staticmethod
    def _page_suffix(page: int | None) -> str:
        if page is None:
            return ""
        if isinstance(page, bool) or not isinstance(page, int) or page < 0:
            raise ValueError(f"page must be a non-negative integer: {page!r}")
        return f"_page_{page:04d}"

    def write_raw_page(
        self,
        ingest_date: str,
        batch_id: str,
        name: str,
        data: list[dict],
        page: int | None = None,
        metadata: dict | None = None,
    ) -> WriteResult:
        """Write one raw payload as NDJSON (one JSON object per line)."""
        key = self._build_raw_key(ingest_date, batch_id, name, page=page)
        lines = [json.dumps(record, ensure_ascii=False) for record in data]
        body = "\n".join(lines).encode("utf-8")

        object_metadata = {
            "source": self.config.source_system,
            "name": safe_token(require_text(name, "name")),
            "batch_id": batch_id,
            "ingest_date": ingest_date,
            "record_count": str(len(data)),
        }
        if page is not None:
            object_metadata["page"] = str(page)
        for metadata_key, metadata_value in (metadata or {}).items():
            object_metadata[str(metadata_key).lower()] = str(metadata_value)

        try:
            response = self.s3.put_object(
                Bucket=self.config.raw_bucket,
                Key=key,
                Body=body,
                ContentType=RAW_CONTENT_TYPE,
                Metadata=object_metadata,
            )
        except ClientError:
            logger.error("Failed to write raw page to S3: %s", key)
            raise

        return WriteResult(
            bucket=self.config.raw_bucket,
            key=key,
            size_bytes=len(body),
            etag=response["ETag"].strip('"'),
            record_count=len(data),
        )

    def write_quarantine(
        self,
        ingest_date: str,
        batch_id: str,
        name: str,
        error_type: str,
        error_message: str,
        raw_data: Any = None,
        response_metadata: dict | None = None,
        page: int | None = None,
    ) -> WriteResult:
        """Write a structurally invalid payload to quarantine.

        Per ADR-002, payloads rejected at the file/schema level never reach raw
        or Bronze. The object keeps the reason, the source, the batch and the
        ingestion date so the rejection can be diagnosed later.
        """
        key = self._build_quarantine_key(
            ingest_date, batch_id, name, error_type, page=page
        )
        safe_name = safe_token(require_text(name, "name"))

        payload = {
            "source": self.config.source_system,
            "name": safe_name,
            "page": page,
            "batch_id": batch_id,
            "ingest_date": ingest_date,
            "rejected_at": datetime.now(UTC).isoformat(),
            "error_type": error_type,
            "error_message": error_message,
            "raw_data": raw_data,
            "response_metadata": response_metadata or {},
        }
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        object_metadata = {
            "source": self.config.source_system,
            "name": safe_name,
            "batch_id": batch_id,
            "ingest_date": ingest_date,
            "error_type": safe_token(error_type),
            "quarantined": "true",
        }
        if page is not None:
            object_metadata["page"] = str(page)

        try:
            response = self.s3.put_object(
                Bucket=self.config.raw_bucket,
                Key=key,
                Body=body,
                ContentType=QUARANTINE_CONTENT_TYPE,
                Metadata=object_metadata,
            )
        except ClientError:
            logger.error("Failed to write quarantine object to S3: %s", key)
            raise

        logger.warning(
            "Quarantined %s (batch %s, page %s): %s - %s",
            safe_name,
            batch_id,
            page,
            error_type,
            error_message,
        )

        return WriteResult(
            bucket=self.config.raw_bucket,
            key=key,
            size_bytes=len(body),
            etag=response["ETag"].strip('"'),
            record_count=len(raw_data) if isinstance(raw_data, list) else None,
        )
