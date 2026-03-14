-- ============================================================================
-- SCHEMA VERIFICATION SCRIPT
-- ============================================================================
-- Purpose: Check schema differences between local and production
-- Run this on BOTH databases to compare
--
-- Usage:
--   Local:      psql -h localhost -p 5432 -U admin -d erp -f .ci/verify_schemas.sql
--   Production: psql -h localhost -p 5433 -U admin -d erp -f .ci/verify_schemas.sql
-- ============================================================================

\echo '════════════════════════════════════════════════════════════════════'
\echo 'SCHEMA VERIFICATION'
\echo '════════════════════════════════════════════════════════════════════'
\echo ''

-- Check monthly_billings.included_adhoc_ids
\echo '1. CRITICAL: monthly_billings.included_adhoc_ids'
\echo '   Expected: JSONB type'
\echo ''
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable,
    CASE
        WHEN data_type = 'jsonb' THEN '✅ CORRECT'
        WHEN data_type = 'text' THEN '❌ NEEDS FIX'
        ELSE '⚠️  UNEXPECTED'
    END as status
FROM information_schema.columns
WHERE table_name = 'monthly_billings'
AND column_name = 'included_adhoc_ids';

\echo ''
\echo '────────────────────────────────────────────────────────────────────'
\echo ''

-- Check if table exists
\echo '2. Table existence check:'
\echo ''
SELECT
    COUNT(*) as table_count,
    CASE
        WHEN COUNT(*) > 0 THEN '✅ monthly_billings table exists'
        ELSE '❌ monthly_billings table NOT FOUND'
    END as status
FROM information_schema.tables
WHERE table_name = 'monthly_billings';

\echo ''
\echo '────────────────────────────────────────────────────────────────────'
\echo ''

-- Count records with adhoc data
\echo '3. Data check - Records with adhoc billing data:'
\echo ''
SELECT
    COUNT(*) as total_records,
    COUNT(*) FILTER (WHERE included_adhoc_ids IS NOT NULL) as records_with_adhoc_ids,
    COUNT(*) FILTER (WHERE included_adhoc_ids IS NOT NULL AND included_adhoc_ids::text != '[]') as non_empty_adhoc
FROM monthly_billings;

\echo ''
\echo '════════════════════════════════════════════════════════════════════'
\echo 'Verification complete'
\echo '════════════════════════════════════════════════════════════════════'
\echo ''
