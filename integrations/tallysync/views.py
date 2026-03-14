from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum, Count, Q
from integrations.tallysync.models import (
    TallyVoucher, TallyCompany, TallyVoucherCostCentreAllocation,
    VarianceAlert
)
from integrations.models import SyncLog
from operations.models import MonthlyBilling
from datetime import datetime, timedelta
from django.contrib import messages
from django.utils import timezone
import logging


def _default_date_context():
    """Return default from/to dates for TallySync dashboards (previous month)."""
    today = timezone.now().date()
    first_of_current = today.replace(day=1)
    last_of_prev = first_of_current - timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    return {
        'default_from_date': first_of_prev.strftime('%Y-%m-%d'),
        'default_to_date': last_of_prev.strftime('%Y-%m-%d'),
    }

logger = logging.getLogger(__name__)


@login_required
def reconciliation_dashboard(request):
    """Main reconciliation dashboard"""
    
    # Get filter parameters
    month = request.GET.get('month')
    year = request.GET.get('year')
    company_id = request.GET.get('company')
    
    # Base querysets
    tally_vouchers = TallyVoucher.objects.filter(voucher_type='Sales')
    erp_billings = MonthlyBilling.objects.all()
    
    # Apply filters
    if month and year:
        tally_vouchers = tally_vouchers.filter(
            date__year=year,
            date__month=month
        )
        billing_month = datetime(int(year), int(month), 1).date()
        erp_billings = erp_billings.filter(billing_month=billing_month)
    
    if company_id:
        tally_vouchers = tally_vouchers.filter(company_id=company_id)
    
    # Calculate summary stats
    tally_total = tally_vouchers.aggregate(total=Sum('amount'))['total'] or 0
    erp_total = erp_billings.aggregate(total=Sum('client_total'))['total'] or 0
    variance = abs(tally_total - erp_total)
    variance_pct = (variance / erp_total * 100) if erp_total > 0 else 0
    
    # Count matched/unmatched
    matched_vouchers = tally_vouchers.filter(
        Q(erp_monthly_billing__isnull=False) | Q(erp_adhoc_billing__isnull=False)
    ).count()
    unmatched_vouchers = tally_vouchers.filter(
        erp_monthly_billing__isnull=True,
        erp_adhoc_billing__isnull=True
    ).count()
    
    matched_erp = erp_billings.filter(tally_vouchers__isnull=False).distinct().count()
    unmatched_erp = erp_billings.filter(tally_vouchers__isnull=True).count()
    
    # Get companies for filter
    companies = TallyCompany.objects.all()
    
    # Recent variances
    recent_alerts = VarianceAlert.objects.filter(
        status='open'
    ).order_by('-created_at')[:10]
    
    context = {
        'tally_total': tally_total,
        'erp_total': erp_total,
        'variance': variance,
        'variance_pct': variance_pct,
        'matched_vouchers': matched_vouchers,
        'unmatched_vouchers': unmatched_vouchers,
        'matched_erp': matched_erp,
        'unmatched_erp': unmatched_erp,
        'total_vouchers': tally_vouchers.count(),
        'total_erp': erp_billings.count(),
        'companies': companies,
        'recent_alerts': recent_alerts,
        'selected_month': month,
        'selected_year': year,
        'selected_company': company_id,
    }
    
    return render(request, 'tallysync/reconciliation_dashboard.html', context)


@login_required
def reconciliation_detail(request):
    """Detailed reconciliation table"""
    
    # Get filters
    month = request.GET.get('month')
    year = request.GET.get('year')
    company_id = request.GET.get('company')
    status = request.GET.get('status', 'all')
    
    # Get vouchers with cost centre allocations
    vouchers = TallyVoucher.objects.filter(
        voucher_type='Sales'
    ).select_related('company').prefetch_related(
        'cost_allocations__cost_centre__erp_project'
    )
    
    # Apply filters
    if month and year:
        vouchers = vouchers.filter(date__year=year, date__month=month)
    if company_id:
        vouchers = vouchers.filter(company_id=company_id)
    
    # Status filter
    if status == 'matched':
        vouchers = vouchers.filter(
            Q(erp_monthly_billing__isnull=False) | Q(erp_adhoc_billing__isnull=False)
        )
    elif status == 'unmatched_tally':
        vouchers = vouchers.filter(
            erp_monthly_billing__isnull=True,
            erp_adhoc_billing__isnull=True
        )
    
    # Prepare data with ERP matching info
    voucher_data = []
    for voucher in vouchers:
        # Get cost centre allocation
        allocation = voucher.cost_allocations.first()
        erp_project = allocation.cost_centre.erp_project if allocation and allocation.cost_centre else None
        
        voucher_data.append({
            'voucher': voucher,
            'allocation': allocation,
            'erp_project': erp_project,
            'is_matched': voucher.erp_monthly_billing is not None or voucher.erp_adhoc_billing is not None
        })
    
    # Get unmatched ERP billings
    unmatched_erp = []
    if status in ['all', 'unmatched_erp']:
        erp_query = MonthlyBilling.objects.filter(
            tally_vouchers__isnull=True
        ).select_related('project')
        
        if month and year:
            billing_month = datetime(int(year), int(month), 1).date()
            erp_query = erp_query.filter(billing_month=billing_month)
        
        unmatched_erp = erp_query[:50]
    
    companies = TallyCompany.objects.all()
    
    context = {
        'voucher_data': voucher_data,
        'unmatched_erp': unmatched_erp,
        'companies': companies,
        'selected_month': month,
        'selected_year': year,
        'selected_company': company_id,
        'selected_status': status,
    }
    
    return render(request, 'tallysync/reconciliation_detail.html', context)


@login_required
def reconciliation_detail(request):
    """Reconciliation detail view"""
    context = {
        'page_title': 'Reconciliation Detail'
    }
    return render(request, 'tallysync/reconciliation_detail.html', context)


@login_required
def project_profitability_dashboard(request):
    """Project profitability dashboard.
    Supports ?client_names=X,Y and ?vendor_names=X,Y for drill-down from client/vendor dashboards.
    """
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')

    context = {
        'page_title': 'Project Profitability Dashboard',
        'filter_client_names': request.GET.get('client_names', ''),
        'filter_vendor_names': request.GET.get('vendor_names', ''),
        **_default_date_context(),
    }
    return render(request, 'tallysync/project_profitability.html', context)


@login_required
def project_detail(request, project_id):
    """Project detail view - detailed P&L for a single project"""
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')

    context = {
        'page_title': 'Project Detail',
        'project_id': project_id,
    }
    return render(request, 'tallysync/project_detail.html', context)


@login_required
def client_profitability_dashboard(request):
    """Client profitability dashboard"""
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')

    context = {
        'page_title': 'Client Profitability Dashboard',
        **_default_date_context(),
    }
    return render(request, 'tallysync/client_profitability.html', context)


@login_required
def vendor_profitability_dashboard(request):
    """Vendor profitability dashboard"""
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')

    context = {
        'page_title': 'Vendor Profitability Dashboard',
        **_default_date_context(),
    }
    return render(request, 'tallysync/vendor_profitability.html', context)


@login_required
def cost_centre_profitability_dashboard(request):
    """Cost centre (project code) profitability dashboard"""
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')

    context = {
        'page_title': 'Cost Centre Profitability',
        **_default_date_context(),
    }
    return render(request, 'tallysync/cost_centre_profitability.html', context)


@login_required
def cash_liquidity_dashboard(request):
    """Cash & liquidity dashboard"""
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')
    
    context = {
        'page_title': 'Cash & Liquidity Dashboard',
        **_default_date_context(),
    }
    return render(request, 'tallysync/cash_liquidity.html', context)


@login_required
def aging_report_dashboard(request):
    """Aging report dashboard — party-wise receivables & payables aging"""
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')

    context = {
        'page_title': 'Aging Report',
    }
    return render(request, 'tallysync/aging_report.html', context)


@login_required
def gst_compliance_dashboard(request):
    """GST compliance dashboard"""
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')

    context = {
        'page_title': 'GST Compliance Dashboard',
        **_default_date_context(),
    }
    return render(request, 'tallysync/gst_compliance.html', context)


@login_required
def operations_dashboard(request):
    """Operations analytics dashboard"""
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')

    context = {
        'page_title': 'Operations Analytics Dashboard',
        **_default_date_context(),
    }
    return render(request, 'tallysync/operations.html', context)


@login_required
def vendor_detail_dashboard(request, vendor_name):
    """Vendor detail: project-wise breakdown with voucher drill-down"""
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')

    date_ctx = _default_date_context()
    if request.GET.get('from_date'):
        date_ctx['default_from_date'] = request.GET['from_date']
    if request.GET.get('to_date'):
        date_ctx['default_to_date'] = request.GET['to_date']

    context = {
        'vendor_name': vendor_name,
        **date_ctx,
    }
    return render(request, 'tallysync/vendor_detail.html', context)


@login_required
def salesperson_detail_dashboard(request, salesperson_name):
    """Salesperson detail: client-wise breakdown with voucher drill-down"""
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')

    date_ctx = _default_date_context()
    # Allow pre-filling dates from query params (passed by operations.html link)
    if request.GET.get('from_date'):
        date_ctx['default_from_date'] = request.GET['from_date']
    if request.GET.get('to_date'):
        date_ctx['default_to_date'] = request.GET['to_date']

    context = {
        'salesperson_name': salesperson_name,
        **date_ctx,
    }
    return render(request, 'tallysync/salesperson_detail.html', context)


@login_required
def sales_financial_detail(request):
    """
    Detailed financial report page showing all projects in a table.
    Accessible to Sales Managers and CRM Executives.
    """
    return render(request, 'tallysync/sales_financial_detail.html', {
        'today': timezone.now().date(),
        **_default_date_context(),
    })


def test_library(request):
    """Test page for TallySync library"""
    return render(request, 'test_tallysync_lib.html')


@login_required
def settings(request):
    """
    Settings page for TallySync integration - manage sync and connection.
    Admin/Director only.
    """
    from django.contrib import messages

    # Check if user is admin or director
    if request.user.role not in ['admin', 'director']:
        messages.error(request, "Access denied. Admin or Director access required.")
        return redirect('accounts:dashboard')

    # Check if TallySync has been configured (check for any records)
    from integrations.tallysync.models import TallyVoucher, TallyCompany

    companies = TallyCompany.objects.all()
    is_connected = companies.exists()

    # Get sync status from SyncLog
    running_sync = SyncLog.objects.filter(
        integration='tallysync', log_kind='batch', status='running'
    ).order_by('-started_at').first()

    is_syncing = running_sync is not None
    sync_progress = running_sync.overall_progress_percent if running_sync else 0
    sync_id = running_sync.id if running_sync else None

    # Get last completed sync
    last_completed = SyncLog.objects.filter(
        integration='tallysync', log_kind='batch', status='completed'
    ).order_by('-completed_at').first()

    # Get record counts
    vouchers_count = TallyVoucher.objects.count()
    invoices_count = TallyVoucher.objects.filter(is_invoice=True).count()

    context = {
        'is_connected': is_connected,
        'companies': companies,
        'is_syncing': is_syncing,
        'sync_progress': sync_progress,
        'sync_id': sync_id,
        'last_completed_sync': last_completed,
        'vouchers_count': vouchers_count,
        'invoices_count': invoices_count,
    }

    return render(request, 'tallysync/settings.html', context)


# ─── Sync Progress Polling ────────────────────────────────────────────────────

@login_required
def sync_progress(request):
    """
    Get sync progress for TallySync.
    Returns JSON with current sync status and operation-level activity log.
    """
    batch = SyncLog.objects.filter(
        integration='tallysync',
        log_kind='batch',
        status__in=['running', 'stopping']
    ).order_by('-started_at').first()

    # If no batch running, return idle state
    if not batch:
        return JsonResponse({
            'status': 'idle',
            'progress_percentage': 0,
            'message': 'No sync running',
            'server_logs': [],
            'can_start': True,
            'can_stop': False,
        })

    # Get operation logs for activity log
    operation_logs = SyncLog.objects.filter(
        batch=batch,
        log_kind='operation'
    ).order_by('-started_at')[:50]

    # Format activity log with timestamps and icons
    activity_log = []
    for op_log in reversed(operation_logs):
        timestamp = timezone.localtime(op_log.started_at).strftime('%H:%M:%S')
        level_icon = {'DEBUG': '🔍', 'INFO': 'ℹ️', 'SUCCESS': '✅', 'WARNING': '⚠️', 'ERROR': '❌', 'CRITICAL': '🔥'}.get(op_log.level, '')
        message = f"{level_icon} {op_log.operation}"
        if op_log.message:
            message += f": {op_log.message}"
        activity_log.append({'timestamp': timestamp, 'message': message})

    # Build server_logs from activity_log
    server_logs = [
        f"{log['timestamp']} - {log['message']}"
        for log in activity_log
    ]

    # Add UI control states
    status = batch.status
    can_start = status not in ['running', 'stopping']
    can_stop = status == 'running'

    return JsonResponse({
        'status': 'in_progress',
        'progress_percentage': batch.overall_progress_percent,
        'current_status': batch.current_module or 'Syncing...',
        'message': batch.current_module or 'Syncing...',
        'sync_id': batch.id,
        'activity_log': activity_log,
        'server_logs': server_logs,
        'stop_requested': batch.stop_requested,
        'total_records_synced': batch.total_records_synced,
        'records_created': batch.records_created,
        'records_updated': batch.records_updated,
        'errors_count': batch.errors_count,
        'can_start': can_start,
        'can_stop': can_stop,
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
        sync_log = SyncLog.objects.get(id=sync_id, integration='tallysync', log_kind='batch')
    except SyncLog.DoesNotExist:
        return JsonResponse({'error': f'Sync {sync_id} not found'}, status=404)
    if sync_log.status != 'running':
        return JsonResponse({'error': f'Sync is not running (status: {sync_log.status})'}, status=400)
    sync_log.stop_requested = True
    sync_log.save(update_fields=['stop_requested'])
    logger.info(f"[TallySync] Stop requested for sync {sync_id} by {request.user}")
    return JsonResponse({'status': 'success', 'message': 'Stop requested. Sync will finish current entity then stop.'})


@login_required
def force_stop_sync(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if request.user.role not in ['admin', 'director']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    sync_id = request.POST.get('sync_id')
    try:
        if sync_id:
            sync_log = SyncLog.objects.get(id=sync_id, integration='tallysync', log_kind='batch')
        else:
            sync_log = SyncLog.objects.filter(
                integration='tallysync', log_kind='batch'
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
    logger.warning(f"[TallySync] Force-stopped sync {sync_log.id} by {request.user} after {elapsed}s")
    return JsonResponse({'status': 'success', 'message': f'Sync force-stopped after {elapsed}s.'})