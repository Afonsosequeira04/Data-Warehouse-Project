---
name: test-data
description: Use when a client, DAG task, SQL file or dbt model needs tests, to write synthetic test data with the edge cases and the expected result written first, following the fixture conventions of this repo. Never uses real data and never calls the cloud.
---

# Test data

The job: small synthetic fixtures with the edge cases, and the expected result decided before the code is run.

Input: the function, task, SQL file or model under test (for example `ingestion/core/http.py`).

## Ground rules

- Talk to Afonso in European Portuguese. Fixtures, tests and comments are in English.
- Synthetic data only. Never call a real API, S3, Databricks or Fivetran, and never read real data or credentials.
- Follow the existing style: look at `tests/conftest.py` and `tests/fixtures/<source>/` before you write anything, and reuse the helpers that exist.
- Do not add dependencies (`pyproject.toml`). Use what is already installed.
- Only write inside `tests/` (and, once it exists, the test folders of the dbt project). Never write under data or source folders.
- Work only on the current phase (see `AGENTS.md`). Say so and stop if the task belongs to a later phase.

## Steps

1. Name the thing under test and, for each edge case, what it must do.
2. Read the existing fixtures and tests for the same source, so the new fixtures have the same shape as the recorded API payloads.
3. Write the expected result first: a short table (input case, expected output or error) in the test file's docstring or in a comment block, before the test code.
4. Cases to consider, only those that apply:
   - a page boundary (last page, empty page, one more page than expected);
   - an API error payload and a payload with the wrong shape;
   - missing fields, nulls, and placeholder values the source uses for "no value";
   - duplicate observations and out-of-order rows;
   - a retry after a partial failure (the second call must not corrupt or overwrite the first batch);
   - a second delivery with a renamed or new field (schema drift) that validation must stop;
   - for the quarantine work (ADR-002): one record that is structurally invalid (rejected at ingestion) and one that is semantically invalid (rejected in dbt), each with the reason it must carry.
5. Put fixtures in `tests/fixtures/<source>/`, one small file per case, named for the case.
6. Write the tests beside the existing ones, comparing the result with the expected result from step 3.
7. Run the narrowest `pytest` command and report the exact command and which tests passed or failed. Never write "should pass".

## Output

The fixture files and the test file(s), plus a short summary in the chat: cases covered, cases deliberately left out, the command that was run and its result.

## Reads

- the code under test, existing tests and fixtures, `docs/data-sources.md`

## Writes

- fixtures and tests under `tests/`

## Never

- Never uses real or production data. Never calls the network. Never edits the code under test (if the test shows a bug, report it).

<!-- Adapted from DataWithBaraa/claude-code-data-engineering-skills (MIT). See ../NOTICE.md. -->
