-- ============================================================================
-- ROLLBACK SCRIPT FOR PRODUCTION SCHEMA SYNC
-- ============================================================================
-- Purpose: Rollback the schema changes made by sync_prod_to_local_schema.sql
-- Use this ONLY if you need to revert the changes
-- ============================================================================

BEGIN;

-- ============================================================================
-- ROLLBACK: included_adhoc_ids TYPE CHANGE
-- ============================================================================
-- WARNING: This will convert JSONB back to TEXT
-- Any JSON data will be preserved as text representation

ALTER TABLE monthly_billings
    ALTER COLUMN included_adhoc_ids TYPE text USING included_adhoc_ids::text;

-- ============================================================================
-- ROLLBACK: NULLABLE CONSTRAINTS
-- ============================================================================
-- Remove NOT NULL constraints that were added

-- Supply module
ALTER TABLE supply_vendorwarehouse
    ALTER COLUMN warehouse_code DROP NOT NULL,
    ALTER COLUMN warehouse_name DROP NOT NULL,
    ALTER COLUMN city DROP NOT NULL,
    ALTER COLUMN state DROP NOT NULL,
    ALTER COLUMN vendor_id DROP NOT NULL;

-- Operations module - Daily Space Utilization
ALTER TABLE operations_dailyspaceutilization
    ALTER COLUMN project_id DROP NOT NULL,
    ALTER COLUMN entry_date DROP NOT NULL,
    ALTER COLUMN space_utilized DROP NOT NULL,
    ALTER COLUMN unit DROP NOT NULL,
    ALTER COLUMN inventory_value DROP NOT NULL,
    ALTER COLUMN entered_by_id DROP NOT NULL,
    ALTER COLUMN remarks DROP NOT NULL;

-- Operations module - Monthly Billings
ALTER TABLE monthly_billings
    ALTER COLUMN project_id DROP NOT NULL,
    ALTER COLUMN billing_month DROP NOT NULL,
    ALTER COLUMN status DROP NOT NULL,
    ALTER COLUMN created_by_id DROP NOT NULL,
    ALTER COLUMN created_at DROP NOT NULL;

-- Operations module - Adhoc Billing
ALTER TABLE operations_adhocbillingentry
    ALTER COLUMN project_id DROP NOT NULL,
    ALTER COLUMN event_date DROP NOT NULL,
    ALTER COLUMN status DROP NOT NULL,
    ALTER COLUMN created_by_id DROP NOT NULL,
    ALTER COLUMN total_client_amount DROP NOT NULL,
    ALTER COLUMN total_vendor_amount DROP NOT NULL,
    ALTER COLUMN billing_remarks DROP NOT NULL,
    ALTER COLUMN updated_at DROP NOT NULL;

ALTER TABLE operations_adhocbillinglineitem
    ALTER COLUMN entry_id DROP NOT NULL,
    ALTER COLUMN side DROP NOT NULL,
    ALTER COLUMN charge_type DROP NOT NULL,
    ALTER COLUMN description DROP NOT NULL,
    ALTER COLUMN quantity DROP NOT NULL,
    ALTER COLUMN rate DROP NOT NULL,
    ALTER COLUMN unit DROP NOT NULL,
    ALTER COLUMN amount DROP NOT NULL;

ALTER TABLE operations_adhocbillingattachment
    ALTER COLUMN entry_id DROP NOT NULL,
    ALTER COLUMN file DROP NOT NULL,
    ALTER COLUMN filename DROP NOT NULL,
    ALTER COLUMN attachment_type DROP NOT NULL,
    ALTER COLUMN uploaded_by_id DROP NOT NULL;

-- Dropdown master data tables
ALTER TABLE dropdown_adhoc_billing_statuses
    ALTER COLUMN code DROP NOT NULL,
    ALTER COLUMN label DROP NOT NULL,
    ALTER COLUMN display_order DROP NOT NULL,
    ALTER COLUMN is_active DROP NOT NULL;

ALTER TABLE master_adhoc_charge_types
    ALTER COLUMN code DROP NOT NULL,
    ALTER COLUMN label DROP NOT NULL,
    ALTER COLUMN display_order DROP NOT NULL,
    ALTER COLUMN is_active DROP NOT NULL;

-- ============================================================================
-- NOTE: Indexes are kept as they improve performance
-- ============================================================================
-- If you need to drop the indexes, uncomment the following:
--
-- DROP INDEX IF EXISTS monthly_billings_project_id_idx;
-- DROP INDEX IF EXISTS monthly_billings_status_idx;
-- DROP INDEX IF EXISTS monthly_billings_created_by_id_idx;
-- DROP INDEX IF EXISTS monthly_billings_billing_month_idx;
-- DROP INDEX IF EXISTS operations_adhocbillingentry_project_event_idx;
-- DROP INDEX IF EXISTS operations_adhocbillingentry_service_month_status_idx;
-- DROP INDEX IF EXISTS operations_dailyspaceutilization_project_date_idx;

COMMIT;

RAISE NOTICE '✅ Schema sync rollback completed';
