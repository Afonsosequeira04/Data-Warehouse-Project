# ADR-003: Where dbt Runs in the Daily DAG

## Status

Accepted

## Context

The daily pipeline DAG (orchestrated by Airflow/MWAA) must execute dbt transformations (Silver, Gold, tests, snapshots). The execution environment for dbt is not yet decided.

Constraints:
- MWAA is ephemeral (created/destroyed per work window)
- No long-running compute cluster in the portfolio scope
- Databricks SQL Warehouse is available
- dbt-databricks adapter supports SQL Warehouse and clusters
- dbt must access Unity Catalog governed tables
- Credentials must come from environment variables / Secrets Manager (no committed profiles.yml)

## Decision Being Considered

Where does dbt execute in the daily DAG: inside MWAA (PythonOperator/task), via Databricks Jobs API, or an external runner (dbt Cloud, GitHub Actions, etc.)?

## Options

### Option 1: dbt Inside MWAA (PythonOperator / BashOperator)

Install dbt-core + dbt-databricks in MWAA's `requirements.txt`. Run `dbt build`/`dbt test` as a task in the DAG using a PythonOperator or BashOperator.

**Trade-offs:**
- Pros:
  - Simple: runs in the same orchestration context
  - DAG controls retries, timeouts, dependencies natively
  - No additional infrastructure
  - Logs in Airflow UI
- Cons:
  - MWAA worker must have dbt dependencies (larger image, longer startup)
  - dbt execution time adds to MWAA billed hours
  - Worker resource limits (memory/CPU) may constrain dbt
  - MWAA environment must have network access to Databricks

### Option 2: Databricks Job (dbt as a Databricks Job Task)

Create a Databricks Job that runs dbt (using a job cluster or SQL Warehouse). Trigger the job from Airflow using `DatabricksRunNowOperator` or `DatabricksSubmitRunOperator`, wait for completion.

**Trade-offs:**
- Pros:
  - Runs on Databricks compute (optimized for dbt-databricks)
  - Decouples dbt runtime from MWAA lifecycle
  - Can use job cluster (ephemeral) or SQL Warehouse
  - Native Databricks logging and monitoring
  - MWAA only triggers and waits (lower MWAA cost)
- Cons:
  - Requires managing Databricks Job definition (Terraform or API)
  - More complex DAG: trigger → poll/wait → handle result
  - Job cluster startup latency (~3-5 min)
  - Need to pass parameters (vars, target) via Job API

### Option 3: dbt Cloud (Hosted)

Use dbt Cloud to run transformations. Trigger via API from Airflow.

**Trade-offs:**
- Pros:
  - Zero infrastructure for dbt runtime
  - Built-in scheduling, logging, artifacts, CI
  - Separate from MWAA/Databricks compute
- Cons:
  - Cost (dbt Cloud seats/pricing)
  - External dependency (SaaS)
  - May not align with "portfolio demonstrates self-hosted stack"
  - Credential management across platforms

### Option 4: GitHub Actions (on merge / scheduled)

Run dbt in GitHub Actions workflow (self-hosted or GitHub-hosted runner with Databricks connectivity).

**Trade-offs:**
- Pros:
  - Leverages existing CI/CD
  - No MWAA runtime cost for dbt
- Cons:
  - Not part of the daily DAG (separate trigger)
  - Harder to coordinate with ingestion (Bronze readiness)
  - GitHub Actions runners may lack Databricks network access
  - Not designed for daily operational pipeline orchestration

### Option 5: Databricks SQL Warehouse with dbt SQL Execution

Run dbt models as SQL statements directly on SQL Warehouse via dbt's SQL execution mode (no Spark cluster).

**Trade-offs:**
- Pros:
  - Uses existing SQL Warehouse (already provisioned)
  - Low cost, fast startup
  - Simpler than job clusters
- Cons:
  - Not all dbt features supported (incremental strategies, some macros)
  - dbt-databricks on SQL Warehouse has limitations vs Spark
  - Still needs a runner (MWAA, Job, or external)

## Consequences

| Aspect | Inside MWAA | Databricks Job | dbt Cloud | GitHub Actions | SQL Wh Direct |
|--------|-------------|----------------|-----------|----------------|---------------|
| MWAA cost impact | High (runtime) | Low (trigger only) | Low | Low | Low |
| Compute cost | MWAA worker | Job cluster/SQL Wh | dbt Cloud | GH Actions | SQL Wh |
| Operational complexity | Low | Medium | Low (managed) | Medium | Low |
| DAG integration | Native | Trigger/wait | Trigger/wait | Decoupled | Trigger/wait |
| Feature completeness | Full | Full (cluster) / Limited (SQL Wh) | Full | Full | Limited |
| Credential management | MWAA secrets | Databricks secrets | dbt Cloud | GH secrets | MWAA/Job secrets |

## Decision

**dbt runs from the MWAA execution context against the Databricks SQL Warehouse.**

MWAA owns orchestration.

The later daily pipeline will conceptually orchestrate:

```
API ingestion
-> Bronze readiness
-> optional/enabled Fivetran sync
-> dbt build
-> dbt test
-> quality checks
```

Do not implement the DAG in P0.

Do not create a dbt project in P0.

Do not use dbt Cloud.

Do not create a Databricks Job Cluster.

## Related

- ADR-001 (Bronze loading mechanism may influence dbt runner choice)
- ADR-004 (MWAA operating model affects whether dbt runs inside MWAA)
- D-005: MWAA is ephemeral
- Architecture: dbt starts at Bronze/Raw → Silver → Gold