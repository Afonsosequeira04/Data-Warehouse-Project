"""FRED economic series API client.

Fetches observations for FRED series. Implements pagination, rate limiting,
bounded retries, and response validation. Pages that cannot be trusted as a
whole (invalid JSON, an error payload returned with HTTP 200) are returned
with a quarantine reason instead of being silently dropped, following the
boundary in ADR-002.

The api_key must never appear in logs, exceptions, or quarantine content;
all outbound error text and URLs are redacted before being exposed.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Self

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEFAULT_SERIES = (
    "CPIAUCSL",  # Consumer Price Index for All Urban Consumers
    "UNRATE",    # Unemployment rate
    "FEDFUNDS",  # Federal funds effective rate
)

REQUIRED_OBSERVATION_FIELDS = (
    "date",
    "value",
    "realtime_start",
    "realtime_end",
)


@dataclass(frozen=True)
class FredConfig:
    """Configuration for the FRED API client."""

    api_key: str = ""
    base_url: str = "https://api.stlouisfed.org/fred"
    series_ids: tuple[str, ...] = DEFAULT_SERIES
    limit: int = 1000
    max_pages: int = 100
    observation_start: str | None = None
    observation_end: str | None = None
    rate_limit_rps: float = 2.0  # FRED allows 120 requests per minute
    max_retries: int = 3
    backoff_factor: float = 1.0
    timeout_seconds: int = 30


@dataclass(frozen=True)
class RejectedObservation:
    """A single observation rejected during row-level validation."""

    observation: dict
    reason: str


@dataclass(frozen=True)
class FredPage:
    """A single FRED observations page and its validation outcome."""

    series_id: str
    offset: int
    count: int | None = None
    observations: tuple[dict, ...] = ()
    rejections: tuple[RejectedObservation, ...] = ()
    quarantine_reason: str | None = None
    quarantine_raw: str | None = None
    request_url: str = ""


class FredAPIError(Exception):
    """Raised when the FRED API cannot be read after retries."""


class RedactingFilter(logging.Filter):
    """Logging filter that replaces a secret in formatted log messages."""

    def __init__(self, secret: str):
        super().__init__()
        self._secret = secret

    @property
    def secret(self) -> str:
        return self._secret

    def filter(self, record: logging.LogRecord) -> bool:
        if self._secret and self._secret in record.getMessage():
            record.msg = record.getMessage().replace(self._secret, "***")
            record.args = ()
        return True


def _validate_date_string(value: str, name: str) -> None:
    """Validate an ISO date (YYYY-MM-DD) configuration value."""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise ValueError(
            f"{name} must be an ISO date (YYYY-MM-DD), got: {value!r}"
        ) from None


def _observation_rejection_reason(item: object) -> str | None:
    """Return why an observation is invalid, or None when it is acceptable."""
    if not isinstance(item, dict):
        return "observation is not a JSON object"
    missing = [name for name in REQUIRED_OBSERVATION_FIELDS if item.get(name) is None]
    if missing:
        return f"missing required field(s): {', '.join(missing)}"
    return None


class FredClient:
    """Client for fetching observations from the FRED API."""

    def __init__(self, config: FredConfig | None = None):
        self.config = config or FredConfig()
        if not self.config.api_key:
            raise ValueError("FRED api_key is required")
        if self.config.observation_start is not None:
            _validate_date_string(self.config.observation_start, "observation_start")
        if self.config.observation_end is not None:
            _validate_date_string(self.config.observation_end, "observation_end")
        self._session = self._create_session()
        self._last_request_time = 0.0
        self._install_log_redaction()

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

    def _install_log_redaction(self) -> None:
        """Make sure the api_key is masked in our logs and urllib3 logs.

        urllib3 emits request URLs (which carry the api_key) from several
        loggers, notably ``urllib3.connectionpool`` and ``urllib3.util.retry``
        during retries, so every one of them needs the redacting filter.
        """
        urllib3_loggers = (
            "urllib3",
            "urllib3.connectionpool",
            "urllib3.util.retry",
            "urllib3.poolmanager",
        )
        for target in (logger, *(logging.getLogger(name) for name in urllib3_loggers)):
            already_installed = any(
                isinstance(existing, RedactingFilter)
                and existing.secret == self.config.api_key
                for existing in target.filters
            )
            if not already_installed:
                target.addFilter(RedactingFilter(self.config.api_key))

    def _redact(self, text: str) -> str:
        """Replace the api_key in text so it never leaks."""
        return text.replace(self.config.api_key, "***")

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        min_interval = 1.0 / self.config.rate_limit_rps
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _observations_url(self) -> str:
        """Build the observations endpoint URL for the configured base URL."""
        return f"{self.config.base_url.rstrip('/')}/series/observations"

    def _build_params(self, series_id: str, offset: int) -> dict[str, str | int]:
        """Build the query parameters for one observations page."""
        params: dict[str, str | int] = {
            "series_id": series_id,
            "api_key": self.config.api_key,
            "file_type": "json",
            "limit": self.config.limit,
            "offset": offset,
            "sort_order": "asc",
        }
        if self.config.observation_start is not None:
            params["observation_start"] = self.config.observation_start
        if self.config.observation_end is not None:
            params["observation_end"] = self.config.observation_end
        return params

    def _parse_page(
        self, series_id: str, offset: int, response: requests.Response
    ) -> FredPage:
        """Validate one response body and separate valid observations."""
        request_url = self._redact(response.url)

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as e:
            logger.warning(
                f"FRED returned invalid JSON for {series_id} at offset {offset}: {e}"
            )
            return FredPage(
                series_id=series_id,
                offset=offset,
                quarantine_reason=f"invalid_json: {e}",
                quarantine_raw=self._redact(response.text),
                request_url=request_url,
            )

        if not isinstance(payload, dict):
            return FredPage(
                series_id=series_id,
                offset=offset,
                quarantine_reason="invalid_payload: response is not a JSON object",
                quarantine_raw=self._redact(response.text),
                request_url=request_url,
            )

        error_code = payload.get("error_code")
        error_message = payload.get("error_message")
        if error_code is not None or error_message is not None:
            reason = f"api_error: code={error_code} message={error_message}"
            return FredPage(
                series_id=series_id,
                offset=offset,
                quarantine_reason=self._redact(reason),
                quarantine_raw=self._redact(response.text),
                request_url=request_url,
            )

        observations = payload.get("observations")
        if not isinstance(observations, list):
            return FredPage(
                series_id=series_id,
                offset=offset,
                quarantine_reason="invalid_payload: missing observations list",
                quarantine_raw=self._redact(response.text),
                request_url=request_url,
            )

        count = payload.get("count")
        if not isinstance(count, int):
            count = None

        accepted: list[dict] = []
        rejected: list[RejectedObservation] = []
        for item in observations:
            reason = _observation_rejection_reason(item)
            if reason is None:
                accepted.append(item)
                continue
            rejected.append(
                RejectedObservation(
                    observation=item if isinstance(item, dict) else {"raw": item},
                    reason=reason,
                )
            )
            logger.warning(
                f"Rejected FRED observation for {series_id} at offset {offset}: {reason}"
            )

        return FredPage(
            series_id=series_id,
            offset=offset,
            count=count,
            observations=tuple(accepted),
            rejections=tuple(rejected),
            request_url=request_url,
        )

    def fetch_series(self, series_id: str) -> Iterator[FredPage]:
        """Fetch all observation pages for a single FRED series.

        Stops at the reported observation count, at an empty page, at
        ``max_pages``, or after a page that must be quarantined. The
        quarantined page is yielded so callers can persist it.
        """
        offset = 0
        for _ in range(self.config.max_pages):
            self._rate_limit()
            logger.info(f"Fetching FRED series {series_id} offset {offset}")

            try:
                response = self._session.get(
                    self._observations_url(),
                    params=self._build_params(series_id, offset),
                    timeout=self.config.timeout_seconds,
                )
            except requests.RequestException as e:
                raise FredAPIError(
                    self._redact(
                        f"Request failed for FRED series {series_id} "
                        f"offset {offset}: {e}"
                    )
                ) from None

            if response.status_code != 200:
                raise FredAPIError(
                    self._redact(
                        f"HTTP {response.status_code} for FRED series {series_id} "
                        f"offset {offset}: {response.text[:500]}"
                    )
                )

            page = self._parse_page(series_id, offset, response)
            yield page

            if page.quarantine_reason is not None:
                logger.warning(
                    f"Quarantined FRED page for {series_id} at offset {offset}: "
                    f"{page.quarantine_reason}"
                )
                return

            page_size = len(page.observations) + len(page.rejections)
            if page_size == 0:
                # Empty page: no more data even if ``count`` claims otherwise.
                return
            offset += self.config.limit
            if page.count is not None:
                if offset >= page.count:
                    return
            elif page_size < self.config.limit:
                return

    def close(self) -> None:
        """Close the underlying session."""
        self._session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
