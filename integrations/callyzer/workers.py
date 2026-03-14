"""
Cloud Tasks worker endpoints for Callyzer integration
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
from integration_workers.validation import CallyzerSyncPayload, validate_payload
from .models import CallyzerToken
from .callyzer_sync import sync_callyzer_account, sync_all_callyzer_accounts

logger = logging.getLogger(__name__)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_callyzer_account_worker(request):
    """
    Cloud Tasks worker: Sync a single Callyzer account

    Payload:
        {
            "token_id": 123,
            "days_back": 150
        }

    Returns:
        JsonResponse with sync statistics
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🚀 Callyzer sync task started: {task_info.get('task_name')}")

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
            payload = validate_payload(CallyzerSyncPayload, raw_payload)
        except ValidationError as e:
            logger.error(f"Payload validation failed: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid payload format'
            }, status=400)

        token = CallyzerToken.objects.get(id=payload.token_id)
        logger.info(f"[Worker] Starting Callyzer sync for {token.account_name}")

        # Get batch_log_id and scheduled_job_id from payload if provided
        batch_log_id = raw_payload.get('batch_log_id')
        scheduled_job_id = raw_payload.get('scheduled_job_id')
        stats = sync_callyzer_account(token, days_back=payload.days_back, batch_log_id=batch_log_id, scheduled_job_id=scheduled_job_id)

        logger.info(f"[Worker] Callyzer sync complete for {token.account_name}")

        return JsonResponse({
            'status': 'success',
            'token_id': payload.token_id,
            'stats': stats,
            'task_name': task_info.get('task_name'),
            'retry_count': task_info.get('retry_count')
        })

    except CallyzerToken.DoesNotExist:
        logger.error(f"[Worker] CallyzerToken {payload.token_id} not found")
        return JsonResponse({
            'status': 'error',
            'error': 'Callyzer token not found'
        }, status=404)

    except ValidationError as e:
        # Payload validation error - don't retry (4xx error)
        logger.error(f"Validation error: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Invalid request payload'
        }, status=400)

    except Exception as e:
        # Log full error server-side, return generic message
        logger.error(f"❌ Callyzer sync failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Sync operation failed. Please contact support.'
        }, status=500)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_all_callyzer_accounts_worker(request):
    """
    Cloud Tasks worker: Sync all Callyzer accounts

    Payload:
        {
            "days_back": 150
        }

    Returns:
        JsonResponse with overall sync statistics
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🚀 Callyzer all accounts sync task started: {task_info.get('task_name')}")

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

        # For "all accounts" sync, we just need the days_back parameter
        days_back = raw_payload.get('days_back', 150)

        # Validate days_back range (1-365)
        if not isinstance(days_back, int) or days_back < 1 or days_back > 365:
            return JsonResponse({
                'status': 'error',
                'error': 'days_back must be between 1 and 365'
            }, status=400)

        scheduled_job_id = raw_payload.get('scheduled_job_id')
        logger.info(f"[Worker] Starting Callyzer sync for all accounts (days_back={days_back})")

        stats = sync_all_callyzer_accounts(days_back=days_back, scheduled_job_id=scheduled_job_id)

        logger.info(f"[Worker] Callyzer sync complete: {stats['successful']}/{stats['total_accounts']} accounts successful")

        return JsonResponse({
            'status': 'success',
            'stats': stats,
            'task_name': task_info.get('task_name'),
            'retry_count': task_info.get('retry_count')
        })

    except Exception as e:
        # Log full error server-side, return generic message
        logger.error(f"❌ Callyzer sync failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Sync operation failed. Please contact support.'
        }, status=500)
