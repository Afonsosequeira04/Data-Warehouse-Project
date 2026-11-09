"""Tests for the Bronze COPY INTO template for NASA FIRMS fires.

No Databricks connection: the template is rendered with fake values and its
structure is checked textually.
"""

from __future__ import annotations

import re
from pathlib import Path

from ingestion.databricks_sql import render_sql_template, split_sql_statements
from ingestion.firms.client import EXPECTED_COLUMNS

SQL_PATH = Path(__file__).parents[1] / "ingestion" / "sql" / "bronze_nasa_firms_fires.sql"

CATALOG = "dwh_dev"
SCHEMA = "bronze"
TABLE = f"{CATALOG}.{SCHEMA}.nasa_firms_fires"
BATCH_ID = "nasa_firms_fires_20261108T060000Z_deadbeefcafe"
BATCH_DATE = "2026-11-08"
RAW_PATH = (
    f"s3://test-raw-bucket/api/nasa_firms_fires/"
    f"ingest_date={BATCH_DATE}/{BATCH_ID}/*.csv"
)

METADATA_COLUMNS = [
    "data_id",
    "_batch_id",
    "_ingested_at",
    "_source_file",
    "_source_system",
    "_batch_date",
]

_COLUMN_LINE = re.compile(
    r"^\s+([a-z_][a-z0-9_]*)\s+(STRING|TIMESTAMP|DATE)\s*(?:NOT NULL)?,?\s*$"
)
_ALIAS = re.compile(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)")


def _rendered() -> str:
    return render_sql_template(
        SQL_PATH.read_text(encoding="utf-8"),
        catalog=CATALOG,
        schema=SCHEMA,
        raw_path=RAW_PATH,
        batch_id=BATCH_ID,
        batch_date=BATCH_DATE,
    )


def _without_comments(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )


def _table_columns(statement: str) -> list[str]:
    return [
        match.group(1)
        for match in map(_COLUMN_LINE.match, _without_comments(statement).splitlines())
        if match
    ]


def test_all_placeholders_are_resolved():
    rendered = _rendered()

    assert "${" not in rendered


def test_split_yields_create_table_then_copy_into():
    statements = split_sql_statements(_rendered())

    assert len(statements) == 2
    assert f"CREATE TABLE IF NOT EXISTS {TABLE}" in statements[0]
    assert "USING DELTA" in statements[0]
    assert f"COPY INTO {TABLE}" in statements[1]
    assert "FILEFORMAT = CSV" in statements[1]


def test_select_metadata_aliases_follow_table_column_order():
    statements = split_sql_statements(_rendered())
    table_columns = _table_columns(statements[0])
    select_aliases = _ALIAS.findall(_without_comments(statements[1]))

    # The SELECT aliases are exactly the metadata columns, in table order:
    # the 14 source columns are selected by name without an alias.
    assert select_aliases == METADATA_COLUMNS
    assert table_columns[-len(METADATA_COLUMNS) :] == METADATA_COLUMNS


def test_source_columns_match_the_csv_header_order():
    table_columns = _table_columns(split_sql_statements(_rendered())[0])

    assert table_columns[:14] == list(EXPECTED_COLUMNS)


def test_copy_into_reads_the_batch_prefix_with_a_glob():
    copy_statement = split_sql_statements(_rendered())[1]

    assert f"FROM '{RAW_PATH}'" in copy_statement
    assert RAW_PATH.endswith(f"{BATCH_ID}/*.csv")


def test_copy_into_is_not_forced():
    copy_statement = split_sql_statements(_rendered())[1]

    assert "'force' = 'false'" in copy_statement
    assert "'mergeSchema' = 'false'" in copy_statement
