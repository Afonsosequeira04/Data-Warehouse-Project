"""Task-level tests for the ingest_firms DAG.

The DAG runs without MWAA: the file is executed like Airflow's DagBag does and
the task callables are called directly. No network, no Databricks, no S3.
"""

from __future__ import annotations

import pytest
from airflow.sdk.exceptions import AirflowSkipException

DAG_ID = "ingest_firms"
BATCH_ID = "nasa_firms_fires_20261108T060000Z_deadbeefcafe"
INGEST_DATE = "2026-11-08"
RAW_BUCKET = "test-raw-bucket"
RAW_PREFIX = "api/nasa_firms_fires"
TABLE_NAME = "dwh_dev.bronze.nasa_firms_fires"


def _load_dag_module() -> dict:
    """Exec the DAG file and return its namespace (like test_dag_import)."""
    from pathlib import Path

    dag_file = (
        Path(__file__).parent.parent / "orchestration" / "dags" / "ingest_firms.py"
    )
    namespace = {"__file__": str(dag_file)}
    with open(dag_file) as handle:
        code = compile(handle.read(), str(dag_file), "exec")
        exec(code, namespace)
    return namespace


@pytest.fixture
def dag_module() -> dict:
    return _load_dag_module()


def _callable(dag_module: dict, task_id: str):
    return dag_module["dag"].task_dict[task_id].python_callable


def _summary(**overrides) -> dict:
    summary = {
        "batch_id": BATCH_ID,
        "ingest_date": INGEST_DATE,
        "raw_bucket": RAW_BUCKET,
        "raw_batch_prefix": f"{RAW_PREFIX}/ingest_date={INGEST_DATE}/{BATCH_ID}",
        "backfill_days": 0,
        "catalog": "dwh_dev",
        "schema": "bronze",
        "table_name": TABLE_NAME,
        "satellites": [
            {
                "data_id": "VIIRS_NOAA20_NRT",
                "status": "ok",
                "written_count": 1,
                "quarantined_count": 0,
                "errors": [],
            }
        ],
        "written_count": 1,
        "quarantined_count": 0,
        "error_count": 0,
    }
    summary.update(overrides)
    return summary


def _databricks() -> dict:
    return {
        "host": "https://dbc-test.cloud.databricks.com/",
        "token": "dapi_test_token",
        "warehouse_id": "warehouse_123",
    }


class TestDagStructure:
    def test_dag_id_schedule_and_tasks(self, dag_module):
        dag = dag_module["dag"]

        assert dag.dag_id == DAG_ID
        assert dag.schedule == "0 6 * * *"
        assert dag.catchup is False
        assert {task.task_id for task in dag.tasks} == {
            "fetch_and_validate",
            "copy_into_bronze",
            "verify_bronze_load",
        }

    def test_task_dependencies_are_linear(self, dag_module):
        tasks = dag_module["dag"].task_dict

        assert tasks["fetch_and_validate"].downstream_task_ids == {"copy_into_bronze"}
        assert tasks["copy_into_bronze"].downstream_task_ids == {"verify_bronze_load"}

    def test_default_params(self, dag_module):
        params = dag_module["dag"].params

        assert params["catalog"] == "dwh_dev"
        assert params["schema"] == "bronze"
        assert params["backfill_days"] == 0


class TestFetchAndValidate:
    def test_runs_ingestion_and_returns_summary(self, dag_module, monkeypatch):
        captured = {}

        def fake_run_ingestion(*, raw_writer, backfill_days):
            captured["writer"] = raw_writer
            captured["backfill_days"] = backfill_days
            return _summary()

        monkeypatch.setitem(
            dag_module,
            "_dag_params",
            lambda: {"catalog": "dwh_dev", "schema": "bronze", "backfill_days": 3},
        )
        monkeypatch.setitem(dag_module, "_raw_bucket", lambda: RAW_BUCKET)
        import ingestion.firms.ingest as ingest_module

        monkeypatch.setattr(ingest_module, "run_ingestion", fake_run_ingestion)

        result = _callable(dag_module, "fetch_and_validate")()

        config = captured["writer"].config
        assert config.raw_bucket == RAW_BUCKET
        assert config.raw_prefix == RAW_PREFIX
        assert config.quarantine_prefix == "quarantine/stream/nasa_firms_fires"
        assert config.source_system == "nasa_firms_fires"
        assert captured["backfill_days"] == 3
        assert result["table_name"] == TABLE_NAME
        assert result["catalog"] == "dwh_dev"


class TestCopyIntoBronze:
    def test_renders_batch_glob_and_executes_both_statements(
        self, dag_module, monkeypatch
    ):
        captured = {}

        def fake_execute(**kwargs):
            captured.update(kwargs)
            return [{"statement_id": "stmt_1"}, {"statement_id": "stmt_2"}]

        monkeypatch.setitem(dag_module, "_databricks_config", _databricks)
        monkeypatch.setitem(dag_module, "execute_sql_batch", fake_execute)

        result = _callable(dag_module, "copy_into_bronze")(_summary())

        statements = captured["statements"]
        assert len(statements) == 2
        assert f"CREATE TABLE IF NOT EXISTS {TABLE_NAME}" in statements[0]
        assert f"COPY INTO {TABLE_NAME}" in statements[1]
        assert (
            f"s3://{RAW_BUCKET}/{RAW_PREFIX}/ingest_date={INGEST_DATE}/{BATCH_ID}/*.csv"
            in statements[1]
        )
        assert BATCH_ID in statements[1]
        assert INGEST_DATE in statements[1]
        assert "${" not in statements[1]
        assert captured["host"] == "https://dbc-test.cloud.databricks.com"
        assert result["copy_into_status"] == "success"
        assert result["statements_executed"] == 2
        assert result["raw_path"].endswith("/*.csv")

    def test_skips_when_nothing_written_or_rejected(self, dag_module, monkeypatch):
        def fail_execute(**kwargs):  # pragma: no cover - must not be called
            raise AssertionError("Databricks must not be called when skipping")

        monkeypatch.setitem(dag_module, "_databricks_config", _databricks)
        monkeypatch.setitem(dag_module, "execute_sql_batch", fail_execute)

        summary = _summary(written_count=0, satellites=[])

        with pytest.raises(AirflowSkipException):
            _callable(dag_module, "copy_into_bronze")(summary)

    def test_still_loads_good_data_when_a_satellite_failed(
        self, dag_module, monkeypatch
    ):
        captured = {}

        def fake_execute(**kwargs):
            captured.update(kwargs)
            return [{"statement_id": "stmt_1"}, {"statement_id": "stmt_2"}]

        monkeypatch.setitem(dag_module, "_databricks_config", _databricks)
        monkeypatch.setitem(dag_module, "execute_sql_batch", fake_execute)

        summary = _summary(error_count=1, quarantined_count=1)

        result = _callable(dag_module, "copy_into_bronze")(summary)

        assert captured["statements"]
        assert result["copy_into_status"] == "success"

    def test_missing_sql_template_fails_loudly(self, dag_module, monkeypatch):
        monkeypatch.setitem(dag_module, "_databricks_config", _databricks)

        def missing():
            raise FileNotFoundError("SQL file not found")

        monkeypatch.setitem(dag_module, "_sql_template_path", missing)

        with pytest.raises(FileNotFoundError):
            _callable(dag_module, "copy_into_bronze")(_summary())


class TestVerifyBronzeLoad:
    def test_passes_and_reports_row_count(self, dag_module, monkeypatch):
        captured = {}

        def fake_execute_statement(**kwargs):
            captured.update(kwargs)
            return {"result": {"data_array": [["10", "3"]]}}

        monkeypatch.setitem(dag_module, "_databricks_config", _databricks)
        monkeypatch.setitem(dag_module, "execute_statement", fake_execute_statement)

        result = _callable(dag_module, "verify_bronze_load")(
            {**_summary(), "written_count": 3}
        )

        assert result["verification"] == {
            "row_count": 10,
            "satellite_count": 3,
            "written_count": 3,
            "status": "passed",
        }
        assert f"FROM {TABLE_NAME}" in captured["statement"]
        assert BATCH_ID in captured["statement"]

    def test_skips_when_nothing_written_or_rejected(self, dag_module, monkeypatch):
        monkeypatch.setitem(dag_module, "_databricks_config", _databricks)

        with pytest.raises(AirflowSkipException):
            _callable(dag_module, "verify_bronze_load")(
                _summary(written_count=0, satellites=[])
            )

    def test_fails_when_a_satellite_errored(self, dag_module, monkeypatch):
        def fail_execute_statement(**kwargs):  # pragma: no cover - must not run
            raise AssertionError("Verification must fail before querying")

        monkeypatch.setitem(dag_module, "_databricks_config", _databricks)
        monkeypatch.setitem(
            dag_module, "execute_statement", fail_execute_statement
        )

        summary = _summary(
            error_count=1,
            satellites=[
                {
                    "data_id": "VIIRS_SNPP_NRT",
                    "status": "error",
                    "written_count": 0,
                    "quarantined_count": 0,
                    "errors": ["HTTP 400"],
                }
            ],
        )

        with pytest.raises(ValueError, match="is not clean"):
            _callable(dag_module, "verify_bronze_load")(summary)

    def test_fails_when_a_payload_was_quarantined(self, dag_module, monkeypatch):
        monkeypatch.setitem(dag_module, "_databricks_config", _databricks)

        summary = _summary(
            quarantined_count=1,
            satellites=[
                {
                    "data_id": "VIIRS_NOAA20_NRT",
                    "status": "ok",
                    "written_count": 1,
                    "quarantined_count": 1,
                    "errors": [],
                }
            ],
        )

        with pytest.raises(ValueError, match="is not clean"):
            _callable(dag_module, "verify_bronze_load")(summary)

    @pytest.mark.parametrize("data_array", [[], [["0", "0"]], [["1", "1"]]])
    def test_fails_when_loaded_rows_do_not_match(
        self, dag_module, monkeypatch, data_array
    ):
        def fake_execute_statement(**kwargs):
            return {"result": {"data_array": data_array}}

        monkeypatch.setitem(dag_module, "_databricks_config", _databricks)
        monkeypatch.setitem(dag_module, "execute_statement", fake_execute_statement)

        with pytest.raises((RuntimeError, ValueError)):
            _callable(dag_module, "verify_bronze_load")(
                {**_summary(), "written_count": 3}
            )
