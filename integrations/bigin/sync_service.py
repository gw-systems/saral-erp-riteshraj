"""
Bigin Sync Service
Core sync logic extracted from tasks.py for use by Cloud Tasks workers
"""

import logging
import time
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from dateutil import parser as dateparser

from .api_client import fetch_module_list, fetch_changed_ids_via_coql, fetch_records_by_ids, _extract_times
from django.db.models import Q
from .models import BiginRecord, BiginAuthToken
from integrations.models import SyncLog
from integrations.sync_logger import SyncLogHandler
from django.conf import settings
import requests

logger = logging.getLogger(__name__)

# Modules synced on every run (incremental uses COQL two-step for Contacts)
MODULES_TO_SYNC = [
    "Contacts",      # COQL incremental (with inline notes fetch) or full REST paginated
    "Pipelines",     # COQL incremental or full REST paginated
    "Accounts",      # COQL incremental or full REST paginated
    "Products",      # COQL incremental or full REST paginated
]

# Notes module is only synced as a standalone module during full sync.
# On incremental, notes are fetched inline for each changed Contact (see _sync_module_coql).
MODULES_FULL_ONLY = [
    "Notes",         # Only on full sync (run_full=True), not incremental
]


def _log_operation(batch_log, level, operation, message='', module=None, duration_ms=None):
    """
    Helper function for operation-level logging.

    Args:
        batch_log: SyncLog batch instance
        level: Log level (INFO, SUCCESS, WARNING, ERROR)
        operation: Operation name (e.g., 'module_start', 'api_fetch', 'processing')
        message: Human-readable message
        module: Module name (Contacts, Deals, Pipelines, etc.) - used as sub_type
        duration_ms: Duration in milliseconds for timed operations
    """
    if batch_log:
        SyncLog.log(
            integration='bigin',
            sync_type=batch_log.sync_type,
            level=level,
            operation=operation,
            message=message,
            sub_type=module or '',
            duration_ms=duration_ms,
            batch=batch_log,
        )


def run_sync_all_modules(run_full=False, triggered_by_user=None, scheduled_job_id=None):
    """
    Sync all modules from Zoho Bigin into DB.
    Supports graceful stop and real-time progress tracking.

    Args:
        run_full: If True, full sync. If False, incremental (modified_since).
        triggered_by_user: Username of user who triggered the sync.
    """
    start_time = timezone.now()
    logger.info("[Bigin Sync] Starting sync_all_modules at %s (full=%s, user=%s)", start_time, run_full, triggered_by_user)

    # Check for existing running syncs with database locking (prevent race condition)
    # Auto-clean stale syncs: if last_updated > 3 minutes ago with no progress, container crashed
    STALE_THRESHOLD_MINUTES = 3
    with transaction.atomic():
        existing_sync = SyncLog.objects.select_for_update().filter(integration='bigin', status='running').first()
        if existing_sync:
            stale_cutoff = timezone.now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
            if existing_sync.last_updated < stale_cutoff:
                elapsed = int((timezone.now() - existing_sync.started_at).total_seconds())
                stale_for = int((timezone.now() - existing_sync.last_updated).total_seconds())
                logger.warning(
                    "[Bigin Sync] Auto-cleaning stale sync (ID: %s, started %ss ago, stale for %ss)",
                    existing_sync.id, elapsed, stale_for
                )
                existing_sync.status = 'stopped'
                existing_sync.completed_at = timezone.now()
                existing_sync.duration_seconds = elapsed
                existing_sync.error_message = (
                    f"Auto-stopped: container crashed or restarted "
                    f"(stale for {stale_for}s, no progress update in >{STALE_THRESHOLD_MINUTES}m)"
                )
                existing_sync.save()
            else:
                logger.warning("[Bigin Sync] Another sync is already running (ID: %s) — skipping", existing_sync.id)
                return {
                    'status': 'skipped',
                    'reason': f'Another sync already running (ID: {existing_sync.id})',
                    'synced': 0, 'created': 0, 'updated': 0, 'errors': 0,
                }

        # Full sync includes Notes module; incremental skips it (saves ~140 API calls/run)
        active_modules = MODULES_TO_SYNC + (MODULES_FULL_ONLY if run_full else [])

        # Create SyncLog entry atomically with user tracking
        sync_type = 'bigin_full' if run_full else 'bigin_incremental'
        sync_log = SyncLog.objects.create(
            integration='bigin',
            sync_type=sync_type,
            log_kind='batch',
            status='running',
            triggered_by='api',
            triggered_by_user=triggered_by_user,
            modules=active_modules,
            overall_progress_percent=0,
            scheduled_job_id=scheduled_job_id,
        )

    # Log sync start
    _log_operation(sync_log, 'INFO', 'sync_start',
                  f'Starting {"full" if run_full else "incremental"} sync for {len(MODULES_TO_SYNC)} modules',
                  module='')

    # Early check for OAuth token
    try:
        from .token_manager import get_valid_token
        token = get_valid_token()
        logger.info("[Bigin Sync] OAuth token validated successfully")
        _log_operation(sync_log, 'INFO', 'oauth_validated',
                      'OAuth token validated successfully', module='')
    except Exception as e:
        import traceback
        error_msg = f"OAuth Token Error: {type(e).__name__}: {str(e)}"
        error_traceback = traceback.format_exc()
        logger.error(f"[Bigin Sync] {error_msg}\n{error_traceback}")

        # Log OAuth error
        _log_operation(sync_log, 'ERROR', 'oauth_error',
                      error_msg, module='')

        sync_log.status = 'failed'
        sync_log.completed_at = timezone.now()
        sync_log.duration_seconds = 0
        sync_log.error_message = error_msg
        sync_log.error_details = {'traceback': error_traceback}
        sync_log.save()
        return

    total_synced = 0
    total_created = 0
    total_updated = 0
    total_errors = 0
    module_results = {}

    _sync_log_handler = SyncLogHandler(sync_log, integration='bigin', sync_type=sync_type,
                                       loggers=['integrations.bigin'])
    _sync_log_handler._attach()
    try:
        for idx, module in enumerate(active_modules):
            # Check if stop requested before starting module
            sync_log.refresh_from_db(fields=['stop_requested'])
            if sync_log.stop_requested:
                logger.info("[Bigin Sync] Stop requested before module %s, gracefully stopping...", module)
                sync_log.status = 'stopping'
                sync_log.save()
                break

            try:
                logger.info("[Bigin Sync] Syncing module: %s (%d/%d)", module, idx+1, len(MODULES_TO_SYNC))

                # Update current module
                sync_log.current_module = module
                sync_log.current_module_progress = 0
                sync_log.overall_progress_percent = int((idx / len(active_modules)) * 100)
                sync_log.save()

                stats = sync_module(module, run_full=run_full, sync_log_id=sync_log.id)

                # Check again after module completes
                sync_log.refresh_from_db(fields=['stop_requested'])
                if sync_log.stop_requested:
                    logger.info("[Bigin Sync] Stop requested after module %s, stopping...", module)
                    break

                # Accumulate stats
                total_synced += stats['synced']
                total_created += stats['created']
                total_updated += stats['updated']
                total_errors += stats['errors']

                # Store per-module results
                module_results[module] = stats

            except Exception as e:
                import traceback
                error_traceback = traceback.format_exc()
                error_msg = f"{type(e).__name__}: {str(e)}"
                logger.exception("Error syncing module %s: %s", module, e)

                # Log module error
                _log_operation(sync_log, 'ERROR', 'module_error',
                              f'{module} sync failed: {error_msg}',
                              module=module)

                total_errors += 1
                module_results[module] = {
                    'synced': 0,
                    'created': 0,
                    'updated': 0,
                    'errors': 1,
                    'error_message': error_msg,
                    'traceback': error_traceback[:500]
                }

        duration = timezone.now() - start_time
        logger.info("[Bigin Sync] Finished sync_all_modules in %s", duration)

        # Update SyncLog with results
        sync_log.refresh_from_db(fields=['stop_requested', 'status'])
        if sync_log.stop_requested or sync_log.status == 'stopping':
            sync_log.status = 'stopped'
            logger.info("[Bigin Sync] Sync was stopped by user request")
            # Log sync stopped
            _log_operation(sync_log, 'WARNING', 'sync_stopped',
                          f'Sync stopped by user: {total_synced:,} records synced before stop',
                          module='')
        else:
            sync_log.status = 'completed' if total_errors == 0 else 'partial'
            # Log sync completion
            status_level = 'SUCCESS' if total_errors == 0 else 'WARNING'
            _log_operation(sync_log, status_level, 'sync_complete',
                          f'Sync {"completed" if total_errors == 0 else "partially completed"}: {total_synced:,} synced, {total_created:,} created, {total_updated:,} updated, {total_errors} errors in {int(duration.total_seconds())}s',
                          module='')

        sync_log.completed_at = timezone.now()
        sync_log.duration_seconds = int(duration.total_seconds())
        sync_log.total_records_synced = total_synced
        sync_log.records_created = total_created
        sync_log.records_updated = total_updated
        sync_log.errors_count = total_errors
        sync_log.module_results = module_results
        sync_log.overall_progress_percent = 100
        sync_log.current_module = None
        sync_log.api_calls_count = sync_log.operations.count()
        sync_log.save()

    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        error_traceback = traceback.format_exc()
        logger.exception("[Bigin Sync] Critical error in sync_all_modules")

        # Log critical error
        _log_operation(sync_log, 'CRITICAL', 'sync_critical_error',
                      f'Critical sync error: {error_msg}',
                      module='')

        # Mark sync as failed
        sync_log.status = 'failed'
        sync_log.completed_at = timezone.now()
        sync_log.duration_seconds = int((timezone.now() - start_time).total_seconds())
        sync_log.error_message = error_msg
        sync_log.error_details = {'traceback': error_traceback}
        sync_log.total_records_synced = total_synced
        sync_log.records_created = total_created
        sync_log.records_updated = total_updated
        sync_log.errors_count = total_errors + 1
        sync_log.module_results = module_results
        sync_log.save()

        raise

    finally:
        _sync_log_handler._detach()


def sync_module(module_name, run_full=False, sync_log_id=None):
    """
    Sync a single Bigin module with optimized batch operations.

    For incremental: uses COQL two-step for ALL modules (IDs → batch REST fetch).
    Contacts uses Last_Activity_Time; other modules use Modified_Time.

    For full sync: uses REST paginated fetch_module_list().
    """
    BATCH_SIZE = 1000
    PROGRESS_UPDATE_INTERVAL = 1000

    # --- COQL fast path: ALL modules on incremental ---
    if not run_full:
        if module_name == 'Contacts':
            since_dt = _get_last_activity_time_for_contacts()
        else:
            since_dt = _get_last_modified_time_for_module(module_name)
        if since_dt:
            return _sync_module_coql(module_name, since_dt, sync_log_id)
        # No baseline yet — fall through to full paginated fetch to build initial dataset
        logger.info("[Bigin Sync] %s: no baseline found, running full fetch to build initial dataset", module_name)

    last_modified = None if run_full else _get_last_modified_time_for_module(module_name)
    logger.info(f"[Bigin Sync] {module_name} - last_modified={last_modified}, run_full={run_full}")

    count = 0
    created_count = 0
    updated_count = 0
    error_count = 0

    # Get sync log
    sync_log = None
    if sync_log_id:
        try:
            sync_log = SyncLog.objects.get(id=sync_log_id)
            if sync_log.stop_requested:
                _log_operation(sync_log, 'WARNING', 'sync_stopped',
                              f'{module_name} sync stopped before start', module=module_name)
                return {'synced': 0, 'created': 0, 'updated': 0, 'errors': 0}
        except SyncLog.DoesNotExist:
            pass

    # Log module sync start
    module_start_time = time.time()
    _log_operation(sync_log, 'INFO', 'module_start',
                  f'Starting {module_name} sync ({"full" if run_full else "incremental"})',
                  module=module_name)

    # Fetch existing IDs in bulk — include DB pk to avoid N+1 query inside sync loop
    existing_records = {}   # bigin_id -> modified_time
    existing_pks = {}       # bigin_id -> DB pk (for bulk_update)
    if not run_full:
        for rec in BiginRecord.objects.filter(module=module_name).values('id', 'bigin_id', 'modified_time'):
            existing_records[rec['bigin_id']] = rec['modified_time']
            existing_pks[rec['bigin_id']] = rec['id']
        logger.info(f"[Sync] Loaded {len(existing_records)} existing {module_name} IDs")

    to_create = []
    to_update = []

    # Fetch records from API with timing
    api_start_time = time.time()
    api_record_count = 0

    for record in fetch_module_list(module_name, modified_since=last_modified):
        api_record_count += 1

        # Log API fetch completion after first batch
        if api_record_count == 1:
            api_duration_ms = int((time.time() - api_start_time) * 1000)
            _log_operation(sync_log, 'INFO', 'api_fetch_start',
                          f'Started fetching {module_name} from API',
                          module=module_name, duration_ms=api_duration_ms)
        # Check stop flag
        if sync_log and count % 100 == 0:
            sync_log.refresh_from_db(fields=['stop_requested'])
            if sync_log.stop_requested:
                _log_operation(sync_log, 'WARNING', 'sync_stopped',
                              f'{module_name} sync stopped at {count} records',
                              module=module_name)
                break

        try:
            r_id = str(record.get("id"))
            if not r_id:
                error_count += 1
                _log_operation(sync_log, 'ERROR', 'record_error',
                              f'{module_name} record missing ID',
                              module=module_name)
                continue

            # Extract fields
            created_s, modified_s = _extract_times(record)
            extracted_fields = _extract_record_fields(module_name, record, created_s, modified_s)

            # Separate create vs update — use pre-loaded pk (no N+1 query)
            if r_id in existing_records:
                rec_modified = extracted_fields.get('modified_time')
                if rec_modified and rec_modified > existing_records[r_id]:
                    to_update.append(BiginRecord(
                        id=existing_pks[r_id],
                        bigin_id=r_id,
                        module=module_name,
                        **extracted_fields
                    ))
            else:
                to_create.append(BiginRecord(
                    bigin_id=r_id,
                    module=module_name,
                    **extracted_fields
                ))

            count += 1

            # Bulk operations every BATCH_SIZE
            if len(to_create) + len(to_update) >= BATCH_SIZE:
                created_count, updated_count = _bulk_save(to_create, to_update, module_name, created_count, updated_count, sync_log)
                to_create = []
                to_update = []

            # Update progress and log milestones
            if count % PROGRESS_UPDATE_INTERVAL == 0 and sync_log:
                sync_log.current_module_progress = count
                sync_log.save(update_fields=['current_module_progress', 'last_updated'])

                # Log processing milestones
                if count % 1000 == 0:
                    _log_operation(sync_log, 'INFO', 'processing_milestone',
                                  f'{module_name}: Processed {count:,} records ({created_count:,} new, {updated_count:,} updated)',
                                  module=module_name)
                elif count % 500 == 0:
                    _log_operation(sync_log, 'INFO', 'processing_milestone',
                                  f'{module_name}: Processed {count:,} records',
                                  module=module_name)
                elif count % 100 == 0:
                    _log_operation(sync_log, 'INFO', 'processing_progress',
                                  f'{module_name}: Processing at {count:,} records',
                                  module=module_name)

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(
                "[Bigin Sync] Error processing %s record id=%s email=%s name=%s: %s",
                module_name, record.get('id'), record.get('Email'),
                record.get('Full_Name'), error_msg
            )
            _log_operation(sync_log, 'ERROR', 'record_processing_error',
                          f'{module_name} record {record.get("id", "unknown")}: {error_msg}',
                          module=module_name)
            error_count += 1

    # Log API fetch completion
    api_total_duration_ms = int((time.time() - api_start_time) * 1000)
    _log_operation(sync_log, 'INFO', 'api_fetch_complete',
                  f'Fetched {api_record_count:,} {module_name} records from API',
                  module=module_name, duration_ms=api_total_duration_ms)

    # Final bulk commit
    if to_create or to_update:
        created_count, updated_count = _bulk_save(to_create, to_update, module_name, created_count, updated_count, sync_log)

    # Calculate total module duration
    module_duration_ms = int((time.time() - module_start_time) * 1000)

    logger.info(f"[Bigin Sync] Module {module_name} complete. {count} records processed.")

    # Log module completion
    _log_operation(sync_log, 'SUCCESS', 'module_complete',
                  f'{module_name} sync complete: {count:,} processed, {created_count:,} created, {updated_count:,} updated, {error_count} errors',
                  module=module_name, duration_ms=module_duration_ms)

    return {
        'synced': count,
        'created': created_count,
        'updated': updated_count,
        'errors': error_count
    }


def _sync_module_coql(module_name, since_dt, sync_log_id=None):
    """
    COQL two-step incremental sync for a single module.

    Step 1 — COQL: get IDs of records with Last_Activity_Time >= since_dt (1 API call per 200 IDs)
    Step 2 — REST: batch-fetch full records by IDs (1 API call per 100 records)

    For a typical 15-min window with 5-50 changed contacts: 2-3 total API calls
    vs the previous 140 REST paginated calls for all contacts.
    """
    module_start_time = time.time()

    sync_log = None
    if sync_log_id:
        try:
            sync_log = SyncLog.objects.get(id=sync_log_id)
        except SyncLog.DoesNotExist:
            pass

    _log_operation(sync_log, 'INFO', 'module_start',
                   f'Starting {module_name} COQL incremental sync since {since_dt}',
                   module=module_name)

    # Step 1: COQL — get IDs of changed records (cheap, no field data)
    coql_start = time.time()
    changed_ids = fetch_changed_ids_via_coql(module_name, since_dt)
    coql_ms = int((time.time() - coql_start) * 1000)

    if not changed_ids:
        _log_operation(sync_log, 'SUCCESS', 'module_complete',
                       f'{module_name} COQL incremental: no changes since {since_dt}',
                       module=module_name, duration_ms=int((time.time() - module_start_time) * 1000))
        return {'synced': 0, 'created': 0, 'updated': 0, 'errors': 0}

    _log_operation(sync_log, 'INFO', 'coql_complete',
                   f'{module_name}: {len(changed_ids)} changed IDs via COQL',
                   module=module_name, duration_ms=coql_ms)

    # Load existing records for the changed IDs only (not the full table)
    existing_records = {}
    existing_pks = {}
    for rec in BiginRecord.objects.filter(
        module=module_name, bigin_id__in=changed_ids
    ).values('id', 'bigin_id', 'modified_time'):
        existing_records[rec['bigin_id']] = rec['modified_time']
        existing_pks[rec['bigin_id']] = rec['id']

    # Step 2: REST batch fetch — full records for only the changed IDs
    to_create = []
    to_update = []
    count = 0
    created_count = 0
    updated_count = 0
    error_count = 0

    rest_start = time.time()
    for record in fetch_records_by_ids(module_name, changed_ids):
        try:
            r_id = str(record.get("id"))
            if not r_id:
                error_count += 1
                continue

            created_s, modified_s = _extract_times(record)
            extracted_fields = _extract_record_fields(module_name, record, created_s, modified_s)

            # Inline notes fetch for Contacts — fetch notes for each changed contact
            if module_name == 'Contacts':
                try:
                    from integrations.bigin.bigin_sync import fetch_contact_notes
                    notes_text = fetch_contact_notes(r_id)
                    extracted_fields['notes'] = notes_text
                    extracted_fields['notes_fetched_at'] = timezone.now()
                    time.sleep(0.2)  # 200ms rate limit
                except Exception as e:
                    logger.warning("[COQL Sync] Failed to fetch notes for contact %s: %s", r_id, e)

            if r_id in existing_records:
                rec_modified = extracted_fields.get('modified_time')
                # Always update for COQL path — Last_Activity_Time changed even if Modified_Time didn't
                to_update.append(BiginRecord(
                    id=existing_pks[r_id],
                    bigin_id=r_id,
                    module=module_name,
                    **extracted_fields
                ))
            else:
                to_create.append(BiginRecord(
                    bigin_id=r_id,
                    module=module_name,
                    **extracted_fields
                ))

            count += 1

            if len(to_create) + len(to_update) >= 500:
                c, u = _bulk_save(to_create, to_update, module_name, 0, 0, sync_log)
                created_count += c
                updated_count += u
                to_create = []
                to_update = []

        except Exception as e:
            logger.error(f"[COQL Sync] Error processing {module_name} id={record.get('id')}: {e}")
            error_count += 1

    rest_ms = int((time.time() - rest_start) * 1000)

    # Final batch save
    if to_create or to_update:
        c, u = _bulk_save(to_create, to_update, module_name, 0, 0, sync_log)
        created_count += c
        updated_count += u

    module_duration_ms = int((time.time() - module_start_time) * 1000)
    logger.info(
        f"[COQL Sync] {module_name}: {count} processed, {created_count} created, "
        f"{updated_count} updated, {error_count} errors | "
        f"COQL: {coql_ms}ms, REST batch: {rest_ms}ms"
    )
    _log_operation(sync_log, 'SUCCESS', 'module_complete',
                   f'{module_name} COQL incremental: {count} processed ({created_count} new, {updated_count} updated, {error_count} errors)',
                   module=module_name, duration_ms=module_duration_ms)

    return {
        'synced': count,
        'created': created_count,
        'updated': updated_count,
        'errors': error_count
    }


def _bulk_save(to_create, to_update, module_name, created_count, updated_count, sync_log=None):
    """Helper to bulk save records with operation logging"""
    bulk_start_time = time.time()

    try:
        with transaction.atomic():
            if to_create:
                BiginRecord.objects.bulk_create(to_create, ignore_conflicts=True, batch_size=500)
                created_count += len(to_create)
            if to_update:
                BiginRecord.objects.bulk_update(
                    to_update,
                    fields=['raw', 'created_time', 'modified_time', 'full_name', 'first_name',
                            'last_name', 'title', 'email', 'mobile', 'owner', 'account_name',
                            'description', 'contact_type', 'lead_source', 'lead_stage', 'status',
                            'reason', 'locations', 'area_requirement', 'industry_type',
                            'business_type', 'business_model', 'last_activity_time',
                            'notes', 'notes_fetched_at'],
                    batch_size=500
                )
                updated_count += len(to_update)

        bulk_duration_ms = int((time.time() - bulk_start_time) * 1000)
        logger.info(f"[Bulk] {module_name}: Created {len(to_create)}, Updated {len(to_update)}")

        # Log bulk save operation
        if sync_log and (len(to_create) > 0 or len(to_update) > 0):
            _log_operation(sync_log, 'INFO', 'bulk_save',
                          f'{module_name}: Saved batch ({len(to_create)} new, {len(to_update)} updated)',
                          module=module_name, duration_ms=bulk_duration_ms)

    except Exception as bulk_error:
        error_msg = f"{type(bulk_error).__name__}: {str(bulk_error)}"
        logger.error(f"[Bulk] Error in bulk operation for {module_name}: {error_msg}")

        # Log bulk save error
        _log_operation(sync_log, 'ERROR', 'bulk_save_error',
                      f'{module_name}: Bulk save failed, falling back to individual saves: {error_msg}',
                      module=module_name)

        # Fallback to individual saves
        for rec in to_create:
            try:
                rec.save()
                created_count += 1
            except Exception as individual_err:
                logger.error(f"[Bigin] Individual save failed for {module_name} bigin_id={getattr(rec, 'bigin_id', 'unknown')}: {individual_err}")
                _log_operation(sync_log, 'ERROR', 'individual_save_error',
                              f'{module_name}: Individual create failed for bigin_id={getattr(rec, "bigin_id", "unknown")}: {individual_err}',
                              module=module_name)
        for rec in to_update:
            try:
                rec.save()
                updated_count += 1
            except Exception as individual_err:
                logger.error(f"[Bigin] Individual update failed for {module_name} bigin_id={getattr(rec, 'bigin_id', 'unknown')}: {individual_err}")
                _log_operation(sync_log, 'ERROR', 'individual_save_error',
                              f'{module_name}: Individual update failed for bigin_id={getattr(rec, "bigin_id", "unknown")}: {individual_err}',
                              module=module_name)

    return created_count, updated_count


def _get_last_modified_time_for_module(module):
    latest = BiginRecord.objects.filter(module=module).order_by('-modified_time').first()
    if latest and latest.modified_time:
        return latest.modified_time
    return None


def _get_last_activity_time_for_contacts():
    """
    For COQL incremental sync: use Last_Activity_Time as the sync boundary.
    This catches contacts where notes/calls were logged without editing contact fields,
    which Modified_Time would miss.
    """
    latest = BiginRecord.objects.filter(
        module='Contacts', last_activity_time__isnull=False
    ).order_by('-last_activity_time').first()
    if latest and latest.last_activity_time:
        return latest.last_activity_time
    # Fall back to modified_time if no last_activity_time recorded yet
    return _get_last_modified_time_for_module('Contacts')


def _parse_time(s):
    if not s:
        return None
    try:
        dt = dateparser.parse(s)
        if dt and timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt
    except Exception:
        return None


def _extract_record_fields(module, record, created_s, modified_s):
    """Extract fields from record dict"""
    created_dt = _parse_time(created_s)
    modified_dt = _parse_time(modified_s)

    def join_array(value):
        if isinstance(value, list):
            return ", ".join(str(v) for v in value if v)
        return value

    def get_owner_name(owner_data):
        if isinstance(owner_data, dict):
            return owner_data.get("name")
        return None

    def get_account_name(account_data):
        if isinstance(account_data, dict):
            return account_data.get("name")
        return None

    def s(value, max_len=255):
        """Safely convert to string and truncate to max_len to avoid varchar overflow."""
        if value is None:
            return None
        v = str(value)
        return v[:max_len] if len(v) > max_len else v

    extracted = {
        "raw": record,
        "created_time": created_dt,
        "modified_time": modified_dt,
    }

    if module == "Contacts":
        raw_email = record.get("Email")
        # Drop invalid emails (spaces, missing @) that would fail EmailField validation
        if raw_email and (' ' in str(raw_email) or '@' not in str(raw_email)):
            logger.warning("[Bigin Sync] Dropping invalid email for contact %s: %r", record.get('id'), raw_email)
            raw_email = None

        extracted.update({
            "full_name": s(record.get("Full_Name")),
            "first_name": s(record.get("First_Name")),
            "last_name": s(record.get("Last_Name")),
            "title": s(record.get("Title")),
            "email": s(raw_email),
            "mobile": s(record.get("Mobile")),
            "owner": s(get_owner_name(record.get("Owner"))),
            "account_name": s(get_account_name(record.get("Account_Name"))),
            "description": record.get("Description"),  # TextField — no limit needed
            "contact_type": s(record.get("Type")),
            "lead_source": s(record.get("Lead_Source")),
            "lead_stage": s(join_array(record.get("Status_of_Action")), max_len=500),
            "status": s(join_array(record.get("Status")), max_len=500),
            "reason": s(record.get("Reason")),
            "locations": s(join_array(record.get("Locations")), max_len=500),
            "area_requirement": s(record.get("Area_Requirement")),
            "industry_type": s(record.get("Industry_Type")),
            "business_type": s(join_array(record.get("Bussiness_Type"))),
            "business_model": s(record.get("Business_Model")),
            "last_activity_time": _parse_time(record.get("Last_Activity_Time")),
        })

    return extracted


def run_refresh_bigin_token():
    """
    Auto-refresh Bigin OAuth token before expiry.
    """
    try:
        token = BiginAuthToken.objects.first()

        if not token:
            logger.warning("No BiginAuthToken found - OAuth flow needed")
            return "No token found"

        # Check if token expires in next 10 minutes
        if timezone.now() >= token.expires_at - timedelta(minutes=10):
            logger.info(f"Refreshing token (expires at {token.expires_at})")

            # Refresh token — use DB settings (priority) over env vars
            from integrations.bigin.utils.settings_helper import get_bigin_config
            bigin_cfg = get_bigin_config()
            data = {
                "refresh_token": token.refresh_token,
                "client_id": bigin_cfg['client_id'] or getattr(settings, 'ZOHO_CLIENT_ID', ''),
                "client_secret": bigin_cfg['client_secret'] or getattr(settings, 'ZOHO_CLIENT_SECRET', ''),
                "grant_type": "refresh_token",
            }

            token_url = bigin_cfg.get('token_url') or getattr(settings, 'ZOHO_TOKEN_URL', 'https://accounts.zoho.com/oauth/v2/token')
            response = requests.post(token_url, data=data)

            if response.status_code == 200:
                token_data = response.json()

                token.access_token = token_data.get("access_token")
                token.expires_at = timezone.now() + timedelta(seconds=token_data.get("expires_in", 3600))
                token.save()

                logger.info(f"✅ Token refreshed successfully, expires at {token.expires_at}")
                return f"Token refreshed, expires at {token.expires_at}"
            else:
                logger.error(f"Token refresh failed: {response.text}")
                return f"Failed: {response.text}"
        else:
            logger.info(f"Token still valid until {token.expires_at}")
            return f"Token valid until {token.expires_at}"

    except Exception as e:
        logger.error(f"Error in refresh_bigin_token: {e}")
        return f"Error: {str(e)}"
