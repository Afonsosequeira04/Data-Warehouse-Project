"""World Bank Indicators ingestion DAG.

Tasks:
1. fetch_and_validate: Fetch from World Bank API, validate, write raw JSON to S3
2. copy_into_bronze: Run COPY INTO via Databricks SQL Warehouse to load Bronze table
3. verify_bronze_load: Verify row count and _batch_id in Bronze table
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.configuration import conf
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.databricks.hooks.databricks import DatabricksHook
from airflow.sdk import DAG, Variable, task

logger = logging.getLogger(__name__)

# Default DAG parameters (can be overridden at runtime)
DEFAULT_CATALOG = "dwh_dev"
DEFAULT_SCHEMA = "bronze"
SOURCE_NAME = "world_bank_indicators"
RAW_PREFIX = "api/world_bank_indicators"
QUARANTINE_PREFIX = "quarantine/api/world_bank_indicators"
SQL_FILE_PATH = "ingestion/sql/bronze_world_bank_indicators.sql"

with DAG(
    dag_id="ingest_world_bank",
    description="Ingest World Bank Indicators -> S3 raw -> Bronze Delta table",
    schedule=None,  # Triggered manually or by daily_pipeline
    start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
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
        "indicators": None,  # None = use defaults from client config
        "date_range": None,  # None = use defaults
        "backfill": False,
    },
    tags=["ingestion", "world_bank", "bronze"],
) as dag:

    @task
    def fetch_and_validate(**context) -> dict:
        """Fetch World Bank data, validate responses, write raw JSON to S3.

        Returns dict with batch metadata for downstream tasks.
        """
        from ingestion.api.world_bank_client import WorldBankClient, WorldBankConfig, WorldBankAPIError
        from ingestion.api.s3_writer import S3Writer, S3WriterConfig, generate_batch_id, get_ingest_date

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

        # Generate batch identifiers
        batch_id = generate_batch_id()
        ingest_date = get_ingest_date()

        # Initialize clients
        config = WorldBankConfig()
        if params.get("indicators"):
            config = WorldBankConfig(indicators=tuple(params["indicators"]))
        if params.get("date_range"):
            config = WorldBankConfig(date_range=params["date_range"])

        s3_config = S3WriterConfig(
            raw_bucket=raw_bucket,
            raw_prefix=RAW_PREFIX,
            quarantine_prefix=QUARANTINE_PREFIX,
        )
        s3_writer = S3Writer(s3_config)
        client = WorldBankClient(config)

        # Track results
        total_pages_written = 0
        total_records = 0
        quarantined_pages = 0
        errors = []

        try:
            for indicator in config.indicators:
                logger.info(f"Processing indicator: {indicator}")

                for page, raw_data in client.fetch_raw_pages(indicator):
                    try:
                        # Validate by attempting to parse
                        parsed_count = 0
                        for item in raw_data:
                            obs = client._parse_observation(item, indicator)
                            if obs is not None:
                                parsed_count += 1

                        if parsed_count == 0 and raw_data:
                            # Data exists but nothing parsed - quarantine
                            s3_writer.write_quarantine(
                                ingest_date=ingest_date,
                                batch_id=batch_id,
                                indicator=indicator,
                                page=page,
                                error_type="parse_error",
                                error_message="All records in page failed to parse",
                                raw_data=raw_data,
                            )
                            quarantined_pages += 1
                            continue

                        # Write valid raw page to S3
                        result = s3_writer.write_raw_page(
                            ingest_date=ingest_date,
                            batch_id=batch_id,
                            indicator=indicator,
                            page=page,
                            data=raw_data,
                            metadata={"parsed_count": parsed_count},
                        )
                        total_pages_written += 1
                        total_records += parsed_count
                        logger.info(f"Wrote raw page: {result.key} ({parsed_count} records)")

                    except WorldBankAPIError as e:
                        # API-level errors (invalid schema, error payload) - quarantine
                        s3_writer.write_quarantine(
                            ingest_date=ingest_date,
                            batch_id=batch_id,
                            indicator=indicator,
                            page=page,
                            error_type="api_error",
                            error_message=str(e),
                            raw_data=raw_data if "raw_data" in locals() else None,
                        )
                        quarantined_pages += 1
                        errors.append(f"{indicator} page {page}: {e}")
                        logger.error(f"Quarantined {indicator} page {page}: {e}")

                    except Exception as e:
                        # Unexpected errors - quarantine and re-raise
                        s3_writer.write_quarantine(
                            ingest_date=ingest_date,
                            batch_id=batch_id,
                            indicator=indicator,
                            page=page,
                            error_type="unexpected_error",
                            error_message=str(e),
                            raw_data=raw_data if "raw_data" in locals() else None,
                        )
                        quarantined_pages += 1
                        raise

        finally:
            client.close()

        if total_pages_written == 0:
            raise ValueError("No raw pages were successfully written to S3")

        # Build raw path for COPY INTO
        raw_path = f"s3://{raw_bucket}/{RAW_PREFIX}/ingest_date={ingest_date}/{batch_id}/"

        result = {
            "batch_id": batch_id,
            "ingest_date": ingest_date,
            "raw_bucket": raw_bucket,
            "raw_path": raw_path,
            "catalog": catalog,
            "schema": schema,
            "total_pages_written": total_pages_written,
            "total_records": total_records,
            "quarantined_pages": quarantined_pages,
            "errors": errors,
            "table_name": f"{catalog}.{schema}.{SOURCE_NAME}",
        }

        logger.info(f"Fetch complete: {json.dumps(result, indent=2)}")
        return result

    @task
    def copy_into_bronze(fetch_result: dict) -> dict:
        """Run COPY INTO via Databricks SQL Warehouse to load Bronze table."""
        # Get Databricks connection from secret
        databricks_secret = Variable.get("databricks", deserialize_json=True)
        if not isinstance(databricks_secret, dict):
            raise ValueError("databricks secret must be a JSON object")

        host = databricks_secret.get("host")
        token = databricks_secret.get("token")
        warehouse_id = databricks_secret.get("warehouse_id")

        if not all([host, token, warehouse_id]):
            raise ValueError("databricks secret must contain host, token, and warehouse_id")

        # Read SQL template
        sql_path = Path(__file__).parent.parent / SQL_FILE_PATH
        if not sql_path.exists():
            raise FileNotFoundError(f"SQL file not found: {sql_path}")

        with open(sql_path) as f:
            sql_template = f.read()

        # Render SQL with batch parameters
        sql = sql_template.replace("${catalog}", fetch_result["catalog"]) \
                         .replace("${schema}", fetch_result["schema"]) \
                         .replace("${raw_path}", fetch_result["raw_path"]) \
                         .replace("${batch_id}", fetch_result["batch_id"]) \
                         .replace("${batch_date}", fetch_result["ingest_date"])

        logger.info(f"Executing COPY INTO for batch {fetch_result['batch_id']}")

        # Execute via Databricks SQL Warehouse
        hook = DatabricksHook(databricks_conn_id="databricks_default")
        # Override connection with secret values
        hook.host = host
        hook.token = token

        # Submit SQL statement
        response = hook.run_sql(
            sql=sql,
            warehouse_id=warehouse_id,
            wait_timeout=300,
        )

        if response.get("status", {}).get("state") != "SUCCEEDED":
            error_msg = response.get("status", {}).get("error", {}).get("message", "Unknown error")
            raise RuntimeError(f"COPY INTO failed: {error_msg}")

        logger.info("COPY INTO completed successfully")

        return {
            **fetch_result,
            "copy_into_status": "success",
            "statement_id": response.get("statement_id"),
        }

    @task
    def verify_bronze_load(copy_result: dict) -> dict:
        """Verify Bronze table load: row count and _batch_id match."""
        databricks_secret = Variable.get("databricks", deserialize_json=True)
        host = databricks_secret.get("host")
        token = databricks_secret.get("token")
        warehouse_id = databricks_secret.get("warehouse_id")

        hook = DatabricksHook(databricks_conn_id="databricks_default")
        hook.host = host
        hook.token = token

        table_name = copy_result["table_name"]
        batch_id = copy_result["batch_id"]
        expected_records = copy_result["total_records"]

        # Verification query
        verify_sql = f"""
            SELECT
                COUNT(*) as row_count,
                COUNT(DISTINCT _batch_id) as batch_count,
                MIN(year) as min_year,
                MAX(year) as max_year,
                SUM(CASE WHEN value IS NOT NULL THEN 1 ELSE 0 END) as non_null_values
            FROM {table_name}
            WHERE _batch_id = '{batch_id}'
        """

        logger.info(f"Verifying Bronze load for batch {batch_id}")
        response = hook.run_sql(
            sql=verify_sql,
            warehouse_id=warehouse_id,
            wait_timeout=60,
        )

        if response.get("status", {}).get("state") != "SUCCEEDED":
            error_msg = response.get("status", {}).get("error", {}).get("message", "Unknown error")
            raise RuntimeError(f"Verification query failed: {error_msg}")

        # Parse result
        result_data = response.get("result", {})
        rows = result_data.get("data_array", [])
        if not rows:
            raise RuntimeError("Verification query returned no rows")

        row = rows[0]
        actual_count = row[0]
        batch_count = row[1]
        min_year = row[2]
        max_year = row[3]
        non_null_values = row[4]

        # Validate
        if batch_count != 1:
            raise ValueError(f"Expected 1 distinct _batch_id, found {batch_count}")

        if actual_count == 0:
            raise ValueError("No rows loaded into Bronze table")

        # Allow some tolerance for null values being filtered
        if actual_count < expected_records * 0.5:
            raise ValueError(
                f"Row count mismatch: expected ~{expected_records}, got {actual_count}"
            )

        logger.info(
            f"Verification passed: {actual_count} rows, batch_id={batch_id}, "
            f"year range={min_year}-{max_year}, non-null values={non_null_values}"
        )

        return {
            **copy_result,
            "verification": {
                "row_count": actual_count,
                "min_year": min_year,
                "max_year": max_year,
                "non_null_values": non_null_values,
                "status": "passed",
            },
        }

    # Task dependencies
    fetch_result = fetch_and_validate()
    copy_result = copy_into_bronze(fetch_result)
    verify_bronze_load(copy_result)