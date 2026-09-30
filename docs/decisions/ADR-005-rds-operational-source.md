# ADR-005: Amazon RDS PostgreSQL as the Operational Source for Fivetran

## Status

Accepted

## Context

The architecture defines two distinct ingestion paths:
1. **API path**: Public REST APIs → Python → MWAA/Airflow → S3 RAW → Databricks Bronze
2. **Database path**: Operational database → Fivetran → Databricks (schema: raw_fivetran, prefix to be confirmed in P8)

The second path requires a real operational database source to demonstrate the Fivetran managed ingestion strategy. The source must be:
- A genuine operational database (not a copy of API data)
- Small enough for portfolio scope (under 1,000 rows)
- Representative of real-world master data / configuration use cases
- Compatible with Fivetran's PostgreSQL connector

Previously, the project documentation stated that "Redshift, Glue, EMR, Athena, Kinesis, Lambda, DynamoDB, ECR, ECS, and RDS are out of scope unless the architecture is explicitly revised." This blanket statement needs to be scoped to allow the specific, approved use of RDS PostgreSQL as an operational source for the Fivetran path.

## Problem

The project needs a real operational database source for the Fivetran ingestion path to demonstrate a managed database ingestion strategy. However, the existing AGENTS.md and NOTION_PROJECT_PLAN.md contain a blanket statement that RDS is out of scope, which conflicts with this architectural requirement.

## Decision

**Use Amazon RDS PostgreSQL only as the operational database source for `macro_watchlist_db` and the Fivetran ingestion path.**

### Source Definition: `macro_watchlist_db`

**Provider:** Amazon Web Services  
**Database:** Amazon RDS for PostgreSQL  
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
Amazon RDS PostgreSQL
-> Fivetran
-> Databricks (schema: raw_fivetran)
```

### Destination Convention
`dwh_dev.raw_fivetran.<table>` (Fivetran destination schema prefix to be confirmed in P8; Unity Catalog uses three-level naming: catalog.schema.table)

### Initial Incremental Strategy
Query-Based using `xmin`.

### Security
- TLS
- Dedicated read-only Fivetran database user
- Restricted network access
- No 0.0.0.0/0 exposure
- No credentials in Git
- Future credentials stored through approved secret mechanism

### Status
Selected (for P8 implementation)

## Alternatives Considered

### Alternative 1: Neon PostgreSQL
- Pros: Serverless, branchable, generous free tier
- Cons: Not AWS-native; adds another vendor; Fivetran connector exists but less "portfolio standard" for AWS + Databricks story

### Alternative 2: Skip Fivetran / Mark P8 as Skipped
- Pros: Simplifies architecture, removes RDS dependency
- Cons: Loses the managed ingestion strategy demonstration; P8 is a valuable portfolio piece showing dual ingestion paths

### Alternative 3: Other Database Options (MySQL, SQL Server, MongoDB)
- Pros: Different technology demonstration
- Cons: PostgreSQL is the most common operational DB for this use case; Fivetran PostgreSQL connector is mature

### Alternative 4: Use a SaaS Source (e.g., HubSpot, Salesforce) via Fivetran
- Pros: Demonstrates SaaS connector
- Cons: Requires SaaS account/setup; less control over data; doesn't demonstrate operational DB → Fivetran → Databricks pattern as clearly

## Trade-offs Discussed

| Dimension | RDS PostgreSQL | Neon | Skip Fivetran | SaaS Source |
|-----------|----------------|------|---------------|-------------|
| AWS Alignment | Native | External | N/A | External |
| Cost (portfolio) | Low (db.t3.micro, stopped when not used) | Free tier | Zero | Varies |
| Networking | Standard VPC | Serverless | N/A | SaaS |
| Fivetran Integration | Native PostgreSQL connector | Native PostgreSQL connector | N/A | Connector-specific |
| Operational Simplicity | Standard RDS operations | Simpler (serverless) | Simplest | SaaS-dependent |
| Portability | Standard PostgreSQL | Standard PostgreSQL | N/A | Vendor-specific |

## Consequences

### Positive
- Demonstrates a complete managed ingestion strategy (RDS → Fivetran → Databricks)
- Aligns with AWS + Databricks architecture
- Uses standard, well-understood technology (PostgreSQL)
- Enables BQ-001 and BQ-003 which require the watchlist/alert configuration
- Fivetran remains optional (D-001) — if plan/account doesn't support Databricks destination, P8 can be formally skipped with documented reason

### Negative / Limitations
- RDS is a persistent resource that incurs cost even when stopped (storage)
- Adds networking complexity (VPC, security groups, Fivetran IP allowlisting)
- Must be created in the persistent Terraform stack (not ephemeral)
- Requires careful credential management (Secrets Manager)

## Scope Limitation

**IMPORTANT:**

RDS is **NOT** a general-purpose platform database.

RDS is approved **ONLY** for the operational PostgreSQL source defined by this ADR (`macro_watchlist_db`).

It must **NOT** become:
- Analytical storage
- Data warehouse
- General ETL staging
- Unrelated application storage

The actual RDS resource is a later-phase implementation item (P1 persistent stack for infrastructure, P8 for Fivetran integration).

## Related

- D-001: Fivetran is optional
- D-002: APIs use S3 as immutable raw storage; Fivetran writes directly to Databricks
- D-006: Terraform starts in P1; AWS infrastructure split into persistent and ephemeral stacks
- ADR-001: Bronze loading (API path)
- ADR-003: dbt runner (both paths converge at dbt)
- P8: Fivetran ingestion path
- docs/data-sources.md: macro_watchlist_db source definition
- docs/business-questions.md: BQ-001, BQ-003 require this source