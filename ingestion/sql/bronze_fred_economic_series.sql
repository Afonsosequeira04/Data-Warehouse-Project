-- Bronze table for FRED Economic Series observations
-- Loaded via COPY INTO from raw NDJSON in S3 (ADR-001)
-- Source: s3://${raw_bucket}/api/fred_economic_series/ingest_date=YYYY-MM-DD/<batch_id>/<series_id>.ndjson
-- Note: value stays STRING in Bronze so the FRED "." missing-value marker is preserved;
-- it is cast to NULL in Silver.

CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.fred_economic_series (
    -- Source data fields
    series_id STRING NOT NULL,
    `date` DATE NOT NULL,
    value STRING,
    realtime_start DATE NOT NULL,
    realtime_end DATE NOT NULL,

    -- Technical metadata (added at ingestion)
    _batch_id STRING NOT NULL,
    _ingested_at TIMESTAMP NOT NULL,
    _source_file STRING NOT NULL,
    _source_system STRING NOT NULL,
    _batch_date DATE NOT NULL
)
USING DELTA
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'pipelines.autoOptimize.managed' = 'true'
);

-- COPY INTO statement for incremental loading
-- Run this after raw NDJSON files are written to S3 for a given batch
COPY INTO ${catalog}.${schema}.fred_economic_series
FROM (
    SELECT
        -- COPY INTO exposes top-level JSON fields as columns for NDJSON (multiLine=false)
        '${series_id}' AS series_id,
        CAST(`date` AS DATE) AS `date`,
        value::STRING AS value,
        CAST(realtime_start AS DATE) AS realtime_start,
        CAST(realtime_end AS DATE) AS realtime_end,
        -- Technical metadata
        _metadata.file_path AS _source_file,
        CURRENT_TIMESTAMP() AS _ingested_at,
        '${batch_id}' AS _batch_id,
        'fred_economic_series' AS _source_system,
        TO_DATE('${batch_date}') AS _batch_date
    FROM '${raw_path}'
)
FILEFORMAT = JSON
FORMAT_OPTIONS ('multiLine' = 'false')
COPY_OPTIONS (
    'mergeSchema' = 'false',
    'force' = 'false'
);

-- Verification query: count rows and verify batch_id for one series
-- SELECT _batch_id, series_id, COUNT(*) as row_count, MIN(`date`), MAX(`date`)
-- FROM ${catalog}.${schema}.fred_economic_series
-- WHERE _batch_id = '${batch_id}'
-- GROUP BY _batch_id, series_id;
