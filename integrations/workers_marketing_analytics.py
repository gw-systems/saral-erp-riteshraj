"""
Cloud Tasks worker endpoints for Marketing Analytics
Daily attribution refresh: Gmail Leads → Bigin Contacts matching

SECURITY: These endpoints are protected by Cloud Tasks OIDC authentication.
Only requests from Google Cloud Tasks with valid OIDC tokens are accepted.
"""

import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timedelta

from integration_workers.auth import require_cloud_tasks_auth, get_cloud_tasks_task_name
from integrations.models import LeadAttribution

logger = logging.getLogger(__name__)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def refresh_lead_attributions_worker(request):
    """
    Cloud Tasks worker: Refresh lead attribution records
    Triggered daily by Cloud Scheduler at 2 AM

    Refreshes last 7 days of lead attributions to catch any:
    - New Gmail Leads that need matching
    - New Bigin Contacts that match existing leads
    - Improved matching logic

    Returns:
        JsonResponse with sync statistics
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🚀 Lead attribution refresh task started: {task_info.get('task_name')}")

    try:
        # Refresh last 7 days
        start_date = timezone.now() - timedelta(days=7)

        logger.info(f"Refreshing attributions from {start_date.strftime('%Y-%m-%d %H:%M:%S')}")

        matched_count = LeadAttribution.objects.refresh_attributions(start_date)

        logger.info(f"✅ Lead attribution refresh completed: {matched_count} new matches created")

        return JsonResponse({
            'status': 'success',
            'matched_count': matched_count,
            'start_date': start_date.isoformat(),
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"❌ Lead attribution refresh failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)
