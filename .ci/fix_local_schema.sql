-- ============================================================================
-- LOCAL DATABASE SCHEMA FIX
-- ============================================================================
-- Purpose: Fix local database to match production (which is already correct)
--
-- IMPORTANT: Run this on LOCAL database, NOT production!
--
-- Usage:
--   psql -h localhost -p 5432 -U admin -d erp -f .ci/fix_local_schema.sql
-- ============================================================================

BEGIN;

-- ============================================================================
-- Check current state
-- ============================================================================
\echo 'Current schema for included_adhoc_ids:'
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'monthly_billings'
AND column_name = 'included_adhoc_ids';

-- ============================================================================
-- CRITICAL FIX: Convert TEXT to JSONB
-- ============================================================================
\echo ''
\echo 'Converting included_adhoc_ids from TEXT to JSONB...'

ALTER TABLE monthly_billings
    ALTER COLUMN included_adhoc_ids TYPE jsonb USING
    CASE
        WHEN included_adhoc_ids IS NULL THEN '[]'::jsonb
        WHEN included_adhoc_ids = '' THEN '[]'::jsonb
        WHEN included_adhoc_ids::text ~ '^\[.*\]$' THEN included_adhoc_ids::jsonb
        ELSE ('["' || included_adhoc_ids || '"]')::jsonb
    END;

-- Set default
ALTER TABLE monthly_billings
    ALTER COLUMN included_adhoc_ids SET DEFAULT '[]'::jsonb;

-- Add comment
COMMENT ON COLUMN monthly_billings.included_adhoc_ids IS 'JSON array of included adhoc billing IDs';

-- ============================================================================
-- Verify the change
-- ============================================================================
\echo ''
\echo 'Verification - New schema:'
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'monthly_billings'
AND column_name = 'included_adhoc_ids';

-- Show sample data
\echo ''
\echo 'Sample data after conversion:'
SELECT
    id,
    billing_month,
    included_adhoc_ids,
    pg_typeof(included_adhoc_ids) as data_type
FROM monthly_billings
WHERE included_adhoc_ids IS NOT NULL
LIMIT 5;

COMMIT;

\echo ''
\echo '✅ Local database schema fix completed!'
\echo 'included_adhoc_ids is now JSONB type, matching production'
