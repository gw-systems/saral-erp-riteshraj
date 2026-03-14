"""
Callyzer Views
Dashboard, settings, and management views
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Avg, Count
from datetime import datetime, timedelta
from django.utils import timezone

from .models import (
    CallyzerToken,
    CallSummary,
    EmployeeSummary,
    CallAnalysis,
    NeverAttendedCall,
    NotPickedUpCall,
    UniqueClient,
    HourlyAnalytic,
    DailyAnalytic,
    CallHistory,
)
from integrations.models import SyncLog
from .utils.encryption import CallyzerEncryption
from integration_workers import create_task
from django.utils import timezone

import logging
logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    """
    Main Callyzer dashboard
    Shows call statistics and reports
    """
    # RBAC: Admin/Director and CRM Executive only
    if request.user.role not in ['admin', 'director', 'crm_executive']:
        messages.error(request, "You don't have permission to access Callyzer dashboard.")
        return redirect('accounts:home')

    # Get active tokens
    tokens = CallyzerToken.objects.filter(is_active=True)

    # Get filter parameters
    token_id = request.GET.get('token_id', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    # Default date range (last 30 days)
    if not start_date:
        start_date = (timezone.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = timezone.now().strftime('%Y-%m-%d')

    # Build queryset
    call_histories = CallHistory.objects.all().order_by('-call_date', '-call_time')

    # Filter by token
    if token_id:
        call_histories = call_histories.filter(token_id=token_id)

    # Filter by date range
    if start_date:
        call_histories = call_histories.filter(call_date__gte=start_date)
    if end_date:
        call_histories = call_histories.filter(call_date__lte=end_date)

    # Calculate summary statistics
    summary_stats = call_histories.aggregate(
        total_calls=Count('id'),
        total_duration=Sum('duration_seconds'),
        avg_duration=Avg('duration_seconds')
    )

    # Call type breakdown
    call_type_breakdown = {
        'incoming': call_histories.filter(call_type='incoming').count(),
        'outgoing': call_histories.filter(call_type='outgoing').count(),
        'missed': call_histories.filter(call_type='missed').count(),
    }

    # Recent call summaries
    recent_summaries = CallSummary.objects.all().order_by('-synced_at')[:5]

    # Employee performance
    top_employees = EmployeeSummary.objects.all().order_by('-total_calls')[:10]

    # Pagination
    paginator = Paginator(call_histories, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_title': 'Callyzer Dashboard',
        'tokens': tokens,
        'page_obj': page_obj,
        'summary_stats': summary_stats,
        'call_type_breakdown': call_type_breakdown,
        'recent_summaries': recent_summaries,
        'top_employees': top_employees,
        'filters': {
            'token_id': token_id,
            'start_date': start_date,
            'end_date': end_date,
        }
    }

    return render(request, 'callyzer/dashboard.html', context)


@login_required
def analytics(request):
    """
    Analytics dashboard with detailed metrics
    """
    # RBAC: Admin/Director and CRM Executive only
    if request.user.role not in ['admin', 'director', 'crm_executive']:
        messages.error(request, "You don't have permission to access analytics.")
        return redirect('accounts:home')

    # Get filter parameters
    token_id = request.GET.get('token_id', '')

    # Get analytics data
    hourly_analytics = HourlyAnalytic.objects.all().order_by('hour')
    daily_analytics = DailyAnalytic.objects.all().order_by('-date')[:30]

    # Filter by token if specified
    if token_id:
        hourly_analytics = hourly_analytics.filter(token_id=token_id)
        daily_analytics = daily_analytics.filter(token_id=token_id)

    # Employee summaries
    employee_summaries = EmployeeSummary.objects.all().order_by('-total_calls')
    if token_id:
        employee_summaries = employee_summaries.filter(token_id=token_id)

    # Call analysis
    call_analyses = CallAnalysis.objects.all()
    if token_id:
        call_analyses = call_analyses.filter(token_id=token_id)

    context = {
        'page_title': 'Callyzer Analytics',
        'tokens': CallyzerToken.objects.filter(is_active=True),
        'hourly_analytics': hourly_analytics,
        'daily_analytics': daily_analytics,
        'employee_summaries': employee_summaries,
        'call_analyses': call_analyses,
        'filters': {
            'token_id': token_id,
        }
    }

    return render(request, 'callyzer/analytics.html', context)


@login_required
def settings(request):
    """
    Callyzer settings page - Admin only
    Manage API tokens and accounts
    """
    # RBAC: Admin/Director only
    if request.user.role not in ['admin', 'director']:
        messages.error(request, "You don't have permission to access settings.")
        return redirect('callyzer:dashboard')

    # Get all tokens
    tokens = CallyzerToken.objects.all().order_by('-created_at')

    context = {
        'page_title': 'Callyzer Settings',
        'tokens': tokens,
    }

    return render(request, 'callyzer/settings.html', context)


@login_required
def connect(request):
    """
    Connect a new Callyzer account
    """
    # RBAC: Admin/Director only
    if request.user.role not in ['admin', 'director']:
        messages.error(request, "You don't have permission to connect accounts.")
        return redirect('callyzer:dashboard')

    if request.method == 'POST':
        account_name = request.POST.get('account_name', '').strip()
        api_key = request.POST.get('api_key', '').strip()

        if not account_name or not api_key:
            messages.error(request, "Account name and API key are required.")
            return redirect('/accounts/dashboard/admin/integrations/?tab=callyzer')

        # Check if account name already exists
        if CallyzerToken.objects.filter(account_name=account_name).exists():
            messages.error(request, f"Account '{account_name}' already exists.")
            return redirect('/accounts/dashboard/admin/integrations/?tab=callyzer')

        try:
            # Encrypt API key
            encrypted_api_key = CallyzerEncryption.encrypt(api_key)

            # Create token
            token = CallyzerToken.objects.create(
                user=request.user,
                account_name=account_name,
                encrypted_api_key=encrypted_api_key,
                is_active=True
            )

            messages.success(request, f"Successfully connected Callyzer account '{account_name}'!")
            logger.info(f"[Callyzer] Account connected: {account_name} by {request.user.get_full_name()}")

            return redirect('/accounts/dashboard/admin/integrations/?tab=callyzer')

        except Exception as e:
            logger.error(f"[Callyzer] Failed to connect account: {e}")
            messages.error(request, f"Failed to connect account: {str(e)}")
            return redirect('/accounts/dashboard/admin/integrations/?tab=callyzer')

    return redirect('/accounts/dashboard/admin/integrations/?tab=callyzer')


@login_required
def disconnect(request, token_id):
    """
    Disconnect a Callyzer account
    """
    # RBAC: Admin/Director only
    if request.user.role not in ['admin', 'director']:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if request.method == 'POST':
        try:
            token = get_object_or_404(CallyzerToken, id=token_id)
            account_name = token.account_name

            # Delete token (cascade will delete related data)
            token.delete()

            messages.success(request, f"Successfully disconnected '{account_name}'")
            logger.info(f"[Callyzer] Account disconnected: {account_name} by {request.user.get_full_name()}")

        except Exception as e:
            logger.error(f"[Callyzer] Failed to disconnect account: {e}")
            messages.error(request, f"Failed to disconnect account: {str(e)}")

    return redirect('/accounts/dashboard/admin/integrations/?tab=callyzer')


@login_required
def sync_account(request, token_id):
    """
    AJAX endpoint: Sync single Callyzer account
    """
    # RBAC: Admin/Director only
    if request.user.role not in ['admin', 'director']:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if request.method == 'POST':
        try:
            token = get_object_or_404(CallyzerToken, id=token_id)

            # Create batch log before dispatching sync
            from integrations.models import SyncLog
            from django.conf import settings
            batch_log = SyncLog.objects.create(
                integration='callyzer',
                sync_type='callyzer_full',
                log_kind='batch',
                status='running',
                triggered_by_user=token.account_name,
            )

            task_name = create_task(
                endpoint='/integrations/callyzer/workers/sync-account/',
                payload={
                    'token_id': token_id,
                    'days_back': 150,
                    'triggered_by_user': request.user.username,
                    'batch_log_id': batch_log.id,
                },
                task_name=f'callyzer-sync-{token_id}-{int(timezone.now().timestamp())}'
            )

            return JsonResponse({
                'status': 'success',
                'message': f'Sync started for {token.account_name}',
                'task_name': task_name,
                'sync_id': batch_log.id
            })

        except Exception as e:
            logger.error(f"[Callyzer] Sync failed: {e}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)


@login_required
def sync_all_accounts(request):
    """
    AJAX endpoint: Sync all active Callyzer accounts
    """
    # RBAC: Admin/Director only
    if request.user.role not in ['admin', 'director']:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if request.method == 'POST':
        try:
            from django.conf import settings

            task_name = create_task(
                endpoint='/integrations/callyzer/workers/sync-all-accounts/',
                payload={
                    'days_back': 150
                },
                task_name=f'callyzer-sync-all-{int(timezone.now().timestamp())}'
            )

            return JsonResponse({
                'status': 'success',
                'message': 'Sync started for all accounts',
                'task_name': task_name
            })

        except Exception as e:
            logger.error(f"[Callyzer] Sync all failed: {e}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)


@login_required
def sync_logs(request):
    """
    View Callyzer sync logs
    """
    # RBAC: Admin/Director and CRM Executive
    if request.user.role not in ['admin', 'director', 'crm_executive']:
        messages.error(request, "You don't have permission to view logs.")
        return redirect('accounts:home')

    # Get filter parameters
    level_filter = request.GET.get('level', '')
    token_id = request.GET.get('token_id', '')

    # Build queryset - batch logs for overview, operation logs for detail
    batch_logs = SyncLog.objects.filter(integration='callyzer', log_kind='batch').order_by('-started_at')[:50]
    op_logs = SyncLog.objects.filter(integration='callyzer', log_kind='operation').order_by('-started_at')

    if level_filter:
        op_logs = op_logs.filter(level=level_filter)

    op_logs = op_logs[:500]

    context = {
        'page_title': 'Callyzer Sync Logs',
        'batch_logs': batch_logs,
        'logs': op_logs,
        'level_filter': level_filter,
        'tokens': CallyzerToken.objects.filter(is_active=True),
    }

    return render(request, 'callyzer/sync_logs.html', context)


@login_required
def reports(request):
    """
    View specific Callyzer reports
    """
    # RBAC: Admin/Director and CRM Executive
    if request.user.role not in ['admin', 'director', 'crm_executive']:
        messages.error(request, "You don't have permission to view reports.")
        return redirect('accounts:home')

    report_type = request.GET.get('type', 'call_history')
    token_id = request.GET.get('token_id', '')
    search_q = request.GET.get('q', '').strip()
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    tokens = CallyzerToken.objects.filter(is_active=True)

    context = {
        'page_title': 'Callyzer Reports',
        'report_type': report_type,
        'tokens': tokens,
        'search_q': search_q,
        'start_date': start_date,
        'end_date': end_date,
        'token_id': token_id,
    }

    def _filter_token(qs):
        if token_id:
            qs = qs.filter(token_id=token_id)
        return qs

    if report_type == 'call_history':
        qs = CallHistory.objects.all().order_by('-call_date', '-call_time')
        qs = _filter_token(qs)
        if start_date:
            qs = qs.filter(call_date__gte=start_date)
        if end_date:
            qs = qs.filter(call_date__lte=end_date)
        if search_q:
            qs = qs.filter(
                Q(emp_name__icontains=search_q) |
                Q(client_name__icontains=search_q) |
                Q(client_number__icontains=search_q)
            )
        paginator = Paginator(qs, 100)
        context['page_obj'] = paginator.get_page(request.GET.get('page', 1))
        context['report_title'] = 'Call History'

    elif report_type == 'never_attended':
        qs = NeverAttendedCall.objects.all().order_by('-call_date', '-call_time')
        qs = _filter_token(qs)
        if start_date:
            qs = qs.filter(call_date__gte=start_date)
        if end_date:
            qs = qs.filter(call_date__lte=end_date)
        if search_q:
            qs = qs.filter(
                Q(emp_name__icontains=search_q) |
                Q(client_name__icontains=search_q) |
                Q(client_number__icontains=search_q)
            )
        paginator = Paginator(qs, 100)
        context['page_obj'] = paginator.get_page(request.GET.get('page', 1))
        context['report_title'] = 'Never Attended Calls'

    elif report_type == 'not_picked_up':
        qs = NotPickedUpCall.objects.all().order_by('-call_date', '-call_time')
        qs = _filter_token(qs)
        if start_date:
            qs = qs.filter(call_date__gte=start_date)
        if end_date:
            qs = qs.filter(call_date__lte=end_date)
        if search_q:
            qs = qs.filter(
                Q(emp_name__icontains=search_q) |
                Q(client_name__icontains=search_q) |
                Q(client_number__icontains=search_q)
            )
        paginator = Paginator(qs, 100)
        context['page_obj'] = paginator.get_page(request.GET.get('page', 1))
        context['report_title'] = 'Not Picked Up By Client'

    elif report_type == 'unique_clients':
        qs = UniqueClient.objects.all().order_by('-total_calls')
        qs = _filter_token(qs)
        if search_q:
            qs = qs.filter(
                Q(client_name__icontains=search_q) |
                Q(client_number__icontains=search_q)
            )
        paginator = Paginator(qs, 100)
        context['page_obj'] = paginator.get_page(request.GET.get('page', 1))
        context['report_title'] = 'Unique Clients'

    elif report_type == 'employee_summary':
        qs = EmployeeSummary.objects.all().order_by('-total_calls')
        qs = _filter_token(qs)
        if search_q:
            qs = qs.filter(emp_name__icontains=search_q)
        paginator = Paginator(qs, 100)
        context['page_obj'] = paginator.get_page(request.GET.get('page', 1))
        context['report_title'] = 'Employee Summary'

    elif report_type == 'overall_summary':
        summaries = CallSummary.objects.all().order_by('-synced_at')
        summaries = _filter_token(summaries)
        context['summaries'] = summaries
        context['report_title'] = 'Overall Summary'

    elif report_type == 'call_analysis':
        analyses = CallAnalysis.objects.all().order_by('-synced_at')
        analyses = _filter_token(analyses)
        context['analyses'] = analyses
        context['report_title'] = 'Call Analysis'

    elif report_type == 'hourly_analytics':
        qs = HourlyAnalytic.objects.all().order_by('hour')
        qs = _filter_token(qs)
        context['analytics'] = qs
        context['report_title'] = 'Hourly Analytics'

    elif report_type == 'daily_analytics':
        qs = DailyAnalytic.objects.all().order_by('-date')
        qs = _filter_token(qs)
        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)
        paginator = Paginator(qs, 100)
        context['page_obj'] = paginator.get_page(request.GET.get('page', 1))
        context['report_title'] = 'Daily Analytics'

    return render(request, 'callyzer/reports.html', context)


# ─── Sync Progress Polling ────────────────────────────────────────────────────

@login_required
def sync_progress(request, token_id):
    LEVEL_ICON = {
        'DEBUG': '🔍', 'INFO': 'ℹ️', 'SUCCESS': '✅',
        'WARNING': '⚠️', 'ERROR': '❌', 'CRITICAL': '🔥'
    }

    # Always fetch the most recent batch log (running OR completed/failed)
    batch = SyncLog.objects.filter(
        integration='callyzer', log_kind='batch',
    ).order_by('-started_at').first()

    if not batch:
        return JsonResponse({
            'status': 'idle',
            'progress_percentage': 0,
            'message': 'No sync runs yet',
            'server_logs': [],
            'can_start': True,
            'can_stop': False,
        })

    # Get operation logs ordered chronologically for the log panel
    operation_logs = SyncLog.objects.filter(
        batch=batch, log_kind='operation'
    ).order_by('started_at')

    server_logs = []
    for op_log in operation_logs:
        ts = timezone.localtime(op_log.started_at).strftime('%H:%M:%S')
        icon = LEVEL_ICON.get(op_log.level, '')
        line = f"[{ts}] {icon} {op_log.operation}"
        if op_log.message:
            line += f": {op_log.message}"
        if op_log.duration_ms:
            line += f" ({op_log.duration_ms}ms)"
        server_logs.append(line)

    status = batch.status

    if status == 'running':
        message = f"Syncing {batch.current_module}..." if batch.current_module else 'Syncing...'
    elif status == 'completed':
        records = batch.total_records_synced or 0
        message = f'✅ Sync complete — {records} records synced'
    elif status == 'failed':
        message = f'❌ Sync failed: {batch.error_message or "unknown error"}'
    elif status in ('stopped', 'stopping'):
        message = '⏹️ Sync stopped'
    else:
        message = status

    return JsonResponse({
        'status': status,
        'progress_percentage': batch.overall_progress_percent or (100 if status == 'completed' else 0),
        'current_status': message,
        'message': message,
        'sync_id': batch.id,
        'server_logs': server_logs,
        'stop_requested': batch.stop_requested,
        'can_start': status not in ['running', 'stopping'],
        'can_stop': status == 'running',
        'current_module': batch.current_module,
        'records_synced': batch.total_records_synced or 0,
    })


# ─── Stop / Force-Stop Sync ───────────────────────────────────────────────────

@login_required
def stop_sync(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if request.user.role not in ['admin', 'director']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    sync_id = request.POST.get('sync_id')
    if not sync_id:
        return JsonResponse({'error': 'sync_id is required'}, status=400)
    try:
        sync_log = SyncLog.objects.get(id=sync_id, integration='callyzer', log_kind='batch')
    except SyncLog.DoesNotExist:
        return JsonResponse({'error': f'Sync {sync_id} not found'}, status=404)
    if sync_log.status != 'running':
        return JsonResponse({'error': f'Sync is not running (status: {sync_log.status})'}, status=400)
    sync_log.stop_requested = True
    sync_log.save(update_fields=['stop_requested'])
    logger.info(f"[Callyzer] Stop requested for sync {sync_id} by {request.user}")
    return JsonResponse({'status': 'success', 'message': 'Stop requested. Sync will finish current report then stop.'})


@login_required
def force_stop_sync(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if request.user.role not in ['admin', 'director']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    sync_id = request.POST.get('sync_id')
    try:
        if sync_id:
            sync_log = SyncLog.objects.get(id=sync_id, integration='callyzer', log_kind='batch')
        else:
            sync_log = SyncLog.objects.filter(
                integration='callyzer', log_kind='batch'
            ).order_by('-started_at').first()
            if not sync_log:
                return JsonResponse({'error': 'No sync log found'}, status=404)
    except SyncLog.DoesNotExist:
        return JsonResponse({'error': f'Sync {sync_id} not found'}, status=404)
    elapsed = int((timezone.now() - sync_log.started_at).total_seconds())
    sync_log.status = 'stopped'
    sync_log.stop_requested = True
    sync_log.completed_at = timezone.now()
    sync_log.duration_seconds = elapsed
    sync_log.error_message = f'Force-stopped by {request.user} after {elapsed}s'
    sync_log.save()
    logger.warning(f"[Callyzer] Force-stopped sync {sync_log.id} by {request.user} after {elapsed}s")
    return JsonResponse({'status': 'success', 'message': f'Sync force-stopped after {elapsed}s.'})


@login_required
def api_sync_logs(request, batch_id):
    """
    API endpoint to fetch detailed operation logs for a specific sync batch.

    Args:
        batch_id: SyncLog batch ID

    Returns:
        JSON with operation-level logs
    """
    try:
        # Get the batch log
        batch_log = SyncLog.objects.get(pk=batch_id, integration='callyzer', log_kind='batch')

        # Get all operation logs for this batch
        operation_logs = SyncLog.objects.filter(
            batch=batch_log,
            log_kind='operation'
        ).order_by('started_at')

        # Format logs for frontend
        logs = []
        for op_log in operation_logs:
            logs.append({
                'id': op_log.id,
                'timestamp': timezone.localtime(op_log.started_at).strftime('%H:%M:%S'),
                'level': op_log.level,
                'operation': op_log.operation,
                'message': op_log.message or '',
                'duration_ms': op_log.duration_ms
            })

        return JsonResponse({
            'logs': logs,
            'batch_status': batch_log.status,
            'batch_started': batch_log.started_at.isoformat(),
            'batch_completed': batch_log.completed_at.isoformat() if batch_log.completed_at else None
        })

    except SyncLog.DoesNotExist:
        return JsonResponse({'error': 'Sync log not found'}, status=404)
    except Exception as e:
        logger.error(f"Failed to fetch sync logs: {e}")
        return JsonResponse({'error': str(e)}, status=500)
