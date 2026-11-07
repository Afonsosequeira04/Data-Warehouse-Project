# ADR-008: Streaming Ingestion Path (P4c and P8b)

## Status

Proposed

## Direction

Directed by Afonso on 2026-11-06:

- P8b is a regular phase in the project roadmap and counts toward portfolio completion. It is not optional and there is no formal-skip escape hatch.
- P8b remains time-boxed, cost-aware, and manually applied/destroyed; those are operational constraints, not reasons to skip the phase.
- Question 6 (Databricks plan type) is answered: the Free Edition workspace supports Structured Streaming jobs and the Kinesis connector. Confirmed by Afonso on 2026-11-06.

Updated 2026-11-06 (later): always-on while applied; replaces time-boxed. The streaming path covers the always-on foundation in P4c (EMSC, USGS Water Data, NOAA buoys, GDACS) and the AISstream scale-out in P8b.

## Context

The platform ingests six public sources in four shapes:

1. **Batch (Airflow)**: NASA FIRMS → Python → MWAA/Airflow → S3 raw → Databricks Bronze (ADR-001).
2. **Always-on producers → Kinesis**: EMSC earthquakes and AISstream vessel positions are WebSocket feeds consumed by long-running clients; USGS Water Data, NOAA buoys and GDACS are HTTP/RSS feeds read by long-lived polling loops. All five run in one always-on container, publish to Kinesis Data Streams, and a Databricks Structured Streaming job writes `bronze.stream_<source>`.
3. **Managed sync (Fivetran)**: Supabase PostgreSQL → Fivetran → Databricks (`raw_fivetran`).

A scheduled Airflow task is a poor fit for those five sources: a WebSocket client must hold an open connection, and a polling loop must keep a cadence shorter than the batch schedule to keep freshness. The streaming path exists to ingest them and to demonstrate a third ingestion pattern alongside batch and managed sync. It does not replace them. The legacy World Bank/FRED sources were retired on 2026-11-06; the streaming path is not related to them.

AISstream is deferred to P8b because of its volume. The other four sources are built in P4c.

## Decision Being Considered

Should the project include an always-on ingestion path through Kinesis for EMSC, AISstream, USGS Water Data, NOAA buoys and GDACS (P4c and P8b), and if so, what architecture, scope limits and open questions must be resolved before implementation?

## Proposed Architecture

```
EMSC feed (WebSocket) ──────────┐
AISstream feed (WebSocket) ─────┤
USGS Water Data (polling) ──────┤
NOAA buoys (polling) ───────────┤
GDACS (RSS/API polling) ────────┤
                                ▼
              Always-on producer container (ECS Fargate)
              WebSocket consumers + polling loops,
              reconnect/backoff, validate, PutRecords
                                │
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
           bronze.stream_usgs_water_gauges
           bronze.stream_noaa_ocean_buoys
           bronze.stream_gdacs_disaster_alerts
                                │
                                ▼
             dbt incremental Silver models
                                │
                                ▼
                            Gold layer
```

### Key Design Points

- **Sources**: EMSC, AISstream, USGS Water Data, NOAA buoys and GDACS, all selected in `docs/data-sources.md`. The feeds, filters and message shapes are recorded in the per-source spikes; do not assume an endpoint, auth method or schema before those spikes.
- **Producers**: one Python container with a WebSocket consumer per streaming feed and a polling loop per polled feed, with reconnect/backoff, bounded retries, schema validation before publishing, and `PutRecords` to Kinesis. The exact split into processes and tasks is decided in the spike. Producers must not run inside MWAA, because MWAA is ephemeral (D-005) and cannot host long-lived connections.
- **Producer runtime**: a small always-on container on ECS Fargate with an ECR image, in its own Terraform root, proposed in ADR-010. It runs while the root is applied and is started and stopped manually by Afonso.
- **Kinesis**: 1 shard, 24-hour retention, in an `aws/streaming` Terraform root, applied and destroyed manually by Afonso. Never created by CI/CD and never part of the persistent stack. Kinesis retention bounds how far replay can go.
- **Databricks**: a Structured Streaming job reads from Kinesis and writes to the `bronze.stream_<source>` Delta tables.
- **No immutable raw S3 object**: unlike the batch path, streaming messages are not first written to S3 raw. The first persistent copy is Bronze; Kinesis retains messages for 24 hours and bounds replay.
- **dbt**: incremental Silver models transform the streaming Bronze tables; Gold models follow the same conventions as the batch Gold models.
- **Quarantine**: invalid messages are diverted to the S3 prefix `quarantine/stream/<source>/` with rejection metadata (source, batch id, rejection reason, rejected-at timestamp), consistent with ADR-002.
- **Checkpoints**: stored in a writable non-raw location (Unity Catalog managed storage or a separate checkpoint bucket). Never inside the raw external location, which is immutable.
- **Observability**: streaming freshness is shown in the data-quality dashboard alongside batch freshness.
- **Cost control**: the streaming root runs while applied and is stopped manually. Kinesis 1 shard is roughly US$0.015/hour plus PUT payload units (verify current pricing). The full cost model and the spending cap are tracked in ADR-011.

## Scope Limits

- **Proposed**: ADR-008 is Proposed. No implementation may start until it is Accepted by Afonso.
- **Always-on while applied**: the producers, Kinesis and the Databricks streaming job run continuously while the streaming root is applied, and are destroyed manually when no longer needed.
- **Cost-aware, not $10-bounded**: the batch platform keeps its existing small monthly guardrail. Streaming and large-volume extensions are explicitly not bound by that guardrail or by Free Edition limits; the cap is set by Afonso and recorded in ADR-011. No monthly figure is invented here.
- **No CI/CD**: the streaming Terraform root (`aws/streaming`) is applied and destroyed manually. It is never created by GitHub Actions on merge to `main`.
- **Kinesis stays out of scope** until ADR-008 is Accepted.
- **ECS stays out of scope** until ADR-010 is Accepted.

## Open Questions

The following items must be resolved before ADR-008 can be Accepted. Do not decide them here.

1. **Databricks compute for the streaming job**: serverless vs job cluster. ADR-001/ADR-003 constrain the batch platform to "no cluster" (SQL Warehouse only). Does a streaming job require a job cluster, and how does that fit? The Free Edition workspace is serverless-only, which narrows this question but does not by itself resolve it.
2. **Checkpoint location**: the raw external location is read-only. Choose the writable location (UC managed storage or a separate S3 prefix/bucket) and who owns it.
3. **dbt runner for streaming tables**: ADR-003 places dbt in MWAA against a SQL Warehouse. Streaming tables may need a different runner or incremental pattern. Define how incremental dbt models read streaming Bronze tables.
4. **Monthly cost and spending cap**: estimate Kinesis + Databricks compute + data transfer while the root is applied; Afonso sets the cap (ADR-011).
5. **Firehose as a second consumer**: is an optional Kinesis Firehose delivery to S3 raw worth adding so the streaming path also has immutable raw history? Not decided.
6. **Fivetran interaction**: confirm the streaming path is independent of the Fivetran path. Expected answer: independent.
7. **Quarantine structure for streaming**: define the quarantine table/prefix schema for rejected stream messages, consistent with ADR-002.
8. **Duplicate overlapping polling windows**: polled sources can return overlapping windows. Deduplicate in Silver using station/identifier + parameter + timestamp. Confirm the exact key per source in the spike.
9. **Feed filters and volume**: define the AISstream geographic/MMSI filter and the EMSC subscription so the producer stays inside the monthly budget.

### Resolved on 2026-11-06

- **Streaming sources**: EMSC earthquakes and AISstream vessel positions (recorded in `docs/data-sources.md`). Extended later that day to the always-on routing above, which also covers USGS Water Data, NOAA buoys and GDACS.
- **Business questions**: streaming serves BQ-001, BQ-002 and BQ-005 (recorded in `docs/business-questions.md`). The old placeholder BQ-004 is retired.
- **Databricks plan type**: Free Edition supports Structured Streaming and the Kinesis connector (confirmed by Afonso).

## Consequences

### Positive

- Demonstrates a third ingestion pattern (streaming) alongside batch API and managed DB ingestion.
- Shows Kinesis + Databricks Structured Streaming with five real sources.
- Adds real-time and short-cadence freshness to the data-quality dashboard and supports near-real-time hazard questions.
- Manual apply/destroy keeps cloud cost under Afonso's control.

### Negative / Limitations

- Adds Kinesis (normally out of scope) and streaming job complexity.
- The "no cluster" constraint from ADR-001/ADR-003 may conflict with streaming job requirements.
- A manual Terraform root (`aws/streaming`) breaks the "everything in CI/CD" pattern.
- An always-on producer (ADR-010) is a different operational model from the rest of the platform.
- Streaming has no immutable raw S3 object: Kinesis 24-hour retention bounds replay and Bronze is the first persistent copy.
- Polled sources can deliver overlapping windows and therefore duplicate rows unless Silver deduplicates them.
- Additional open questions must be resolved before any implementation.

## Related

- ADR-001: Bronze loading (batch path — COPY INTO via SQL Warehouse, no cluster)
- ADR-002: Quarantine boundary
- ADR-003: dbt runner (MWAA + SQL Warehouse)
- ADR-007: Supabase PostgreSQL as the operational source for Fivetran (amended by ADR-012, Proposed)
- ADR-010: Where the always-on ingestion producers run (Proposed)
- ADR-011: Compute and budget model for streaming and large-volume extensions (Proposed)
- ADR-012: Supabase operational source re-scope (Proposed)
- P4c: Always-on foundation (EMSC, USGS Water Data, NOAA buoys, GDACS)
- P8b: Streaming ingestion scale-out (AISstream)
- `docs/data-sources.md`: source entries and ingestion modes
- `docs/business-questions.md`: BQ-001, BQ-002, BQ-005
