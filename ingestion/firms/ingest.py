"""NASA FIRMS fires ingestion orchestration.

Per satellite: read data_availability, select target dates, skip dates already
in raw, fetch one area CSV per date, store valid CSVs to raw and quarantine
invalid ones. One satellite failure never affects the others.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ingestion.core.ids import generate_batch_id, get_ingest_date
from ingestion.firms.client import (
    DEFAULT_SECRET_ID,
    AreaResponse,
    Availability,
    FirmsClient,
    FirmsCredentials,
    FirmsError,
    FirmsHTTPError,
    FirmsPayloadError,
    load_credentials,
    validate_area_body,
)
from ingestion.firms.raw_writer import (
    RAW_PREFIX,
    RAW_SOURCE_SYSTEM,
    FirmsRawWriter,
)

logger = logging.getLogger(__name__)

SATELLITES = (
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_NRT",
)

DAY_RANGE = 1
MAX_BACKFILL_DAYS = 7
LAG_WARN_DAYS = 3
HEADER_ONLY_ROW_COUNT = 0


def select_target_dates(max_date, min_date, backfill_days=0):
    """Return ISO date strings to request for one satellite.

    With ``backfill_days <= 0`` (daily run) only ``max_date`` is returned.
    With a positive backfill, dates run back from ``max_date`` for
    ``backfill_days`` days, each clamped to stay within ``[min_date,
    max_date]``; dates outside the window are excluded so they are never
    requested (the caller logs them as skipped).
    """
    if isinstance(max_date, str):
        max_date = date.fromisoformat(max_date)
    if isinstance(min_date, str):
        min_date = date.fromisoformat(min_date)

    if backfill_days and backfill_days > 0:
        dates = []
        for i in range(backfill_days):
            candidate = max_date - timedelta(days=i)
            if candidate < min_date:
                continue
            dates.append(candidate.isoformat())
        return dates
    return [max_date.isoformat()]


def run_ingestion(
    *,
    client=None,
    raw_writer: FirmsRawWriter | None = None,
    credentials: FirmsCredentials | None = None,
    secret_id=DEFAULT_SECRET_ID,
    backfill_days=0,
    ingest_date=None,
) -> dict:
    """Run one ingestion batch for every satellite.

    Returns a JSON-safe summary dict. A failure in one satellite is recorded
    and never aborts the others.
    """
    backfill_days = max(0, min(int(backfill_days), MAX_BACKFILL_DAYS))
    if ingest_date is None:
        ingest_date = get_ingest_date()

    if client is None:
        if credentials is None:
            credentials = load_credentials(secret_id=secret_id)
        client = FirmsClient(credentials)

    if raw_writer is None:
        raise ValueError("raw_writer is required")

    batch_id = generate_batch_id(RAW_SOURCE_SYSTEM)
    raw_batch_prefix = FirmsRawWriter.raw_batch_prefix(
        RAW_PREFIX, ingest_date, batch_id
    )

    per_satellite = []
    written_count = 0
    quarantined_count = 0
    error_count = 0

    for data_id in SATELLITES:
        outcome = _ingest_one_satellite(
            client=client,
            raw_writer=raw_writer,
            data_id=data_id,
            ingest_date=ingest_date,
            batch_id=batch_id,
            backfill_days=backfill_days,
        )
        per_satellite.append(outcome)
        written_count += outcome["written_count"]
        quarantined_count += outcome["quarantined_count"]
        error_count += outcome["error_count"]

    return {
        "batch_id": batch_id,
        "ingest_date": ingest_date,
        "raw_bucket": raw_writer.config.raw_bucket,
        "raw_batch_prefix": raw_batch_prefix,
        "backfill_days": backfill_days,
        "satellites": per_satellite,
        "written_count": written_count,
        "quarantined_count": quarantined_count,
        "error_count": error_count,
    }


def _ingest_one_satellite(
    *,
    client: FirmsClient,
    raw_writer: FirmsRawWriter,
    data_id: str,
    ingest_date: str,
    batch_id: str,
    backfill_days: int,
) -> dict:
    outcome: dict[str, Any] = {
        "data_id": data_id,
        "status": "ok",
        "min_date": None,
        "max_date": None,
        "target_dates": [],
        "skipped_dates": [],
        "written_count": 0,
        "quarantined_count": 0,
        "error_count": 0,
        "errors": [],
    }

    try:
        availability: Availability = client.get_data_availability(data_id)
    except FirmsError as exc:
        outcome["status"] = "error"
        outcome["error_count"] = 1
        outcome["errors"].append(str(exc))
        logger.error("Satellite %s availability failed: %s", data_id, exc)
        return outcome
    except Exception as exc:  # pragma: no cover - safety net, one satellite must not abort
        outcome["status"] = "error"
        outcome["error_count"] = 1
        outcome["errors"].append(f"unexpected: {exc}")
        logger.error("Satellite %s availability failed unexpectedly: %s", data_id, exc)
        return outcome

    outcome["min_date"] = availability.min_date.isoformat()
    outcome["max_date"] = availability.max_date.isoformat()

    today = datetime.now(UTC).date()
    lag = (today - availability.max_date).days
    if lag > LAG_WARN_DAYS:
        logger.warning(
            "Satellite %s lag is %d days (max_date %s)",
            data_id,
            lag,
            availability.max_date,
        )

    target_dates = select_target_dates(
        availability.max_date, availability.min_date, backfill_days
    )

    if backfill_days > 0:
        ideal = [
            (availability.max_date - timedelta(days=i)).isoformat()
            for i in range(backfill_days)
        ]
        out_of_window = [d for d in ideal if d not in target_dates]
        if out_of_window:
            logger.info(
                "Satellite %s: dates outside availability window skipped: %s",
                data_id,
                out_of_window,
            )
    outcome["target_dates"] = target_dates

    try:
        existing = raw_writer.existing_data_dates(data_id)
    except Exception as exc:
        # Without the raw listing we cannot tell which dates are already
        # stored, so a rerun could duplicate data. Record the error and make
        # no requests for this satellite instead of guessing.
        outcome["status"] = "error"
        outcome["error_count"] = 1
        outcome["errors"].append(f"failed to list existing raw dates: {exc}")
        logger.error(
            "Satellite %s: could not list existing raw dates, skipping satellite: %s",
            data_id,
            exc,
        )
        return outcome

    dates_to_fetch = [d for d in target_dates if d not in existing]
    skipped = [d for d in target_dates if d in existing]
    outcome["skipped_dates"] = skipped
    for data_date in skipped:
        logger.info(
            "Satellite %s date %s: already in raw, skipping", data_id, data_date
        )

    for data_date in dates_to_fetch:
        try:
            response: AreaResponse = client.fetch_area(
                data_id, day_range=DAY_RANGE, date=data_date
            )
        except FirmsPayloadError as exc:
            try:
                raw_writer.write_quarantine(
                    ingest_date=ingest_date,
                    batch_id=batch_id,
                    data_id=data_id,
                    data_date=data_date,
                    error_type="payload_error",
                    error_message=exc.reason,
                    raw_data={"sample": exc.sample},
                    response_metadata={"url": exc.url},
                )
            except Exception as write_exc:
                # A failed quarantine write must not abort the batch, but the
                # rejected payload is now lost, so it counts as an error.
                outcome["error_count"] += 1
                outcome["errors"].append(
                    f"{data_date}: quarantine write failed: {write_exc}"
                )
                logger.error(
                    "Satellite %s date %s: quarantine write failed: %s",
                    data_id,
                    data_date,
                    write_exc,
                )
                continue
            outcome["quarantined_count"] += 1
            logger.warning(
                "Satellite %s date %s: quarantined payload (%s)",
                data_id,
                data_date,
                exc.reason,
            )
            continue
        except FirmsHTTPError as exc:
            outcome["error_count"] += 1
            outcome["errors"].append(str(exc))
            logger.error("Satellite %s date %s: HTTP %s", data_id, data_date, exc.status_code)
            continue
        except FirmsError as exc:
            outcome["error_count"] += 1
            outcome["errors"].append(str(exc))
            logger.error("Satellite %s date %s: %s", data_id, data_date, exc)
            continue
        except Exception as exc:  # pragma: no cover - safety net
            outcome["error_count"] += 1
            outcome["errors"].append(f"unexpected: {exc}")
            logger.error("Satellite %s date %s: unexpected %s", data_id, data_date, exc)
            continue

        if response.row_count == HEADER_ONLY_ROW_COUNT:
            logger.info(
                "Satellite %s date %s: header only, no detections",
                data_id,
                data_date,
            )
            continue

        try:
            raw_writer.write_csv(
                ingest_date=ingest_date,
                batch_id=batch_id,
                data_id=data_id,
                data_date=data_date,
                body=response.body,
                row_count=response.row_count,
            )
        except Exception as write_exc:
            outcome["error_count"] += 1
            outcome["errors"].append(f"{data_date}: raw write failed: {write_exc}")
            logger.error(
                "Satellite %s date %s: raw write failed: %s",
                data_id,
                data_date,
                write_exc,
            )
            continue
        outcome["written_count"] += 1

    outcome["status"] = "error" if outcome["error_count"] else "ok"
    return outcome
