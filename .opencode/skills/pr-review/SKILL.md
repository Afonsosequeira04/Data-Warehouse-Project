---
name: pr-review
description: Use before a pull request is merged, or when asked to review a branch, a diff or a file, to review it pass by pass against this repo's AGENTS.md, ADRs and current phase, and write a report with findings and a verdict. It never edits, pushes or merges.
---

# Pull request review

The job: review one change in fixed passes, in this order, and report every finding with its fix. Afonso reviews and merges on GitHub; this skill prepares that review.

Input: a branch, the current diff, or a file. Default: the current branch against `origin/main`.

## Ground rules

- Talk to Afonso in European Portuguese. The report page is in European Portuguese. Anything written into the repo is in English (this skill writes nothing into the repo).
- Read-only. Follow "Permissions and safety" in `AGENTS.md`. Never read or print credentials, `.env`, `terraform.tfvars`, state or plan files.
- Tag every finding `[high]` (you checked it and can show the command or the line), `[med]` (likely) or `[guess]` (you do not know). Never present a `[guess]` as a fact.
- Never write "should pass". Run the check, or say it was not run and why.

## Steps

1. Scope: `git fetch origin --prune`, then `git log --oneline origin/main..HEAD` and `git diff --stat origin/main...HEAD`. Say which phase or chore the branch is, and read the matching section of `docs/NOTION_PROJECT_PLAN.md` and the ADRs it references.
2. Phase discipline: the change only does the current phase's tasks (see "Current phase" in `AGENTS.md`). Flag anything that belongs to a later phase, depends on an ADR that is still Proposed (ADR-008, ADR-009), or edits the "Current phase" block without the Definition of Done being met.
3. Security (the repo is PUBLIC): secrets in code or docs; `git ls-files | grep -E "\.env|tfstate|tfvars|profiles\.yml" | grep -v "\.example$"` must print nothing (`terraform.tfvars.example` is allowed on purpose); IAM least privilege; no long-lived AWS keys in workflows; no credentials logged.
4. Correctness: raw S3 objects are never overwritten (ingestion-date path, batch id); a retry or rerun gives the same result; pagination, rate limits and retries are bounded; the response shape is validated before a write counts as success.
5. Tests: new behaviour has tests, with synthetic fixtures under `tests/fixtures/`; a failure path is covered; run the narrowest relevant `pytest` and report the exact command and result.
6. Architecture: the rules in "Non-negotiable architecture rules" and the decisions D-001 to D-006; no new AWS service outside the documented scope; business logic lives in dbt, not in Python or DAGs; DAG files describe orchestration only.
7. Infrastructure (only if `.tf` files changed): persistent vs ephemeral stack separation, `prevent_destroy` on the raw bucket, tags, no hard-coded account ids or paths. Run `terraform fmt -check`; run `validate` or `plan` only if they work without credentials, otherwise say they were not run. Never `apply`.
8. Cost: anything that can leave a billable resource running (MWAA, NAT Gateway, SQL Warehouse) is stated with window, estimated cost and the exact destroy command.
9. Portability: absolute paths such as `/Users/...`, machine-specific settings, files that only work on one laptop.
10. Duplication and style: code that already exists in the repo; conventional commit prefixes; branch name (`feat/pX-...`, `chore/...`); English in the repo.
11. Documentation: README, ADR statuses, `docs/data-sources.md`, runbooks and `docs/evidence/` match the change.
12. For every finding: risk (high, medium, low), file and line, the rule it breaks (quote the section of `AGENTS.md` or the ADR number), and the suggested change.
13. Verdict: `approve` or `changes requested`, with the list of what blocks the merge.

## Pushback

A finding that Afonso declines stays in the report as declined, with his reason. It is never dropped and never quietly downgraded.

## Output

One self-contained HTML file `reports/pr-review-<branch>.html` (create `reports/` if needed; it is git-ignored). Inline CSS, no external fonts, scripts or network calls. Layout: the change and the verdict on top, then the findings with the code, the rule and the suggested change, high risk first, then the checks that were run and the ones that were not. Tell Afonso the path and that he can open it with `open reports/<file>.html`.

## Reads

- the change, `AGENTS.md`, the plan, the ADRs, the tests

## Writes

- the report page only

## Never

- Never edits the change, never commits, never pushes, never merges, never comments on the PR.
- Never runs `terraform apply`, `destroy`, `import` or any command that touches AWS, Databricks or Fivetran.

<!-- Adapted from DataWithBaraa/claude-code-data-engineering-skills (MIT). See ../NOTICE.md. -->
