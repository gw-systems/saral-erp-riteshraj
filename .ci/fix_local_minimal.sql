-- ============================================================================
-- MINIMAL LOCAL DATABASE FIX - Bug #1 Only
-- ============================================================================
-- Purpose: Fix ONLY the critical included_adhoc_ids type mismatch
-- Target: LOCAL database (localhost:5432)
--
-- Usage: psql -h localhost -p 5432 -U admin -d erp -f .ci/fix_local_minimal.sql
-- ============================================================================

\echo '════════════════════════════════════════════════════════════════════'
\echo 'Bug #1 Fix: Convert included_adhoc_ids from TEXT to JSONB'
\echo '════════════════════════════════════════════════════════════════════'
\echo ''

-- Show current state
\echo 'BEFORE:'
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'monthly_billings'
AND column_name = 'included_adhoc_ids';

\echo ''
\echo 'Applying fix...'
\echo ''

BEGIN;

-- Convert TEXT to JSONB
ALTER TABLE monthly_billings
    ALTER COLUMN included_adhoc_ids TYPE jsonb USING
    CASE
        WHEN included_adhoc_ids IS NULL THEN '[]'::jsonb
        WHEN included_adhoc_ids = '' THEN '[]'::jsonb
        WHEN included_adhoc_ids::text ~ '^\[.*\]$' THEN included_adhoc_ids::jsonb
        ELSE '[]'::jsonb
    END;

-- Set default to empty array
ALTER TABLE monthly_billings
    ALTER COLUMN included_adhoc_ids SET DEFAULT '[]'::jsonb;

COMMIT;

\echo ''
\echo 'AFTER:'
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'monthly_billings'
AND column_name = 'included_adhoc_ids';

\echo ''
\echo '✅ Fix completed!'
\echo 'Local database now matches production schema for included_adhoc_ids'
\echo ''
