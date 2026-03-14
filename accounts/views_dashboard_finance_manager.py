"""
Finance Manager Dashboard View
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Q, Avg, F
from django.db.models.functions import TruncMonth

from accounts.models import User
from projects.models import ProjectCode
from operations.models import MonthlyBilling
from operations.models_adhoc import AdhocBillingEntry


@login_required
def finance_manager_dashboard(request):
    """
    Finance Manager Dashboard
    Focused on financial metrics, revenue tracking, and billing oversight
    """
    # Role check
    if request.user.role not in ['finance_manager', 'admin', 'director']:
        messages.error(request, "Access denied. Finance Manager access required.")
        return redirect('accounts:dashboard')
    
    # Date context
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)
    current_quarter_start = today.replace(month=((today.month-1)//3)*3+1, day=1)
    current_year_start = today.replace(month=1, day=1)
    
    # ==================== REVENUE METRICS ====================
    
    # Monthly revenue (from Adhoc Billing)
    monthly_revenue_data = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start,
        event_date__lte=today,
        status__in=['billed', 'approved']
    ).aggregate(
        total=Sum('total_client_amount')
    )
    
    monthly_revenue = float(monthly_revenue_data['total'] or 0) / 100000  # Lakhs
    
    # Last month revenue
    last_month_revenue_data = AdhocBillingEntry.objects.filter(
        event_date__gte=last_month_start,
        event_date__lte=last_month_end,
        status__in=['billed', 'approved']
    ).aggregate(
        total=Sum('total_client_amount')
    )
    
    last_month_revenue = float(last_month_revenue_data['total'] or 0) / 100000
    
    # Revenue growth
    if last_month_revenue > 0:
        revenue_growth = round(
            ((monthly_revenue - last_month_revenue) / last_month_revenue) * 100, 1
        )
    else:
        revenue_growth = 0
    
    # Quarterly revenue
    quarterly_revenue_data = AdhocBillingEntry.objects.filter(
        event_date__gte=current_quarter_start,
        event_date__lte=today,
        status__in=['billed', 'approved']
    ).aggregate(
        total=Sum('total_client_amount')
    )
    
    quarterly_revenue = float(quarterly_revenue_data['total'] or 0) / 100000
    
    # Yearly revenue
    yearly_revenue_data = AdhocBillingEntry.objects.filter(
        event_date__gte=current_year_start,
        event_date__lte=today,
        status__in=['billed', 'approved']
    ).aggregate(
        total=Sum('total_client_amount')
    )
    
    yearly_revenue = float(yearly_revenue_data['total'] or 0) / 100000
    
    # ==================== BILLING STATUS ====================
    
    # Adhoc Billing — 1 aggregate instead of 7 queries
    _fm_adhoc_agg = AdhocBillingEntry.objects.aggregate(
        pending_count=Count('id', filter=Q(status='pending')),
        approved_count=Count('id', filter=Q(status='approved')),
        billed_count=Count('id', filter=Q(status='billed')),
        pending_amount=Sum('total_client_amount', filter=Q(status='pending')),
        approved_amount=Sum('total_client_amount', filter=Q(status='approved')),
        billed_amount=Sum('total_client_amount', filter=Q(status='billed')),
        pending_old=Count('id', filter=Q(status='pending', event_date__lt=today - timedelta(days=30))),
    )
    adhoc_pending = _fm_adhoc_agg['pending_count']
    adhoc_approved = _fm_adhoc_agg['approved_count']
    adhoc_billed = _fm_adhoc_agg['billed_count']
    adhoc_pending_amount = float(_fm_adhoc_agg['pending_amount'] or 0) / 100000
    adhoc_approved_amount = float(_fm_adhoc_agg['approved_amount'] or 0) / 100000
    adhoc_billed_amount = float(_fm_adhoc_agg['billed_amount'] or 0) / 100000
    adhoc_pending_old = _fm_adhoc_agg['pending_old']

    # Monthly Billing — 1 aggregate instead of 4 queries
    _fm_billing_agg = MonthlyBilling.objects.filter(
        billing_month__gte=current_month_start
    ).aggregate(
        generated=Count('id', filter=Q(status='generated')),
        sent=Count('id', filter=Q(status='sent')),
        pending=Count('id', filter=Q(status='pending')),
        paid=Count('id', filter=Q(status='paid')),
    )
    billing_generated = _fm_billing_agg['generated']
    billing_sent = _fm_billing_agg['sent']
    billing_pending = _fm_billing_agg['pending']
    billing_paid = _fm_billing_agg['paid']
    
    # ==================== REVENUE BY SERIES ====================
    
    # Revenue by series type — 1 batch query instead of 6
    _fm_series_agg = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start,
        status__in=['billed', 'approved']
    ).values('project__series_type').annotate(
        total=Sum('total_client_amount')
    )
    _fm_series_totals = {row['project__series_type']: float(row['total'] or 0) / 100000 for row in _fm_series_agg}

    revenue_by_series = []
    for series in ['WAAS', 'SAAS', 'GW']:
        series_amount = _fm_series_totals.get(series, 0)
        series_percentage = round((series_amount / monthly_revenue * 100), 1) if monthly_revenue > 0 else 0
        revenue_by_series.append({
            'series': series,
            'amount': series_amount,
            'percentage': series_percentage
        })
    
    # ==================== REVENUE BY CLIENT ====================
    
    # Top clients by revenue (this month)
    top_clients_revenue = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start,
        status__in=['billed', 'approved']
    ).values('project__client_name').annotate(
        revenue=Sum('total_client_amount')
    ).order_by('-revenue')[:10]
    
    top_clients_list = []
    for idx, client in enumerate(top_clients_revenue, 1):
        amount = float(client['revenue'] or 0) / 100000
        percentage = round((amount / monthly_revenue * 100), 1) if monthly_revenue > 0 else 0
        
        top_clients_list.append({
            'rank': idx,
            'name': client['project__client_name'],
            'revenue': amount,
            'percentage': percentage
        })
    
    # ==================== REVENUE BY STATE ====================
    
    # Top states by revenue (this month)
    top_states_revenue = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start,
        status__in=['billed', 'approved']
    ).values('project__state').annotate(
        revenue=Sum('total_client_amount')
    ).order_by('-revenue')[:10]
    
    top_states_list = []
    for state in top_states_revenue:
        amount = float(state['revenue'] or 0) / 100000
        percentage = round((amount / monthly_revenue * 100), 1) if monthly_revenue > 0 else 0
        
        top_states_list.append({
            'state': state['project__state'],
            'revenue': amount,
            'percentage': percentage
        })
    
    # ==================== REVENUE TREND ====================
    
    # Revenue trend (last 12 months) — 1 batch query instead of 12
    _fm_twelve_months_ago = (today - timedelta(days=11*30)).replace(day=1)
    _fm_monthly_rev = dict(
        AdhocBillingEntry.objects.filter(
            event_date__gte=_fm_twelve_months_ago,
            status__in=['billed', 'approved']
        ).annotate(
            month=TruncMonth('event_date')
        ).values('month').annotate(
            total=Sum('total_client_amount')
        ).values_list('month', 'total')
    )

    revenue_trend_12months = []
    for i in range(11, -1, -1):
        month_date = (today - timedelta(days=i*30)).replace(day=1)
        month_total = _fm_monthly_rev.get(month_date, 0)
        month_amount = float(month_total or 0) / 100000
        revenue_trend_12months.append({
            'month': month_date.strftime('%b'),
            'year': month_date.strftime('%y'),
            'amount': month_amount
        })
    
    # ==================== PAYMENT COLLECTION ====================
    
    # Payments collected this month
    payments_collected = monthly_revenue  # Simplified - using billed amount
    
    # Pending payments (approved but not billed)
    payments_pending = adhoc_approved_amount
    
    # Overdue payments (pending > 30 days)
    payments_overdue = AdhocBillingEntry.objects.filter(
        status='pending',
        event_date__lt=today - timedelta(days=30)
    ).aggregate(total=Sum('total_client_amount'))['total'] or 0
    payments_overdue = float(payments_overdue) / 100000
    
    # Collection efficiency
    total_billable = payments_collected + payments_pending + payments_overdue
    collection_efficiency = round((payments_collected / total_billable * 100), 1) if total_billable > 0 else 0
    
    # ==================== OUTSTANDING INVOICES ====================
    
    # Top overdue invoices
    top_overdue_invoices = AdhocBillingEntry.objects.filter(
        status='pending',
        event_date__lt=today - timedelta(days=30)
    ).order_by('event_date')[:10]
    
    overdue_list = []
    for invoice in top_overdue_invoices:
        days_overdue = (today - invoice.event_date).days
        amount = float(invoice.total_client_amount or 0) / 100000
        
        overdue_list.append({
            'id': invoice.id,
            'project_id': invoice.project.project_id if invoice.project else None,
            'client_name': invoice.project.client_name if invoice.project else None,
            'event_date': invoice.event_date,
            'days_overdue': days_overdue,
            'amount': amount
        })
    
    # ==================== FINANCIAL METRICS ====================
    
    # Average transaction value
    total_transactions = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start,
        status__in=['billed', 'approved']
    ).count()
    
    avg_transaction_value = round(monthly_revenue / total_transactions, 2) if total_transactions > 0 else 0
    
    # Average revenue per project
    active_projects = ProjectCode.objects.filter(project_status='Active').count()
    avg_revenue_per_project = round(monthly_revenue / active_projects, 2) if active_projects > 0 else 0
    
    # Revenue per client
    total_clients = ProjectCode.objects.filter(project_status='Active').values('client_name').distinct().count()
    avg_revenue_per_client = round(monthly_revenue / total_clients, 2) if total_clients > 0 else 0
    
    # ==================== BILLING EFFICIENCY ====================
    
    # Average approval time (days) — DB aggregate instead of Python loop
    _fm_avg_approval = AdhocBillingEntry.objects.filter(
        status__in=['approved', 'billed'],
        created_at__isnull=False,
        updated_at__isnull=False,
        event_date__gte=current_month_start
    ).aggregate(
        avg_days=Avg(F('updated_at') - F('created_at'))
    )
    if _fm_avg_approval['avg_days']:
        avg_approval_days = round(_fm_avg_approval['avg_days'].total_seconds() / 86400, 1)
    else:
        avg_approval_days = 0
    
    # Billing cycle time
    billing_cycle_time = avg_approval_days  # Simplified
    
    # ==================== ALERTS ====================
    
    total_alerts = adhoc_pending_old + billing_pending
    
    # ==================== PROJECT METRICS ====================
    
    # Total projects
    total_projects = ProjectCode.objects.count()
    active_projects_count = ProjectCode.objects.filter(project_status='Active').count()
    
    # ==================== CONTEXT ====================
    
    context = {
        # Date
        'today': today,
        'current_time': timezone.now().strftime('%I:%M %p'),
        
        # Revenue
        'monthly_revenue': monthly_revenue,
        'last_month_revenue': last_month_revenue,
        'revenue_growth': revenue_growth,
        'quarterly_revenue': quarterly_revenue,
        'yearly_revenue': yearly_revenue,
        
        # Billing Status
        'adhoc_pending': adhoc_pending,
        'adhoc_approved': adhoc_approved,
        'adhoc_billed': adhoc_billed,
        'adhoc_pending_amount': adhoc_pending_amount,
        'adhoc_approved_amount': adhoc_approved_amount,
        'adhoc_billed_amount': adhoc_billed_amount,
        'adhoc_pending_old': adhoc_pending_old,
        'billing_generated': billing_generated,
        'billing_sent': billing_sent,
        'billing_pending': billing_pending,
        'billing_paid': billing_paid,
        
        # Revenue Distribution
        'revenue_by_series': revenue_by_series,
        'top_clients_revenue': top_clients_list,
        'top_states_revenue': top_states_list,
        
        # Revenue Trend
        'revenue_trend_12months': revenue_trend_12months,
        
        # Payment Collection
        'payments_collected': payments_collected,
        'payments_pending': payments_pending,
        'payments_overdue': payments_overdue,
        'collection_efficiency': collection_efficiency,
        'overdue_invoices': overdue_list,
        
        # Financial Metrics
        'avg_transaction_value': avg_transaction_value,
        'avg_revenue_per_project': avg_revenue_per_project,
        'avg_revenue_per_client': avg_revenue_per_client,
        'avg_approval_days': avg_approval_days,
        'billing_cycle_time': billing_cycle_time,
        
        # Alerts
        'total_alerts': total_alerts,
        
        # Projects
        'total_projects': total_projects,
        'active_projects': active_projects_count,
    }
    
    return render(request, 'dashboards/finance_manager_dashboard.html', context)