"""
Cloud Tasks worker endpoints for Gmail integration
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
from integration_workers.validation import GmailSyncPayload, validate_payload
from gmail.models import GmailToken
from gmail.sync_engine import SyncEngine

logger = logging.getLogger("gmail.workers")


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_gmail_account_worker(request):
    """
    Cloud Tasks worker: Sync a single Gmail account

    Payload:
        {
            "gmail_token_id": 123,
            "full_sync": false
        }

    Returns:
        JsonResponse with sync statistics
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🚀 Gmail sync task started: {task_info.get('task_name')}")

    try:
        # Parse JSON payload
        try:
            raw_payload = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request body: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid JSON payload'
            }, status=400)

        # Get token_id
        token_id = raw_payload.get('gmail_token_id')
        full_sync = raw_payload.get('full_sync', False)

        if not token_id:
            return JsonResponse({
                'status': 'error',
                'error': 'gmail_token_id required'
            }, status=400)

        logger.info(f"[Worker] Starting sync for token ID {token_id}, full_sync={full_sync}")

        # Perform sync using new sync engine
        scheduled_job_id = raw_payload.get('scheduled_job_id')
        SyncEngine.sync_account(token_id, full_sync=full_sync, scheduled_job_id=scheduled_job_id)

        logger.info(f"[Worker] Completed sync for token ID {token_id}")

        return JsonResponse({
            'status': 'success',
            'token_id': token_id,
            'task_name': task_info.get('task_name'),
            'retry_count': task_info.get('retry_count')
        })

    except GmailToken.DoesNotExist:
        logger.error(f"[Worker] GmailToken {token_id} not found")
        return JsonResponse({
            'status': 'error',
            'error': 'Gmail token not found'
        }, status=404)

    except Exception as e:
        logger.error(f"❌ Gmail sync failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Sync operation failed. Please contact support.'
        }, status=500)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_all_gmail_accounts_worker(request):
    """
    Cloud Tasks worker: Sync all Gmail accounts

    Payload:
        {
            "full_sync": false
        }

    Returns:
        JsonResponse with overall sync statistics
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🚀 Gmail all accounts sync task started: {task_info.get('task_name')}")

    try:
        # Parse JSON payload
        try:
            raw_payload = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request body: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid JSON payload'
            }, status=400)

        full_sync = raw_payload.get('full_sync', False)
        scheduled_job_id = raw_payload.get('scheduled_job_id')

        logger.info("[Worker] Starting sync_all_gmail_accounts")

        # Get all active tokens
        tokens = GmailToken.objects.filter(is_active=True)

        synced_count = 0
        for token in tokens:
            try:
                SyncEngine.sync_account(token.id, full_sync=full_sync, scheduled_job_id=scheduled_job_id)
                synced_count += 1
            except Exception as e:
                logger.error(f"Failed to sync token {token.id}: {e}")

        logger.info(f"[Worker] Completed sync for {synced_count}/{tokens.count()} accounts")

        return JsonResponse({
            'status': 'success',
            'total_accounts': tokens.count(),
            'synced_accounts': synced_count,
            'task_name': task_info.get('task_name'),
            'retry_count': task_info.get('retry_count')
        })

    except Exception as e:
        logger.error(f"❌ Gmail sync all failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Sync operation failed. Please contact support.'
        }, status=500)
