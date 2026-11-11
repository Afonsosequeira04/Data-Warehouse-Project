# Notion Implementation Plan - Cloud Data Platform

## Project outcome

Build and document a real-data, end-to-end cloud data platform that demonstrates:

`Public feeds (streaming + batch) -> controlled ingestion -> S3/Databricks -> Bronze -> Silver -> Gold -> data quality -> BI`

with:

`Terraform + GitHub Actions/OIDC + Unity Catalog + Secrets Manager + monitoring + cost controls`

The platform monitors natural hazards and maritime activity across sources: earthquakes and disaster alerts,
vessel traffic, ocean buoys, river/stream gauges, and active fires. It is a data-engineering portfolio project,
so the goal is a small, understandable production-style solution rather than a large architecture.

Revision note (2026-11-06): the platform was re-planned from a macroeconomic source set (World Bank Indicators,
FRED Economic Series) to a cross-source Earth-monitoring lakehouse. Six public sources are now `Selected`:
EMSC (earthquakes), AISstream (vessel positions), NASA FIRMS (active fires), USGS Water Data (gauges),
NOAA buoys, and GDACS (disaster alerts). P3 and P4 were completed against the retired World Bank and FRED
sources; they stay in this plan as completed legacy history and their evidence is kept unchanged. The current
roadmap continues at P4b. ADR-010 (always-on producer runtime), ADR-011 (streaming compute and budget),
and ADR-012 (re-scoped Supabase operational source) are `Proposed`; ADR-008 was rewritten for the streaming path.
Only Afonso moves an ADR to `Accepted`.

Earlier revision note: this version adds a phase for the ephemeral MWAA environment, moves Terraform to the start
of the project (persistent + ephemeral stacks), turns the open technical questions into ADRs, and adds a
branch -> cleanup -> PR workflow. The old "P8 - Terraform" phase no longer exists: Terraform is built
incrementally in P1 and P2, and reviewed in P11.

Fixed decisions: MWAA is used directly (no local Airflow) as an ephemeral environment created and destroyed with
Terraform; Terraform starts in P1; raw data, secrets and the budget live in a persistent stack that a destroy can
never touch. See `AGENTS.md` (D-001 to D-006) for the full list.

## Phase overview

| Phase | Name | Main outcome |
|---|---|---|
| P0 | Decisions and bootstrap | **DONE** — ADRs accepted, guardrails ready. Sources and business questions later re-planned on 2026-11-06 |
| P1 | Persistent foundation | **DONE** — Terraform persistent stack, S3 raw, IAM, secrets, budget, Unity Catalog |
| P2 | Ephemeral MWAA | **DONE** — repeatable create/destroy of MWAA with a hello DAG |
| P3 | API 1 ingestion (legacy) | **DONE** — World Bank Indicators -> S3 raw -> Bronze (source retired 2026-11-06) |
| P4 | API 2 ingestion (legacy) | **DONE** — FRED -> S3 raw -> Bronze (source retired 2026-11-06) |
| P4b | NASA FIRMS batch ingestion | **DONE** — three VIIRS satellites -> S3 raw -> Bronze via COPY INTO (2026-11-10) |
| P4c | Always-on foundation (EMSC, USGS, NOAA, GDACS) | One container on ECS Fargate -> Kinesis -> Structured Streaming -> Bronze (blocked until ADR-008, ADR-010 and ADR-011 are Accepted) |
| P5 | dbt Silver + Gold | Models, tests, snapshots over NASA FIRMS, EMSC, USGS, NOAA and GDACS |
| P6 | Data quality + quarantine | Rejected records visible and explained |
| P7 | daily_pipeline | Daily MWAA DAG for FIRMS ingestion, Fivetran trigger/wait, Bronze load, dbt build and dbt test |
| P8 | Fivetran ingestion path | Managed sync of Supabase `watch_region` and `alert_rule` into Databricks (re-scoped by ADR-012) |
| P8b | AISstream scale-out | AISstream producer -> Kinesis -> Databricks Structured Streaming (blocked until ADR-008, ADR-010 and ADR-011 are Accepted) |
| P9 | CI/CD with OIDC | PR checks and merge-to-main deployment (persistent stack only) |
| P10 | AI/BI dashboards | Hazard, maritime and data-quality dashboards |
| P11 | Hardening | Security, cost, idempotency, docs, evidence |
| P12 | Source discovery agent | OpenCode agent that proposes new public data sources of any geography — blocked until ADR-009 is Accepted and P9 is merged |

The implementation should be portfolio-ready: reproducible, observable, secure enough for a demo environment, and easy to explain in an interview.

---

# 0. How to build this in Notion

Create one main Notion page called:

**Cloud Data Platform - Build Tracker**

Inside it, create these databases.

## Database A - Tasks

Use these properties:

| Property | Type | Suggested values |
|---|---|---|
| Task | Title | Task name |
| Phase | Select | P0 Decisions, P1 Foundation, P2 MWAA, P3 API 1 (legacy), P4 API 2 (legacy), P4b FIRMS, P4c Always-on, P5 dbt, P6 Quality, P7 Pipeline, P8 Fivetran, P8b AISstream, P9 CI/CD, P10 BI, P11 Hardening, P12 Discovery |
| Status | Status | Not started, In progress, Blocked, Review, Done |
| Priority | Select | Must, Should, Could |
| Component | Multi-select | AWS, S3, IAM, Databricks, Unity Catalog, Python, Airflow/MWAA, Fivetran, dbt, Terraform, GitHub Actions, BI, Docs |
| Depends on | Relation | Relation to Tasks |
| Definition of Done | Text | Testable completion criteria |
| Verification | Text | Command/check used |
| GitHub | URL | PR/issue/commit |
| Notes | Text | Decisions, risks, follow-ups |

Use **Status** as the main board view.

Create these views:

- **Board - by Status**
- **Roadmap - by Phase**
- **Blocked**
- **Must Have**
- **Portfolio Ready**

## Database B - Architecture Decisions

Properties:

`ADR ID | Decision | Status | Date | Area | Context | Decision | Alternatives | Consequences`

Use this for source selection, Fivetran usage, database choice, ingestion modes, runtime placement, streaming
compute, incremental strategy, snapshot strategy, networking decisions, and anything else that changes architecture.

## Database C - Data Sources

Properties:

`Source | Mode | Type | Owner/Provider | API/Connector | Auth | Frequency | Grain | Expected Volume | Raw Path | Destination | Status | Notes`

`Mode` is mandatory: Streaming, Polling, Batch, or Managed sync.
Status values: Not selected, Shortlisted, Selected, Ready, Retired.
Do not mark a source "Ready" until its endpoint/connector, authentication approach, expected response shape, and
destination are known. A property that has not been verified must say "To verify in spike"; never invent endpoints,
rate limits or volumes.

## Database D - Portfolio Evidence

Properties:

`Evidence | Phase | Type | Location | Status | Notes`

Examples:

- architecture diagram
- screenshot of successful Airflow run
- screenshot of Databricks lineage
- dbt docs screenshot
- data quality dashboard
- GitHub Actions successful run
- Terraform plan output
- README section

This database is important because every major phase should leave visible proof that it works.


## Notion vs repository

Notion is for tracking. OpenCode only sees the repository, so anything the agent needs must exist in the repo:
ADRs in `docs/decisions/`, sources in `docs/data-sources.md`, business questions in `docs/business-questions.md`,
the current phase in `AGENTS.md`. Mirror these into Notion, never the other way round.

---

# 1. P0 - Decisions and project bootstrap

**Goal:** remove ambiguity before writing implementation code.

> **Legacy (2026-11-06):** P0 was completed against World Bank Indicators, FRED and Supabase. The two macro
> sources were retired and the business questions were replaced. This section remains as history; current source
> decisions live in `docs/data-sources.md`, `docs/business-questions.md`, ADR-008 and ADR-010 to ADR-012.

### Repository bootstrap (OpenCode, first PR)

- [x] Inspect the repo and confirm it only contains documentation.
- [x] Add `.gitignore` (env files, Terraform state, dbt artifacts, profiles, caches).
- [x] Create `docs/decisions/` with an ADR template and index.
- [x] Create `docs/data-sources.md` and `docs/business-questions.md`.
- [x] Create ADR-001 to ADR-004 as `Proposed` (options and trade-offs only).

### Decisions (Afonso, with OpenCode shortlists)

- [x] Accept or amend ADR-001 (how Bronze is loaded and who runs it) — **Accepted: COPY INTO via SQL Warehouse**
- [x] Accept or amend ADR-002 (quarantine boundary) — **Accepted: Hybrid (ingestion structural, dbt semantic)**
- [x] Accept or amend ADR-003 (where dbt runs) — **Accepted: dbt from MWAA execution context against SQL Warehouse**
- [x] Accept or amend ADR-004 (MWAA ephemeral operating model) — **Accepted: GitHub Actions create/destroy, private subnets + NAT**
- [x] Accept ADR-005 (RDS PostgreSQL operational source for Fivetran) — **Accepted (superseded by ADR-007 on 2026-10-13)**
- [x] Define business questions the Gold layer and dashboard must answer, **before** choosing APIs — **replaced on 2026-11-06 by BQ-001 to BQ-005**
- [x] Shortlist and choose **API 1** — **World Bank Indicators API** (retired 2026-11-06)
- [x] Shortlist and choose **API 2** — **FRED Economic Series API** (retired 2026-11-06)
- [x] Choose the **SaaS/DB source** for Fivetran — **Supabase PostgreSQL** (`macro_watchlist_db`; re-scoped by ADR-012, Proposed)
- [x] Record each source in `docs/data-sources.md` and in the Data Sources database.
- [x] Define a rough data grain for each source.
- [x] Define target catalog and schemas in Unity Catalog — **Catalog: `dwh_dev`; Schemas: `bronze`, `silver`, `gold`, `quarantine`, `snapshots`, `raw_fivetran`**
- [x] Define environment naming convention (`dev` and `prod` only if actually needed).

### Manual prerequisites (Afonso)

- [x] AWS: MFA on the root account, an admin identity that is not root, and an **AWS Budget with alerts** created before anything billable.
- [x] Databricks: confirm the workspace plan/type and that it supports a storage credential and an external location on S3
      plus a SQL Warehouse.
- [x] Fivetran: confirm whether the Databricks destination is available on the plan; otherwise mark P8 optional.

### Definition of Done (historical)

- ADR-001 to ADR-005 are `Accepted` (ADR-005 superseded by ADR-007).
- API 1 (World Bank Indicators), API 2 (FRED), and SaaS/DB (Supabase PostgreSQL) were no longer placeholders.
- Data sources had expected schemas/grains documented in `docs/data-sources.md`.
- The Gold/dashboard questions were defined and the chosen sources could answer them.
- Cost guardrails exist (AWS Budget $10/month with alerts at 50%, 80%, 100% actual and 100% forecasted).
- The Databricks workspace capability is confirmed.
- No implementation depends on an undocumented service.

The 2026-11-06 replan keeps the cost guardrail for batch sources only. Streaming and TB-scale extensions are
covered by ADR-011 and are not bound by the $10/month guardrail or by Databricks Free Edition limits.

---

# 2. P1 - Persistent foundation: Terraform + S3 + IAM + Unity Catalog

**Goal:** establish the minimum secure platform that never gets destroyed, and build it as code from the start.

### Terraform bootstrap

- [x] Decide and document the Terraform state approach (remote S3 backend; native lockfile locking since DynamoDB is out of scope).
- [x] Document how the state bucket itself is bootstrapped.
- [x] Create `infra/terraform/aws/persistent` and `infra/terraform/databricks` with `fmt` / `validate` / `plan` passing.

### AWS tasks (persistent stack)

- [x] Raw/landing S3 bucket: versioning, SSE-S3, public access blocked, `prevent_destroy`, no `force_destroy`.
- [x] Separate S3 location (or bucket) for MWAA DAGs and `requirements.txt`, also persistent.
- [x] Define the raw path convention and document it.
- [x] IAM roles/policies with least privilege.
- [x] Secrets Manager entries (names and structure only, no secret values in Git).
- [x] AWS Budgets managed in Terraform (or the manual budget documented and imported).
- [x] Resource tagging convention for cost attribution.
- [x] Validate that no credentials are stored in Git.

**Note:** The Supabase PostgreSQL source (`macro_watchlist_db`) is a manual prerequisite (create project, schema,
tables, read-only user). The AWS persistent stack only holds the secret container. No RDS resource is created in
the persistent stack. (Supersedes the previous RDS note from ADR-005, superseded by ADR-007 on 2026-10-13;
re-scoped by ADR-012, Proposed.)

### Databricks / Unity Catalog tasks

- [x] Confirm the Unity Catalog metastore / workspace relationship.
- [x] Storage credential and IAM role, resolving the external-ID circular dependency (verify the current documented procedure).
- [x] S3 external location.
- [x] Target catalog `dwh_dev` and the `bronze`, `silver`, `gold`, `quarantine`, `snapshots`, `raw_fivetran` schemas (Fivetran destination schema prefix to be confirmed in P8).
- [x] Baseline grants for pipeline, BI, and developer access.
- [x] SQL Warehouse: smallest size, short auto-stop.
- [x] Verify Databricks can read the intended S3 location without hard-coded cloud credentials.

### Definition of Done

- The persistent stack is created from Terraform and `plan` shows no drift.
- S3 exists and follows the immutable raw design.
- Unity Catalog governs the target schemas with least-privilege grants.
- A small S3 -> Databricks smoke test passes (a test file under a non-raw prefix).
- Budget and alerts exist.

### Evidence to save

- `terraform plan` / apply output (without secrets)
- Unity Catalog catalog/schemas screenshot
- smoke test result

---

# 3. P2 - Ephemeral MWAA environment: create, run, destroy

**Goal:** prove that MWAA can be created for a work window and destroyed afterwards without losing anything important,
before any real pipeline depends on it.

### Tasks

- [ ] Create `infra/terraform/aws/ephemeral` (VPC/subnets, NAT or the accepted networking option from ADR-004, security groups, MWAA execution role, MWAA environment, log configuration).
- [ ] Pin the Airflow version and constraints; confirm they are supported by MWAA.
- [ ] Point MWAA at the persistent DAG location so a rebuilt environment loads DAGs and `requirements.txt` automatically.
- [ ] Configure the Secrets Manager backend so connections/variables survive a rebuild.
- [ ] Write a `hello_world` DAG that reads one secret and writes a small object under a **test** prefix (never the raw prefix).
- [ ] Write `docs/runbooks/mwaa-up-down.md`: exact create command, destroy command, expected duration, expected cost, post-destroy checklist.
- [ ] Add a DAG import/parse test that runs without MWAA.
- [ ] Run one full cycle: apply -> run DAG -> collect evidence -> destroy. Record how long creation and deletion took.
- [ ] Verify after destroy that the persistent stack (raw bucket, DAG bucket, secrets, budget, Unity Catalog) is untouched.
- [ ] Verify nothing billable is left running.

### Definition of Done

- One complete apply -> DAG run -> destroy cycle is documented with measured time and cost.
- Destroying the ephemeral stack leaves all persistent resources intact.
- A rebuilt environment needs no manual configuration.

### Evidence to save

- Airflow UI with the successful `hello_world` run
- CloudWatch log sample
- runbook with measured durations
- post-destroy check (console / Cost Explorer)

---

# 4. P3 - World Bank ingestion (legacy): Python -> Airflow -> S3 -> Bronze

**Goal:** complete the first real ingestion path end to end.

> **Legacy (2026-11-06):** completed against World Bank Indicators, a source retired on 2026-11-06. The code and
> evidence stay in the repository until a later chore removes the retired source. Do not extend this phase.

Client logic is tested with `pytest` and recorded fixtures without MWAA running. The DAG run happens inside one planned MWAA window (see the P2 runbook).

### Tasks

- [x] Create a source-specific API client for World Bank Indicators.
- [x] Implement authentication/configuration through secrets or environment variables (no auth required for World Bank).
- [x] Implement pagination (page + per_page).
- [x] Implement rate-limit handling.
- [x] Implement bounded retries with backoff.
- [x] Validate response shape.
- [x] Write raw JSON to the immutable S3 path (`s3://<bucket>/api/world_bank_indicators/ingest_date=YYYY-MM-DD/`).
- [x] Generate a batch identifier.
- [x] Include ingestion-date information.
- [x] Add technical metadata for Bronze.
- [x] Create the first Bronze Delta table using the mechanism accepted in ADR-001 (COPY INTO via SQL Warehouse).
- [x] Test a successful run.
- [x] Test an expected API/schema failure.
- [x] Test a retry/idempotency scenario.

### Definition of Done

A real API call produces a dated raw object in S3 and a usable Bronze table, with metadata and a clear failure path.

### Evidence to save in Notion

- successful ingestion log/screenshot
- S3 object path
- Bronze table preview
- failure/retry example

---

# 5. P4 - FRED ingestion (legacy)

**Goal:** prove the architecture handles more than one API shape.

> **Legacy (2026-11-06):** completed against FRED, a source retired on 2026-11-06. The code and evidence stay in
> the repository until a later chore removes the retired source. Do not extend this phase.

### Tasks

- [x] Build FRED client independently from World Bank client.
- [x] Reuse common ingestion utilities only where genuinely useful.
- [x] Handle FRED's pagination (limit + offset), rate limits (120 req/min), and API key auth.
- [x] Write FRED raw payloads to its own S3 prefix (`s3://<bucket>/api/fred_economic_series/ingest_date=YYYY-MM-DD/`).
- [x] Add FRED Bronze table (`<catalog>.bronze.fred_economic_series`).
- [x] Add validation for source-specific fields.
- [x] Test a bad payload/validation path.
- [x] Confirm both APIs can coexist in the same daily pipeline without overwriting each other's raw data.

### Definition of Done

Two real APIs run through the same platform pattern while preserving source-specific logic and raw data.

---

# 5b. P4b - NASA FIRMS batch ingestion

**Goal:** add the first current source: a scheduled HTTP batch ingestion of active-fire detections into immutable
S3 raw storage and Bronze, without depending on MWAA for the client tests.

NASA FIRMS is the only source that follows the MWAA batch pattern. Read the source entry in `docs/data-sources.md`
first; every property not verified there says "To verify in spike".

### Tasks

- [x] **Spike:** verify endpoint, authentication (e.g. API key), rate limits, response format, terms/licence and
      expected volume. Save real recorded samples (never synthetic stand-ins for the real shape) under
      `tests/fixtures/nasa_firms_fires/` and record the findings in `docs/data-sources.md`.
- [x] Create a source-specific client, separate from orchestration.
- [x] Read credentials/configuration from environment variables or AWS Secrets Manager; never hard-code them.
- [x] Implement bounded retries with backoff and respect the documented rate limits.
- [x] Validate the response shape before writing a successful ingestion.
- [x] Write raw payloads to the immutable path `s3://<bucket>/api/nasa_firms_fires/ingest_date=YYYY-MM-DD/`.
- [x] Generate a batch identifier and include ingestion metadata.
- [x] Load Bronze (`dwh_dev.bronze.nasa_firms_fires`) with the mechanism accepted in ADR-001 (COPY INTO via SQL Warehouse).
- [x] Add source-specific field validation.
- [x] Test: successful run, expected schema failure, and rerun/idempotency (no raw overwrite).
- [x] Add the DAG task that runs the client, with a client import/parse test that runs without MWAA.

### Definition of Done

A real NASA FIRMS call produces dated raw objects in S3 and a usable Bronze table with the standard technical
metadata, the spike samples and findings are committed, and the failure/retry path is tested.

Met on 2026-11-10: batch `nasa_firms_fires_20261110T005534Z_35c6528c151f` wrote three raw objects (139 253 rows
in total) and loaded them into `dwh_dev.bronze.nasa_firms_fires`; a same-day rerun skipped all three satellites
and added nothing. The retry/backoff and payload-failure paths are covered by
`tests/test_core_http.py` and `tests/test_firms_client.py`. Evidence: `docs/evidence/P4b-evidence.md`.

Advancing "Current phase" to P4c is deliberately not done here: P4c is blocked until ADR-008, ADR-010 and
ADR-011 are `Accepted`, which is Afonso's decision.

### Evidence to save

- successful ingestion log/screenshot
- S3 object path
- Bronze table preview
- spike notes and fixture paths
- failure/retry example

---

# 5c. P4c - Always-on foundation (EMSC, USGS, NOAA, GDACS)

**Goal:** prove the always-on ingestion path with one Python container on ECS Fargate that runs a WebSocket
consumer for EMSC and polling loops for USGS Water Data, NOAA buoys and GDACS, publishing every message to
Kinesis and landing it in Bronze through Databricks Structured Streaming.

Blocked until ADR-008, ADR-010 and ADR-011 are `Accepted`.

### Tasks

Spike each source separately, saving real samples under `tests/fixtures/<source_name>/` and recording findings in
`docs/data-sources.md`:

- [ ] `emsc_earthquakes` (WebSocket)
- [ ] `usgs_water_gauges` (polling)
- [ ] `noaa_ocean_buoys` (polling)
- [ ] `gdacs_disaster_alerts` (polling)

Then:

- [ ] Package one Python container image with the EMSC WebSocket consumer and the three polling loops (runtime per ADR-010).
- [ ] Read configuration and any credentials from environment variables or AWS Secrets Manager.
- [ ] Implement reconnection, bounded retries/backoff, validation and bounded queueing.
- [ ] Write the producer runtime and its Terraform root; keep Kinesis and the container out of the persistent stack.
- [ ] Create the Kinesis stream (1 shard, 24h retention) and the Databricks Structured Streaming job.
- [ ] Land messages into `bronze.stream_emsc_earthquakes`, `bronze.stream_usgs_water_gauges`,
      `bronze.stream_noaa_ocean_buoys` and `bronze.stream_gdacs_disaster_alerts`.
- [ ] Route invalid messages to `s3://<bucket>/quarantine/stream/<source>/` with source and batch context.
- [ ] Keep checkpoints in a non-raw location (Unity Catalog managed storage or a separate checkpoint bucket).
- [ ] Deploy the container to ECS Fargate and verify it keeps running with reconnection.
- [ ] Add producer tests that run without AWS, plus an idempotent restart check from a checkpoint.
- [ ] Document the manual apply/destroy procedure for the streaming stack and its cost while applied.

### Definition of Done

The four always-on sources reach their `bronze.stream_*` tables end to end through Kinesis and Structured
Streaming, invalid messages are visible in Quarantine, each spike sample and finding is committed, a restart from
the checkpoint is verified, and the streaming stack is applied and destroyed manually without touching the
persistent stack.

### Evidence to save

- container and Kinesis metrics screenshots
- streaming job run
- Bronze previews per source
- quarantine example
- restart-from-checkpoint evidence
- spike notes and fixture paths

---

# 6. P5 - dbt Silver + Gold + tests + snapshots

**Goal:** convert the Bronze sources (NASA FIRMS, EMSC, USGS, NOAA, GDACS) into analytics-ready data that answers
BQ-001 to BQ-005. AISstream arrives later, in P8b.

## Silver / staging

- [ ] Configure the dbt Databricks adapter (connection via environment variables, no committed `profiles.yml` with real values; run location per ADR-003).
- [ ] Create source definitions for each Bronze table (batch and stream).
- [ ] Create one staging model per source (FIRMS, EMSC earthquakes, USGS gauges, NOAA buoys, GDACS).
- [ ] Standardize names and data types.
- [ ] Deduplicate records where required.
- [ ] Normalize dates, identifiers, coordinates and categorical fields.
- [ ] Implement business rules that belong in transformation, not ingestion.
- [ ] Resolve the common spatial key open question (candidate: H3; resolution to be decided in this phase) and document it.

## Gold / marts

- [ ] Decide the analytical grain of each fact table against `docs/business-questions.md` (draft grains there still need Afonso's confirmation).
- [ ] Create dimension models (e.g. `dim_region`, `dim_fire_detection`, `dim_gauge_station`, `dim_buoy_station`, `dim_disaster_event`, `dim_alert_rule`).
- [ ] Create fact models (e.g. `fact_fire_detection`, `fact_gauge_observation`, `fact_buoy_observation`, `fact_disaster_event`, `fact_alert_evaluation`).
- [ ] Document how the same earthquake appearing in EMSC and GDACS will be reconciled.
- [ ] Add a stable metric layer for dashboard KPIs.
- [ ] Document business definitions.

## Data quality

- [ ] Add not-null tests where appropriate.
- [ ] Add unique tests where appropriate.
- [ ] Add relationship tests for foreign keys.
- [ ] Add accepted-value tests where business domains are controlled.
- [ ] Add source freshness/recency checks where useful.
- [ ] Add custom tests for important business rules.

## Snapshots

- [ ] Identify an entity whose attribute history is meaningful (e.g. a gauge, buoy or disaster event).
- [ ] Implement a dbt snapshot using SCD2 semantics.
- [ ] Verify historical versions can be reconstructed.

### Definition of Done

`Bronze -> dbt Silver -> dbt Gold` builds successfully over the Bronze sources (NASA FIRMS, EMSC, USGS, NOAA,
GDACS), quality tests are meaningful, and at least one historical change is represented through a snapshot.

---

# 7. P6 - Data quality + quarantine

**Goal:** demonstrate what happens when data is bad instead of silently accepting or dropping it.

### Tasks

- [ ] Define which records are invalid vs merely incomplete.
- [ ] Implement the quarantine boundary accepted in ADR-002 and keep the diagram, README and AGENTS.md consistent with it.
- [ ] Define validation rules at the correct layer.
- [ ] Create a Quarantine destination/table.
- [ ] Persist rejection reason.
- [ ] Persist source/batch metadata with rejected records.
- [ ] Add a quality summary: ingested rows, rejected rows, failed tests, freshness.
- [ ] Create a reproducible bad-record test fixture.
- [ ] Verify that valid and invalid records follow separate paths.

### Definition of Done

A controlled invalid-record scenario is visible in the Quarantine path and in the data-quality reporting.

---

# 8. P7 - daily_pipeline on MWAA

**Goal:** orchestrate the daily batch pipeline over the MWAA environment proven in P2.

The environment is created for planned windows only. Each window: apply the ephemeral stack, run/observe the DAG, capture evidence, destroy.
The always-on sources (EMSC, USGS, NOAA, GDACS, AISstream) run continuously in their own container and are never orchestrated by MWAA.

### Tasks

- [ ] Add the NASA FIRMS batch ingestion task.
- [ ] Add FIRMS S3 availability/check tasks.
- [ ] Add the FIRMS Bronze load step (mechanism per ADR-001).
- [ ] Add Fivetran trigger/wait steps only when Fivetran is enabled.
- [ ] Add the dbt build step over the batch and always-on Bronze tables (runner per ADR-003).
- [ ] Add the dbt test / data-quality step.
- [ ] Add the final mart-availability check.
- [ ] Configure retries, timeouts, and failure visibility.
- [ ] Test a full successful run inside one MWAA window.
- [ ] Test a controlled failure and recovery inside a window.
- [ ] Destroy the environment and confirm the persistent stack is intact.

### Definition of Done

One Airflow DAG runs the daily batch pipeline (FIRMS ingestion, the optional Fivetran sync, the Bronze load, and the dbt build and dbt test) with clear dependencies, retries, and observable outcomes, and the environment can be destroyed and rebuilt without losing the ability to run it.

### Evidence to save

- DAG graph
- successful run screenshot
- failed/recovered task screenshot
- CloudWatch log sample
- cost of the window

---

# 9. P8 - Fivetran ingestion path

**Goal:** demonstrate a managed database ingestion strategy using:

```
Supabase PostgreSQL (watch_region, alert_rule)
-> Fivetran
-> Databricks (schema: raw_fivetran, prefix to be confirmed in P8)
```

Fivetran is the intended second ingestion strategy, but can only be formally skipped later if the actual Fivetran
plan/account does not support the Databricks destination or another documented blocker exists. ADR-012 (Proposed)
re-scopes the Supabase database from the old macro watchlist to hazard-monitoring configuration. The Gold alert
logic evaluates `alert_rule` against the batch sources; `watch_region` holds the regions being watched.
Until P8, the batch producers read a static configuration from the repository.

### Tasks

- [ ] Create the Supabase project and schema manually (outside AWS Terraform).
- [ ] Seed `macro_watchlist_db` with `watch_region` and `alert_rule` tables (design to be confirmed when ADR-012 is Accepted).
- [ ] Create a dedicated read-only Fivetran database user in Supabase.
- [ ] Store credentials in the AWS Secrets Manager secret for the database.
- [ ] Configure the Fivetran PostgreSQL connector via the Supabase session pooler.
- [ ] Configure the Databricks destination (verify Fivetran plan supports it).
- [ ] Define `raw_fivetran` convention: `dwh_dev.raw_fivetran.<table>` (Fivetran destination schema prefix to be confirmed in P8; Unity Catalog uses three-level naming: catalog.schema.table).
- [ ] Validate initial synchronization.
- [ ] Validate incremental synchronization (Query-Based using `xmin`, exact cursor to verify in P8 via session pooler).
- [ ] Integrate trigger/wait logic with Airflow.
- [ ] Add downstream dbt staging for the ingested configuration tables.
- [ ] Verify core pipeline remains functional if Fivetran is disabled.

### Definition of Done

Fivetran demonstrates a managed ingestion path while the core AWS + Databricks + dbt pipeline remains independent.
The Supabase project is a manual prerequisite; the AWS persistent stack only holds the secret container.

---

# 9b. P8b - AISstream scale-out

**Goal:** add AISstream to the always-on foundation built in P4c, as a regular phase of the portfolio (not
optional). Blocked until ADR-008, ADR-010 and ADR-011 are Accepted.

```
AISstream (WebSocket)
-> existing ECS Fargate container (new consumer alongside EMSC and the polling loops; runtime per ADR-010)
-> Kinesis Data Streams (1 shard, 24h retention; separate Terraform root)
-> Databricks streaming job (Structured Streaming; compute per ADR-011)
-> bronze.stream_ais_vessel_positions
-> dbt incremental Silver -> Gold
```

Invalid messages go to the S3 raw bucket prefix `quarantine/stream/<source>/`. Checkpoints live in a non-raw
location (Unity Catalog managed storage or a separate checkpoint bucket). Streaming freshness and consumer health
are shown in the data-quality dashboard. The environment is applied and destroyed manually, never by CI, and it
runs continuously while it is applied; cost is tracked and the decision is documented.

### Tasks

- [ ] **Spike:** verify endpoint, authentication, message format, rate limits, terms/licence and expected volume; save real samples under `tests/fixtures/aisstream_vessel_positions/`; record findings in `docs/data-sources.md`.
- [ ] Add the AISstream consumer to the existing producer container.
- [ ] Implement reconnection, bounded retries/backoff, validation and bounded queueing.
- [ ] Publish messages to the Kinesis stream created in P4c.
- [ ] Land messages into `bronze.stream_ais_vessel_positions` with the standard technical metadata.
- [ ] Route invalid messages to the quarantine prefix with source and ingestion context.
- [ ] Add dbt incremental Silver models and Gold models on top of the AIS Bronze table and the spatial joins needed by BQ-001 and BQ-002.
- [ ] Show AISstream freshness and consumer health in the data-quality dashboard.
- [ ] Run one apply -> stream -> verify -> destroy cycle with measured cost.
- [ ] Add a consumer test that runs without AWS.

### Definition of Done

AISstream reaches Bronze end to end through Kinesis and Structured Streaming, invalid messages are visible in
Quarantine, the Gold layer answers BQ-002 and completes BQ-001, the stack is applied and destroyed manually with
measured cost, and nothing billable is left running.

### Evidence to save

- producer and Kinesis metrics screenshots
- streaming job run
- Bronze and Gold previews
- quarantine example
- cost while the stack is applied
- post-destroy check

---

# 10. P9 - GitHub Actions + OIDC CI/CD

**Goal:** turn the project into a repeatable engineering workflow.

### Pull Request workflow

- [ ] Python tests.
- [ ] Python lint/format checks.
- [ ] `dbt parse`.
- [ ] dbt tests that can run safely in CI.
- [ ] gitleaks/secret scanning.
- [ ] Terraform formatting.
- [ ] Terraform validation.
- [ ] Terraform plan (persistent stack, ephemeral stack, Databricks; not the streaming root unless explicitly selected).
- [ ] DAG import test.

### Main workflow

- [ ] Establish protected `main` workflow.
- [ ] Authenticate to AWS with OIDC.
- [ ] Deploy Terraform for the persistent stack and Databricks only. Merge to `main` must never create the ephemeral (MWAA) stack or the streaming stack.
- [ ] Deploy Databricks changes.
- [ ] Run `dbt build`.
- [ ] Surface failures clearly.

### Definition of Done

A pull request produces automated verification, and merge-to-main performs the documented deployment path
without long-lived AWS keys.

---

# 11. P10 - Databricks AI/BI dashboards

**Goal:** make the result understandable to a business user and a data engineer.

## Business dashboard

Answer the approved business questions, for example:

- recent significant earthquakes and the vessels near each one (BQ-001)
- buoys with anomalous wave height or pressure and the vessels in the area (BQ-002)
- gauges near or above flood thresholds, or rising fast (BQ-003)
- active fires and their evolution by region (BQ-004)
- GDACS orange/red events and what other sources show nearby (BQ-005)

Do not force metrics that do not make sense for the final sources.

## Data quality dashboard

Include:

- pipeline status
- latest successful batch and latest stream checkpoint
- rows ingested
- rows rejected
- failed tests
- freshness/recency
- source health where possible

### Definition of Done

A user can understand both the business output and the health of the data pipeline without opening the source code.

---

# 12. P11 - Security, reliability, and portfolio hardening

**Goal:** move from "it works" to "it is explainable and defensible in an interview".

### Tasks

- [ ] Remove secrets and accidental credentials from Git history/repository.
- [ ] Confirm least-privilege IAM, including the producer runtime and the streaming stack.
- [ ] Confirm OIDC workflow.
- [ ] Confirm no raw S3 overwrite behavior.
- [ ] Confirm retry/idempotency behavior.
- [ ] Confirm failure alerts/logging are useful.
- [ ] Confirm quarantine behavior for batch and streaming.
- [ ] Confirm dbt tests cover the critical models.
- [ ] Confirm snapshot history works.
- [ ] Review cloud cost controls, including a check that nothing billable is left running.
- [ ] Terraform completeness review: anything created by hand is either in code or documented as manual.
- [ ] Full rebuild test: destroy and recreate the ephemeral and streaming stacks from a clean checkout and run the pipelines.
- [ ] Review dependency versions and remove unused packages, including the retired World Bank/FRED code.
- [ ] Add architecture diagram showing the final implementation, not only the planned state.
- [ ] Update README with a reproducible quickstart.
- [ ] Add a "How data flows" section.
- [ ] Add a "Why these technologies" section.
- [ ] Add a "Trade-offs and limitations" section.
- [ ] Add screenshots/evidence to the portfolio documentation.

### Definition of Done

Someone unfamiliar with the project can clone it, read the documentation, understand the architecture/trade-offs, and see evidence that each major component was actually used.

---

# 12b. P12 - Source discovery agent

**Goal:** demonstrate a governed, agent-assisted way to extend the platform with new real public sources of any geography, without weakening the existing ingestion design.

```
Ingestion pipeline (MWAA + Databricks + streaming)
-> one client per source (existing design, unchanged)

Discovery agent (OpenCode on GitHub Actions, weekly, no AWS/Databricks credentials)
-> opens a source proposal (issue or docs PR)

Afonso
-> reviews the proposal, assigns the BQ number, integrates the accepted source
```

The agent runs weekly on GitHub Actions, inspects public information about candidate sources, and opens a proposal describing the source, the business question it could answer, and its access method. It never receives AWS or Databricks credentials; its only repository permissions are `contents: write` and `pull-requests: write`. It generates no ingestion code and does not modify the pipeline. Source secrets (API keys) live in AWS Secrets Manager and never appear in a proposal. A source with no documented access may be investigated with REA (github.com/morluto/rea, MIT), limited to a separate manual `workflow_dispatch` run with a user-approved URL and a pinned version — never in the scheduled job, CI, Airflow, or MWAA.

Every proposed source must satisfy the selection criteria in `docs/data-sources.md`: a real analytical need tied to an approved business question, real external data, free or free-tier access, a documented access method, a licence compatible with the project, and a volume appropriate to the portfolio scope. Geography is not a criterion.

### Open Questions (blocking Acceptance of ADR-009)

- Which model/provider runs the agent, and what spending limit applies?
- Is REA acceptable for this repository, and which terms-of-use policy approves a target before any fetch?
- Does the GitHub plan support environments with required reviewers for the agent's proposal workflow?
- GitHub App or `GITHUB_TOKEN` for the agent's write access?

### Tasks

- [ ] Choose the first real source and the business question it answers. Afonso assigns the BQ number; this chore creates no BQ.
- [ ] Implement the discovery agent at option 2 (propose only: issue or docs PR, no ingestion code).
- [ ] Review the agent's first proposal and integrate the accepted source through the normal phase or chore flow.
- [ ] Capture the evidence of a real proposed source reaching Bronze.

### Definition of Done

An agent run proposes at least one real, publicly available source of any geography; Afonso reviews the proposal and integrates the accepted source; the data reaches Bronze without weakening the existing architecture; the flow is documented and reproducible.

### Evidence to save

- Links to the agent runs and the proposal it opened.
- The integration PR for the accepted source and the resulting Bronze table.

No implementation may start until ADR-009 is Accepted by Afonso and P9 is merged.

---

# 13. Suggested Notion milestones

Create milestone pages or checkboxes for these outcomes:

- [x] **M1 - Architecture locked** (P0)
- [x] **M2 - S3 + Unity Catalog working, built with Terraform** (P1)
- [x] **M3 - MWAA create/run/destroy cycle proven** (P2)
- [x] **M4 - First API reaches Bronze** (P3, legacy)
- [x] **M5 - Two APIs reach Bronze** (P4, legacy)
- [ ] **M5b - First current batch source (NASA FIRMS) reaches Bronze** (P4b)
- [ ] **M5c - EMSC, USGS, NOAA and GDACS reach Bronze** (P4c)
- [ ] **M6 - Silver + Gold + tests working over the batch and always-on sources** (P5)
- [ ] **M7 - Quarantine path working** (P6)
- [ ] **M8 - Daily Airflow pipeline working** (P7)
- [ ] **M9 - Fivetran path working or formally skipped with a documented reason** (P8)
- [ ] **M10 - Always-on streaming path demonstrated end to end** (P4c foundation, P8b AISstream)
- [ ] **M11 - CI/CD with OIDC working** (P9)
- [ ] **M12 - BI + data-quality dashboards working** (P10)
- [ ] **M13 - Portfolio hardening complete** (P11)
- [ ] **M14 - Source discovery agent** (P12)

---

# 14. OpenCode execution style

Do not give OpenCode the entire roadmap as one giant implementation request.
Use one phase, or one small group of dependent tasks, at a time. One phase = one branch = one PR.

Recommended prompt pattern:

```text
Read AGENTS.md and the section of docs/NOTION_PROJECT_PLAN.md for the current phase.
We are in phase <PX>. Branch: <feat/pX-name>.

Task:
<copy one group of tasks here>

Constraints:
- Follow AGENTS.md, including "Permissions and safety" (no apply/destroy, no cloud mutations).
- Follow the architecture in docs/technical_datasheet.pdf and the accepted ADRs.
- Do not depend on any ADR that is still Proposed.
- Do not change unrelated components.
- Do not invent credentials or cloud resources that do not exist.
- Keep the implementation minimal and production-like.

Before editing:
- identify the current state
- list files you expect to change
- identify dependencies/risks

After editing:
- run the narrowest relevant verification
- report changed files, exact commands and results
- list any manual AWS/Databricks steps still required

When the phase tasks are done:
- run the cleanup checklist from AGENTS.md
- push the branch and produce the PR title and body
- do not merge and do not start the next phase
```

For infrastructure tasks, use a plan-first approach: `terraform plan` is the agent's limit; Afonso applies after reviewing.
For source selection, stop and resolve the source decision before building source-specific ingestion code.

---

# 15. Definition of portfolio completion

The project is complete when all of the following are true:

- real data from the selected public sources is ingested into immutable raw storage (S3 raw for the MWAA batch source, Kinesis for the always-on sources);
- Bronze, Silver, Gold, Quarantine, and Snapshot layers exist where applicable;
- dbt transformations and tests are reproducible;
- the daily Airflow pipeline orchestrates the configured batch components;
- the always-on streaming path is demonstrated end to end (P4c foundation, P8b AISstream);
- the second ingestion strategy is demonstrated through Fivetran or explicitly documented as skipped;
- Unity Catalog governs the Databricks objects;
- Terraform represents the core infrastructure, including a separate streaming root;
- CI/CD runs checks and uses OIDC rather than long-lived AWS credentials;
- secrets are handled outside source code;
- business and data-quality dashboards exist;
- monitoring, cost control, and failure handling are documented;
- the source discovery agent proposes a real public source that is then integrated through the normal phase flow (P12);
- the README and architecture diagram describe the actual final state;
- screenshots/logs/examples provide evidence for the major portfolio claims.

---

# 16. Starting the replanned roadmap (2026-11-06)

The bootstrap and P1 to P4 are historical and complete. World Bank and FRED are retired; their code is removed in a
later dedicated chore, after the shared ingestion core is in place.

1. Review and merge the replan PR (`docs: replan around Earth-monitoring sources`).
2. Afonso accepts or amends ADR-008, ADR-010, ADR-011 and ADR-012.
3. Run the P4b spike for NASA FIRMS and save real samples under `tests/fixtures/nasa_firms_fires/`.
4. Build P4b (NASA FIRMS) end to end, including Bronze.
5. Build P4c in two steps: the always-on foundation (container, Kinesis, Structured Streaming) and then the EMSC, USGS, NOAA and GDACS producers, with one spike per source.
6. Move to P5 (dbt Silver + Gold) once NASA FIRMS and the four always-on sources reach Bronze.
7. Do not start Fivetran, AISstream, or CI/CD before the batch data contracts are understood.

Schedule the later chores explicitly in the PR/backlog: remove the World Bank/FRED code after the shared ingestion
core is extracted; rename the Supabase secrets in Terraform (plan only, Afonso applies); redraw
`docs/project-architecture.png`; update `docs/technical_datasheet.pdf`.

Done 2026-11-11: chore `chore/remove-legacy-sources` deleted the retired `world-bank` and `fred` Secrets Manager entries from the persistent stack (names stay reserved during the 30-day recovery window) and moved the `hello_world` DAG to the `databricks` variable.
