"""Unit tests for World Bank API client."""

from __future__ import annotations

import pytest
import responses

from ingestion.api.world_bank_client import (
    Observation,
    WorldBankAPIError,
    WorldBankClient,
    WorldBankConfig,
)


class TestWorldBankClient:
    """Tests for WorldBankClient."""

    def test_build_url(self, mock_world_bank_config):
        """Test URL building with pagination and date range."""
        client = WorldBankClient(mock_world_bank_config)
        url = client._build_url("NY.GDP.MKTP.KD.ZG", 1)
        assert "NY.GDP.MKTP.KD.ZG" in url
        assert "page=1" in url
        assert "per_page=500" in url
        assert "date=2023:2023" in url  # date parameter uses unencoded colon
        assert url.startswith("https://api.worldbank.org/v2/")
        assert "format=json" in url

    @responses.activate
    def test_fetch_indicator_success(self, mock_world_bank_config, gdp_growth_page1, gdp_growth_page2):
        """Test successful fetch of an indicator across multiple pages."""
        indicator = "NY.GDP.MKTP.KD.ZG"
        base_url = mock_world_bank_config.base_url.rstrip("/")
        path = f"/country/{mock_world_bank_config.countries}/indicator/{indicator}"

        responses.get(
            f"{base_url}{path}",
            json=gdp_growth_page1,
            match=[
                responses.matchers.query_param_matcher({
                    "format": "json",
                    "per_page": "500",
                    "page": "1",
                    "date": "2023:2023",
                })
            ],
        )
        responses.get(
            f"{base_url}{path}",
            json=gdp_growth_page2,
            match=[
                responses.matchers.query_param_matcher({
                    "format": "json",
                    "per_page": "500",
                    "page": "2",
                    "date": "2023:2023",
                })
            ],
        )

        client = WorldBankClient(mock_world_bank_config)
        observations = list(client.fetch_indicator(indicator))

        assert len(observations) == 5
        assert all(isinstance(obs, Observation) for obs in observations)

        # Verify first observation
        obs = observations[0]
        assert obs.country_id == "ABW"
        assert obs.country_name == "Aruba"
        assert obs.indicator_id == "NY.GDP.MKTP.KD.ZG"
        assert obs.year == 2023
        assert obs.value == 2.5

        # Verify null value handling
        null_obs = observations[-1]
        assert null_obs.country_id == "AND"
        assert null_obs.value is None

    @responses.activate
    def test_fetch_indicator_http_error(self, mock_world_bank_config):
        """Test handling of HTTP errors."""
        indicator = "NY.GDP.MKTP.KD.ZG"
        base_url = mock_world_bank_config.base_url.rstrip("/")
        path = f"/country/{mock_world_bank_config.countries}/indicator/{indicator}"

        responses.get(
            f"{base_url}{path}",
            status=500,
            body="Internal Server Error",
        )

        client = WorldBankClient(mock_world_bank_config)
        with pytest.raises(WorldBankAPIError) as exc_info:
            list(client.fetch_indicator(indicator))

        assert "HTTP 500" in str(exc_info.value)

    @responses.activate
    def test_fetch_indicator_api_error_payload(self, mock_world_bank_config, api_error_payload):
        """Test handling of API error payload at HTTP 200."""
        indicator = "NY.GDP.MKTP.KD.ZG"
        base_url = mock_world_bank_config.base_url.rstrip("/")
        path = f"/country/{mock_world_bank_config.countries}/indicator/{indicator}"

        responses.get(
            f"{base_url}{path}",
            json=api_error_payload,
            status=200,
            match=[
                responses.matchers.query_param_matcher({
                    "format": "json",
                    "per_page": "500",
                    "page": "1",
                    "date": "2023:2023",
                })
            ],
        )

        client = WorldBankClient(mock_world_bank_config)
        with pytest.raises(WorldBankAPIError) as exc_info:
            list(client.fetch_indicator(indicator))

        assert "API error" in str(exc_info.value)
        assert "Invalid value" in str(exc_info.value)

    @responses.activate
    def test_fetch_indicator_invalid_schema(self, mock_world_bank_config, invalid_schema_response):
        """Test handling of invalid response schema."""
        indicator = "NY.GDP.MKTP.KD.ZG"
        base_url = mock_world_bank_config.base_url.rstrip("/")
        path = f"/country/{mock_world_bank_config.countries}/indicator/{indicator}"

        responses.get(
            f"{base_url}{path}",
            json=invalid_schema_response,
            status=200,
            match=[
                responses.matchers.query_param_matcher({
                    "format": "json",
                    "per_page": "500",
                    "page": "1",
                    "date": "2023:2023",
                })
            ],
        )

        client = WorldBankClient(mock_world_bank_config)
        with pytest.raises(WorldBankAPIError) as exc_info:
            list(client.fetch_indicator(indicator))

        assert "Data is not a list" in str(exc_info.value)

    @responses.activate
    def test_fetch_indicator_invalid_json(self, mock_world_bank_config):
        """Test handling of invalid JSON response."""
        indicator = "NY.GDP.MKTP.KD.ZG"
        base_url = mock_world_bank_config.base_url.rstrip("/")
        path = f"/country/{mock_world_bank_config.countries}/indicator/{indicator}"

        responses.get(
            f"{base_url}{path}",
            body="not valid json",
            status=200,
        )

        client = WorldBankClient(mock_world_bank_config)
        with pytest.raises(WorldBankAPIError) as exc_info:
            list(client.fetch_indicator(indicator))

        assert "Invalid JSON" in str(exc_info.value)

    @responses.activate
    def test_fetch_indicator_empty_page_ends_pagination(self, mock_world_bank_config):
        """Test that empty data page ends pagination."""
        indicator = "NY.GDP.MKTP.KD.ZG"
        base_url = mock_world_bank_config.base_url.rstrip("/")
        path = f"/country/{mock_world_bank_config.countries}/indicator/{indicator}"

        empty_response = [
            {"page": 1, "pages": 1, "per_page": 500, "total": 0, "source": [{"id": "2"}]},
            []
        ]

        responses.get(
            f"{base_url}{path}",
            json=empty_response,
            match=[
                responses.matchers.query_param_matcher({
                    "format": "json",
                    "per_page": "500",
                    "page": "1",
                    "date": "2023:2023",
                })
            ],
        )

        client = WorldBankClient(mock_world_bank_config)
        observations = list(client.fetch_indicator(indicator))

        assert len(observations) == 0

    @responses.activate
    def test_fetch_indicator_max_pages_limit(self, mock_world_bank_config):
        """Test that max_pages limit is respected."""
        indicator = "NY.GDP.MKTP.KD.ZG"
        base_url = mock_world_bank_config.base_url.rstrip("/")
        path = f"/country/{mock_world_bank_config.countries}/indicator/{indicator}"

        # Create a response that indicates more pages exist
        page_with_more = [
            {"page": 1, "pages": 10, "per_page": 500, "total": 5000, "source": [{"id": "2"}]},
            [{"country": {"id": "ABW"}, "indicator": {"id": indicator}, "date": "2023", "value": 1.0}]
        ]

        # Mock enough pages to hit max_pages - use date_range 2014:2024 to match default config
        for page in range(1, mock_world_bank_config.max_pages + 2):
            responses.get(
                f"{base_url}{path}",
                json=page_with_more,
                match=[
                    responses.matchers.query_param_matcher({
                        "format": "json",
                        "per_page": "500",
                        "page": str(page),
                        "date": "2014:2024",  # Default date_range from mock_world_bank_config
                    })
                ],
            )

        config = WorldBankConfig(
            base_url=mock_world_bank_config.base_url,
            indicators=(indicator,),
            max_pages=3,
            rate_limit_rps=1000.0,
            max_retries=0,
        )
        client = WorldBankClient(config)
        observations = list(client.fetch_indicator(indicator))

        # Should only fetch max_pages (3) even though API says 10 pages exist
        assert len(observations) == 3

    def test_parse_observation_with_null_value(self, mock_world_bank_config):
        """Test parsing observation with null value."""
        client = WorldBankClient(mock_world_bank_config)
        item = {
            "country": {"id": "TEST", "value": "Test Country"},
            "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth"},
            "date": "2023",
            "value": None,
            "unit": "%",
            "obs_status": "M",
            "decimal": 1,
        }
        obs = client._parse_observation(item, "NY.GDP.MKTP.KD.ZG")
        assert obs is not None
        assert obs.value is None

    def test_parse_observation_with_non_numeric_value(self, mock_world_bank_config):
        """Test parsing observation with non-numeric value."""
        client = WorldBankClient(mock_world_bank_config)
        item = {
            "country": {"id": "TEST", "value": "Test Country"},
            "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth"},
            "date": "2023",
            "value": "not_a_number",
            "unit": "%",
        }
        obs = client._parse_observation(item, "NY.GDP.MKTP.KD.ZG")
        assert obs is not None
        assert obs.value is None

    def test_parse_observation_with_invalid_year(self, mock_world_bank_config):
        """Test parsing observation with invalid year."""
        client = WorldBankClient(mock_world_bank_config)
        item = {
            "country": {"id": "TEST", "value": "Test Country"},
            "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth"},
            "date": "not_a_year",
            "value": 1.0,
        }
        obs = client._parse_observation(item, "NY.GDP.MKTP.KD.ZG")
        assert obs is None

    def test_context_manager(self, mock_world_bank_config):
        """Test client as context manager."""
        with WorldBankClient(mock_world_bank_config) as client:
            assert client._session is not None
        # Session should be closed after exit


class TestWorldBankConfig:
    """Tests for WorldBankConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = WorldBankConfig()
        assert config.base_url == "https://api.worldbank.org/v2"
        assert len(config.indicators) == 3
        assert "NY.GDP.MKTP.KD.ZG" in config.indicators
        assert config.per_page == 500
        assert config.max_pages == 100
        assert config.rate_limit_rps == 50.0