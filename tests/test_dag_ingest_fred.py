"""Task-level tests for the ingest_fred DAG (fetch, Bronze load, verification).

The DAG is loaded from its real file with ``exec`` so the tests exercise the
actual task callables rather than a re-implementation. HTTP is mocked with
``responses``; the FRED client, the S3 writer and the Airflow config/Variables
are patched so no external service is contacted.
"""

from __future__ import annotations

# S102: exec is intentional for loading the DAG from its file
# ruff: noqa: S102
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import mock_open, patch

import pytest
import responses


def _load_fred_dag_namespace() -> dict:
    """Load the real ingest_fred DAG file into a namespace."""
    repo_root = Path(__file__).parent.parent
    dag_file = repo_root / "orchestration" / "dags" / "ingest_fred.py"
    namespace = {"__file__": str(dag_file)}
    with open(dag_file) as f:
        code = compile(f.read(), str(dag_file), "exec")
        exec(code, namespace)
    return namespace


def _load_fred_dag():
    """Load the ingest_fred DAG and return the dag object."""
    return _load_fred_dag_namespace()["dag"]


class _FakeFredWriter:
    """Minimal stand-in for FredWriter that records calls in memory."""

    instances: ClassVar[list] = []

    def __init__(self, config, s3_client=None):
        self.config = config
        self.written: list = []
        self.quarantined: list = []
        _FakeFredWriter.instances.append(self)

    def write_series(self, *, ingest_date, batch_id, series_id, observations):
        key = (
            f"{self.config.raw_prefix}/ingest_date={ingest_date}/"
            f"{batch_id}/{series_id}.ndjson"
        )
        self.written.append({"series_id": series_id, "observations": list(observations)})
        return SimpleNamespace(key=key, record_count=len(observations))

    def write_quarantine(self, **kwargs):
        self.quarantined.append(kwargs)
        return SimpleNamespace(key="quarantine")


class _FakeFredClient:
    """Minimal stand-in for FredClient driven by a pages-per-series mapping."""

    pages_by_series: ClassVar[dict] = {}
    instances: ClassVar[list] = []

    def __init__(self, config):
        self.config = config
        self.closed = False
        _FakeFredClient.instances.append(self)

    def fetch_series(self, series_id):
        return iter(self.pages_by_series.get(series_id, []))

    def close(self):
        self.closed = True


def _make_page(
    observations,
    *,
    rejections=(),
    quarantine_reason=None,
    offset=0,
    request_url="https://api.stlouisfed.org/fred/series/observations",
):
    """Build a page object shaped like ingestion.api.fred_client.FredPage."""
    return SimpleNamespace(
        series_id=None,
        offset=offset,
        count=len(observations),
        observations=list(observations),
        rejections=list(rejections),
        quarantine_reason=quarantine_reason,
        quarantine_raw={"error": quarantine_reason} if quarantine_reason else None,
        request_url=request_url,
    )


def _observation(day: str, value: str = "1.0") -> dict:
    return {
        "date": day,
        "value": value,
        "realtime_start": day,
        "realtime_end": day,
    }


def _make_fetch_result(batch_id: str = "fred_test_batch") -> dict:
    """Create a standard FRED fetch_result dict for copy/verify testing."""
    series_ids = ["CPIAUCSL", "UNRATE"]
    series_files = {
        series_id: {
            "key": (
                f"api/fred_economic_series/ingest_date=2025-01-15/"
                f"{batch_id}/{series_id}.ndjson"
            ),
            "record_count": 10 if series_id == "CPIAUCSL" else 8,
        }
        for series_id in series_ids
    }
    series_raw_paths = {
        series_id: f"s3://test-bucket/{info['key']}"
        for series_id, info in series_files.items()
    }
    return {
        "batch_id": batch_id,
        "ingest_date": "2025-01-15",
        "raw_bucket": "test-bucket",
        "catalog": "dwh_dev",
        "schema": "bronze",
        "observation_start": "2020-01-01",
        "observation_end": None,
        "series_ids": series_ids,
        "series_files": series_files,
        "series_raw_paths": series_raw_paths,
        "series_count": len(series_ids),
        "total_records": 18,
        "quarantined_pages": 0,
        "rejected_observations": 0,
        "errors": [],
        "table_name": "dwh_dev.bronze.fred_economic_series",
    }


def _make_copy_result(fetch_result: dict) -> dict:
    """Create a copy_result dict for verify_bronze_load testing."""
    return {
        **fetch_result,
        "copy_into_status": "success",
        "statements_executed": 3,
    }


# --------------------------------------------------------------------------- #
# fetch_and_validate
# --------------------------------------------------------------------------- #


def test_fetch_and_validate_writes_one_object_per_series():
    """fetch_and_validate writes one NDJSON object per series and returns paths."""
    dag = _load_fred_dag()
    fetch_fn = dag.task_dict["fetch_and_validate"].python_callable

    _FakeFredClient.pages_by_series = {
        "CPIAUCSL": [_make_page([_observation("2024-01-01"), _observation("2024-02-01")])],
        "UNRATE": [_make_page([_observation("2024-01-01")])],
    }

    with patch("airflow.sdk.Variable.get") as mock_var, \
         patch("airflow.configuration.conf.get", return_value="test-bucket"), \
         patch("ingestion.api.fred_writer.FredWriter", _FakeFredWriter), \
         patch("ingestion.api.fred_writer.generate_batch_id", return_value="fred_test_batch"), \
         patch("ingestion.api.fred_writer.get_ingest_date", return_value="2025-01-15"), \
         patch("ingestion.api.fred_client.FredClient", _FakeFredClient):
        mock_var.return_value = {"api_key": "test_key"}

        result = fetch_fn(params={"series_ids": ["CPIAUCSL", "UNRATE"]})

    assert result["batch_id"] == "fred_test_batch"
    assert result["ingest_date"] == "2025-01-15"
    assert result["raw_bucket"] == "test-bucket"
    assert result["series_count"] == 2
    assert result["total_records"] == 3
    assert set(result["series_raw_paths"]) == {"CPIAUCSL", "UNRATE"}
    assert result["series_raw_paths"]["CPIAUCSL"].endswith("/CPIAUCSL.ndjson")
    assert result["series_raw_paths"]["UNRATE"].endswith("/UNRATE.ndjson")

    writer = _FakeFredWriter.instances[-1]
    assert [w["series_id"] for w in writer.written] == ["CPIAUCSL", "UNRATE"]
    assert _FakeFredClient.instances[-1].closed is True


def test_fetch_and_validate_quarantines_bad_pages_and_rejections():
    """Quarantined pages and rejected rows are recorded without losing the series."""
    dag = _load_fred_dag()
    fetch_fn = dag.task_dict["fetch_and_validate"].python_callable

    rejection = SimpleNamespace(reason="missing value", observation={"date": "2024-03-01"})
    _FakeFredClient.pages_by_series = {
        "CPIAUCSL": [
            _make_page([_observation("2024-01-01")]),
            _make_page([], quarantine_reason="invalid JSON payload"),
        ],
        "UNRATE": [
            _make_page([_observation("2024-01-01")], rejections=[rejection]),
        ],
    }

    with patch("airflow.sdk.Variable.get") as mock_var, \
         patch("airflow.configuration.conf.get", return_value="test-bucket"), \
         patch("ingestion.api.fred_writer.FredWriter", _FakeFredWriter), \
         patch("ingestion.api.fred_writer.generate_batch_id", return_value="fred_test_batch"), \
         patch("ingestion.api.fred_writer.get_ingest_date", return_value="2025-01-15"), \
         patch("ingestion.api.fred_client.FredClient", _FakeFredClient):
        mock_var.return_value = {"api_key": "test_key"}

        result = fetch_fn(params={"series_ids": ["CPIAUCSL", "UNRATE"]})

    assert result["series_count"] == 2
    assert result["total_records"] == 2
    assert result["quarantined_pages"] == 1
    assert result["rejected_observations"] == 1
    assert len(result["errors"]) == 1

    writer = _FakeFredWriter.instances[-1]
    error_types = sorted(q["error_type"] for q in writer.quarantined)
    assert error_types == ["api_error", "validation_error"]


# --------------------------------------------------------------------------- #
# copy_into_bronze
# --------------------------------------------------------------------------- #

_SQL_CONTENT = """
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.fred_economic_series (
  series_id STRING,
  _batch_id STRING,
  _batch_date DATE
);
COPY INTO ${catalog}.${schema}.fred_economic_series
FROM '${raw_path}'
FILEFORMAT = JSON
SELECT '${series_id}' AS series_id, '${batch_id}' AS _batch_id, DATE '${batch_date}' AS _batch_date;
"""


@pytest.mark.parametrize(
    "host_input",
    [
        "https://dbc-test.cloud.databricks.com",
        "https://dbc-test.cloud.databricks.com/",
        "dbc-test.cloud.databricks.com",
    ],
)
@responses.activate
def test_copy_into_bronze_runs_one_copy_per_series(host_input):
    """copy_into_bronze renders CREATE once and one COPY INTO per series."""
    dag = _load_fred_dag()
    copy_fn = dag.task_dict["copy_into_bronze"].python_callable

    fetch_result = _make_fetch_result()

    with patch("airflow.sdk.Variable.get") as mock_var:
        mock_var.return_value = {
            "host": host_input,
            "token": "dapi_test_token",
            "warehouse_id": "warehouse_123",
        }

        for i in range(1, 4):
            responses.post(
                "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
                json={"statement_id": f"stmt_{i}", "status": {"state": "SUCCEEDED"}},
                status=200,
            )
            responses.get(
                f"https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_{i}",
                json={"status": {"state": "SUCCEEDED"}, "statement_id": f"stmt_{i}"},
                status=200,
            )

        with patch("pathlib.Path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_SQL_CONTENT)):
            result = copy_fn(fetch_result)

    # 1 CREATE TABLE + 2 COPY INTO (one per series)
    assert result["statements_executed"] == 3
    assert result["copy_into_status"] == "success"

    post_calls = [c for c in responses.calls if c.request.method == "POST"]
    assert len(post_calls) == 3
    for call in post_calls:
        assert call.request.url == "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements"

    import json

    statements = [
        json.loads(call.request.body)["statement"] for call in post_calls
    ]

    assert "CREATE TABLE" in statements[0]
    assert "COPY INTO" not in statements[0]

    for statement, series_id in ((statements[1], "CPIAUCSL"), (statements[2], "UNRATE")):
        assert "COPY INTO dwh_dev.bronze.fred_economic_series" in statement
        assert f"'{series_id}'" in statement
        assert f"{series_id}.ndjson" in statement
        assert "fred_test_batch" in statement


@responses.activate
def test_copy_into_bronze_rejects_empty_paths():
    """copy_into_bronze fails fast when there is no series to load."""
    dag = _load_fred_dag()
    copy_fn = dag.task_dict["copy_into_bronze"].python_callable

    fetch_result = _make_fetch_result()
    fetch_result["series_raw_paths"] = {}

    with patch("airflow.sdk.Variable.get") as mock_var:
        mock_var.return_value = {
            "host": "dbc-test.cloud.databricks.com",
            "token": "dapi_test_token",
            "warehouse_id": "warehouse_123",
        }
        with pytest.raises(ValueError, match="No series raw paths to load"):
            copy_fn(fetch_result)


# --------------------------------------------------------------------------- #
# verify_bronze_load
# --------------------------------------------------------------------------- #


@responses.activate
def test_verify_bronze_load_parses_string_values():
    """verify_bronze_load parses the FRED JSON_ARRAY row (strings -> types)."""
    dag = _load_fred_dag()
    verify_fn = dag.task_dict["verify_bronze_load"].python_callable

    copy_result = _make_copy_result(_make_fetch_result())

    with patch("airflow.sdk.Variable.get") as mock_var:
        mock_var.return_value = {
            "host": "https://dbc-test.cloud.databricks.com/",
            "token": "dapi_test_token",
            "warehouse_id": "warehouse_123",
        }

        responses.post(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
            json={"statement_id": "stmt_verify", "status": {"state": "SUCCEEDED"}},
        )
        responses.get(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_verify",
            json={
                "status": {"state": "SUCCEEDED"},
                "statement_id": "stmt_verify",
                "result": {
                    "data_array": [["500", "2", "2020-01-01", "2024-12-01", "489"]]
                },
            },
        )

        result = verify_fn(copy_result)

    assert result["verification"] == {
        "row_count": 500,
        "series_count": 2,
        "min_date": "2020-01-01",
        "max_date": "2024-12-01",
        "non_null_values": 489,
        "status": "passed",
    }


@responses.activate
def test_verify_bronze_load_zero_rows():
    """verify_bronze_load fails when no rows are found for the batch."""
    dag = _load_fred_dag()
    verify_fn = dag.task_dict["verify_bronze_load"].python_callable

    copy_result = _make_copy_result(_make_fetch_result())

    with patch("airflow.sdk.Variable.get") as mock_var:
        mock_var.return_value = {
            "host": "dbc-test.cloud.databricks.com",
            "token": "dapi_test_token",
            "warehouse_id": "warehouse_123",
        }
        responses.post(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
            json={"statement_id": "stmt_verify", "status": {"state": "SUCCEEDED"}},
        )
        responses.get(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_verify",
            json={
                "status": {"state": "SUCCEEDED"},
                "statement_id": "stmt_verify",
                "result": {"data_array": [["0", "0", None, None, "0"]]},
            },
        )

        with pytest.raises(ValueError, match="No rows loaded into FRED Bronze table"):
            verify_fn(copy_result)


@responses.activate
def test_verify_bronze_load_series_mismatch():
    """verify_bronze_load fails when the distinct series count is wrong."""
    dag = _load_fred_dag()
    verify_fn = dag.task_dict["verify_bronze_load"].python_callable

    copy_result = _make_copy_result(_make_fetch_result())

    with patch("airflow.sdk.Variable.get") as mock_var:
        mock_var.return_value = {
            "host": "dbc-test.cloud.databricks.com",
            "token": "dapi_test_token",
            "warehouse_id": "warehouse_123",
        }
        responses.post(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
            json={"statement_id": "stmt_verify", "status": {"state": "SUCCEEDED"}},
        )
        responses.get(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_verify",
            json={
                "status": {"state": "SUCCEEDED"},
                "statement_id": "stmt_verify",
                "result": {"data_array": [["500", "1", "2020-01-01", "2024-12-01", "489"]]},
            },
        )

        with pytest.raises(ValueError, match="Expected 2 distinct series, found 1"):
            verify_fn(copy_result)


# --------------------------------------------------------------------------- #
# Module-level helpers
# --------------------------------------------------------------------------- #


def test_parse_fred_verification_row_valid():
    namespace = _load_fred_dag_namespace()
    parsed = namespace["_parse_fred_verification_row"](
        ["500", "3", "2020-01-01", "2024-12-01", "489"]
    )
    assert parsed == (500, 3, "2020-01-01", "2024-12-01", 489)


def test_parse_fred_verification_row_null_dates_and_values():
    namespace = _load_fred_dag_namespace()
    parsed = namespace["_parse_fred_verification_row"](["0", "0", None, None, None])
    assert parsed == (0, 0, "", "", 0)


def test_parse_fred_verification_row_wrong_length():
    namespace = _load_fred_dag_namespace()
    with pytest.raises(ValueError, match="Expected 5 columns"):
        namespace["_parse_fred_verification_row"](["500", "3"])


def test_parse_fred_verification_row_bad_value():
    namespace = _load_fred_dag_namespace()
    with pytest.raises(ValueError, match="Failed to parse FRED verification row"):
        namespace["_parse_fred_verification_row"](
            ["not_a_number", "3", "2020-01-01", "2024-12-01", "489"]
        )


def test_default_observation_start_is_five_years_ago():
    namespace = _load_fred_dag_namespace()
    start = namespace["_default_observation_start"]()

    parsed = date.fromisoformat(start)
    today = datetime.now(UTC).date()

    assert parsed <= today
    assert today.year - parsed.year == 5


@pytest.fixture(autouse=True)
def reset_state():
    """Reset responses and fake client/writer state between tests."""
    responses.reset()
    _FakeFredWriter.instances = []
    _FakeFredClient.instances = []
    _FakeFredClient.pages_by_series = {}
    yield
    responses.reset()
    _FakeFredWriter.instances = []
    _FakeFredClient.instances = []
    _FakeFredClient.pages_by_series = {}
