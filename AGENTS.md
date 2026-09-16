# Agent Guide - Data Warehouse Project

## 🚧 Modernization in progress
- Roadmap: see `PLANO_MODERNIZACAO.md` in repo root — phased plan (dbt, Docker, Airflow, CI/CD, live lineage via OpenLineage/Marquez).
- Current phase: **Fase 3 (migração para dbt) — not started yet.**
- Rule for agents: only implement the phase explicitly requested in the prompt. Do not jump ahead to a later phase even if it seems convenient. Update this section's "Current phase" line when a phase is merged.
- **Branch workflow (mandatory):** before touching any file, run `git branch` to check the current branch. If on `main`, create and switch to the phase branch first (`git checkout -b fase-N-nome`). Never commit phase work directly to `main` — all phase work is committed to its own branch and merged via Pull Request, reviewed by the project owner before merge.

## 🏗️ Architecture
- **Stack:** PostgreSQL (13+) using `psql` CLI.
- **Pattern:** Medallion (`bronze` -> `silver` -> `gold`).
- **Data Flow:** CRM/ERP CSVs -> Bronze (Raw) -> Silver (Cleaned) -> Gold (Views).

## ⚙️ Operational Quirks
- **CSV Path Configuration:** `scripts/bronze/load_bronze.sql` uses a parameterised `datasets_dir` argument. In Docker, pass the container path `/data/datasets` via `psql -v datasets_dir="/data/datasets"`. On host, use `psql -v datasets_dir="$(pwd)/datasets"`.
- **Header Validation:** Run `scripts/bronze/validate_headers.sh` (or `make validate-headers`) to fail early if source CSV headers don't match `expected_headers.txt` — do this *before* the Bronze Load.
- **Database Name:** All scripts now use `data_warehouse_project` consistently (fix applied in Fase 0).
- **Gold Layer:** Now implemented (Fase 1) as views in `scripts/gold/`. See `docs/data_catalog.md` for column definitions.
- **Silver Load:** The `CALL silver.load_silver()` is now included in `scripts/silver/load_silver.sql` and will execute when the script is run.

## 🚀 Commands

### Docker Compose (recommended — Fase 2)
```bash
# Full pipeline from zero to Gold
make all

# Or step by step:
make up              # Start Postgres container
make init-db         # Drop/recreate database + schemas
make validate-headers  # Validate CSV headers on host (fail-fast)
make load-bronze     # Load Bronze layer (server-side COPY from /data/datasets)
make load-silver     # Load Silver layer
make load-gold       # Create Gold layer views

# Utilities
make psql            # Open psql shell in container
make logs            # Follow container logs
make down            # Stop container (preserves data volume)
```

### Legacy psql (still works — manual path management)
1. **Initialize DB:** `psql -f scripts/init_database.sql` (Drops and recreates `data_warehouse_project`).
2. **Bronze DDL:** `psql -d data_warehouse_project -f scripts/bronze/ddl_bronze.sql`
3. **Validate Headers:** `./scripts/bronze/validate_headers.sh` (fail-fast check; run before Bronze Load)
4. **Bronze Load:** `psql -d data_warehouse_project -v datasets_dir="$(pwd)/datasets" -f scripts/bronze/load_bronze.sql` (Sets the source CSV path via psql variable.)
5. **Silver DDL:** `psql -d data_warehouse_project -f scripts/silver/ddl_silver.sql`
6. **Silver Load:** `psql -d data_warehouse_project -f scripts/silver/load_silver.sql` (includes the `CALL silver.load_silver()` statement).
7. **Gold DDL:** `psql -d data_warehouse_project -f scripts/gold/ddl_gold.sql` (creates dimension + fact views).

## ✅ Data Quality
- Bronze load uses a stored procedure `bronze.load_bronze()` with persistent error logging in `bronze.load_errors`.
- Silver DDL adds metadata columns: `dwh_source_system`, `dwh_create_date`.
- Date handling: Some Bronze fields (e.g., `sls_order_dt`) are `INT` and require conversion to `DATE` in Silver.