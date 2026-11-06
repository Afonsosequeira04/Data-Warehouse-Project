---
name: profile
description: Use when a new data source, a recorded API payload, a sample file or a query result needs to be understood before any ingestion, dbt or quarantine rule is written, to profile its format, schema, quality, bad records, relationships and gaps. Writes only a report page.
---

# Profile

The job: understand new data before anything is built on it. It writes nothing but the report.

Input: a folder, a file or a sample, for example a recorded JSON payload, a CSV export, or a result Afonso pasted from a read-only query.

## Ground rules

- Talk to Afonso in European Portuguese. The report page is in European Portuguese.
- Only profile data you were given as files or pasted samples. Do not call a real API and do not connect to S3, Databricks, Supabase or Fivetran. If more data is needed, tell Afonso exactly which read-only query or export to run.
- Count with scripts, never by eye. Put the scripts in a scratch folder outside the repo (for example `/tmp/profile-<name>/`) and use the Python standard library or what is already installed. Do not add dependencies.
- Never read credentials. Show personal data masked, if any appears.
- Tag every finding `[high]`, `[med]` or `[guess]`.

## Steps

1. Format: file type, encoding, delimiter and quoting, null tokens, decimal separators, date formats. A format is what the values show, never a guess.
2. Schema: fields, types, row counts, nested structures, and differences between pages or files (schema drift).
3. Quality: nulls, empty or constant fields, duplicate rows, and whether the intended key (see the grain in `docs/data-sources.md`) is unique.
4. Bad records: corrupt records, values out of range, placeholder values the source uses for "no value".
5. Relationships: for every key that should match another source (for example watchlist countries against World Bank country codes), the orphans on each side.
6. Gaps: missing years, dates or periods; series that never change; how the source marks a deleted or revised row.
7. Compare with `docs/data-sources.md`: expected grain, volume and fields against what arrived.
8. Rank the findings. Each one has the rows it affects and the decision it needs, marked for one of: ingestion validation (structural), quarantine or dbt rule (semantic, see ADR-002), dbt staging, or documentation.
9. Give the result as one web page, with the input for the ingestion code and the dbt staging models at the end.

## Output

One self-contained HTML file `reports/profile-<name>.html` (git-ignored; inline CSS, no external fonts, scripts or network calls): the numbers on top, one section per check with a table, the ranked findings, and the inputs for ingestion and dbt last. Tell Afonso the path.

## Reads

- the files or samples given, read-only, and `docs/data-sources.md`

## Writes

- the report page only (scratch scripts go outside the repo and are deleted when done)

## Never

- Never changes a file of the project. Never guesses a format. Never calls a real API or the cloud.

<!-- Adapted from DataWithBaraa/claude-code-data-engineering-skills (MIT). See ../NOTICE.md. -->
