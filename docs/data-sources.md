# Data Sources

This document tracks the concrete data sources selected for the platform. Sources are chosen **after** business questions are defined (see `docs/business-questions.md`).

Status values: `Not selected` | `Shortlisted` | `Selected` | `Ready`

---

## API 1 (Public REST API)

| Property | Value |
|----------|-------|
| **Source Name** | `<API 1>` |
| **Type** | Public REST API |
| **Owner/Provider** | Not selected |
| **Base URL** | Not selected |
| **Authentication** | Not selected (API key / OAuth / none) |
| **Rate Limits** | Not selected |
| **Pagination** | Not selected (cursor / offset / page) |
| **Response Format** | Not selected (JSON) |
| **Key Endpoints** | Not selected |
| **Expected Volume (per run)** | Not selected |
| **Data Grain** | Not selected (e.g., one record per transaction/event) |
| **Raw S3 Path Pattern** | `s3://<bucket>/api/<source_name>/ingest_date=YYYY-MM-DD/<object>.json` |
| **Destination** | Bronze: `<catalog>.bronze.<table>` |
| **Status** | Not selected |
| **Notes** | Prefer an API with pagination to demonstrate the ingestion pattern. |

---

## API 2 (Public REST API)

| Property | Value |
|----------|-------|
| **Source Name** | `<API 2>` |
| **Type** | Public REST API |
| **Owner/Provider** | Not selected |
| **Base URL** | Not selected |
| **Authentication** | Not selected (API key preferred to exercise Secrets Manager) |
| **Rate Limits** | Not selected |
| **Pagination** | Not selected (meaningfully different from API 1) |
| **Response Format** | Not selected (JSON, different structure from API 1) |
| **Key Endpoints** | Not selected |
| **Expected Volume (per run)** | Not selected |
| **Data Grain** | Not selected |
| **Raw S3 Path Pattern** | `s3://<bucket>/api/<source_name>/ingest_date=YYYY-MM-DD/<object>.json` |
| **Destination** | Bronze: `<catalog>.bronze.<table>` |
| **Status** | Not selected |
| **Notes** | Prefer a different response structure and auth mechanism from API 1 to prove architectural flexibility. |

---

## SaaS / Database Source (Fivetran)

| Property | Value |
|----------|-------|
| **Source Name** | `<SaaS/DB>` |
| **Type** | SaaS application or Database |
| **Owner/Provider** | Not selected |
| **Fivetran Connector** | Not selected |
| **Authentication** | Not selected (API key / DB credentials / OAuth) |
| **Sync Frequency** | Not selected (e.g., 15 min, 1 hour, 6 hours) |
| **Expected Volume (per sync)** | Not selected |
| **Data Grain** | Not selected |
| **Destination** | Databricks: `<catalog>.raw_fivetran.<schema>.<table>` |
| **Status** | Not selected |
| **Notes** | Fivetran is optional (D-001). Confirm Databricks destination is available on the Fivetran plan. If not available or cost-prohibitive, mark P8 as formally skipped with reason. |

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
| - | API 1 | - | Not selected | - | Awaiting business questions |
| - | API 2 | - | Not selected | - | Awaiting business questions |
| - | SaaS/DB | - | Not selected | - | Awaiting business questions + Fivetran plan check |