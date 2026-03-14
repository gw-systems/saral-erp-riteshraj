"""
Cloud Tasks worker endpoints for Bigin integration
Replaces Celery tasks with HTTP endpoints

SECURITY: These endpoints are protected by Cloud Tasks OIDC authentication.
Only requests from Google Cloud Tasks with valid OIDC tokens are accepted.
"""

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pydantic import ValidationError

from integration_workers.auth import require_cloud_tasks_auth, get_cloud_tasks_task_name
from integration_workers.validation import BiginSyncPayload, validate_payload
from .sync_service import run_sync_all_modules, run_refresh_bigin_token
from .stale_lead_checker import check_stale_leads

logger = logging.getLogger(__name__)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_all_modules_worker(request):
    """
    Cloud Tasks worker: Sync all modules from Zoho Bigin

    Payload:
        {
            "modules": ["Contacts", "Deals"],  # Optional: specific modules
        }

    Returns:
        JsonResponse with sync statistics
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"[Worker] Bigin sync task started: {task_info.get('task_name')}")

    try:
        # Parse and validate JSON payload
        try:
            raw_payload = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request body: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid JSON payload'
            }, status=400)

        # Validate payload with Pydantic schema
        try:
            payload = validate_payload(BiginSyncPayload, raw_payload)
        except ValidationError as e:
            logger.error(f"Payload validation failed: {e}")
            return JsonResponse({
                'status': 'error',
                'error': f'Invalid payload: {str(e)}'
            }, status=400)

        run_full = payload.run_full
        triggered_by_user = payload.triggered_by_user or 'cloud_tasks'
        scheduled_job_id = raw_payload.get('scheduled_job_id')
        sync_type = "Full" if run_full else "Incremental"
        logger.info(f"[Worker] Starting {sync_type} Bigin sync triggered by {triggered_by_user}, modules: {payload.modules}")

        # This will run the sync and create/update SyncLog
        run_sync_all_modules(run_full=run_full, triggered_by_user=triggered_by_user, scheduled_job_id=scheduled_job_id)

        logger.info(f"[Worker] Bigin sync completed successfully")

        return JsonResponse({
            'status': 'success',
            'message': f'{sync_type} sync completed',
            'task_name': task_info.get('task_name'),
            'retry_count': task_info.get('retry_count')
        })

    except RuntimeError as e:
        # Handle "another sync already running" error
        logger.warning(f"[Worker] Sync conflict: {e}")
        return JsonResponse({
            'status': 'error',
            'error': 'Another sync is already running. Please wait.'
        }, status=409)

    except ValidationError as e:
        # Payload validation error - don't retry (4xx error)
        logger.error(f"[Worker] Validation error: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Invalid request payload'
        }, status=400)

    except Exception as e:
        # Unexpected error - log full details server-side, return generic message
        logger.error(f"[Worker] Bigin sync failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Sync operation failed. Please contact support.'
        }, status=500)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def refresh_bigin_token_worker(request):
    """
    Cloud Tasks worker: Refresh Bigin OAuth token

    Payload: {} (no parameters needed)

    Returns:
        JsonResponse with refresh status
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"[Worker] Token refresh task started: {task_info.get('task_name')}")

    try:
        logger.info("[Worker] Starting Bigin token refresh")

        result = run_refresh_bigin_token()

        logger.info(f"[Worker] Token refresh result: {result}")

        return JsonResponse({
            'status': 'success',
            'message': 'Token refreshed successfully',
            'task_name': task_info.get('task_name')
        })

    except Exception as e:
        # Log full error server-side, return generic message
        logger.error(f"[Worker] Token refresh failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Token refresh failed. Please contact support.'
        }, status=500)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def stale_lead_check_worker(request):
    """
    Cloud Tasks worker: Check for new leads with no CRM activity in 45 minutes.
    Schedule every 15 minutes via Cloud Scheduler (business hours only).

    Payload: {} (no parameters needed)

    Returns:
        JsonResponse with check statistics
    """
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"[Worker] Stale lead check started: {task_info.get('task_name')}")

    try:
        result = check_stale_leads()
        logger.info(
            f"[Worker] Stale lead check done: "
            f"{result['checked']} checked, {result['alerted']} alerted, "
            f"{result['skipped_dedup']} skipped"
        )
        return JsonResponse({
            'status': 'success',
            'task_name': task_info.get('task_name'),
            **result,
        })

    except Exception as e:
        logger.error(f"[Worker] Stale lead check failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Stale lead check failed. Please contact support.'
        }, status=500)
