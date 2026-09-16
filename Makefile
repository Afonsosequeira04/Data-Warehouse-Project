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

.PHONY: up down logs psql init-db validate-headers load-bronze load-silver load-gold all help

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
	@echo "  make up              Start the Postgres container"
	@echo "  make down            Stop and remove the container (keeps volume)"
	@echo "  make logs            Follow container logs"
	@echo "  make psql            Open psql shell in the container"
	@echo "  make init-db         Drop/recreate database and schemas (runs init_database.sql)"
	@echo "  make validate-headers Validate CSV headers on host (run before load-bronze)"
	@echo "  make load-bronze     Load Bronze layer (requires running container)"
	@echo "  make load-silver     Load Silver layer (requires Bronze loaded)"
	@echo "  make load-gold       Create Gold layer views"
	@echo "  make all             Run full pipeline: up -> init-db -> validate-headers -> load-bronze -> load-silver -> load-gold"
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
# load-silver — run Silver DDL + load
# -------------------------------------------------------------
load-silver: up
	@echo "Creating Silver tables..."
	$(COMPOSE_CMD) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /scripts/silver/ddl_silver.sql
	@echo "Loading Silver data..."
	$(COMPOSE_CMD) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /scripts/silver/load_silver.sql

# -------------------------------------------------------------
# load-gold — run Gold DDL (creates views)
# -------------------------------------------------------------
load-gold: up
	@echo "Creating Gold layer views..."
	$(COMPOSE_CMD) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /scripts/gold/ddl_gold.sql

# -------------------------------------------------------------
# all — full pipeline from zero to Gold
# -------------------------------------------------------------
all: up init-db validate-headers load-bronze load-silver load-gold
	@echo ""
	@echo "========================================================"
	@echo "Pipeline complete! Gold layer is ready for queries."
	@echo "Run 'make psql' to connect and explore."
	@echo "========================================================"