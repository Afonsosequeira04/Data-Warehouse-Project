# Cloud Data Platform - OpenCode Project Instructions

## Mission

This repository implements an end-to-end cloud data platform using real external data.

The target architecture is AWS + Databricks with Python/Airflow API ingestion, S3 immutable raw storage,
Databricks Delta Lake + Unity Catalog, dbt transformations, optional Fivetran ingestion, Terraform IaC,
GitHub Actions CI/CD with OIDC, and Databricks AI/BI dashboards.

The project is a data-engineering portfolio project. Prefer a small, understandable production-style solution
over adding services just to make the architecture look larger.

## Current phase

```
Current phase : P0 - Decisions and project bootstrap
Status        : in progress
Last completed: none
Next phase    : P1 - Persistent foundation (Terraform + S3 + IAM + Unity Catalog)
```

Rules for this block:

- Work only on the current phase. If a task belongs to a later phase, say so and stop instead of doing it early.
- This block is updated as the last commit of the phase's PR, so merging the PR advances the project.
- Never advance the phase yourself if the phase's Definition of Done (in `docs/NOTION_PROJECT_PLAN.md`) is not met.
  If it is only partly met, keep the phase and list what is missing in the PR.

## How Afonso starts work

- "começa a fase atual" / "continua": work on the phase in "Current phase".
- "começa a fase N": valid only if N is the current phase. If N is a later phase, say so and stop.
  If N is an earlier phase, ask before doing anything. Never edit the "Current phase" block to make N valid.
- Read only the section of `docs/NOTION_PROJECT_PLAN.md` for that phase, plus the ADRs it references.
  Do not read or work on other phases.
- Before editing, print: the current repo state, the files you expect to touch, and any open ADRs or decisions
  that block you. Wait for Afonso's OK.
- P0 special case: OpenCode only does "Repository bootstrap (OpenCode, first PR)" and may draft Proposed ADRs and
  source shortlists on request. "Decisions" and "Manual prerequisites" belong to Afonso. Do not do them and do not
  mark them as done. The P0 bootstrap PR does not advance "Current phase"; Afonso advances it once the P0
  Definition of Done is met.

## Working language

- Talk to Afonso in European Portuguese in chat.
- Write everything that lands in the repository (code, comments, commit messages, docs, ADRs, PR text) in English.

## Source of truth

Use these files as the primary project references:

- `README.md` - public project overview and high-level setup.
- `docs/technical_datasheet.pdf` - architecture, technology choices, constraints, and build order.
- `docs/architecture1.png` - visual architecture reference.
- `docs/NOTION_PROJECT_PLAN.md` - implementation roadmap, phases and Definition of Done. (Not in the repo root.)
- `docs/decisions/` - Architecture Decision Records (ADRs). Decisions live here, not only in Notion,
  because OpenCode can only see the repository.
- `docs/data-sources.md` - the concrete data sources and their status.
- `AGENTS.md` - OpenCode working rules (this file).

Notion is Afonso's tracking tool; it mirrors these files but is never the source of truth.

When an implementation detail is not specified, choose the simplest option that preserves the documented architecture.
Do not silently change the architecture. Record meaningful changes as decisions (see "Documentation rules").

## Current repository state

The repository may begin as a design/scaffold rather than a fully implemented platform. Do not claim that a
component exists merely because it appears in the datasheet or architecture diagram.

Before modifying an area, inspect the actual files and verify its current state.

At the time of writing the repository contains documentation only: no code, no Terraform, no dbt project,
no `.gitignore`, no dependency files. Verify this rather than trusting this paragraph.

The datasheet and README intentionally contain placeholders such as `<API 1>`, `<API 2>`, and `<SaaS/DB>`.
Never invent that these placeholders have already been selected or configured. Keep them explicit until the
project makes a concrete source decision, recorded in `docs/data-sources.md` with status `Selected`.
Only then update the README rows.

## Decisions already taken

These are settled. Do not reverse them casually; if one must change, follow the change process in "Documentation rules".

| ID | Decision |
| --- | --- |
| D-001 | Fivetran is optional, not mandatory. The core platform must work without it. |
| D-002 | APIs use S3 as immutable raw storage; Fivetran writes directly to Databricks. |
| D-003 | KMS is not required at project start; SSE-S3 is sufficient for the portfolio scope. |
| D-004 | AWS Budgets exist from the beginning, before any expensive resource. |
| D-005 | MWAA is used directly. There is no local Airflow / Docker Compose orchestration in this project. MWAA is treated as an ephemeral environment: created for a work window with Terraform and destroyed afterwards. |
| D-006 | Terraform starts in P1, not at the end. AWS infrastructure is split into a persistent stack (survives destroys) and an ephemeral stack (MWAA and its networking). |

D-005 and D-006 refine the datasheet: the datasheet's "shut resources down when not in use" is implemented
by destroying the ephemeral stack, because MWAA cannot be paused. The datasheet's flat `infra/terraform/aws/`
becomes `aws/persistent/` and `aws/ephemeral/`.

## Open decisions (ADRs)

These are unresolved. Do not implement code that depends on an open ADR. Present options and trade-offs,
then wait for Afonso to accept one.

| ADR | Question | Status |
| --- | --- | --- |
| ADR-001 | How is Bronze loaded from raw JSON in S3 (who runs it, which mechanism), given a SQL Warehouse and no cluster? | Proposed |
| ADR-002 | Where is the quarantine boundary: file/schema level at ingestion, row level in dbt, or both? | Proposed |
| ADR-003 | Where does dbt run in the daily DAG (inside MWAA, external runner, Databricks job)? | Proposed |
| ADR-004 | MWAA operating model: creation/destruction workflow, what state must survive a destroy, networking cost options, how DAGs are validated before spending environment time. | Proposed |

Also open, tracked in `docs/data-sources.md` and `docs/business-questions.md`: the concrete API 1, API 2 and
SaaS/DB sources, and the business questions the Gold layer must answer. Choose sources after the
business questions, not before.

If you find a new decision that is not covered here, propose a new ADR instead of choosing silently.

## Architecture

### End-to-end flow

```
Public API 1 ─┐
              ├─> MWAA / Airflow ─> S3 immutable raw ─> Databricks Bronze
Public API 2 ─┘                                      └─> Quarantine for rejected records (boundary: ADR-002)

SaaS / Database ─> Fivetran ─> Databricks Raw Fivetran
                                      │
                                      └─> dbt staging (Silver) ─> dbt marts (Gold) ─> AI/BI

GitHub ─> GitHub Actions (OIDC) ─> Terraform / deployment / dbt checks
```

The mechanism that turns raw JSON in S3 into a Bronze Delta table is not decided yet (ADR-001).
Do not assume `COPY INTO`, `read_files`, streaming tables, or dbt does it.

### Core layers

- **S3 Raw/Landing**: immutable source payloads. API ingestions create new objects per ingestion date; do not overwrite raw data.
- **Bronze**: data kept close to source plus technical metadata: `_batch_id`, `_ingested_at`, `_source_file`, `_source_system`, `_batch_date`.
- **Silver**: parsing, types, deduplication, normalization, and business rules. Implement this primarily with dbt staging models.
- **Gold**: analytical dimensions and facts in dbt marts.
- **Quarantine**: records rejected by validation rules; retain enough metadata to diagnose the rejection.
- **Snapshots**: dbt snapshot history using SCD2 where historical tracking is required.

### Ingestion responsibilities

- Python + Airflow owns API extraction, pagination, rate limiting, retries, schema validation, and writing raw JSON to S3.
- dbt does not own the main API ingestion. dbt starts at Bronze/Raw and transforms toward Silver/Gold.
- Fivetran is an additional ingestion path, not a prerequisite for the core platform.
- Airflow may coordinate Fivetran through its API, including triggering and waiting for synchronization,
  but Fivetran remains responsible for the connector sync itself.

### Non-negotiable architecture rules

- Use real external sources for the production pipeline. Test fixtures may be synthetic and must live under `tests/fixtures/`.
- Do not replace S3 raw storage with local files for the production flow.
- Do not overwrite immutable raw S3 objects. Use an ingestion-date-based path.
- Do not introduce AWS services that are outside the documented scope unless a concrete requirement justifies them.
- Prefer S3, IAM, MWAA, VPC/networking, CloudWatch Logs, Secrets Manager, and AWS Budgets as the essential AWS footprint.
- KMS, SNS, EventBridge, and CloudTrail are optional only when there is a demonstrated need.
- Redshift, Glue, EMR, Athena, Kinesis, Lambda, DynamoDB, ECR, ECS, and RDS are out of scope unless the architecture is explicitly revised.
  (Consequence: Terraform state locking must not use DynamoDB. See "Terraform conventions".)
- Secrets and credentials must never be committed to Git. Use AWS Secrets Manager or the appropriate runtime secret mechanism.
- GitHub authentication to AWS should use OIDC. Do not add long-lived AWS access keys to GitHub Actions.
- Keep Fivetran optional so the platform remains functional without it if cost or plan constraints make it unavailable.
- Preserve lineage and governance through Unity Catalog; do not introduce a separate lineage system without a specific requirement.
- Keep transformations in dbt models/macros/tests rather than duplicating business logic across Python, DAGs, and SQL.
- Do not add a local orchestration setup (local Airflow, Docker Compose Airflow, etc.). See D-005.
- Destroying the ephemeral stack must never be able to delete raw data, Unity Catalog storage, secrets or the budget.
  Those resources live only in the persistent stack.

## Repository structure

Use this structure unless there is a strong reason to change it:

```
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
│       │   ├── persistent/     # S3 raw + DAG buckets, IAM, Secrets Manager, Budgets
│       │   └── ephemeral/      # VPC/NAT, MWAA, CloudWatch log config for MWAA
│       └── databricks/
├── docs/
│   ├── decisions/              # ADRs
│   ├── runbooks/               # e.g. MWAA up/down
│   ├── evidence/               # notes/screenshots proving each phase works
│   ├── data-sources.md
│   └── business-questions.md
├── tests/
│   └── fixtures/
├── .github/
│   └── workflows/
├── .gitignore
├── README.md
└── AGENTS.md
```

Create directories only in the phase that needs them. Do not create empty scaffolding "for later".
Keep source-specific code isolated. Shared utilities are acceptable only when they are genuinely reusable.
Avoid creating large generic frameworks for a portfolio project.

## Phase workflow (branch -> cleanup -> PR -> stop)

One phase = one branch = one PR. Never commit directly to `main`.
(Single exception: the very first commit that adds `AGENTS.md` and the plan, made by Afonso.)

### Start of phase

1. Read "Current phase" in this file and the matching section of `docs/NOTION_PROJECT_PLAN.md`.
2. `git switch main && git pull`, then create `feat/pX-<short-name>` (or `chore/...` for docs-only work).
3. For a large phase, make small commits with clear messages as you go.

### End of phase: cleanup checklist (before opening the PR)

- Remove scratch files, debug prints, commented-out code, unused imports and unused dependencies.
- Confirm no secrets or state are tracked: `git status`, and
  `git ls-files | grep -E "\.env|tfstate|tfvars|profiles\.yml"` must return nothing. Run gitleaks if configured.
- Run the checks that match the files changed (fmt / lint / validate / tests / dbt parse).
  Report each command with its result. Never say "should pass".
- Tick the phase's Definition of Done in the plan; update README, ADR statuses and `docs/data-sources.md` if they changed.
- List every cloud resource that exists or is running because of this phase, with estimated cost, and say whether
  the ephemeral stack is currently up.
- List the evidence Afonso must capture manually (screenshots, console views) and where to store it in `docs/evidence/`.

### Open the PR, then stop

- Push the branch. Do not merge. Do not start the next phase.
- Produce a PR title and body containing: summary, files touched, verification results, cloud resources and cost
  impact, manual steps left, open decisions, evidence to capture.
- Use `gh pr create` if `gh` is installed and authenticated; otherwise print the title and body so Afonso can paste
  them in the GitHub web UI.
- Last commit on the branch: update "Current phase" (only if the Definition of Done is met).
- Afonso reviews and merges manually. If he requests changes, fix them on the same branch and update the PR text.

## Mandatory Phase-Completion Report

At the end of every completed phase/task, the agent MUST output exactly this structure:

## PHASE COMPLETION SUMMARY

Phase:
Status:

### What changed

### Files changed

### Verification

### Cloud resources / cost

### Manual steps remaining

### Open decisions

### Evidence

### PR

After this summary:

STOP.

The agent must NOT:

* start the next phase
* merge the PR
* continue making unrelated improvements
* silently expand the scope

The report must include the exact commands executed and their results under `### Verification`.

The report must explicitly state whether any cloud resources were created or modified and the resulting cost impact.

## Permissions and safety

Allowed without asking: reading files, git on the working branch, formatters, linters, unit tests, `dbt parse`,
`terraform fmt / init / validate / plan`, read-only cloud CLI calls.

Never do without explicit, per-action approval from Afonso in the current conversation:

- `terraform apply`, `terraform destroy`, `terraform import`, `terraform state` write commands.
- Any command that creates, modifies or deletes AWS, Databricks or Fivetran resources or data.
- Anything that starts or leaves running a billable resource (MWAA, NAT Gateway, SQL Warehouse).
- Pushing to `main`, force-pushing, rewriting history, `--no-verify`, or merging a PR.
- Reading, printing or committing credentials, `.env` files or Terraform state.

If a task seems to require one of these, stop, explain what would run and its cost, and ask.

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
- Keep client code testable with plain `pytest` and recorded fixtures, so most logic can be verified without MWAA running.

Recommended raw path pattern:

```
s3://<bucket>/api/<source_name>/ingest_date=YYYY-MM-DD/<object>.json
```

## Airflow / MWAA conventions

- DAG files should describe orchestration, not contain large blocks of business logic.
- Prefer small tasks with clear inputs/outputs and explicit dependencies.
- MWAA is ephemeral (D-005), so:
  - DAGs and `requirements.txt` live in a persistent S3 location managed by the persistent stack; a rebuilt
    environment must pick them up with no manual steps.
  - Connections and variables come from AWS Secrets Manager (Airflow secrets backend) or Terraform-managed
    configuration, never from values typed into the Airflow UI. Anything created only in the UI is lost on destroy.
  - Do not rely on the Airflow metadata database (run history, UI variables) for anything that must persist.
    Persistent facts (batch ids, ingestion status) live in S3 / Databricks.
- Pin the Airflow version and provider/constraint versions; check MWAA's supported versions before choosing.
- Add a DAG import/parse test that runs without MWAA, so mistakes are caught before spending environment time.

The intended main DAG flow is:

```
API ingestion
  > check S3
  > trigger / wait for Fivetran sync (when enabled)
  > validate raw/landing availability
  > load Bronze (mechanism: ADR-001)
  > dbt build (runner: ADR-003)
  > dbt test / data quality checks
  > confirm marts are available
```

Use retries, timeouts, and clear failure states. Avoid infinite polling or unbounded retries.
When a provider API requires a long wait, use an Airflow-friendly sensor/deferrable pattern where appropriate
rather than blocking a worker unnecessarily.

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
- Connection settings (host, HTTP path, token/OAuth) come from environment variables. `profiles.yml` with real values
  is never committed; commit only a profile that reads from `env_var()`.
- Where dbt runs in the daily DAG is open (ADR-003). Do not wire dbt into MWAA before that ADR is accepted.

## Unity Catalog conventions

Use the documented structure:

```
<catalog>.<schema>.<table>
```

The intended schema groups are: `bronze`, `silver`, `gold`, `quarantine`, `snapshots`.

- Use permissions that follow least privilege: pipeline identities need write access where necessary,
  BI consumers need read access, and developers receive only the access needed for development.
- S3 access should use Unity Catalog storage credentials and external locations rather than ad-hoc credentials in code.
- Setup gotcha: the storage credential's external ID is needed in the IAM role trust policy, while the credential
  references the role. This is a circular dependency. Resolve it in Terraform by following the Databricks provider
  documentation (for example building the role ARN from its name), and verify the exact current procedure
  instead of assuming it. Confirm the workspace type actually supports storage credentials and external locations on
  S3 before writing any Terraform for it.

## Terraform conventions

- Keep AWS and Databricks resources separated under `infra/terraform/aws` and `infra/terraform/databricks`.
- Inside `aws/`, keep the persistent and ephemeral stacks as separate root modules with separate state.
- Cross-stack values (bucket names, role ARNs) pass through outputs, data sources or explicit variables, not copy-paste.
- Persistent stack: raw bucket (versioned, SSE-S3, public access blocked), DAG bucket, IAM, Secrets Manager entries
  (no secret values), Budgets. Protect the raw bucket with `prevent_destroy` and no `force_destroy`.
- Ephemeral stack: VPC/subnets/NAT, MWAA environment, security groups, MWAA log configuration.
  Nothing here may hold data that must survive.
- Prefer small, composable modules/resources over one huge Terraform file.
- Use variables for environment-specific values and avoid hard-coded account IDs, ARNs, secrets, or personal paths.
- Tag every resource (project, stack, phase) so Cost Explorer can attribute spend.
- State: use a remote S3 backend for anything beyond a throwaway experiment. DynamoDB is out of scope, so use S3's
  native lockfile locking if the Terraform version in use supports it (verify), and document the state bucket
  bootstrap procedure. Never commit local state, plans, provider caches, or credentials.
- Run `terraform fmt -check` and `terraform validate` before considering an infrastructure task complete.
- `terraform plan` is verification. The agent does not apply (see "Permissions and safety"); Afonso applies and destroys.

## GitHub Actions conventions

Expected PR checks include, when the relevant files exist:

- tests
- `dbt parse`
- DAG import test
- linting
- gitleaks or equivalent secret scanning
- `terraform fmt -check`, `validate` and `plan`

Expected deployment behavior on merge to `main`, once infrastructure is ready:

- Terraform apply for the persistent stack and Databricks resources only
- Databricks deployment
- `dbt build`

Merge to `main` must never create the ephemeral stack (MWAA). Creating and destroying it is a deliberate manual action.

Use OIDC for AWS authentication. Never create a workflow that depends on a long-lived AWS secret unless the
documented architecture has been explicitly changed.

## Secrets and configuration

Never hard-code:

- API keys
- AWS access keys
- Databricks tokens
- Fivetran credentials
- database passwords
- account IDs when they should be variables

Use environment variables, AWS Secrets Manager, GitHub OIDC/secret mechanisms, or the native secret mechanism of
the target platform. Provide safe examples using placeholders only (for example `.env.example` with empty values).

## Data quality and quarantine

Data quality is a first-class output of the platform, not an afterthought.

- Validation failures should be observable and, when appropriate, diverted to Quarantine instead of being silently dropped.
- Include enough context to answer: which source produced the record? which batch produced it? why was it rejected?
  when was it rejected?
- Do not silently coerce bad data into plausible values just to make a test pass.
- The boundary between ingestion-time validation (file/schema level, Airflow) and row-level validation (dbt) is
  open (ADR-002). The architecture diagram, README and this file must all describe the accepted boundary once decided.

## Monitoring and cost control

- Use Airflow, CloudWatch Logs, and Databricks monitoring for operational visibility.
- The portfolio should demonstrate awareness of cloud cost, especially for MWAA and the Databricks SQL Warehouse.
- MWAA is billed while the environment exists, even when idle, and cannot be paused; only deleting it stops the charge.
  The small environment cost roughly US$0.49/hour when this was written; check current pricing before each window.
  Networking (especially a NAT Gateway) and log storage are billed separately and are the usual surprises.
- Use MWAA in short, planned windows. Every PR that involves MWAA states the expected window length, the
  estimated cost, and the exact destroy command. Creation and deletion take time that is also billed; account for it.
- Databricks SQL Warehouse: smallest size, short auto-stop, no leaving it running between sessions.
- AWS Budgets and alerts must exist before the first billable apply, and be created in the persistent stack once
  Terraform manages them.
- After a window, verify nothing is left running (console or Cost Explorer) and say so in the PR.
- When adding a managed service, document why it is needed and what cost/operational trade-off it introduces.

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

- Update documentation when architecture, source choices, operational behavior, or setup steps change.
- At minimum, keep `README.md`, the technical datasheet/architecture references, and this file consistent enough
  that a new contributor can understand the actual state of the platform.
- ADRs live in `docs/decisions/` as `ADR-NNN-short-title.md` with: Context, Options (with trade-offs),
  Decision, Consequences, Status (Proposed / Accepted / Superseded). An agent may write a Proposed ADR;
  only Afonso moves it to Accepted.
- When a decision changes, document: the old assumption, the new decision, why it changed, and the impact on
  architecture/cost/operations.
- Every phase should leave visible proof that it works. Note in `docs/evidence/` what proof exists or is still to be captured.

## Verification protocol

Before declaring a task complete:

1. Inspect the changed files and confirm the implementation matches the requested scope.
2. Run the narrowest relevant verification first.
3. Run broader checks when the change crosses component boundaries.
4. Report commands run and whether they passed or failed.
5. Never claim a cloud deployment, API sync, Terraform apply, or external integration succeeded unless it was
   actually executed and verified.

Typical checks, only when the corresponding project components exist:

```bash
python -m compileall ingestion orchestration tests
pytest

cd dbt_project
dbt deps
dbt parse
# dbt build / dbt test only against an approved target, never as a casual check

cd ../infra/terraform/aws/persistent
terraform fmt -check
terraform init
terraform validate
terraform plan

cd ../ephemeral
terraform fmt -check
terraform init
terraform validate
terraform plan

cd ../../databricks
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
Confirm the current phase. Do not start editing from the task description alone.

### 2. Plan

For changes spanning multiple components, first state a compact implementation plan and identify dependencies.
Check whether any open ADR blocks the work. For small, local fixes, proceed directly after inspecting the target code.

### 3. Implement minimally

- Make the smallest coherent change that satisfies the task.
- Do not opportunistically refactor unrelated code.
- Do not introduce new infrastructure services unless required.

### 4. Verify

Run focused tests/checks and inspect their output.
For infrastructure, use `fmt`, `validate`, and `plan`; never apply (see "Permissions and safety").

### 5. Report

Finish with:

- what changed
- files touched
- verification performed (exact commands and results)
- cloud resources created or running, and cost impact
- any remaining manual/cloud steps
- any assumptions or unresolved decisions

At the end of a phase, continue with "Phase workflow": cleanup checklist, PR, stop.

## Git rules

- Branch names: `feat/pX-...`, `chore/...`, `fix/...`, `docs/...`.
- Commit messages: short imperative subject, conventional prefix (`feat:`, `fix:`, `chore:`, `docs:`, `infra:`, `test:`).
- One logical change per commit. Do not mix unrelated changes.
- Do not commit generated artifacts, large files, virtualenvs, `target/`, `.terraform/`, or state.
- Do not rewrite shared history.

## Git safety

- Never merge PRs; merging is done by Afonso on GitHub.
- Never push directly to main, never force push, never git reset --hard.
- Never discard uncommitted changes without asking.
- Never touch branches other than the current phase branch.
- Phase workflow is triggered by the /phase command and cleanup by
  /cleanup (see .opencode/command/).

