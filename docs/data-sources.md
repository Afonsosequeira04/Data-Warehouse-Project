# Data Sources

This document tracks the concrete data sources selected for the platform. Sources are chosen **after** business questions are defined (see `docs/business-questions.md`).

Status values: `Not selected` | `Shortlisted` | `Selected` | `Ready`

---

## API 1 — World Bank Indicators

| Property | Value |
|----------|-------|
| **Source Name** | `world_bank_indicators` |
| **Type** | Public REST API |
| **Owner/Provider** | World Bank |
| **Base URL** | `https://api.worldbank.org/v2` |
| **Authentication** | None |
| **Rate Limits** | ~120 requests/second (undocumented, be respectful) |
| **Pagination** | `page` + `per_page` (max 500 per page) |
| **Response Format** | JSON |
| **Key Endpoints** | `/country/{country}/indicator/{indicator}?format=json&per_page={per_page}&page={page}` |
| **Expected Volume (per run)** | ~3 indicators × ~200 countries × 10 years = ~6,000 observations |
| **Data Grain** | One observation per country + indicator + year |
| **Raw S3 Path Pattern** | `s3://<bucket>/api/world_bank_indicators/ingest_date=YYYY-MM-DD/<object>.json` |
| **Destination** | Bronze: `<catalog>.bronze.world_bank_indicators` |
| **Status** | Selected |
| **Notes** | Initial indicators: NY.GDP.MKTP.KD.ZG (GDP growth), FP.CPI.TOTL.ZG (inflation), SL.UEM.TOTL.ZS (unemployment). Historical analytical range: 10 years. |

---

## API 2 — FRED Economic Series

| Property | Value |
|----------|-------|
| **Source Name** | `fred_economic_series` |
| **Type** | Public REST API |
| **Owner/Provider** | Federal Reserve Bank of St. Louis / FRED |
| **Base URL** | `https://api.stlouisfed.org/fred` |
| **Authentication** | API key (provided later through approved secret mechanism) |
| **Rate Limits** | 120 requests/minute per API key |
| **Pagination** | `limit` + `offset` |
| **Response Format** | JSON |
| **Key Endpoints** | `/series/observations?series_id={series_id}&api_key={api_key}&file_type=json&limit={limit}&offset={offset}` |
| **Expected Volume (per run)** | ~3 series × ~260 observations (5 years monthly) = ~780 observations |
| **Data Grain** | One observation per series + observation date |
| **Raw S3 Path Pattern** | `s3://<bucket>/api/fred_economic_series/ingest_date=YYYY-MM-DD/<object>.json` |
| **Destination** | Bronze: `<catalog>.bronze.fred_economic_series` |
| **Status** | Selected |
| **Notes** | Initial series: CPIAUCSL (CPI), UNRATE (unemployment rate), FEDFUNDS (federal funds rate). Historical analytical range: 5 years. API key will be provided later through the approved secret mechanism. Do not claim a key already exists. Never put credentials in Git. |

---

## SaaS / Database Source — Amazon RDS PostgreSQL via Fivetran

| Property | Value |
|----------|-------|
| **Source Name** | `macro_watchlist_db` |
| **Type** | Operational PostgreSQL database |
| **Owner/Provider** | Amazon Web Services |
| **Database** | Amazon RDS for PostgreSQL |
| **Fivetran Connector** | PostgreSQL |
| **Authentication** | Database credentials (provided later through approved secret mechanism) |
| **Sync Frequency** | Daily (or on-demand via Airflow trigger) |
| **Expected Volume (per sync)** | Under 1,000 rows total across all tables |
| **Data Grain** | One row per entity (country, indicator, alert rule) |
| **Destination** | Databricks: `dwh_dev.raw_fivetran.<table>` (Fivetran destination schema prefix to be confirmed in P8) |
| **Status** | Selected |
| **Notes** | Fivetran is optional (D-001). Confirm Databricks destination is available on the Fivetran plan. If not available or cost-prohibitive, mark P8 as formally skipped with reason. This source is NOT a copy of World Bank or FRED data. It is a small operational/master-data source controlling the macro watchlist and alert configuration. Tables: `watchlist_country`, `watchlist_indicator`, `alert_rule`. See ADR-005 for details. Security: TLS, dedicated read-only Fivetran database user, restricted network access, no 0.0.0.0/0 exposure, no credentials in Git, future credentials stored through approved secret mechanism. |

---

## Source Selection Criteria

1. **Business questions first**: Sources must answer the questions in `docs/business-questions.md`
2. **Real data**: No synthetic/mock APIs for production pipeline
3. **API 1 + API 2**: Meaningfully different shapes (pagination, auth, response structure)
4. **API 2**: Prefer API key auth to exercise Secrets Manager
5. **Fivetran**: Optional; only if Databricks destination supported on plan
6. **Volume**: Portfolio-scale (thousands to low millions of records), not big data
7. **Accessibility**: Publicly accessible or free tier available for demo

---

## Decision Log

| Date | Source | Previous Status | New Status | Decision Maker | Notes |
|------|--------|-----------------|------------|----------------|-------|
| 2026-09-29 | World Bank Indicators | Not selected | Selected | Afonso | Approved for BQ-001, BQ-003 |
| 2026-09-29 | FRED Economic Series | Not selected | Selected | Afonso | Approved for BQ-002 |
| 2026-09-29 | Amazon RDS PostgreSQL (macro_watchlist_db) | Not selected | Selected | Afonso | Approved for BQ-001, BQ-003; Fivetran path |