# Business Questions

This document defines the analytical questions the Gold layer and dashboards must answer. **Business questions are defined before selecting data sources.**

The chosen APIs and SaaS/DB source must collectively enable answering these questions.

---

## Template for Business Questions

For each question, specify:

| Field | Description |
|-------|-------------|
| **ID** | Unique identifier (e.g., BQ-001) |
| **Question** | The business question in plain language |
| **Domain** | Business domain (e.g., sales, marketing, operations, finance) |
| **Required Grain** | Analytical grain (e.g., daily per store, monthly per customer) |
| **Required Metrics** | KPIs, aggregations, calculations needed |
| **Required Dimensions** | Attributes for slicing/filtering (e.g., region, product, channel) |
| **Time Range** | Historical depth needed (e.g., 13 months, 3 years) |
| **Freshness SLA** | How current the data must be (e.g., T+1, intraday) |
| **Candidate Sources** | Which selected source(s) could answer this |
| **Status** | `Draft` \| `Approved` \| `Implemented` |

---

## Business Questions (To Be Defined)

### BQ-001: [Placeholder]
- **Question**: [e.g., What is the daily revenue trend by product category over the last 12 months?]
- **Domain**: 
- **Required Grain**: 
- **Required Metrics**: 
- **Required Dimensions**: 
- **Time Range**: 
- **Freshness SLA**: 
- **Candidate Sources**: 
- **Status**: Draft

### BQ-002: [Placeholder]
- **Question**: 
- **Domain**: 
- **Required Grain**: 
- **Required Metrics**: 
- **Required Dimensions**: 
- **Time Range**: 
- **Freshness SLA**: 
- **Candidate Sources**: 
- **Status**: Draft

### BQ-003: [Placeholder]
- **Question**: 
- **Domain**: 
- **Required Grain**: 
- **Required Metrics**: 
- **Required Dimensions**: 
- **Time Range**: 
- **Freshness SLA**: 
- **Candidate Sources**: 
- **Status**: Draft

### BQ-004: [Placeholder]
- **Question**: 
- **Domain**: 
- **Required Grain**: 
- **Required Metrics**: 
- **Required Dimensions**: 
- **Time Range**: 
- **Freshness SLA**: 
- **Candidate Sources**: 
- **Status**: Draft

### BQ-005: [Placeholder]
- **Question**: 
- **Domain**: 
- **Required Grain**: 
- **Required Metrics**: 
- **Required Dimensions**: 
- **Time Range**: 
- **Freshness SLA**: 
- **Candidate Sources**: 
- **Status**: Draft

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

## Source-to-Question Mapping (To Be Completed After Source Selection)

| Business Question | Primary Source | Supporting Sources | Gold Models Needed |
|-------------------|----------------|--------------------|-------------------|
| BQ-001 | | | |
| BQ-002 | | | |
| BQ-003 | | | |
| BQ-004 | | | |
| BQ-005 | | | |

---

## Notes

- Do not invent business questions that are not already specified by project documentation
- The technical datasheet and README contain placeholder sources (`<API 1>`, `<API 2>`, `<SaaS/DB>`) — actual questions will drive the source selection
- Keep the list small (3-5 core questions) for portfolio scope
- Each question should be answerable by a single dashboard tile or a small set of related tiles