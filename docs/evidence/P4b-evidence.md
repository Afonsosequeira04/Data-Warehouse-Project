# P4b Evidence - NASA FIRMS Active Fires Ingestion

> STATUS: COMPLETED. The values below come from the supervised cloud run of `ingest_firms` on
> 2026-11-10, batch `nasa_firms_fires_20261110T005534Z_35c6528c151f`. The MWAA environment was
> created for the work window and destroyed afterwards; nothing billable was left running.
> The deviations in "Deviations from the plan" are part of this evidence: they describe what was
> actually executed, not what the plan intended.

## Overview

Adds the first current source to the platform: NASA FIRMS active-fire detections, fetched as three
separate VIIRS requests (`VIIRS_SNPP_NRT`, `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`), stored byte for
byte as CSV in immutable S3 raw storage, and loaded into one Bronze Delta table through COPY INTO via
the Databricks SQL Warehouse (ADR-001). The source contract, licence and fixtures were recorded in
P4b step 1; this file covers the end-to-end cloud run only.

## MWAA DAG Run

| Item | Value |
|---|---|
| DAG | `ingest_firms` |
| MWAA environment | `cloud-data-platform-dev` (`mw1.small`), ephemeral stack, destroyed after the window |
| Batch ID | `nasa_firms_fires_20261110T005534Z_35c6528c151f` |
| Ingest date | `2026-11-10` |
| `backfill_days` | `0` (DAG default: only each satellite's `max_date`) |
| Writing run | `scheduled__2026-11-09T06:00` (see deviation 3) |
| Second run | manual trigger with `backfill_days=0`, used as the idempotency check |

## S3 Raw Objects

Bucket `dwh-raw-data-9015f2`, prefix
`s3://dwh-raw-data-9015f2/api/nasa_firms_fires/ingest_date=2026-11-10/<batch_id>/`:

| Satellite | `data_date` | Object | Bytes | `row_count` (S3 metadata) |
|---|---|---|---|---|
| `VIIRS_SNPP_NRT` | 2026-11-02 | `viirs_snpp_nrt_2026-11-02.csv` | 2 867 736 | 35 261 |
| `VIIRS_NOAA20_NRT` | 2026-11-09 | `viirs_noaa20_nrt_2026-11-09.csv` | 5 145 636 | 61 601 |
| `VIIRS_NOAA21_NRT` | 2026-11-09 | `viirs_noaa21_nrt_2026-11-09.csv` | 3 536 080 | 42 391 |

Every object has `ContentType=text/csv` and the metadata keys written by
`ingestion/firms/raw_writer.py`: `source`, `data_id`, `data_date`, `batch_id`, `ingest_date`,
`row_count`.

**SNPP lag.** `VIIRS_SNPP_NRT` reported `max_date=2026-11-02`, eight days behind the ingest date, and
the run logged a lag warning instead of failing. This matches the NASA Earthdata alert recorded in
`docs/data-sources.md` (Suomi NPP stopped delivering new observations on 2026-11-02), so the date is
an end of data, not a transient delay. NOAA-20 and NOAA-21 reported `max_date=2026-11-09`, one day
behind, and both payloads contain data rows rather than a header-only CSV.

## Bronze Validation

Table `dwh_dev.bronze.nasa_firms_fires`, loaded by `copy_into_bronze` and checked by
`verify_bronze_load`, both executed inside MWAA through `ingestion/databricks_sql.py`. The Databricks
token was read only from the MWAA runtime secret and never outside that environment.

| `data_id` | rows |
|---|---|
| `VIIRS_NOAA20_NRT` | 61 601 |
| `VIIRS_NOAA21_NRT` | 42 391 |
| `VIIRS_SNPP_NRT` | 35 261 |
| **Total for the batch** | **139 253** |

The row counts equal the S3 `row_count` metadata of each object, so no row was lost or duplicated by
COPY INTO.

Sample row observed in Bronze:

| Column | Value |
|---|---|
| `data_id` | `VIIRS_NOAA20_NRT` |
| `_batch_id` | `nasa_firms_fires_20261110T005534Z_35c6528c151f` |
| `_batch_date` | `2026-11-10` |
| `_source_file` | `s3://dwh-raw-data-9015f2/api/nasa_firms_fires/ingest_date=2026-11-10/nasa_firms_fires_20261110T005534Z_35c6528c151f/viirs_noaa20_nrt_2026-11-09.csv` |

The per-satellite counts and the sample row were obtained with a temporary probe DAG
(`firms_bronze_probe`, never committed) that ran the same SQL utility as the real DAG. The probe was
removed from the DAG bucket and from the Airflow metadata database at the end of the window.

## Idempotency

A second execution was triggered on the same day with `backfill_days=0`:

- `already in raw, skipping` for the three satellites; `written_count=0`
- `copy_into_bronze` and `verify_bronze_load` skipped, because the batch wrote nothing
- no new object under the second batch's prefix
- zero new rows in Bronze

The skip decision comes from `existing_data_dates()`, which lists the already stored
`<data_id>_<data_date>.csv` objects under `ingest_date=*` before any HTTP request. A rerun therefore
cannot overwrite a raw object or duplicate a day in Bronze.

## Timings

| Step | Duration |
|---|---|
| MWAA environment creation | 37m 47s |
| Run 1 (fetch 19s, COPY INTO 28s, verify 4s) | 51s |
| Run 2 (idempotency) | 3s |
| MWAA destroy | 25m 51s |
| **Total window** | **95m 42s** (23:55:07Z to 01:30:49Z) |

## Cost

Estimated **US$0.85 to US$0.95** for the window:

| Resource | Basis | Estimate |
|---|---|---|
| MWAA `mw1.small` | ~US$0.49/h x ~1.6h | ~US$0.78 |
| NAT Gateway + Elastic IP | ~1.6h | ~US$0.08 |
| CloudWatch Logs | MWAA log groups | < US$0.02 |

The P2 runbook measured US$0.65 for a 73-minute window, which confirms the order of magnitude.
**This is an estimate only:** `scripts/mwaa_cost_report.sh` does not exist in the repository, so no
cost report was produced and Cost Explorer (24h lag) remains the authority.

## Teardown Proof

- `terraform destroy` in `infra/terraform/aws/ephemeral`: `Destroy complete! Resources: 17 destroyed.`
- `aws mwaa list-environments`: `{"Environments": []}`
- NAT Gateway tagged for the project: `state: deleted`; ephemeral VPCs: `[]`
- Persistent stack intact: raw bucket with the batch, DAG bucket, five `cloud-data-platform/*`
  secrets, budget `monthly-cost-guardrail`

## Deviations from the plan

1. **Missing scripts.** `scripts/mwaa_cycle.sh` and `scripts/mwaa_cost_report.sh` do not exist in the
   repository, so the window followed `docs/runbooks/mwaa-up-down.md` by hand and no cost report was
   produced.
2. **`-auto-approve`.** Apply and destroy ran with `-auto-approve`; the runbook asks for a manual
   confirmation on destroy. Without it the commands block waiting for input. Apply followed the
   approved `terraform plan`; the destroy was mandatory and already authorised for this window.
3. **DAG born paused.** `ingest_firms` is created with `is_paused_upon_creation=True`, so it had to be
   unpaused to run at all. Unpausing made Airflow create the missing scheduled run
   `scheduled__2026-11-09T06:00`, which started 7 seconds before the manual trigger. The evidence
   batch was therefore written by the scheduled run (with the DAG default `backfill_days=0`), and the
   manual trigger became the second execution used for the idempotency check. Both runs finished
   green with no duplication.
4. **Probe DAG.** `firms_bronze_probe` was uploaded outside the repository for the per-`data_id`
   counts and the sample row, then removed from S3 and from the Airflow metadata database.
5. **Stale objects in the DAG bucket.** `ingest_fred.py`, `ingest_world_bank.py`, `ingestion/api/` and
   old SQL files from the retired 2026-11-06 sources are still in the DAG bucket. They parse without
   import errors and were never triggered. They were not deleted because they are outside this
   phase's scope.
6. **MWAA CLI tokens.** The 60-second MWAA CLI tokens were used transiently and never printed or
   stored. A `grep` of the run logs found no `/api/.../csv/<key>` URL and no token.
7. **Account id in output.** The AWS account id appeared unredacted in the Terraform apply outputs (the
   MWAA ARN) and in one early `sts` call; the remaining commands substituted `<account>`. The full
   apply log stayed outside the repository (`/tmp/ephemeral-apply.txt`). The account id is not a
   secret and is deliberately not copied into this repository.

## Remaining Limitations

1. **No MERGE/UPSERT in Bronze.** COPY INTO appends per batch and skips files it already loaded; a new
   batch for the same `data_date` would append again. Deduplication by natural key belongs to the dbt
   staging models in P5.
2. **One day of latency for NOAA-20/21** and an indefinite gap for SNPP. A daily run therefore loads
   the previous day, not the current one.
3. **No automatic retry across satellites.** A satellite that fails raises and the DAG retries the
   whole task (2 retries, 5-minute delay); the others are re-fetched too, but the raw layer skips the
   days already stored.
4. **Empty days are not stored.** A header-only CSV is valid and produces no raw object, so a quiet day
   leaves no trace in S3.
5. **The failure/retry path is covered by tests, not by a live incident in this window.** Retries,
   backoff and rate limiting live in `ingestion/core/http.py` and are tested in
   `tests/test_core_http.py`; payload and HTTP failures in `tests/test_firms_client.py`. The local run
   of the full suite passed 152 tests.

## Artifacts

| Item | Location |
|---|---|
| Raw objects | `s3://dwh-raw-data-9015f2/api/nasa_firms_fires/ingest_date=2026-11-10/nasa_firms_fires_20261110T005534Z_35c6528c151f/` |
| Bronze table | `dwh_dev.bronze.nasa_firms_fires` |
| Source contract and licence | `docs/data-sources.md`, section 3 |
| Recorded fixtures | `tests/fixtures/nasa_firms_fires/` |
| Client, orchestration, raw writer | `ingestion/firms/` |
| Bronze SQL | `ingestion/sql/bronze_nasa_firms_fires.sql` |
| DAG | `orchestration/dags/ingest_firms.py` |
| Tests | `tests/test_firms_*.py`, `tests/test_dag_import.py` |

No screenshots: this phase keeps evidence in text, as P2 to P4 do.
