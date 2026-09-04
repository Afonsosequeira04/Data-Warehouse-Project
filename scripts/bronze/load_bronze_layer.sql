-- =============================================================
-- Bronze Layer Load Script
-- =============================================================
-- Progress log (kept here so it travels with the script):
--   v1 - Basic load: one COPY per table, no error handling.
--   v2 - Wrapped each table load in BEGIN...EXCEPTION WHEN OTHERS,
--        so one bad table doesn't stop the rest from loading.
--   v3 - Added all 5 upgrades discussed:
--          1. Persistent error logging -> bronze.load_errors table
--          2. Per-table and total batch timing (clock_timestamp())
--          3. Branching by error type (undefined_file /
--             bad_copy_file_format / OTHERS) instead of one
--             catch-all handler
--          4. Success/fail summary count at the end of the run
--          5. Retry logic: up to 3 attempts per table with a short
--             pause between attempts, for errors that are likely
--             transient (locked file, brief I/O hiccup). A missing
--             file (undefined_file) is NOT retried, since retrying
--             won't make a nonexistent file appear.
--
-- Source: translated from a YouTube data warehouse tutorial
-- originally written for SQL Server; adapted here for Postgres.
-- =============================================================


-- =============================================================
-- Error log table (created once, outside the procedure)
-- IF NOT EXISTS means re-running this whole script is safe and
-- won't wipe out the history of past failed runs.
-- =============================================================
CREATE TABLE IF NOT EXISTS bronze.load_errors (
    error_id       SERIAL PRIMARY KEY,
    table_name     TEXT,
    error_type     TEXT,
    error_message  TEXT,
    attempt_number INT,
    occurred_at    TIMESTAMP DEFAULT now()
);


-- =============================================================
-- Procedure: bronze.load_bronze
-- =============================================================
-- Script Purpose:
--     Loads data into the 'bronze' schema tables from external CSV
--     files. Each table is truncated before loading, so calling
--     this procedure is safe to repeat anytime.
--
--     Each table load:
--       - is wrapped in its own BEGIN...EXCEPTION block
--       - is retried up to 3 times if it hits a likely-transient
--         error (anything other than a missing file)
--       - logs every failed attempt permanently to
--         bronze.load_errors, tagged with the error type
--       - is timed individually with clock_timestamp()
--
--     If a table fails all retry attempts, the procedure logs it
--     as failed and moves on to the next table instead of stopping
--     the whole batch.
--
-- Usage:
--     CALL bronze.load_bronze();
-- =============================================================
CREATE OR REPLACE PROCEDURE bronze.load_bronze()
LANGUAGE plpgsql
AS $$
DECLARE
    batch_start_time TIMESTAMP;
    batch_end_time   TIMESTAMP;
    start_time       TIMESTAMP;
    end_time         TIMESTAMP;
    success_count    INT := 0;
    fail_count       INT := 0;

    max_retries      INT := 3;
    retry_delay_sec  NUMERIC := 2;   -- pause between retry attempts
    attempt          INT;
    loaded           BOOLEAN;
BEGIN
    batch_start_time := clock_timestamp();

    -- =========================================================
    -- crm_cust_info
    -- =========================================================
    RAISE NOTICE 'Loading table: crm_cust_info';
    start_time := clock_timestamp();
    attempt := 0;
    loaded  := FALSE;
    WHILE attempt < max_retries AND NOT loaded LOOP
        attempt := attempt + 1;
        BEGIN
            TRUNCATE TABLE bronze.crm_cust_info;
            COPY bronze.crm_cust_info
            FROM '/Users/ritamoreda/Desktop/source_crm/cust_info.csv'
            DELIMITER ','
            CSV HEADER;
            loaded := TRUE;
            success_count := success_count + 1;
        EXCEPTION
            WHEN undefined_file THEN
                RAISE WARNING 'File not found for crm_cust_info: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('crm_cust_info', 'undefined_file', SQLERRM, attempt);
                attempt := max_retries; -- don't retry a missing file
            WHEN bad_copy_file_format THEN
                RAISE WARNING 'CSV format issue in crm_cust_info: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('crm_cust_info', 'bad_copy_file_format', SQLERRM, attempt);
                attempt := max_retries; -- format won't fix itself either
            WHEN OTHERS THEN
                RAISE WARNING 'Attempt % failed for crm_cust_info: %', attempt, SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('crm_cust_info', 'other', SQLERRM, attempt);
                IF attempt < max_retries THEN
                    PERFORM pg_sleep(retry_delay_sec);
                END IF;
        END;
    END LOOP;
    IF NOT loaded THEN
        fail_count := fail_count + 1;
    END IF;
    end_time := clock_timestamp();
    RAISE NOTICE 'Duration: % seconds', EXTRACT(EPOCH FROM (end_time - start_time));

    -- =========================================================
    -- crm_prd_info
    -- =========================================================
    RAISE NOTICE 'Loading table: crm_prd_info';
    start_time := clock_timestamp();
    attempt := 0;
    loaded  := FALSE;
    WHILE attempt < max_retries AND NOT loaded LOOP
        attempt := attempt + 1;
        BEGIN
            TRUNCATE TABLE bronze.crm_prd_info;
            COPY bronze.crm_prd_info
            FROM '/Users/ritamoreda/Desktop/source_crm/prd_info.csv'
            DELIMITER ','
            CSV HEADER;
            loaded := TRUE;
            success_count := success_count + 1;
        EXCEPTION
            WHEN undefined_file THEN
                RAISE WARNING 'File not found for crm_prd_info: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('crm_prd_info', 'undefined_file', SQLERRM, attempt);
                attempt := max_retries;
            WHEN bad_copy_file_format THEN
                RAISE WARNING 'CSV format issue in crm_prd_info: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('crm_prd_info', 'bad_copy_file_format', SQLERRM, attempt);
                attempt := max_retries;
            WHEN OTHERS THEN
                RAISE WARNING 'Attempt % failed for crm_prd_info: %', attempt, SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('crm_prd_info', 'other', SQLERRM, attempt);
                IF attempt < max_retries THEN
                    PERFORM pg_sleep(retry_delay_sec);
                END IF;
        END;
    END LOOP;
    IF NOT loaded THEN
        fail_count := fail_count + 1;
    END IF;
    end_time := clock_timestamp();
    RAISE NOTICE 'Duration: % seconds', EXTRACT(EPOCH FROM (end_time - start_time));

    -- =========================================================
    -- crm_sales_details
    -- =========================================================
    RAISE NOTICE 'Loading table: crm_sales_details';
    start_time := clock_timestamp();
    attempt := 0;
    loaded  := FALSE;
    WHILE attempt < max_retries AND NOT loaded LOOP
        attempt := attempt + 1;
        BEGIN
            TRUNCATE TABLE bronze.crm_sales_details;
            COPY bronze.crm_sales_details
            FROM '/Users/ritamoreda/Desktop/source_crm/sales_details.csv'
            DELIMITER ','
            CSV HEADER;
            loaded := TRUE;
            success_count := success_count + 1;
        EXCEPTION
            WHEN undefined_file THEN
                RAISE WARNING 'File not found for crm_sales_details: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('crm_sales_details', 'undefined_file', SQLERRM, attempt);
                attempt := max_retries;
            WHEN bad_copy_file_format THEN
                RAISE WARNING 'CSV format issue in crm_sales_details: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('crm_sales_details', 'bad_copy_file_format', SQLERRM, attempt);
                attempt := max_retries;
            WHEN OTHERS THEN
                RAISE WARNING 'Attempt % failed for crm_sales_details: %', attempt, SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('crm_sales_details', 'other', SQLERRM, attempt);
                IF attempt < max_retries THEN
                    PERFORM pg_sleep(retry_delay_sec);
                END IF;
        END;
    END LOOP;
    IF NOT loaded THEN
        fail_count := fail_count + 1;
    END IF;
    end_time := clock_timestamp();
    RAISE NOTICE 'Duration: % seconds', EXTRACT(EPOCH FROM (end_time - start_time));

    -- =========================================================
    -- erp_cust_az12
    -- =========================================================
    RAISE NOTICE 'Loading table: erp_cust_az12';
    start_time := clock_timestamp();
    attempt := 0;
    loaded  := FALSE;
    WHILE attempt < max_retries AND NOT loaded LOOP
        attempt := attempt + 1;
        BEGIN
            TRUNCATE TABLE bronze.erp_cust_az12;
            COPY bronze.erp_cust_az12
            FROM '/Users/ritamoreda/Desktop/source_erp/CUST_AZ12.csv'
            DELIMITER ','
            CSV HEADER;
            loaded := TRUE;
            success_count := success_count + 1;
        EXCEPTION
            WHEN undefined_file THEN
                RAISE WARNING 'File not found for erp_cust_az12: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('erp_cust_az12', 'undefined_file', SQLERRM, attempt);
                attempt := max_retries;
            WHEN bad_copy_file_format THEN
                RAISE WARNING 'CSV format issue in erp_cust_az12: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('erp_cust_az12', 'bad_copy_file_format', SQLERRM, attempt);
                attempt := max_retries;
            WHEN OTHERS THEN
                RAISE WARNING 'Attempt % failed for erp_cust_az12: %', attempt, SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('erp_cust_az12', 'other', SQLERRM, attempt);
                IF attempt < max_retries THEN
                    PERFORM pg_sleep(retry_delay_sec);
                END IF;
        END;
    END LOOP;
    IF NOT loaded THEN
        fail_count := fail_count + 1;
    END IF;
    end_time := clock_timestamp();
    RAISE NOTICE 'Duration: % seconds', EXTRACT(EPOCH FROM (end_time - start_time));

    -- =========================================================
    -- erp_loc_a101
    -- =========================================================
    RAISE NOTICE 'Loading table: erp_loc_a101';
    start_time := clock_timestamp();
    attempt := 0;
    loaded  := FALSE;
    WHILE attempt < max_retries AND NOT loaded LOOP
        attempt := attempt + 1;
        BEGIN
            TRUNCATE TABLE bronze.erp_loc_a101;
            COPY bronze.erp_loc_a101
            FROM '/Users/ritamoreda/Desktop/source_erp/LOC_A101.csv'
            DELIMITER ','
            CSV HEADER;
            loaded := TRUE;
            success_count := success_count + 1;
        EXCEPTION
            WHEN undefined_file THEN
                RAISE WARNING 'File not found for erp_loc_a101: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('erp_loc_a101', 'undefined_file', SQLERRM, attempt);
                attempt := max_retries;
            WHEN bad_copy_file_format THEN
                RAISE WARNING 'CSV format issue in erp_loc_a101: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('erp_loc_a101', 'bad_copy_file_format', SQLERRM, attempt);
                attempt := max_retries;
            WHEN OTHERS THEN
                RAISE WARNING 'Attempt % failed for erp_loc_a101: %', attempt, SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('erp_loc_a101', 'other', SQLERRM, attempt);
                IF attempt < max_retries THEN
                    PERFORM pg_sleep(retry_delay_sec);
                END IF;
        END;
    END LOOP;
    IF NOT loaded THEN
        fail_count := fail_count + 1;
    END IF;
    end_time := clock_timestamp();
    RAISE NOTICE 'Duration: % seconds', EXTRACT(EPOCH FROM (end_time - start_time));

    -- =========================================================
    -- erp_px_cat_g1v2
    -- =========================================================
    RAISE NOTICE 'Loading table: erp_px_cat_g1v2';
    start_time := clock_timestamp();
    attempt := 0;
    loaded  := FALSE;
    WHILE attempt < max_retries AND NOT loaded LOOP
        attempt := attempt + 1;
        BEGIN
            TRUNCATE TABLE bronze.erp_px_cat_g1v2;
            COPY bronze.erp_px_cat_g1v2
            FROM '/Users/ritamoreda/Desktop/source_erp/PX_CAT_G1V2.csv'
            DELIMITER ','
            CSV HEADER;
            loaded := TRUE;
            success_count := success_count + 1;
        EXCEPTION
            WHEN undefined_file THEN
                RAISE WARNING 'File not found for erp_px_cat_g1v2: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('erp_px_cat_g1v2', 'undefined_file', SQLERRM, attempt);
                attempt := max_retries;
            WHEN bad_copy_file_format THEN
                RAISE WARNING 'CSV format issue in erp_px_cat_g1v2: %', SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('erp_px_cat_g1v2', 'bad_copy_file_format', SQLERRM, attempt);
                attempt := max_retries;
            WHEN OTHERS THEN
                RAISE WARNING 'Attempt % failed for erp_px_cat_g1v2: %', attempt, SQLERRM;
                INSERT INTO bronze.load_errors (table_name, error_type, error_message, attempt_number)
                VALUES ('erp_px_cat_g1v2', 'other', SQLERRM, attempt);
                IF attempt < max_retries THEN
                    PERFORM pg_sleep(retry_delay_sec);
                END IF;
        END;
    END LOOP;
    IF NOT loaded THEN
        fail_count := fail_count + 1;
    END IF;
    end_time := clock_timestamp();
    RAISE NOTICE 'Duration: % seconds', EXTRACT(EPOCH FROM (end_time - start_time));

    -- =========================================================
    -- Summary
    -- =========================================================
    batch_end_time := clock_timestamp();
    RAISE NOTICE 'Bronze layer load complete: % succeeded, % failed', success_count, fail_count;
    RAISE NOTICE 'Total batch duration: % seconds', EXTRACT(EPOCH FROM (batch_end_time - batch_start_time));
END;
$$;


-- =============================================================
-- Run the load
-- =============================================================
CALL bronze.load_bronze();


-- =============================================================
-- Verify row counts after loading
-- =============================================================
SELECT 'crm_cust_info' AS table_name, COUNT(*) FROM bronze.crm_cust_info
UNION ALL
SELECT 'crm_prd_info', COUNT(*) FROM bronze.crm_prd_info
UNION ALL
SELECT 'crm_sales_details', COUNT(*) FROM bronze.crm_sales_details
UNION ALL
SELECT 'erp_cust_az12', COUNT(*) FROM bronze.erp_cust_az12
UNION ALL
SELECT 'erp_loc_a101', COUNT(*) FROM bronze.erp_loc_a101
UNION ALL
SELECT 'erp_px_cat_g1v2', COUNT(*) FROM bronze.erp_px_cat_g1v2;


-- =============================================================
-- Check logged errors from any run (persists across sessions)
-- =============================================================
SELECT * FROM bronze.load_errors ORDER BY occurred_at DESC;
