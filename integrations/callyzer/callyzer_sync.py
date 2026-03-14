"""
Callyzer Sync Engine
Core logic for syncing call data from Callyzer API
"""

import logging
import time
from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone

from .api_client import CallyzerAPIClient, get_unix_timestamp_range
from .models import (
    CallyzerToken,
    CallSummary,
    EmployeeSummary,
    CallAnalysis,
    NeverAttendedCall,
    NotPickedUpCall,
    UniqueClient,
    HourlyAnalytic,
    DailyAnalytic,
    CallHistory,
)
from integrations.models import SyncLog
from .utils.encryption import CallyzerEncryption
from .utils.parsers import (
    parse_call_logs,
    extract_call_date,
    extract_call_time,
    safe_int,
    safe_float,
    safe_str
)

logger = logging.getLogger(__name__)


def _log(batch_log, level, operation, message='', sub_type='', duration_ms=None):
    """Helper: write an operation-level log to unified SyncLog."""
    if batch_log is None:
        logger.warning(f"[Callyzer] _log called but batch_log is None! Operation: {operation}")
        return
    SyncLog.log(
        integration='callyzer',
        sync_type='callyzer',
        level=level,
        operation=operation,
        message=message,
        sub_type=sub_type,
        duration_ms=duration_ms,
        batch=batch_log,
    )


def sync_callyzer_account(token: CallyzerToken, days_back: int = 150, batch_log_id: int = None, scheduled_job_id=None) -> dict:
    """
    Sync all reports for a single Callyzer account

    Args:
        token: CallyzerToken instance
        days_back: Number of days to fetch (default: 150)
        batch_log_id: Optional pre-created batch log ID (if None, creates new one)

    Returns:
        Dictionary with sync statistics
    """
    logger.info(f"[Callyzer Sync] Starting sync for {token.account_name}")
    start_time = timezone.now()

    stats = {
        'account': token.account_name,
        'success': False,
        'reports_synced': 0,
        'total_records': 0,
        'errors': []
    }

    # Create or reuse batch log entry with stale sync cleanup
    if batch_log_id:
        batch_log = SyncLog.objects.get(id=batch_log_id)
    else:
        STALE_THRESHOLD_MINUTES = 10
        with transaction.atomic():
            existing_sync = SyncLog.objects.select_for_update().filter(
                integration='callyzer',
                log_kind='batch',
                status='running'
            ).order_by('-started_at').first()

            if existing_sync:
                stale_cutoff = timezone.now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
                if existing_sync.last_updated < stale_cutoff:
                    logger.warning(f"[Callyzer Sync] Stale sync {existing_sync.id} detected, marking as stopped")
                    existing_sync.status = 'stopped'
                    existing_sync.error_message = 'Marked as stopped due to staleness (no updates for 10 minutes)'
                    existing_sync.save(update_fields=['status', 'error_message', 'last_updated'])
                else:
                    raise RuntimeError(f"Another sync is already running (started {existing_sync.started_at})")

            # Create new batch log
            batch_log = SyncLog.objects.create(
                integration='callyzer',
                sync_type='callyzer',
                log_kind='batch',
                status='running',
                triggered_by_user=token.account_name,
                scheduled_job_id=scheduled_job_id,
            )

    from integrations.sync_logger import SyncLogHandler
    # Attach handler so all logger.* calls in this thread appear in the UI log panel
    _sync_log_handler = SyncLogHandler(batch_log, integration='callyzer', sync_type='callyzer',
                                       loggers=['integrations.callyzer'])
    _sync_log_handler._attach()
    try:
        # Decrypt API key
        api_key = CallyzerEncryption.decrypt(token.encrypted_api_key)

        # Initialize API client
        client = CallyzerAPIClient(api_key)

        # Get date range
        call_from, call_to = get_unix_timestamp_range(days_back)

        _log(batch_log, 'INFO', 'Sync Started',
             f"Syncing {token.account_name} for last {days_back} days "
             f"(from {datetime.utcfromtimestamp(call_from).date()} to {datetime.utcfromtimestamp(call_to).date()})")

        # Test connection
        _log(batch_log, 'INFO', 'Connection Test', 'Testing Callyzer API connection...')
        conn_start = time.time()
        if not client.test_connection(call_from, call_to):
            error_msg = "API connection test failed"
            stats['errors'].append(error_msg)
            _log(batch_log, 'ERROR', 'Connection Test', error_msg)
            batch_log.status = 'failed'
            batch_log.error_message = error_msg
            batch_log.completed_at = timezone.now()
            batch_log.save()
            return stats
        conn_ms = int((time.time() - conn_start) * 1000)
        _log(batch_log, 'SUCCESS', 'Connection Test', f'API connection OK ({conn_ms}ms)', duration_ms=conn_ms)

        # Sync each report type
        reports = [
            ('Call Summary', sync_call_summary),
            ('Employee Summary', sync_employee_summary),
            ('Call Analysis', sync_call_analysis),
            ('Never Attended', sync_never_attended),
            ('Not Picked Up', sync_not_picked_up),
            ('Unique Clients', sync_unique_clients),
            ('Hourly Analytics', sync_hourly_analytics),
            ('Daily Analytics', sync_daily_analytics),
            ('Call History', sync_call_history),
        ]
        total_reports = len(reports)

        for idx, (report_name, sync_func) in enumerate(reports):
            # Check for stop request before each report
            batch_log.refresh_from_db(fields=['stop_requested'])
            if batch_log.stop_requested:
                logger.info(f"[Callyzer Sync] Sync {batch_log.id} stopped by user request before {report_name}")
                _log(batch_log, 'WARNING', 'Sync Stopped',
                     f'Sync stopped by user request before {report_name} '
                     f'({stats["reports_synced"]}/{total_reports} reports done, '
                     f'{stats["total_records"]} records synced)')
                batch_log.status = 'stopped'
                batch_log.completed_at = timezone.now()
                batch_log.duration_seconds = int((timezone.now() - start_time).total_seconds())
                batch_log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'last_updated'])
                stats['success'] = False
                return stats

            try:
                logger.info(f"[Callyzer Sync] Syncing {report_name} ({idx+1}/{total_reports})...")
                batch_log.current_module = report_name
                batch_log.overall_progress_percent = int((idx / total_reports) * 100)
                batch_log.save(update_fields=['current_module', 'overall_progress_percent', 'last_updated'])

                _log(batch_log, 'INFO', f'Syncing {report_name}',
                     f'Starting {report_name} sync ({idx+1}/{total_reports})',
                     sub_type=report_name)

                report_start = time.time()
                record_count = sync_func(client, token, call_from, call_to, batch_log=batch_log)
                report_ms = int((time.time() - report_start) * 1000)

                stats['reports_synced'] += 1
                stats['total_records'] += record_count

                _log(batch_log, 'SUCCESS', f'{report_name} Complete',
                     f'Synced {record_count} records in {report_ms}ms',
                     sub_type=report_name, duration_ms=report_ms)

            except Exception as e:
                error_msg = f"{report_name} sync failed: {str(e)}"
                stats['errors'].append(error_msg)
                logger.exception(f"[Callyzer Sync] {error_msg}")
                _log(batch_log, 'ERROR', f'{report_name} Failed', error_msg, sub_type=report_name)

        # Update last sync time
        token.last_sync_at = timezone.now()
        token.save()

        stats['success'] = True
        duration = (timezone.now() - start_time).total_seconds()

        _log(batch_log, 'SUCCESS', 'Sync Complete',
             f"Synced {stats['reports_synced']}/{total_reports} reports, "
             f"{stats['total_records']} total records in {duration:.1f}s. "
             f"Errors: {len(stats['errors'])}",
             duration_ms=int(duration * 1000))

        batch_log.status = 'completed'
        batch_log.completed_at = timezone.now()
        batch_log.duration_seconds = int(duration)
        batch_log.total_records_synced = stats['total_records']
        batch_log.errors_count = len(stats['errors'])
        batch_log.overall_progress_percent = 100
        batch_log.api_calls_count = batch_log.operations.count()
        batch_log.save()

        logger.info(f"[Callyzer Sync] ✓ Complete for {token.account_name}: "
                    f"{stats['reports_synced']} reports, {stats['total_records']} records")

    except Exception as e:
        error_msg = f"Critical sync error: {str(e)}"
        stats['errors'].append(error_msg)
        logger.exception(f"[Callyzer Sync] {error_msg}")
        _log(batch_log, 'CRITICAL', 'Sync Failed', error_msg)
        batch_log.status = 'failed'
        batch_log.error_message = error_msg
        batch_log.completed_at = timezone.now()
        batch_log.save()
    finally:
        _sync_log_handler._detach()

    return stats


def sync_all_callyzer_accounts(days_back: int = 150, scheduled_job_id=None) -> dict:
    """
    Sync all active Callyzer accounts

    Args:
        days_back: Number of days to fetch

    Returns:
        Dictionary with overall sync statistics
    """
    logger.info("[Callyzer Sync] Starting sync for all accounts")

    tokens = CallyzerToken.objects.filter(is_active=True)
    total_stats = {
        'total_accounts': tokens.count(),
        'successful': 0,
        'failed': 0,
        'accounts': []
    }

    for token in tokens:
        account_stats = sync_callyzer_account(token, days_back, scheduled_job_id=scheduled_job_id)
        total_stats['accounts'].append(account_stats)

        if account_stats['success']:
            total_stats['successful'] += 1
        else:
            total_stats['failed'] += 1

    logger.info(f"[Callyzer Sync] All accounts complete: {total_stats['successful']}/{total_stats['total_accounts']} successful")
    return total_stats


# ==================== INDIVIDUAL REPORT SYNC FUNCTIONS ====================

def sync_call_summary(client: CallyzerAPIClient, token: CallyzerToken,
                     call_from: int, call_to: int, batch_log=None) -> int:
    """Sync Call Summary report"""
    _log(batch_log, 'DEBUG', 'API Fetch', 'Fetching call summary from Callyzer API', sub_type='Call Summary')

    fetch_start = time.time()
    data = client.get_call_summary(call_from, call_to)
    fetch_ms = int((time.time() - fetch_start) * 1000)

    if not data:
        _log(batch_log, 'WARNING', 'No Data', 'Call summary API returned empty response',
             sub_type='Call Summary', duration_ms=fetch_ms)
        return 0

    total_calls = safe_int(data.get('total_calls'))
    answered = safe_int(data.get('answered_calls'))
    missed = safe_int(data.get('missed_calls'))

    _log(batch_log, 'INFO', 'API Fetch',
         f'Received call summary in {fetch_ms}ms — total={total_calls}, answered={answered}, missed={missed}',
         sub_type='Call Summary', duration_ms=fetch_ms)

    # Clear existing data
    deleted = CallSummary.objects.filter(token=token).delete()
    _log(batch_log, 'DEBUG', 'DB Clear', f'Cleared {deleted[0]} existing call summary records',
         sub_type='Call Summary')

    # Create new summary
    save_start = time.time()
    CallSummary.objects.create(
        token=token,
        raw_data=data,
        total_calls=total_calls,
        answered_calls=answered,
        missed_calls=missed,
        total_duration_seconds=safe_int(data.get('total_duration')),
        avg_duration_seconds=safe_float(data.get('avg_duration')),
    )
    save_ms = int((time.time() - save_start) * 1000)
    _log(batch_log, 'DEBUG', 'DB Save', f'Saved call summary record in {save_ms}ms',
         sub_type='Call Summary', duration_ms=save_ms)

    return 1


def sync_employee_summary(client: CallyzerAPIClient, token: CallyzerToken,
                         call_from: int, call_to: int, batch_log=None) -> int:
    """Sync Employee Summary report"""
    _log(batch_log, 'DEBUG', 'API Fetch', 'Fetching employee summary (paginated)', sub_type='Employee Summary')

    fetch_start = time.time()
    records = client.fetch_all_paginated(
        client.get_employee_summary,
        call_from,
        call_to
    )
    fetch_ms = int((time.time() - fetch_start) * 1000)

    if not records:
        _log(batch_log, 'WARNING', 'No Data', 'Employee summary returned no records',
             sub_type='Employee Summary', duration_ms=fetch_ms)
        return 0

    _log(batch_log, 'INFO', 'API Fetch', f'Fetched {len(records)} employee records in {fetch_ms}ms',
         sub_type='Employee Summary', duration_ms=fetch_ms)

    # Clear existing data
    deleted = EmployeeSummary.objects.filter(token=token).delete()
    _log(batch_log, 'DEBUG', 'DB Clear', f'Cleared {deleted[0]} existing employee summary records',
         sub_type='Employee Summary')

    # Batch create new records
    employees = []
    parse_errors = 0
    for record in records:
        try:
            employees.append(EmployeeSummary(
                token=token,
                raw_data=record,
                emp_name=safe_str(record.get('emp_name')),
                emp_id=safe_str(record.get('emp_id')),
                total_calls=safe_int(record.get('total_calls')),
                answered_calls=safe_int(record.get('answered_calls')),
                missed_calls=safe_int(record.get('missed_calls')),
                outbound_calls=safe_int(record.get('outbound_calls')),
                inbound_calls=safe_int(record.get('inbound_calls')),
                total_duration_seconds=safe_int(record.get('total_duration')),
                avg_duration_seconds=safe_float(record.get('avg_duration')),
            ))
        except Exception as e:
            parse_errors += 1
            logger.error(f"[Callyzer] Error parsing employee record {record.get('emp_id')}: {e}")
            _log(batch_log, 'ERROR', 'Parse Error',
                 f"Failed to parse employee record emp_id={record.get('emp_id')}: {e}",
                 sub_type='Employee Summary')

    if parse_errors:
        _log(batch_log, 'WARNING', 'Parse Errors',
             f'{parse_errors} employee records failed to parse', sub_type='Employee Summary')

    save_start = time.time()
    EmployeeSummary.objects.bulk_create(employees, batch_size=500)
    save_ms = int((time.time() - save_start) * 1000)
    _log(batch_log, 'DEBUG', 'DB Save',
         f'Bulk-created {len(employees)} employee records in {save_ms}ms',
         sub_type='Employee Summary', duration_ms=save_ms)

    return len(employees)


def sync_call_analysis(client: CallyzerAPIClient, token: CallyzerToken,
                      call_from: int, call_to: int, batch_log=None) -> int:
    """Sync Call Analysis report"""
    _log(batch_log, 'DEBUG', 'API Fetch', 'Fetching call analysis from Callyzer API', sub_type='Call Analysis')

    fetch_start = time.time()
    data = client.get_call_analysis(call_from, call_to)
    fetch_ms = int((time.time() - fetch_start) * 1000)

    if not data:
        _log(batch_log, 'WARNING', 'No Data', 'Call analysis API returned empty response',
             sub_type='Call Analysis', duration_ms=fetch_ms)
        return 0

    _log(batch_log, 'INFO', 'API Fetch',
         f'Received call analysis in {fetch_ms}ms — answered={safe_int(data.get("answered_calls"))}, '
         f'missed={safe_int(data.get("missed_calls"))}, '
         f'never_attended={safe_int(data.get("never_attended"))}, '
         f'not_picked_up={safe_int(data.get("not_picked_up_by_client"))}',
         sub_type='Call Analysis', duration_ms=fetch_ms)

    # Clear existing data
    deleted = CallAnalysis.objects.filter(token=token).delete()
    _log(batch_log, 'DEBUG', 'DB Clear', f'Cleared {deleted[0]} existing call analysis records',
         sub_type='Call Analysis')

    # Create new analysis
    save_start = time.time()
    CallAnalysis.objects.create(
        token=token,
        raw_data=data,
        answered_calls=safe_int(data.get('answered_calls')),
        missed_calls=safe_int(data.get('missed_calls')),
        rejected_calls=safe_int(data.get('rejected_calls')),
        busy_calls=safe_int(data.get('busy_calls')),
        never_attended=safe_int(data.get('never_attended')),
        not_picked_up_by_client=safe_int(data.get('not_picked_up_by_client')),
        total_talk_time_seconds=safe_int(data.get('total_talk_time')),
        avg_talk_time_seconds=safe_float(data.get('avg_talk_time')),
    )
    save_ms = int((time.time() - save_start) * 1000)
    _log(batch_log, 'DEBUG', 'DB Save', f'Saved call analysis record in {save_ms}ms',
         sub_type='Call Analysis', duration_ms=save_ms)

    return 1


def sync_never_attended(client: CallyzerAPIClient, token: CallyzerToken,
                       call_from: int, call_to: int, batch_log=None) -> int:
    """Sync Never Attended Calls report"""
    _log(batch_log, 'DEBUG', 'API Fetch', 'Fetching never-attended calls (paginated)', sub_type='Never Attended')

    fetch_start = time.time()
    records = client.fetch_all_paginated(
        client.get_never_attended,
        call_from,
        call_to
    )
    fetch_ms = int((time.time() - fetch_start) * 1000)

    if not records:
        _log(batch_log, 'INFO', 'No Data', 'No never-attended call records found',
             sub_type='Never Attended', duration_ms=fetch_ms)
        return 0

    _log(batch_log, 'INFO', 'API Fetch', f'Fetched {len(records)} never-attended records in {fetch_ms}ms',
         sub_type='Never Attended', duration_ms=fetch_ms)

    # Clear existing data
    deleted = NeverAttendedCall.objects.filter(token=token).delete()
    _log(batch_log, 'DEBUG', 'DB Clear', f'Cleared {deleted[0]} existing never-attended records',
         sub_type='Never Attended')

    # Batch create new records
    calls = []
    parse_errors = 0
    for record in records:
        try:
            call_log = parse_call_logs(record.get('call_logs'))
            calls.append(NeverAttendedCall(
                token=token,
                raw_data=record,
                emp_name=safe_str(record.get('emp_name')),
                emp_id=safe_str(record.get('emp_id')),
                client_name=safe_str(record.get('client_name')),
                client_number=safe_str(record.get('client_number')),
                call_type=safe_str(call_log.get('call_type')) if call_log else '',
                call_direction=safe_str(call_log.get('call_direction')) if call_log else '',
                call_status=safe_str(call_log.get('call_status')) if call_log else '',
                call_date=extract_call_date(call_log) or timezone.now().date(),
                call_time=extract_call_time(call_log) or timezone.now().time(),
                call_duration_seconds=safe_int(call_log.get('duration')) if call_log else 0,
            ))
        except Exception as e:
            parse_errors += 1
            logger.error(f"[Callyzer] Error parsing never-attended record: {e}")
            _log(batch_log, 'ERROR', 'Parse Error',
                 f"Failed to parse never-attended record for {record.get('client_number', 'unknown')}: {e}",
                 sub_type='Never Attended')

    if parse_errors:
        _log(batch_log, 'WARNING', 'Parse Errors',
             f'{parse_errors} never-attended records failed to parse', sub_type='Never Attended')

    save_start = time.time()
    NeverAttendedCall.objects.bulk_create(calls, batch_size=500)
    save_ms = int((time.time() - save_start) * 1000)
    _log(batch_log, 'DEBUG', 'DB Save',
         f'Bulk-created {len(calls)} never-attended records in {save_ms}ms',
         sub_type='Never Attended', duration_ms=save_ms)

    return len(calls)


def sync_not_picked_up(client: CallyzerAPIClient, token: CallyzerToken,
                      call_from: int, call_to: int, batch_log=None) -> int:
    """Sync Not Picked Up By Client report"""
    _log(batch_log, 'DEBUG', 'API Fetch', 'Fetching not-picked-up calls (paginated)', sub_type='Not Picked Up')

    fetch_start = time.time()
    records = client.fetch_all_paginated(
        client.get_not_picked_up,
        call_from,
        call_to
    )
    fetch_ms = int((time.time() - fetch_start) * 1000)

    if not records:
        _log(batch_log, 'INFO', 'No Data', 'No not-picked-up call records found',
             sub_type='Not Picked Up', duration_ms=fetch_ms)
        return 0

    _log(batch_log, 'INFO', 'API Fetch', f'Fetched {len(records)} not-picked-up records in {fetch_ms}ms',
         sub_type='Not Picked Up', duration_ms=fetch_ms)

    # Clear existing data
    deleted = NotPickedUpCall.objects.filter(token=token).delete()
    _log(batch_log, 'DEBUG', 'DB Clear', f'Cleared {deleted[0]} existing not-picked-up records',
         sub_type='Not Picked Up')

    # Batch create new records
    calls = []
    parse_errors = 0
    for record in records:
        try:
            call_log = parse_call_logs(record.get('call_logs'))
            calls.append(NotPickedUpCall(
                token=token,
                raw_data=record,
                emp_name=safe_str(record.get('emp_name')),
                emp_id=safe_str(record.get('emp_id')),
                client_name=safe_str(record.get('client_name')),
                client_number=safe_str(record.get('client_number')),
                call_type=safe_str(call_log.get('call_type')) if call_log else '',
                call_direction=safe_str(call_log.get('call_direction')) if call_log else '',
                call_status=safe_str(call_log.get('call_status')) if call_log else '',
                call_date=extract_call_date(call_log) or timezone.now().date(),
                call_time=extract_call_time(call_log) or timezone.now().time(),
                call_duration_seconds=safe_int(call_log.get('duration')) if call_log else 0,
            ))
        except Exception as e:
            parse_errors += 1
            logger.error(f"[Callyzer] Error parsing not-picked-up record: {e}")
            _log(batch_log, 'ERROR', 'Parse Error',
                 f"Failed to parse not-picked-up record for {record.get('client_number', 'unknown')}: {e}",
                 sub_type='Not Picked Up')

    if parse_errors:
        _log(batch_log, 'WARNING', 'Parse Errors',
             f'{parse_errors} not-picked-up records failed to parse', sub_type='Not Picked Up')

    save_start = time.time()
    NotPickedUpCall.objects.bulk_create(calls, batch_size=500)
    save_ms = int((time.time() - save_start) * 1000)
    _log(batch_log, 'DEBUG', 'DB Save',
         f'Bulk-created {len(calls)} not-picked-up records in {save_ms}ms',
         sub_type='Not Picked Up', duration_ms=save_ms)

    return len(calls)


def sync_unique_clients(client: CallyzerAPIClient, token: CallyzerToken,
                       call_from: int, call_to: int, batch_log=None) -> int:
    """Sync Unique Clients report"""
    _log(batch_log, 'DEBUG', 'API Fetch', 'Fetching unique clients (paginated)', sub_type='Unique Clients')

    fetch_start = time.time()
    records = client.fetch_all_paginated(
        client.get_unique_clients,
        call_from,
        call_to
    )
    fetch_ms = int((time.time() - fetch_start) * 1000)

    if not records:
        _log(batch_log, 'INFO', 'No Data', 'No unique client records found',
             sub_type='Unique Clients', duration_ms=fetch_ms)
        return 0

    _log(batch_log, 'INFO', 'API Fetch', f'Fetched {len(records)} unique client records in {fetch_ms}ms',
         sub_type='Unique Clients', duration_ms=fetch_ms)

    # Clear existing data
    deleted = UniqueClient.objects.filter(token=token).delete()
    _log(batch_log, 'DEBUG', 'DB Clear', f'Cleared {deleted[0]} existing unique client records',
         sub_type='Unique Clients')

    # Batch create new records
    clients = []
    parse_errors = 0
    for record in records:
        try:
            # Parse dates
            first_call = record.get('first_call_date')
            last_call = record.get('last_call_date')

            if isinstance(first_call, str):
                try:
                    first_call = datetime.strptime(first_call, '%Y-%m-%d').date()
                except Exception as e:
                    logger.warning(f"[Callyzer] Could not parse first_call_date '{first_call}': {e}")
                    first_call = None

            if isinstance(last_call, str):
                try:
                    last_call = datetime.strptime(last_call, '%Y-%m-%d').date()
                except Exception as e:
                    logger.warning(f"[Callyzer] Could not parse last_call_date '{last_call}': {e}")
                    last_call = None

            clients.append(UniqueClient(
                token=token,
                raw_data=record,
                client_name=safe_str(record.get('client_name')),
                client_number=safe_str(record.get('client_number')),
                total_calls=safe_int(record.get('total_calls')),
                answered_calls=safe_int(record.get('answered_calls')),
                missed_calls=safe_int(record.get('missed_calls')),
                outbound_calls=safe_int(record.get('outbound_calls')),
                inbound_calls=safe_int(record.get('inbound_calls')),
                first_call_date=first_call,
                last_call_date=last_call,
            ))
        except Exception as e:
            parse_errors += 1
            logger.error(f"[Callyzer] Error parsing unique client record: {e}")
            _log(batch_log, 'ERROR', 'Parse Error',
                 f"Failed to parse unique client record for {record.get('client_number', 'unknown')}: {e}",
                 sub_type='Unique Clients')

    if parse_errors:
        _log(batch_log, 'WARNING', 'Parse Errors',
             f'{parse_errors} unique client records failed to parse', sub_type='Unique Clients')

    save_start = time.time()
    UniqueClient.objects.bulk_create(clients, batch_size=500, ignore_conflicts=True)
    save_ms = int((time.time() - save_start) * 1000)
    _log(batch_log, 'DEBUG', 'DB Save',
         f'Bulk-created {len(clients)} unique client records in {save_ms}ms',
         sub_type='Unique Clients', duration_ms=save_ms)

    return len(clients)


def sync_hourly_analytics(client: CallyzerAPIClient, token: CallyzerToken,
                         call_from: int, call_to: int, batch_log=None) -> int:
    """Sync Hourly Analytics report"""
    _log(batch_log, 'DEBUG', 'API Fetch', 'Fetching hourly analytics', sub_type='Hourly Analytics')

    fetch_start = time.time()
    records = client.get_hourly_analytics(call_from, call_to)
    fetch_ms = int((time.time() - fetch_start) * 1000)

    if not records:
        _log(batch_log, 'INFO', 'No Data', 'No hourly analytics records found',
             sub_type='Hourly Analytics', duration_ms=fetch_ms)
        return 0

    _log(batch_log, 'INFO', 'API Fetch', f'Fetched {len(records)} hourly analytics records in {fetch_ms}ms',
         sub_type='Hourly Analytics', duration_ms=fetch_ms)

    # Clear existing data
    deleted = HourlyAnalytic.objects.filter(token=token).delete()
    _log(batch_log, 'DEBUG', 'DB Clear', f'Cleared {deleted[0]} existing hourly analytics records',
         sub_type='Hourly Analytics')

    # Batch create new records
    analytics = []
    parse_errors = 0
    for record in records:
        try:
            analytics.append(HourlyAnalytic(
                token=token,
                raw_data=record,
                hour=safe_int(record.get('hour')),
                total_calls=safe_int(record.get('total_calls')),
                answered_calls=safe_int(record.get('answered_calls')),
                missed_calls=safe_int(record.get('missed_calls')),
                total_duration_seconds=safe_int(record.get('total_duration')),
                avg_duration_seconds=safe_float(record.get('avg_duration')),
            ))
        except Exception as e:
            parse_errors += 1
            logger.error(f"[Callyzer] Error parsing hourly analytics record hour={record.get('hour')}: {e}")
            _log(batch_log, 'ERROR', 'Parse Error',
                 f"Failed to parse hourly analytics record hour={record.get('hour')}: {e}",
                 sub_type='Hourly Analytics')

    if parse_errors:
        _log(batch_log, 'WARNING', 'Parse Errors',
             f'{parse_errors} hourly analytics records failed to parse', sub_type='Hourly Analytics')

    save_start = time.time()
    HourlyAnalytic.objects.bulk_create(analytics, batch_size=500, ignore_conflicts=True)
    save_ms = int((time.time() - save_start) * 1000)
    _log(batch_log, 'DEBUG', 'DB Save',
         f'Bulk-created {len(analytics)} hourly analytics records in {save_ms}ms',
         sub_type='Hourly Analytics', duration_ms=save_ms)

    return len(analytics)


def sync_daily_analytics(client: CallyzerAPIClient, token: CallyzerToken,
                        call_from: int, call_to: int, batch_log=None) -> int:
    """Sync Daily Analytics report"""
    _log(batch_log, 'DEBUG', 'API Fetch', 'Fetching daily analytics', sub_type='Daily Analytics')

    fetch_start = time.time()
    records = client.get_daily_analytics(call_from, call_to)
    fetch_ms = int((time.time() - fetch_start) * 1000)

    if not records:
        _log(batch_log, 'INFO', 'No Data', 'No daily analytics records found',
             sub_type='Daily Analytics', duration_ms=fetch_ms)
        return 0

    _log(batch_log, 'INFO', 'API Fetch', f'Fetched {len(records)} daily analytics records in {fetch_ms}ms',
         sub_type='Daily Analytics', duration_ms=fetch_ms)

    # Clear existing data
    deleted = DailyAnalytic.objects.filter(token=token).delete()
    _log(batch_log, 'DEBUG', 'DB Clear', f'Cleared {deleted[0]} existing daily analytics records',
         sub_type='Daily Analytics')

    # Batch create new records
    analytics = []
    skipped = 0
    parse_errors = 0
    for record in records:
        try:
            date_str = record.get('date')
            date_obj = None

            if isinstance(date_str, str):
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                except Exception as e:
                    logger.warning(f"[Callyzer] Could not parse daily analytics date '{date_str}': {e}")
                    _log(batch_log, 'WARNING', 'Date Parse Error',
                         f"Could not parse date '{date_str}': {e}", sub_type='Daily Analytics')

            if not date_obj:
                skipped += 1
                continue

            analytics.append(DailyAnalytic(
                token=token,
                raw_data=record,
                date=date_obj,
                total_calls=safe_int(record.get('total_calls')),
                answered_calls=safe_int(record.get('answered_calls')),
                missed_calls=safe_int(record.get('missed_calls')),
                total_duration_seconds=safe_int(record.get('total_duration')),
                avg_duration_seconds=safe_float(record.get('avg_duration')),
            ))
        except Exception as e:
            parse_errors += 1
            logger.error(f"[Callyzer] Error parsing daily analytics record date={record.get('date')}: {e}")
            _log(batch_log, 'ERROR', 'Parse Error',
                 f"Failed to parse daily analytics record date={record.get('date')}: {e}",
                 sub_type='Daily Analytics')

    if skipped:
        _log(batch_log, 'WARNING', 'Skipped Records',
             f'{skipped} daily analytics records skipped (invalid/missing date)', sub_type='Daily Analytics')
    if parse_errors:
        _log(batch_log, 'WARNING', 'Parse Errors',
             f'{parse_errors} daily analytics records failed to parse', sub_type='Daily Analytics')

    save_start = time.time()
    DailyAnalytic.objects.bulk_create(analytics, batch_size=500, ignore_conflicts=True)
    save_ms = int((time.time() - save_start) * 1000)
    _log(batch_log, 'DEBUG', 'DB Save',
         f'Bulk-created {len(analytics)} daily analytics records in {save_ms}ms '
         f'({skipped} skipped, {parse_errors} errors)',
         sub_type='Daily Analytics', duration_ms=save_ms)

    return len(analytics)


def sync_call_history(client: CallyzerAPIClient, token: CallyzerToken,
                     call_from: int, call_to: int, batch_log=None) -> int:
    """Sync Call History report"""
    _log(batch_log, 'INFO', 'Fetching Call History',
         'Fetching paginated call history (may take several minutes)...',
         sub_type='Call History')

    fetch_start = time.time()
    records = client.fetch_all_paginated(
        client.get_call_history,
        call_from,
        call_to,
        progress_callback=lambda page, total: _log(
            batch_log, 'INFO', 'Call History Progress',
            f'Fetched page {page} — {total} records so far',
            sub_type='Call History',
        ) if batch_log and page % 5 == 0 else None,
    )
    fetch_ms = int((time.time() - fetch_start) * 1000)

    if not records:
        _log(batch_log, 'INFO', 'No Data', 'No call history records found',
             sub_type='Call History', duration_ms=fetch_ms)
        return 0

    _log(batch_log, 'INFO', 'API Fetch',
         f'Fetched {len(records)} call history records in {fetch_ms}ms',
         sub_type='Call History', duration_ms=fetch_ms)

    # Clear existing data
    deleted = CallHistory.objects.filter(token=token).delete()
    _log(batch_log, 'DEBUG', 'DB Clear', f'Cleared {deleted[0]} existing call history records',
         sub_type='Call History')

    # Batch create new records
    calls = []
    parse_errors = 0
    date_fallbacks = 0
    for record in records:
        call_date_str = record.get('call_date')
        call_time_str = record.get('call_time')

        call_date = None
        call_time = None

        if isinstance(call_date_str, str):
            try:
                call_date = datetime.strptime(call_date_str, '%Y-%m-%d').date()
            except Exception as e:
                logger.warning(f"[Callyzer] Could not parse call_date '{call_date_str}': {e}")

        if isinstance(call_time_str, str):
            try:
                call_time = datetime.strptime(call_time_str, '%H:%M:%S').time()
            except Exception:
                try:
                    call_time = datetime.strptime(call_time_str, '%H:%M').time()
                except Exception as e:
                    logger.warning(f"[Callyzer] Could not parse call_time '{call_time_str}': {e}")

        if not call_date:
            date_fallbacks += 1
            call_date = timezone.now().date()
        if not call_time:
            call_time = timezone.now().time()

        try:
            calls.append(CallHistory(
                token=token,
                raw_data=record,
                emp_name=safe_str(record.get('emp_name')),
                emp_id=safe_str(record.get('emp_id')),
                emp_number=safe_str(record.get('emp_number')),
                client_name=safe_str(record.get('client_name')),
                client_number=safe_str(record.get('client_number')),
                call_type=safe_str(record.get('call_type')),
                call_direction=safe_str(record.get('call_direction')),
                call_date=call_date,
                call_time=call_time,
                duration_seconds=safe_int(record.get('duration')),
                call_status=safe_str(record.get('call_status')),
                recording_url=safe_str(record.get('call_recording_url')) if record.get('call_recording_url') else None,
            ))
        except Exception as e:
            parse_errors += 1
            logger.error(f"[Callyzer] Error building CallHistory record: {e}")
            _log(batch_log, 'ERROR', 'Parse Error',
                 f"Failed to build call history record for {record.get('client_number', 'unknown')}: {e}",
                 sub_type='Call History')

    if date_fallbacks:
        _log(batch_log, 'WARNING', 'Date Fallbacks',
             f'{date_fallbacks} call history records used today as fallback date',
             sub_type='Call History')
    if parse_errors:
        _log(batch_log, 'WARNING', 'Parse Errors',
             f'{parse_errors} call history records failed to build', sub_type='Call History')

    save_start = time.time()
    CallHistory.objects.bulk_create(calls, batch_size=500)
    save_ms = int((time.time() - save_start) * 1000)
    _log(batch_log, 'DEBUG', 'DB Save',
         f'Bulk-created {len(calls)} call history records in {save_ms}ms '
         f'({date_fallbacks} date fallbacks, {parse_errors} errors)',
         sub_type='Call History', duration_ms=save_ms)

    return len(calls)
