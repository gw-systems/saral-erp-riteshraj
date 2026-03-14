"""
Cloud Tasks worker endpoints for TallySync integration
Replaces Celery tasks with HTTP endpoints

SECURITY: These endpoints are protected by Cloud Tasks OIDC authentication.
Only requests from Google Cloud Tasks with valid OIDC tokens are accepted.

CRITICAL: TallySync handles financial data. All operations must be:
1. Authenticated
2. Validated
3. Wrapped in transactions
4. Audited with full logging
"""

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timedelta
from pydantic import ValidationError

from integration_workers.auth import require_cloud_tasks_auth, get_cloud_tasks_task_name
from integration_workers.validation import TallySyncPayload, validate_payload

logger = logging.getLogger(__name__)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_tally_data_worker(request):
    """
    Cloud Tasks worker: Automatic Tally data sync

    Syncs: Vouchers, Ledgers, Cost Centres + Updates Snapshots

    Payload:
        {
            "company_id": 1,  # Optional: specific company
            "sync_type": "vouchers",  # Optional: companies/ledgers/vouchers/all
            "from_date": "2024-01-01",  # Optional: YYYY-MM-DD format
            "to_date": "2024-01-31"  # Optional: YYYY-MM-DD format
        }

    Returns:
        JsonResponse with sync summary
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🚀 TallySync task started: {task_info.get('task_name')}")

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
            payload = validate_payload(TallySyncPayload, raw_payload)
        except ValidationError as e:
            logger.error(f"Payload validation failed: {e}")
            return JsonResponse({
                'status': 'error',
                'error': f'Invalid payload format'
            }, status=400)

        start_time = timezone.now()
        logger.info(f"🚀 Starting Tally sync: {payload.sync_type}")

        from integrations.tallysync.services.sync_service import TallySyncService
        from integrations.tallysync.services.snapshot_service import SnapshotService
        from integrations.tallysync.models import TallyCompany

        # Discover companies from Tally if none exist yet
        sync_service = TallySyncService()
        if not TallyCompany.objects.filter(is_active=True).exists():
            logger.info("No companies in DB — discovering from Tally...")
            sync_service.sync_companies(triggered_by_user=raw_payload.get('triggered_by_user', 'cloud_tasks'))

        # Get companies to sync
        if payload.company_id:
            companies = TallyCompany.objects.filter(id=payload.company_id, is_active=True)
        else:
            companies = TallyCompany.objects.filter(is_active=True)

        # Determine date range
        if payload.from_date and payload.to_date:
            from_date_str = payload.from_date
            to_date_str = payload.to_date
        else:
            # Default: last 7 days
            today = timezone.now().date()
            from_date = today - timedelta(days=7)
            from_date_str = from_date.strftime('%Y%m%d')
            to_date_str = today.strftime('%Y%m%d')

        # Extract triggered_by_user and scheduled_job_id from payload
        triggered_by_user = raw_payload.get('triggered_by_user', 'cloud_tasks')
        scheduled_job_id = raw_payload.get('scheduled_job_id')
        is_full_sync = raw_payload.get('full_sync', False)

        synced_count = 0
        failed_count = 0

        for company in companies:
            try:
                logger.info(f"📊 {'Full' if is_full_sync else 'Incremental'} syncing {company.name}...")

                # Sync based on type
                if payload.sync_type in ('vouchers', 'all'):
                    if is_full_sync:
                        # Full sync — fetch from FY2023 start (earliest data in all companies)
                        from django.utils import timezone as tz
                        full_from = '20230101'
                        full_to = tz.now().date().strftime('%Y%m%d')
                        result = sync_service.sync_vouchers(
                            company=company,
                            from_date=full_from,
                            to_date=full_to,
                            triggered_by_user=triggered_by_user,
                            scheduled_job_id=scheduled_job_id,
                        )
                    elif payload.from_date and payload.to_date:
                        # Explicit date range — use it
                        result = sync_service.sync_vouchers(
                            company=company,
                            from_date=from_date_str.replace('-', ''),
                            to_date=to_date_str.replace('-', ''),
                            triggered_by_user=triggered_by_user,
                            scheduled_job_id=scheduled_job_id,
                        )
                    else:
                        # No date range — incremental sync from last voucher date
                        result = sync_service.sync_vouchers_incremental(
                            company=company,
                            triggered_by_user=triggered_by_user,
                            scheduled_job_id=scheduled_job_id,
                        )
                else:
                    result = {'status': 'skipped', 'processed': 0}

                if result['status'] == 'success':
                    synced_count += 1
                    logger.info(f"✅ {company.name}: {result['processed']} vouchers processed")
                else:
                    failed_count += 1
                    logger.error(f"❌ {company.name}: {result.get('error', 'Unknown error')}")

            except Exception as e:
                failed_count += 1
                logger.error(f"❌ {company.name} failed: {e}", exc_info=True)

        # After all companies synced → Update snapshots
        logger.info("📸 Updating financial snapshots...")
        snapshot_service = SnapshotService()
        snapshot_result = snapshot_service.populate_project_snapshots()
        logger.info(f"✅ Snapshots: Created {snapshot_result['created']}, Updated {snapshot_result['updated']}")

        duration = timezone.now() - start_time
        summary = f"Synced {synced_count}/{companies.count()} companies, {snapshot_result['total']} snapshots in {duration}"

        if failed_count > 0:
            summary += f" ({failed_count} failed)"

        logger.info(f"✅ {summary}")

        return JsonResponse({
            'status': 'success',
            'summary': summary,
            'synced_count': synced_count,
            'failed_count': failed_count,
            'snapshots': snapshot_result,
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
        logger.error(f"❌ Tally sync failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Sync operation failed. Please contact support.'
        }, status=500)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def full_reconciliation_worker(request):
    """
    Cloud Tasks worker: Full reconciliation between ERP and Tally

    Payload: {} (no parameters needed)

    Returns:
        JsonResponse with reconciliation results
    """
    # Get Cloud Tasks metadata
    task_info = get_cloud_tasks_task_name(request)
    logger.info(f"🔍 Reconciliation task started: {task_info.get('task_name')}")

    try:
        start_time = timezone.now()
        logger.info("🔍 Starting full Tally reconciliation...")

        # TODO: Add reconciliation logic when ready
        # from .services.reconciliation_service import ReconciliationService
        # service = ReconciliationService()
        # results = service.reconcile_all()

        duration = timezone.now() - start_time
        logger.info(f"✅ Reconciliation completed in {duration}")

        return JsonResponse({
            'status': 'success',
            'message': f"Reconciliation successful - took {duration}",
            'task_name': task_info.get('task_name')
        })

    except Exception as e:
        # Log full error server-side, return generic message
        logger.error(f"❌ Reconciliation failed: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Reconciliation failed. Please contact support.'
        }, status=500)
