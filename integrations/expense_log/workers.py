"""
Cloud Tasks worker for background expense sync.
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import logging

from .expense_log_sync import ExpenseLogSyncEngine

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(['POST'])
def sync_worker(request):
    """
    Cloud Tasks worker endpoint for expense sync.

    Expected POST body:
        {
            "token_id": int,
            "sync_type": "incremental" or "full",
            "triggered_by_user": str (optional)
        }

    Returns:
        JSON with sync stats
    """
    try:
        # Parse request body
        payload = json.loads(request.body)
        token_id = payload.get('token_id')
        sync_type = payload.get('sync_type', 'incremental')
        triggered_by_user = payload.get('triggered_by_user')

        if not token_id:
            return JsonResponse({'error': 'token_id required'}, status=400)

        logger.info(f"Starting {sync_type} sync for token {token_id} (triggered by: {triggered_by_user or 'system'})")

        # Run sync
        scheduled_job_id = payload.get('scheduled_job_id')
        engine = ExpenseLogSyncEngine(token_id, sync_type, triggered_by_user=triggered_by_user, scheduled_job_id=scheduled_job_id)
        stats = engine.sync()

        logger.info(f"Sync completed for token {token_id}: {stats}")

        return JsonResponse({
            'status': 'success',
            'stats': {
                'total_rows': stats['total_rows'],
                'processed': stats['processed'],
                'created': stats['created'],
                'updated': stats['updated'],
                'errors': stats['errors'],
            },
            'batch_log_id': engine.batch_log.id
        })

    except Exception as e:
        logger.error(f"Sync worker error: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)
