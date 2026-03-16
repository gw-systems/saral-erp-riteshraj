# Apollo Integration Handoff Note

## What was added

Apollo is now integrated into the ERP with:

- Apollo database tables
- Apollo sync worker and service
- Apollo dashboard in the ERP
- Apollo visibility in the admin integrations dashboard
- Hourly scheduled historical sync registration
- CSV import command for historical backfill

## Apollo tables

The Apollo app creates these tables:

- `apollo_apollocampaign`
- `apollo_apollomessage`
- `apollo_apollosyncstate`

The relevant migrations are:

- `apollo/0001_initial.py`
- `apollo/0002_apollosyncstate.py`
- `apollo/0003_expand_linkedin_url.py`

There is also a shared scheduler data migration:

- `integrations/0011_add_apollo_hourly_sync_job.py`

That migration adds an enabled scheduled job for Apollo historical sync.

## Data sources

There are now two supported Apollo data sources:

1. Direct Apollo API sync into the database
2. CSV import into the same database tables

The CSV import is intended for historical backfill.
The API sync is intended for live and ongoing updates.

## Historical CSV already available

The historical CSV currently available is:

- `Apollo Data 28-01-2026 to oldest.csv`

This file contains Apollo data from:

- `January 28, 2026`
- backward to the oldest available historical records

This means the CSV can be used as the historical base load.

The importer was validated in dry-run mode on the real file and the result was:

- `202,027` rows read
- `0` rows skipped
- `6` duplicate rows in the CSV
- `79` campaigns created
- `202,021` unique messages created

## CSV import command

The CSV importer is:

- `integrations/apollo/management/commands/import_apollo_csv.py`

Recommended command:

```powershell
$env:DEBUG='False'
$env:PYTHONIOENCODING='utf-8'
venv\Scripts\python.exe -u manage.py import_apollo_csv "Apollo Data 28-01-2026 to oldest.csv" --replace-existing --batch-size 5000
```

Notes:

- `--replace-existing` clears existing Apollo campaign/message data before import
- `--batch-size 5000` is a safe large-file setting
- the command is idempotent on `Message ID`
- the CSV does not contain Apollo campaign IDs, so stable synthetic campaign IDs are generated from campaign name
- the importer does not change `ApolloSyncState`

## API sync logic

Apollo API syncing is modeled after the original Apps Script logic.

There are two sync modes:

### 1. Full sync

This is the checkpointed historical crawler.

It works like this:

- starts from the newest configured month
- fetches campaigns for that month
- fetches messages page by page for each campaign
- writes data directly into the Apollo tables
- stores progress after each page
- stops when it reaches the configured Apollo call budget
- resumes from the saved checkpoint on the next run

The checkpoint fields are stored in `apollo_apollosyncstate` and correspond to the original Apps Script properties:

- `c_year`
- `c_month`
- `c_camp_idx`
- `c_page`
- `is_complete`

Month indexing is intentionally zero-based to match the Apps Script:

- `0 = January`
- `1 = February`
- `2 = March`

### 2. Incremental sync

This is the recent-data sync.

It is meant for:

- pulling newly sent or recently updated Apollo messages
- ongoing sync after historical data is already present

It does not use the historical checkpoint row.

## API limit logic

Apollo is treated as having an hourly request limit.

The project is configured with:

- `APOLLO_CALL_LIMIT = 350`

This is intentionally lower than the assumed Apollo hourly ceiling of about `400` calls, to leave a safety buffer.

Behavior:

- each full-sync worker run can use up to `350` Apollo API calls
- when that limit is reached, the run ends with status `partial`
- this is expected behavior, not a failure
- the current checkpoint is saved before exit
- the next scheduled run resumes from that checkpoint

So for Apollo, `partial` usually means:

- sync is healthy
- checkpoint was saved
- more work remains for the next hourly run

## Hourly scheduling logic

Apollo historical sync is registered as an hourly scheduled job:

- name: `Apollo Historical Sync`
- endpoint: `/integrations/apollo/workers/sync/`
- cron: `0 * * * *`

Important:

- Apollo does not run itself automatically
- the shared ERP scheduler must already be calling `/integrations/scheduled-jobs/tick/`
- the Apollo hourly job only fires when that master tick is active

## Data behavior

All Apollo message statuses are retained.

This is intentional because the Apollo data may be used later for:

- CRM analysis
- delivery analysis
- reply-rate analysis
- lead-quality analysis
- campaign diagnostics

That means failed, unsent, verified, unavailable, replied, and other status combinations are not filtered out during import.

## Recommended production flow

Recommended order for production:

1. Deploy the Apollo code and run migrations
2. Import the historical CSV:
   - `Apollo Data 28-01-2026 to oldest.csv`
3. Use Apollo incremental sync for new data moving forward
4. Use full historical sync only if additional API backfill is still needed outside the CSV-covered range

This is the safest approach because:

- the CSV already covers the historical range from January 28, 2026 backward
- the API can then be used mainly for newer or missing records
- unnecessary historical re-crawling can be avoided

## Operational notes

- Apollo dashboard route: `/integrations/apollo/dashboard/`
- Apollo is also surfaced in the admin integrations dashboard
- `partial` Apollo runs are expected when the call budget is hit
- `failed` means an actual error
- LinkedIn URL field was expanded to `500` chars because real data exceeded Django's default URL length

## Files of interest

- `integrations/apollo/models.py`
- `integrations/apollo/sync_service.py`
- `integrations/apollo/workers.py`
- `integrations/apollo/views.py`
- `integrations/apollo/management/commands/import_apollo_csv.py`
- `integrations/apollo/README.md`
- `integrations/migrations/0011_add_apollo_hourly_sync_job.py`
