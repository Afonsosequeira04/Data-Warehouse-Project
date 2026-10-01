# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records for the Cloud Data Platform project.

## ADR Index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](ADR-001-bronze-loading.md) | How Bronze is loaded from raw JSON in S3 | Accepted |
| [ADR-002](ADR-002-quarantine-boundary.md) | Quarantine boundary: file/schema vs row level | Accepted |
| [ADR-003](ADR-003-dbt-runner.md) | Where dbt runs in the daily DAG | Accepted |
| [ADR-004](ADR-004-mwaa-operating-model.md) | MWAA ephemeral operating model | Accepted |
| [ADR-005](ADR-005-rds-operational-source.md) | Amazon RDS PostgreSQL as the operational source for Fivetran | Accepted |
| [ADR-006](ADR-006-unity-catalog-grants-dev.md) | Unity Catalog grants in dev with single principal | Accepted |

## ADR Lifecycle

- **Proposed**: Draft written, under review, not yet accepted
- **Accepted**: Decision approved by Afonso, implementation may proceed
- **Superseded**: Replaced by a later ADR

## ADR Template

Use [ADR-template.md](ADR-template.md) when creating new ADRs.

## Process

1. OpenCode may draft Proposed ADRs
2. Only Afonso moves an ADR to Accepted
3. When a decision changes, create a new ADR that supersedes the old one
4. Never delete ADRs; mark them Superseded instead