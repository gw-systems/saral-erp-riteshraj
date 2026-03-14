# Production Schema Sync - Quick Guide

## Status Summary

### Bug #1: Monthly Billing JSON Error ✅ Code Fixed, ❌ Schema NOT Synced
- **Root Cause**: `monthly_billings.included_adhoc_ids` is TEXT in local but JSONB in production
- **Code Status**: Fixed in commit `fa54135` (model changed to JSONField)
- **Local DB**: TEXT (needs fix)
- **Production DB**: JSONB (already correct)
- **Action Required**: Fix LOCAL database to match PRODUCTION

### Bug #2: Unit Type Defaulting to Square Feet ✅ FIXED
- **Root Cause**: Code wasn't capturing unit field from form
- **Status**: Fixed in commit `e8b63f2`
- **No database changes required**

## Quick Commands

### Option 1: Simple Fix Script (Recommended)

```bash
# This fixes LOCAL database to match production
./.ci/fix_schema_mismatch.sh
```

This script:
- Checks schema in both local and production
- Fixes LOCAL database (production is already correct)
- Verifies the fix

### Option 2: Manual SQL Execution (LOCAL only)

```bash
# Connect to LOCAL database
psql -h localhost -p 5432 -U admin -d erp

# Apply the critical fix to LOCAL
\i .ci/fix_local_schema.sql
```

### Option 3: Compare Schemas First

```bash
# 1. Start Cloud SQL proxy
cloud-sql-proxy saral-erp-479508:asia-south1:saral-erp-db --port=5433

# 2. Run comparison
python .ci/schema_comparator.py --local --production --output=schema_comparison.txt

# 3. Review the output
cat schema_comparison.txt
```

## Files Created

### ⭐ Recommended (Simple Fix)
1. **`.ci/fix_schema_mismatch.sh`** - Simple automated fix for LOCAL database
2. **`.ci/fix_local_schema.sql`** - SQL to fix LOCAL database schema

### Advanced (Full Sync - Not Needed)
3. **`.ci/sync_prod_to_local_schema.sql`** - Full sync script (has issues with table names)
4. **`.ci/rollback_schema_sync.sql`** - Rollback script
5. **`.ci/apply_schema_sync.sh`** - Automated bash script
6. **`.ci/SCHEMA_SYNC_README.md`** - Detailed documentation

### Tools
7. **`.ci/schema_comparator.py`** - Schema comparison tool

## Critical Changes Applied by Sync Script

1. **Type Conversion** (CRITICAL)
   ```sql
   ALTER TABLE monthly_billings
       ALTER COLUMN included_adhoc_ids TYPE jsonb USING included_adhoc_ids::jsonb;
   ```

2. **NOT NULL Constraints** (126 columns across multiple tables)
   - Supply tables: vendor warehouse fields
   - Operations tables: daily entries, monthly billing, adhoc billing
   - Dropdown master data tables

3. **Performance Indexes**
   - Foreign key indexes on monthly_billings
   - Composite indexes on adhoc billing
   - Date-based indexes on daily entries

## What's Already Fixed

### Bug #2 Code Changes (commit `e8b63f2`)
- File: `operations/views.py`
- Functions modified:
  - `daily_entry_single` (lines 301-334)
  - `daily_entry_edit` (lines 515-531)
  - `daily_entry_bulk_import` (lines 430-462)
- Change: Added unit mapping from display labels to StorageUnit codes
  ```python
  unit_mapping = {
      'Sq. Ft.': 'sqft',
      'Pallet': 'pallet',
      'Unit': 'unit',
      'Order': 'order',
      'Lumpsum': 'lumpsum'
  }
  ```

### Bug #1 Code Changes (commit `fa54135`)
- File: `operations/models.py` (line 1042)
- Change: Changed from TextField to JSONField
  ```python
  included_adhoc_ids = models.JSONField(
      blank=True,
      default=list,
      help_text='JSON array of included adhoc billing IDs'
  )
  ```

## Verification After Sync

```sql
-- 1. Check column type
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'monthly_billings' AND column_name = 'included_adhoc_ids';
-- Expected: jsonb | NO

-- 2. Check indexes
SELECT indexname FROM pg_indexes WHERE tablename = 'monthly_billings';
-- Should see: monthly_billings_project_id_idx, etc.

-- 3. Test the fix
-- Create a monthly billing with adhoc entries and verify it saves correctly
```

## Rollback

If anything goes wrong:

```bash
psql -h localhost -p 5433 -U admin -d erp -f .ci/rollback_schema_sync.sql
```

## Summary

- **Bug #1**: PRODUCTION schema is already correct (JSONB), LOCAL needs to be fixed
- **Bug #2**: Code is fixed, no schema changes needed
- **Action**: Run `.ci/fix_schema_mismatch.sh` to fix LOCAL database
- **Production**: No changes needed - already correct
- **Risk**: Very low - Only affects local development database
- **Time**: Less than 1 minute

## Support

Issues? Check:
1. Cloud SQL proxy is running
2. Database credentials are correct
3. No active transactions blocking the ALTER statements
4. Review the error messages carefully
5. Restore from backup if needed
