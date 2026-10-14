"""World Bank Indicators API client.

Fetches macroeconomic indicators for countries from the World Bank API.
Implements pagination, rate limiting, bounded retries, and response validation.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorldBankConfig:
    """Configuration for World Bank API client."""

    base_url: str = "https://api.worldbank.org/v2"
    indicators: tuple[str, ...] = (
        "NY.GDP.MKTP.KD.ZG",   # GDP growth (annual %)
        "FP.CPI.TOTL.ZG",      # Inflation, consumer prices (annual %)
        "SL.UEM.TOTL.ZS",      # Unemployment, total (% of total labor force)
    )
    countries: str = "all"
    per_page: int = 500
    max_pages: int = 100
    date_range: str = "2014:2024"
    rate_limit_rps: float = 50.0
    max_retries: int = 3
    backoff_factor: float = 1.0
    timeout_seconds: int = 30


@dataclass(frozen=True)
class Observation:
    """A single World Bank observation."""

    country_id: str
    country_name: str
    indicator_id: str
    indicator_name: str
    year: int
    value: float | None
    unit: str
    obs_status: str | None
    decimal: int | None


class WorldBankAPIError(Exception):
    """Raised when the World Bank API returns an error response."""

    pass


class WorldBankClient:
    """Client for fetching data from the World Bank Indicators API."""

    def __init__(self, config: WorldBankConfig | None = None):
        self.config = config or WorldBankConfig()
        self._session = self._create_session()
        self._last_request_time = 0.0

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy."""
        session = requests.Session()
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        min_interval = 1.0 / self.config.rate_limit_rps
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _build_url(self, indicator: str, page: int) -> str:
        """Build the API URL for a given indicator and page."""
        base = self.config.base_url.rstrip("/")
        # Split base into scheme+netloc and path parts
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(base)
        base_path = parsed.path.rstrip("/")
        path = f"{base_path}/country/{self.config.countries}/indicator/{indicator}"
        params = {
            "format": "json",
            "per_page": self.config.per_page,
            "page": page,
            "date": self.config.date_range,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        # Reconstruct URL with proper path
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            path,
            "",
            query,
            "",
        ))

    def _validate_response(self, response: requests.Response, indicator: str, page: int) -> list[dict]:
        """Validate API response structure and extract data.

        World Bank API can return HTTP 200 with an error payload like:
        [{"message": [{"id": "120", "key": "Invalid value", "value": "The provided parameter value is not valid"}]}]
        """
        if response.status_code != 200:
            raise WorldBankAPIError(
                f"HTTP {response.status_code} for {indicator} page {page}: {response.text[:500]}"
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as e:
            raise WorldBankAPIError(f"Invalid JSON for {indicator} page {page}: {e}") from e

        if not isinstance(payload, list) or len(payload) < 2:
            raise WorldBankAPIError(
                f"Unexpected response structure for {indicator} page {page}: {payload}"
            )

        metadata, data = payload[0], payload[1]

        if not isinstance(metadata, dict):
            raise WorldBankAPIError(f"Invalid metadata for {indicator} page {page}: {metadata}")

        if "message" in metadata:
            messages = metadata["message"]
            if isinstance(messages, list) and messages:
                msg = messages[0]
                raise WorldBankAPIError(
                    f"API error for {indicator} page {page}: {msg.get('key', 'Unknown')} - {msg.get('value', '')}"
                )

        if data is None:
            return []

        if not isinstance(data, list):
            raise WorldBankAPIError(f"Data is not a list for {indicator} page {page}: {type(data)}")

        return data

    def _parse_observation(self, item: dict, indicator: str) -> Observation | None:
        """Parse a single observation from the API response."""
        try:
            country = item.get("country", {})
            country_id = country.get("id", "")
            country_name = country.get("value", "")

            indicator_info = item.get("indicator", {})
            indicator_id = indicator_info.get("id", indicator)
            indicator_name = indicator_info.get("value", indicator)

            year_str = item.get("date", "")
            if not year_str.isdigit():
                logger.warning(f"Invalid year '{year_str}' for {indicator_id}, skipping")
                return None
            year = int(year_str)

            value = item.get("value")
            if value is not None:
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    logger.warning(f"Non-numeric value '{value}' for {indicator_id}/{year}, treating as null")
                    value = None

            unit = item.get("unit", "")
            obs_status = item.get("obs_status")
            decimal = item.get("decimal")
            if decimal is not None:
                try:
                    decimal = int(decimal)
                except (TypeError, ValueError):
                    decimal = None

            return Observation(
                country_id=country_id,
                country_name=country_name,
                indicator_id=indicator_id,
                indicator_name=indicator_name,
                year=year,
                value=value,
                unit=unit,
                obs_status=obs_status,
                decimal=decimal,
            )
        except Exception as e:
            logger.warning(f"Failed to parse observation for {indicator}: {e}")
            return None

    def fetch_indicator(self, indicator: str) -> Iterator[Observation]:
        """Fetch all pages for a single indicator."""
        for page in range(1, self.config.max_pages + 1):
            self._rate_limit()
            url = self._build_url(indicator, page)
            logger.info(f"Fetching {indicator} page {page}")

            try:
                response = self._session.get(url, timeout=self.config.timeout_seconds)
            except requests.RequestException as e:
                raise WorldBankAPIError(f"Request failed for {indicator} page {page}: {e}") from e

            data = self._validate_response(response, indicator, page)

            if not data:
                logger.info(f"No more data for {indicator} at page {page}")
                break

            parsed_count = 0
            for item in data:
                obs = self._parse_observation(item, indicator)
                if obs is not None:
                    yield obs
                    parsed_count += 1

            logger.info(f"Parsed {parsed_count} observations from {indicator} page {page}")

            metadata = response.json()[0]
            total_pages = metadata.get("pages", 1)
            if page >= total_pages:
                break

    def fetch_all(self) -> Iterator[Observation]:
        """Fetch all configured indicators."""
        for indicator in self.config.indicators:
            logger.info(f"Starting fetch for indicator: {indicator}")
            yield from self.fetch_indicator(indicator)

    def fetch_raw_pages(self, indicator: str) -> Iterator[tuple[int, list[dict]]]:
        """Fetch raw API pages for an indicator (for raw S3 storage).

        Yields tuples of (page_number, raw_data_list).
        """
        for page in range(1, self.config.max_pages + 1):
            self._rate_limit()
            url = self._build_url(indicator, page)
            logger.info(f"Fetching raw page {page} for {indicator}")

            try:
                response = self._session.get(url, timeout=self.config.timeout_seconds)
            except requests.RequestException as e:
                raise WorldBankAPIError(f"Request failed for {indicator} page {page}: {e}") from e

            data = self._validate_response(response, indicator, page)

            if not data:
                logger.info(f"No more data for {indicator} at page {page}")
                break

            yield page, data

            metadata = response.json()[0]
            total_pages = metadata.get("pages", 1)
            if page >= total_pages:
                break

    def close(self) -> None:
        """Close the underlying session."""
        self._session.close()

    def __enter__(self) -> WorldBankClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()