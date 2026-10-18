"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "world_bank"
FRED_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fred"


@pytest.fixture
def gdp_growth_page1() -> dict:
    """Valid GDP growth page 1 response."""
    with open(FIXTURES_DIR / "gdp_growth_page1.json") as f:
        return json.load(f)


@pytest.fixture
def gdp_growth_page2() -> dict:
    """Valid GDP growth page 2 response (last page)."""
    with open(FIXTURES_DIR / "gdp_growth_page2.json") as f:
        return json.load(f)


@pytest.fixture
def api_error_payload() -> dict:
    """API error payload returned as HTTP 200."""
    with open(FIXTURES_DIR / "api_error_payload.json") as f:
        return json.load(f)


@pytest.fixture
def invalid_schema_response() -> dict:
    """Response with invalid schema (data is not a list)."""
    with open(FIXTURES_DIR / "invalid_schema.json") as f:
        return json.load(f)


@pytest.fixture
def mock_world_bank_config():
    """Mock World Bank configuration for testing."""
    from ingestion.api.world_bank_client import WorldBankConfig
    return WorldBankConfig(
        base_url="https://api.worldbank.org/v2",
        indicators=("NY.GDP.MKTP.KD.ZG",),
        countries="all",
        per_page=500,
        max_pages=2,
        date_range="2023:2023",
        rate_limit_rps=1000.0,  # Fast for tests
        max_retries=0,
        timeout_seconds=5,
    )


@pytest.fixture
def fred_unrate_page1() -> dict:
    """Valid FRED UNRATE page 1 response (includes a '.' value)."""
    with open(FRED_FIXTURES_DIR / "unrate_page1.json") as f:
        return json.load(f)


@pytest.fixture
def fred_unrate_page2() -> dict:
    """Valid FRED UNRATE page 2 response (last page)."""
    with open(FRED_FIXTURES_DIR / "unrate_page2.json") as f:
        return json.load(f)


@pytest.fixture
def fred_api_error_payload() -> dict:
    """FRED error payload returned as HTTP 200."""
    with open(FRED_FIXTURES_DIR / "api_error_payload.json") as f:
        return json.load(f)


@pytest.fixture
def fred_missing_fields_page() -> dict:
    """FRED page with an observation missing required fields."""
    with open(FRED_FIXTURES_DIR / "missing_fields_page.json") as f:
        return json.load(f)


@pytest.fixture
def mock_fred_config():
    """Mock FRED configuration for testing."""
    from ingestion.api.fred_client import FredConfig
    return FredConfig(
        api_key="test_fred_key",
        base_url="https://api.stlouisfed.org/fred",
        series_ids=("UNRATE",),
        limit=2,
        max_pages=10,
        rate_limit_rps=1000.0,  # Fast for tests
        max_retries=0,
        timeout_seconds=5,
    )