"""
Gmail Leads Sync Module
Core sync logic for fetching CONTACT_US and SAAS_INVENTORY lead emails
Follows Bigin integration pattern
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List
from django.utils import timezone
from django.db import transaction

from .models import (
    GmailLeadsToken,
    LeadEmail,
    LastProcessedTime,
    DuplicateCheckCache
)
from integrations.models import SyncLog
from integrations.sync_logger import SyncLogHandler
from .utils.encryption import EncryptionUtils
from .utils.gmail_auth import get_gmail_service, refresh_token
from .utils.gmail_api import (
    fetch_messages_list,
    fetch_message,
    parse_gmail_message
)
from .utils.parsers import parse_email_body
from .sync_progress import SyncProgressTracker

logger = logging.getLogger(__name__)

# Thread-local storage for batch log context (thread-safe for concurrent syncs)
_thread_local = threading.local()


def _gl_log(level, operation, message='', sub_type='', duration_ms=None, **_ignored):
    """Helper: log a gmail_leads operation to unified SyncLog."""
    batch_log = getattr(_thread_local, 'batch_log', None)
    sync_type = getattr(_thread_local, 'sync_type', 'gmail_leads_incremental')
    if batch_log is None:
        logger.warning(f"[Gmail Leads] _gl_log called but batch_log is None! Operation: {operation}")
        return  # Skip logging if no batch context

    SyncLog.log(
        integration='gmail_leads',
        sync_type=sync_type,
        level=level,
        operation=operation,
        message=message,
        sub_type=sub_type,
        duration_ms=duration_ms,
        batch=batch_log,
    )


def retry_with_exponential_backoff(func, *args, max_retries=None, **kwargs):
    """
    Retry a function with exponential backoff

    Args:
        func: Function to retry
        *args: Positional arguments for func
        max_retries: Maximum retry attempts (defaults to CONFIG['MAX_RETRIES'])
        **kwargs: Keyword arguments for func

    Returns:
        Function result

    Raises:
        Last exception if all retries fail
    """
    if max_retries is None:
        max_retries = CONFIG['MAX_RETRIES']

    last_exception = None

    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:  # Don't sleep on last attempt
                delay = CONFIG['RETRY_BASE_DELAY'] * (2 ** attempt)  # Exponential: 2s, 4s, 8s
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}: {e}. Retrying in {delay}s...")
                _gl_log('WARNING', 'API Retry',
                        f'{func.__name__} attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {delay}s...')
                time.sleep(delay)
            else:
                logger.error(f"All {max_retries} attempts failed for {func.__name__}: {e}")
                _gl_log('ERROR', 'API Retry Exhausted',
                        f'All {max_retries} attempts failed for {func.__name__}: {e}')

    raise last_exception


# Configuration
CONFIG = {
    "LEAD_TYPES": [
        {
            "type": "CONTACT_US",
            # Use key words only - Gmail search doesn't support quotes in subject queries well
            "subject": 'Godamwale Contact us form submission',
            "max_emails_per_sync": 100
        },
        {
            "type": "SAAS_INVENTORY",
            # Use key words only
            "subject": 'Inventory Management Inciflo LEAD',
            "max_emails_per_sync": 100
        }
    ],
    "BATCH_SIZE": 20,  # Process emails in batches
    "HISTORY_SYNC_DAYS": 3650,  # Full sync lookback period (10 years to fetch all available data)
    "MAX_RETRIES": 3,  # Maximum retry attempts for API calls
    "RETRY_BASE_DELAY": 2,  # Base delay in seconds for exponential backoff
}


def get_valid_token_data(gmail_token: GmailLeadsToken) -> Dict:
    """
    Get decrypted and validated token data

    Args:
        gmail_token: GmailLeadsToken object

    Returns:
        dict: Decrypted token data

    Raises:
        ValueError: If token is invalid or decryption fails
    """
    if not gmail_token.is_active:
        raise ValueError(f"Token for {gmail_token.email_account} is inactive")

    token_data = EncryptionUtils.decrypt(gmail_token.encrypted_token_data)

    if not token_data:
        raise ValueError(f"Failed to decrypt token for {gmail_token.email_account}")

    # Check if token needs refresh
    if token_data.get('expiry'):
        try:
            expiry_dt = datetime.fromisoformat(token_data['expiry'].replace('Z', '+00:00'))
            if expiry_dt < datetime.now(expiry_dt.tzinfo):
                logger.info(f"Token expired for {gmail_token.email_account}, refreshing...")
                _gl_log('WARNING', 'Token Refresh',
                        f'Token for {gmail_token.email_account} expired at {expiry_dt.isoformat()}, refreshing...')
                token_data = refresh_token(token_data)

                # Update stored token
                gmail_token.encrypted_token_data = EncryptionUtils.encrypt(token_data)
                gmail_token.save(update_fields=['encrypted_token_data'])
                _gl_log('SUCCESS', 'Token Refresh',
                        f'Token for {gmail_token.email_account} refreshed successfully')

        except Exception as e:
            logger.warning(f"Could not check token expiry: {e}")
            _gl_log('WARNING', 'Token Expiry Check',
                    f'Could not check/refresh token for {gmail_token.email_account}: {e}')

    return token_data


def sync_lead_type(
    service,
    gmail_token: GmailLeadsToken,
    lead_config: Dict,
    force_full: bool = False,
    tracker=None
) -> Dict:
    """
    Sync emails for a single lead type

    Args:
        service: Gmail API service
        gmail_token: GmailLeadsToken object
        lead_config: Lead type configuration dict
        force_full: If True, sync from history; if False, incremental sync

    Returns:
        dict with sync statistics
    """
    lead_type = lead_config['type']
    subject_query = lead_config['subject']
    # No limit - fetch ALL emails for both full and incremental syncs
    max_emails = 999999

    start_time = timezone.now()

    _gl_log(
        'INFO',
        'Lead Type Start',
        f'Processing for: {lead_type}, Subject: "{subject_query}"',
        sub_type=lead_type
    )

    stats = {
        'lead_type': lead_type,
        'checked': 0,
        'created': 0,
        'duplicates': 0,
        'failed': 0,
        'api_calls': 0
    }

    try:
        # Determine sync type and query date
        if force_full:
            # Full sync: Sync from very beginning (Gmail API supports after:1970/01/01)
            # Use epoch start date to get absolutely everything
            query_after_date = timezone.make_aware(datetime(1970, 1, 1))
            _gl_log(
                'INFO',
                'Full Sync',
                f'For {lead_type}, syncing ALL available historical data (from the beginning)',
                sub_type=lead_type
            )

            # Get or create LPT record but don't use it for querying
            lpt_record, _ = LastProcessedTime.objects.get_or_create(
                account_link=gmail_token,
                lead_type=lead_type,
                defaults={'last_processed_time': query_after_date}
            )
            # For full sync, use query_after_date as last_processed_time for filtering
            last_processed_time = query_after_date
        else:
            # Incremental sync: Use Last Processed Time (LPT)
            lpt_record, created = LastProcessedTime.objects.get_or_create(
                account_link=gmail_token,
                lead_type=lead_type,
                defaults={'last_processed_time': timezone.now() - timedelta(days=CONFIG['HISTORY_SYNC_DAYS'])}
            )

            last_processed_time = lpt_record.last_processed_time

            if created:
                # First time sync: Start from HISTORY_SYNC_DAYS ago
                query_after_date = last_processed_time
                _gl_log(
                    'INFO',
                    'Initial Sync',
                    f'For {lead_type}, first sync from {query_after_date.date()}',
                    sub_type=lead_type
                )
            else:
                # Incremental sync: Start from LPT
                query_after_date = last_processed_time
                _gl_log(
                    'INFO',
                    'Incremental Sync',
                    f'For {lead_type}, syncing from LPT: {last_processed_time.isoformat()}',
                    sub_type=lead_type
                )

        # Build Gmail query
        # Format: subject:(words) after:epoch_timestamp
        # Note: Gmail doesn't support nested quotes in subject:"..." queries
        # So we use subject:(Godamwale Contact) which matches emails containing those words
        epoch_timestamp = int(query_after_date.timestamp())

        # Gmail API doesn't accept after:0 (returns 0 results), use after:1 instead
        if epoch_timestamp == 0:
            epoch_timestamp = 1

        # Remove quotes from subject and use parentheses instead for word matching
        # This handles subjects like: Godamwale "Contact us form submission from website"
        subject_words = subject_query.replace('"', '').strip()
        gmail_query = f'subject:({subject_words}) after:{epoch_timestamp}'

        _gl_log(
            'DEBUG',
            'GMAIL_QUERY_RAW',
            f'Constructed Gmail Query: [{gmail_query}]',
            sub_type=lead_type
        )

        # Fetch message list
        page_token = None
        all_message_ids = []

        while True:
            _gl_log(
                'INFO',
                'Gmail API',
                f'Req list for "{subject_query}" (Page: {"Yes" if page_token else "No"})',
                sub_type=lead_type
            )

            api_start = timezone.now()
            result = retry_with_exponential_backoff(
                fetch_messages_list,
                service,
                gmail_query,
                max_results=500,
                page_token=page_token
            )
            api_duration = int((timezone.now() - api_start).total_seconds() * 1000)

            stats['api_calls'] += 1

            _gl_log(
                'DEBUG',
                'Quota',
                f'Used 1 GMAIL_API_QUERIES (List Messages Call). Total {stats["api_calls"]}',
                sub_type=lead_type,
                duration_ms=api_duration
            )

            messages = result.get('messages', [])
            all_message_ids.extend([msg['id'] for msg in messages])

            # Check for next page
            page_token = result.get('nextPageToken')
            if not page_token or len(all_message_ids) >= max_emails:
                break

        if not all_message_ids:
            _gl_log(
                'INFO',
                'No New Emails',
                f'No messages found for {lead_type}',
                sub_type=lead_type
            )
            return stats

        # Limit to max_emails
        all_message_ids = all_message_ids[:max_emails]

        # Process in batches
        batch_size = CONFIG['BATCH_SIZE']
        batches = [all_message_ids[i:i + batch_size] for i in range(0, len(all_message_ids), batch_size)]

        # Initialize newest_datetime to track the most recent email processed
        newest_datetime = query_after_date

        for batch_idx, batch_ids in enumerate(batches):
            batch_start = timezone.now()
            batch_number = batch_idx + 1
            total_batches = len(batches)

            _gl_log(
                'INFO',
                'Batch Start',
                f'Processing batch {batch_number}/{total_batches} with {len(batch_ids)} message IDs',
                sub_type=lead_type
            )

            batch_stats = {
                'batch_number': batch_number,
                'checked': 0,
                'created': 0,
                'duplicates': 0,
                'excluded': 0,
                'failed': 0
            }

            for message_id in batch_ids:
                try:
                    stats['checked'] += 1
                    batch_stats['checked'] += 1

                    # Update frontend tracker every 5 messages
                    if tracker and stats['checked'] % 5 == 0:
                        tracker.update(
                            message=f'Processing {lead_type}: {stats["checked"]}/{len(all_message_ids)} emails checked, {stats["created"]} leads created',
                            emails_processed=stats['checked'],
                            leads_created=stats['created']
                        )

                    # Fetch full message with retry logic
                    api_start = timezone.now()
                    message = retry_with_exponential_backoff(
                        fetch_message,
                        service,
                        message_id,
                        format='full'
                    )
                    api_duration = int((timezone.now() - api_start).total_seconds() * 1000)

                    stats['api_calls'] += 1

                    _gl_log(
                        'DEBUG',
                        'Quota',
                        f'Used 1 GMAIL_API_QUERIES (Get Message Call). Total {stats["api_calls"]}',
                        sub_type=lead_type,
                        duration_ms=api_duration
                    )

                    if not message:
                        stats['failed'] += 1
                        batch_stats['failed'] += 1
                        continue

                    # Parse message
                    parsed_data = parse_gmail_message(message, lead_type)

                    # Check excluded emails
                    if gmail_token.is_email_excluded(parsed_data['from_email']) or \
                       gmail_token.is_email_excluded(parsed_data['reply_to_email']):
                        batch_stats['excluded'] += 1
                        _gl_log(
                            'DEBUG',
                            'Excluded Email',
                            f"Skipping ID {message_id}: Email is in excluded list",
                            sub_type=lead_type
                        )
                        continue

                    # Check if already processed (date-based filtering)
                    # Skip this check for full syncs - we want ALL emails
                    if not force_full and parsed_data['datetime'] <= last_processed_time:
                        _gl_log(
                            'DEBUG',
                            'Filtering',
                            f"Skipping ID {message_id} ({lead_type}): "
                            f"Date ({parsed_data['datetime'].isoformat()}) <= Stored LPT ({last_processed_time.isoformat()}).",
                            sub_type=lead_type
                        )
                        continue

                    # Parse form data from body
                    form_data = parse_email_body(lead_type, parsed_data['body_text'], message_id)

                    # Skip if no email was extracted (parser failed)
                    if not form_data.get('form_email'):
                        stats['failed'] += 1
                        batch_stats['failed'] += 1
                        _gl_log(
                            'WARNING',
                            'Parse Failed',
                            f'Skipping ID {message_id}: No email could be extracted from body',
                            sub_type=lead_type
                        )
                        continue

                    # Check for duplicates
                    duplicate_key = f"{form_data['form_email']}|{parsed_data['date'].strftime('%m/%d/%Y')}|{form_data['form_name'].lower()}"

                    if DuplicateCheckCache.objects.filter(
                        lead_type=lead_type,
                        cache_key=duplicate_key
                    ).exists():
                        stats['duplicates'] += 1
                        batch_stats['duplicates'] += 1
                        _gl_log(
                            'DEBUG',
                            'DupeCheck',
                            f'Duplicate detected: {duplicate_key}',
                            sub_type=lead_type
                        )
                        continue

                    # Create LeadEmail
                    with transaction.atomic():
                        lead_email = LeadEmail.objects.create(
                            account_link=gmail_token,
                            lead_type=lead_type,
                            month_year=parsed_data['datetime'].strftime('%B %Y'),
                            from_name=parsed_data['from_name'],
                            from_email=parsed_data['from_email'],
                            reply_to_name=parsed_data['reply_to_name'],
                            reply_to_email=parsed_data['reply_to_email'],
                            to_addresses=parsed_data['to_addresses'],
                            utm_term=parsed_data['utm_term'],
                            utm_campaign=parsed_data['utm_campaign'],
                            utm_medium=parsed_data['utm_medium'],
                            utm_content=parsed_data['utm_content'],
                            gclid=form_data.get('gclid', ''),
                            subject=parsed_data['subject'],
                            date_received=parsed_data['date'],
                            time_received=parsed_data['time'],
                            datetime_received=parsed_data['datetime'],
                            form_name=form_data['form_name'],
                            form_email=form_data['form_email'],
                            form_phone=form_data['form_phone'],
                            form_address=form_data.get('form_address', ''),
                            form_company_name=form_data.get('form_company_name', ''),
                            message_preview=form_data['message_preview'],
                            full_message_body=parsed_data.get('full_message_body', ''),
                            message_id=message_id
                        )

                        # Add to duplicate cache
                        DuplicateCheckCache.objects.create(
                            account_link=gmail_token,
                            lead_type=lead_type,
                            cache_key=duplicate_key,
                            message_id=message_id
                        )

                        stats['created'] += 1
                        batch_stats['created'] += 1

                        # Track newest datetime
                        if parsed_data['datetime'] > newest_datetime:
                            newest_datetime = parsed_data['datetime']

                        _gl_log(
                            'SUCCESS',
                            'Message Process',
                            f'Processed ID: {message_id} ({lead_type}).',
                            sub_type=lead_type
                        )

                except Exception as e:
                    stats['failed'] += 1
                    batch_stats['failed'] += 1
                    logger.error(f"Failed to process message {message_id} ({lead_type}): {e}")
                    _gl_log(
                        'ERROR',
                        'Message Process',
                        f'Failed ID {message_id}: {str(e)}',
                        sub_type=lead_type
                    )

            # Log batch completion with detailed stats
            batch_duration = int((timezone.now() - batch_start).total_seconds() * 1000)
            _gl_log(
                'INFO',
                'Batch End',
                f'Batch {batch_number}/{total_batches} complete - '
                f'Checked: {batch_stats["checked"]}, Created: {batch_stats["created"]}, '
                f'Duplicates: {batch_stats["duplicates"]}, Excluded: {batch_stats["excluded"]}, '
                f'Failed: {batch_stats["failed"]}',
                sub_type=lead_type,
                duration_ms=batch_duration
            )

        # Update Last Processed Time to the newest email datetime processed
        if newest_datetime > lpt_record.last_processed_time:
            lpt_record.last_processed_time = newest_datetime
            lpt_record.save()

            _gl_log(
                'INFO',
                'Time Update',
                f'Updated LPT for {lead_type}: {newest_datetime.isoformat()}',
                sub_type=lead_type
            )

        # Log summary
        duration = int((timezone.now() - start_time).total_seconds() * 1000)
        _gl_log(
            'INFO',
            'Lead Type Summary',
            f'{lead_type} - Checked: {stats["checked"]}, Created: {stats["created"]}, '
            f'Duplicates: {stats["duplicates"]}, Failed: {stats["failed"]}',
            sub_type=lead_type,
            duration_ms=duration
        )

    except Exception as e:
        logger.error(f"Failed to sync {lead_type}: {e}")
        _gl_log(
            'ERROR',
            'Lead Type Sync',
            f'Failed to sync {lead_type}: {str(e)}',
            sub_type=lead_type
        )
        raise

    return stats


def sync_gmail_leads_account(gmail_token: GmailLeadsToken, force_full: bool = False, batch_log_id: int = None, scheduled_job_id=None) -> Dict:
    """
    Sync all lead types for a single Gmail account

    Args:
        gmail_token: GmailLeadsToken object
        force_full: If True, sync from history; if False, incremental sync
        batch_log_id: Optional pre-created batch log ID (if None, creates new one)

    Returns:
        dict with overall sync statistics
    """
    start_time = timezone.now()

    # Initialize progress tracker
    sync_type = 'full' if force_full else 'incremental'
    tracker = SyncProgressTracker(token_id=gmail_token.id, sync_type=sync_type)
    tracker.start()

    # Set up unified SyncLog batch entry (thread-local vars used by _gl_log)
    _thread_local.sync_type = 'gmail_leads_full' if force_full else 'gmail_leads_incremental'

    if batch_log_id:
        # Reuse existing batch log created by view
        _thread_local.batch_log = SyncLog.objects.get(id=batch_log_id)
    else:
        # Create new batch log with stale sync cleanup
        STALE_THRESHOLD_MINUTES = 10
        with transaction.atomic():
            existing_sync = SyncLog.objects.select_for_update().filter(
                integration='gmail_leads',
                log_kind='batch',
                status='running'
            ).order_by('-started_at').first()

            if existing_sync:
                stale_cutoff = timezone.now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
                if existing_sync.last_updated < stale_cutoff:
                    logger.warning(f"[Gmail Leads Sync] Stale sync {existing_sync.id} detected, marking as stopped")
                    existing_sync.status = 'stopped'
                    existing_sync.error_message = 'Marked as stopped due to staleness (no updates for 10 minutes)'
                    existing_sync.save(update_fields=['status', 'error_message', 'last_updated'])
                else:
                    raise RuntimeError(f"Another sync is already running (started {existing_sync.started_at})")

            # Create new batch log
            _thread_local.batch_log = SyncLog.objects.create(
                integration='gmail_leads',
                sync_type=_thread_local.sync_type,
                log_kind='batch',
                status='running',
                triggered_by_user=gmail_token.email_account,
                scheduled_job_id=scheduled_job_id,
            )

    # Full sync: delete existing data atomically before starting
    if force_full:
        tracker.update(message='🗑️ Clearing existing data for fresh start...', progress_percentage=3)
        with transaction.atomic():
            deleted_leads = LeadEmail.objects.filter(account_link=gmail_token).delete()
            deleted_cache = DuplicateCheckCache.objects.filter(account_link=gmail_token).delete()
            deleted_lpt = LastProcessedTime.objects.filter(account_link=gmail_token).delete()
        logger.info(f"[Full Sync] Cleared {deleted_leads[0]} leads, {deleted_cache[0]} cache, {deleted_lpt[0]} LPT for {gmail_token.email_account}")
        _gl_log(
            'INFO',
            'Full Sync',
            f'Cleared all existing data: {deleted_leads[0]} leads, {deleted_cache[0]} cache entries, {deleted_lpt[0]} LPT records'
        )

    tracker.update(message='🔐 Authenticating with Gmail API...', progress_percentage=5)
    _gl_log(
        'INFO',
        'Job Start',
        f'Lead sync initiated for {gmail_token.email_account} at {start_time.isoformat()}.'
    )

    overall_stats = {
        'account': gmail_token.email_account,
        'lead_types': {},
        'total_created': 0,
        'total_api_calls': 0,
        'status': 'success'
    }

    _sync_log_handler = SyncLogHandler(_thread_local.batch_log, integration='gmail_leads', sync_type=_thread_local.sync_type,
                                       loggers=['integrations.gmail_leads'])
    _sync_log_handler._attach()
    try:
        # Get valid token
        token_data = get_valid_token_data(gmail_token)
        tracker.update(message='📡 Fetching message list from Gmail...', progress_percentage=15)

        # Create Gmail service
        service = get_gmail_service(token_data)
        if not service:
            raise ValueError(f"Failed to create Gmail service for {gmail_token.email_account}")

        tracker.update(message='✅ Gmail API connection established', progress_percentage=25)

        _gl_log(
            'INFO',
            'Gmail API Init',
            'Wrapper initialized.'
        )

        # Sync each lead type
        total_lead_types = len(CONFIG['LEAD_TYPES'])
        for idx, lead_config in enumerate(CONFIG['LEAD_TYPES']):
            # Check for stop request before each lead type
            if _thread_local.batch_log:
                _thread_local.batch_log.refresh_from_db(fields=['stop_requested'])
                if _thread_local.batch_log.stop_requested:
                    logger.info(f"[Gmail Leads] Sync {_thread_local.batch_log.id} stopped by user request before {lead_config['type']}")
                    _thread_local.batch_log.status = 'stopped'
                    _thread_local.batch_log.completed_at = timezone.now()
                    _thread_local.batch_log.duration_seconds = int((timezone.now() - _thread_local.batch_log.started_at).total_seconds())
                    _thread_local.batch_log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'last_updated'])
                    overall_stats['status'] = 'stopped'
                    return overall_stats
            try:
                lead_type_name = lead_config['type'].replace('_', ' ').title()
                tracker.update(
                    message=f'🔍 Scanning for {lead_type_name} leads...',
                    progress_percentage=30 + (idx * 30 / total_lead_types)
                )

                lead_stats = sync_lead_type(service, gmail_token, lead_config, force_full, tracker)

                overall_stats['lead_types'][lead_config['type']] = lead_stats
                overall_stats['total_created'] += lead_stats['created']
                overall_stats['total_api_calls'] += lead_stats['api_calls']

                # Update tracker with intermediate stats
                tracker.update(
                    message=f'✅ Processed {lead_type_name}: {lead_stats["created"]} new leads',
                    progress_percentage=30 + ((idx + 1) * 30 / total_lead_types),
                    emails_processed=lead_stats.get('checked', 0),
                    leads_created=overall_stats['total_created'],
                    contact_us=overall_stats['lead_types'].get('CONTACT_US', {}).get('created', 0),
                    saas_inventory=overall_stats['lead_types'].get('SAAS_INVENTORY', {}).get('created', 0)
                )

            except Exception as e:
                logger.error(f"Failed to sync {lead_config['type']}: {e}")
                overall_stats['status'] = 'partial_failure'
                tracker.update(message=f'⚠️ Warning: {lead_config["type"]} sync encountered an error')

        tracker.update(message='💾 Saving lead data to database...', progress_percentage=85)

        # Update last_sync_at
        gmail_token.last_sync_at = timezone.now()
        gmail_token.save(update_fields=['last_sync_at'])

        tracker.update(message='📊 Updating statistics...', progress_percentage=95)

        duration = int((timezone.now() - start_time).total_seconds() * 1000)
        _gl_log(
            'INFO',
            'Job Complete',
            f'Synced {overall_stats["total_created"]} leads using {overall_stats["total_api_calls"]} API calls.',
            duration_ms=duration
        )

        # Finalize batch log
        _thread_local.batch_log.status = 'completed'
        _thread_local.batch_log.completed_at = timezone.now()
        _thread_local.batch_log.duration_seconds = int(duration / 1000)
        _thread_local.batch_log.records_created = overall_stats['total_created']
        _thread_local.batch_log.total_records_synced = overall_stats.get('total_checked', 0)
        _thread_local.batch_log.errors_count = overall_stats.get('total_errors', 0)
        _thread_local.batch_log.overall_progress_percent = 100
        _thread_local.batch_log.api_calls_count = overall_stats.get('total_api_calls', 0)
        _thread_local.batch_log.save()

        # Complete tracker with final stats
        tracker.complete(
            success=True,
            message=f'✅ Sync completed! Found {overall_stats["total_created"]} new leads.',
            stats={
                'emails_processed': overall_stats.get('total_checked', 0),
                'leads_created': overall_stats['total_created'],
                'contact_us': overall_stats['lead_types'].get('CONTACT_US', {}).get('created', 0),
                'saas_inventory': overall_stats['lead_types'].get('SAAS_INVENTORY', {}).get('created', 0)
            }
        )

    except Exception as e:
        overall_stats['status'] = 'error'
        overall_stats['error'] = str(e)
        logger.error(f"Failed to sync account {gmail_token.email_account}: {e}")

        _gl_log(
            'ERROR',
            'Job Failed',
            f'Sync failed for {gmail_token.email_account}: {str(e)}'
        )

        # Finalize batch log as failed
        if _thread_local.batch_log:
            _thread_local.batch_log.status = 'failed'
            _thread_local.batch_log.error_message = str(e)
            _thread_local.batch_log.completed_at = timezone.now()
            _thread_local.batch_log.save()

        # Mark tracker as failed
        tracker.complete(
            success=False,
            message=f'❌ Sync failed: {str(e)}'
        )

    finally:
        _sync_log_handler._detach()

    return overall_stats


def sync_all_gmail_leads_accounts(force_full: bool = False, scheduled_job_id=None) -> Dict:
    """
    Sync all active Gmail Leads accounts

    Args:
        force_full: If True, sync from history; if False, incremental sync

    Returns:
        dict with overall statistics
    """
    start_time = timezone.now()
    logger.info(f"Starting sync for all Gmail Leads accounts (force_full={force_full})")

    _gl_log(
        'INFO',
        'All Accounts Start',
        f'Syncing all active Gmail Leads accounts at {start_time.isoformat()}.'
    )

    # Get all active tokens
    active_tokens = GmailLeadsToken.objects.filter(is_active=True)

    overall_stats = {
        'total_accounts': active_tokens.count(),
        'successful': 0,
        'failed': 0,
        'total_leads_created': 0,
        'accounts': []
    }

    for gmail_token in active_tokens:
        try:
            account_stats = sync_gmail_leads_account(gmail_token, force_full, scheduled_job_id=scheduled_job_id)

            if account_stats['status'] == 'success':
                overall_stats['successful'] += 1
            else:
                overall_stats['failed'] += 1

            overall_stats['total_leads_created'] += account_stats['total_created']
            overall_stats['accounts'].append(account_stats)

        except Exception as e:
            overall_stats['failed'] += 1
            logger.error(f"Failed to sync {gmail_token.email_account}: {e}")

    duration = int((timezone.now() - start_time).total_seconds() * 1000)
    _gl_log(
        'INFO',
        'All Accounts Complete',
        f'Synced {overall_stats["successful"]}/{overall_stats["total_accounts"]} accounts. '
        f'Total leads: {overall_stats["total_leads_created"]}',
        duration_ms=duration
    )

    logger.info(
        f"Sync complete: {overall_stats['successful']}/{overall_stats['total_accounts']} accounts, "
        f"{overall_stats['total_leads_created']} leads created"
    )

    return overall_stats


def sync_date_range(
    gmail_token: GmailLeadsToken,
    start_date: datetime,
    end_date: datetime
) -> Dict:
    """
    Sync emails for a specific date range

    Args:
        gmail_token: GmailLeadsToken object
        start_date: Start date for sync (inclusive)
        end_date: End date for sync (inclusive)

    Returns:
        dict with sync statistics
    """
    sync_start = timezone.now()

    _gl_log(
        'INFO',
        'Date Range Sync Start',
        f'Syncing date range {start_date.date()} to {end_date.date()} for {gmail_token.email_account}'
    )

    overall_stats = {
        'account': gmail_token.email_account,
        'start_date': start_date.date().isoformat(),
        'end_date': end_date.date().isoformat(),
        'lead_types': {},
        'total_created': 0,
        'total_api_calls': 0,
        'status': 'success'
    }

    try:
        # Get valid token
        token_data = get_valid_token_data(gmail_token)

        # Create Gmail service
        service = get_gmail_service(token_data)
        if not service:
            raise ValueError(f"Failed to create Gmail service for {gmail_token.email_account}")

        _gl_log(
            'INFO',
            'Gmail API Init',
            'Gmail service initialized for date range sync'
        )

        # Sync each lead type for the date range
        for lead_config in CONFIG['LEAD_TYPES']:
            lead_type = lead_config['type']
            subject_query = lead_config['subject']

            try:
                _gl_log(
                    'INFO',
                    'Date Range Lead Type',
                    f'Processing {lead_type} for date range',
                    sub_type=lead_type
                )

                # Build Gmail query with date range
                # Gmail uses epoch timestamps for after: and before:
                start_epoch = int(start_date.timestamp())
                end_epoch = int(end_date.timestamp())
                gmail_query = f'subject:"{subject_query}" after:{start_epoch} before:{end_epoch}'

                _gl_log(
                    'DEBUG',
                    'Date Range Query',
                    f'Query: [{gmail_query}]',
                    sub_type=lead_type
                )

                # Fetch messages
                page_token = None
                all_message_ids = []

                while True:
                    api_start = timezone.now()
                    result = retry_with_exponential_backoff(
                        fetch_messages_list,
                        service,
                        gmail_query,
                        max_results=500,
                        page_token=page_token
                    )
                    api_duration = int((timezone.now() - api_start).total_seconds() * 1000)

                    overall_stats['total_api_calls'] += 1

                    _gl_log(
                        'DEBUG',
                        'Quota',
                        f'List Messages API call - Total: {overall_stats["total_api_calls"]}',
                        sub_type=lead_type,
                        duration_ms=api_duration
                    )

                    messages = result.get('messages', [])
                    all_message_ids.extend([msg['id'] for msg in messages])

                    page_token = result.get('nextPageToken')
                    if not page_token:
                        break

                if not all_message_ids:
                    _gl_log(
                        'INFO',
                        'No Messages',
                        f'No messages found for {lead_type} in date range',
                        sub_type=lead_type
                    )
                    overall_stats['lead_types'][lead_type] = {
                        'checked': 0,
                        'created': 0,
                        'duplicates': 0,
                        'failed': 0
                    }
                    continue

                # Process messages
                lead_stats = {
                    'checked': 0,
                    'created': 0,
                    'duplicates': 0,
                    'excluded': 0,
                    'failed': 0
                }

                for message_id in all_message_ids:
                    try:
                        lead_stats['checked'] += 1

                        # Fetch message with retry
                        api_start = timezone.now()
                        message = retry_with_exponential_backoff(
                            fetch_message,
                            service,
                            message_id,
                            format='full'
                        )
                        api_duration = int((timezone.now() - api_start).total_seconds() * 1000)

                        overall_stats['total_api_calls'] += 1

                        if not message:
                            lead_stats['failed'] += 1
                            continue

                        # Parse message
                        parsed_data = parse_gmail_message(message, lead_type)

                        # Check excluded emails
                        if gmail_token.is_email_excluded(parsed_data['from_email']) or \
                           gmail_token.is_email_excluded(parsed_data['reply_to_email']):
                            lead_stats['excluded'] += 1
                            continue

                        # Parse form data
                        form_data = parse_email_body(lead_type, parsed_data['body_text'], message_id)

                        # Check for duplicates
                        duplicate_key = f"{form_data['form_email']}|{parsed_data['date'].strftime('%m/%d/%Y')}|{form_data['form_name'].lower()}"

                        if DuplicateCheckCache.objects.filter(
                            lead_type=lead_type,
                            cache_key=duplicate_key
                        ).exists():
                            lead_stats['duplicates'] += 1
                            continue

                        # Check if already exists by message_id
                        if LeadEmail.objects.filter(message_id=message_id).exists():
                            lead_stats['duplicates'] += 1
                            continue

                        # Create LeadEmail
                        with transaction.atomic():
                            LeadEmail.objects.create(
                                account_link=gmail_token,
                                lead_type=lead_type,
                                month_year=parsed_data['datetime'].strftime('%B %Y'),
                                from_name=parsed_data['from_name'],
                                from_email=parsed_data['from_email'],
                                reply_to_name=parsed_data['reply_to_name'],
                                reply_to_email=parsed_data['reply_to_email'],
                                to_addresses=parsed_data['to_addresses'],
                                utm_term=parsed_data['utm_term'],
                                utm_campaign=parsed_data['utm_campaign'],
                                utm_medium=parsed_data['utm_medium'],
                                utm_content=parsed_data['utm_content'],
                                subject=parsed_data['subject'],
                                date_received=parsed_data['date'],
                                time_received=parsed_data['time'],
                                datetime_received=parsed_data['datetime'],
                                form_name=form_data['form_name'],
                                form_email=form_data['form_email'],
                                form_phone=form_data['form_phone'],
                                form_address=form_data.get('form_address', ''),
                                form_company_name=form_data.get('form_company_name', ''),
                                message_preview=form_data['message_preview'],
                                full_message_body=parsed_data.get('full_message_body', ''),
                                message_id=message_id
                            )

                            # Add to duplicate cache
                            DuplicateCheckCache.objects.create(
                                account_link=gmail_token,
                                lead_type=lead_type,
                                cache_key=duplicate_key,
                                message_id=message_id
                            )

                            lead_stats['created'] += 1

                    except Exception as e:
                        lead_stats['failed'] += 1
                        logger.error(f"Failed to process message {message_id}: {e}")

                overall_stats['lead_types'][lead_type] = lead_stats
                overall_stats['total_created'] += lead_stats['created']

                _gl_log(
                    'INFO',
                    'Date Range Lead Summary',
                    f'{lead_type} - Created: {lead_stats["created"]}, Duplicates: {lead_stats["duplicates"]}, '
                    f'Excluded: {lead_stats["excluded"]}, Failed: {lead_stats["failed"]}',
                    sub_type=lead_type
                )

            except Exception as e:
                logger.error(f"Failed to sync {lead_type} for date range: {e}")
                overall_stats['status'] = 'partial_failure'

        # Update last_sync_at
        gmail_token.last_sync_at = timezone.now()
        gmail_token.save(update_fields=['last_sync_at'])

        duration = int((timezone.now() - sync_start).total_seconds() * 1000)
        _gl_log(
            'INFO',
            'Date Range Sync Complete',
            f'Synced {overall_stats["total_created"]} leads from date range using {overall_stats["total_api_calls"]} API calls',
            duration_ms=duration
        )

    except Exception as e:
        overall_stats['status'] = 'error'
        overall_stats['error'] = str(e)
        logger.error(f"Failed date range sync for {gmail_token.email_account}: {e}")

        _gl_log(
            'ERROR',
            'Date Range Sync Failed',
            f'Date range sync failed: {str(e)}'
        )

    return overall_stats
