# =============================================================
# Makefile — Data Warehouse Project (Docker Compose)
# =============================================================
# This Makefile provides convenience targets for the Docker-based
# PostgreSQL data warehouse. All psql commands run against the
# containerised Postgres, with datasets mounted at /data/datasets
# inside the container.
#
# Critical: bronze.load_bronze() uses server-side COPY, so the
# datasets_dir passed to the procedure MUST be the container path
# (/data/datasets), not the host path.
# =============================================================

.PHONY: up down logs psql init-db validate-headers load-bronze load-silver load-gold load-silver-legacy load-gold-legacy all all-dbt dbt-setup dbt-build dbt-docs help

# Load environment variables from .env if present
ifneq ("$(wildcard infra/.env)","")
    include infra/.env
    export
endif

# Default values (can be overridden by .env or command line)
POSTGRES_USER     ?= data_warehouse
POSTGRES_PASSWORD ?= data_warehouse
POSTGRES_DB       ?= data_warehouse_project
POSTGRES_PORT     ?= 5432
DATASETS_DIR_CONTAINER = /data/datasets
COMPOSE_FILE      = infra/docker-compose.yml
COMPOSE_CMD       = docker compose -f $(COMPOSE_FILE)

# Connection string for psql
PG_CONN = postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_PORT)/$(POSTGRES_DB)

# -------------------------------------------------------------
# help — show available targets
# -------------------------------------------------------------
help:
	@echo "Data Warehouse Project — Make targets"
	@echo ""
	@echo "  make up                    Start the Postgres container"
	@echo "  make down                  Stop and remove the container (keeps volume)"
	@echo "  make logs                  Follow container logs"
	@echo "  make psql                  Open psql shell in the container"
	@echo "  make init-db               Drop/recreate database and schemas (runs init_database.sql)"
	@echo "  make validate-headers      Validate CSV headers on host (run before load-bronze)"
	@echo "  make load-bronze           Load Bronze layer (requires running container)"
	@echo "  make load-silver-legacy    Load Silver layer (legacy plain SQL)"
	@echo "  make load-gold-legacy      Create Gold layer views (legacy plain SQL)"
	@echo "  make all                   Legacy pipeline: up -> init-db -> validate-headers -> load-bronze -> load-silver-legacy -> load-gold-legacy"
	@echo ""
	@echo "  make dbt-setup             Create .venv (Python >= 3.10) and install dbt from requirements.txt"
	@echo "  make dbt-build             dbt build: staging + marts + tests (always the full build)"
	@echo "  make dbt-docs              dbt docs generate + serve (owner only; blocks the terminal)"
	@echo "  make all-dbt               dbt pipeline: up -> init-db -> validate-headers -> load-bronze -> dbt-build"
	@echo ""

# -------------------------------------------------------------
# up — start the database container
# -------------------------------------------------------------
up:
	@echo "Starting PostgreSQL container..."
	$(COMPOSE_CMD) up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@until $(COMPOSE_CMD) exec -T postgres pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB) >/dev/null 2>&1; do sleep 1; done
	@echo "PostgreSQL is ready."

# -------------------------------------------------------------
# down — stop and remove container (preserves volume)
# -------------------------------------------------------------
down:
	@echo "Stopping PostgreSQL container..."
	$(COMPOSE_CMD) down

# -------------------------------------------------------------
# logs — follow container logs
# -------------------------------------------------------------
logs:
	$(COMPOSE_CMD) logs -f postgres

# -------------------------------------------------------------
# psql — open interactive psql session
# -------------------------------------------------------------
psql:
	$(COMPOSE_CMD) exec -it postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

# -------------------------------------------------------------
# init-db — run init_database.sql (DROP/CREATE database + schemas)
# -------------------------------------------------------------
# NOTE: We use an explicit Make target instead of /docker-entrypoint-initdb.d
# because init_database.sql does DROP DATABASE / CREATE DATABASE, which
# conflicts with the postgres entrypoint's initialization flow (the DB
# is already created by the time initdb.d scripts run). Running it
# explicitly via psql after the container is up is the correct approach.
# -------------------------------------------------------------
init-db: up
	@echo "Initializing database (drop/create data_warehouse_project + schemas)..."
	$(COMPOSE_CMD) exec -T postgres psql -U $(POSTGRES_USER) -d postgres -f /scripts/init_database.sql

# -------------------------------------------------------------
# validate-headers — run client-side CSV header validation on HOST
# -------------------------------------------------------------
# This runs on the host (not in container) because it reads CSV files
# directly from the local filesystem. It MUST run before load-bronze
# and will fail the make if headers don't match expected_headers.txt.
# -------------------------------------------------------------
validate-headers:
	@echo "Validating CSV headers against manifest..."
	./scripts/bronze/validate_headers.sh $(shell pwd)/datasets

# -------------------------------------------------------------
# load-bronze — run Bronze DDL + load (server-side COPY)
# -------------------------------------------------------------
# The datasets_dir passed to bronze.load_bronze() is the CONTAINER path
# (/data/datasets) because COPY is executed server-side inside Postgres.
# -------------------------------------------------------------
load-bronze: up
	@echo "Creating Bronze tables..."
	$(COMPOSE_CMD) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /scripts/bronze/ddl_bronze.sql
	@echo "Loading Bronze data (server-side COPY from $(DATASETS_DIR_CONTAINER))..."
	$(COMPOSE_CMD) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v datasets_dir="$(DATASETS_DIR_CONTAINER)" -f /scripts/bronze/load_bronze.sql

# -------------------------------------------------------------
# load-silver-legacy — run Silver DDL + load (legacy plain SQL)
# -------------------------------------------------------------
load-silver-legacy: up
	@echo "Creating Silver tables..."
	$(COMPOSE_CMD) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /legacy_sql/silver/ddl_silver.sql
	@echo "Loading Silver data..."
	$(COMPOSE_CMD) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /legacy_sql/silver/load_silver.sql

# -------------------------------------------------------------
# load-gold-legacy — run Gold DDL (creates views, legacy plain SQL)
# -------------------------------------------------------------
load-gold-legacy: up
	@echo "Creating Gold layer views..."
	$(COMPOSE_CMD) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /legacy_sql/gold/ddl_gold.sql

# -------------------------------------------------------------
# dbt-setup — create .venv and install dbt requirements
# -------------------------------------------------------------
dbt-setup:
	@echo "Setting up dbt environment..."
	@if [ ! -d .venv ]; then \
		echo "Creating .venv with python3..."; \
		python3 -m venv .venv; \
	fi
	@.venv/bin/pip install --upgrade pip >/dev/null 2>&1
	@.venv/bin/pip install -r dbt_project/requirements.txt
	@echo "dbt setup complete."

# -------------------------------------------------------------
# dbt-build — run full dbt build (staging + marts + tests)
# -------------------------------------------------------------
dbt-build:
	@echo "Running dbt build..."
	@.venv/bin/dbt build --project-dir dbt_project --profiles-dir dbt_project

# -------------------------------------------------------------
# dbt-docs — generate and serve dbt docs
# -------------------------------------------------------------
dbt-docs:
	@echo "Generating dbt docs..."
	@.venv/bin/dbt docs generate --project-dir dbt_project --profiles-dir dbt_project
	@echo "Starting dbt docs server (blocks terminal)..."
	@.venv/bin/dbt docs serve --project-dir dbt_project --profiles-dir dbt_project

# -------------------------------------------------------------
# all-dbt — full dbt pipeline from zero to Marts
# -------------------------------------------------------------
all-dbt: up init-db validate-headers load-bronze dbt-build
	@echo ""
	@echo "========================================================"
	@echo "dbt pipeline complete! Marts are ready for queries."
	@echo "Run 'make dbt-docs' to view documentation."
	@echo "========================================================"

# -------------------------------------------------------------
# all — full legacy pipeline from zero to Gold
# -------------------------------------------------------------
all: up init-db validate-headers load-bronze load-silver-legacy load-gold-legacy
	@echo ""
	@echo "========================================================"
	@echo "Pipeline complete! Gold layer is ready for queries."
	@echo "Run 'make psql' to connect and explore."
	@echo "========================================================"