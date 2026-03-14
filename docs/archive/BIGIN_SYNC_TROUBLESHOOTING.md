# Bigin Sync Error Troubleshooting Guide

## Problem
Bigin full sync was failing in staging with "Errors: 1" for all modules (Contacts, Pipelines, Accounts, Products, Notes) but no error details were shown.

## Root Cause Analysis
The sync task was catching exceptions and storing them in `module_results[module]['error_message']`, but:
1. The UI wasn't displaying the error messages from module results
2. No traceback information was being captured
3. No early validation of OAuth token before starting sync

## Solutions Implemented

### 1. Enhanced Error Logging in Sync Task
**File**: `integrations/bigin/tasks.py`

#### Early OAuth Token Validation
Added validation at the start of sync to catch token issues immediately:
```python
# Early check for OAuth token
try:
    from .token_manager import get_valid_token
    token = get_valid_token()
    logger.info("[Bigin Sync] OAuth token validated successfully")
except Exception as e:
    # Store detailed error with traceback
    error_msg = f"OAuth Token Error: {type(e).__name__}: {str(e)}"
    sync_log.status = 'failed'
    sync_log.error_message = error_msg
    sync_log.error_details = {'traceback': traceback.format_exc()}
    return
```

#### Enhanced Module Error Handling
Added traceback capture for each module failure:
```python
except Exception as e:
    import traceback
    error_traceback = traceback.format_exc()
    module_results[module] = {
        'synced': 0,
        'created': 0,
        'updated': 0,
        'errors': 1,
        'error_message': f"{type(e).__name__}: {str(e)}",
        'traceback': error_traceback[:500]  # First 500 chars
    }
```

### 2. Improved UI Error Display
**File**: `templates/dashboards/admin/sync_audit.html`

#### Module-Level Error Display
- Failed modules now have red background/border
- Error messages displayed prominently
- Expandable traceback details for debugging

#### Overall Sync Error Display
- Main error message shown at bottom of sync details
- Expandable full traceback from `error_details`

## Common Errors and Solutions

### Error: "No token found in database"
**Cause**: OAuth token not configured in staging environment

**Solution**:
1. Go to Bigin OAuth setup page in staging
2. Complete OAuth flow to store access/refresh tokens
3. Or manually insert BiginAuthToken record in database

### Error: "Token refresh failed"
**Cause**: Refresh token expired or invalid

**Solution**:
1. Re-run OAuth flow to get new refresh token
2. Check ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET in settings
3. Verify OAuth app is active in Zoho Developer Console

### Error: "Module {name} not found" (404)
**Cause**: Invalid module name or API endpoint changed

**Solution**:
- Check module names in MODULES_TO_SYNC match Zoho Bigin API
- Verify API base URL is correct for your Zoho region

### Error: Rate limit exceeded (429)
**Cause**: Too many API requests

**Solution**:
- The sync has built-in retry with exponential backoff
- Check if multiple syncs are running simultaneously
- Reduce DEFAULT_PER_PAGE if needed

## How to Use the Enhanced Error Logging

### 1. Check Sync Audit Page
Navigate to: `/bigin/sync-audit/`

### 2. View Sync Details
Click "Details" on any failed/partial sync

### 3. Check Module Results
Each module shows:
- Synced/Created/Updated counts
- Error count
- **Error message** (if errors > 0)
- **Traceback** (expandable, if available)

### 4. Check Overall Error
If entire sync failed:
- Error message shown at bottom
- **Full traceback** (expandable)

## Testing the Fix in Staging

After deployment:

1. **Trigger a sync**:
   ```bash
   # Via API
   POST /bigin/api/trigger-sync/
   {
     "sync_type": "bigin_full"
   }
   ```

2. **Check the sync audit page**:
   - Navigate to sync audit
   - Find the latest sync
   - Click "Details"
   - You should now see **detailed error messages** instead of just "Errors: 1"

3. **Look for common errors**:
   - OAuth token issues will appear immediately
   - Module-specific errors will show which exact module failed and why
   - Tracebacks help identify the exact line of code

## Next Steps

If errors persist after seeing the detailed messages:

1. **OAuth Token Issues**: Re-run OAuth setup
2. **API Errors**: Check Zoho API status and credentials
3. **Code Errors**: Check traceback and fix the issue in the code
4. **Data Issues**: Validate data format from Bigin API

## Log Files

Server logs also contain detailed information:
```bash
# Check application logs
tail -f /var/log/your-app/django.log | grep "Bigin Sync"
```

Look for:
- `[Bigin Sync]` prefixed messages
- `logger.exception()` outputs with full tracebacks
- OAuth token refresh attempts

## Migration Reminder

The Bigin migration `0006_remove_biginrecord_idx_incremental_sync_and_more.py` was added and committed. Make sure it's applied in staging:

```bash
python manage.py migrate bigin
```

## Update: Field Length Issue Fixed (2026-02-02)

### Error in Production
```
DataError: value too long for type character varying(100)
```

### Root Cause
Migration `0002_add_missing_fields.py` created several fields with max_length too small:
- `first_name`: 100 chars (should be 255)
- `last_name`: 100 chars (should be 255)
- `mobile`: 50 chars (should be 255)
- `area_requirement`: 50 chars (should be 255)
- `status`: 50 chars (should be 500)

When Bigin API returned contact records with names longer than 100 characters, the sync failed.

### Solution
Created migration `0007_increase_field_lengths.py` to increase all field sizes to match the model definition.

### Apply in Production
```bash
python manage.py migrate bigin
```

This will increase the VARCHAR field sizes in PostgreSQL without data loss.

### Prevention
The enhanced error logging now shows:
1. Exact error type: `DataError`
2. Exact error message: "value too long for type character varying(100)"
3. Full traceback with line numbers

This makes it much easier to identify and fix similar issues in the future.
