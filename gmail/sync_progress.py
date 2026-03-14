"""
Real-time sync progress tracking for Gmail Inbox
Uses Django cache to store progress updates that the frontend can poll
"""

from django.core.cache import cache
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

CACHE_TIMEOUT = 86400  # 24 hours


class SyncProgressTracker:
    """Track Gmail Inbox sync progress in cache for real-time frontend updates."""

    def __init__(self, token_id, sync_type='incremental'):
        self.token_id = token_id
        self.sync_type = sync_type
        self.cache_key = f'gmail_inbox_sync_progress_{token_id}'

    def start(self):
        progress = {
            'status': 'running',
            'sync_type': self.sync_type,
            'started_at': timezone.now().isoformat(),
            'progress_percentage': 0,
            'current_status': 'Initializing sync...',
            'stats': {
                'messages_synced': 0,
                'threads_synced': 0,
            },
            'log': [],
            'server_logs': [],
        }
        cache.set(self.cache_key, progress, CACHE_TIMEOUT)
        self.log('Sync initialized', 'INFO')

    def log(self, message, level='INFO'):
        progress = cache.get(self.cache_key)
        if not progress:
            return
        timestamp = timezone.localtime(timezone.now()).strftime('%H:%M:%S')
        level_icon = {
            'DEBUG': '🔍', 'INFO': 'ℹ️', 'SUCCESS': '✅',
            'WARNING': '⚠️', 'ERROR': '❌', 'CRITICAL': '🔥'
        }.get(level, 'ℹ️')
        log_entry = f'[{timestamp}] {level_icon} {message}'
        if 'server_logs' not in progress:
            progress['server_logs'] = []
        progress['server_logs'].append(log_entry)
        progress['server_logs'] = progress['server_logs'][-100:]
        cache.set(self.cache_key, progress, CACHE_TIMEOUT)

    def update(self, message=None, progress_percentage=None, **stats):
        progress = cache.get(self.cache_key)
        if not progress:
            return
        if message:
            progress['current_status'] = message
            timestamp = timezone.localtime(timezone.now()).strftime('%H:%M:%S')
            progress['log'].append({'time': timestamp, 'message': message})
            progress['log'] = progress['log'][-50:]
        if progress_percentage is not None:
            progress['progress_percentage'] = min(100, max(0, progress_percentage))
        for key, value in stats.items():
            progress['stats'][key] = value
        cache.set(self.cache_key, progress, CACHE_TIMEOUT)

    def complete(self, success=True, message=None, stats=None):
        progress = cache.get(self.cache_key)
        if not progress:
            return
        progress['status'] = 'completed' if success else 'failed'
        progress['completed_at'] = timezone.now().isoformat()
        progress['progress_percentage'] = 100 if success else progress.get('progress_percentage', 0)
        if message:
            progress['current_status'] = message
            timestamp = timezone.localtime(timezone.now()).strftime('%H:%M:%S')
            progress['log'].append({'time': timestamp, 'message': message})
        if stats:
            progress['stats'] = stats
        cache.set(self.cache_key, progress, CACHE_TIMEOUT)

    def get_progress(self):
        return cache.get(self.cache_key)

    def clear(self):
        cache.delete(self.cache_key)


def get_sync_progress(token_id):
    """
    Get current sync progress for a Gmail token.
    Always reads the most recent batch log from DB (regardless of status)
    so logs remain visible after sync completes.
    """
    from integrations.models import SyncLog

    LEVEL_ICON = {
        'DEBUG': '🔍', 'INFO': 'ℹ️', 'SUCCESS': '✅',
        'WARNING': '⚠️', 'ERROR': '❌', 'CRITICAL': '🔥'
    }

    # Always fetch the most recent batch log (running OR completed/failed/stopped)
    try:
        batch_log = SyncLog.objects.filter(
            integration='gmail',
            log_kind='batch',
        ).order_by('-started_at').first()
    except Exception as e:
        logger.error(f"[Gmail Progress] DB query failed: {e}")
        batch_log = None

    if not batch_log:
        return {
            'status': 'idle',
            'progress_percentage': 0,
            'message': 'No sync runs yet',
            'server_logs': [],
            'can_start': True,
            'can_stop': False,
        }

    # Read operation logs for this batch
    server_logs = []
    try:
        op_logs = SyncLog.objects.filter(
            batch=batch_log,
            log_kind='operation',
        ).order_by('started_at')

        for op in op_logs:
            ts = timezone.localtime(op.started_at).strftime('%H:%M:%S')
            icon = LEVEL_ICON.get(op.level, '')
            line = f"[{ts}] {icon} {op.operation}"
            if op.message:
                line += f": {op.message}"
            if op.duration_ms:
                line += f" ({op.duration_ms}ms)"
            server_logs.append(line)
    except Exception as e:
        logger.error(f"[Gmail Progress] Failed to fetch operation logs: {e}")

    # Also merge cache tracker logs (for granular progress % and status text)
    cache_key = f'gmail_inbox_sync_progress_{token_id}'
    cache_progress = cache.get(cache_key) or {}

    status = batch_log.status  # always trust DB as source of truth
    current_status = cache_progress.get('current_status', '')

    # Build human-readable status message
    if status == 'running':
        message = current_status or 'Syncing...'
    elif status == 'completed':
        records = batch_log.records_created or 0
        message = cache_progress.get('current_status') or f'✅ Sync complete — {records} messages synced'
    elif status == 'failed':
        message = f'❌ Sync failed: {batch_log.error_message or "unknown error"}'
    elif status in ('stopped', 'stopping'):
        message = f'⏹️ Sync stopped: {batch_log.error_message or "stopped by user"}'
    else:
        message = cache_progress.get('current_status', status)

    return {
        'status': status,
        'progress_percentage': cache_progress.get('progress_percentage', 100 if status == 'completed' else 0),
        'message': message,
        'current_status': message,
        'server_logs': server_logs,
        'can_start': status not in ['running', 'stopping'],
        'can_stop': status == 'running',
        'stop_requested': batch_log.stop_requested,
        'sync_id': batch_log.id,
    }
