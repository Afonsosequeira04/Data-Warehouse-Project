# ADR-001: How Bronze is Loaded from Raw JSON in S3

## Status

Accepted

## Context

The architecture defines an immutable S3 raw/landing layer where API ingestions write dated JSON objects. The next step is to load this data into Bronze Delta tables in Databricks with technical metadata (`_batch_id`, `_ingested_at`, `_source_file`, `_source_system`, `_batch_date`).

The Databricks environment provides a SQL Warehouse but no general-purpose compute cluster (per the portfolio scope). The mechanism that turns raw JSON in S3 into Bronze Delta tables is not yet decided.

Constraints:
- No cluster available; only SQL Warehouse
- Must preserve immutable raw data in S3
- Must attach required technical metadata
- Must be idempotent and support reruns
- Must work within MWAA-orchestrated DAGs (or alternative runner)

## Decision Being Considered

What mechanism loads raw JSON from S3 into Bronze Delta tables, and who/what executes it?

## Options

### Option 1: `COPY INTO` via SQL Warehouse

Use Databricks `COPY INTO` command executed through the SQL Warehouse to load JSON files into Delta tables.

**Trade-offs:**
- Pros:
  - Native Databricks SQL command, no cluster needed
  - Idempotent (tracks loaded files)
  - Runs on existing SQL Warehouse
  - Simple to invoke from Airflow via Databricks SQL operator
- Cons:
  - Limited transformation capability during load
  - File format/schema evolution handling can be rigid
  - Requires Unity Catalog external location + storage credential setup

### Option 2: `read_files` / `read_json` in Databricks SQL

Use `read_files` table-valued function or `read_json` in a `CREATE TABLE AS SELECT` or `MERGE` statement via SQL Warehouse.

**Trade-offs:**
- Pros:
  - Pure SQL, runs on SQL Warehouse
  - Flexible schema inference and transformation in-flight
  - Can add metadata columns in the SELECT
- Cons:
  - No built-in idempotency/file tracking (must implement manually)
  - Schema evolution requires careful handling
  - Large files may hit SQL Warehouse limits

### Option 3: Databricks Streaming Tables (DLT)

Use Delta Live Tables streaming tables to incrementally ingest from S3.

**Trade-offs:**
- Pros:
  - Managed incremental ingestion with exactly-once semantics
  - Built-in schema evolution and data quality expectations
  - Declarative pipeline definition
- Cons:
  - Requires DLT pipeline (may need cluster or serverless compute)
  - More complex operational model
  - May exceed portfolio scope/complexity budget

### Option 4: Python/Spark Job on Ephemeral Cluster

Spin up a small ephemeral Databricks job cluster for the Bronze load step.

**Trade-offs:**
- Pros:
  - Full Spark flexibility for complex transformations
  - Can handle any file format/schema scenario
- Cons:
  - Contradicts "no cluster" constraint
  - Adds cost and operational complexity
  - Cluster startup latency in DAG

### Option 5: dbt with `external` Materialization or Custom Materialization

Use dbt to define Bronze models that read from S3 via `read_files` or external tables.

**Trade-offs:**
- Pros:
  - Keeps transformation logic in dbt (consistent with Silver/Gold)
  - Version-controlled, testable
- Cons:
  - dbt typically runs after Bronze exists (per architecture)
  - Custom materialization adds maintenance burden
  - Blurs Bronze/ingestion responsibility boundary

## Consequences

| Aspect | COPY INTO | read_files/SQL | DLT | Ephemeral Cluster | dbt |
|--------|-----------|----------------|-----|-------------------|-----|
| Compute | SQL Warehouse | SQL Warehouse | DLT (serverless/cluster) | Job Cluster | SQL Warehouse/Cluster |
| Idempotency | Built-in | Manual | Built-in | Manual | Manual |
| Metadata injection | Limited | Flexible | Flexible | Full | Flexible |
| Schema evolution | Limited | Manual | Built-in | Full | Manual |
| Operational complexity | Low | Low | Medium | High | Medium |
| Cost | Low (SQL Wh) | Low (SQL Wh) | Medium | Medium-High | Low-Medium |

## Decision

**COPY INTO through Databricks SQL Warehouse.**

Reasoning:
- SQL Warehouse is already part of the intended Databricks architecture
- No long-lived general-purpose cluster is needed
- Suitable for the project scale
- Works with JSON files in S3
- Supports retryable/idempotent ingestion behavior
- Preserves immutable S3 raw
- Easy to orchestrate from MWAA/Airflow
- Avoids introducing another compute service

Bronze technical metadata:
- `_batch_id`
- `_ingested_at`
- `_source_file`
- `_source_system`
- `_batch_date`

Do not introduce:
- Auto Loader
- Delta Live Tables
- Spark job clusters
- Glue
- Another Bronze ingestion service

## Related

- ADR-002 (quarantine boundary affects validation during load)
- ADR-003 (dbt runner affects whether dbt can own Bronze)
- Architecture: S3 Raw → Bronze flow
- D-002: APIs use S3 as immutable raw storage