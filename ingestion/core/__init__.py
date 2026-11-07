"""Shared, source-agnostic ingestion utilities.

This package holds only helpers that are genuinely reused across sources:
HTTP session/retry setup with secret redaction, batch and ingest-date
identifiers, and the immutable raw/quarantine S3 writer. Source-specific
clients, payload parsing, pagination and validation stay next to the source
that owns them.
"""
