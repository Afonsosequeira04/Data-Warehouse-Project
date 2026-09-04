# Agent Guide - Data Warehouse Project

## 🚧 Modernization in progress
- Roadmap: see `PLANO_MODERNIZACAO.md` in repo root — phased plan (dbt, Docker, Airflow, CI/CD, live lineage via OpenLineage/Marquez).
- Current phase: **Fase 0 (higiene e fundação) — not started yet.**
- Rule for agents: only implement the phase explicitly requested in the prompt. Do not jump ahead to a later phase even if it seems convenient. Update this section's "Current phase" line when a phase is merged.

## 🏗️ Architecture
- **Stack:** PostgreSQL (13+) using `psql` CLI.
- **Pattern:** Medallion (`bronze` -> `silver` -> `gold`).
- **Data Flow:** CRM/ERP CSVs -> Bronze (Raw) -> Silver (Cleaned) -> Gold (Views).

## ⚙️ Operational Quirks
- **Hardcoded Paths:** `scripts/bronze/load_bronze_layer.sql` uses absolute paths (e.g., `/Users/ritamoreda/...`). **Must** be updated to local absolute paths of `datasets/` before running.
- **Database Name:** README says `data_warehouse`, but `scripts/init_database.sql` creates `data_warehouse_project`. Use the latter.
- **Missing Layer:** Gold layer (DDL + views) doesn't exist yet — this is the main functional gap (Fase 1). Silver load logic already exists in full (`silver_load_procedure.sql`, `load_silver()`) — only its `CALL` at the end of the script is commented out (see Command 5 for the workaround).
- **Naming Mismatch:** README refers to `ddl_bronze.sql`; actual file is `bronze_layer_ddl_script.sql`. Trust the file system.

## 🚀 Commands
1. **Initialize DB:** `psql -f scripts/init_database.sql` (Drops and recreates `data_warehouse_project`).
2. **Bronze DDL:** `psql -d data_warehouse_project -f scripts/bronze/bronze_layer_ddl_script.sql`
3. **Bronze Load:** `psql -d data_warehouse_project -f scripts/bronze/load_bronze_layer.sql` (Update paths first).
4. **Silver DDL:** `psql -d data_warehouse_project -f scripts/silver/ddl_silver.sql`
5. **Silver Load:** `psql -d data_warehouse_project -c "CALL silver.load_silver();"` (the `CALL` at the end of `silver_load_procedure.sql` is currently commented out — call it directly like this until Fase 0 separates definition from execution).

## ✅ Data Quality
- Bronze load uses a stored procedure `bronze.load_bronze()` with persistent error logging in `bronze.load_errors`.
- Silver DDL adds metadata columns: `dwh_source_system`, `dwh_create_date`.
- Date handling: Some Bronze fields (e.g., `sls_order_dt`) are `INT` and require conversion to `DATE` in Silver.
