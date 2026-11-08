# Data Sources

This document tracks the concrete data sources selected for the platform. Sources are chosen **after** business questions are defined (see `docs/business-questions.md`).

Status values: `Not selected` | `Shortlisted` | `Selected` | `Ready` | `Retired`

`Mode` is mandatory for every source. It determines the ingestion path and the phase that builds it:

- **Streaming** — a long-lived WebSocket consumer runs inside the always-on producers container and publishes each message to Kinesis Data Streams; a Databricks Structured Streaming job lands it in a Bronze stream table. Proposed in ADR-008; the runtime is proposed in ADR-010.
- **Polling** — a long-lived loop in the same always-on producers container calls an HTTP API at a fixed interval and publishes each response to Kinesis Data Streams; it follows the same Bronze path as streaming.
- **Batch** — a scheduled MWAA/Airflow task pulls an HTTP API and writes raw JSON to S3; Bronze loads it with COPY INTO (ADR-001).
- **Managed sync** — a Fivetran connector, with no custom ingestion code.

Sources on the Kinesis path have no immutable raw S3 object: Kinesis retains messages for 24 hours and the first persistent copy is Bronze. Rejected messages go to the S3 quarantine prefix.

Everything marked **"To verify in spike"** is unknown today. Each source gets one spike in its phase that records a real sample in `tests/fixtures/` before any ingestion code is written. Do not fill these fields from memory or from another project.

---

## 1. EMSC — Earthquakes

| Property | Value |
|----------|-------|
| **Source Name** | `emsc_earthquakes` |
| **Mode** | Streaming |
| **Type** | Public real-time feed (WebSocket) |
| **Owner/Provider** | EMSC (European-Mediterranean Seismological Centre) |
| **Endpoint** | To verify in spike |
| **Authentication** | To verify in spike |
| **Rate Limits** | To verify in spike |
| **Response Format** | To verify in spike |
| **Expected Volume** | To verify in spike |
| **Data Grain** | To verify in spike (expected: one earthquake event per message) |
| **Raw S3 Path Pattern** | Not applicable — Kinesis path; first persistent copy is Bronze. Rejected messages: `s3://<bucket>/quarantine/stream/emsc_earthquakes/` |
| **Destination** | Bronze: `<catalog>.bronze.stream_emsc_earthquakes` (name proposed in ADR-008); Silver/Gold via dbt incremental |
| **Business Questions** | BQ-001 (primary); BQ-005 (corroboration) |
| **Status** | Selected |
| **Notes** | Built in P4c. Streaming path only; blocked until ADR-008, ADR-010 and ADR-011 are Accepted. Terms, licence and message shape to be captured in the spike. |

---

## 2. AISstream — Vessel Positions

| Property | Value |
|----------|-------|
| **Source Name** | `ais_vessel_positions` |
| **Mode** | Streaming |
| **Type** | Public real-time feed (WebSocket) |
| **Owner/Provider** | AISstream |
| **Endpoint** | To verify in spike |
| **Authentication** | To verify in spike |
| **Rate Limits** | To verify in spike |
| **Response Format** | To verify in spike |
| **Expected Volume** | To verify in spike (globally high; the spike must measure the volume for the selected feed filter) |
| **Data Grain** | To verify in spike (expected: one position report per vessel per observation) |
| **Raw S3 Path Pattern** | Not applicable — Kinesis path; first persistent copy is Bronze. Rejected messages: `s3://<bucket>/quarantine/stream/ais_vessel_positions/` |
| **Destination** | Bronze: `<catalog>.bronze.stream_ais_vessel_positions` (name proposed in ADR-008); Silver/Gold via dbt incremental |
| **Business Questions** | BQ-001 (supporting); BQ-002 (supporting); BQ-005 (corroboration) |
| **Status** | Selected |
| **Notes** | Built in P8b (high-volume scale-out). Streaming path only; blocked until ADR-008, ADR-010 and ADR-011 are Accepted. Volume control matters: the spike must document feed filtering and the producer's bounded window. Terms and licence to be captured in the spike. |

---

## 3. NASA FIRMS — Active Fires

| Property | Value |
|----------|-------|
| **Source Name** | `nasa_firms_fires` |
| **Mode** | Batch |
| **Type** | Scheduled HTTP API |
| **Owner/Provider** | NASA FIRMS |
| **Endpoint** | `https://firms.modaps.eosdis.nasa.gov/api/area/csv/<MAP_KEY>/<DATA_ID>/<AREA_COORDINATES>/<DAY_RANGE>[/<DATE>]`; availability at `/api/data_availability/csv/<MAP_KEY>/<DATA_ID>` (verified 2026-11-08) |
| **Authentication** | API key in the URL path (`<MAP_KEY>`); stored in AWS Secrets Manager as `${project_name}/firms` (`map_key`, optional `base_url`), never in code, fixtures or logs |
| **Rate Limits** | 5000 transactions per 10 minutes per API key (documented). Ingestion issues one request per satellite per run, far below the limit |
| **Response Format** | CSV, 14 columns, no trailing newline. Header: `latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight`. `satellite` is `N` / `N20` / `N21`, `instrument` is `VIIRS`, `version` is `2.0NRT`. The availability endpoint returns CSV `data_id,min_date,max_date` |
| **Expected Volume** | `world/5` on 2026-11-08: NOAA-20 243 788 rows (20.4 MB) and NOAA-21 235 219 rows (19.7 MB), about 155k rows per day combined; `world/1/2026-11-02` for SNPP 35 261 rows (2.9 MB). Small enough for one raw object per satellite per day |
| **Data Grain** | One satellite detection per location and time (one row per hot spot per overpass, per satellite) |
| **Raw S3 Path Pattern** | `s3://<bucket>/api/nasa_firms_fires/ingest_date=YYYY-MM-DD/<object>.csv`; one new object per satellite per `batch_id`, never overwritten |
| **Destination** | Bronze: `<catalog>.bronze.nasa_firms_fires` (three satellites land in one table, discriminated by the CSV `satellite` column) |
| **Business Questions** | BQ-004 (primary); BQ-005 (corroboration) |
| **Status** | Selected |
| **Notes** | Built in P4b. Fetched as three separate requests (`VIIRS_SNPP_NRT`, `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`); one satellite failing does not stop the others. A request accepts at most 5 days (`world/7` returns HTTP 400 `Invalid day range. Expects [1..5].`), so ingestion reads `data_availability` per satellite and requests an explicit date instead of `DAY_RANGE=5`. An empty day is a valid 122-byte header-only CSV and is not written to raw. **Suomi NPP stopped delivering new observations on 2026-11-02** (NASA Earthdata data alert), so its `max_date` is an end of data rather than a delay; NOAA-20 and NOAA-21 were one day behind on 2026-11-08. Whether the current UTC day keeps filling during the day is still To verify in spike. Fixtures: `tests/fixtures/nasa_firms_fires/`. |

### Licence and attribution (verified 2026-11-08)

Data and imagery are freely available and may be stored and redistributed; NASA supports full and open sharing of data. The provider texts below are recorded verbatim.

- Acknowledgement in publications (LANCE), from [earthdata.nasa.gov/data/projects/lance](https://www.earthdata.nasa.gov/data/projects/lance): "We acknowledge the use of data and/or imagery from NASA's Land, Atmosphere Near real-time Capability for Earth observations (LANCE) (https://earthdata.nasa.gov/lance), part of NASA's Earth Science Data and Information System (ESDIS)."
- Image captions, from the [FIRMS FAQ](https://www.earthdata.nasa.gov/data/tools/firms/faq): "when doing so for image captions, please cite it as "NASA FIRMS" and also consider including a direct link to the imagery in FIRMS to allow others to explore the imagery."
- FIRMS-specific acknowledgement, from the same [FIRMS FAQ](https://www.earthdata.nasa.gov/data/tools/firms/faq): "We acknowledge the use of imagery from the NASA LANCE FIRMS (https://earthdata.nasa.gov/firms), part of the NASA Earth Science Data and Information System (ESDIS)."
- Disclaimer, from [earthdata.nasa.gov/data/projects/lance/disclaimer](https://www.earthdata.nasa.gov/data/projects/lance/disclaimer): "LANCE is operated by the ESDIS project. The information presented through LANCE, GIBS, Worldview, and FIRMS are provided "as is" and users bear all responsibility and liability for their use of data."

---

## 4. USGS Water Data — River Gauges

| Property | Value |
|----------|-------|
| **Source Name** | `usgs_water_gauges` |
| **Mode** | Polling |
| **Type** | HTTP polling API (always-on) |
| **Owner/Provider** | USGS |
| **Endpoint** | To verify in spike |
| **Authentication** | To verify in spike |
| **Rate Limits** | To verify in spike |
| **Response Format** | To verify in spike |
| **Expected Volume** | To verify in spike |
| **Data Grain** | To verify in spike (expected: one observation per gauge and timestamp) |
| **Polling interval** | To verify in spike |
| **History available for initial backfill** | To verify in spike |
| **Raw S3 Path Pattern** | Not applicable — Kinesis path; first persistent copy is Bronze. Rejected messages: `s3://<bucket>/quarantine/stream/usgs_water_gauges/` |
| **Destination** | Bronze: `<catalog>.bronze.stream_usgs_water_gauges` (name proposed in ADR-008) |
| **Business Questions** | BQ-003 (primary); BQ-005 (corroboration) |
| **Status** | Selected |
| **Notes** | Built in P4c. Blocked until ADR-008, ADR-010 and ADR-011 are Accepted. The spike must confirm the parameter list for gauge height and discharge, how missing/estimated values are represented, the polling interval and the history available for backfill. |

---

## 5. NOAA — Ocean Buoys

| Property | Value |
|----------|-------|
| **Source Name** | `noaa_ocean_buoys` |
| **Mode** | Polling |
| **Type** | HTTP polling feed (always-on) |
| **Owner/Provider** | NOAA |
| **Endpoint** | To verify in spike |
| **Authentication** | To verify in spike |
| **Rate Limits** | To verify in spike |
| **Response Format** | To verify in spike |
| **Expected Volume** | To verify in spike |
| **Data Grain** | To verify in spike (expected: one observation per station and timestamp) |
| **Polling interval** | To verify in spike |
| **History available for initial backfill** | To verify in spike |
| **Raw S3 Path Pattern** | Not applicable — Kinesis path; first persistent copy is Bronze. Rejected messages: `s3://<bucket>/quarantine/stream/noaa_ocean_buoys/` |
| **Destination** | Bronze: `<catalog>.bronze.stream_noaa_ocean_buoys` (name proposed in ADR-008) |
| **Business Questions** | BQ-002 (primary); BQ-005 (corroboration) |
| **Status** | Selected |
| **Notes** | Built in P4c. Blocked until ADR-008, ADR-010 and ADR-011 are Accepted. The spike must confirm which station set and which measurements (wave height, atmospheric pressure) are available, their update cadence, the polling interval and the history available for backfill. |

---

## 6. GDACS — Disaster Alerts

| Property | Value |
|----------|-------|
| **Source Name** | `gdacs_disaster_alerts` |
| **Mode** | Polling |
| **Type** | RSS / API polling (always-on) |
| **Owner/Provider** | GDACS (Global Disaster Alert and Coordination System) |
| **Endpoint** | To verify in spike |
| **Authentication** | To verify in spike |
| **Rate Limits** | To verify in spike |
| **Response Format** | To verify in spike |
| **Expected Volume** | To verify in spike |
| **Data Grain** | To verify in spike (expected: one disaster event per item, updated over its lifetime) |
| **Polling interval** | To verify in spike |
| **History available for initial backfill** | To verify in spike |
| **Raw S3 Path Pattern** | Not applicable — Kinesis path; first persistent copy is Bronze. Rejected messages: `s3://<bucket>/quarantine/stream/gdacs_disaster_alerts/` |
| **Destination** | Bronze: `<catalog>.bronze.stream_gdacs_disaster_alerts` (name proposed in ADR-008) |
| **Business Questions** | BQ-005 (primary) |
| **Status** | Selected |
| **Notes** | Built in P4c. Blocked until ADR-008, ADR-010 and ADR-011 are Accepted. The spike must decide RSS or API, record the polling interval and the history available for backfill, and record how event updates (same event, new alert level) appear so Silver can keep history without duplicating events. |

---

## SaaS / Database Source — Supabase PostgreSQL via Fivetran

| Property | Value |
|----------|-------|
| **Source Name** | `macro_watchlist_db` |
| **Mode** | Managed sync |
| **Type** | Operational PostgreSQL database |
| **Owner/Provider** | Supabase |
| **Database** | Supabase PostgreSQL (via session pooler) |
| **Fivetran Connector** | PostgreSQL |
| **Authentication** | Database credentials (provided later through approved secret mechanism) |
| **Sync Frequency** | Daily (or on-demand via Airflow trigger) |
| **Expected Volume (per sync)** | Under 1,000 rows total across all tables |
| **Data Grain** | One row per entity (`watch_region`, `alert_rule`) |
| **Destination** | Databricks: `dwh_dev.raw_fivetran.<table>` (Fivetran destination schema prefix to be confirmed in P8) |
| **Status** | Selected |
| **Notes** | Re-scoped by ADR-012 (Proposed): the tables are `watch_region` and `alert_rule`, replacing the earlier `watchlist_country`, `watchlist_indicator` and old `alert_rule`. They hold reference data for the Gold alert evaluation, not copies of the public feeds. Until P8 the producers read static configuration from the repository. Fivetran is optional (D-001); if the Databricks destination is unavailable or cost-prohibitive on the plan, P8 is formally skipped with a reason. Security: TLS, dedicated read-only Fivetran database user, no credentials in Git, credentials stored through the approved secret mechanism. Supabase project created manually, outside AWS Terraform; the AWS persistent stack only holds the secret container. Session pooler connection, Query-Based sync with xmin cursor (exact cursor to verify in P8). See ADR-007 and ADR-012. |

---

## Retired Sources

Retained here for history. Any ingestion code for them still in the repository will be removed in a later chore, after the shared ingestion core is generalised.

| Source | Former Role | Retired | Reason |
|--------|-------------|---------|--------|
| `world_bank_indicators` | API 1 (macro indicators, batch) | 2026-11-06 | Project re-scoped to Earth monitoring; macro questions retired |
| `fred_economic_series` | API 2 (macro series, batch) | 2026-11-06 | Project re-scoped to Earth monitoring; macro questions retired |

---

## Source Selection Criteria

1. **Business questions first**: sources must answer the questions in `docs/business-questions.md`
2. **Real data**: no synthetic or mock APIs in the production pipeline
3. **Mode variety**: the set must exercise streaming, polling, batch and managed sync
4. **Auth variety**: at least one source must exercise API-key handling through Secrets Manager
5. **Volume**: portfolio-scale (thousands to low millions of records per run), except where ADR-011 explicitly allows more
6. **Accessibility**: publicly accessible or a free tier that supports a demo
7. **Licence**: terms must allow the use the project makes of the data; recorded per source in its spike

---

## Decision Log

| Date | Source | Previous Status | New Status | Decision Maker | Notes |
|------|--------|-----------------|------------|----------------|-------|
| 2026-09-29 | World Bank Indicators | Not selected | Selected | Afonso | Approved for BQ-001, BQ-003 |
| 2026-09-29 | FRED Economic Series | Not selected | Selected | Afonso | Approved for BQ-002 |
| 2026-09-29 | Amazon RDS PostgreSQL (macro_watchlist_db) | Not selected | Selected | Afonso | Approved for BQ-001, BQ-003; Fivetran path |
| 2026-10-13 | Amazon RDS PostgreSQL -> Supabase PostgreSQL (macro_watchlist_db) | Selected (RDS) | Selected (Supabase) | Afonso | RDS -> Supabase, ADR-007 supersedes ADR-005 |
| 2026-11-06 | EMSC (earthquakes) | Not selected | Selected | Afonso | Streaming; BQ-001 |
| 2026-11-06 | AISstream (vessel positions) | Not selected | Selected | Afonso | Streaming; BQ-001, BQ-002, BQ-005 |
| 2026-11-06 | NASA FIRMS (active fires) | Not selected | Selected | Afonso | Batch; BQ-004 |
| 2026-11-06 | USGS Water Data (river gauges) | Not selected | Selected | Afonso | Polling; BQ-003 |
| 2026-11-06 | NOAA (ocean buoys) | Not selected | Selected | Afonso | Polling; BQ-002 |
| 2026-11-06 | GDACS (disaster alerts) | Not selected | Selected | Afonso | Polling; BQ-005 |
| 2026-11-06 | Supabase PostgreSQL (macro_watchlist_db) | Selected | Selected (re-scoped) | Afonso | Tables `watch_region`, `alert_rule`; ADR-012 amends ADR-007 |
| 2026-11-06 | World Bank Indicators | Selected | Retired | Afonso | Project re-scoped to Earth monitoring |
| 2026-11-06 | FRED Economic Series | Selected | Retired | Afonso | Project re-scoped to Earth monitoring |
