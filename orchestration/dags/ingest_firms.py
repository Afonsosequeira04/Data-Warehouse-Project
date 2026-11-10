"""NASA FIRMS active fire detections ingestion DAG.

Tasks:
1. fetch_and_validate: read each satellite's data_availability, fetch the
   target date(s), write valid CSVs byte for byte to S3 raw and quarantine
   structurally invalid payloads (ingestion/firms).
2. copy_into_bronze: CREATE the Bronze table once and run one idempotent
   COPY INTO for the whole batch via the Databricks SQL Statement Execution
   API (ADR-001). Skipped when the batch wrote nothing and rejected nothing.
3. verify_bronze_load: fail when any satellite errored or paid a quarantined
   payload, otherwise check the row count loaded for this batch. A changed
   NASA header must never end green.

The API key lives in Secrets Manager (``cloud-data-platform/firms``) and is
never logged.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.configuration import conf
from airflow.sdk import DAG, Variable, get_current_context, task
from airflow.sdk.exceptions import AirflowSkipException

from ingestion.databricks_sql import (
    execute_sql_batch,
    execute_statement,
    normalize_host,
    render_sql_template,
    split_sql_statements,
)

logger = logging.getLogger(__name__)

DEFAULT_CATALOG = "dwh_dev"
DEFAULT_SCHEMA = "bronze"
SOURCE_NAME = "nasa_firms_fires"
RAW_PREFIX = "api/nasa_firms_fires"
QUARANTINE_PREFIX = "quarantine/stream/nasa_firms_fires"
# The SQL file lives in ingestion/sql/, synced to dags/ingestion/sql/ in MWAA.
SQL_FILE_PATH = "ingestion/sql/bronze_nasa_firms_fires.sql"


def _dag_params() -> dict:
    """Return the DAG run params (empty dict when none were supplied)."""
    return get_current_context().get("params") or {}


def _raw_bucket() -> str:
    """Raw bucket name injected by the ephemeral Terraform stack."""
    raw_bucket = conf.get("mwaa", "raw_bucket", fallback=None)
    if not raw_bucket:
        raise ValueError(
            "mwaa.raw_bucket not set in airflow_configuration_options. "
            "Add it in infra/terraform/aws/ephemeral/mwaa.tf"
        )
    return raw_bucket


def _databricks_config() -> dict:
    """Databricks host, token and warehouse id from Secrets Manager."""
    config = Variable.get("databricks", deserialize_json=True)
    if not isinstance(config, dict):
        raise TypeError("databricks secret must be a JSON object")
    if not all(config.get(key) for key in ("host", "token", "warehouse_id")):
        raise ValueError("databricks secret must contain host, token, and warehouse_id")
    return config


def _sql_template_path() -> Path:
    """Locate the Bronze SQL template in the repo and in the MWAA DAG bucket."""
    candidates = (
        Path(__file__).parent / SQL_FILE_PATH,
        Path(__file__).parents[2] / SQL_FILE_PATH,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"SQL file not found: {SQL_FILE_PATH}")


def _raw_path_for_batch(summary: dict) -> str:
    """s3 path of the LOADED batch prefix, with the CSV glob COPY INTO needs."""
    return (
        f"s3://{summary['raw_bucket']}/{summary['raw_batch_prefix']}/*.csv"
    )


with DAG(
    dag_id="ingest_firms",
    description="Ingest NASA FIRMS fires -> S3 raw -> Bronze Delta table",
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(hours=1),
    },
    params={
        "catalog": DEFAULT_CATALOG,
        "schema": DEFAULT_SCHEMA,
        # 0 = daily run (only each satellite's max_date); max 7.
        "backfill_days": 0,
    },
    tags=["ingestion", "nasa-firms", "bronze"],
) as dag:

    @task
    def fetch_and_validate() -> dict:
        """Fetch every satellite and write raw CSVs plus quarantine objects."""
        from ingestion.core.s3_writer import RawS3WriterConfig
        from ingestion.firms.ingest import run_ingestion
        from ingestion.firms.raw_writer import RAW_SOURCE_SYSTEM, FirmsRawWriter

        params = _dag_params()
        catalog = params.get("catalog", DEFAULT_CATALOG)
        schema = params.get("schema", DEFAULT_SCHEMA)
        backfill_days = int(params.get("backfill_days") or 0)

        raw_bucket = _raw_bucket()
        raw_writer = FirmsRawWriter(
            RawS3WriterConfig(
                raw_bucket=raw_bucket,
                raw_prefix=RAW_PREFIX,
                quarantine_prefix=QUARANTINE_PREFIX,
                source_system=RAW_SOURCE_SYSTEM,
            )
        )

        summary = run_ingestion(
            raw_writer=raw_writer, backfill_days=backfill_days
        )
        summary["catalog"] = catalog
        summary["schema"] = schema
        summary["table_name"] = f"{catalog}.{schema}.{SOURCE_NAME}"

        logger.info(
            "FIRMS ingest finished: batch=%s written=%s quarantined=%s errors=%s",
            summary["batch_id"],
            summary["written_count"],
            summary["quarantined_count"],
            summary["error_count"],
        )
        logger.debug("FIRMS batch summary: %s", json.dumps(summary, default=str))
        return summary

    @task
    def copy_into_bronze(fetch_result: dict) -> dict:
        """Load the batch with one idempotent COPY INTO (ADR-001)."""
        written = fetch_result.get("written_count", 0)
        errors = fetch_result.get("error_count", 0)
        quarantined = fetch_result.get("quarantined_count", 0)

        if written == 0 and errors == 0 and quarantined == 0:
            raise AirflowSkipException(
                "No new FIRMS data for batch "
                f"{fetch_result['batch_id']}: nothing to load"
            )

        databricks = _databricks_config()
        sql_template = _sql_template_path().read_text(encoding="utf-8")
        raw_path = _raw_path_for_batch(fetch_result)

        rendered = render_sql_template(
            sql_template,
            catalog=fetch_result["catalog"],
            schema=fetch_result["schema"],
            raw_path=raw_path,
            batch_id=fetch_result["batch_id"],
            batch_date=fetch_result["ingest_date"],
        )
        statements = split_sql_statements(rendered)

        logger.info(
            "Loading %s raw object(s) for batch %s with %d statement(s)",
            written,
            fetch_result["batch_id"],
            len(statements),
        )
        results = execute_sql_batch(
            host=normalize_host(databricks["host"]),
            token=databricks["token"],
            warehouse_id=databricks["warehouse_id"],
            statements=statements,
            wait_timeout="50s",
        )
        for index, result in enumerate(results, 1):
            logger.info("Statement %d completed: %s", index, result.get("statement_id"))

        return {
            **fetch_result,
            "raw_path": raw_path,
            "copy_into_status": "success",
            "statements_executed": len(statements),
        }

    @task
    def verify_bronze_load(copy_result: dict) -> dict:
        """Fail on any rejected payload, else check the loaded row count."""
        written = copy_result.get("written_count", 0)
        errors = copy_result.get("error_count", 0)
        quarantined = copy_result.get("quarantined_count", 0)

        if written == 0 and errors == 0 and quarantined == 0:
            raise AirflowSkipException(
                f"No new FIRMS data for batch {copy_result['batch_id']}"
            )

        if errors > 0 or quarantined > 0:
            bad = [
                {
                    "data_id": satellite.get("data_id"),
                    "status": satellite.get("status"),
                    "quarantined_count": satellite.get("quarantined_count"),
                    "errors": satellite.get("errors"),
                }
                for satellite in copy_result.get("satellites", [])
                if satellite.get("status") == "error"
                or satellite.get("quarantined_count")
            ]
            raise ValueError(
                f"FIRMS batch {copy_result['batch_id']} is not clean: "
                f"{errors} error(s), {quarantined} quarantined payload(s). "
                f"{written} object(s) were loaded but the run must be reviewed: {bad}"
            )

        databricks = _databricks_config()
        table_name = copy_result["table_name"]
        batch_id = copy_result["batch_id"]

        verify_sql = f"""
            SELECT
                COUNT(*) AS row_count,
                COUNT(DISTINCT data_id) AS satellite_count
            FROM {table_name}
            WHERE _batch_id = '{batch_id}'
        """

        logger.info("Verifying Bronze load for batch %s", batch_id)
        result = execute_statement(
            host=normalize_host(databricks["host"]),
            token=databricks["token"],
            warehouse_id=databricks["warehouse_id"],
            statement=verify_sql,
            wait_timeout="50s",
            disposition="INLINE",
            format="JSON_ARRAY",
        )

        rows = result.get("result", {}).get("data_array", [])
        if not rows:
            raise RuntimeError("Verification query returned no rows")

        row_count = int(rows[0][0])
        satellite_count = int(rows[0][1]) if rows[0][1] is not None else 0

        if row_count == 0:
            raise ValueError(f"No rows loaded into Bronze for batch {batch_id}")
        if row_count < written:
            raise ValueError(
                f"Row count mismatch for batch {batch_id}: "
                f"{row_count} rows for {written} raw object(s)"
            )

        logger.info(
            "Verification passed: %d rows from %d satellite(s) for batch %s",
            row_count,
            satellite_count,
            batch_id,
        )
        return {
            **copy_result,
            "verification": {
                "row_count": row_count,
                "satellite_count": satellite_count,
                "written_count": written,
                "status": "passed",
            },
        }

    fetch_result = fetch_and_validate()
    copy_result = copy_into_bronze(fetch_result)
    verify_bronze_load(copy_result)
