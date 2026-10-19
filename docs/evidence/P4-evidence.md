# P4 Evidence - FRED API 2 Ingestion

> STATUS: COMPLETED. Values below come from the first real MWAA run of `ingest_fred`
> (2026-10-18). The Databricks token expired mid-run and the load was recovered in the same
> run after rotating the token (see "Failure/Recovery Example"). One earlier object under
> `.../fred_20261018T201705Z_2a11700df1a6/` was produced by a local validation script and was
> NEVER loaded into Bronze; it is not part of this run.

## Overview
Extends the ingestion pattern from P3 to a second, structurally different source: FRED Economic
Series API (API key auth, `limit`+`offset` pagination) → S3 raw (NDJSON) → Bronze Delta table via
Databricks COPY INTO, reusing the shared Databricks SQL utilities while keeping the FRED client
independent from the World Bank client.

## MWAA DAG Run

### Environment
- **DAG**: `ingest_fred`
- **MWAA Environment**: `cloud-data-platform-dev` (class `mw1.small`, created 2026-10-18T22:20:36+01:00)
- **Run ID**: `manual__2026-10-18T22:36:12.619833+00:00`
- **Run Date**: 2026-10-18 (UTC) — final state **Success**

### S3 Raw Object
- **Bucket**: `dwh-raw-data-9015f2`
- **Path**: `s3://dwh-raw-data-9015f2/api/fred_economic_series/ingest_date=2026-10-18/fred_20261018T223620Z_f983d7b4dff4/`
- **Format**: NDJSON (one observation per line)
- **Files**: 3 (one per series)
  - `CPIAUCSL.ndjson` — 6294 bytes
  - `FEDFUNDS.ndjson` — 6120 bytes
  - `UNRATE.ndjson` — 6058 bytes
- **Total records**: 180 (60 observations per series × 3 series)

### Batch Metadata
- **Batch ID**: `fred_20261018T223620Z_f983d7b4dff4` (format `fred_<UTC timestamp>_<hex12>`)
- **Ingest Date**: 2026-10-18
- **Source System**: `fred_economic_series`
- **Series Written**: 3 (CPIAUCSL, UNRATE, FEDFUNDS) — `total_records` 180
- **Observation Start**: 2021-10-18 (computed at runtime as today − 5 years)
- **Quarantined Pages**: 0 (`quarantined_pages` 0)
- **Rejected Observations**: 0 (`rejected_observations` 0)
- **Errors**: `[]`

## Bronze Table Validation

### Bronze Table
- **Catalog**: `dwh_dev`
- **Schema**: `bronze`
- **Table**: `fred_economic_series`
- **Format**: Delta Lake
- **Load**: `copy_into_bronze` succeeded on try 4 (2026-10-18T22:48:30Z–22:49:02Z UTC, 31.98 s; 4 statements across 3 series). `verify_bronze_load` (try 1, 2026-10-18T22:49:02Z) passed: 180 rows, 3 series, date range 2021-10-01..2026-09-01.

### Row Counts & Quality
| Metric | Value |
|--------|-------|
| Total Rows | 180 |
| Distinct Series | 3 (CPIAUCSL, UNRATE, FEDFUNDS) |
| Earliest Date | 2021-10-01 |
| Latest Date | 2026-09-01 |
| Distinct Batch Count | 1 (`f983d7b4dff4`) |
| Non-Null Value Count | 180 (see note 1) |
| Null Value Count (value column) | 0 as NULL; 2 FRED `.` placeholders stored as STRING (see note 1) |
| Duplicate Keys (series_id+date) | 0 |

**Per-series breakdown (observed in Databricks):**

| series_id | rows | distinct _batch_id | earliest date | latest date | `.` placeholders |
|-----------|------|--------------------|---------------|-------------|------------------|
| CPIAUCSL | 60 | 1 | 2021-10-01 | 2026-09-01 | 1 |
| FEDFUNDS | 60 | 1 | 2021-10-01 | 2026-09-01 | 0 |
| UNRATE | 60 | 1 | 2021-10-01 | 2026-09-01 | 1 |

**Evidence note 1 (value semantics):** the DAG's `verify_bronze_load` reports
"non-null values=180" because the FRED `.` placeholder is a non-NULL STRING. The true breakdown is
178 numeric values + 2 `'.'` placeholders (CPIAUCSL 1, UNRATE 1). The `.` marker is cast to NULL
in Silver (P5).

**Evidence note 2 (date range vs observation_start):** the earliest loaded date (2021-10-01) is
before the computed `observation_start` (2021-10-18). Each series has 60 monthly observations
spanning October 2021 – September 2026, so the first monthly period begins before the exact
start day.

### Duplicate Key Check
```sql
SELECT series_id, date, COUNT(*) as cnt
FROM dwh_dev.bronze.fred_economic_series
GROUP BY series_id, date
HAVING COUNT(*) > 1
```
**Result**: No duplicate keys found (0 rows returned). Whole-table check confirms 180 rows and a
single distinct `_batch_id` (`f983d7b4dff4`); no rows from earlier runs are present.

### Sample Data
Per-row values were not captured during validation. The observed facts for this run are the
per-series counts, batch IDs, date ranges and placeholder counts in the table above. The earlier
local-validation object (`fred_20261018T201705Z_2a11700df1a6`, 945 UNRATE rows from 1948) was
written to S3 only and was deliberately NOT loaded into Bronze.

## Automated Test Results

### Unit Tests (116 passed)
| Test Module | Tests | Status |
|-------------|-------|--------|
| test_fred_writer.py | 32 | Passed |
| test_fred_client.py | 19 | Passed |
| test_databricks_sql.py | 17 | Passed |
| test_world_bank_client.py | 15 | Passed |
| test_dag_ingest_fred.py | 14 | Passed |
| test_s3_writer.py | 7 | Passed |
| test_dag_copy_into_bronze.py | 4 | Passed |
| test_dag_tasks_integration.py | 3 | Passed |
| test_dag_import.py | 3 | Passed |
| test_dag_coexistence.py | 2 | Passed |

### Key Test Coverage
- **API Key Auth**: `api_key` never logged, never in exceptions, never in quarantine payloads; URLs redacted
- **Pagination**: `limit`+`offset` traversal, `max_pages` limit, empty/zero-record/short-page termination
- **Rate Limiting**: bounded requests per second with backoff
- **Quarantine (ADR-002)**: structurally invalid page (invalid JSON or error payload at HTTP 200) diverted to quarantine instead of silently dropped
- **Response Validation**: required observation fields, null values, the FRED `.` marker preserved as STRING
- **S3 Writer**: NDJSON output, one object per series (`<series_id>.ndjson`), batch ID generation, quarantine path
- **DAG Coexistence**: World Bank and FRED namespaces, raw/quarantine prefixes and Bronze tables are disjoint
- **DAG Tasks**: `copy_into_bronze` renders SQL once per series (literal `series_id`), `verify_bronze_load` string→int casting

## Failure/Recovery Example

### Databricks Token Expired (HTTP 403) — real incident, recovered in the same run
- **Scenario**: Databricks token stored in secret `cloud-data-platform/databricks` expired before the run
- **Behavior**: `copy_into_bronze` failed on tries 1–3 with HTTP 403 Forbidden from the Databricks Statement Execution API; the DAG did not silently succeed
- **Recovery**: The token was rotated (only the token field of the secret was updated). Within the SAME run, `copy_into_bronze` and all downstream tasks were cleared and re-run — no new batch, no new S3 object
- **Outcome**: Try 4 succeeded (2026-10-18T22:48:30Z–22:49:02Z UTC, 31.98 s); `verify_bronze_load` then passed and the run finished Success
- **Note**: No duplicate rows resulted because tries 1–3 failed at authentication, before any COPY INTO executed

### Transient Error Handling
- **Scenario**: FRED API returns a transient HTTP error on a request
- **Behavior**: Client retries with exponential backoff (bounded); errors are redacted so the API key never appears in logs
- **Test**: `test_fetch_series_http_error_is_redacted`, `test_api_key_redacted_from_urllib3_retry_logs`

### API Error Handling
- **Scenario**: FRED returns an error payload at HTTP 200
- **Behavior**: Client detects the error structure and diverts the page to quarantine (ADR-002) instead of silently dropping it
- **Test**: `test_api_error_payload_is_quarantined`, `test_invalid_json_is_quarantined`

## Idempotency Assessment

### Current State
- **Rerun Behavior**: Each DAG run creates a new `batch_id` and writes new objects under a new prefix (`ingest_date=YYYY-MM-DD/<batch_id>/`)
- **Bronze Table**: COPY INTO appends new records with the new `_batch_id`; no deduplication on natural keys (series_id+date)
- **Result**: Reruns create duplicate natural keys differentiated only by `_batch_id`

### Limitation
Full idempotency is NOT achieved (same as P3). No MERGE/UPSERT; duplicates are distinguished by `_batch_id` and can be deduplicated downstream in dbt. In this specific run, the 403 retries did not add duplicates because they failed before the load; the batch contains exactly one row per (series_id, date).

### Mitigation
- `_batch_id` distinguishes ingestion runs
- dbt models deduplicate with `ROW_NUMBER() OVER (PARTITION BY series_id, date ORDER BY _ingested_at DESC)`
- Quarantine path captures structurally invalid responses for investigation

## Remaining Limitations
1. **No automatic deduplication**: reruns create duplicate natural keys
2. **No incremental state**: each run fetches the configured observation window (default: last 5 years)
3. **`value` stays STRING in Bronze**: the FRED `.` marker is preserved; numeric cast happens in Silver
4. **No schema evolution handling**: new fields in the API response would require manual schema updates

## Artifacts
- **S3 Raw Path**: `s3://dwh-raw-data-9015f2/api/fred_economic_series/ingest_date=2026-10-18/fred_20261018T223620Z_f983d7b4dff4/`
- **Bronze Table**: `dwh_dev.bronze.fred_economic_series`
- **Test Fixtures**: `tests/fixtures/fred/` (4 files)
- **Test Files**: `test_fred_client.py`, `test_fred_writer.py`, `test_dag_ingest_fred.py`, `test_dag_coexistence.py`

## MWAA Environment Status
- **Environment**: DESTROYED after the work window (observed: `aws mwaa list-environments` → `{"Environments": []}`)
- **NAT Gateway**: DESTROYED (observed: pending/available NAT gateways → `[]`)
- **Elastic IPs**: released (observed: `[]`)
- **VPC**: DESTROYED (Terraform: `Destroy complete! Resources: 17 destroyed.`)
- **CloudWatch Log Groups**: MWAA creates log groups that are not Terraform-managed; they may persist (as noted in P3) with no cost without logs
- **Persistent Stack**: Intact (S3 buckets, IAM roles, Secrets Manager, Budget, Unity Catalog)

## Cost
| Resource | Duration | Estimated Cost |
|----------|----------|----------------|
| MWAA `mw1.small` | ~2.2 hours | ~$1.21 |
| NAT Gateway | ~2.2 hours | ~$0.10 |
| **Total (estimated)** | | **~$1.31** |

*ESTIMATE only: MWAA (~$0.55/h) + NAT (~$0.045/h); data transfer negligible. The MWAA window ran
from creation 2026-10-18T22:20:36+01:00 to destroy observed complete 2026-10-19T00:33 (local),
about 2h10m including creation/destruction time that is also billed. Actual cost to be verified in
Cost Explorer (24h lag).*
