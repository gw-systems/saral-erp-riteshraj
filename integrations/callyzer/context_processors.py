"""
Context processors for Callyzer
Injects global data into all templates
"""

from django.core.cache import cache
from integrations.models import SyncLog
from .models import CallyzerToken


def active_syncs(request):
    """
    Add active Callyzer syncs to template context
    This allows the navbar to show sync status globally
    """
    if not request.user.is_authenticated:
        return {}

    # Cache token list for 30 seconds to avoid hitting DB on every request
    cache_key = 'callyzer_active_tokens'
    tokens_data = cache.get(cache_key)

    if tokens_data is None:
        # Cache miss — query DB
        tokens = CallyzerToken.objects.filter(is_active=True).values('id', 'account_name')
        tokens_data = list(tokens)
        cache.set(cache_key, tokens_data, 30)

    if not tokens_data:
        return {'callyzer_active_syncs': [], 'has_active_callyzer_sync': False}

    # Cache the entire result for 10 seconds to avoid SyncLog query on every request
    result_cache_key = 'callyzer_active_syncs_ctx'
    cached_result = cache.get(result_cache_key)
    if cached_result is not None:
        return cached_result

    # Single batch query for ALL running callyzer syncs (instead of 1 query per token)
    _account_names = [t['account_name'] for t in tokens_data]
    _running_batches = SyncLog.objects.filter(
        integration='callyzer',
        log_kind='batch',
        status='running',
        sub_type__in=_account_names,
    ).order_by('sub_type', '-started_at')

    # Keep only the most recent batch per account_name
    _batch_by_account = {}
    for batch in _running_batches:
        if batch.sub_type not in _batch_by_account:
            _batch_by_account[batch.sub_type] = batch

    active_syncs_list = []
    for token_data in tokens_data:
        batch = _batch_by_account.get(token_data['account_name'])
        if batch:
            active_syncs_list.append({
                'token_id': token_data['id'],
                'account_name': token_data['account_name'],
                'progress': {
                    'status': 'running',
                    'progress_percentage': batch.overall_progress_percent,
                    'current_status': batch.current_module or 'Syncing...',
                    'sync_id': batch.id
                }
            })

    result = {
        'callyzer_active_syncs': active_syncs_list,
        'has_active_callyzer_sync': len(active_syncs_list) > 0
    }
    cache.set(result_cache_key, result, 10)
    return result
