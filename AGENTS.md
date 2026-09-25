# Agent Guide - Data Warehouse Project

## 🚧 Modernization in progress
- Roadmap: see `PLANO_MODERNIZACAO.md` in repo root — phased plan (dbt, Docker, Airflow, CI/CD, live lineage via OpenLineage/Marquez).
- Current phase: **Fase 6 (Histórico e cargas incrementais) — not started yet.**
- Rule for agents: only implement the phase explicitly requested in the prompt. Do not jump ahead to a later phase even if it seems convenient.
- **Branch workflow (mandatory):** before touching any file, run `git branch` to check the current branch. If on `main`, create and switch to the phase branch first (`git checkout -b fase-N-nome`). Never commit phase work directly to `main` — all phase work is committed to its own branch and merged via Pull Request, reviewed by the project owner before merge. Never merge and never push to `main` yourself.

### Lifecycle of a phase
1. **Start:** run the automatic cleanup of the previous phase (see "Post-merge cleanup"), then create the phase branch from an up-to-date `main`.
2. **Work:** implement only the requested phase, following its Definition of Done.
3. **Phase closing** (below).
4. **Publishing** (below): push the branch and open the PR.
5. **Owner:** reviews and merges the PR on GitHub. The agent never merges.
6. **Cleanup:** when the next phase starts (or when the owner asks), local `main` is synced with GitHub and the merged phase branch is deleted.

### Phase closing (agent does this, automatically)
When — and only when — **every Definition of Done item of the phase has been verified by you** (commands run, results seen), make one last commit on the phase branch, titled `docs: close Fase N`, that does exactly this:
1. Update the "Current phase" line above to the next phase, using its title from `PLANO_MODERNIZACAO.md`: `**Fase N+1 (<title>) — not started yet.**` If the closed phase was Fase 10, write `**Roadmap complete.**`
2. Tick the closed phase's checkboxes (`- [x]`) in `PLANO_MODERNIZACAO.md`. Tick only what was really done.
3. Make sure `README.md` and this file match reality (commands, targets and paths that they mention must exist).
4. Update `docs/HUB.md`: mark the closed phase ✅ and the next one 🔜 in the status table and the roadmap diagram (`:::done` / `:::next`), update the **Status** line, and refresh row counts or tool availability if they changed.

Guardrails:
- This must be the **last commit of the phase's work**. Only housekeeping commits explicitly authorized by the owner may follow it. The line reaches `main` only when the owner merges the PR.
- If any Definition of Done item failed, could not be verified (e.g. needs a UI check) or a validation difference is unexplained: **do not advance the line.** Leave it as is and list the pending items in the final summary.
- Never start the next phase. Never touch the "Current phase" line at any other moment.

### Publishing (agent does this, automatically, after Phase closing)
Standing authorization: this applies to every phase; prompts do not need to repeat it. Run it only if Phase closing was completed (the "Current phase" line was advanced). If it was not, do not push: report the pending items.
The repo is **PUBLIC** — everything pushed is visible to anyone. Steps:
1. Pre-push checks. If any fails, stop and report; do not push.
   - `git branch --show-current` is the phase branch, never `main`.
   - `git status --short` is empty.
   - `git ls-files | grep -E "\.env$|\.venv|target/|logs/"` prints nothing.
   - `git remote get-url origin` points to the owner's repo. Show `git log --oneline main..HEAD` and `git diff --stat main`.
2. `git push -u origin <phase-branch>`. Never push to `main`, never force-push (`--force`, `--force-with-lease`), never delete remote branches (the only exception is "Post-merge cleanup" below). If the push asks for credentials or fails to authenticate, stop and report; do not configure tokens or credentials.
3. Open the PR against `main`, unless a PR for this branch already exists (then the push is enough). Write the final phase summary to a temporary file outside the repo (e.g. `/tmp/pr-body.md`). If `gh auth status` succeeds, run `gh pr create --base main --head <phase-branch> --title "Fase N — <title>" --body-file /tmp/pr-body.md`. Otherwise print the link `https://github.com/<owner>/<repo>/compare/main...<phase-branch>?expand=1` (derive owner/repo from `git remote get-url origin`).
4. Stop. The owner reviews and merges the PR. Never merge, close, approve or mark ready any PR.

### Post-merge cleanup
The merge happens on GitHub and you cannot know when it was approved, so run this only in two situations: (a) the owner asks (e.g. "cleanup Fase N"); (b) automatically as the first step of the next phase or chore, before creating its branch, for every leftover local phase or chore branch that is already merged. Never at any other time.
1. `git fetch origin --prune`
2. Verify the previous phase branch is really merged: `git merge-base --is-ancestor <phase-branch> origin/main` must succeed. If it fails (PR not merged, or squash/rebase-merged), stop, report and ask the owner; delete nothing and, in case (b), do not start the new phase. If the branch no longer exists locally, there is nothing to clean up: continue.
3. `git checkout main && git pull --ff-only origin main`. Local `main` must end identical to `origin/main` (`git rev-parse main origin/main` gives the same hash, `git status` clean). Never use `git reset --hard` or force-push; if the fast-forward fails, stop and report.
4. Delete the local branch with `git branch -d <phase-branch>` (never `-D`). Delete the remote one with `git push origin --delete <phase-branch>` only if it still exists (`git ls-remote --heads origin <phase-branch>`); GitHub may have deleted it already.
5. Report `git branch -a` and `git log --oneline -5`.

### Working rules
- **Read-only requests:** when asked to check, verify, test or audit, run read-only commands only. Never install packages, create venvs or files, run `dbt init`, or change git state unless explicitly asked. Report findings and ask before fixing.
- **Git hygiene:** stage files by explicit path, never `git add .` / `git add -A`. Show `git status --short` before every commit. Never commit `.venv/`, `target/`, `logs/`, `dbt_packages/` or `infra/.env`. One commit per step, with a clear message.
- **Scope guard:** no dbt-utils, snapshots, incremental models, quarantine tables, Airflow, CI/CD or observability until their own phases. Do not "improve" business logic while migrating it.
- **Legacy bugs are reported, not silently fixed.** List them in the final summary of the phase.
- **Destructive commands:** `make init-db` and `make all` / `make all-dbt` drop the whole warehouse database. Run them only when the prompt asks for it or after confirming with the owner.
- **Processes, services and volumes:** never kill processes or stop services outside this project's Docker containers (e.g. a local Postgres). Never run `docker compose down -v` unless the prompt asks for it. If a port is busy, stop and report.
- **Stop instead of improvising:** if a tool is missing (Docker not running, Python < 3.10, busy port 5432) or a validation shows unexplained differences, stop and report. Do not install anything globally.
- **Chores (non-phase work):** use a `chore/<name>` branch created from an up-to-date `main`. No Phase closing, and never touch the "Current phase" line. Publishing (push + PR) only when the prompt asks for it, following the Publishing steps.

## 🏗️ Architecture
- **Stack:** PostgreSQL 16 (Docker Compose) + `psql` CLI for ingestion + dbt-core / dbt-postgres for transformations.
- **Pattern:** Medallion (`bronze` -> staging -> marts).
- **Data Flow:** CRM/ERP CSVs -> Bronze (raw, `psql` COPY) -> Staging (dbt **tables**, schema `staging`) -> Marts (dbt **views**, schema `marts`).
- **Legacy:** the original plain-SQL Silver and Gold (`silver.*`, `gold.*`) are kept in `legacy_sql/` for reference and reconciliation until they are removed. They no longer feed the dbt models.
- **Repo layout:**
  - `datasets/` — source CSVs (mounted read-only into the container at `/data/datasets`)
  - `infra/` — `docker-compose.yml`, `.env.example` (`.env` is local and git-ignored)
  - `scripts/` — `init_database.sql` and `bronze/` (DDL, load procedure, header validation). Bronze ingestion stays outside dbt.
  - `legacy_sql/` — legacy `silver/` and `gold/` scripts (mounted read-only into the container at `/legacy_sql`)
  - `dbt_project/` — `models/staging`, `models/marts`, `macros/`, `profiles.yml`, `requirements.txt`
  - `docs/` — `HUB.md` (project hub: roadmap, lineage, tools, ports), `data_catalog.md`, diagrams, `baseline_fase3.md`, `validacao_fase3.md`

## 🧱 dbt conventions
- Naming: `stg_<source>__<table>` for staging (e.g. `stg_crm__cust_info`), `dim_*` and `fct_*` for marts.
- Use `{{ source('bronze', '<table>') }}` for Bronze and `{{ ref('<model>') }}` between models. **Never hardcode schema names in dbt SQL.**
- Every model has an entry in its folder's `_models.yml` (description of the main columns + tests). Bronze tables are declared in `models/staging/_sources.yml`.
- Only built-in dbt tests until Fase 4 (`not_null`, `unique`, `relationships`, `accepted_values`).
- Generic test arguments go under `arguments:` (e.g. `accepted_values: arguments: values: [...]`); the old top-level syntax is deprecated in dbt >= 1.10. New tests must use the new syntax; the existing Fase 3 tests are migrated in Fase 4.
- `dbt_project/profiles.yml` reads credentials from environment variables (`POSTGRES_*`) — no secrets in the repo.

## ⚙️ Operational Quirks
- **CSV Path Configuration:** `scripts/bronze/load_bronze.sql` uses a parameterised `datasets_dir` argument. In Docker, pass the container path `/data/datasets` via `psql -v datasets_dir="/data/datasets"`. On host, use `psql -v datasets_dir="$(pwd)/datasets"`.
- **Header Validation:** Run `scripts/bronze/validate_headers.sh` (or `make validate-headers`) to fail early if source CSV headers don't match `expected_headers.txt` — do this *before* the Bronze Load.
- **Database Name:** All scripts use `data_warehouse_project` consistently.
- **Busy host port 5432:** a local Postgres (e.g. Postgres.app) listening on `127.0.0.1:5432` shadows the container's `*:5432`, so host tools such as dbt connect to the wrong server (symptom: `role "data_warehouse" does not exist`). Do not kill it. Set `POSTGRES_PORT` (e.g. `5433`) in `infra/.env` — docker-compose maps `${POSTGRES_PORT:-5432}:5432` and dbt reads the same variable — then recreate the container (`make down && make up`).
- **dbt runs in two modes:**
  - **Host (dev/CI):** inside `.venv` (Python >= 3.10), via `make dbt-*` targets; connects to warehouse Postgres on `localhost:${POSTGRES_PORT}`.
  - **Airflow (production DAG):** inside the Airflow container (built from `infra/airflow.Dockerfile`), using the same `dbt_project/requirements.txt`; connects to warehouse Postgres on internal hostname `postgres:5432` (Docker network). A named volume `airflow_dbt_target` is mounted at `/opt/airflow/dbt_project/target` for writable dbt artifacts.
- **Schema names:** dbt writes to `staging` and `marts` thanks to the `generate_schema_name` macro in `dbt_project/macros/`. Without it the schemas become `public_staging` / `public_marts`.
- **Staging is a TABLE on purpose:** `scripts/bronze/ddl_bronze.sql` uses `DROP TABLE` without `CASCADE`, so dbt views over Bronze would make `make load-bronze` fail. Tables derived with `CREATE TABLE AS` do not block the drop.
- **CASCADE drop of marts views:** `dbt run --select staging` drops and recreates staging TABLES. Because marts models are VIEWS depending on staging, this CASCADE-drops the marts views. They are recreated only when `dbt run --select marts` runs next. If `dbt test --select staging` fails, the DAG stops and marts remain unavailable until the next successful run — intentional quarantine at orchestration level.
- **Never run `dbt run` / `dbt build` with `--select staging` alone.** Rebuilding a staging table cascade-drops the marts views that depend on it. Use `--select staging+` or a full `make dbt-build`.
- **`make init-db` (and therefore `make all` / `make all-dbt`) drops the whole database**, including the dbt schemas. After it, run `make dbt-build` again (`make all-dbt` already does).
- **Legacy quirk (known, not fixed):** re-running the legacy Silver DDL after the legacy Gold views exist fails on `DROP TABLE` (views depend on the tables), but `psql -f` still exits 0, so `make` reports success. For a legacy rebuild use `make all`.
- **`.gitignore` gotcha:** `.env.*` also matches `infra/.env.example`; the file needs `!.env.example` *after* that line. `git check-ignore -v` is misleading with negated patterns — verify with `git status` / `git ls-files` instead.
- **Never run `dbt docs serve`** from an agent (it blocks the terminal). Run `dbt docs generate`; the owner serves it with `make dbt-docs`.
- **Airflow dbt_packages fix (chore/airflow-hardening):** the `chown -R airflow:root /opt/airflow/dbt_project` in `infra/airflow.Dockerfile` must include the whole `dbt_project` directory (not just `target/`), otherwise `dbt deps` fails with `Permission denied: 'dbt_packages'`. The fix adds `dbt deps` at image build time and a `test -d dbt_packages/dbt_utils || exit 1` guard; the COPY of `dbt_project` is now read-only from host (`.dockerignore` excludes `dbt_packages/`, `target/`, `logs/` from the build context) so packages are always installed fresh in the image.

## 🚀 Commands

### Docker Compose + Make (recommended)
```bash
# Legacy pipeline from zero to Gold (bronze -> silver -> gold, plain SQL)
make all

# dbt pipeline from zero to Marts (bronze -> staging -> marts)
make all-dbt

# Step by step
make up                  # Start Postgres container
make init-db             # Drop/recreate database + schemas (DESTRUCTIVE)
make validate-headers    # Validate CSV headers on host (fail-fast)
make load-bronze         # Load Bronze layer (server-side COPY from /data/datasets)
make load-silver-legacy  # Legacy Silver load (plain SQL)
make load-gold-legacy    # Legacy Gold views (plain SQL)

# dbt
make dbt-setup           # Create .venv (Python >= 3.10) and install dbt from requirements.txt
make dbt-build           # dbt build: staging + marts + tests (always the full build)
make dbt-docs            # dbt docs generate + serve (owner only; blocks the terminal)

# Airflow (Fase 5+)
make airflow-build       # Build custom Airflow image (with dbt + postgresql-client)
make airflow-up          # Start Postgres + Airflow stack (--profile airflow)
make airflow-down        # Stop Airflow stack (preserves volumes)
make airflow-logs        # Follow Airflow container logs

# Utilities
make psql                # Open psql shell in container
make logs                # Follow container logs
make down                # Stop container (preserves data volume)
```

### Legacy psql (manual path management)
1. **Initialize DB:** `psql -f scripts/init_database.sql` (drops and recreates `data_warehouse_project`).
2. **Bronze DDL:** `psql -d data_warehouse_project -f scripts/bronze/ddl_bronze.sql`
3. **Validate Headers:** `./scripts/bronze/validate_headers.sh` (fail-fast check; run before Bronze Load)
4. **Bronze Load:** `psql -d data_warehouse_project -v datasets_dir="$(pwd)/datasets" -f scripts/bronze/load_bronze.sql`
5. **Silver DDL:** `psql -d data_warehouse_project -f legacy_sql/silver/ddl_silver.sql`
6. **Silver Load:** `psql -d data_warehouse_project -f legacy_sql/silver/load_silver.sql` (includes the `CALL silver.load_silver()` statement).
7. **Gold DDL:** `psql -d data_warehouse_project -f legacy_sql/gold/ddl_gold.sql` (creates dimension + fact views).

## ✅ Data Quality
- Bronze load uses a stored procedure `bronze.load_bronze()` with persistent error logging in `bronze.load_errors`.
- dbt tests run inside `dbt build` and gate downstream models: a failing test skips the models that depend on it. Advanced tests and quarantine tables arrive in Fase 4.
- Reconciliation: `docs/validacao_fase3.md` records that `staging.*` matches legacy `silver.*` and `marts.*` matches legacy `gold.*` (row counts + `EXCEPT` diff, ignoring `dwh_create_date`).
- Legacy Silver DDL adds metadata columns `dwh_source_system`, `dwh_create_date`; the dbt staging models keep them.
- Date handling: some Bronze fields (e.g. `sls_order_dt`) are `INT` and require conversion to `DATE` in Staging.