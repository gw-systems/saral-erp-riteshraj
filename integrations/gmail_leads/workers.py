"""
Cloud Tasks worker endpoints for Gmail Leads integration
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
from integration_workers.validation import GmailLeadsSyncPayload, validate_payload
from .models import GmailLeadsToken
from .gmail_leads_sync import sync_gmail_leads_account, sync_all_gmail_leads_accounts

logger = logging.getLogger(__name__)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_gmail_leads_account_worker(request):
    """
    Cloud Tasks worker: Sync a single Gmail Leads account

    Payload:
        {
            "token_id": 123,
            "force_full": false
        }

    Returns:
        JsonResponse with sync statistics
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🚀 Gmail Leads sync task started: {task_info.get('task_name')}")

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
            payload = validate_payload(GmailLeadsSyncPayload, raw_payload)
        except ValidationError as e:
            logger.error(f"Payload validation failed: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid payload format'
            }, status=400)

        gmail_token = GmailLeadsToken.objects.get(id=payload.token_id)

        sync_type = "Full" if payload.force_full else "Incremental"
        logger.info(f"[Worker] {sync_type} sync starting for {gmail_token.email_account}")

        # Get batch_log_id and scheduled_job_id from payload if provided
        batch_log_id = raw_payload.get('batch_log_id')
        scheduled_job_id = raw_payload.get('scheduled_job_id')
        stats = sync_gmail_leads_account(gmail_token, force_full=payload.force_full, batch_log_id=batch_log_id, scheduled_job_id=scheduled_job_id)

        logger.info(
            f"[Worker] Sync complete for {gmail_token.email_account}: "
            f"{stats['total_created']} leads created"
        )

        return JsonResponse({
            'status': 'success',
            'token_id': payload.token_id,
            'stats': stats,
            'task_name': task_info.get('task_name'),
            'retry_count': task_info.get('retry_count')
        })

    except GmailLeadsToken.DoesNotExist:
        logger.error(f"[Worker] GmailLeadsToken {payload.token_id} not found")
        return JsonResponse({
            'status': 'error',
            'error': 'Gmail Leads token not found'
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
        logger.error(f"❌ Gmail Leads sync failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Sync operation failed. Please contact support.'
        }, status=500)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_all_gmail_leads_accounts_worker(request):
    """
    Cloud Tasks worker: Sync all Gmail Leads accounts

    Payload:
        {
            "force_full": false
        }

    Returns:
        JsonResponse with overall sync statistics
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🚀 Gmail Leads all accounts sync task started: {task_info.get('task_name')}")

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

        # For "all accounts" sync, we just need the force_full flag
        force_full = raw_payload.get('force_full', False)
        scheduled_job_id = raw_payload.get('scheduled_job_id')

        sync_type = "Full" if force_full else "Incremental"
        logger.info(f"[Worker] {sync_type} sync starting for all Gmail Leads accounts")

        stats = sync_all_gmail_leads_accounts(force_full=force_full, scheduled_job_id=scheduled_job_id)

        logger.info(
            f"[Worker] Gmail Leads sync complete: {stats['successful']}/{stats['total_accounts']} accounts, "
            f"{stats['total_leads_created']} leads created"
        )

        return JsonResponse({
            'status': 'success',
            'stats': stats,
            'task_name': task_info.get('task_name'),
            'retry_count': task_info.get('retry_count')
        })

    except Exception as e:
        # Log full error server-side, return generic message
        logger.error(f"❌ Gmail Leads sync failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Sync operation failed. Please contact support.'
        }, status=500)
