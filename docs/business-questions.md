# Business Questions

This document defines the analytical questions the Gold layer and dashboards must answer. **Business questions are defined before selecting data sources.**

The chosen APIs and SaaS/DB source must collectively enable answering these questions.

---

## Business Questions

### BQ-001

**Question:**

How have GDP growth, inflation, and unemployment evolved over time for the countries on the macro watchlist?

**Domain:**
Macroeconomics / Country risk monitoring

**Required Grain:**

country + indicator + year

**Required Dimensions:**

- country
- region
- indicator
- year

**Required Metrics:**

- indicator value
- latest available value
- absolute change where meaningful
- percentage change where meaningful
- historical trend

**Time Range:**

10 years

**Sources:**

World Bank + macro_watchlist_db

**Status:**

Approved

---

### BQ-002

**Question:**

What are the latest trends in the selected US macroeconomic series, and how do their values change over time?

**Domain:**
US Macroeconomics / Monetary policy monitoring

**Required Grain:**

series + observation date

**Required Dimensions:**

- series
- date
- frequency
- unit

**Required Metrics:**

- latest value
- previous-period value
- absolute change
- percentage change where meaningful
- historical trend

**Time Range:**

5 years

**Source:**

FRED

**Status:**

Approved

---

### BQ-003

**Question:**

Which configured macroeconomic alert rules are currently breached, and for which countries or indicators?

**Domain:**
Alerting / Operational monitoring

**Required Grain:**

country + indicator + alert rule + latest observation

**Required Dimensions:**

- country
- region
- indicator
- source_system
- direction
- active flag

**Required Metrics:**

- latest value
- threshold
- difference from threshold
- breach status
- latest observation date

**Time Range:**

latest available observation

**Sources:**

World Bank + macro_watchlist_db

**Status:**

Approved

---

## Data Quality Questions (Always Required)

These questions are answered by the Data Quality dashboard regardless of business domain:

| ID | Question | Metric |
|----|----------|--------|
| DQ-001 | Did the latest pipeline run succeed? | Pipeline status (success/failed/running) |
| DQ-002 | When was the last successful batch? | Latest successful batch timestamp |
| DQ-003 | How many rows were ingested in the latest batch? | Row count per source per batch |
| DQ-004 | How many rows were rejected/quarantined? | Quarantine row count per source per batch |
| DQ-005 | Are there any failing dbt tests? | Failed test count + details |
| DQ-006 | Is data fresh within SLA? | Max data age per source/table vs SLA |
| DQ-007 | Are source APIs healthy? | API response time, error rate, last success |

---

## Source-to-Question Mapping

| Business Question | Primary Source | Supporting Sources | Gold Models Needed |
|-------------------|----------------|--------------------|-------------------|
| BQ-001 | World Bank | macro_watchlist_db | dim_country, dim_indicator, fact_macro_indicator |
| BQ-002 | FRED | none | dim_fred_series, fact_fred_observation |
| BQ-003 | World Bank | macro_watchlist_db | dim_country, dim_indicator, dim_alert_rule, fact_macro_indicator, fact_alert_evaluation |

---

## Notes

- Do not invent business questions that are not already specified by project documentation
- Keep the list small (3 core questions) for portfolio scope
- Each question should be answerable by a single dashboard tile or a small set of related tiles
- The technical datasheet and README now reflect the selected sources: World Bank, FRED, Amazon RDS PostgreSQL via Fivetran