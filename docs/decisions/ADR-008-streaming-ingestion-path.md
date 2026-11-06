# ADR-008: Streaming Ingestion Path (P8b)

## Status

Proposed

## Direction

Directed by Afonso on 2026-11-06:

- P8b is a regular phase in the project roadmap and counts toward portfolio completion. It is not optional and there is no formal-skip escape hatch.
- P8b remains time-boxed, cost-aware, and manually applied/destroyed; those are operational constraints, not reasons to skip the phase.
- Question 6 (Databricks plan type) is answered: the Free Edition workspace supports Structured Streaming jobs and the Kinesis connector. Confirmed by Afonso on 2026-11-06.

## Context

The platform now ingests six public sources in two shapes:

1. **Batch / polling (Airflow)**: NASA FIRMS, USGS Water Data, NOAA buoys and GDACS → Python → MWAA/Airflow → S3 raw → Databricks Bronze.
2. **Managed sync (Fivetran)**: Supabase PostgreSQL → Fivetran → Databricks (`raw_fivetran`).

Two selected sources publish continuously and are a poor fit for scheduled polling:

- **EMSC earthquakes** — public real-time earthquake feed.
- **AISstream** — public real-time vessel position feed.

The streaming path exists to ingest those two sources and to demonstrate a third ingestion pattern alongside batch and managed sync. It does not replace them. The legacy World Bank/FRED sources were retired on 2026-11-06; the streaming path is not related to them.

## Decision Being Considered

Should the project include a streaming ingestion path (P8b) for EMSC and AISstream, and if so, what architecture, scope limits and open questions must be resolved before implementation?

## Proposed Architecture

```
EMSC feed (WebSocket) ─────┐
                           ├─> Python producer (reconnect, validate, PutRecords)
AISstream feed (WebSocket) ┘            │
                                        ▼
                       Kinesis Data Streams (1 shard, 24h retention)
                                        │   aws/streaming Terraform root
                                        │   applied/destroyed manually, never by CI
                                        ▼
                     Databricks Structured Streaming job
                                        │
                                        ▼
        Bronze: bronze.stream_emsc_earthquakes
                bronze.stream_ais_vessel_positions
                                        │
                                        ▼
                     dbt incremental Silver models
                                        │
                                        ▼
                                    Gold layer
```

### Key Design Points

- **Sources**: EMSC earthquakes and AISstream vessel positions, both selected in `docs/data-sources.md`. The selected feeds, filters and message shapes are recorded in the P8b spike; do not assume an endpoint, auth method or schema before that spike.
- **Producer**: Python WebSocket client per source, with reconnect/backoff, bounded retries, schema validation before publishing, and `PutRecords` to Kinesis. One producer process per source or one process handling both streams; the spike decides which is simpler.
- **Producer runtime**: running the producer on Afonso's machine only during a demo window is the fallback. The recommended option is a small always-on container (ECS Fargate) in its own Terraform root, proposed in ADR-010. Producers must not run inside MWAA, because MWAA is ephemeral (D-005) and cannot host a long-lived WebSocket client.
- **Kinesis**: 1 shard, 24-hour retention, in an ephemeral `aws/streaming` Terraform root, applied and destroyed manually by Afonso. Never created by CI/CD and never part of the persistent stack.
- **Databricks**: Structured Streaming job reads from Kinesis and writes to `bronze.stream_emsc_earthquakes` and `bronze.stream_ais_vessel_positions` Delta tables.
- **dbt**: incremental Silver models transform the streaming Bronze tables; Gold models follow the same conventions as the batch Gold models.
- **Quarantine**: invalid messages are diverted to S3 prefix `quarantine/stream/<source>/` with rejection metadata (source, batch/micro-batch id, rejection reason, rejected-at timestamp), consistent with ADR-002.
- **Checkpoints**: stored in a writable non-raw location (Unity Catalog managed storage or a separate checkpoint bucket). Never inside the raw external location, which is immutable.
- **Observability**: streaming freshness is shown in the data-quality dashboard alongside batch freshness.
- **Cost control**: the streaming Terraform root is ephemeral and time-boxed; Kinesis 1 shard is roughly US$0.015/hour plus PUT payload units (verify current pricing). The full cost model and the spending cap are tracked in ADR-011.

## Scope Limits

- **Proposed**: ADR-008 is Proposed. No implementation may start until it is Accepted by Afonso.
- **Time-boxed**: producers run only during a planned window. Kinesis and the Databricks streaming job exist only during that window.
- **Cost-aware, not $10-bounded**: the batch platform keeps its existing small monthly guardrail. Streaming and large-volume extensions are explicitly not bound by that guardrail or by Free Edition limits; the cap is set by Afonso and recorded in ADR-011. No monthly figure is invented here.
- **No CI/CD**: the streaming Terraform root (`aws/streaming`) is applied and destroyed manually. It is never created by GitHub Actions on merge to `main`.
- **Kinesis stays out of scope** until ADR-008 is Accepted.
- **ECS stays out of scope** until ADR-010 is Accepted.

## Open Questions

The following items must be resolved before ADR-008 can be Accepted. Do not decide them here.

1. **Databricks compute for the streaming job**: serverless vs job cluster. ADR-001/ADR-003 constrain the batch platform to "no cluster" (SQL Warehouse only). Does a streaming job require a job cluster, and how does that fit? The Free Edition workspace is serverless-only, which narrows this question but does not by itself resolve it.
2. **Checkpoint location**: the raw external location is read-only. Choose the writable location (UC managed storage or a separate S3 prefix/bucket) and who owns it.
3. **dbt runner for streaming tables**: ADR-003 places dbt in MWAA against a SQL Warehouse. Streaming tables may need a different runner or incremental pattern. Define how incremental dbt models read streaming Bronze tables.
4. **Cost per window and spending cap**: estimate Kinesis + Databricks compute + data transfer per window; Afonso sets the cap (ADR-011).
5. **Fivetran interaction**: confirm the streaming path is independent of the Fivetran path. Expected answer: independent.
6. **Quarantine structure for streaming**: define the quarantine table/prefix schema for rejected stream messages, consistent with ADR-002.
7. **Feed filters and volume**: define the AISstream geographic/MMSI filter and the EMSC subscription so the producer stays inside the window budget.

### Resolved on 2026-11-06

- **Streaming source**: EMSC earthquakes and AISstream vessel positions (recorded in `docs/data-sources.md`).
- **Business questions**: streaming serves BQ-001, BQ-002 and BQ-005 (recorded in `docs/business-questions.md`). The old placeholder BQ-004 is retired.
- **Databricks plan type**: Free Edition supports Structured Streaming and the Kinesis connector (confirmed by Afonso).

## Consequences

### Positive

- Demonstrates a third ingestion pattern (streaming) alongside batch API and managed DB ingestion.
- Shows Kinesis + Databricks Structured Streaming with two real sources.
- Adds real-time freshness to the data-quality dashboard and supports near-real-time hazard questions.
- Time-boxed, manual control keeps cost predictable.

### Negative / Limitations

- Adds Kinesis (normally out of scope) and streaming job complexity.
- The "no cluster" constraint from ADR-001/ADR-003 may conflict with streaming job requirements.
- A manual Terraform root (`aws/streaming`) breaks the "everything in CI/CD" pattern.
- An always-on producer (ADR-010) is a different operational model from the rest of the platform.
- Additional open questions must be resolved before any implementation.

## Related

- ADR-001: Bronze loading (batch path — COPY INTO via SQL Warehouse, no cluster)
- ADR-002: Quarantine boundary
- ADR-003: dbt runner (MWAA + SQL Warehouse)
- ADR-007: Supabase PostgreSQL as the operational source for Fivetran (amended by ADR-012, Proposed)
- ADR-010: Where the always-on ingestion producers run (Proposed)
- ADR-011: Compute and budget model for streaming and large-volume extensions (Proposed)
- ADR-012: Supabase operational source re-scope (Proposed)
- P8b: Streaming ingestion path
- `docs/data-sources.md`: EMSC and AISstream entries
- `docs/business-questions.md`: BQ-001, BQ-002, BQ-005
