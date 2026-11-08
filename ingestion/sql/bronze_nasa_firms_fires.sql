-- Bronze table for NASA FIRMS active fire detections (VIIRS satellites)
-- Loaded via idempotent COPY INTO from the immutable raw CSVs in S3 (ADR-001)
-- Source: s3://${raw_bucket}/api/nasa_firms_fires/ingest_date=YYYY-MM-DD/<batch_id>/<data_id>_<YYYY-MM-DD>.csv
--
-- All source columns stay STRING in Bronze: ingestion validates structure only
-- (header + 14 fields per row, ADR-002) and typing/normalisation happens in the
-- dbt staging models. Keeping them as text means one odd numeric value cannot
-- fail the whole COPY INTO.
--
-- The CSV already carries the satellite short code (N, N20, N21) in its own
-- `satellite` column. The request-level lineage column is therefore named
-- `data_id` (VIIRS_NOAA20_NRT, ...) and is derived from the raw file name, so
-- Bronze never has two columns with the same meaning.

CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.nasa_firms_fires (
    -- Source data fields (exact CSV header order, all STRING in Bronze)
    latitude STRING,
    longitude STRING,
    bright_ti4 STRING,
    scan STRING,
    track STRING,
    acq_date STRING,
    acq_time STRING,
    satellite STRING,
    instrument STRING,
    confidence STRING,
    version STRING,
    bright_ti5 STRING,
    frp STRING,
    daynight STRING,

    -- Technical metadata (added at ingestion)
    data_id STRING NOT NULL,
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

-- COPY INTO statement for incremental loading.
-- ${raw_path} is the batch prefix with a glob (…/<batch_id>/*.csv), so all
-- satellites of one batch load in a single idempotent statement: COPY INTO
-- tracks the files it already loaded and skips them on a rerun.
COPY INTO ${catalog}.${schema}.nasa_firms_fires
FROM (
    SELECT
        -- CSV fields are named by the header row ('header' = 'true')
        latitude,
        longitude,
        bright_ti4,
        scan,
        track,
        acq_date,
        acq_time,
        satellite,
        instrument,
        confidence,
        version,
        bright_ti5,
        frp,
        daynight,
        -- Lineage: file name is <data_id>_<YYYY-MM-DD>.csv, already lowercased
        -- by the raw writer, so upper() restores VIIRS_*_NRT.
        UPPER(
            REGEXP_EXTRACT(
                _metadata.file_path,
                '/([a-z0-9_]+)_[0-9]{4}-[0-9]{2}-[0-9]{2}[.]csv$',
                1
            )
        ) AS data_id,
        -- Technical metadata
        _metadata.file_path AS _source_file,
        CURRENT_TIMESTAMP() AS _ingested_at,
        '${batch_id}' AS _batch_id,
        'nasa_firms_fires' AS _source_system,
        TO_DATE('${batch_date}') AS _batch_date
    FROM '${raw_path}'
)
FILEFORMAT = CSV
FORMAT_OPTIONS (
    'header' = 'true',
    'sep' = ',',
    'quote' = '"',
    'escape' = '"',
    'encoding' = 'UTF-8'
)
COPY_OPTIONS (
    'mergeSchema' = 'false',
    'force' = 'false'
);

-- Verification query: row count per satellite for one batch
-- SELECT data_id, _batch_id, COUNT(*) AS row_count
-- FROM ${catalog}.${schema}.nasa_firms_fires
-- WHERE _batch_id = '${batch_id}'
-- GROUP BY data_id, _batch_id;
