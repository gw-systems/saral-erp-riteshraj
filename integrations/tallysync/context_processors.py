"""
Context processors for TallySync
Injects global data into all templates
"""

from django.core.cache import cache
from integrations.models import SyncLog


CACHE_TIMEOUT = 30  # 30 seconds — same as other sync context processors


def active_syncs(request):
    """
    Add active TallySync syncs to template context
    This allows the navbar to show sync status globally
    """
    if not request.user.is_authenticated:
        return {}

    cache_key = 'tallysync_active_syncs'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    active_syncs_list = []

    # Find any running TallySync batch logs
    running_batches = SyncLog.objects.filter(
        integration='tallysync',
        log_kind='batch',
        status='running'
    ).order_by('-started_at')

    for batch in running_batches:
        active_syncs_list.append({
            'company_name': batch.sub_type or 'Unknown',
            'sync_type': batch.sync_type,
            'progress': {
                'status': 'running',
                'progress_percentage': batch.overall_progress_percent,
                'current_status': batch.current_module or 'Syncing...',
                'sync_id': batch.id
            }
        })

    result = {
        'tallysync_active_syncs': active_syncs_list,
        'has_active_tallysync_sync': len(active_syncs_list) > 0
    }
    cache.set(cache_key, result, CACHE_TIMEOUT)
    return result
