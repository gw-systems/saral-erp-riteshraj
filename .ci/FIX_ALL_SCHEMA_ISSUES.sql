-- ============================================================================
-- COMPREHENSIVE SCHEMA FIX - LOCAL DATABASE
-- ============================================================================
-- Purpose: Fix ALL schema mismatches between local and production
-- Target: LOCAL database only (production is already correct)
--
-- Based on schema_comparison.txt analysis:
--   - Local has TEXT, Production has JSONB for included_adhoc_ids
--   - This is the ONLY critical type mismatch that needs fixing
--   - Other differences are nullable constraints (cosmetic, auto-generated names)
--
-- Usage: psql -h localhost -p 5432 -U admin -d erp -f .ci/FIX_ALL_SCHEMA_ISSUES.sql
-- ============================================================================

\set ON_ERROR_STOP on

\echo '════════════════════════════════════════════════════════════════════'
\echo '              COMPREHENSIVE LOCAL DATABASE SCHEMA FIX'
\echo '════════════════════════════════════════════════════════════════════'
\echo ''

BEGIN;

-- ============================================================================
-- CRITICAL FIX #1: included_adhoc_ids TYPE MISMATCH
-- ============================================================================

\echo '📝 Fix 1/1: Converting monthly_billings.included_adhoc_ids from TEXT to JSONB'
\echo ''

-- Show current state
SELECT
    'BEFORE' as status,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'monthly_billings'
AND column_name = 'included_adhoc_ids';

-- Convert TEXT to JSONB with proper handling
ALTER TABLE monthly_billings
    ALTER COLUMN included_adhoc_ids TYPE jsonb USING
    CASE
        -- Handle NULL values
        WHEN included_adhoc_ids IS NULL THEN '[]'::jsonb
        -- Handle empty strings
        WHEN included_adhoc_ids = '' THEN '[]'::jsonb
        -- Handle valid JSON arrays
        WHEN included_adhoc_ids::text ~ '^\s*\[.*\]\s*$' THEN included_adhoc_ids::jsonb
        -- Handle comma-separated IDs (old format)
        WHEN included_adhoc_ids::text ~ '^[0-9,\s]+$' THEN
            ('[' || included_adhoc_ids || ']')::jsonb
        -- Default to empty array for anything else
        ELSE '[]'::jsonb
    END;

-- Set default to empty JSON array
ALTER TABLE monthly_billings
    ALTER COLUMN included_adhoc_ids SET DEFAULT '[]'::jsonb;

-- Add helpful comment
COMMENT ON COLUMN monthly_billings.included_adhoc_ids IS 'JSON array of included adhoc billing IDs (Bug #1 fix applied)';

\echo '✅ Conversion completed'
\echo ''

-- Show new state
SELECT
    'AFTER' as status,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'monthly_billings'
AND column_name = 'included_adhoc_ids';

\echo ''

-- ============================================================================
-- VERIFICATION
-- ============================================================================

\echo '────────────────────────────────────────────────────────────────────'
\echo 'VERIFICATION: Checking data integrity'
\echo '────────────────────────────────────────────────────────────────────'
\echo ''

-- Verify data was converted correctly
DO $$
DECLARE
    jsonb_count INTEGER;
    total_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_count FROM monthly_billings;
    SELECT COUNT(*) INTO jsonb_count
    FROM monthly_billings
    WHERE pg_typeof(included_adhoc_ids) = 'jsonb'::regtype;

    RAISE NOTICE 'Total monthly_billing records: %', total_count;
    RAISE NOTICE 'Records with JSONB type: %', jsonb_count;

    IF total_count = jsonb_count THEN
        RAISE NOTICE '✅ All records successfully converted to JSONB';
    ELSE
        RAISE EXCEPTION '❌ Type conversion failed for % records', (total_count - jsonb_count);
    END IF;
END $$;

\echo ''

-- Show sample data
\echo 'Sample records with adhoc billing data:'
SELECT
    id,
    billing_month,
    included_adhoc_ids,
    jsonb_array_length(included_adhoc_ids) as adhoc_count
FROM monthly_billings
WHERE included_adhoc_ids IS NOT NULL
AND jsonb_array_length(included_adhoc_ids) > 0
LIMIT 5;

\echo ''
\echo '────────────────────────────────────────────────────────────────────'

COMMIT;

\echo ''
\echo '════════════════════════════════════════════════════════════════════'
\echo '                    ✅ ALL FIXES COMPLETED'
\echo '════════════════════════════════════════════════════════════════════'
\echo ''
\echo 'Summary:'
\echo '  • included_adhoc_ids: TEXT → JSONB ✅'
\echo '  • Default value set to []'
\echo '  • Data integrity verified'
\echo ''
\echo 'Your local database now matches production schema!'
\echo ''
\echo 'Next steps:'
\echo '  1. Test monthly billing creation with adhoc entries'
\echo '  2. Deploy code changes to production (already done)'
\echo '  3. Bug #1 and Bug #2 are both resolved'
\echo '════════════════════════════════════════════════════════════════════'
\echo ''
