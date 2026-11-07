"""Tests for the shared batch identifier and S3-safe token helpers."""

from __future__ import annotations

import re

import pytest

from ingestion.core.ids import (
    SAFE_TOKEN_UNKNOWN,
    generate_batch_id,
    get_ingest_date,
    require_text,
    safe_token,
    validate_ingest_date,
)


class TestRequireText:
    """require_text rejects blank or non-string configuration values."""

    def test_returns_value_unchanged(self) -> None:
        assert require_text("api/emsc", "raw_prefix") == "api/emsc"

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="raw_prefix must be a non-empty string"):
            require_text("", "raw_prefix")

    def test_rejects_whitespace_only_string(self) -> None:
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            require_text("   ", "name")

    def test_rejects_non_string(self) -> None:
        with pytest.raises(ValueError, match="source must be a non-empty string"):
            require_text(123, "source")  # type: ignore[arg-type]


class TestSafeToken:
    """safe_token turns arbitrary text into a filename-safe S3 path token."""

    def test_replaces_unsafe_characters_with_underscore(self) -> None:
        assert safe_token("v1.2/data") == "v1.2_data"

    def test_keeps_dots_in_versioned_names(self) -> None:
        assert safe_token("page-1.2_final") == "page-1.2_final"

    def test_trims_leading_and_trailing_separators(self) -> None:
        assert safe_token("._-report._-") == "report"

    def test_lowercases_only_when_requested(self) -> None:
        assert safe_token("NASA_FIRMS") == "NASA_FIRMS"
        assert safe_token("NASA_FIRMS", lowercase=True) == "nasa_firms"

    @pytest.mark.parametrize("value", ["", "   ", "...", "/", "._-"])
    def test_falls_back_to_unknown_for_empty_tokens(self, value: str) -> None:
        assert safe_token(value) == SAFE_TOKEN_UNKNOWN


class TestGenerateBatchId:
    """generate_batch_id produces a unique, source-prefixed batch id."""

    def test_matches_expected_format(self) -> None:
        batch_id = generate_batch_id("NASA FIRMS")
        assert re.fullmatch(
            r"nasa_firms_\d{8}T\d{6}Z_[0-9a-f]{12}", batch_id
        ), batch_id

    def test_is_unique_per_call(self) -> None:
        batch_ids = {generate_batch_id("emsc") for _ in range(1000)}
        assert len(batch_ids) == 1000

    @pytest.mark.parametrize("source", ["", "   "])
    def test_rejects_blank_source(self, source: str) -> None:
        with pytest.raises(ValueError, match="source must be a non-empty string"):
            generate_batch_id(source)


class TestIngestDate:
    """get_ingest_date and validate_ingest_date agree on the ISO-8601 form."""

    def test_get_ingest_date_is_iso_8601_date(self) -> None:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", get_ingest_date())

    def test_get_ingest_date_validates(self) -> None:
        ingest_date = get_ingest_date()
        assert validate_ingest_date(ingest_date) == ingest_date

    def test_validate_accepts_valid_date(self) -> None:
        assert validate_ingest_date("2026-11-07") == "2026-11-07"

    @pytest.mark.parametrize(
        "ingest_date",
        [
            "2026-11-7",
            "20261107",
            "2026-13-01",
            "not-a-date",
            "2026-11-07T00:00:00",
            "",
        ],
    )
    def test_validate_rejects_non_canonical_dates(self, ingest_date: str) -> None:
        with pytest.raises(ValueError, match="ingest_date must be ISO-8601"):
            validate_ingest_date(ingest_date)
