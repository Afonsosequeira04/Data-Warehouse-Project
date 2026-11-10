"""NASA FIRMS API client, secret loading and payload validation.

Source contract (verified in the P4b spike, see
``tests/fixtures/nasa_firms_fires/README.md``):

- ``GET /api/data_availability/csv/<MAP_KEY>/<DATA_ID>`` returns a two-row CSV
  with ``data_id,min_date,max_date``.
- ``GET /api/area/csv/<MAP_KEY>/<DATA_ID>/<AREA>/<DAY_RANGE>[/<DATE>]`` returns
  the fire detections for that area and window, repeating the 14-column header.
  ``DAY_RANGE`` must be between 1 and 5 inclusive.
- A response with only the header is valid and means "no detections".

The API key travels inside the URL path, so every URL, exception message and
log record derived from a request is redacted before it leaves this module.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass
from datetime import date

import boto3
import requests

from ingestion.core.http import build_session, install_log_redaction, redact
from ingestion.core.ids import require_text

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://firms.modaps.eosdis.nasa.gov"
DEFAULT_SECRET_ID = "cloud-data-platform/firms"

EXPECTED_COLUMNS = (
    "latitude",
    "longitude",
    "bright_ti4",
    "scan",
    "track",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
    "confidence",
    "version",
    "bright_ti5",
    "frp",
    "daynight",
)
EXPECTED_HEADER = ",".join(EXPECTED_COLUMNS)
COLUMN_COUNT = len(EXPECTED_COLUMNS)

MIN_DAY_RANGE = 1
MAX_DAY_RANGE = 5

MAX_SAMPLE_CHARS = 2000
MAX_BODY_BYTES = 20 * 1024 * 1024

AVAILABILITY_TIMEOUT = (10, 60)
AREA_TIMEOUT = (10, 120)

_AVAILABILITY_HEADER = ("data_id", "min_date", "max_date")


class FirmsError(Exception):
    """Base error for NASA FIRMS ingestion."""


class FirmsRequestError(FirmsError):
    """The HTTP request itself failed (network, DNS, TLS, timeout)."""


class FirmsHTTPError(FirmsError):
    """The API answered with a non-200 status."""

    def __init__(self, *, status_code: int, url: str, body_sample: str | None = None):
        message = f"HTTP {status_code} from {url}"
        if body_sample:
            message = f"{message}: {body_sample}"
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.body_sample = body_sample


class FirmsPayloadError(FirmsError):
    """The response body does not match the documented CSV shape."""

    error_type = "payload_error"

    def __init__(
        self,
        reason: str,
        *,
        sample: str | None = None,
        url: str | None = None,
    ):
        super().__init__(reason)
        self.reason = reason
        self.sample = sample
        self.url = url


@dataclass(frozen=True)
class FirmsCredentials:
    """FIRMS API key and base URL."""

    map_key: str
    base_url: str = DEFAULT_BASE_URL

    def __post_init__(self) -> None:
        require_text(self.map_key, "map_key")
        require_text(self.base_url, "base_url")


@dataclass(frozen=True)
class Availability:
    """Per-satellite data availability window."""

    data_id: str
    min_date: date
    max_date: date


@dataclass(frozen=True)
class AreaResponse:
    """A structurally valid area response for one satellite and date."""

    data_id: str
    date: str | None
    day_range: int
    body: bytes
    row_count: int
    url: str


def load_credentials(
    secret_id: str = DEFAULT_SECRET_ID, *, client=None
) -> FirmsCredentials:
    """Load FIRMS credentials from AWS Secrets Manager.

    The secret must be a JSON object with a ``map_key`` field and an optional
    ``base_url`` override. Nothing from the secret is ever included in an error
    message.
    """
    secrets_client = client or boto3.client("secretsmanager")
    try:
        response = secrets_client.get_secret_value(SecretId=secret_id)
        payload = json.loads(response["SecretString"])
        map_key = payload["map_key"]
        base_url = payload.get("base_url") or DEFAULT_BASE_URL
        return FirmsCredentials(map_key=map_key, base_url=base_url)
    except (KeyError, TypeError, ValueError):
        raise FirmsError(
            f"Secret {secret_id} is missing map_key or is not valid JSON"
        ) from None


def _decode_prefix(body: bytes) -> str:
    """Decode the leading bytes of a body for diagnostics."""
    return body[:MAX_SAMPLE_CHARS].decode("utf-8", errors="replace")


def _truncate(text: str) -> str:
    return text[:MAX_SAMPLE_CHARS]


def _validate_day_range(day_range: int) -> int:
    if isinstance(day_range, bool) or not isinstance(day_range, int):
        raise ValueError(f"day_range must be an integer: {day_range!r}")
    if not MIN_DAY_RANGE <= day_range <= MAX_DAY_RANGE:
        raise ValueError(
            f"day_range must be between {MIN_DAY_RANGE} and {MAX_DAY_RANGE}: "
            f"{day_range!r}"
        )
    return day_range


def _validate_date_text(date_text: str) -> str:
    try:
        parsed = date.fromisoformat(date_text)
    except (TypeError, ValueError):
        raise ValueError(
            f"date must be ISO-8601 (YYYY-MM-DD): {date_text!r}"
        ) from None
    if parsed.isoformat() != date_text:
        raise ValueError(f"date must be ISO-8601 (YYYY-MM-DD): {date_text!r}")
    return date_text


def _parse_data_date(value: str, *, url: str | None = None) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise FirmsPayloadError(
            f"invalid date in data_availability: {value!r}", url=url
        ) from None


def _validate_data_id(data_id: str) -> str:
    return require_text(data_id, "data_id")


class FirmsClient:
    """Minimal NASA FIRMS client with redaction and structural validation."""

    def __init__(
        self,
        credentials: FirmsCredentials,
        *,
        session: requests.Session | None = None,
    ):
        self.credentials = credentials
        self._session = session or build_session()
        install_log_redaction(credentials.map_key)

    def _redact(self, text: str) -> str:
        return redact(text, self.credentials.map_key)

    def _url(self, path: str) -> str:
        return f"{self.credentials.base_url.rstrip('/')}{path}"

    def _get(self, path: str, *, timeout: tuple[int, int]) -> tuple[bytes, str]:
        url = self._url(path)
        safe_url = self._redact(url)
        try:
            response = self._session.get(url, timeout=timeout)
        except requests.RequestException as exc:
            message = f"GET {safe_url} failed: {exc}"
            raise FirmsRequestError(self._redact(message)) from None

        if response.status_code != 200:
            sample = _truncate(self._redact(_decode_prefix(response.content)))
            raise FirmsHTTPError(
                status_code=response.status_code,
                url=safe_url,
                body_sample=sample,
            )

        content = response.content
        if len(content) > MAX_BODY_BYTES:
            raise FirmsPayloadError(
                f"response body exceeds {MAX_BODY_BYTES} bytes",
                sample=_truncate(self._redact(_decode_prefix(content))),
                url=safe_url,
            )
        return content, safe_url

    def get_data_availability(self, data_id: str) -> Availability:
        """Return the satellite's available date window."""
        data_id = _validate_data_id(data_id)
        path = (
            f"/api/data_availability/csv/{self.credentials.map_key}/{data_id}"
        )
        content, safe_url = self._get(path, timeout=AVAILABILITY_TIMEOUT)
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FirmsPayloadError(
                f"data_availability is not valid UTF-8: {exc}",
                sample=_decode_prefix(content),
                url=safe_url,
            ) from None

        reader = csv.reader(io.StringIO(text.lstrip("\ufeff"), newline=""))
        header = next(reader, None)
        if header is None or tuple(header) != _AVAILABILITY_HEADER:
            raise FirmsPayloadError(
                "unexpected data_availability header",
                sample=_truncate(text),
                url=safe_url,
            )

        row = next(reader, None)
        if row is None or len(row) != len(_AVAILABILITY_HEADER):
            raise FirmsPayloadError(
                "data_availability is missing the data row",
                sample=_truncate(text),
                url=safe_url,
            )
        if next(reader, None) is not None:
            raise FirmsPayloadError(
                "data_availability has more than one data row",
                sample=_truncate(text),
                url=safe_url,
            )
        if row[0] != data_id:
            raise FirmsPayloadError(
                f"data_availability returned {row[0]!r} for {data_id!r}",
                sample=_truncate(text),
                url=safe_url,
            )

        return Availability(
            data_id=data_id,
            min_date=_parse_data_date(row[1], url=safe_url),
            max_date=_parse_data_date(row[2], url=safe_url),
        )

    def fetch_area(
        self,
        data_id: str,
        *,
        day_range: int,
        date: str | None = None,
    ) -> AreaResponse:
        """Fetch one area CSV and validate its structural shape."""
        data_id = _validate_data_id(data_id)
        day_range = _validate_day_range(day_range)
        if date is not None:
            date = _validate_date_text(date)

        path = (
            f"/api/area/csv/{self.credentials.map_key}/{data_id}/world/{day_range}"
        )
        if date is not None:
            path = f"{path}/{date}"

        content, safe_url = self._get(path, timeout=AREA_TIMEOUT)
        row_count = validate_area_body(content, url=safe_url)
        return AreaResponse(
            data_id=data_id,
            date=date,
            day_range=day_range,
            body=content,
            row_count=row_count,
            url=safe_url,
        )


def validate_area_body(body: bytes, *, url: str | None = None) -> int:
    """Validate one area CSV body and return its data row count.

    The whole file is rejected when the header does not match or any row does
    not have exactly :data:`COLUMN_COUNT` fields. Semantic checks (types,
    ranges, duplicates) belong to dbt, not to ingestion.
    """
    if not body:
        raise FirmsPayloadError("response body is empty", url=url)

    stream = io.TextIOWrapper(
        io.BytesIO(body), encoding="utf-8-sig", newline=""
    )
    reader = csv.reader(stream)
    try:
        header = next(reader, None)
        if header is None:
            raise FirmsPayloadError("response body is empty", url=url)
        if tuple(header) != EXPECTED_COLUMNS:
            raise FirmsPayloadError(
                "unexpected CSV header",
                sample=_truncate(_decode_prefix(body)),
                url=url,
            )
        row_count = 0
        for row in reader:
            if len(row) != COLUMN_COUNT:
                raise FirmsPayloadError(
                    f"row {row_count + 2} has {len(row)} fields, "
                    f"expected {COLUMN_COUNT}",
                    sample=_truncate(_decode_prefix(body)),
                    url=url,
                )
            row_count += 1
    except UnicodeDecodeError as exc:
        raise FirmsPayloadError(
            f"response body is not valid UTF-8: {exc}",
            sample=_decode_prefix(body),
            url=url,
        ) from None
    return row_count
