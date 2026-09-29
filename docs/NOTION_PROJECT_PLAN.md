# Notion Implementation Plan - Cloud Data Platform

## Project outcome

Build and document a real-data, end-to-end cloud data platform that demonstrates:

`Real APIs + SaaS/DB source -> controlled ingestion -> S3/Databricks -> Bronze -> Silver -> Gold -> data quality -> BI`

with:

`Terraform + GitHub Actions/OIDC + Unity Catalog + Secrets Manager + monitoring + cost controls`

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
| Phase | Select | P0 Decisions, P1 Foundation, P2 API, P3 dbt, P4 Orchestration, P5 Fivetran, P6 IaC, P7 CI/CD, P8 BI, P9 Hardening |
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

`Decision | Status | Date | Area | Context | Decision | Alternatives | Consequences`

Use this for source selection, Fivetran usage, database choice, incremental strategy, snapshot strategy, networking decisions, and anything else that changes architecture.

## Database C - Data Sources

Properties:

`Source | Type | Owner/Provider | API/Connector | Auth | Frequency | Grain | Expected Volume | Raw Path | Destination | Status | Notes`

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

---

# 1. P0 - Decisions and project bootstrap

**Goal:** remove ambiguity before writing implementation code.

### Tasks

- [ ] Confirm final architecture against `docs/technical_datasheet.pdf`.
- [ ] Choose concrete **API 1**.
- [ ] Choose concrete **API 2** with a meaningfully different response structure.
- [ ] Choose concrete **SaaS/DB source** for Fivetran.
- [ ] Record each source in the Data Sources database.
- [ ] Define the business questions the Gold layer and dashboard must answer.
- [ ] Define a rough data grain for each source.
- [ ] Define target catalog and schemas in Unity Catalog.
- [ ] Define environment naming convention (for example `dev` and `prod` only if actually needed).
- [ ] Create the AWS Budget before running expensive infrastructure.
- [ ] Confirm the Databricks workspace and SQL Warehouse approach.
- [ ] Confirm whether Fivetran is financially/technically available; otherwise mark Phase P5 optional.
- [ ] Create a first architecture decision log entry.

### Definition of Done

- API 1, API 2, and SaaS/DB are no longer placeholders.
- Data sources have expected schemas/grains documented.
- Cost guardrails exist.
- The first Gold/dashboard questions are defined.
- No implementation depends on an undocumented service.

---

# 2. P1 - AWS + S3 + IAM + Unity Catalog foundation

**Goal:** establish the minimum secure platform on which the pipeline can run.

### AWS tasks

- [ ] Create the S3 landing/raw bucket.
- [ ] Enable S3 versioning.
- [ ] Configure SSE-S3 encryption.
- [ ] Define the project raw path convention.
- [ ] Create IAM roles/policies using least privilege.
- [ ] Create the minimum networking needed by MWAA/Databricks access.
- [ ] Configure CloudWatch logging where required.
- [ ] Configure Secrets Manager placeholders/secrets.
- [ ] Validate that no credentials are stored in Git.

### Databricks / Unity Catalog tasks

- [ ] Configure the Unity Catalog metastore/workspace relationship.
- [ ] Create the target catalog.
- [ ] Create `bronze`, `silver`, `gold`, `quarantine`, and `snapshots` schemas.
- [ ] Create a storage credential.
- [ ] Create the S3 external location.
- [ ] Apply baseline grants for pipeline, BI, and developer access.
- [ ] Verify that Databricks can read the intended S3 location without hard-coded cloud credentials.

### Definition of Done

- S3 exists and follows the immutable raw design.
- Unity Catalog can govern the target schemas.
- Access works with least privilege.
- A small end-to-end smoke test can prove S3 -> Databricks connectivity.

---

# 3. P2 - API 1 ingestion: Python -> Airflow -> S3 -> Bronze

**Goal:** complete the first real ingestion path end to end.

### Tasks

- [ ] Create a source-specific API client.
- [ ] Implement authentication/configuration through secrets or environment variables.
- [ ] Implement pagination if required.
- [ ] Implement rate-limit handling.
- [ ] Implement bounded retries with backoff.
- [ ] Validate response shape.
- [ ] Write raw JSON to the immutable S3 path.
- [ ] Generate a batch identifier.
- [ ] Include ingestion-date information.
- [ ] Add technical metadata for Bronze.
- [ ] Create the first Bronze Delta table.
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

# 4. P3 - API 2 ingestion

**Goal:** prove the architecture handles more than one API shape.

### Tasks

- [ ] Build API 2 client independently from API 1.
- [ ] Reuse common ingestion utilities only where genuinely useful.
- [ ] Handle the source's own pagination/rate-limit/schema rules.
- [ ] Write API 2 raw payloads to its own S3 prefix.
- [ ] Add API 2 Bronze table.
- [ ] Add validation for source-specific fields.
- [ ] Test a bad payload/validation path.
- [ ] Confirm both APIs can coexist in the same daily pipeline without overwriting each other's raw data.

### Definition of Done

Two real APIs run through the same platform pattern while preserving source-specific logic and raw data.

---

# 5. P4 - dbt Silver + Gold + tests + snapshots

**Goal:** convert raw/Bronze data into analytics-ready data.

## Silver / staging

- [ ] Configure dbt Databricks adapter.
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

# 6. P5 - Data quality + quarantine

**Goal:** demonstrate what happens when data is bad instead of silently accepting or dropping it.

### Tasks

- [ ] Define which records are invalid vs merely incomplete.
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

# 7. P6 - MWAA + daily_pipeline

**Goal:** orchestrate the platform with managed Airflow.

### Tasks

- [ ] Provision/configure MWAA.
- [ ] Upload DAGs and `requirements.txt` to the correct S3 location.
- [ ] Configure required Airflow connections/variables using safe secret handling.
- [ ] Implement `daily_pipeline`.
- [ ] Add API ingestion tasks.
- [ ] Add S3 availability/check tasks.
- [ ] Add Fivetran trigger/wait steps only when Fivetran is enabled.
- [ ] Add dbt build step.
- [ ] Add dbt test/data-quality step.
- [ ] Add final mart-availability check.
- [ ] Configure retries, timeouts, and failure visibility.
- [ ] Test a full successful run.
- [ ] Test a controlled failure and recovery.

### Definition of Done

One Airflow DAG can run the full configured pipeline with clear dependencies, retries, and observable outcomes.

### Evidence to save

- DAG graph
- successful run screenshot
- failed/recovered task screenshot
- CloudWatch log sample

---

# 8. P7 - Fivetran ingestion path (optional but valuable)

**Goal:** demonstrate a second ingestion strategy without making the entire platform depend on Fivetran.

### Tasks

- [ ] Create/confirm the real SaaS/DB source.
- [ ] Configure the Fivetran connector.
- [ ] Configure the Databricks destination if the selected Fivetran plan supports it.
- [ ] Define the target `raw_fivetran` area/table convention.
- [ ] Validate direct write into Databricks.
- [ ] Integrate trigger/wait logic with Airflow.
- [ ] Validate the sync state from Airflow.
- [ ] Add downstream dbt staging for the ingested data.
- [ ] Verify the pipeline can still function without Fivetran when the connector is disabled.

### Definition of Done

Fivetran demonstrates a managed ingestion path while the core AWS + Databricks + dbt pipeline remains independent.

---

# 9. P8 - Terraform: AWS + Databricks

**Goal:** make infrastructure reproducible.

### AWS Terraform tasks

- [ ] Define providers and backend/state approach.
- [ ] Create S3 resources.
- [ ] Create IAM roles/policies.
- [ ] Define MWAA resources.
- [ ] Define required networking.
- [ ] Define CloudWatch logging resources/configuration where appropriate.
- [ ] Define Secrets Manager resources/configuration without embedding secret values.
- [ ] Define AWS Budgets.
- [ ] Run `terraform fmt`.
- [ ] Run `terraform validate`.
- [ ] Run `terraform plan`.

### Databricks Terraform tasks

- [ ] Configure the Databricks provider.
- [ ] Define catalogs/schemas.
- [ ] Define storage credentials/external locations.
- [ ] Define grants.
- [ ] Define SQL Warehouse resources if managed through Terraform.
- [ ] Run formatting, validation, and plan.

### Definition of Done

The key platform resources can be recreated from version-controlled Terraform without hard-coded credentials.

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
- [ ] Terraform plan.

### Main workflow

- [ ] Establish protected `main` workflow.
- [ ] Authenticate to AWS with OIDC.
- [ ] Deploy Terraform.
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
- [ ] Review cloud cost controls.
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

- [ ] **M1 - Architecture locked**
- [ ] **M2 - S3 + Unity Catalog working**
- [ ] **M3 - First API reaches Bronze**
- [ ] **M4 - Two APIs reach Bronze**
- [ ] **M5 - Silver + Gold + tests working**
- [ ] **M6 - Daily Airflow pipeline working**
- [ ] **M7 - Fivetran path working or formally skipped with a documented reason**
- [ ] **M8 - Terraform reproduces infrastructure**
- [ ] **M9 - CI/CD with OIDC working**
- [ ] **M10 - BI + data-quality dashboards working**
- [ ] **M11 - Portfolio hardening complete**

---

# 14. OpenCode execution style

Do not give OpenCode the entire roadmap as one giant implementation request.
Use one phase or one small group of dependent tasks at a time.

Recommended pattern for each task:

```text
Read AGENTS.md and the files relevant to this task.

Task:
<copy one Notion task here>

Constraints:
- Follow the architecture in docs/technical_datasheet.pdf.
- Do not change unrelated components.
- Do not invent credentials or cloud resources that do not exist.
- Keep the implementation minimal and production-like.

Before editing:
- identify the current state
- list files you expect to change
- identify dependencies/risks

After editing:
- run the narrowest relevant verification
- report changed files
- report exact commands and results
- list any manual AWS/Databricks steps still required
```

For infrastructure tasks, use a plan-first approach and prefer `terraform plan` over apply until the configuration is reviewed.
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

1. Fill the Data Sources database with concrete API 1, API 2, and SaaS/DB choices.
2. Fill the Architecture Decisions database with the source choices and the Fivetran decision.
3. Create the P0 tasks in the Tasks database.
4. Complete P1 only after P0 is locked.
5. Do not start MWAA, Fivetran, or CI/CD before the local/data contracts for the first API are understood.
