# ADR-011: Compute and Budget Model for Streaming and Large-Volume Extensions

## Status

Proposed

## Context

The original platform was designed around a small, batch-only footprint:

- Six-month budget guardrail of about US$10/month for the persistent AWS stack.
- Databricks Free Edition for the workspace and SQL Warehouse.
- MWAA and a NAT Gateway used only in short, deliberate work windows (ADR-004).

The replanned platform keeps those constraints for the batch path: only NASA FIRMS still runs inside the small budget. The other five sources are always-on and break that envelope:

1. **Always-on ingestion** (EMSC, AISstream, USGS Water Data, NOAA buoys, GDACS) needs a producer container (ADR-010, Proposed), a Kinesis stream with 24-hour retention, a Databricks Structured Streaming job, and checkpoints. None of these are covered by the batch guardrail, and the producers cannot be turned off without abandoning the freshness claim.
2. **Large-volume extensions** (for example, a wider FIRMS area, denser vessel traffic, or longer retention) can exceed Free Edition and TB-scale assumptions.

Afonso has directed that always-on streaming and the large-volume extensions are **not bound by the US$10/month guardrail or by Free Edition limits**. What has not been decided is which compute tier and which budget envelope govern them, and how spend is stopped when the streaming root is destroyed.

Current state of the account matters: Databricks Free Edition has usage limits, and the AWS account has budgets and alerts (per the persistent stack). This ADR must not invent monthly figures. The cap is **to be set by Afonso**, based on real prices measured while the streaming root is applied.

## Decision Being Considered

Which compute tier (workspace/SQL/Jobs) should run streaming and large-volume workloads, and which budget envelope and stop procedure should govern that spend, given that it is deliberately outside the US$10/month batch guardrail?

## Options

### Option 1: Keep Free Edition, smallest compute, monthly cap and manual stop

Keep Databricks Free Edition and the smallest available compute for the streaming job; run streaming while the streaming root is applied; set a monthly budget cap and tear everything down to stop spend.

**Trade-offs:**
- Pros: No new Databricks spend commitment; consistent with the existing portfolio budget story; forces a clean start/stop runbook.
- Cons: Free Edition limits may block a 24/7 streaming job or the required Kinesis connector behavior; a monthly cap plus manual stop still requires someone to notice the budget alert; the platform may spend more time being rebuilt than running.
- Best use: proving the streaming path cheaply before committing to paid compute.

### Option 2: Paid workspace tier with serverless/Jobs compute

Move the Databricks workspace (or only the streaming workload) to a paid tier with serverless or Jobs compute sized for the stream, and keep the batch path on the free/smallest footprint.

**Trade-offs:**
- Pros: A real 24/7 streaming deployment is feasible; serverless avoids a permanently running cluster; the platform demonstrates cost-aware tiering.
- Cons: Introduces recurring Databricks spend; requires a clear account/workspace decision and Afonso's budget approval; more Terraform and account configuration; a paid tier is a larger change than the rest of the portfolio.
- Best use: the durable streaming deployment once the path is proven.

### Option 3: No fixed cap, alerts only

Run the streaming and large-volume work with budget alerts but no hard monthly cap, relying on Afonso to notice the alerts and destroy the streaming root manually.

**Trade-offs:**
- Pros: Maximum flexibility for spikes and experiments; no artificial ceiling on a portfolio demonstration.
- Cons: Weakest cost discipline; an unattended producer or stream can accumulate charges; contradicts the project's documented cost-awareness goal.
- Best use: not recommended as the default.

## Consequences

### Architecture

- Option 1 and Option 2 both require the streaming Terraform root (`aws/streaming`) and the Databricks streaming job described in ADR-008. Option 2 may also require changes to the Databricks Terraform stack and account tier.
- The batch path keeps the current persistent stack, MWAA windows, and SQL Warehouse auto-stop.

### Cost

- The batch guardrail (about US$10/month) stays in force for the batch path only.
- The streaming/large-volume envelope is separate. The exact monthly cap is **to be set by Afonso** after the first measured period. This ADR does not assume a figure.
- Every time the streaming root is applied, the expected resources and the exact stop/destroy commands must be documented. Creation and deletion time also bills.

### Operations

- Each option needs a documented start/stop runbook and a check that Kinesis, the producer, and the Databricks job are actually stopped afterwards.
- Option 1 adds repeated rebuild work; Option 2 needs a stable, always-on operational posture; Option 3 needs manual vigilance.
- Budget alerts must be verified before the first paid streaming run.

### Security

- No change to the secrets model: AISstream keys and Databricks tokens stay in Secrets Manager or the platform's secret mechanism.
- A paid Databricks tier may change workspace/account permissions, which must be reviewed against ADR-006 (least privilege).

### Developer experience

- Option 1 keeps the local/Free Edition workflow but limits what can be demonstrated.
- Option 2 is a more realistic deployment but requires account and budget setup.
- Option 3 is the least structured and should not be the default.

### Timeline

- Option 1 can start as soon as ADR-008 and ADR-010 are Accepted.
- Option 2 adds a budget approval and account/tier change before the durable streaming phase.
- Option 3 imposes no setup but risks cost surprises.

## Decision

*To be filled when Accepted: which option was chosen and why.*

## Related

- ADR-008: Streaming ingestion path (EMSC, AISstream, USGS Water Data, NOAA buoys, GDACS → Kinesis → Databricks)
- ADR-010: Where the always-on ingestion producers run (Proposed)
- ADR-004: MWAA ephemeral operating model and window costs
- ADR-006: Unity Catalog grants in dev (permissions if the Databricks tier changes)
- `docs/NOTION_PROJECT_PLAN.md`: P4c always-on foundation, P8b AISstream scale-out, and budget rules
- `AGENTS.md`: "Monitoring and cost control"
