# Root Folder Audit - ERP Project

**Audit Date**: 2026-02-08
**Purpose**: Identify files to keep vs delete after Celery to Cloud Tasks migration

---

## ✅ KEEP - Essential Files

### Core Django Files
- `manage.py` - Django management script (REQUIRED)
- `requirements.txt` - Python dependencies (REQUIRED)
- `.env.example` - Environment variable template (REQUIRED)
- `.gitignore` - Git ignore rules (REQUIRED)
- `.gcloudignore` - GCP deployment ignore rules (REQUIRED)

### Deployment Files
- `Dockerfile` - Container definition for Cloud Run (REQUIRED)
- `cloudbuild.yaml` - GCP build configuration (REQUIRED)
- `current_service.yaml` - Cloud Run service configuration (REQUIRED)
- `deploy.sh` - Deployment automation script (USEFUL)
- `run_migrations.sh` - Migration automation script (USEFUL)

### Documentation - Migration & Setup
- `README.md` - Project documentation (REQUIRED)
- `CLOUD_TASKS_DEPLOYMENT.md` - Cloud Tasks deployment guide (REQUIRED)
- `MIGRATION_SUMMARY.md` - Migration documentation (REQUIRED)
- `MIGRATION_CHECKLIST.md` - Migration checklist (REQUIRED)
- `FRONTEND_COMPATIBILITY.md` - Frontend compatibility notes (REQUIRED)
- `FULL_SYNC_TEST_RESULTS.md` - Test results documentation (REQUIRED)

### Documentation - Integration Guides (Keep if still relevant)
- `GMAIL_SETUP_GUIDE.md` - Gmail integration setup
- `GMAIL_LEADS_SETUP.md` - Gmail Leads setup
- `GMAIL_CREDENTIALS_SETUP.md` - Gmail OAuth setup
- `BIGIN_CRUD_SETUP.md` - Bigin CRUD operations guide
- `CLOUD_RUN_SETUP.md` - Cloud Run setup guide
- `QUICKSTART.md` - Quick start guide

### Test Files (Keep for future testing)
- `test_cloud_tasks_migration.py` - Cloud Tasks endpoint tests
- `test_full_sync_all_apps.py` - Full sync integration tests
- `test_health_staging.py` - Health check tests
- `pytest.ini` - Pytest configuration

### Configuration Files
- `mypy.ini` - Type checking configuration
- `docker-compose.yml` - Local development compose file

---

## ❌ DELETE - Celery-Related Files (No Longer Needed)

### Celery Runtime Files
- `celerybeat-schedule` - Celery Beat schedule database (96 KB)
- `celerybeat-schedule-shm` - Shared memory file (32 KB)
- `celerybeat-schedule-wal` - Write-ahead log (4.1 MB)
- **Total**: ~4.2 MB

### Celery Scripts
- `start_celery.sh` - Starts Celery worker/beat
- `stop_celery.sh` - Stops Celery processes

**Reason**: All Celery functionality replaced with Cloud Tasks. These files are obsolete.

---

## ❌ DELETE - Old Backup Files

### Database Backups
- `backup_before_migration_fix.json` - Nov 27 backup (733 KB)
- `backup_before_migration_fix_20260120_131422.sql` - Empty file
- `backup_before_rename.sql` - Nov 22 backup (348 KB)
- **Total**: ~1.1 MB

**Reason**: Old backups from November/January. Should be archived externally or deleted.

---

## ❌ DELETE - Old Schema/Migration Analysis Files

### Schema Export Files (Large, historical)
- `db_schema_local.json` - Jan 27 schema (612 KB)
- `beautiful_database_schema.md` - Dec 31 schema (232 KB)
- `schema_clean_export.json` - Jan 27 export (335 KB)
- `schema_audit_reference.txt` - Jan 27 audit (146 KB)
- `schema_map.txt` - Jan 27 map (48 KB)
- `schema_map_complete.txt` - Jan 27 complete map (146 KB)
- `schema_fk_relationships.txt` - Jan 27 relationships (42 KB)
- `schema_quick_lookup.txt` - Jan 27 lookup (9 KB)
- `schema_stats.json` - Jan 27 stats (476 bytes)
- `local_schema.txt` - Dec 16 schema (121 KB)
- `production_schema.txt` - Dec 16 schema (117 KB)
- `schema_comparison.txt` - Feb 2 comparison (79 KB)
- **Total**: ~1.8 MB

### Migration Analysis Files
- `COMPLETE_MIGRATIONS_REPORT_20260120_145203.md` - Jan 20 report (485 KB)
- `migrations_analysis_20260120_145203.json` - Jan 20 analysis (136 KB)
- `extract_migrations_mac.sh` - Migration extraction script
- `extract_complete_migrations.py` - Migration extraction script
- `local_migrations.txt` - Jan 25 list (5 KB)
- `staging_migrations.txt` - Jan 25 list (5 KB)
- `staging_diff.json` - Jan 23 diff (54 KB)
- **Total**: ~685 KB

### Schema Analysis Scripts (one-time use)
- `create_audit_schema_reference.py` - Creates schema reference
- `export_schema_json.py` - Exports schema to JSON
- `parse_schema.py` - Parses schema
- `parse_comprehensive_schema.py` - Comprehensive schema parser
- `view_db_schema.py` - Views database schema
- `compare_schemas.py` - Compares schemas
- `check_columns.py` - Checks column structure
- `check_migrations.py` - Checks migration state

**Reason**: These are historical analysis files from January/December. Schema is stable now. If needed again, regenerate from database.

**Recommendation**: Archive externally if historical record is needed, otherwise DELETE.

---

## ❌ DELETE - Old Bigin Migration/Fix Scripts

### Bigin-Specific Fix Scripts
- `check_bigin_schema.sh` - Checks Bigin schema
- `check_migration_state.sh` - Checks migration state
- `fix_bigin_migration_state.sh` - Fixes Bigin migrations
- `fix_bigin_migrations_corrected.sh` - Corrected migration fixes

**Reason**: These were used to fix specific migration issues in January. No longer needed.

---

## ❌ DELETE - Bigin Field Metadata Files

### Bigin API Field Definitions
- `bigin_fields_Accounts.json` - Jan 13 (42 KB)
- `bigin_fields_Contacts.json` - Jan 13 (158 KB)
- `bigin_fields_Notes.json` - Jan 13 (17 KB)
- `bigin_fields_Pipelines.json` - Jan 13 (46 KB)
- `bigin_fields_Products.json` - Jan 13 (25 KB)
- **Total**: ~288 KB

**Reason**: These are API field definitions from January. If needed again, fetch from Bigin API.

**Alternative**: Move to `integrations/bigin/docs/` if you want to keep for reference.

---

## ❌ DELETE - Old Documentation Files (Outdated/Redundant)

### Potentially Obsolete Guides
- `GMAIL_LEADS_IMPLEMENTATION.md` - Feb 3 implementation (13 KB)
- `GMAIL_SYNC_IMPLEMENTATION.md` - Feb 3 implementation (11 KB)
- `IMPLEMENTATION_COMPLETE.md` - Feb 3 completion (8 KB)
- `RFQ_IMPLEMENTATION_SUMMARY.md` - Feb 3 RFQ summary (12 KB)
- `BIGIN_SYNC_TROUBLESHOOTING.md` - Feb 2 troubleshooting (6 KB)
- `PRODUCTION_SCHEMA_SYNC.md` - Feb 2 schema sync (5 KB)
- `SCHEMA_AUDIT_SUMMARY.md` - Jan 27 audit (18 KB)
- `SCHEMA_FILES_INDEX.md` - Jan 27 index (7 KB)
- `MONTHLY_BILLING_DATA_INTEGRITY_TESTS.md` - Feb 5 tests (11 KB)
- `TEST_RESULTS_SUMMARY.md` - Feb 5 summary (10 KB)
- `TESTING_GUIDE.md` - Feb 3 guide (14 KB)
- `QUICK_SCHEMA_REFERENCE.txt` - Jan 27 reference (7 KB)
- `SETUP_STATUS.md` - Feb 3 status (6 KB)
- **Total**: ~128 KB

**Recommendation**:
- If these document completed features that are now stable, ARCHIVE or DELETE
- If they're still actively referenced, KEEP
- Consider consolidating into a single `/docs/archive/` folder

---

## ❌ DELETE - Utility Scripts (One-Time Use)

### One-off Scripts
- `check_storage.py` - Jan 5 storage check
- `fix_permissions.py` - Jan 27 permission fix
- `populate_location_codes.py` - Jan 5 location population
- `scan_hardcoded_dropdowns.py` - Jan 5 dropdown scanner
- `project_structure_map.py` - Jan 5 structure mapper
- `update_edit_template.py` - Feb 7 template updater

**Reason**: These are utility scripts for one-time tasks. Keep only if they're reusable.

---

## ❌ DELETE - Log Files

### Application Logs
- `ravi_notes_sync.log` - Jan 10 sync log (232 KB)

**Reason**: Old log from January. Logs should not be in root folder.

---

## ❌ DELETE - Test/Debug Files

### Test Data Files
- `hardcoded_dropdowns_inventory.json` - Jan 3 test data (48 KB)
- `warehouse_data_template.csv` - Feb 2 template (2 KB)

**Recommendation**: Move to `tests/fixtures/` or DELETE if not needed.

---

## ❌ DELETE - Misc Files

- `.coverage` - Dec 24 code coverage data (98 KB)
- `.deployment-log.txt` - Jan 22 deployment log (56 bytes)
- `Dockerfile.backup` - Dec 22 backup (818 bytes)
- `credentials.json` - Feb 3 credentials (403 bytes) - **Should be in .gitignore!**
- `project_structure.md` - Jan 23 structure (125 KB)
- `QUICK_TEST_COMMANDS.sh` - Feb 3 commands (3 KB)
- `WAREHOUSE_IMPORT_GUIDE.md` - Feb 2 guide (4 KB)

**Reason**: Old files, backups, or files that should be ignored.

---

## ⚠️ REVIEW - Folders

### `.ci/` folder
- Contains CI/CD configuration
- **Action**: Review contents, keep if actively used

### `.pytest_cache/` folder
- Pytest cache data
- **Action**: Should be in .gitignore, safe to DELETE (regenerates)

### `htmlcov/` folder
- HTML coverage reports
- **Action**: Should be in .gitignore, safe to DELETE (regenerates)

### `logs/` folder
- Application logs
- **Action**: Check if still needed, likely DELETE (should be in .gitignore)

### `data/` folder
- Data files (already in .gitignore)
- **Action**: Keep if contains important data, otherwise DELETE

### `query_attachments/` folder
- Query attachments (already in .gitignore)
- **Action**: Keep structure, DELETE contents

### `venv/` folder
- Virtual environment (already in .gitignore)
- **Action**: Keep for local development

---

## 📊 Summary

### Files to DELETE Immediately (Safe)
**Total Size**: ~7.5 MB

1. **Celery files** (4.2 MB): All celerybeat-schedule files, start/stop scripts
2. **Old backups** (1.1 MB): backup_before_*.sql/json files
3. **Schema analysis** (1.8 MB): All schema_*.txt/json files from Jan/Dec
4. **Migration analysis** (685 KB): COMPLETE_MIGRATIONS_REPORT, migrations_analysis files
5. **Bigin metadata** (288 KB): bigin_fields_*.json files
6. **Log files** (232 KB): ravi_notes_sync.log
7. **Misc** (200 KB): .coverage, Dockerfile.backup, credentials.json, project_structure.md

### Files to Archive (Move to `/docs/archive/`)
**Total**: ~128 KB

- IMPLEMENTATION_COMPLETE.md
- GMAIL_SYNC_IMPLEMENTATION.md
- GMAIL_LEADS_IMPLEMENTATION.md
- RFQ_IMPLEMENTATION_SUMMARY.md
- BIGIN_SYNC_TROUBLESHOOTING.md
- SCHEMA_AUDIT_SUMMARY.md
- MONTHLY_BILLING_DATA_INTEGRITY_TESTS.md
- TEST_RESULTS_SUMMARY.md
- TESTING_GUIDE.md

### Files to Keep
- All core Django files (manage.py, requirements.txt, etc.)
- All deployment files (Dockerfile, cloudbuild.yaml, etc.)
- Current migration documentation (CLOUD_TASKS_*.md, MIGRATION_*.md)
- Active setup guides (GMAIL_SETUP_GUIDE.md, etc.)
- Test files (test_*.py, pytest.ini)
- Configuration files (mypy.ini, docker-compose.yml)

---

## 🔧 Recommended Actions

### Step 1: Delete Celery Files
```bash
rm -f celerybeat-schedule*
rm -f start_celery.sh stop_celery.sh
```

### Step 2: Delete Old Backups
```bash
rm -f backup_before_*.sql backup_before_*.json
```

### Step 3: Delete Schema Analysis Files
```bash
rm -f db_schema_local.json beautiful_database_schema.md
rm -f schema_*.txt schema_*.json
rm -f *_schema.txt
rm -f COMPLETE_MIGRATIONS_REPORT_*.md migrations_analysis_*.json
rm -f local_migrations.txt staging_migrations.txt staging_diff.json
```

### Step 4: Delete One-Time Scripts
```bash
rm -f check_bigin_schema.sh check_migration_state.sh
rm -f fix_bigin_migration*.sh extract_migrations_mac.sh
rm -f create_audit_schema_reference.py export_schema_json.py
rm -f parse_schema.py parse_comprehensive_schema.py
rm -f view_db_schema.py compare_schemas.py
rm -f check_columns.py check_migrations.py
rm -f check_storage.py fix_permissions.py
rm -f populate_location_codes.py scan_hardcoded_dropdowns.py
rm -f project_structure_map.py update_edit_template.py
```

### Step 5: Delete Bigin Metadata
```bash
rm -f bigin_fields_*.json
```

### Step 6: Delete Misc Files
```bash
rm -f .coverage .deployment-log.txt Dockerfile.backup
rm -f credentials.json project_structure.md
rm -f ravi_notes_sync.log
rm -f hardcoded_dropdowns_inventory.json warehouse_data_template.csv
rm -f QUICK_TEST_COMMANDS.sh WAREHOUSE_IMPORT_GUIDE.md
```

### Step 7: Clean Folders
```bash
rm -rf .pytest_cache/
rm -rf htmlcov/
rm -rf logs/
```

### Step 8: Archive Old Documentation (Optional)
```bash
mkdir -p docs/archive
mv IMPLEMENTATION_COMPLETE.md docs/archive/
mv GMAIL_SYNC_IMPLEMENTATION.md docs/archive/
mv GMAIL_LEADS_IMPLEMENTATION.md docs/archive/
mv RFQ_IMPLEMENTATION_SUMMARY.md docs/archive/
mv BIGIN_SYNC_TROUBLESHOOTING.md docs/archive/
mv SCHEMA_AUDIT_SUMMARY.md docs/archive/
mv SCHEMA_FILES_INDEX.md docs/archive/
mv MONTHLY_BILLING_DATA_INTEGRITY_TESTS.md docs/archive/
mv TEST_RESULTS_SUMMARY.md docs/archive/
mv TESTING_GUIDE.md docs/archive/
mv PRODUCTION_SCHEMA_SYNC.md docs/archive/
mv SETUP_STATUS.md docs/archive/
mv QUICK_SCHEMA_REFERENCE.txt docs/archive/
```

### Step 9: Update .gitignore
Add these entries to ensure clean future:
```
# Coverage reports
.coverage
htmlcov/

# Pytest cache
.pytest_cache/

# Logs
logs/
*.log

# Credentials (already there but worth verifying)
credentials.json

# Schema analysis files
schema_*.txt
schema_*.json
*_schema.txt
*_schema.json
```

---

## 📈 Expected Results

### Before Cleanup
- Root folder: ~134 files
- Total size: ~8-10 MB (excluding folders)

### After Cleanup
- Root folder: ~40-50 files (essential only)
- Total size: ~500 KB - 1 MB
- Freed space: ~7-9 MB

### Benefits
- ✅ Cleaner repository
- ✅ Faster git operations
- ✅ No confusion with obsolete files
- ✅ Clear separation of active vs archived documentation

---

**Last Updated**: 2026-02-08
