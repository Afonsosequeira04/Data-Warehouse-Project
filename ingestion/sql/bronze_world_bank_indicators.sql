-- Bronze table for World Bank Indicators
-- Loaded via COPY INTO from raw NDJSON in S3 (ADR-001)
-- Source: s3://${raw_bucket}/api/world_bank_indicators/ingest_date=YYYY-MM-DD/<batch_id>/*.json

CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.world_bank_indicators (
    -- Source data fields
    country_id STRING NOT NULL,
    country_name STRING NOT NULL,
    indicator_id STRING NOT NULL,
    indicator_name STRING NOT NULL,
    year INT NOT NULL,
    value DOUBLE,
    unit STRING,
    obs_status STRING,
    `decimal` INT,

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
COPY INTO ${catalog}.${schema}.world_bank_indicators
FROM (
    SELECT
        -- COPY INTO exposes top-level JSON fields as columns for NDJSON (multiLine=false)
        country.id::STRING AS country_id,
        country.value::STRING AS country_name,
        indicator.id::STRING AS indicator_id,
        indicator.value::STRING AS indicator_name,
        CAST(date AS INT) AS year,
        TRY_CAST(value AS DOUBLE) AS value,
        unit::STRING AS unit,
        obs_status::STRING AS obs_status,
        TRY_CAST(`decimal` AS INT) AS `decimal`,
        -- Technical metadata
        _metadata.file_path AS _source_file,
        CURRENT_TIMESTAMP() AS _ingested_at,
        '${batch_id}' AS _batch_id,
        'world_bank_indicators' AS _source_system,
        TO_DATE('${batch_date}') AS _batch_date
    FROM '${raw_path}'
)
FILEFORMAT = JSON
FORMAT_OPTIONS ('multiLine' = 'false')
COPY_OPTIONS (
    'mergeSchema' = 'false',
    'force' = 'false'
);

-- Verification query: count rows and verify batch_id
-- SELECT _batch_id, COUNT(*) as row_count, MIN(year), MAX(year)
-- FROM ${catalog}.${schema}.world_bank_indicators
-- WHERE _batch_id = '${batch_id}'
-- GROUP BY _batch_id;