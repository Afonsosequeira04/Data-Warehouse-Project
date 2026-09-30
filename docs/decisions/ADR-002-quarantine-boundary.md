# ADR-002: Quarantine Boundary for Invalid Records

## Status

Accepted

## Context

The architecture includes a Quarantine layer for records rejected by validation rules. The boundary between ingestion-time validation (file/schema level in Airflow/Python) and row-level validation (in dbt) is not yet decided.

Requirements:
- Validation failures must be observable, not silently dropped
- Rejected records must retain enough context to diagnose: source, batch, rejection reason, timestamp
- The platform must demonstrate data quality as a first-class output
- Valid and invalid records must follow separate, traceable paths

Current architecture assumptions:
- Python + Airflow owns API extraction, pagination, rate limiting, retries, schema validation, and writing raw JSON to S3
- dbt starts at Bronze/Raw and transforms toward Silver/Gold
- Quarantine is a separate schema in Unity Catalog

## Decision Being Considered

Where is the quarantine boundary enforced: at ingestion (file/schema level), at transformation (row level in dbt), or both?

## Options

### Option 1: Ingestion-Time Only (File/Schema Level in Airflow)

Validate entire files/schemas in the Python ingestion code before writing to S3. Reject entire files that fail schema validation; divert to a quarantine S3 prefix. Row-level validation happens later in dbt but does not divert to quarantine.

**Trade-offs:**
- Pros:
  - Fast fail: bad files never enter the raw layer
  - Simple: single validation point
  - Protects downstream from structural/schema surprises
- Cons:
  - All-or-nothing: one bad record rejects entire file/batch
  - Cannot handle row-level business rule violations
  - Loses granular visibility into which records failed

### Option 2: Transformation-Time Only (Row Level in dbt)

Write all raw data to S3 (including structurally valid but semantically bad records). dbt staging models validate each row; failing rows are inserted into Quarantine tables via dbt logic (e.g., `CASE WHEN` splits or custom materializations).

**Trade-offs:**
- Pros:
  - Granular: individual bad rows quarantined, good rows proceed
  - Business rules naturally expressed in SQL/dbt
  - Full raw fidelity preserved in S3
- Cons:
  - Structurally invalid JSON (malformed) may break dbt `read_files`/`COPY INTO`
  - Raw layer contains known-bad data
  - Quarantine logic split across dbt models

### Option 3: Both Layers (Defense in Depth)

- **Ingestion layer**: File/schema validation in Python. Malformed JSON, missing required top-level fields, or schema mismatches → divert entire file to quarantine S3 prefix with error metadata. Valid files proceed to raw S3.
- **Transformation layer**: dbt row-level validation (null PKs, FK violations, business rules, accepted values). Failing rows → Quarantine Delta tables with rejection reason, source metadata, batch info.

**Trade-offs:**
- Pros:
  - Catches structural issues early (protects downstream)
  - Catches semantic/business rule issues at row level
  - Clear separation: ingestion validates "can we parse it?", dbt validates "is it correct?"
  - Maximum observability and traceability
- Cons:
  - Two quarantine destinations (S3 prefix + Delta tables) to monitor
  - More complex operational model
  - Need to correlate file-level and row-level rejections

### Option 4: Ingestion Validates Structure, dbt Validates Semantics (Hybrid)

Similar to Option 3 but with a cleaner contract:
- Ingestion: Only structural/schema validation (JSON well-formed, matches expected schema). Invalid files → quarantine S3.
- dbt: All semantic/business validation (PK, FK, domain values, completeness). Invalid rows → quarantine Delta tables.
- No overlap; each layer has a single, well-defined responsibility.

**Trade-offs:**
- Pros:
  - Clear contract between layers
  - Simpler than full "both" - no duplicate validation logic
  - Aligns with "Python owns ingestion, dbt owns transformation"
- Cons:
  - Still two quarantine surfaces
  - Requires agreement on what "structural" vs "semantic" means

## Consequences

| Aspect | Ingestion Only | dbt Only | Both | Hybrid |
|--------|----------------|----------|------|--------|
| Structural protection | Yes | No | Yes | Yes |
| Row-level granularity | No | Yes | Yes | Yes |
| Raw layer purity | High | Low | High | High |
| Operational surfaces | 1 (S3) | 1 (Delta) | 2 | 2 |
| Implementation effort | Low | Medium | High | Medium |
| Traceability | File-level | Row-level | Both | Both |

## Decision

**Hybrid quarantine boundary.**

Structural validation during ingestion:
- Valid JSON
- Expected response structure
- Required structural fields
- Basic payload/schema integrity

Structural failures:
S3 quarantine.

Semantic/business validation in dbt:
- Business key validity
- Allowed values
- Relationships
- Business rules
- Completeness
- Semantic consistency

Semantic failures:
`<catalog>.quarantine`

Retain diagnostic metadata:
- `source_system`
- `source_file`
- `batch_id`
- `rejection_timestamp`
- `rejection_reason`

Do not silently discard bad data.

## Related

- ADR-001 (Bronze loading mechanism affects where validation can happen)
- Architecture: Quarantine schema in Unity Catalog
- Data quality requirements in AGENTS.md