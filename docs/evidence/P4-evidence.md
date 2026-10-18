# P4 Evidence - FRED API 2 Ingestion

> STATUS: PENDING. The code path (client, writer, DAG, SQL, local/validation scripts, tests)
> is implemented, but a real MWAA run has NOT been executed yet. Every value below marked
> `PENDING` must be filled from the first real DAG run before the phase is considered done.
> Do not treat this file as proof until the placeholders are replaced with observed values.

## Overview
Extends the ingestion pattern from P3 to a second, structurally different source: FRED Economic
Series API (API key auth, `limit`+`offset` pagination) → S3 raw (NDJSON) → Bronze Delta table via
Databricks COPY INTO, reusing the shared Databricks SQL utilities while keeping the FRED client
independent from the World Bank client.

## MWAA DAG Run

### Environment
- **DAG**: `ingest_fred`
- **MWAA Environment**: `cloud-data-platform-dev` (class `mw1.small`) — PENDING
- **Run ID**: PENDING (manual trigger via Airflow UI)
- **Run Date**: PENDING

### S3 Raw Object
- **Bucket**: `dwh-raw-data-9015f2`
- **Path**: `s3://dwh-raw-data-9015f2/api/fred_economic_series/ingest_date=<date>/<batch_id>/<series_id>.ndjson` — PENDING
- **Format**: NDJSON (one observation per line)
- **Files**: 3 expected (one per series: CPIAUCSL, UNRATE, FEDFUNDS) — PENDING
- **Total records**: PENDING

### Batch Metadata
- **Batch ID**: PENDING (format `fred_<UTC timestamp>_<hex12>`)
- **Ingest Date**: PENDING
- **Source System**: `fred_economic_series`
- **Series Written**: PENDING (3 expected)
- **Quarantined Pages**: PENDING (0 expected)
- **Errors**: PENDING

## Bronze Table Validation

### Bronze Table
- **Catalog**: `dwh_dev`
- **Schema**: `bronze`
- **Table**: `fred_economic_series`
- **Format**: Delta Lake

### Row Counts & Quality
| Metric | Value |
|--------|-------|
| Total Rows | PENDING |
| Distinct Series | PENDING (3 expected) |
| Earliest Date | PENDING |
| Latest Date | PENDING |
| Non-Null Value Count | PENDING |
| Null Value Count (value column) | PENDING (FRED `.` marker preserved as STRING; cast to NULL in Silver) |
| Duplicate Keys (series_id+date) | PENDING (0 expected within a single batch) |

### Duplicate Key Check
```sql
SELECT series_id, date, COUNT(*) as cnt
FROM dwh_dev.bronze.fred_economic_series
GROUP BY series_id, date
HAVING COUNT(*) > 1
```
**Result**: PENDING

### Sample Data
| series_id | date | value | realtime_start | realtime_end | _batch_id |
|-----------|------|-------|----------------|--------------|-----------|
| PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |

## Automated Test Results

### Unit Tests (PENDING)
| Test Module | Tests | Status |
|-------------|-------|--------|
| test_fred_client.py | PENDING | PENDING |
| test_fred_writer.py | PENDING | PENDING |
| test_dag_ingest_fred.py | 14 | PENDING (14 passed locally) |
| test_dag_import.py | PENDING | PENDING |
| test_databricks_sql.py | PENDING | PENDING |

### Key Test Coverage
- **API Key Auth**: `api_key` never logged, never in exceptions, never in quarantine payloads; URLs redacted
- **Pagination**: `limit`+`offset` traversal, `max_pages` limit, empty/terminal page handling
- **Rate Limiting**: bounded requests per second with backoff
- **Quarantine (ADR-002)**: structurally invalid page (invalid JSON or error payload at HTTP 200) diverted to quarantine instead of silently dropped
- **Response Validation**: required observation fields, null values, the FRED `.` marker preserved as STRING
- **S3 Writer**: NDJSON output, one object per series (`<series_id>.ndjson`), batch ID generation, quarantine path
- **DAG Tasks**: `copy_into_bronze` renders SQL once per series (literal `series_id`), `verify_bronze_load` string→int casting

## Failure/Recovery Example

### Transient Error Handling
- **Scenario**: FRED API returns a transient HTTP error on first request
- **Behavior**: Client retries with exponential backoff (bounded)
- **Outcome**: PENDING
- **Test**: PENDING

### API Error Handling
- **Scenario**: FRED returns an error payload at HTTP 200
- **Behavior**: Client detects the error structure and raises `FredAPIError` / diverts the page to quarantine
- **Test**: PENDING

## Idempotency Assessment

### Current State
- **Rerun Behavior**: Each DAG run creates a new `batch_id` and writes new objects under a new prefix (`ingest_date=YYYY-MM-DD/<batch_id>/`)
- **Bronze Table**: COPY INTO appends new records with the new `_batch_id`; no deduplication on natural keys (series_id+date)
- **Result**: Reruns create duplicate natural keys differentiated only by `_batch_id`

### Limitation
Full idempotency is NOT achieved (same as P3). No MERGE/UPSERT; duplicates are distinguished by `_batch_id` and can be deduplicated downstream in dbt.

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
- **S3 Raw Path**: PENDING
- **Bronze Table**: `dwh_dev.bronze.fred_economic_series`
- **Test Fixtures**: `tests/fixtures/fred/` (4 files)
- **Test Files**: `test_fred_client.py`, `test_fred_writer.py`, `test_dag_ingest_fred.py`

## MWAA Environment Status
- **Environment**: PENDING (created only for the work window, then destroyed)
- **NAT Gateway**: PENDING
- **VPC**: PENDING
- **Persistent Stack**: Intact (S3 buckets, IAM roles, Secrets Manager, Budget, Unity Catalog)

## Cost
| Resource | Duration | Estimated Cost |
|----------|----------|----------------|
| MWAA `mw1.small` | PENDING | PENDING |
| NAT Gateway | PENDING | PENDING |
| **Total (estimated)** | | **PENDING** |

*Actual cost to be verified in Cost Explorer (24h lag).*
