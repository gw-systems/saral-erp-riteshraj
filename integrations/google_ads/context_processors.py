"""
Context processors for Google Ads
Injects global data into all templates
"""

from django.core.cache import cache
from .sync_progress import get_sync_progress
from .models import GoogleAdsToken


def active_syncs(request):
    """
    Add active Google Ads syncs to template context
    This allows the navbar to show sync status globally
    """
    if not request.user.is_authenticated:
        return {}

    # Cache token list for 30 seconds to avoid hitting DB on every request
    cache_key = 'google_ads_active_tokens'
    tokens_data = cache.get(cache_key)

    if tokens_data is None:
        # Cache miss — query DB
        tokens = GoogleAdsToken.objects.filter(is_active=True).values('id', 'account_name')
        tokens_data = list(tokens)
        cache.set(cache_key, tokens_data, 30)

    # Cache the entire result for 10 seconds to avoid per-token DB queries on every request
    result_cache_key = 'google_ads_active_syncs_ctx'
    cached_result = cache.get(result_cache_key)
    if cached_result is not None:
        return cached_result

    active_syncs_list = []

    for token_data in tokens_data:
        progress = get_sync_progress(token_data['id'])
        if progress and progress.get('status') == 'running':
            active_syncs_list.append({
                'token_id': token_data['id'],
                'account_name': token_data['account_name'],
                'progress': progress
            })

    result = {
        'google_ads_active_syncs': active_syncs_list,
        'has_active_google_ads_sync': len(active_syncs_list) > 0
    }
    cache.set(result_cache_key, result, 10)
    return result
