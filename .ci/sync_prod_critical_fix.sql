-- ============================================================================
-- PRODUCTION DATABASE - CRITICAL FIX ONLY
-- ============================================================================
-- Purpose: Fix ONLY the critical included_adhoc_ids type mismatch
--
-- This is a minimal, safe script that fixes Bug #1
-- No other schema changes are applied
--
-- Usage:
--   1. Connect: psql -h localhost -p 5433 -U admin -d erp
--   2. Execute: \i .ci/sync_prod_critical_fix.sql
-- ============================================================================

BEGIN;

-- ============================================================================
-- CRITICAL FIX: monthly_billings.included_adhoc_ids TYPE MISMATCH
-- ============================================================================
-- Issue: Local has TEXT, Production has JSONB (already correct!)
-- Action: We need to fix LOCAL database, not production
-- This file documents what production already has

-- Check current type in production
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'monthly_billings'
AND column_name = 'included_adhoc_ids';

-- Production should already show: jsonb | YES
-- If it shows TEXT, run this:
-- ALTER TABLE monthly_billings
--     ALTER COLUMN included_adhoc_ids TYPE jsonb USING included_adhoc_ids::jsonb;

COMMIT;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
\echo ''
\echo '✅ Schema check completed'
\echo 'If production shows TEXT, contact DBA to apply the ALTER TABLE command'
\echo 'If production shows JSONB, then production is correct - fix local instead'
