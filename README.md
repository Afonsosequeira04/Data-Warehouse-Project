# Data Warehouse Project

A modern data warehouse built on **PostgreSQL**, following the **Medallion Architecture** (Bronze → Staging → Marts) to ingest, clean, and model data from CRM and ERP source systems for analytics, reporting, and machine learning.

![Data Warehouse Architecture](docs/data_warehouse_project.drawio.png)

![Data Flow](docs/bronze_silver_gold_data_flow_styled.png)


## 🔗 Useful Links

- 📝 [Project Notion](https://app.notion.com/p/Data-Warehouse-Project-3c745b08c0b680ffa7fed0b348f511d0?source=copy_link) — planning, notes, and project steps
- 📐 [`docs/data_warehouse_project.drawio`](https://github.com/Afonsosequeira04/Data-Warehouse-Project/blob/main/docs/data_warehouse_project.drawio) — architecture diagram source (open in [draw.io](https://app.diagrams.net/))

---

## 📖 Overview

This project implements an end-to-end ETL pipeline that moves raw operational data through three progressively refined layers inside a single PostgreSQL data warehouse. It's designed to be simple to run locally, easy to extend, and a solid reference implementation of the medallion pattern in a PostgreSQL environment.

**Goals:**
- Consolidate data from multiple source systems (CRM, ERP) into one warehouse
- Apply consistent cleansing, standardization, and enrichment rules
- Deliver business-ready, query-friendly data for BI tools, ad hoc SQL, and ML workflows

---

## 🏗️ Architecture

The warehouse follows the **Bronze → Staging → Marts** medallion pattern (dbt-native from Fase 3):

### 🥉 Bronze Layer — Raw Data
- **Object type:** Tables (schema `bronze`)
- **Load strategy:** Batch processing, full load (truncate & insert) via `psql` COPY
- **Transformations:** None — data is stored exactly as received
- **Managed by:** `scripts/bronze/` (outside dbt)
- **Purpose:** An unaltered, auditable copy of the source data

### 🥈 Staging Layer — Cleaned & Standardized Data (dbt)
- **Object type:** Tables (schema `staging`)
- **Load strategy:** Full rebuild (`CREATE TABLE AS`) via dbt
- **Transformations:** Data cleansing, standardization, normalization, derived columns, enrichment
- **Managed by:** `dbt_project/models/staging/` (6 models: `stg_crm__*`, `stg_erp__*`)
- **Tests:** `not_null`, `unique`, `accepted_values` on key columns
- **Purpose:** A clean, consistent foundation for business modeling

### 🥇 Marts Layer — Business-Ready Data (dbt)
- **Object type:** Views (schema `marts`)
- **Load strategy:** Computed on query
- **Transformations:** Data integration across sources, business logic
- **Data modeling:** Star schema (2 dimensions + 1 fact)
- **Managed by:** `dbt_project/models/marts/` (3 models: `dim_customers`, `dim_products`, `fct_sales`)
- **Tests:** `not_null`, `unique` on surrogate keys; `relationships` between fact and dimensions; `accepted_values` on enum-like columns
- **Purpose:** The consumption layer — ready for reporting and analysis

---

## 🔌 Sources → Consumption Flow

```
CRM (CSV files)  ┐
                  ├──► Bronze ──► Staging (dbt) ──► Marts (dbt) ──► Consume
ERP (CSV files)  ┘
```

**Sources**
- CRM — CSV files, delivered as files in a folder
- ERP — CSV files, delivered as files in a folder

**Consumers of the Marts layer**
- 📊 BI & Reporting (e.g. Power BI, Metabase)
- 🔍 Ad hoc SQL queries
- 🤖 Machine learning

---

## 🛠️ Tech Stack

| Component        | Technology                     |
|-------------------|--------------------------------|
| Database           | PostgreSQL 16 (Docker Compose) |
| Ingestion (Bronze) | `psql` COPY + stored procedure |
| Transform (Staging/Marts) | **dbt-core / dbt-postgres** |
| Source format       | CSV files                      |
| Diagramming        | draw.io / Mermaid              |
| Orchestration      | (Fase 5) Airflow               |
| CI/CD              | (Fase 7) GitHub Actions        |
| Observability      | (Fase 8) OpenLineage + Marquez |

---

## 📂 Project Structure

```
data-warehouse-project/
│
├── datasets/                  # Raw source CSV files (CRM, ERP) — mounted RO in container at /data/datasets
│   ├── source_crm/
│   └── source_erp/
│
├── infra/                     # Docker Compose & environment config
│   ├── docker-compose.yml
│   └── .env.example           # (copy to .env; .env is git-ignored)
│
├── scripts/
│   ├── init_database.sql      # Creates database + schemas (bronze, silver, gold)
│   └── bronze/                # DDL + load procedure + header validation (outside dbt)
│
├── legacy_sql/                # Legacy plain-SQL Silver/Gold (Fase 1), kept for reference until validated
│   ├── silver/
│   └── gold/
│
├── dbt_project/               # dbt project (Fase 3+)
│   ├── dbt_project.yml
│   ├── profiles.yml           # Reads POSTGRES_* from env; no secrets in repo
│   ├── requirements.txt       # dbt-core, dbt-postgres versions pinned
│   ├── models/
│   │   ├── staging/           # 6 table models (stg_<source>__<table>)
│   │   └── marts/             # 3 view models (dim_*, fct_*)
│   └── macros/
│       └── generate_schema_name.sql  # Keeps staging/marts schemas without target prefix
│
├── docs/
│   ├── data_warehouse_project.drawio      # Architecture diagram
│   ├── bronze_silver_gold_data_flow_styled.png
│   ├── data_catalog.md                    # Field-level docs (legacy Gold + note about dbt)
│   ├── baseline_fase3.md                  # Bronze/Silver/Gold counts before dbt migration
│   └── validacao_fase3.md                 # Reconciliation: staging=silver, marts=gold
│
├── tests/                     # Data quality checks (placeholder)
│
├── Makefile                   # All automation targets (legacy + dbt)
├── AGENTS.md                  # Agent rules for this repo
└── README.md
```

---

## ⚙️ Setup & Usage

### Prerequisites
- Docker & Docker Compose (recommended)
- **OR** PostgreSQL (13+) + `psql` CLI for legacy manual setup
- CRM and ERP source CSV files placed under `datasets/`

### Option A — Docker Compose + dbt (Fase 3+)

The easiest way to run the full dbt pipeline. All paths are handled automatically.

```bash
# 1. Copy the example environment file and adjust if needed
cp infra/.env.example infra/.env

# 2. Run the complete dbt pipeline (Bronze → Staging → Marts)
make all-dbt
```

**Step-by-step (if you want to inspect each layer):**
```bash
make up              # Start Postgres container
make init-db         # Drop/recreate database + schemas
make validate-headers  # Validate CSV headers on host (fail-fast)
make load-bronze     # Load Bronze layer (server-side COPY from /data/datasets)
make dbt-build       # Run dbt build (staging + marts + tests)

# Utilities
make psql            # Open psql shell in container
make logs            # Follow container logs
make down            # Stop container (preserves data volume)

# dbt utilities
make dbt-setup       # Create .venv + install dbt (idempotent)
make dbt-docs        # Generate & serve dbt docs (blocks terminal)
```

### Option B — Legacy pipeline (plain SQL, Fase 1/2)

Runs the original Silver/Gold scripts kept in `legacy_sql/`.

```bash
# Full legacy pipeline (Bronze → Silver → Gold)
make all
```

**Step-by-step:**
```bash
make up                  # Start Postgres container
make init-db             # Drop/recreate database + schemas
make validate-headers    # Validate CSV headers on host (fail-fast)
make load-bronze         # Load Bronze layer
make load-silver-legacy  # Load Silver layer (legacy plain SQL)
make load-gold-legacy    # Create Gold layer views (legacy plain SQL)
```

### Option C — Legacy psql (Manual)

If you prefer not to use Docker, you can run the scripts directly against a local PostgreSQL instance. You must manage paths manually.

1. **Create the database**
   ```sql
    CREATE DATABASE data_warehouse_project;
   ```

2. **Build the Bronze layer** — creates raw tables and loads source CSVs as-is
   ```bash
   psql -d data_warehouse_project -f scripts/bronze/ddl_bronze.sql
   psql -d data_warehouse_project -v datasets_dir="$(pwd)/datasets" -f scripts/bronze/load_bronze.sql
   ```

3. **Build the Silver layer (legacy)** — cleanses, standardizes, and enriches Bronze data
   ```bash
    psql -d data_warehouse_project -f legacy_sql/silver/ddl_silver.sql
    psql -d data_warehouse_project -f legacy_sql/silver/load_silver.sql
   ```

4. **Build the Gold layer (legacy)** — creates the business-facing views
   ```bash
    psql -d data_warehouse_project -f legacy_sql/gold/ddl_gold.sql
   ```

5. **Query the Gold layer**
   ```sql
   SELECT * FROM gold.fact_sales LIMIT 10;
   ```

---

## 📊 Data Model (Marts Layer)

The Marts layer exposes a **star schema** made up of dimension and fact views.

- `marts.dim_customers` — Customer dimension (CRM + ERP merge)
- `marts.dim_products` — Product dimension (CRM + ERP category merge)
- `marts.fct_sales` — Sales fact table (links to both dimensions)

See `docs/data_catalog.md` for full column-level definitions (legacy Gold + note about dbt).
For the live, authoritative catalog with tests and lineage, run `make dbt-docs`.

---

## ✅ Data Quality

- **Bronze:** Server-side COPY with retry (3x), persistent error logging in `bronze.load_errors`, header validation before load.
- **Staging (dbt):** Built-in tests (`not_null`, `unique`, `accepted_values`) run inside `dbt build`; failing tests gate downstream marts.
- **Marts (dbt):** `not_null` + `unique` on surrogate keys (`customer_key`, `product_key`, `sales_key`); `relationships` from `fct_sales` to both dimensions; `accepted_values` on gender, marital_status, product_line.
- **Reconciliation:** `docs/validacao_fase3.md` records that `staging.*` matches legacy `silver.*` and `marts.*` matches legacy `gold.*` (row counts + `EXCEPT` diff, ignoring `dwh_create_date`).

---

## 🗺️ Roadmap

See `PLANO_MODERNIZACAO.md` for the phased plan:
- **Fase 3** (current): dbt migration ✅
- **Fase 4:** Advanced data quality (dbt-utils, singular tests, quarantine)
- **Fase 5:** Orchestration (Airflow)
- **Fase 6:** History & incremental loads (dbt snapshots, incremental models)
- **Fase 7:** CI/CD (GitHub Actions)
- **Fase 8:** Observability, live lineage (OpenLineage + Marquez)
- **Fase 9:** BI / Semantic layer

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.