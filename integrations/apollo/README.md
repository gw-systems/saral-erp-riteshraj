# Apollo Integration Handoff

This app adds Apollo outreach data into the ERP through two paths:

- direct Apollo API sync into `apollo_apollocampaign`, `apollo_apollomessage`, and `apollo_apollosyncstate`
- one-time or repeat CSV import through `manage.py import_apollo_csv`

## Included pieces

- Django app: `integrations/apollo/`
- Dashboard: `templates/apollo/dashboard.html`
- App wiring:
  - `minierp/settings.py`
  - `minierp/urls.py`
  - `integrations/models.py`
- Admin integrations hub:
  - `accounts/views_dashboard_admin.py`
  - `templates/dashboards/admin/integrations.html`
- Hourly scheduled job seed:
  - `integrations/migrations/0011_add_apollo_hourly_sync_job.py`

## Merge checklist

1. Copy the Apollo app and template files into the target ERP codebase.
2. Add `integrations.apollo` to `INSTALLED_APPS`.
3. Add Apollo settings in `minierp/settings.py`:
   - `APOLLO_API_KEY`
   - `APOLLO_BASE_URL`
   - `APOLLO_REQUEST_TIMEOUT`
   - `APOLLO_INCREMENTAL_LOOKBACK_DAYS`
   - `APOLLO_ACTIVITY_DELAY_MS`
   - `APOLLO_CALL_LIMIT`
4. Include Apollo URLs:
   - `path('integrations/apollo/', include('integrations.apollo.urls', namespace='apollo'))`
5. Extend shared integration metadata in `integrations/models.py` so Apollo appears in sync logs and scheduled jobs.
6. Run migrations:
   - `python manage.py migrate apollo`
   - `python manage.py migrate integrations`
7. Add `APOLLO_API_KEY` in the production environment.

## Scheduling

The migration `integrations/migrations/0011_add_apollo_hourly_sync_job.py` seeds:

- `name`: `Apollo Historical Sync`
- `endpoint`: `/integrations/apollo/workers/sync/`
- `cron`: `0 * * * *`
- `payload`: `{"sync_type": "full", "reset_checkpoint": false}`

This project already uses the shared scheduled-job system. Production must keep calling the master tick endpoint every minute:

- `/integrations/scheduled-jobs/tick/`

Apollo does not self-schedule. The hourly job only fires when that master tick is already running in production.

## Historical sync behavior

- Full sync uses `ApolloSyncState` as a checkpoint store.
- The state mirrors the Apps Script properties:
  - `c_year`
  - `c_month`
  - `c_camp_idx`
  - `c_page`
  - `is_complete`
- Month values are zero-based to match the original Apps Script:
  - `0 = January`
  - `1 = February`
  - `2 = March`
- Each run stops at `APOLLO_CALL_LIMIT` and resumes from the saved checkpoint on the next hourly run.

To initialize a fresh historical crawl, trigger a full sync once from the Apollo dashboard with:

- `start_date`
- `end_date`
- `reset_checkpoint = true`

After that, the hourly scheduled job can continue from the saved checkpoint.

## CSV import

Use the management command:

```bash
python manage.py import_apollo_csv "Apollo Data 28-01-2026 to oldest.csv"
```

Useful flags:

```bash
python manage.py import_apollo_csv "Apollo Data 28-01-2026 to oldest.csv" --dry-run
python manage.py import_apollo_csv "Apollo Data 28-01-2026 to oldest.csv" --replace-existing
python manage.py import_apollo_csv "Apollo Data 28-01-2026 to oldest.csv" --replace-existing --batch-size 5000
```

Notes:

- The CSV import is idempotent on `Message ID`.
- The CSV does not contain Apollo campaign IDs, so the importer creates stable synthetic campaign IDs using the campaign name.
- The importer ignores sheet-artifact columns such as the empty trailing column and `Last Checkpoint (IST): ...`.
- The CSV import does not modify `ApolloSyncState`.

If the CSV is being used as the historical base load, import it first and then use Apollo incremental sync for new data, or explicitly reset the historical checkpoint to the next desired API window.
