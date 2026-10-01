# ADR-006: Unity Catalog Grants in Dev Environment

## Status

Accepted

## Context

The project uses Databricks Free Edition, which provides a single workspace with a single metastore. In this environment, the only available Unity Catalog principal is `account users`. The initial implementation attempted to model three distinct roles (pipeline, BI, developer) using separate `databricks_grant` resources per role per object. However, `databricks_grant` is authoritative by principal and securable object. When multiple grants target the same principal (`account users`) on the same object, they collide — Terraform cannot apply multiple grants for the same principal/object pair, and the provider reports a conflict.

Constraints:
- Free Edition workspace with one metastore
- Only principal available is `account users`
- Need to support three logical roles: pipeline (write), BI (read gold), developer (read all)
- `CREATE_EXTERNAL_TABLE` privilege only applies to external locations, not schemas

## Decision Being Considered

How to model role-based Unity Catalog grants when only one principal (`account users`) is available in the dev environment, while keeping the design extensible for future groups.

## Options

### Option 1: Single `databricks_grants` per object with merged privileges

Use one `databricks_grants` resource per securable object (catalog, schemas, external locations). Map logical roles to principals via variables (`uc_principal_pipeline`, `uc_principal_bi`, `uc_principal_developer`). When multiple roles share the same principal (as in dev), merge their privilege sets (union) so the single grant contains all needed privileges.

**Trade-offs:**
- Pros:
  - No Terraform conflicts; one grant per object
  - Extensible: when real groups exist, just change variables to point to different principals
  - BI access restricted to gold schema only (by not including it in other schema grants)
  - `CREATE_EXTERNAL_TABLE` correctly placed only on external locations
- Cons:
  - In dev, all three roles collapse to `account users`, so no actual separation of access

### Option 2: Separate grants with distinct principals (requires groups)

Wait to implement role-based grants until Databricks groups are provisioned.

**Trade-offs:**
- Pros:
  - Clean separation of duties from the start
- Cons:
  - Blocks P1 completion; groups may not be available in Free Edition
  - Requires infrastructure outside Terraform (group provisioning)

### Option 3: Use single `account users` grant with all privileges everywhere

Give `account users` all privileges on all objects.

**Trade-offs:**
- Pros:
  - Simple, no conflicts
- Cons:
  - No least privilege; BI gets write access to everything
  - No audit trail of intended role boundaries
  - Hard to migrate to real groups later

## Consequences

| Aspect | Impact |
|--------|--------|
| Architecture | Single `databricks_grants` per object; roles mapped via variables |
| Cost | No additional cost |
| Operations | In dev, all roles collapse to `account users` — no real separation |
| Security | Least privilege modeled in code; actual enforcement deferred to when groups exist |
| Developer Experience | Variables make intent clear; easy to migrate by changing `uc_principal_*` |
| Timeline | Unblocks P1; revisit in P11 when groups are available |

## Decision

**Option 1: Single `databricks_grants` per object with merged privileges.**

Implementation:
- One `databricks_grants` per catalog, per schema, per external location
- Roles mapped to principals via `uc_principal_pipeline`, `uc_principal_bi`, `uc_principal_developer` variables
- When multiple roles map to same principal (dev: all three = `account users`), privileges are merged (union)
- BI only gets privileges on gold schema (not on raw, silver, bronze)
- `CREATE_EXTERNAL_TABLE` only on external locations, not schemas

## Related

- ADR-001 (Bronze loading), ADR-002 (Quarantine boundary), ADR-003 (dbt runner)
- Terraform: `infra/terraform/databricks/unity_catalog.tf` (grants)
- Variables: `uc_principal_pipeline`, `uc_principal_bi`, `uc_principal_developer` in `infra/terraform/databricks/variables.tf`
- P11: Revisit when Databricks groups are provisioned