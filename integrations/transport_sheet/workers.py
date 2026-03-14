"""
Cloud Tasks / Cloud Scheduler worker endpoint for transport sheet sync.
Hourly in production only (DEBUG=False).
"""
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .sync_engine import TransportSheetSyncEngine

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(['POST'])
def transport_sync_worker(request):
    """
    Worker endpoint for transport sheet sync.
    Called by Cloud Scheduler hourly (production only).
    Manual trigger also posts here.

    POST body (optional):
        {"triggered_by_user": "username"}
    """
    try:
        payload = {}
        if request.body:
            try:
                payload = json.loads(request.body)
            except json.JSONDecodeError:
                pass

        triggered_by_user = payload.get('triggered_by_user', 'scheduler')
        logger.info(f"Transport sheet sync triggered by: {triggered_by_user}")

        engine = TransportSheetSyncEngine(triggered_by_user=triggered_by_user)
        stats = engine.sync()

        return JsonResponse({'status': 'success', 'stats': stats})

    except Exception as e:
        logger.error(f"Transport sync worker error: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
