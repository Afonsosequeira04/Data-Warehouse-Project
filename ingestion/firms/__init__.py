"""NASA FIRMS batch ingestion (P4b).

The package is split into four concerns:

- :mod:`ingestion.firms.client` - HTTP client, secret loading and structural
  validation of the CSV payload.
- :mod:`ingestion.firms.raw_writer` - immutable CSV raw storage on S3.
- :mod:`ingestion.firms.ingest` - per-satellite orchestration, backfill date
  selection, skip logic and quarantine routing.
"""

from ingestion.firms.client import (
    DEFAULT_BASE_URL,
    DEFAULT_SECRET_ID,
    EXPECTED_COLUMNS,
    MAX_DAY_RANGE,
    MIN_DAY_RANGE,
    AreaResponse,
    Availability,
    FirmsClient,
    FirmsCredentials,
    FirmsError,
    FirmsHTTPError,
    FirmsPayloadError,
    FirmsRequestError,
    load_credentials,
    validate_area_body,
)
from ingestion.firms.ingest import SATELLITES, run_ingestion, select_target_dates
from ingestion.firms.raw_writer import FirmsRawWriter

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_SECRET_ID",
    "EXPECTED_COLUMNS",
    "MAX_DAY_RANGE",
    "MIN_DAY_RANGE",
    "SATELLITES",
    "AreaResponse",
    "Availability",
    "FirmsClient",
    "FirmsCredentials",
    "FirmsError",
    "FirmsHTTPError",
    "FirmsPayloadError",
    "FirmsRawWriter",
    "FirmsRequestError",
    "load_credentials",
    "run_ingestion",
    "select_target_dates",
    "validate_area_body",
]
