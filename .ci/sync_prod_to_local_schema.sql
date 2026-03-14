-- ============================================================================
-- PRODUCTION DATABASE SCHEMA SYNC SCRIPT
-- ============================================================================
-- Purpose: Sync production database schema to match local database structure
--
-- IMPORTANT: Review this script carefully before executing!
-- Backup your production database before running this script.
--
-- Usage:
--   1. Connect to Cloud SQL proxy: cloud-sql-proxy saral-erp-479508:asia-south1:saral-erp-db --port=5433
--   2. Execute: psql -h localhost -p 5433 -U admin -d erp -f .ci/sync_prod_to_local_schema.sql
-- ============================================================================

BEGIN;

-- ============================================================================
-- CRITICAL FIX: monthly_billings.included_adhoc_ids TYPE MISMATCH
-- ============================================================================
-- Issue: Production has TEXT, but Django model expects JSONB
-- This is causing JSON serialization errors when saving monthly billing records

ALTER TABLE monthly_billings
    ALTER COLUMN included_adhoc_ids TYPE jsonb USING included_adhoc_ids::jsonb;

COMMENT ON COLUMN monthly_billings.included_adhoc_ids IS 'JSON array of included adhoc billing IDs';

-- ============================================================================
-- NULLABLE CONSTRAINTS - Add NOT NULL constraints to match local
-- ============================================================================

-- Note: These are safe to add because the columns should never be NULL anyway
-- If any of these fail, it means there's existing NULL data that needs to be cleaned first

-- Supply module
ALTER TABLE supply_vendorwarehouse
    ALTER COLUMN warehouse_code SET NOT NULL,
    ALTER COLUMN warehouse_name SET NOT NULL,
    ALTER COLUMN city SET NOT NULL,
    ALTER COLUMN state SET NOT NULL,
    ALTER COLUMN vendor_id SET NOT NULL;

-- Operations module - Daily Space Utilization
ALTER TABLE operations_dailyspaceutilization
    ALTER COLUMN project_id SET NOT NULL,
    ALTER COLUMN entry_date SET NOT NULL,
    ALTER COLUMN space_utilized SET NOT NULL,
    ALTER COLUMN unit SET NOT NULL,
    ALTER COLUMN inventory_value SET NOT NULL,
    ALTER COLUMN entered_by_id SET NOT NULL,
    ALTER COLUMN remarks SET NOT NULL;

-- Operations module - Monthly Billings (selected critical fields)
ALTER TABLE monthly_billings
    ALTER COLUMN project_id SET NOT NULL,
    ALTER COLUMN billing_month SET NOT NULL,
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN created_by_id SET NOT NULL,
    ALTER COLUMN created_at SET NOT NULL;

-- Operations module - Adhoc Billing
ALTER TABLE operations_adhocbillingentry
    ALTER COLUMN project_id SET NOT NULL,
    ALTER COLUMN event_date SET NOT NULL,
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN created_by_id SET NOT NULL,
    ALTER COLUMN total_client_amount SET NOT NULL,
    ALTER COLUMN total_vendor_amount SET NOT NULL,
    ALTER COLUMN billing_remarks SET NOT NULL,
    ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE operations_adhocbillinglineitem
    ALTER COLUMN entry_id SET NOT NULL,
    ALTER COLUMN side SET NOT NULL,
    ALTER COLUMN charge_type SET NOT NULL,
    ALTER COLUMN description SET NOT NULL,
    ALTER COLUMN quantity SET NOT NULL,
    ALTER COLUMN rate SET NOT NULL,
    ALTER COLUMN unit SET NOT NULL,
    ALTER COLUMN amount SET NOT NULL;

ALTER TABLE operations_adhocbillingattachment
    ALTER COLUMN entry_id SET NOT NULL,
    ALTER COLUMN file SET NOT NULL,
    ALTER COLUMN filename SET NOT NULL,
    ALTER COLUMN attachment_type SET NOT NULL,
    ALTER COLUMN uploaded_by_id SET NOT NULL;

-- Dropdown master data tables
ALTER TABLE dropdown_adhoc_billing_statuses
    ALTER COLUMN code SET NOT NULL,
    ALTER COLUMN label SET NOT NULL,
    ALTER COLUMN display_order SET NOT NULL,
    ALTER COLUMN is_active SET NOT NULL;

ALTER TABLE master_adhoc_charge_types
    ALTER COLUMN code SET NOT NULL,
    ALTER COLUMN label SET NOT NULL,
    ALTER COLUMN display_order SET NOT NULL,
    ALTER COLUMN is_active SET NOT NULL;

-- ============================================================================
-- ADD MISSING INDEXES FOR PERFORMANCE
-- ============================================================================

-- Monthly Billings - Foreign key indexes (if not exists)
CREATE INDEX IF NOT EXISTS monthly_billings_project_id_idx ON monthly_billings(project_id);
CREATE INDEX IF NOT EXISTS monthly_billings_status_idx ON monthly_billings(status);
CREATE INDEX IF NOT EXISTS monthly_billings_created_by_id_idx ON monthly_billings(created_by_id);
CREATE INDEX IF NOT EXISTS monthly_billings_billing_month_idx ON monthly_billings(billing_month);

-- Adhoc Billing - Composite indexes
CREATE INDEX IF NOT EXISTS operations_adhocbillingentry_project_event_idx
    ON operations_adhocbillingentry(project_id, event_date);
CREATE INDEX IF NOT EXISTS operations_adhocbillingentry_service_month_status_idx
    ON operations_adhocbillingentry(service_month, status);

-- Daily Space Utilization
CREATE INDEX IF NOT EXISTS operations_dailyspaceutilization_project_date_idx
    ON operations_dailyspaceutilization(project_id, entry_date);

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Verify included_adhoc_ids type change
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'monthly_billings'
        AND column_name = 'included_adhoc_ids'
        AND data_type = 'jsonb'
    ) THEN
        RAISE EXCEPTION 'CRITICAL: included_adhoc_ids type change failed!';
    END IF;

    RAISE NOTICE '✅ included_adhoc_ids successfully changed to JSONB';
END $$;

-- Count records that might need data migration
SELECT
    COUNT(*) as records_with_adhoc_ids,
    COUNT(*) FILTER (WHERE included_adhoc_ids IS NOT NULL AND included_adhoc_ids::text != '[]') as non_empty_adhoc
FROM monthly_billings;

COMMIT;

-- ============================================================================
-- POST-EXECUTION VERIFICATION
-- ============================================================================
-- Run these queries after the script completes to verify success:
--
-- 1. Check included_adhoc_ids type:
--    SELECT column_name, data_type FROM information_schema.columns
--    WHERE table_name = 'monthly_billings' AND column_name = 'included_adhoc_ids';
--
-- 2. Check NOT NULL constraints:
--    SELECT column_name, is_nullable FROM information_schema.columns
--    WHERE table_name = 'monthly_billings' AND column_name IN
--    ('project_id', 'billing_month', 'status', 'created_by_id');
--
-- 3. Check indexes:
--    SELECT indexname FROM pg_indexes WHERE tablename = 'monthly_billings';
-- ============================================================================
