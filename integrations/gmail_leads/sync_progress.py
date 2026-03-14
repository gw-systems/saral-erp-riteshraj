"""
Real-time sync progress tracking for Gmail Leads
Uses Django cache to store progress updates that the frontend can poll
"""

from django.core.cache import cache
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class SyncProgressTracker:
    """
    Track sync progress in cache for real-time frontend updates

    Usage:
        tracker = SyncProgressTracker(token_id=123, sync_type='full')
        tracker.start()
        tracker.update(message="Fetching emails...", emails_processed=50, leads_created=10)
        tracker.complete(success=True, stats={...})
    """

    CACHE_TIMEOUT = 86400  # 24 hours - keeps sync status even after completion

    def __init__(self, token_id, sync_type='incremental'):
        self.token_id = token_id
        self.sync_type = sync_type
        self.cache_key = f'gmail_leads_sync_progress_{token_id}'

    def start(self):
        """Initialize sync progress tracking"""
        progress = {
            'status': 'running',
            'sync_type': self.sync_type,
            'started_at': timezone.now().isoformat(),
            'progress_percentage': 0,
            'current_status': 'Initializing sync...',
            'stats': {
                'emails_processed': 0,
                'leads_created': 0,
                'contact_us': 0,
                'saas_inventory': 0
            },
            'log': [],
            'server_logs': []  # New: Real-time server logs for UI
        }
        cache.set(self.cache_key, progress, self.CACHE_TIMEOUT)
        logger.info(f"[Progress Tracker] Started tracking for token {self.token_id}")
        self.log("✨ Sync initialized", "INFO")

    def log(self, message, level='INFO'):
        """
        Add server log entry visible in UI

        Args:
            message: Log message
            level: Log level (INFO, DEBUG, SUCCESS, WARNING, ERROR)
        """
        progress = cache.get(self.cache_key)
        if not progress:
            return

        timestamp = timezone.localtime(timezone.now()).strftime('%H:%M:%S')
        level_icon = {
            'DEBUG': '🔍',
            'INFO': 'ℹ️',
            'SUCCESS': '✅',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'CRITICAL': '🔥'
        }.get(level, 'ℹ️')

        log_entry = f'[{timestamp}] {level_icon} {message}'

        if 'server_logs' not in progress:
            progress['server_logs'] = []

        progress['server_logs'].append(log_entry)

        # Keep only last 100 entries
        progress['server_logs'] = progress['server_logs'][-100:]

        cache.set(self.cache_key, progress, self.CACHE_TIMEOUT)
        logger.info(f"[Gmail Leads] {message}")

    def update(self, message=None, progress_percentage=None, **stats):
        """
        Update sync progress

        Args:
            message: Current status message
            progress_percentage: Progress from 0-100
            **stats: Dict of stat counters (emails_processed, leads_created, etc.)
        """
        progress = cache.get(self.cache_key)
        if not progress:
            logger.warning(f"[Progress Tracker] No active tracking found for token {self.token_id}")
            return

        if message:
            progress['current_status'] = message
            # Add to log with timestamp
            timestamp = timezone.localtime(timezone.now()).strftime('%H:%M:%S')
            progress['log'].append({
                'time': timestamp,
                'message': message
            })
            # Keep only last 50 log entries
            progress['log'] = progress['log'][-50:]

        if progress_percentage is not None:
            progress['progress_percentage'] = min(100, max(0, progress_percentage))

        # Update stats
        for key, value in stats.items():
            if isinstance(value, dict):
                # Nested stat
                if key not in progress['stats']:
                    progress['stats'][key] = {}
                progress['stats'][key].update(value)
            else:
                # Simple stat counter
                progress['stats'][key] = value

        cache.set(self.cache_key, progress, self.CACHE_TIMEOUT)

    def complete(self, success=True, message=None, stats=None):
        """Mark sync as completed"""
        progress = cache.get(self.cache_key)
        if not progress:
            logger.warning(f"[Progress Tracker] No active tracking found for token {self.token_id}")
            return

        progress['status'] = 'completed' if success else 'failed'
        progress['completed_at'] = timezone.now().isoformat()
        progress['progress_percentage'] = 100 if success else progress.get('progress_percentage', 0)

        if message:
            progress['current_status'] = message
            timestamp = timezone.localtime(timezone.now()).strftime('%H:%M:%S')
            progress['log'].append({
                'time': timestamp,
                'message': message
            })

        if stats:
            progress['stats'] = stats

        cache.set(self.cache_key, progress, self.CACHE_TIMEOUT)
        logger.info(f"[Progress Tracker] Completed tracking for token {self.token_id} - Success: {success}")

    def get_progress(self):
        """Get current progress"""
        return cache.get(self.cache_key)

    def clear(self):
        """Clear progress tracking"""
        cache.delete(self.cache_key)


def get_sync_progress(token_id):
    """
    Get current sync progress for a token
    Includes server logs and UI control states

    Returns:
        dict: Progress data with server_logs and control states
    """
    from integrations.models import SyncLog

    cache_key = f'gmail_leads_sync_progress_{token_id}'
    progress = cache.get(cache_key)

    LEVEL_ICON = {
        'DEBUG': '🔍', 'INFO': 'ℹ️', 'SUCCESS': '✅',
        'WARNING': '⚠️', 'ERROR': '❌', 'CRITICAL': '🔥'
    }

    # Always fetch the most recent batch log (running OR completed/failed) so
    # logs remain visible after the sync finishes, not just while it is running.
    try:
        batch_log = SyncLog.objects.filter(
            integration='gmail_leads',
            sync_type__in=['gmail_leads_full', 'gmail_leads_incremental'],
            log_kind='batch',
        ).order_by('-started_at').first()
    except Exception as e:
        logger.error(f"Failed to fetch Gmail Leads batch log: {e}")
        batch_log = None

    if not batch_log and not progress:
        return {
            'status': 'idle',
            'progress_percentage': 0,
            'message': 'No sync runs yet',
            'server_logs': [],
            'can_start': True,
            'can_stop': False,
        }

    if not progress:
        progress = {}

    # Build server_logs from DB operation logs
    server_logs = []
    try:
        if batch_log:
            operation_logs = SyncLog.objects.filter(
                batch=batch_log,
                log_kind='operation'
            ).order_by('started_at')

            for op_log in operation_logs:
                timestamp = timezone.localtime(op_log.started_at).strftime('%H:%M:%S')
                icon = LEVEL_ICON.get(op_log.level, '')
                line = f"[{timestamp}] {icon} {op_log.operation}"
                if op_log.message:
                    line += f": {op_log.message}"
                if op_log.duration_ms:
                    line += f" ({op_log.duration_ms}ms)"
                server_logs.append(line)

            # Trust DB status as source of truth
            progress['status'] = batch_log.status
            progress['stop_requested'] = batch_log.stop_requested
    except Exception as e:
        logger.error(f"Failed to fetch SyncLog entries: {e}")

    progress['server_logs'] = server_logs

    # Add UI control states
    status = progress.get('status', 'running')
    progress['can_start'] = status not in ['running', 'stopping']
    progress['can_stop'] = status == 'running'

    if status == 'completed' and not progress.get('current_status'):
        records = batch_log.records_created if batch_log else 0
        progress['current_status'] = f'✅ Sync complete — {records} leads synced'
    elif status == 'failed' and batch_log:
        progress['current_status'] = f'❌ Sync failed: {batch_log.error_message or "unknown error"}'

    progress['message'] = progress.get('current_status', 'Syncing...')

    return progress
