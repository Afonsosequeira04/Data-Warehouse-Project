"""FRED Economic Series ingestion DAG.

Tasks:
1. fetch_and_validate: Fetch observations from the FRED API, validate pages
   and rows, write raw NDJSON to S3 (one object per series) and quarantine
   rejected payloads.
2. copy_into_bronze: CREATE the Bronze table once and run one COPY INTO per
   series via the Databricks SQL Statement Execution API (ADR-001).
3. verify_bronze_load: Verify row/series counts and _batch_id in Bronze.

The api_key is read from the ``fred`` Airflow Variable and is never logged.
The raw path for each series is its own NDJSON object because the COPY INTO
statement writes the series_id literal (the NDJSON has no series_id field).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.configuration import conf
from airflow.sdk import DAG, Variable, task

# Import shared Databricks SQL utilities
from ingestion.databricks_sql import (
    execute_sql_batch,
    execute_statement,
    normalize_host,
    render_sql_template,
    split_sql_statements,
)

logger = logging.getLogger(__name__)

# Default DAG parameters (can be overridden at runtime)
DEFAULT_CATALOG = "dwh_dev"
DEFAULT_SCHEMA = "bronze"
DEFAULT_BASE_URL = "https://api.stlouisfed.org/fred"
DEFAULT_OBSERVATION_YEARS = 5
SOURCE_NAME = "fred_economic_series"
RAW_PREFIX = "api/fred_economic_series"
QUARANTINE_PREFIX = "quarantine/api/fred_economic_series"
# SQL file lives in ingestion/sql/ which is synced to dags/ingestion/sql/
SQL_FILE_PATH = "ingestion/sql/bronze_fred_economic_series.sql"


def _default_observation_start() -> str:
    """Return the default observation_start: today minus 5 years (ISO date)."""
    today = datetime.now(UTC).date()
    try:
        return today.replace(year=today.year - DEFAULT_OBSERVATION_YEARS).isoformat()
    except ValueError:
        # February 29 on a non-leap target year: fall back to a day-based offset.
        return (today - timedelta(days=365 * DEFAULT_OBSERVATION_YEARS)).isoformat()


def _parse_fred_verification_row(row: list) -> tuple[int, int, str, str, int]:
    """Parse the FRED verification row (Databricks returns all values as strings)."""
    if len(row) != 5:
        raise ValueError(f"Expected 5 columns, got {len(row)}: {row}")

    try:
        row_count = int(row[0])
        series_count = int(row[1])
        min_date = "" if row[2] is None else str(row[2])
        max_date = "" if row[3] is None else str(row[3])
        non_null_values = int(row[4]) if row[4] is not None else 0
    except (ValueError, TypeError) as e:
        raise ValueError(f"Failed to parse FRED verification row {row}: {e}")

    return row_count, series_count, min_date, max_date, non_null_values


with DAG(
    dag_id="ingest_fred",
    description="Ingest FRED Economic Series -> S3 raw -> Bronze Delta table",
    schedule=None,  # Triggered manually or by daily_pipeline
    start_date=datetime(2025, 1, 1, tzinfo=UTC),
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(hours=2),
    },
    params={
        "catalog": DEFAULT_CATALOG,
        "schema": DEFAULT_SCHEMA,
        "series_ids": None,  # None = use defaults from client config
        "observation_start": None,  # None = today minus DEFAULT_OBSERVATION_YEARS
        "observation_end": None,  # None = no upper bound
    },
    tags=["ingestion", "fred", "bronze"],
) as dag:

    @task
    def fetch_and_validate(**context) -> dict:
        """Fetch FRED data, validate pages/rows, write raw NDJSON to S3.

        Returns dict with batch metadata (including one raw path per series)
        for downstream tasks.
        """
        from ingestion.api.fred_client import (
            DEFAULT_SERIES,
            FredAPIError,
            FredClient,
            FredConfig,
        )
        from ingestion.api.fred_writer import (
            FredWriter,
            FredWriterConfig,
            generate_batch_id,
            get_ingest_date,
        )

        # Resolve parameters
        params = context.get("params", {})
        catalog = params.get("catalog", DEFAULT_CATALOG)
        schema = params.get("schema", DEFAULT_SCHEMA)

        # Get raw bucket from Airflow config (set via Terraform mwaa.raw_bucket)
        raw_bucket = conf.get("mwaa", "raw_bucket", fallback=None)
        if not raw_bucket:
            raise ValueError(
                "mwaa.raw_bucket not set in airflow_configuration_options. "
                "Add it in infra/terraform/aws/ephemeral/mwaa.tf"
            )

        # Get FRED API credentials from secret (never logged)
        fred_secret = Variable.get("fred", deserialize_json=True)
        if not isinstance(fred_secret, dict):
            raise TypeError("fred secret must be a JSON object")

        api_key = fred_secret.get("api_key")
        base_url = fred_secret.get("base_url") or DEFAULT_BASE_URL
        if not api_key:
            raise ValueError("fred secret must contain api_key")

        series_ids = tuple(params.get("series_ids") or DEFAULT_SERIES)
        observation_start = params.get("observation_start") or _default_observation_start()
        observation_end = params.get("observation_end")

        # Generate batch identifiers
        batch_id = generate_batch_id()
        ingest_date = get_ingest_date()

        # Initialize clients
        config = FredConfig(
            api_key=api_key,
            base_url=base_url,
            series_ids=series_ids,
            observation_start=observation_start,
            observation_end=observation_end,
        )
        writer_config = FredWriterConfig(
            raw_bucket=raw_bucket,
            raw_prefix=RAW_PREFIX,
            quarantine_prefix=QUARANTINE_PREFIX,
        )
        writer = FredWriter(writer_config)
        client = FredClient(config)

        # Track results
        series_files: dict[str, dict] = {}
        total_records = 0
        quarantined_pages = 0
        rejected_observations = 0
        errors: list[str] = []

        try:
            for series_id in series_ids:
                logger.info(f"Processing FRED series: {series_id}")
                accepted: list[dict] = []

                try:
                    for page in client.fetch_series(series_id):
                        if page.quarantine_reason is not None:
                            writer.write_quarantine(
                                ingest_date=ingest_date,
                                batch_id=batch_id,
                                series_id=series_id,
                                error_type="api_error",
                                error_message=page.quarantine_reason,
                                raw_data=page.quarantine_raw,
                                response_metadata={
                                    "request_url": page.request_url,
                                    "offset": page.offset,
                                },
                            )
                            quarantined_pages += 1
                            errors.append(
                                f"{series_id} offset {page.offset}: {page.quarantine_reason}"
                            )
                            logger.error(
                                f"Quarantined FRED page {series_id} offset {page.offset}: "
                                f"{page.quarantine_reason}"
                            )
                            continue

                        for rejection in page.rejections:
                            writer.write_quarantine(
                                ingest_date=ingest_date,
                                batch_id=batch_id,
                                series_id=series_id,
                                error_type="validation_error",
                                error_message=rejection.reason,
                                raw_data=rejection.observation,
                                response_metadata={"offset": page.offset},
                            )
                            rejected_observations += 1

                        accepted.extend(page.observations)
                except FredAPIError as e:
                    writer.write_quarantine(
                        ingest_date=ingest_date,
                        batch_id=batch_id,
                        series_id=series_id,
                        error_type="api_error",
                        error_message=str(e),
                    )
                    quarantined_pages += 1
                    errors.append(f"{series_id}: {e}")
                    logger.error(f"Quarantined FRED series {series_id}: {e}")
                    continue

                if not accepted:
                    errors.append(f"{series_id}: no observations fetched")
                    logger.warning(f"No observations fetched for FRED series {series_id}")
                    continue

                result = writer.write_series(
                    ingest_date=ingest_date,
                    batch_id=batch_id,
                    series_id=series_id,
                    observations=accepted,
                )
                series_files[series_id] = {
                    "key": result.key,
                    "record_count": result.record_count,
                }
                total_records += result.record_count or 0
                logger.info(
                    f"Wrote raw series: {result.key} ({result.record_count} records)"
                )
        finally:
            client.close()

        if not series_files:
            raise ValueError("No FRED series were successfully written to S3")

        # Build the per-series raw path for COPY INTO. The COPY INTO writes the
        # series_id literal, so each series must be loaded from its own object.
        series_raw_paths = {
            series_id: f"s3://{raw_bucket}/{info['key']}"
            for series_id, info in series_files.items()
        }

        result = {
            "batch_id": batch_id,
            "ingest_date": ingest_date,
            "raw_bucket": raw_bucket,
            "catalog": catalog,
            "schema": schema,
            "observation_start": observation_start,
            "observation_end": observation_end,
            "series_ids": list(series_ids),
            "series_files": series_files,
            "series_raw_paths": series_raw_paths,
            "series_count": len(series_files),
            "total_records": total_records,
            "quarantined_pages": quarantined_pages,
            "rejected_observations": rejected_observations,
            "errors": errors,
            "table_name": f"{catalog}.{schema}.{SOURCE_NAME}",
        }

        logger.info(f"Fetch complete: {json.dumps(result, indent=2, default=str)}")
        return result

    @task
    def copy_into_bronze(fetch_result: dict) -> dict:
        """Load Bronze: CREATE TABLE once, then one COPY INTO per series."""
        # Get Databricks connection from secret
        databricks_secret = Variable.get("databricks", deserialize_json=True)
        if not isinstance(databricks_secret, dict):
            raise TypeError("databricks secret must be a JSON object")

        host = databricks_secret.get("host")
        token = databricks_secret.get("token")
        warehouse_id = databricks_secret.get("warehouse_id")

        if not all([host, token, warehouse_id]):
            raise ValueError("databricks secret must contain host, token, and warehouse_id")

        series_raw_paths = fetch_result["series_raw_paths"]
        if not series_raw_paths:
            raise ValueError("No series raw paths to load")

        # Read SQL template (ingestion/sql/ is synced to dags/ingestion/sql/)
        sql_path = Path(__file__).parent / SQL_FILE_PATH
        if not sql_path.exists():
            raise FileNotFoundError(f"SQL file not found: {sql_path}")

        with open(sql_path) as f:
            sql_template = f.read()

        # The template holds CREATE TABLE and COPY INTO. COPY INTO references
        # ${series_id} and ${raw_path}, so render once per series; execute the
        # CREATE TABLE only on the first render.
        statements: list[str] = []
        for index, (series_id, series_raw_path) in enumerate(series_raw_paths.items()):
            rendered = render_sql_template(
                sql_template=sql_template,
                catalog=fetch_result["catalog"],
                schema=fetch_result["schema"],
                raw_path=series_raw_path,
                batch_id=fetch_result["batch_id"],
                batch_date=fetch_result["ingest_date"],
                extra_replacements={"${series_id}": series_id},
            )
            series_statements = split_sql_statements(rendered)
            if index == 0:
                statements.extend(series_statements)
            else:
                # Skip CREATE TABLE on subsequent renders; keep the COPY INTO.
                statements.append(series_statements[-1])

        logger.info(
            f"Executing {len(statements)} statements for batch {fetch_result['batch_id']} "
            f"across {len(series_raw_paths)} series"
        )

        results = execute_sql_batch(
            host=normalize_host(host),
            token=token,
            warehouse_id=warehouse_id,
            statements=statements,
            wait_timeout="50s",
        )

        for i, result in enumerate(results, 1):
            logger.info(f"Statement {i} completed: {result.get('statement_id')}")

        logger.info("All statements completed successfully")

        return {
            **fetch_result,
            "copy_into_status": "success",
            "statements_executed": len(statements),
        }

    @task
    def verify_bronze_load(copy_result: dict) -> dict:
        """Verify Bronze load: row/series counts and _batch_id match."""
        databricks_secret = Variable.get("databricks", deserialize_json=True)
        if not isinstance(databricks_secret, dict):
            raise TypeError("databricks secret must be a JSON object")

        host = databricks_secret.get("host")
        token = databricks_secret.get("token")
        warehouse_id = databricks_secret.get("warehouse_id")

        if not all([host, token, warehouse_id]):
            raise ValueError("databricks secret must contain host, token, and warehouse_id")

        table_name = copy_result["table_name"]
        batch_id = copy_result["batch_id"]
        expected_records = copy_result["total_records"]
        expected_series = copy_result["series_count"]

        # FRED-specific verification query
        verify_sql = f"""
            SELECT
                COUNT(*) as row_count,
                COUNT(DISTINCT series_id) as series_count,
                MIN(`date`) as min_date,
                MAX(`date`) as max_date,
                SUM(CASE WHEN value IS NOT NULL THEN 1 ELSE 0 END) as non_null_values
            FROM {table_name}
            WHERE _batch_id = '{batch_id}'
        """

        logger.info(f"Verifying FRED Bronze load for batch {batch_id}")

        result = execute_statement(
            host=normalize_host(host),
            token=token,
            warehouse_id=warehouse_id,
            statement=verify_sql,
            wait_timeout="50s",
            disposition="INLINE",
            format="JSON_ARRAY",
        )

        rows = result.get("result", {}).get("data_array", [])
        if not rows:
            raise RuntimeError("Verification query returned no rows")

        actual_count, series_count, min_date, max_date, non_null_values = (
            _parse_fred_verification_row(rows[0])
        )

        if actual_count == 0:
            raise ValueError("No rows loaded into FRED Bronze table")

        if series_count != expected_series:
            raise ValueError(
                f"Expected {expected_series} distinct series, found {series_count}"
            )

        # Allow tolerance for null values being filtered.
        if actual_count < expected_records * 0.5:
            raise ValueError(
                f"Row count mismatch: expected ~{expected_records}, got {actual_count}"
            )

        logger.info(
            f"Verification passed: {actual_count} rows, {series_count} series, "
            f"batch_id={batch_id}, date range={min_date}..{max_date}, "
            f"non-null values={non_null_values}"
        )

        return {
            **copy_result,
            "verification": {
                "row_count": actual_count,
                "series_count": series_count,
                "min_date": min_date,
                "max_date": max_date,
                "non_null_values": non_null_values,
                "status": "passed",
            },
        }

    # Task dependencies
    fetch_result = fetch_and_validate()
    copy_result = copy_into_bronze(fetch_result)
    verify_bronze_load(copy_result)
