"""
Coexistence test for the two API ingestion DAGs (World Bank and FRED).

The two ingestion paths share the same Airflow environment, the same raw S3
bucket and the same Bronze catalog/schema. They must never collide on their
source name, raw prefix, quarantine prefix or Bronze table. This test loads
both DAG modules and asserts those namespaces are disjoint, so a future edit
to one side cannot silently start writing into the other side's path.
"""

from pathlib import Path

# S102: exec is intentional for loading DAGs from file, matching test_dag_import
# ruff: noqa: S102
DAGS_DIR = Path(__file__).parent.parent / "orchestration" / "dags"


def _load_dag_namespace(dag_filename: str) -> dict:
    """Execute a DAG file and return its module namespace."""
    dag_path = DAGS_DIR / dag_filename
    namespace = {"__file__": str(dag_path)}
    with open(dag_path, "r") as f:
        code = compile(f.read(), str(dag_path), "exec")
        exec(code, namespace)
    return namespace


def _bronze_table(namespace: dict) -> str:
    return (
        f"{namespace['DEFAULT_CATALOG']}.{namespace['DEFAULT_SCHEMA']}."
        f"{namespace['SOURCE_NAME']}"
    )


def test_world_bank_and_fred_namespaces_are_disjoint():
    """The two ingestion DAGs must not share source, path or table names."""
    world_bank = _load_dag_namespace("ingest_world_bank.py")
    fred = _load_dag_namespace("ingest_fred.py")

    # Source identity
    assert world_bank["SOURCE_NAME"] != fred["SOURCE_NAME"]

    # Raw S3 prefixes must not overlap in either direction.
    wb_raw = world_bank["RAW_PREFIX"]
    fred_raw = fred["RAW_PREFIX"]
    assert wb_raw != fred_raw
    assert not wb_raw.startswith(fred_raw) and not fred_raw.startswith(wb_raw)

    # Quarantine prefixes must not overlap in either direction.
    wb_quarantine = world_bank["QUARANTINE_PREFIX"]
    fred_quarantine = fred["QUARANTINE_PREFIX"]
    assert wb_quarantine != fred_quarantine
    assert not wb_quarantine.startswith(fred_quarantine)
    assert not fred_quarantine.startswith(wb_quarantine)

    # Bronze tables must be distinct.
    assert _bronze_table(world_bank) != _bronze_table(fred)

    # Bronze DDL files must be distinct.
    assert world_bank["SQL_FILE_PATH"] != fred["SQL_FILE_PATH"]


def test_coexistence_expectations_are_pinned():
    """Pin the concrete names so a rename is an explicit, reviewed change."""
    world_bank = _load_dag_namespace("ingest_world_bank.py")
    fred = _load_dag_namespace("ingest_fred.py")

    assert world_bank["SOURCE_NAME"] == "world_bank_indicators"
    assert world_bank["RAW_PREFIX"] == "api/world_bank_indicators"
    assert world_bank["QUARANTINE_PREFIX"] == "quarantine/api/world_bank_indicators"
    assert _bronze_table(world_bank) == "dwh_dev.bronze.world_bank_indicators"

    assert fred["SOURCE_NAME"] == "fred_economic_series"
    assert fred["RAW_PREFIX"] == "api/fred_economic_series"
    assert fred["QUARANTINE_PREFIX"] == "quarantine/api/fred_economic_series"
    assert _bronze_table(fred) == "dwh_dev.bronze.fred_economic_series"
