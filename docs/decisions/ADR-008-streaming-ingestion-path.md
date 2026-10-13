# ADR-008: Optional Streaming Ingestion Path (P8b)

## Status

Proposed

## Context

The current architecture defines two ingestion paths:
1. **API path**: Public REST APIs → Python → MWAA/Airflow → S3 RAW → Databricks Bronze (batch, daily)
2. **Database path**: Operational database (Supabase PostgreSQL) → Fivetran → Databricks (managed, daily)

The project roadmap includes an optional streaming path (P8b) to demonstrate a real-time ingestion capability. This path is strictly optional, time-boxed, and cost-aware. It is not required by the core platform and must not block or delay any core phase.

The streaming path would ingest from a public streaming feed (WebSocket/SSE) into the platform, showing an alternative to batch ingestion for high-frequency data.

## Decision Being Considered

Should the project include an optional streaming ingestion path (P8b), and if so, what is the architecture, scope limits, and open questions that must be resolved before implementation?

## Proposed Architecture

```
Public streaming feed (WebSocket/SSE)
    │
    ▼
Local time-boxed producer (reconnect, validation, PutRecords)
    │
    ▼
Kinesis Data Streams (1 shard, 24h retention)
    │         │
    │         └─> Ephemeral stack (new Terraform root: aws/streaming)
    │               Applied/destroyed manually, never by CI
    │
    ▼
Databricks streaming job (structured streaming)
    │
    ▼
Bronze table: bronze.stream_<source>
    │
    ▼
dbt incremental Silver models
    │
    ▼
Gold layer
```

### Key Design Points

- **Source**: Public streaming feed (WebSocket or SSE) — exact source not yet selected
- **Producer**: Local Python script, time-boxed (e.g., 30-60 min window), handles reconnect, validation, puts to Kinesis via `PutRecords`
- **Kinesis**: 1 shard, 24-hour retention, in the ephemeral stack (`aws/streaming` Terraform root), applied/destroyed manually, never by CI/CD
- **Databricks**: Streaming job (Structured Streaming) reads from Kinesis, writes to `bronze.stream_<source>` Delta table
- **dbt**: Incremental Silver models transform streaming Bronze to Silver/Gold
- **Quarantine**: Invalid messages diverted to S3 raw bucket prefix `quarantine/stream/<source>/` with rejection metadata
- **Checkpoints**: Stored in a non-raw location (Unity Catalog managed storage or separate checkpoint bucket), NOT in the raw external location (which is read-only)
- **Observability**: Streaming freshness shown in the data-quality dashboard
- **Cost control**: Entire streaming stack is ephemeral, time-boxed, manually controlled; Kinesis 1 shard ~$0.015/hour + PUT payload units; Databricks job cluster only during window

## Scope Limits

- **Optional**: Not required for portfolio completion. Core platform (APIs + Fivetran) must work without it.
- **Proposed**: ADR-008 is Proposed. No implementation may start until it is Accepted by Afonso.
- **Time-boxed**: Producer runs only during a planned window (e.g., 30-60 minutes). Kinesis and Databricks job exist only during that window.
- **Cost-aware**: Estimated cost per window must be documented before Acceptance. Kinesis + Databricks job cluster costs must fit within the $10/month budget guardrail.
- **No CI/CD**: The streaming Terraform root (`aws/streaming`) is applied and destroyed manually. It is never created by GitHub Actions on merge to `main`.
- **Kinesis stays out of scope** until ADR-008 is Accepted.

## Open Questions

The following items are **OPEN** and must be resolved before ADR-008 can be Accepted. Do not decide them here; list them as open.

1. **Streaming source**: Which public WebSocket/SSE feed? Must be free, no auth or simple auth, sustainable for demo windows, meaningful data for a dashboard tile. Candidates to evaluate.
2. **BQ-004**: What business question would the streaming path answer? Must be defined before selecting a source.
3. **Databricks compute for the streaming job**: Serverless vs job cluster. ADR-001/ADR-003 constrain the platform to "no cluster" (SQL Warehouse only for batch). Does a streaming job require a job cluster? If so, how does this fit with the "no cluster" constraint? Free Edition workspace limitations apply.
4. **Checkpoint location**: The raw external location is read-only. Checkpoints must go to a writable location (UC managed storage? separate S3 bucket?).
5. **dbt runner for streaming tables**: ADR-003 places dbt in MWAA against SQL Warehouse. Streaming tables may require a different runner or pattern. How do incremental dbt models work with streaming Bronze tables?
6. **Databricks plan type**: Workspace is Free Edition. Does Free Edition support Structured Streaming jobs and Kinesis connector? To verify.
7. **Cost**: Estimate per window (Kinesis 1 shard + Databricks job cluster + data transfer). Must fit budget.
8. **Fivetran interaction**: Does the streaming path affect or integrate with the Fivetran path? Likely independent.
9. **Quarantine schema for streaming**: Define the quarantine table structure for stream invalid messages.

## Consequences

### Positive
- Demonstrates a third ingestion pattern (streaming) alongside batch API and managed DB ingestion
- Shows Kinesis + Databricks Structured Streaming integration
- Adds real-time freshness to the data-quality dashboard
- Time-boxed, manual control keeps cost predictable

### Negative / Limitations
- Adds Kinesis (normally out of scope) and streaming job complexity
- Free Edition Databricks may not support required features
- "No cluster" constraint from ADR-001/ADR-003 may conflict with streaming job requirements
- Manual Terraform root (`aws/streaming`) breaks the "everything in CI/CD" pattern
- Producer runs locally (not in MWAA), which is a different operational model
- Additional open questions must be resolved before any implementation

## Related

- ADR-001: Bronze loading (API path — COPY INTO via SQL Warehouse, no cluster)
- ADR-003: dbt runner (MWAA + SQL Warehouse)
- ADR-007: Supabase PostgreSQL as the operational source for Fivetran
- P8: Fivetran ingestion path
- P8b: Streaming ingestion path (optional, proposed)
- docs/data-sources.md: streaming source entry (Not selected)
- docs/business-questions.md: BQ-004 (to be defined)