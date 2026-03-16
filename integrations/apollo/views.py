import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from integration_workers import create_task
from integrations.models import SyncLog

from .models import ApolloCampaign, ApolloMessage, ApolloSyncState

logger = logging.getLogger(__name__)


def _apollo_permission_denied(request):
    return request.user.role not in ['admin', 'director', 'digital_marketing', 'crm_executive']


@login_required
def dashboard(request):
    if _apollo_permission_denied(request):
        return redirect('accounts:home')

    recent_syncs = SyncLog.objects.filter(
        integration='apollo',
        log_kind='batch',
    ).order_by('-started_at')[:20]
    running_sync = SyncLog.objects.filter(
        integration='apollo',
        log_kind='batch',
        status='running',
    ).order_by('-started_at').first()
    recent_messages = ApolloMessage.objects.select_related('campaign').order_by(
        F('sent_at').desc(nulls_last=True),
        '-id',
    )[:50]

    context = {
        'campaign_count': ApolloCampaign.objects.count(),
        'message_count': ApolloMessage.objects.count(),
        'replied_count': ApolloMessage.objects.filter(replied=True).count(),
        'warm_count': ApolloMessage.objects.filter(lead_category='WARM').count(),
        'last_message': recent_messages[0] if recent_messages else None,
        'recent_messages': recent_messages,
        'recent_syncs': recent_syncs,
        'running_sync': running_sync,
        'sync_state': ApolloSyncState.load('historical'),
    }
    return render(request, 'apollo/dashboard.html', context)


@login_required
@require_POST
def trigger_sync(request):
    if _apollo_permission_denied(request):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    sync_type = request.POST.get('sync_type', 'incremental')
    if sync_type not in {'incremental', 'full'}:
        return JsonResponse({'success': False, 'error': 'Invalid sync_type'}, status=400)

    start_date = request.POST.get('start_date') or None
    end_date = request.POST.get('end_date') or None
    reset_checkpoint = request.POST.get('reset_checkpoint') in {'1', 'true', 'True', 'on'}

    batch_log = SyncLog.objects.create(
        integration='apollo',
        sync_type='apollo_full' if sync_type == 'full' else 'apollo_incremental',
        log_kind='batch',
        status='running',
        triggered_by_user=request.user.username,
    )

    task_name = create_task(
        endpoint='/integrations/apollo/workers/sync/',
        payload={
            'sync_type': sync_type,
            'triggered_by_user': request.user.username,
            'start_date': start_date,
            'end_date': end_date,
            'batch_log_id': batch_log.id,
            'reset_checkpoint': reset_checkpoint,
        },
        task_name=f'apollo-sync-{sync_type}-{batch_log.id}',
        timeout=1800,
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'sync_id': batch_log.id,
            'task_name': task_name,
        })

    messages.success(request, f'Apollo {sync_type} sync queued successfully.')
    return redirect('apollo:dashboard')


@login_required
@require_GET
def sync_progress(request):
    if _apollo_permission_denied(request):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    sync = SyncLog.objects.filter(
        integration='apollo',
        log_kind='batch',
        status='running',
    ).order_by('-started_at').first()

    if not sync:
        return JsonResponse({'status': 'idle'})

    return JsonResponse({
        'status': sync.status,
        'sync_id': sync.id,
        'progress': sync.overall_progress_percent,
        'current_module': sync.current_module,
        'total_records_synced': sync.total_records_synced,
        'records_created': sync.records_created,
        'records_updated': sync.records_updated,
        'records_failed': sync.records_failed,
    })


@login_required
@require_GET
def sync_logs(request, batch_id):
    if _apollo_permission_denied(request):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        batch_log = SyncLog.objects.get(pk=batch_id, integration='apollo', log_kind='batch')
    except SyncLog.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Sync log not found'}, status=404)

    operations = SyncLog.objects.filter(batch=batch_log).order_by('-started_at')[:100]
    return JsonResponse({
        'success': True,
        'batch': {
            'id': batch_log.id,
            'status': batch_log.status,
            'started_at': batch_log.started_at.isoformat(),
            'completed_at': batch_log.completed_at.isoformat() if batch_log.completed_at else None,
            'total_records_synced': batch_log.total_records_synced,
        },
        'operations': [
            {
                'level': op.level,
                'operation': op.operation,
                'message': op.message,
                'started_at': op.started_at.isoformat(),
            }
            for op in operations
        ],
    })
