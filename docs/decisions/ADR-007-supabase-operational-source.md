# ADR-007: Supabase PostgreSQL as the Operational Source for Fivetran

## Status

Accepted

## Context

The architecture defines two distinct ingestion paths:
1. **API path**: Public REST APIs → Python → MWAA/Airflow → S3 RAW → Databricks Bronze
2. **Database path**: Operational database → Fivetran → Databricks (schema: raw_fivetran)

The second path requires a real operational database source to demonstrate the Fivetran managed ingestion strategy. The source must be:
- A genuine operational database (not a copy of API data)
- Small enough for portfolio scope (under 1,000 rows)
- Representative of real-world master data / configuration use cases
- Compatible with Fivetran's PostgreSQL connector

ADR-005 previously selected Amazon RDS PostgreSQL as the operational source. However, RDS introduces persistent AWS infrastructure (VPC, security groups, subnet groups, Fivetran IP allowlisting) that increases cost, networking complexity, and operational overhead for a portfolio project. The RDS instance incurs storage costs even when stopped, and the networking setup required for Fivetran connectivity adds Terraform complexity to the persistent stack.

## Decision Being Considered

Replace Amazon RDS PostgreSQL with Supabase PostgreSQL as the operational source for the Fivetran ingestion path, while keeping the logical source name `macro_watchlist_db` and table structure unchanged.

## Options

### Option 1: Keep Amazon RDS PostgreSQL (ADR-005)

Description: Continue with RDS PostgreSQL in the persistent AWS stack.

**Trade-offs:**
- Pros: Native AWS, fully managed, Fivetran connector is mature, aligns with AWS + Databricks architecture
- Cons: Persistent VPC/networking resources; storage cost even when stopped; Fivetran IP allowlisting complexity; additional Terraform resources in persistent stack; must be created/destroyed with the persistent stack

### Option 2: Supabase PostgreSQL (Selected)

Description: Use a Supabase project (hosted PostgreSQL) as the operational source. The Supabase project is created manually, outside AWS Terraform. The AWS persistent stack only holds the Secrets Manager secret container for Fivetran credentials. Fivetran connects via the Supabase session pooler (exact cursor, e.g., xmin, to verify in P8).

**Trade-offs:**
- Pros: No persistent AWS database infrastructure; no VPC/networking for the source; simpler persistent stack; Supabase free tier is generous; session pooler provides connection pooling; source is outside AWS and outside Terraform, demonstrating a hybrid architecture; manual project setup is a one-time action
- Cons: External vendor dependency; credentials must be manually placed in Secrets Manager; session pooler behavior with Fivetran's Query-Based sync to verify in P8; Supabase project lifecycle is manual

### Option 3: Neon PostgreSQL

Description: Use Neon serverless PostgreSQL.

**Trade-offs:**
- Pros: Serverless, branchable, generous free tier
- Cons: Another external vendor; similar trade-offs to Supabase; less established Fivetran integration pattern

### Option 4: Skip Fivetran / Mark P8 as Skipped

Description: Remove the Fivetran path entirely.

**Trade-offs:**
- Pros: Simplifies architecture, removes database dependency
- Cons: Loses the managed ingestion strategy demonstration; P8 is a valuable portfolio piece showing dual ingestion paths

## Decision

**Use Supabase PostgreSQL as the operational database source for `macro_watchlist_db` and the Fivetran ingestion path.**

### Source Definition: `macro_watchlist_db`

**Provider:** Supabase  
**Database:** PostgreSQL (via Supabase session pooler)  
**Type:** Operational PostgreSQL database  
**Purpose:** Small operational/master-data source controlling the macro watchlist and alert configuration.

This source is **NOT** a copy of World Bank or FRED data.

### Tables

**watchlist_country**
- `country_id`
- `country_code`
- `country_name`
- `region`
- `active`
- `added_at`

**watchlist_indicator**
- `indicator_id`
- `source_system` (values: `world_bank`, `fred`)
- `source_key` (World Bank indicator code or FRED series ID)
- `indicator_name`
- `unit`
- `frequency`
- `active`

**alert_rule**
- `alert_rule_id`
- `country_code`
- `indicator_id`
- `threshold`
- `direction`
- `active`
- `created_at`

### Expected Total Size

Under 1,000 rows.

### Fivetran Connector

PostgreSQL

### Pipeline

```
Supabase PostgreSQL (session pooler)
-> Fivetran
-> Databricks (schema: raw_fivetran)
```

### Destination Convention

`dwh_dev.raw_fivetran.<table>` (Fivetran destination schema prefix to be confirmed in P8; Unity Catalog uses three-level naming: catalog.schema.table)

### Initial Incremental Strategy

Query-Based using `xmin` (exact cursor to verify in P8 via session pooler).

### Security

- TLS
- Dedicated read-only Fivetran database user
- No credentials in Git
- Credentials stored in AWS Secrets Manager secret `cloud-data-platform/macro-watchlist-db` (container only, no values in Git)
- Supabase project created manually, outside AWS Terraform

### Status

Selected (for P8 implementation)

## Alternatives Considered

See Options section above.

## Consequences

### Positive
- Demonstrates a complete managed ingestion strategy (Supabase → Fivetran → Databricks)
- Removes persistent RDS infrastructure from the AWS persistent stack (no VPC, security groups, subnet groups, parameter groups for the source)
- Eliminates Fivetran IP allowlisting complexity for RDS
- Reduces persistent stack cost and complexity
- Demonstrates a hybrid architecture (external operational DB → managed ingestion → AWS lakehouse)
- Fivetran remains optional (D-001) — if plan/account doesn't support Databricks destination, P8 can be formally skipped with documented reason

### Negative / Limitations
- External vendor dependency (Supabase) outside AWS
- Credentials must be manually placed in Secrets Manager (no Terraform-managed RDS credentials)
- Session pooler behavior with Fivetran's Query-Based incremental sync (xmin) to verify in P8
- Supabase project lifecycle is manual (create, seed, manage)
- Free tier limits to verify in P8

## Scope Limitation

**IMPORTANT:**

Supabase is **NOT** a general-purpose platform database.

Supabase is approved **ONLY** for the operational PostgreSQL source defined by this ADR (`macro_watchlist_db`).

It must **NOT** become:
- Analytical storage
- Data warehouse
- General ETL staging
- Unrelated application storage

The Supabase project is a manual prerequisite (create project, create schema `macro_watchlist`, seed 3 tables, create read-only Fivetran user, store credentials in Secrets Manager). The AWS persistent stack only holds the secret container.

## Related

- D-001: Fivetran is optional
- D-002: APIs use S3 as immutable raw storage; Fivetran writes directly to Databricks
- D-006: Terraform starts in P1; AWS infrastructure split into persistent and ephemeral stacks
- ADR-001: Bronze loading (API path)
- ADR-003: dbt runner (both paths converge at dbt)
- ADR-005: Amazon RDS PostgreSQL as the operational source for Fivetran (superseded)
- ADR-008: Streaming ingestion path (proposed)
- P8: Fivetran ingestion path
- docs/data-sources.md: macro_watchlist_db source definition
- docs/business-questions.md: BQ-001, BQ-003 require this source