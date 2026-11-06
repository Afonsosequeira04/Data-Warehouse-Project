# Business Questions

This document defines the analytical questions the Gold layer and dashboards must answer. **Business questions are defined before selecting data sources.**

The chosen sources must collectively enable answering these questions. The questions are approved; the grain, dimensions and metrics below are drafts to be confirmed by Afonso during the dbt phase.

---

## Business Questions

### BQ-001

**Question:**

Which significant recent earthquakes occurred, and which vessels were near each event?

**Domain:**

Seismic hazards / Maritime exposure monitoring

**Required Grain:**

earthquake event + vessel position (to be confirmed by Afonso in review)

**Required Dimensions:**

- event location
- event magnitude and depth
- event time
- vessel identity
- vessel location at observation time
- distance between vessel and event

**Required Metrics:**

- number of significant events in the analysis window
- number of vessels within a configurable radius per event
- time between event and nearest vessel observation

**Time Range:**

rolling last 24-72 hours for live events, with longer history where retained

**Sources:**

EMSC (streaming) + AISstream (streaming)

**Status:**

Approved (grain, dimensions and metrics draft)

---

### BQ-002

**Question:**

Which ocean buoys report anomalous wave height or atmospheric pressure, and which vessels are in the affected area?

**Domain:**

Maritime hazards / Sea-state monitoring

**Required Grain:**

buoy station + observation time + vessel area observation (to be confirmed by Afonso in review)

**Required Dimensions:**

- station identity
- station location
- observation time
- wave height
- atmospheric pressure
- vessel identity and location

**Required Metrics:**

- current value vs. recent baseline per station
- anomaly indicator per metric
- number of vessels in the affected area

**Time Range:**

rolling recent window, with historical baseline built from the retained history

**Sources:**

NOAA (micro-batch) + AISstream (streaming)

**Status:**

Approved (grain, dimensions and metrics draft)

---

### BQ-003

**Question:**

Which river gauges are near or above flood thresholds, or rising unusually fast?

**Domain:**

Hydrological hazards / Flood monitoring

**Required Grain:**

gauge station + observation time (to be confirmed by Afonso in review)

**Required Dimensions:**

- station identity
- station location
- observation time
- gauge height and discharge
- threshold configured in `alert_rule`

**Required Metrics:**

- latest gauge height and discharge
- difference from the configured threshold
- rate of change over the recent window
- flood status

**Time Range:**

latest available observation plus the recent window needed for rate of change

**Sources:**

USGS Water Data (micro-batch) + `macro_watchlist_db` alert rules (Supabase PostgreSQL via Fivetran, re-scoped by ADR-012)

**Status:**

Approved (grain, dimensions and metrics draft)

---

### BQ-004

**Question:**

Where are fires currently active, and how is fire activity evolving by region?

**Domain:**

Wildfire hazards / Regional activity monitoring

**Required Grain:**

fire detection + region + time (to be confirmed by Afonso in review)

**Required Dimensions:**

- detection location
- detection time
- satellite and confidence
- region
- fire radiative power where available

**Required Metrics:**

- active detections per region
- detections over time by region
- fire radiative power sum/average per region

**Time Range:**

recent days for active fires, plus retained history for evolution

**Sources:**

NASA FIRMS (batch)

**Status:**

Approved (grain, dimensions and metrics draft)

---

### BQ-005

**Question:**

Which GDACS orange or red events are active, and what do the other sources show nearby?

**Domain:**

Multi-hazard situational awareness

**Required Grain:**

disaster event + nearby observations from other sources (to be confirmed by Afonso in review)

**Required Dimensions:**

- event identity and type
- alert level (orange/red)
- event location and time
- country and region
- nearby earthquakes, fires, gauges, buoys and vessels

**Required Metrics:**

- number of active orange/red events
- count of corroborating nearby observations per event
- time since the event was last updated

**Time Range:**

active events, with retained history for post-event review

**Sources:**

GDACS (micro-batch) + all other sources for corroboration

**Status:**

Approved (grain, dimensions and metrics draft)

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
| BQ-001 | EMSC | AISstream | dim_earthquake_event, dim_vessel, fact_vessel_position, bridge_event_vessel_proximity |
| BQ-002 | NOAA | AISstream | dim_buoy_station, fact_buoy_observation, dim_vessel, fact_vessel_position |
| BQ-003 | USGS Water Data | macro_watchlist_db (Supabase PostgreSQL via Fivetran) | dim_gauge_station, fact_gauge_observation, dim_alert_rule, fact_alert_evaluation |
| BQ-004 | NASA FIRMS | none | dim_region, fact_fire_detection |
| BQ-005 | GDACS | EMSC, NOAA, USGS, NASA FIRMS, AISstream | dim_disaster_event, fact_disaster_event, fact_disaster_corroboration |

Model names are indicative and may change in the dbt phase.

---

## Open Questions for the dbt Phase

- **Common spatial key.** Several questions join observations by location (earthquake ↔ vessel, buoy ↔ vessel, disaster ↔ nearby events). We need one spatial key across sources. H3 is the leading candidate; the resolution is still to be chosen (coarse enough to be stable, fine enough to be useful). Decision belongs to the dbt phase.
- **Same earthquake in EMSC and GDACS.** GDACS aggregates events that EMSC may also report. The dbt phase must define how to reconcile them without double counting (matching on time, location and magnitude, and which source wins for the event record).

---

## Notes

- Do not invent business questions that are not already specified by project documentation
- Keep the list small (5 core questions) for portfolio scope
- Each question should be answerable by a single dashboard tile or a small set of related tiles
- The technical datasheet and README reflect the current selected sources: EMSC, AISstream, NASA FIRMS, USGS Water Data, NOAA, GDACS, and Supabase PostgreSQL via Fivetran
