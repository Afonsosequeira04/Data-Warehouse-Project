-- Bronze table for World Bank Indicators
-- Loaded via COPY INTO from raw JSON in S3 (ADR-001)
-- Source: s3://${raw_bucket}/api/world_bank_indicators/ingest_date=YYYY-MM-DD/<batch_id>/*.json

CREATE TABLE IF NOT EXISTS ${catalog}.bronze.world_bank_indicators (
    -- Source data fields
    country_id STRING NOT NULL,
    country_name STRING NOT NULL,
    indicator_id STRING NOT NULL,
    indicator_name STRING NOT NULL,
    year INT NOT NULL,
    value DOUBLE,
    unit STRING,
    obs_status STRING,
    decimal INT,

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
-- Run this after raw JSON files are written to S3 for a given batch
COPY INTO ${catalog}.bronze.world_bank_indicators
FROM (
    SELECT
        -- Extract from JSON structure
        json_data:country.id::STRING AS country_id,
        json_data:country.value::STRING AS country_name,
        json_data:indicator.id::STRING AS indicator_id,
        json_data:indicator.value::STRING AS indicator_name,
        json_data:date::INT AS year,
        CASE
            WHEN json_data:value IS NOT NULL AND json_data:value != '' THEN json_data:value::DOUBLE
            ELSE NULL
        END AS value,
        json_data:unit::STRING AS unit,
        json_data:obs_status::STRING AS obs_status,
        CASE
            WHEN json_data:decimal IS NOT NULL AND json_data:decimal != '' THEN json_data:decimal::INT
            ELSE NULL
        END AS decimal,
        -- Technical metadata
        _metadata.file_path AS _source_file,
        CURRENT_TIMESTAMP() AS _ingested_at,
        '${batch_id}' AS _batch_id,
        'world_bank_indicators' AS _source_system,
        TO_DATE('${batch_date}') AS _batch_date
    FROM '${raw_path}'
)
FILEFORMAT = JSON
FORMAT_OPTIONS ('multiline' = 'true')
COPY_OPTIONS (
    'mergeSchema' = 'false',
    'force' = 'false'
);

-- Verification query: count rows and verify batch_id
-- SELECT _batch_id, COUNT(*) as row_count, MIN(year), MAX(year)
-- FROM ${catalog}.bronze.world_bank_indicators
-- WHERE _batch_id = '${batch_id}'
-- GROUP BY _batch_id;