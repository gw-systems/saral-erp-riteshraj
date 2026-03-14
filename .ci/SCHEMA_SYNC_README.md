# Production Database Schema Sync

## Overview

This directory contains SQL scripts to sync the production database schema with the local development database schema.

## Critical Issues Fixed

### 1. Bug #1: `monthly_billings.included_adhoc_ids` Type Mismatch
- **Issue**: Production has `TEXT`, Django model expects `JSONB`
- **Impact**: JSON serialization errors when saving monthly billing records
- **Fix**: Converts column from TEXT to JSONB

### 2. Missing NOT NULL Constraints
- **Issue**: Production missing NOT NULL constraints present in local
- **Impact**: Data integrity, potential NULL values where they shouldn't exist
- **Fix**: Adds NOT NULL constraints to critical columns

### 3. Missing Indexes
- **Issue**: Production missing performance indexes
- **Impact**: Slower query performance
- **Fix**: Adds indexes on foreign keys and frequently queried columns

## Files

1. **`sync_prod_to_local_schema.sql`** - Main sync script (applies changes)
2. **`rollback_schema_sync.sql`** - Rollback script (reverts changes)
3. **`schema_comparator.py`** - Python tool to compare schemas

## Pre-Execution Checklist

- [ ] **BACKUP PRODUCTION DATABASE** - This is critical!
- [ ] Review the sync script carefully
- [ ] Ensure Cloud SQL proxy is running on port 5433
- [ ] Verify no active transactions or users on production
- [ ] Have the rollback script ready
- [ ] Test on staging environment first (if available)

## Execution Steps

### Step 1: Backup Production Database

```bash
# Using gcloud SQL export
gcloud sql export sql saral-erp-db gs://your-backup-bucket/backup-$(date +%Y%m%d-%H%M%S).sql \
    --database=erp
```

### Step 2: Start Cloud SQL Proxy

```bash
cloud-sql-proxy saral-erp-479508:asia-south1:saral-erp-db --port=5433
```

Keep this running in a separate terminal.

### Step 3: Review the Sync Script

```bash
cat .ci/sync_prod_to_local_schema.sql
```

Review each ALTER statement carefully.

### Step 4: Execute the Sync Script

```bash
# Dry run first (wrapped in transaction that rolls back)
psql -h localhost -p 5433 -U admin -d erp << 'EOF'
BEGIN;
\i .ci/sync_prod_to_local_schema.sql
ROLLBACK;  -- This prevents actual changes
EOF

# If dry run looks good, execute for real
psql -h localhost -p 5433 -U admin -d erp -f .ci/sync_prod_to_local_schema.sql
```

### Step 5: Verify Changes

```bash
# Connect to production
psql -h localhost -p 5433 -U admin -d erp

# Run verification queries
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'monthly_billings'
AND column_name = 'included_adhoc_ids';

# Should return: jsonb | NO

# Check indexes
SELECT indexname FROM pg_indexes WHERE tablename = 'monthly_billings';
```

### Step 6: Test Application

1. Deploy latest code to production
2. Test monthly billing creation with adhoc entries
3. Test daily space utilization entry (Bug #2)
4. Monitor logs for any errors

## Rollback Procedure

If something goes wrong:

```bash
psql -h localhost -p 5433 -U admin -d erp -f .ci/rollback_schema_sync.sql
```

Or restore from backup:

```bash
gcloud sql import sql saral-erp-db gs://your-backup-bucket/backup-TIMESTAMP.sql \
    --database=erp
```

## Schema Comparison Tool

To compare schemas anytime:

```bash
# Start Cloud SQL proxy first
cloud-sql-proxy saral-erp-479508:asia-south1:saral-erp-db --port=5433

# Run comparison
python .ci/schema_comparator.py --local --production --output=schema_comparison.txt

# Generate SQL fixes
python .ci/schema_comparator.py --local --production --generate-sql
```

## Bug #2 Status

**Bug #2 (Unit Type Conversion)** is already fixed in code:
- Fixed in commit `e8b63f2`
- Added unit mapping logic in `operations/views.py`
- Functions: `daily_entry_single`, `daily_entry_edit`, `daily_entry_bulk_import`
- No database schema changes required for Bug #2

## Post-Sync Actions

1. **Update Local Database**: Apply the same schema changes to local to stay in sync
2. **Update Staging**: If you have a staging environment, sync it too
3. **Monitor Production**: Watch logs for 24 hours after deployment
4. **Update Documentation**: Document any schema changes in your migration history

## Common Issues

### Issue: "relation does not exist"
- Check if table names are correct
- Verify you're connected to the right database

### Issue: "cannot alter type of a column used by a view"
- Need to drop and recreate dependent views
- Contact DBA before proceeding

### Issue: "column contains null values"
- Need to clean data first before adding NOT NULL constraint
- Use UPDATE statements to fill NULL values

### Issue: Cloud SQL Proxy connection timeout
- Check network connectivity
- Verify Cloud SQL instance is running
- Check if your IP is whitelisted

## Support

For issues:
1. Check the schema comparison output
2. Review PostgreSQL error messages
3. Consult with DBA if unsure
4. Restore from backup if critical

## Notes

- The sync script is wrapped in a transaction (BEGIN/COMMIT)
- If any statement fails, entire transaction rolls back
- Indexes are safe to add (non-blocking in PostgreSQL with CONCURRENTLY)
- Type conversions may take time on large tables
- The script includes verification queries to confirm changes

## Related Files

- `operations/models.py` - Django models defining the schema
- `operations/migrations/` - Django migration files
- Git commit `fa54135` - Original Bug #1 fix (JSONField change)
- Git commit `e8b63f2` - Bug #2 fix (unit mapping)
