# ADR-012: Re-scope the Supabase Operational Source for the Earth-Monitoring Platform

## Status

Proposed

## Context

ADR-007 (Accepted) chose Supabase PostgreSQL as the operational source for the Fivetran ingestion path, under the logical source name `macro_watchlist_db`, with three seeded tables:

- `watchlist_country`
- `watchlist_indicator`
- `alert_rule`

That structure was designed for the retired World Bank/FRED macro track. On 2026-11-06 Afonso replaced those sources with six Earth-monitoring feeds: EMSC earthquakes, AISstream vessel positions, NASA FIRMS fires, USGS Water Data gauges, NOAA buoys, and GDACS disaster events (`docs/data-sources.md`).

The new business questions (BQ-001 to BQ-005) need a small operational reference model, not a macro watchlist:

- **`watch_region`**: the places being watched (for example, a region, basin or alert area). Gold uses this to scope BQ-001 to BQ-005.
- **`alert_rule`**: thresholds and parameters for alert evaluation. BQ-002 uses buoy anomaly thresholds; BQ-003 uses water gauge flood thresholds and rise rates.

`watchlist_country` and `watchlist_indicator` have no counterpart in the new questions. The old `alert_rule` structure was built for economic indicators.

Constraints that still hold:

- Fivetran remains **optional** (D-001). The core batch and streaming platform must work without it, using static configuration from the repository until P8.
- ADR-007's operational decisions (Supabase project created manually, TLS, dedicated read-only Fivetran user, secret container in the persistent stack, no credentials in Git) remain valid.
- Only Afonso accepts ADRs. This ADR is Proposed; it does not by itself change Terraform, secrets, or seeded data.
- The name `macro_watchlist_db` appears in existing docs, secrets, and plans. Renaming it is a cosmetic change with cross-cutting edits, not a functional requirement.

## Decision Being Considered

How should the Supabase operational source be re-scoped so it supports hazard-monitoring alert configuration (BQ-001 to BQ-005) while keeping Fivetran optional and minimizing churn in the existing documented names?

## Options

### Option 1: Keep the logical name `macro_watchlist_db`, replace the tables (recommended)

Retain `macro_watchlist_db` as the logical source name and the existing Supabase project and secret. Replace the seeded table structure with `watch_region` and `alert_rule`, and retire `watchlist_country` and `watchlist_indicator`.

**Trade-offs:**
- Pros: Smallest change; existing ADR-007 names, secret paths, and docs stay valid; no Terraform or secret renames; P8 can proceed without a migration.
- Cons: The name `macro_watchlist_db` no longer describes its content; a reader may assume macro data still exists. The mismatch must be explained in `docs/data-sources.md` and ADR-007's amendment note.
- Best use: the pragmatic path while the platform is still being replanned.

### Option 2: Rename the logical source to `earth_watch_db`

Adopt a name that matches the new purpose, for example `earth_watch_db` (or `hazard_watch_db`), with tables `watch_region` and `alert_rule`.

**Trade-offs:**
- Pros: Self-documenting; removes the stale "macro" vocabulary from the operational source.
- Cons: Touches the secret name, Terraform secret container, ADR-007, the plan, `docs/data-sources.md`, and any P8 runbook; creates a migration step for an otherwise cosmetic gain.
- Best use: a later chore once the platform has settled, not a prerequisite for P8.

### Option 3: Drop the operational database and Fivetran from the core path

Remove the Supabase/Fivetran path entirely and keep alert configuration as static repository files.

**Trade-offs:**
- Pros: Fewer moving parts; no external database to seed or secure.
- Cons: Loses the managed-DB ingestion demonstration that the architecture documents; conflicts with the intent of ADR-007; removes a non-API ingestion pattern from the portfolio.
- Best use: only if the Fivetran path is permanently abandoned, which is not the current direction.

## Consequences

### Architecture

- Options 1 and 2 keep the two ingestion paths: API/streaming to S3 and Kinesis, plus Fivetran writing to `raw_fivetran`. Only the reference tables change.
- Option 3 removes the Fivetran path and the `raw_fivetran` schema from the active architecture.
- In all options, batch and streaming producers read static configuration from the repository until P8.

### Cost

- Options 1 and 2 keep the Supabase free tier and the Fivetran plan already assumed in ADR-007. No new cost.
- Option 3 removes that cost entirely but also removes the demonstration.

### Operations

- Options 1 and 2 require re-seeding the Supabase project with `watch_region` and `alert_rule` before P8. This is a manual prerequisite, as in ADR-007.
- Option 2 additionally requires renaming the secret and any Terraform-managed secret container, with a plan reviewed by Afonso.
- Option 3 removes the seeding step and the Fivetran sync from the runbook.

### Security

- Unchanged from ADR-007: TLS, dedicated read-only Fivetran user, credentials in Secrets Manager, no secrets in Git.
- Option 2 changes the secret name, so the Terraform plan must be reviewed to avoid dangling references.

### Developer experience

- Option 1 requires only documentation and seed-script changes.
- Option 2 adds a rename chore across docs and infra.
- Option 3 simplifies the reference model but removes a documented capability.

### Timeline

- Option 1 can be applied as soon as this ADR is Accepted, before P8.
- Option 2 adds a rename chore that can be scheduled later.
- Option 3 would require editing ADR-007's architectural intent, not just its tables.

## Decision

*To be filled when Accepted: which option was chosen and why.*

## Related

- ADR-007: Supabase PostgreSQL as the operational source for Fivetran (amended by this ADR)
- ADR-005: Amazon RDS PostgreSQL as the operational source (Superseded by ADR-007)
- D-001: Fivetran is optional, not mandatory
- D-002: APIs use S3 as immutable raw storage; Fivetran writes directly to Databricks
- `docs/data-sources.md`: Supabase PostgreSQL entry (re-scoped)
- `docs/business-questions.md`: BQ-001 to BQ-005, `alert_rule` references
- `docs/NOTION_PROJECT_PLAN.md`: P8 Fivetran phase
