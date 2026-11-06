---
name: knowledge-refresh
description: Use after a phase is merged, or when documentation seems out of date, to compare the knowledge the agent reads (AGENTS.md, README, plan, ADRs, data sources, runbooks) with the real code and files, and propose what is stale, missing or wrong. It proposes first and writes only what Afonso approves.
---

# Knowledge refresh

The job: keep the documents the agent reads true to the repo. It proposes; after Afonso's yes it writes only the approved changes.

Input: none, or an area (for example `README`, `ADRs`, `plan`).

## Ground rules

- Talk to Afonso in European Portuguese. Anything written into the repo is in English.
- Read-only until the yes. Follow "Permissions and safety" in `AGENTS.md`.
- Tag every proposal `[high]` (checked, with evidence), `[med]` or `[guess]`. Only `[high]` proposals can be applied without asking again about the evidence.
- Never read or print credentials, `.env`, `terraform.tfvars`, state or plan files.

## Steps

1. Inventory the real repo: `git ls-files`, then the folders that exist versus the folders the documents name.
2. `AGENTS.md`: the "Current phase" block against the plan checkboxes, `docs/evidence/` and `git log`; the "Current repository state" paragraph against the real tree; the ADR table against the ADR files; the repository structure diagram against the tree.
3. `README.md`: roadmap checkboxes, repository structure, stack table and "Getting Started" commands against what exists (paths, requirements files, folders that are not created yet).
4. `docs/NOTION_PROJECT_PLAN.md`: task checkboxes against the code, the tests and the evidence files; phases marked done that have no evidence, and evidence with unticked tasks.
5. `docs/decisions/`: every ADR status, the decision log in `docs/data-sources.md`, and the AGENTS.md table must agree. Superseded ADRs point to the one that replaced them.
6. `docs/data-sources.md` and `docs/business-questions.md` against the code: raw S3 path patterns, Bronze table names, indicators and series, expected volumes.
7. Runbooks (`docs/runbooks/`): the commands and names still exist in the Terraform and scripts.
8. Things you cannot edit (the architecture image, the PDF datasheet): list them as "needs Afonso", with what looks different from the text documents.
9. Keep it short: text that repeats another file is cut and linked.
10. Report each finding as a proposal: file, what it says, what is true, evidence, the change.

## Applying

After Afonso approves some or all proposals:

1. Check `git branch --show-current`. If it is `main`, create `docs/knowledge-refresh-<yyyy-mm-dd>` first. Stop if the working tree is dirty.
2. Write only the approved changes. One logical commit per document, conventional prefix `docs:`.
3. Never change the "Current phase" block unless Afonso says so explicitly for that line.
4. Follow the "Publishing" steps in `AGENTS.md`, then stop.

## Output

A numbered list of proposals in the chat. If there are more than ten, also write `reports/knowledge-refresh-<date>.html` (git-ignored, self-contained, no network).

## Reads

- the documents, the code, the tests, the Terraform, the evidence files, `git log`

## Writes

- nothing until the yes; then only the approved documents on a `docs/...` branch

## Never

- Never applies a change without the yes. Never touches `main`. Never merges.

<!-- Adapted from DataWithBaraa/claude-code-data-engineering-skills (MIT). See ../NOTICE.md. -->
