# P3 Evidence - World Bank API 1 Ingestion

## Overview
Completed the first real ingestion path: World Bank Indicators API → S3 raw (NDJSON) → Bronze Delta table via Databricks COPY INTO.

## MWAA DAG Run

### Environment
- **DAG**: `ingest_world_bank`
- **MWAA Environment**: `cloud-data-platform-dev` (class `mw1.small`)
- **Run ID**: Manual trigger via Airflow UI
- **Run Date**: 2026-10-14

### S3 Raw Object
- **Bucket**: `dwh-raw-data-9015f2`
- **Path**: `s3://dwh-raw-data-9015f2/api/world_bank_indicators/ingest_date=2026-10-14/wb_20261014T114451Z_c823af23/`
- **Format**: NDJSON (one observation per line)
- **Files**: 3 files (one per indicator: NY.GDP.MKTP.KD.ZG, FP.CPI.TOTL.ZG, SL.UEM.TOTL.ZS)
- **Total records**: 8,778 observations across 3 pages

### Batch Metadata
- **Batch ID**: `wb_20261014T114451Z_c823af23`
- **Ingest Date**: 2026-10-14
- **Source System**: `world_bank_indicators`
- **Pages Written**: 3 (one per indicator)
- **Quarantined Pages**: 0
- **Errors**: None

## Bronze Table Validation

### Bronze Table
- **Catalog**: `dwh_dev`
- **Schema**: `bronze`
- **Table**: `world_bank_indicators`
- **Format**: Delta Lake

### Row Counts & Quality
| Metric | Value |
|--------|-------|
| Total Rows | 8,778 |
| Countries/Regions | 266 |
| Indicators | 3 (NY.GDP.MKTP.KD.ZG, FP.CPI.TOTL.ZG, SL.UEM.TOTL.ZS) |
| Earliest Year | 2014 |
| Latest Year | 2024 |
| Distinct Batch Count | 1 |
| Null Value Count (value column) | 840 |
| Duplicate Keys (country+indicator+year) | 0 |

### Duplicate Key Check
```sql
SELECT country_id, indicator_id, year, COUNT(*) as cnt
FROM dwh_dev.bronze.world_bank_indicators
GROUP BY country_id, indicator_id, year
HAVING COUNT(*) > 1
```
**Result**: No duplicate keys found (0 rows returned)

### Sample Data
| country_id | country_name | indicator_id | year | value | _batch_id |
|------------|--------------|--------------|------|-------|-----------|
| ZH | Africa Eastern and Southern | NY.GDP.MKTP.KD.ZG | 2024 | 2.78793146807502 | wb_20261014T114451Z_c823af23 |
| ZH | Africa Eastern and Southern | NY.GDP.MKTP.KD.ZG | 2023 | 1.94138157772015 | wb_20261014T114451Z_c823af23 |
| ZH | Africa Eastern and Southern | NY.GDP.MKTP.KD.ZG | 2022 | 3.66802914041513 | wb_20261014T114451Z_c823af23 |
| ZH | Africa Eastern and Southern | NY.GDP.MKTP.KD.ZG | 2021 | 4.45264295607002 | wb_20261014T114451Z_c823af23 |
| ZH | Africa Eastern and Southern | NY.GDP.MKTP.KD.ZG | 2020 | -2.93076411386527 | wb_20261014T114451Z_c823af23 |

## Automated Test Results

### Unit Tests (48 passed)
| Test Module | Tests | Status |
|-------------|-------|--------|
| test_world_bank_client.py | 15 | ✅ Passed |
| test_s3_writer.py | 7 | ✅ Passed |
| test_dag_import.py | 3 | ✅ Passed |
| test_dag_tasks_integration.py | 3 | ✅ Passed |
| test_dag_copy_into_bronze.py | 4 | ✅ Passed |
| test_databricks_sql.py | 16 | ✅ Passed |

### Key Test Coverage
- **Retry Logic**: HTTP 503 transient error → retry → success (2 tests)
- **API Error Handling**: HTTP 500, API error payload at HTTP 200, invalid schema, invalid JSON
- **Pagination**: Multi-page fetching, max_pages limit, empty page termination
- **Response Validation**: Null values, non-numeric values, invalid years, API error payloads
- **S3 Writer**: NDJSON output, key format, batch ID generation, quarantine path
- **SQL Parsing**: Placeholder replacement, statement splitting (drops comment-only chunks), verification row parsing (string→int casting)
- **DAG Tasks**: copy_into_bronze host normalization (3 host formats), verify_bronze_load string→int casting
- **Databricks Statement Execution API**: Single statement, batch execution, error handling, HTTP errors

## Failure/Recovery Example

### Transient Error Handling
- **Scenario**: World Bank API returns HTTP 503 (Service Unavailable) on first request
- **Behavior**: Client retries with exponential backoff (max_retries=1, backoff_factor=0.01)
- **Outcome**: Second request succeeds, 3 observations parsed
- **Test**: `test_fetch_indicator_retry_on_transient_error` ✅

### Retry Exhaustion
- **Scenario**: World Bank API consistently returns HTTP 503
- **Behavior**: Client retries up to max_retries (1), then raises WorldBankAPIError
- **Outcome**: Error raised with "HTTP 503" message
- **Test**: `test_fetch_indicator_retry_exhausted` ✅

### API Error at HTTP 200
- **Scenario**: World Bank returns HTTP 200 with error payload in response body
- **Behavior**: Client validates response structure, detects error message, raises WorldBankAPIError
- **Test**: `test_fetch_indicator_api_error_payload` ✅

## Idempotency Assessment

### Current State
- **Rerun Behavior**: Each DAG run creates a new batch_id and writes new files to S3 with a new prefix (`ingest_date=YYYY-MM-DD/batch_id/`)
- **Bronze Table**: COPY INTO appends new records with the new `_batch_id`; no deduplication on natural keys (country+indicator+year)
- **Result**: Rerunning ingestion creates duplicate records for the same natural keys, differentiated only by `_batch_id`

### Limitation
**Full idempotency is NOT achieved**. The pipeline does not:
- Check for existing records with the same natural key before inserting
- Use MERGE/UPSERT logic in the COPY INTO statement
- Prevent duplicate natural keys across batch runs

### Mitigation
- The `_batch_id` column allows distinguishing between ingestion runs
- Downstream dbt models can deduplicate using `ROW_NUMBER() OVER (PARTITION BY country_id, indicator_id, year ORDER BY _ingested_at DESC)`
- Quarantine path captures structurally invalid responses for investigation

## Remaining Limitations
1. **No automatic deduplication**: Reruns create duplicate natural keys
2. **No incremental state**: Each run fetches full date range (2014-2024)
3. **Single indicator per file**: One S3 object per indicator per page (could be consolidated)
3. **No schema evolution handling**: New fields in API response would require manual schema updates

## Artifacts
- **S3 Raw Path**: `s3://dwh-raw-data-9015f2/api/world_bank_indicators/ingest_date=2026-10-14/wb_20261014T114451Z_c823af23/`
- **Bronze Table**: `dwh_dev.bronze.world_bank_indicators`
- **Test Fixtures**: `tests/fixtures/world_bank/` (4 files)
- **Test Files**: 6 test modules, 48 tests total

## MWAA Environment Status
- **Environment**: Currently DESTROYED (per P2 destroy step)
- **NAT Gateway**: DESTROYED
- **VPC**: DESTROYED
- **Log Groups**: 5 remaining (created by MWAA, not managed by Terraform; no cost without logs)
- **Persistent Stack**: Intact (S3 buckets, IAM roles, Secrets Manager, Budget, Unity Catalog)

## Cost
| Resource | Duration | Estimated Cost |
|----------|----------|----------------|
| MWAA `mw1.small` | ~1.5 hours | ~$0.74 |
| NAT Gateway | ~1.5 hours | ~$0.07 |
| **Total (estimated)** | | **~$0.81** |

*Actual cost to be verified in Cost Explorer (24h lag).*