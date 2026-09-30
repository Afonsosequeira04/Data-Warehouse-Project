# Notion Implementation Plan - Cloud Data Platform

## Project outcome

Build and document a real-data, end-to-end cloud data platform that demonstrates:

`Real APIs + SaaS/DB source -> controlled ingestion -> S3/Databricks -> Bronze -> Silver -> Gold -> data quality -> BI`

with:

`Terraform + GitHub Actions/OIDC + Unity Catalog + Secrets Manager + monitoring + cost controls`

Revision note: this version adds a phase for the ephemeral MWAA environment, moves Terraform to the start of the
project (persistent + ephemeral stacks), turns the open technical questions into ADRs, and adds a branch -> cleanup -> PR
workflow. The old "P8 - Terraform" phase no longer exists: Terraform is built incrementally in P1 and P2, and reviewed in P11.

Fixed decisions: MWAA is used directly (no local Airflow) as an ephemeral environment created and destroyed with Terraform;
Terraform starts in P1; raw data, secrets and the budget live in a persistent stack that a destroy can never touch.
See `AGENTS.md` (D-001 to D-006) for the full list.

## Phase overview

| Phase | Name | Main outcome |
|---|---|---|
| P0 | Decisions and bootstrap | **DONE** — ADRs accepted, sources and business questions chosen, guardrails ready |
| P1 | Persistent foundation | Terraform persistent stack, S3 raw, IAM, secrets, budget, Unity Catalog |
| P2 | Ephemeral MWAA | Repeatable create/destroy of MWAA with a hello DAG |
| P3 | API 1 ingestion | World Bank -> S3 raw -> Bronze |
| P4 | API 2 ingestion | FRED -> S3 raw -> Bronze |
| P5 | dbt Silver + Gold | Models, tests, snapshots |
| P6 | Data quality + quarantine | Rejected records visible and explained |
| P7 | daily_pipeline | Full DAG running in an MWAA window |
| P8 | Fivetran ingestion path | Managed ingestion path (RDS PostgreSQL -> Fivetran -> Databricks) |
| P9 | CI/CD with OIDC | PR checks and merge-to-main deployment (persistent stack only) |
| P10 | AI/BI dashboards | Business and data-quality dashboards |
| P11 | Hardening | Security, cost, idempotency, docs, evidence |

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
| Phase | Select | P0 Decisions, P1 Foundation, P2 MWAA, P3 API 1, P4 API 2, P5 dbt, P6 Quality, P7 Pipeline, P8 Fivetran, P9 CI/CD, P10 BI, P11 Hardening |
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

Use this for source selection, Fivetran usage, database choice, incremental strategy, snapshot strategy, networking decisions, and anything else that changes architecture.

## Database C - Data Sources

Properties:

`Source | Type | Owner/Provider | API/Connector | Auth | Frequency | Grain | Expected Volume | Raw Path | Destination | Status | Notes`

Status values: Not selected, Shortlisted, Selected, Ready.
Do not mark a source "Ready" until its endpoint/connector, authentication approach, expected response shape, and destination are known.

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

### Repository bootstrap (OpenCode, first PR)

- [ ] Inspect the repo and confirm it only contains documentation.
- [ ] Add `.gitignore` (env files, Terraform state, dbt artifacts, profiles, caches).
- [ ] Create `docs/decisions/` with an ADR template and index.
- [ ] Create `docs/data-sources.md` (three rows, all `Not selected`) and `docs/business-questions.md` (empty template).
- [ ] Create ADR-001 to ADR-004 as `Proposed` (options and trade-offs only).

### Decisions (Afonso, with OpenCode shortlists)

- [x] Accept or amend ADR-001 (how Bronze is loaded and who runs it) — **Accepted: COPY INTO via SQL Warehouse**
- [x] Accept or amend ADR-002 (quarantine boundary) — **Accepted: Hybrid (ingestion structural, dbt semantic)**
- [x] Accept or amend ADR-003 (where dbt runs) — **Accepted: dbt from MWAA execution context against SQL Warehouse**
- [x] Accept or amend ADR-004 (MWAA ephemeral operating model) — **Accepted: GitHub Actions create/destroy, private subnets + NAT**
- [x] Accept ADR-005 (RDS PostgreSQL operational source for Fivetran) — **Accepted**
- [x] Define business questions the Gold layer and dashboard must answer, **before** choosing APIs — **BQ-001, BQ-002, BQ-003 Approved**
- [x] Shortlist and choose **API 1** — **World Bank Indicators API** (pagination, no auth)
- [x] Shortlist and choose **API 2** — **FRED Economic Series API** (API key auth, limit/offset pagination)
- [x] Choose the **SaaS/DB source** for Fivetran — **Amazon RDS PostgreSQL** (`macro_watchlist_db`)
- [x] Record each source in `docs/data-sources.md` and in the Data Sources database.
- [x] Define a rough data grain for each source.
- [x] Define target catalog and schemas in Unity Catalog — **Catalog: `dwh_dev`; Schemas: `bronze`, `silver`, `gold`, `quarantine`, `snapshots`, `raw_fivetran` (Fivetran destination schema prefix to be confirmed in P8)**
- [x] Define environment naming convention (`dev` and `prod` only if actually needed).

### Manual prerequisites (Afonso)

- [ ] AWS: MFA on the root account, an admin identity that is not root, and an **AWS Budget with alerts** created before anything billable.
- [ ] Databricks: confirm the workspace plan/type and that it supports a storage credential and an external location on S3
      plus a SQL Warehouse. If not, P1 changes and this must be resolved first.
- [ ] Fivetran: confirm whether the Databricks destination is available on the plan; otherwise mark P8 optional.

### Definition of Done

- ADR-001 to ADR-005 are `Accepted`.
- API 1 (World Bank Indicators), API 2 (FRED), and SaaS/DB (Amazon RDS PostgreSQL) are no longer placeholders.
- Data sources have expected schemas/grains documented in `docs/data-sources.md`.
- The Gold/dashboard questions (BQ-001, BQ-002, BQ-003) are defined and the chosen sources can answer them.
- Cost guardrails exist (AWS Budget $10/month with alerts at 50%, 80%, 100% actual and 100% forecasted).
- The Databricks workspace capability is confirmed.
- No implementation depends on an undocumented service.

---

# 2. P1 - Persistent foundation: Terraform + S3 + IAM + Unity Catalog

**Goal:** establish the minimum secure platform that never gets destroyed, and build it as code from the start.

### Terraform bootstrap

- [ ] Decide and document the Terraform state approach (remote S3 backend; native lockfile locking since DynamoDB is out of scope).
- [ ] Document how the state bucket itself is bootstrapped.
- [ ] Create `infra/terraform/aws/persistent` and `infra/terraform/databricks` with `fmt` / `validate` / `plan` passing.

### AWS tasks (persistent stack)

- [ ] Raw/landing S3 bucket: versioning, SSE-S3, public access blocked, `prevent_destroy`, no `force_destroy`.
- [ ] Separate S3 location (or bucket) for MWAA DAGs and `requirements.txt`, also persistent.
- [ ] Define the raw path convention and document it.
- [ ] IAM roles/policies with least privilege.
- [ ] Secrets Manager entries (names and structure only, no secret values in Git).
- [ ] AWS Budgets managed in Terraform (or the manual budget documented and imported).
- [ ] Resource tagging convention for cost attribution.
- [ ] Validate that no credentials are stored in Git.

**Note:** The approved RDS PostgreSQL source (`macro_watchlist_db`) is a later implementation task. When implemented, its Terraform representation should be added to the persistent stack. This is not part of P1 scope.

### Databricks / Unity Catalog tasks

- [ ] Confirm the Unity Catalog metastore / workspace relationship.
- [ ] Storage credential and IAM role, resolving the external-ID circular dependency (verify the current documented procedure).
- [ ] S3 external location.
- [ ] Target catalog `dwh_dev` and the `bronze`, `silver`, `gold`, `quarantine`, `snapshots`, `raw_fivetran` schemas (Fivetran destination schema prefix to be confirmed in P8).
- [ ] Baseline grants for pipeline, BI, and developer access.
- [ ] SQL Warehouse: smallest size, short auto-stop.
- [ ] Verify Databricks can read the intended S3 location without hard-coded cloud credentials.

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

# 4. P3 - World Bank ingestion: Python -> Airflow -> S3 -> Bronze

**Goal:** complete the first real ingestion path end to end.

Client logic is tested with `pytest` and recorded fixtures without MWAA running. The DAG run happens inside one planned MWAA window (see the P2 runbook).

### Tasks

- [ ] Create a source-specific API client for World Bank Indicators.
- [ ] Implement authentication/configuration through secrets or environment variables (no auth required for World Bank).
- [ ] Implement pagination (page + per_page).
- [ ] Implement rate-limit handling.
- [ ] Implement bounded retries with backoff.
- [ ] Validate response shape.
- [ ] Write raw JSON to the immutable S3 path (`s3://<bucket>/api/world_bank_indicators/ingest_date=YYYY-MM-DD/`).
- [ ] Generate a batch identifier.
- [ ] Include ingestion-date information.
- [ ] Add technical metadata for Bronze.
- [ ] Create the first Bronze Delta table using the mechanism accepted in ADR-001 (COPY INTO via SQL Warehouse).
- [ ] Test a successful run.
- [ ] Test an expected API/schema failure.
- [ ] Test a retry/idempotency scenario.

### Definition of Done

A real API call produces a dated raw object in S3 and a usable Bronze table, with metadata and a clear failure path.

### Evidence to save in Notion

- successful ingestion log/screenshot
- S3 object path
- Bronze table preview
- failure/retry example

---

# 5. P4 - FRED ingestion

**Goal:** prove the architecture handles more than one API shape.

### Tasks

- [ ] Build FRED client independently from World Bank client.
- [ ] Reuse common ingestion utilities only where genuinely useful.
- [ ] Handle FRED's pagination (limit + offset), rate limits (120 req/min), and API key auth.
- [ ] Write FRED raw payloads to its own S3 prefix (`s3://<bucket>/api/fred_economic_series/ingest_date=YYYY-MM-DD/`).
- [ ] Add FRED Bronze table (`<catalog>.bronze.fred_economic_series`).
- [ ] Add validation for source-specific fields.
- [ ] Test a bad payload/validation path.
- [ ] Confirm both APIs can coexist in the same daily pipeline without overwriting each other's raw data.

### Definition of Done

Two real APIs run through the same platform pattern while preserving source-specific logic and raw data.

---

# 6. P5 - dbt Silver + Gold + tests + snapshots

**Goal:** convert raw/Bronze data into analytics-ready data.

## Silver / staging

- [ ] Configure dbt Databricks adapter (connection via environment variables, no committed `profiles.yml` with real values; run location per ADR-003).
- [ ] Create source definitions.
- [ ] Create staging models.
- [ ] Standardize names and data types.
- [ ] Deduplicate records where required.
- [ ] Normalize dates, identifiers, and categorical fields.
- [ ] Implement business rules that belong in transformation, not ingestion.

## Gold / marts

- [ ] Decide the analytical grain of each fact table.
- [ ] Create dimension models.
- [ ] Create fact models.
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

- [ ] Identify an entity whose attribute history is meaningful.
- [ ] Implement a dbt snapshot using SCD2 semantics.
- [ ] Verify historical versions can be reconstructed.

### Definition of Done

`Bronze -> dbt Silver -> dbt Gold` builds successfully, quality tests are meaningful, and at least one historical change is represented through a snapshot.

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

**Goal:** orchestrate the full platform with the MWAA environment proven in P2.

The environment is created for planned windows only. Each window: apply the ephemeral stack, run/observe the DAG, capture evidence, destroy.

### Tasks

- [ ] Add API ingestion tasks (API 1, API 2).
- [ ] Add S3 availability/check tasks.
- [ ] Add the Bronze load step (mechanism per ADR-001).
- [ ] Add Fivetran trigger/wait steps only when Fivetran is enabled.
- [ ] Add the dbt build step (runner per ADR-003).
- [ ] Add the dbt test / data-quality step.
- [ ] Add the final mart-availability check.
- [ ] Configure retries, timeouts, and failure visibility.
- [ ] Test a full successful run inside one MWAA window.
- [ ] Test a controlled failure and recovery inside a window.
- [ ] Destroy the environment and confirm the persistent stack is intact.

### Definition of Done

One Airflow DAG can run the full configured pipeline with clear dependencies, retries, and observable outcomes,
and the environment can be destroyed and rebuilt without losing the ability to run it.

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
Amazon RDS PostgreSQL
-> Fivetran
-> Databricks (schema: raw_fivetran, prefix to be confirmed in P8)
```

Fivetran is the intended second ingestion strategy, but can only be formally skipped later if the actual Fivetran plan/account does not support the Databricks destination or another documented blocker exists.

### Tasks

- [ ] Create/prepare the RDS PostgreSQL source (`macro_watchlist_db`) in the persistent stack.
- [ ] Seed `macro_watchlist_db` with `watchlist_country`, `watchlist_indicator`, `alert_rule` tables.
- [ ] Configure the Fivetran PostgreSQL connector.
- [ ] Configure the Databricks destination (verify Fivetran plan supports it).
- [ ] Define `raw_fivetran` convention: `dwh_dev.raw_fivetran.<table>` (Fivetran destination schema prefix to be confirmed in P8; Unity Catalog uses three-level naming: catalog.schema.table).
- [ ] Validate initial synchronization.
- [ ] Validate incremental synchronization (Query-Based using `xmin`).
- [ ] Integrate trigger/wait logic with Airflow.
- [ ] Add downstream dbt staging for the ingested data.
- [ ] Verify core pipeline remains functional if Fivetran is disabled.

### Definition of Done

Fivetran demonstrates a managed ingestion path while the core AWS + Databricks + dbt pipeline remains independent.

Because RDS is a persistent resource, note that its later Terraform implementation should use the project's persistent infrastructure strategy, while the source-specific integration work belongs to P8.

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
- [ ] Terraform plan (persistent stack, ephemeral stack, Databricks).
- [ ] DAG import test.

### Main workflow

- [ ] Establish protected `main` workflow.
- [ ] Authenticate to AWS with OIDC.
- [ ] Deploy Terraform for the persistent stack and Databricks only. Merge to `main` must never create the ephemeral (MWAA) stack.
- [ ] Deploy Databricks changes.
- [ ] Run `dbt build`.
- [ ] Surface failures clearly.

### Definition of Done

A pull request produces automated verification, and merge-to-main performs the documented deployment path without long-lived AWS keys.

---

# 11. P10 - Databricks AI/BI dashboards

**Goal:** make the result understandable to a business user and a data engineer.

## Business dashboard

Use metrics appropriate to the selected APIs, for example:

- revenue/value over time
- breakdown by country/product/category
- units/counts
- customer counts
- average value per transaction/order

Do not force metrics that do not make sense for the final sources.

## Data quality dashboard

Include:

- pipeline status
- latest successful batch
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
- [ ] Confirm least-privilege IAM.
- [ ] Confirm OIDC workflow.
- [ ] Confirm no raw S3 overwrite behavior.
- [ ] Confirm retry/idempotency behavior.
- [ ] Confirm failure alerts/logging are useful.
- [ ] Confirm quarantine behavior.
- [ ] Confirm dbt tests cover the critical models.
- [ ] Confirm snapshot history works.
- [ ] Review cloud cost controls, including a check that nothing billable is left running.
- [ ] Terraform completeness review: anything created by hand is either in code or documented as manual.
- [ ] Full rebuild test: destroy and recreate the ephemeral stack from a clean checkout and run the DAG.
- [ ] Review dependency versions and remove unused packages.
- [ ] Add architecture diagram showing the final implementation, not only the planned state.
- [ ] Update README with a reproducible quickstart.
- [ ] Add a "How data flows" section.
- [ ] Add a "Why these technologies" section.
- [ ] Add a "Trade-offs and limitations" section.
- [ ] Add screenshots/evidence to the portfolio documentation.

### Definition of Done

Someone unfamiliar with the project can clone it, read the documentation, understand the architecture/trade-offs, and see evidence that each major component was actually used.

---

# 13. Suggested Notion milestones

Create milestone pages or checkboxes for these outcomes:

- [ ] **M1 - Architecture locked** (P0)
- [ ] **M2 - S3 + Unity Catalog working, built with Terraform** (P1)
- [ ] **M3 - MWAA create/run/destroy cycle proven** (P2)
- [ ] **M4 - First API reaches Bronze** (P3)
- [ ] **M5 - Two APIs reach Bronze** (P4)
- [ ] **M6 - Silver + Gold + tests working** (P5)
- [ ] **M7 - Quarantine path working** (P6)
- [ ] **M8 - Daily Airflow pipeline working** (P7)
- [ ] **M9 - Fivetran path working or formally skipped with a documented reason** (P8)
- [ ] **M10 - CI/CD with OIDC working** (P9)
- [ ] **M11 - BI + data-quality dashboards working** (P10)
- [ ] **M12 - Portfolio hardening complete** (P11)

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
- Follow the architecture in docs/technical_datasheet.pdf.
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

- real API data is ingested into immutable S3 raw storage;
- Bronze, Silver, Gold, Quarantine, and Snapshot layers exist where applicable;
- dbt transformations and tests are reproducible;
- the daily Airflow pipeline orchestrates the configured components;
- the second ingestion strategy is demonstrated through Fivetran or explicitly documented as skipped;
- Unity Catalog governs the Databricks objects;
- Terraform represents the core infrastructure;
- CI/CD runs checks and uses OIDC rather than long-lived AWS credentials;
- secrets are handled outside source code;
- business and data-quality dashboards exist;
- monitoring, cost control, and failure handling are documented;
- the README and architecture diagram describe the actual final state;
- screenshots/logs/examples provide evidence for the major portfolio claims.

---

# 16. First implementation session

Start here, in this order:

1. Commit the new `AGENTS.md` and this plan to `main` (the only direct commit).
2. Do the manual prerequisites listed in P0 (AWS Budget, MFA, non-root admin, Databricks workspace check).
3. Run the bootstrap prompt in OpenCode on branch `chore/p0-bootstrap`. Review the PR and merge.
4. Answer the ADR questions and accept ADR-001 to ADR-005 (all now Accepted).
5. Write the business questions (BQ-001, BQ-002, BQ-003 now Approved), then select sources.
6. Fill `docs/data-sources.md` and the Notion databases (World Bank, FRED, RDS PostgreSQL now Selected).
7. When the P0 Definition of Done is met, update "Current phase" and move to P1.
8. Do not start MWAA, Fivetran, or CI/CD before the data contracts for the first API are understood.

**P0 is complete when all ADRs are Accepted, sources are Selected, business questions are Approved, and the documentation reflects the final architecture.**
