# ADR-009: Source Discovery Agent (P12)

## Status

Proposed

## Direction

Directed by Afonso on 2026-11-06:

- P12 is a regular phase in the project roadmap and counts toward portfolio completion. It is not optional and there is no formal-skip escape hatch.
- Discovery is not limited to Portuguese or European sources: it covers public sources of any geography, subject to the source selection criteria in `docs/data-sources.md`.
- The intended direction is option 2: the agent only proposes sources (an issue or a docs PR). Afonso reviews and integrates accepted sources through the normal phase or chore flow. No YAML-spec refactor and no generic loader.

## Context

The core platform ingests from six selected public sources for an Earth-monitoring platform: EMSC (earthquakes), AISstream (vessel positions), NASA FIRMS (fires), USGS Water Data (gauges), NOAA buoys and GDACS (disaster alerts). They mix streaming, batch and polling ingestion shapes. Adding another source today means hand-writing a client or producer, a DAG or streaming stage, validation, tests, and dbt models. Public sources of any geography (national statistics offices, open-data portals, electricity prices, transport feeds) publish daily or hourly data, and expanding coverage is a natural extension of the portfolio.

The project plan includes P12, where an OpenCode agent runs on GitHub Actions and proposes new public sources. It has three layers:

1. **Pipeline**: MWAA + Databricks (existing architecture, unchanged)
2. **Discovery agent**: OpenCode on GitHub Actions, weekly schedule; no AWS or Databricks credentials; repository permissions limited to `contents: write` and `pull-requests: write`
3. **Afonso**: reviews the proposal, assigns the business-question number, and integrates the accepted source

This ADR is Proposed. No implementation may start until it is Accepted and P9 (CI/CD with OIDC) is merged.

Constraints already decided elsewhere apply:

- Secrets never enter Git (AGENTS.md); source API keys stay in AWS Secrets Manager.
- The repository is public.
- The agent must not replace the documented architecture or act on the production pipeline.

## Decision Being Considered

Should the project include an agent that discovers and proposes new public data sources (P12), and, if so, at what level of autonomy: propose only, propose plus integration PRs, or auto-merge in dev?

## Options

### Option 1: No agent - sources chosen manually

Keep source selection manual. New sources are chosen by Afonso, and ingestion code is written case by case, as with the six current sources.

**Trade-offs:**
- Pros: No new moving parts, no model cost, no new security surface; consistent with the current client-per-API design.
- Cons: Slow to extend; no demonstration of agent-assisted engineering; the platform keeps only two low-frequency sources.

### Option 2: Agent proposes only (level 1)

A weekly GitHub Actions job runs OpenCode with a strict prompt: inspect candidate public sources, validate license and access method, and open a proposal (issue or docs PR) describing the source and its value. No ingestion code is generated.

**Trade-offs:**
- Pros: Low risk; no write access beyond issues and docs; humans do all integration work; validates the discovery idea cheaply.
- Cons: Afonso still writes all ingestion code; partial value for the effort.

### Option 3: Agent proposes and opens integration PRs (level 2)

The weekly job also generates a YAML source spec, a dbt staging model, tests, and a DAG entry, then opens an integration PR. Requires refactoring API ingestion to declarative YAML source specs (the current six sources, new source). Nothing merges without Afonso's review.

**Trade-offs:**
- Pros: End-to-end demonstration of governed agent-assisted delivery; a new source reaches Bronze after one review; keeps secrets and cloud access out of the agent.
- Cons: Requires the YAML-spec refactor, which conflicts with the current client-per-API convention and the AGENTS.md warning on generic frameworks; larger review surface per PR.

### Option 4: Agent auto-merges in dev (level 3)

As option 3, but the agent may merge its own PRs in a development environment or branch after green CI; production stays manual.

**Trade-offs:**
- Pros: Fastest iteration; shows a full autonomous loop.
- Cons: Highest risk on a public repository; unreviewed generated code can touch ingestion paths; hard to bound model behavior; disproportionate for a portfolio.

## Open Questions (blocking Acceptance)

Any proposed source must satisfy the selection criteria in `docs/data-sources.md` before it is considered: a real analytical need tied to an approved business question, real external data, free or free-tier access, a documented access method, a licence compatible with the project, and a volume appropriate to the portfolio scope. Geography is not a criterion.

- **Model and provider**: which model/provider runs the agent, and what spending limit applies to the GitHub Actions job?
- **REA acceptability**: may the agent use REA (github.com/morluto/rea, MIT) to investigate a source with no documented access, and what terms-of-use policy approves a target URL before any fetch?
- **GitHub plan**: does the repository's plan support environments with required reviewers for the agent's proposal workflow?
- **Write access**: GitHub App installation or `GITHUB_TOKEN` for opening PRs?

## Consequences

Describe the implications of each option on:
- **Architecture**: options 3 and 4 add a YAML spec layer and a generic loader to the ingestion path; options 1 and 2 keep the current client-per-source design.
- **Cost**: GitHub Actions minutes plus model/API cost per run for options 2-4, bounded by a spending limit and a job timeout; options 3 and 4 add no cloud cost by themselves.
- **Operations**: a new scheduled workflow to monitor and maintain; failed agent runs must be visible and must not affect the daily pipeline; REA runs, if allowed, stay manual and time-boxed.
- **Security**: the repository is public; the agent receives no AWS/Databricks credentials, only repository write scoped to pull requests; secrets live only in GitHub repository secrets with a provider spending limit; actions pinned by SHA; branch protection on main; no comment-triggered runs.
- **Developer experience**: options 3 and 4 change how new sources are added (spec plus generated code, reviewed via PR) and require the YAML refactor first.
- **Timeline**: option 2 is small; options 3 and 4 require the refactor and land after P9 and after any accepted AGENTS.md amendment.

## Decision

*To be filled when Accepted: which option was chosen and why.*

## Related

- `docs/NOTION_PROJECT_PLAN.md` section `# 12b. P12` (tasks and Definition of Done)
- ADR-003 (where dbt runs), ADR-004 (MWAA operating model), and P9 (CI/CD with OIDC) - the agent integrates with the existing CI/CD, not with a new one
- REA: https://github.com/morluto/rea (MIT)
- AGENTS.md rules on secrets, scope, and framework avoidance
