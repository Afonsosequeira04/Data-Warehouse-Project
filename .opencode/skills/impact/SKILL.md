---
name: impact
description: Use before changing a table, a column, a function, a DAG task, a Terraform resource or a dbt model, to find what it is built from, what depends on it, which tests and business questions cover it, and the safe order of the change. Never makes the change.
---

# Impact

The job: answer "if I change this, what breaks" before the change is made.

Input: the table, column, function, file or model to change.

## Ground rules

- Talk to Afonso in European Portuguese. The report page is in European Portuguese.
- Read-only. Follow "Permissions and safety" in `AGENTS.md`. No cloud calls, no credentials.
- A dependency is one you found in the code, the SQL, the tests, the Terraform or the docs, with file and line. If you cannot find it, tag it `[guess]` and say so. Never invent a dependency.
- Tag every statement `[high]`, `[med]` or `[guess]`.

## Steps

1. Name the thing to change and the kind of change (rename, type change, drop, new column, new behaviour).
2. Upstream: what it is built from. For data: API client, then raw S3 path, then Bronze SQL (`ingestion/sql/`), then dbt sources and models once they exist. For code: the functions and modules it calls.
3. Downstream: search the whole repo (`grep -rn`) for the name in Python, DAGs, SQL, Terraform, tests, fixtures, docs and, once it exists, dbt `ref()` and `source()`. List each hit with file and line.
4. Consumers: map the affected tables to the business questions and data-quality questions in `docs/business-questions.md` (BQ-001 to BQ-003, DQ-001 to DQ-007) and to the Gold models listed there.
5. Tests and checks that cover it, and the ones that will break (`tests/`, fixtures, DAG import test, dbt tests).
6. Infrastructure and governance: Unity Catalog grants, external locations, secrets, IAM policies and ADRs that mention it.
7. Blast radius in numbers: files, tables, tests, DAG tasks, business questions affected.
8. The safe order of the change: what to change first, what to rebuild, what to compare before and after, which manual steps Afonso must do (anything that needs `terraform apply`, a Databricks change or a Fivetran change is his).
9. Give the result as one web page.

## Output

One self-contained HTML file `reports/impact-<thing>.html` (git-ignored; inline CSS, no external fonts, scripts or network calls): the numbers on top, a simple upstream and downstream diagram (inline SVG or nested lists), then the hits table, the tests, the business questions and the safe order of the change. Tell Afonso the path.

## Reads

- the whole repo, read-only

## Writes

- the report page only

## Never

- Never makes the change. Never runs a build, a deploy or a cloud command.

<!-- Adapted from DataWithBaraa/claude-code-data-engineering-skills (MIT). See ../NOTICE.md. -->
