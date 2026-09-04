# Agent Guide - Data Warehouse Project

## 🚧 Modernization in progress
- Roadmap: see `PLANO_MODERNIZACAO.md` in repo root — phased plan (dbt, Docker, Airflow, CI/CD, live lineage via OpenLineage/Marquez).
- Current phase: **Fase 0 (higiene e fundação) — in progress.**
- Rule for agents: only implement the phase explicitly requested in the prompt. Do not jump ahead to a later phase even if it seems convenient. Update this section's "Current phase" line when a phase is merged.

## 🏗️ Architecture
- **Stack:** PostgreSQL (13+) using `psql` CLI.
- **Pattern:** Medallion (`bronze` -> `silver` -> `gold`).
- **Data Flow:** CRM/ERP CSVs -> Bronze (Raw) -> Silver (Cleaned) -> Gold (Views).

## ⚙️ Operational Quirks
- **Hardcoded Paths:** `scripts/bronze/load_bronze.sql` uses absolute paths (e.g., `/Users/ritamoreda/...`). **Must** be updated to local absolute paths of `datasets/` before running.
- **Database Name:** All scripts now use `data_warehouse_project` consistently (fix applied in Fase 0).
- **Missing Layer:** Gold layer (DDL + views) doesn't exist yet — this is the main functional gap (Fase 1).
- **Silver Load:** The `CALL silver.load_silver()` is now included in `scripts/silver/load_silver.sql` and will execute when the script is run.

## 🚀 Commands
1. **Initialize DB:** `psql -f scripts/init_database.sql` (Drops and recreates `data_warehouse_project`).
2. **Bronze DDL:** `psql -d data_warehouse_project -f scripts/bronze/ddl_bronze.sql`
3. **Bronze Load:** `psql -d data_warehouse_project -v datasets_dir="$(pwd)/datasets" -f scripts/bronze/load_bronze.sql` (Sets the source CSV path via psql variable.)
4. **Silver DDL:** `psql -d data_warehouse_project -f scripts/silver/ddl_silver.sql`
5. **Silver Load:** `psql -d data_warehouse_project -f scripts/silver/load_silver.sql` (includes the `CALL silver.load_silver()` statement).

## ✅ Data Quality
- Bronze load uses a stored procedure `bronze.load_bronze()` with persistent error logging in `bronze.load_errors`.
- Silver DDL adds metadata columns: `dwh_source_system`, `dwh_create_date`.
- Date handling: Some Bronze fields (e.g., `sls_order_dt`) are `INT` and require conversion to `DATE` in Silver.
