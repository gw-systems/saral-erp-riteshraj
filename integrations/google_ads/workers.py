"""
Cloud Tasks worker endpoints for Google Ads integration
Replaces Celery tasks with HTTP endpoints

SECURITY: These endpoints are protected by Cloud Tasks OIDC authentication.
Only requests from Google Cloud Tasks with valid OIDC tokens are accepted.

CRITICAL: Google Ads handles API quotas and financial ad spend data.
All operations must be:
1. Authenticated
2. Validated
3. Rate-limited
4. Audited with full logging
"""

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pydantic import ValidationError

from integration_workers.auth import require_cloud_tasks_auth, get_cloud_tasks_task_name
from integration_workers.validation import GoogleAdsSyncPayload, validate_payload
from .models import GoogleAdsToken
from .google_ads_sync import GoogleAdsSync
from integrations.models import SyncLog

logger = logging.getLogger(__name__)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_google_ads_account_worker(request):
    """
    Cloud Tasks worker: Sync a single Google Ads account

    Payload:
        {
            "token_id": 123,
            "sync_yesterday": true,
            "sync_current_month_search_terms": true
        }

    Returns:
        JsonResponse with sync statistics
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🚀 Google Ads sync task started: {task_info.get('task_name')}")

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
            payload = validate_payload(GoogleAdsSyncPayload, raw_payload)
        except ValidationError as e:
            logger.error(f"Payload validation failed: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid payload format'
            }, status=400)

        logger.info(f"[Worker] Starting Google Ads sync for token_id={payload.token_id}")

        # Get batch_log_id and scheduled_job_id from payload if provided
        batch_log_id = raw_payload.get('batch_log_id')
        scheduled_job_id = raw_payload.get('scheduled_job_id')
        sync_engine = GoogleAdsSync(payload.token_id, batch_log_id=batch_log_id, scheduled_job_id=scheduled_job_id)
        stats = sync_engine.sync_all(
            sync_yesterday=payload.sync_yesterday,
            sync_current_month_search_terms=payload.sync_current_month_search_terms
        )

        logger.info(f"[Worker] Google Ads sync completed: {stats}")
        return JsonResponse({
            'status': 'success',
            'token_id': payload.token_id,
            'stats': stats,
            'task_name': task_info.get('task_name'),
            'retry_count': task_info.get('retry_count')
        })

    except ValidationError as e:
        # Payload validation error - don't retry (4xx error)
        logger.error(f"Validation error: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Invalid request payload'
        }, status=400)

    except Exception as e:
        # Log full error server-side, return generic message to client
        logger.error(f"❌ Google Ads sync failed: {e}", exc_info=True)

        # Log the error to sync log
        try:
            SyncLog.log(
                integration='google_ads', sync_type='google_ads',
                level='ERROR', operation='Worker task failed',
                details={'task_name': task_info.get('task_name')}
            )
        except Exception as log_error:
            logger.error(f"Failed to create sync log: {log_error}")

        return JsonResponse({
            'status': 'error',
            'error': 'Sync operation failed. Please contact support.'
        }, status=500)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_all_google_ads_accounts_worker(request):
    """
    Cloud Tasks worker: Sync all active Google Ads accounts

    Payload:
        {
            "sync_yesterday": true,
            "sync_current_month_search_terms": true
        }

    Returns:
        JsonResponse with overall sync statistics
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🚀 Google Ads all accounts sync task started: {task_info.get('task_name')}")

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

        # For "all accounts" sync, token_id is not required
        # We use a minimal validation here (just the boolean flags)
        sync_yesterday = raw_payload.get('sync_yesterday', True)
        sync_current_month_search_terms = raw_payload.get('sync_current_month_search_terms', True)
        scheduled_job_id = raw_payload.get('scheduled_job_id')

        logger.info("[Worker] Starting sync for all Google Ads accounts")

        active_tokens = GoogleAdsToken.objects.filter(is_active=True)

        results = {
            'total_accounts': active_tokens.count(),
            'successful': 0,
            'failed': 0,
            'details': []
        }

        for token in active_tokens:
            try:
                sync_engine = GoogleAdsSync(token.id, scheduled_job_id=scheduled_job_id)
                stats = sync_engine.sync_all(
                    sync_yesterday=sync_yesterday,
                    sync_current_month_search_terms=sync_current_month_search_terms
                )

                results['successful'] += 1
                results['details'].append({
                    'token_id': token.id,
                    'account_name': token.account_name,
                    'status': 'success',
                    'stats': stats
                })

            except Exception as e:
                logger.error(f"[Worker] Failed to sync token_id={token.id}: {e}", exc_info=True)
                results['failed'] += 1
                results['details'].append({
                    'token_id': token.id,
                    'account_name': token.account_name,
                    'status': 'failed',
                    'error': 'Sync failed'  # Generic error to client
                })

        logger.info(f"[Worker] All accounts sync completed: {results}")
        return JsonResponse({
            'status': 'success',
            'results': results,
            'task_name': task_info.get('task_name'),
            'retry_count': task_info.get('retry_count')
        })

    except Exception as e:
        # Log full error server-side, return generic message
        logger.error(f"❌ Failed to sync all Google Ads accounts: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Sync operation failed. Please contact support.'
        }, status=500)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_historical_data_worker(request):
    """
    Cloud Tasks worker: Sync historical data for a Google Ads account

    Payload:
        {
            "token_id": 123,
            "start_date": "2024-01-01"
        }

    Returns:
        JsonResponse with sync statistics
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🚀 Google Ads historical sync task started: {task_info.get('task_name')}")

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
            payload = validate_payload(GoogleAdsSyncPayload, raw_payload)
        except ValidationError as e:
            logger.error(f"Payload validation failed: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid payload format'
            }, status=400)

        # Use validated start_date from Pydantic payload
        start_date = payload.start_date
        if not start_date:
            return JsonResponse({
                'status': 'error',
                'error': 'start_date is required for historical sync'
            }, status=400)

        logger.info(f"[Worker] Starting historical sync for token_id={payload.token_id} from {start_date}")

        # Get batch_log_id and scheduled_job_id from payload if provided
        batch_log_id = raw_payload.get('batch_log_id')
        scheduled_job_id = raw_payload.get('scheduled_job_id')
        sync_engine = GoogleAdsSync(payload.token_id, batch_log_id=batch_log_id, scheduled_job_id=scheduled_job_id)
        stats = sync_engine.sync_historical_data(start_date)

        logger.info(f"[Worker] Historical sync completed: {stats}")
        return JsonResponse({
            'status': 'success',
            'token_id': payload.token_id,
            'start_date': start_date,
            'stats': stats,
            'task_name': task_info.get('task_name'),
            'retry_count': task_info.get('retry_count')
        })

    except ValidationError as e:
        # Payload validation error - don't retry (4xx error)
        logger.error(f"Validation error: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Invalid request payload'
        }, status=400)

    except Exception as e:
        # Log full error server-side, return generic message
        logger.error(f"❌ Google Ads historical sync failed: {e}", exc_info=True)

        # Log the error to sync log
        try:
            SyncLog.log(
                integration='google_ads', sync_type='google_ads_historical',
                level='ERROR', operation='Historical sync failed',
                details={'task_name': task_info.get('task_name')}
            )
        except Exception as log_error:
            logger.error(f"Failed to create sync log: {log_error}")

        return JsonResponse({
            'status': 'error',
            'error': 'Sync operation failed. Please contact support.'
        }, status=500)
