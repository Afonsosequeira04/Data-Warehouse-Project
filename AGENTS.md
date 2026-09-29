# Cloud Data Platform - OpenCode Project Instructions

## Mission

This repository implements an end-to-end cloud data platform using real external data.
The target architecture is AWS + Databricks with Python/Airflow API ingestion, S3 immutable raw storage,
Databricks Delta Lake + Unity Catalog, dbt transformations, optional Fivetran ingestion, Terraform IaC,
GitHub Actions CI/CD with OIDC, and Databricks AI/BI dashboards.

The project is a data-engineering portfolio project. Prefer a small, understandable production-style solution
over adding services just to make the architecture look larger.

## Source of truth

Use these files as the primary project references:

- `README.md` - public project overview and high-level setup.
- `docs/technical_datasheet.pdf` - architecture, technology choices, constraints, and build order.
- `docs/architecture1.png` - visual architecture reference.
- `NOTION_PROJECT_PLAN.md` - implementation roadmap and task breakdown.
- `AGENTS.md` - OpenCode working rules.

When an implementation detail is not specified, choose the simplest option that preserves the documented architecture.
Do not silently change the architecture. Record meaningful changes as decisions in the project documentation.

## Current repository state

The repository may begin as a design/scaffold rather than a fully implemented platform. Do not claim that a
component exists merely because it appears in the datasheet or architecture diagram.
Before modifying an area, inspect the actual files and verify its current state.

The current datasheet intentionally contains placeholders such as `<API 1>`, `<API 2>`, and `<SaaS/DB>`.
Never invent that these placeholders have already been selected or configured. Keep them explicit until the project
makes a concrete source decision.

## Architecture

### End-to-end flow

```text
Public API 1 ─┐
              ├─> MWAA / Airflow ─> S3 immutable raw ─> Databricks Bronze
Public API 2 ─┘                                      └─> Quarantine for rejected records

SaaS / Database ─> Fivetran ─> Databricks Raw Fivetran
                                      │
                                      └─> dbt staging (Silver) ─> dbt marts (Gold) ─> AI/BI

GitHub ─> GitHub Actions (OIDC) ─> Terraform / deployment / dbt checks
```

### Core layers

- **S3 Raw/Landing:** immutable source payloads. API ingestions create new objects per ingestion date; do not overwrite raw data.
- **Bronze:** data kept close to source plus technical metadata: `_batch_id`, `_ingested_at`, `_source_file`, `_source_system`, `_batch_date`.
- **Silver:** parsing, types, deduplication, normalization, and business rules. Implement this primarily with dbt staging models.
- **Gold:** analytical dimensions and facts in dbt marts.
- **Quarantine:** records rejected by validation rules; retain enough metadata to diagnose the rejection.
- **Snapshots:** dbt snapshot history using SCD2 where historical tracking is required.

### Ingestion responsibilities

- Python + Airflow owns API extraction, pagination, rate limiting, retries, schema validation, and writing raw JSON to S3.
- dbt does **not** own the main API ingestion. dbt starts at Bronze/Raw and transforms toward Silver/Gold.
- Fivetran is an additional ingestion path, not a prerequisite for the core platform.
- Airflow may coordinate Fivetran through its API, including triggering and waiting for synchronization, but Fivetran remains responsible for the connector sync itself.

## Non-negotiable architecture rules

1. Use real external sources for the production pipeline. Test fixtures may be synthetic and must live under test-oriented paths.
2. Do not replace S3 raw storage with local files for the production flow.
3. Do not overwrite immutable raw S3 objects. Use an ingestion-date-based path.
4. Do not introduce AWS services that are outside the documented scope unless a concrete requirement justifies them.
5. Prefer S3, IAM, MWAA, VPC/networking, CloudWatch Logs, Secrets Manager, and AWS Budgets as the essential AWS footprint.
6. KMS, SNS, EventBridge, and CloudTrail are optional only when there is a demonstrated need.
7. Redshift, Glue, EMR, Athena, Kinesis, Lambda, DynamoDB, ECR, ECS, and RDS are out of scope unless the architecture is explicitly revised.
8. Secrets and credentials must never be committed to Git. Use AWS Secrets Manager or the appropriate runtime secret mechanism.
9. GitHub authentication to AWS should use OIDC. Do not add long-lived AWS access keys to GitHub Actions.
10. Keep Fivetran optional so the platform remains functional without it if cost or plan constraints make it unavailable.
11. Preserve lineage and governance through Unity Catalog; do not introduce a separate lineage system without a specific requirement.
12. Keep transformations in dbt models/macros/tests rather than duplicating business logic across Python, DAGs, and SQL.

## Repository structure

Prefer this structure unless there is a strong reason to change it:

```text
cloud-data-platform/
├── ingestion/
│   ├── api/
│   └── fivetran/
├── orchestration/
│   └── dags/
├── dbt_project/
│   ├── models/
│   ├── snapshots/
│   ├── tests/
│   └── macros/
├── infra/
│   └── terraform/
│       ├── aws/
│       └── databricks/
├── docs/
├── tests/
├── .github/
│   └── workflows/
├── README.md
├── AGENTS.md
└── NOTION_PROJECT_PLAN.md
```

Keep source-specific code isolated. Shared utilities are acceptable only when they are genuinely reusable.
Avoid creating large generic frameworks for a portfolio project.

## API ingestion conventions

For each API:

- Separate API/client concerns from orchestration concerns.
- Handle pagination when the source supports it.
- Respect documented rate limits and implement bounded retries with backoff where appropriate.
- Validate the response shape before writing it as a successful ingestion.
- Preserve the raw response as JSON as close to the source as practical.
- Attach or derive the required batch/ingestion metadata downstream.
- Make reruns predictable: an Airflow retry must not corrupt the raw layer or silently overwrite a previous batch.
- Log useful operational metadata without logging credentials or sensitive payloads unnecessarily.
- Put source-specific assumptions in code comments or documentation, not hidden in magic constants.

Recommended raw path pattern:

```text
s3://<bucket>/api/<source_name>/ingest_date=YYYY-MM-DD/<object>.json
```

## Airflow / MWAA conventions

DAG files should describe orchestration, not contain large blocks of business logic.
Prefer small tasks with clear inputs/outputs and explicit dependencies.

The intended main DAG flow is:

```text
API ingestion
  > check S3
  > trigger / wait for Fivetran sync (when enabled)
  > validate raw/landing availability
  > dbt build
  > dbt test / data quality checks
  > confirm marts are available
```

Use retries, timeouts, and clear failure states. Avoid infinite polling or unbounded retries.
When a provider API requires a long wait, use an Airflow-friendly sensor/deferrable pattern where appropriate rather than blocking a worker unnecessarily.

## dbt conventions

- Keep staging models focused on source cleanup, typing, normalization, and reusable business rules.
- Keep marts focused on analytics-ready dimensions/facts and stable business definitions.
- Add tests for primary keys, relationships, accepted values, and non-null requirements where they are meaningful.
- Add freshness/recency checks where they provide operational value.
- Use snapshots for entities whose historical changes matter and document the SCD2 key/change semantics.
- Prefer incremental models only when data volume or processing cost justifies them; do not add incremental complexity automatically.
- Avoid duplicating the same metric definition in several models.
- Keep model names, column names, and tests predictable and consistent.
- Document important business assumptions in dbt documentation or project docs.

## Unity Catalog conventions

Use the documented structure:

```text
<catalog>.<schema>.<table>
```

The intended schema groups are:

- `bronze`
- `silver`
- `gold`
- `quarantine`
- `snapshots`

Use permissions that follow least privilege: pipeline identities need write access where necessary, BI consumers need read access, and developers receive only the access needed for development.
S3 access should use Unity Catalog storage credentials and external locations rather than ad-hoc credentials in code.

## Terraform conventions

- Keep AWS and Databricks resources separated under `infra/terraform/aws` and `infra/terraform/databricks`.
- Prefer small, composable modules/resources over one huge Terraform file.
- Use variables for environment-specific values and avoid hard-coded account IDs, ARNs, secrets, or personal paths.
- Keep Terraform state management explicit and safe; never commit local state, plans, provider caches, or credentials.
- Run formatting and validation before considering an infrastructure task complete.
- `terraform plan` is verification; do not apply infrastructure casually when the task only asks for a plan or code change.

## GitHub Actions conventions

Expected PR checks include, when the relevant files exist:

- tests
- `dbt parse`
- linting
- gitleaks or equivalent secret scanning
- `terraform plan`

Expected deployment behavior on merge to `main`, once infrastructure is ready:

- Terraform apply
- Databricks deployment
- `dbt build`

Use OIDC for AWS authentication. Never create a workflow that depends on a long-lived AWS secret unless the documented architecture has been explicitly changed.

## Secrets and configuration

Never hard-code:

- API keys
- AWS access keys
- Databricks tokens
- Fivetran credentials
- database passwords
- account IDs when they should be variables

Use environment variables, AWS Secrets Manager, GitHub OIDC/secret mechanisms, or the native secret mechanism of the target platform.
Provide safe examples using placeholders only.

## Data quality and quarantine

Data quality is a first-class output of the platform, not an afterthought.

Validation failures should be observable and, when appropriate, diverted to Quarantine instead of being silently dropped.
Include enough context to answer:

- which source produced the record?
- which batch produced it?
- why was it rejected?
- when was it rejected?

Do not silently coerce bad data into plausible values just to make a test pass.

## Monitoring and cost control

Use Airflow, CloudWatch Logs, and Databricks monitoring for operational visibility.
The portfolio should demonstrate awareness of cloud cost, especially for MWAA and the Databricks SQL Warehouse.

AWS Budgets should be established early. Avoid leaving expensive compute running without a reason.
When adding a managed service, document why it is needed and what cost/operational trade-off it introduces.

## Code quality

- Prefer readable, explicit code over clever abstractions.
- Keep functions small and testable.
- Use type hints for new Python code where practical.
- Fail loudly on configuration errors and invalid credentials rather than silently falling back.
- Preserve existing conventions when the repository already has them.
- Do not reformat or rewrite unrelated files.
- Do not add dependencies unless an existing dependency cannot reasonably solve the problem.
- Do not generate placeholder implementations that look production-ready without clearly marking them as scaffolding.

## Documentation rules

Update documentation when architecture, source choices, operational behavior, or setup steps change.
At minimum, keep `README.md`, the technical datasheet/architecture references, and this file consistent enough that a new contributor can understand the actual state of the platform.

When a decision changes, document:

- the old assumption
- the new decision
- why it changed
- impact on architecture/cost/operations

## Verification protocol

Before declaring a task complete:

1. Inspect the changed files and confirm the implementation matches the requested scope.
2. Run the narrowest relevant verification first.
3. Run broader checks when the change crosses component boundaries.
4. Report commands run and whether they passed or failed.
5. Never claim a cloud deployment, API sync, Terraform apply, or external integration succeeded unless it was actually executed and verified.

Typical checks, only when the corresponding project components exist:

```bash
python -m compileall ingestion orchestration tests
pytest

cd dbt_project
 dbt deps
 dbt parse
 dbt build
 dbt test

cd ../infra/terraform/aws
terraform fmt -check
terraform init
terraform validate
terraform plan

cd ../databricks
terraform fmt -check
terraform init
terraform validate
terraform plan
```

Do not blindly run every command for every change. Match verification to the files and behavior changed.

## OpenCode workflow

For implementation tasks, follow this sequence:

### 1. Understand

Read `AGENTS.md`, then inspect the relevant repository files and `README.md` / architecture docs as needed.
Do not start editing from the task description alone.

### 2. Plan

For changes spanning multiple components, first state a compact implementation plan and identify dependencies.
For small, local fixes, proceed directly after inspecting the target code.

### 3. Implement minimally

Make the smallest coherent change that satisfies the task.
Do not opportunistically refactor unrelated code.
Do not introduce new infrastructure services unless required.

### 4. Verify

Run focused tests/checks and inspect their output.
For infrastructure, prefer `fmt`, `validate`, and `plan` unless an actual apply is explicitly requested.

### 5. Report

Finish with:

- what changed
- files touched
- verification performed
- any remaining manual/cloud steps
- any assumptions or unresolved decisions

## Important project decisions

The current technical datasheet defines these decisions:

- Fivetran is optional, not mandatory.
- APIs use S3 as immutable raw storage; Fivetran writes directly to Databricks.
- KMS is not required at project start; SSE-S3 is sufficient for the portfolio scope.
- AWS Budgets should exist from the beginning.
- MWAA and the SQL Warehouse are the major cost-sensitive components.
- The core platform should remain functional without Fivetran.

Do not reverse these decisions casually. If the project needs to change one, record the reason and update the relevant documentation.
