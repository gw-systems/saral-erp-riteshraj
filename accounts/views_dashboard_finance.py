"""
Finance Dashboard View
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncMonth

from accounts.models import User
from projects.models import ProjectCode
from operations.models import MonthlyBilling
from operations.models_adhoc import AdhocBillingEntry


@login_required
def finance_dashboard(request):
    """
    Finance Dashboard
    General finance view with revenue and billing overview
    """
    # Role check - Allow multiple finance-related roles
    allowed_roles = ['finance_manager', 'admin', 'super_user', 'director']
    if request.user.role not in allowed_roles:
        messages.error(request, "Access denied. Finance access required.")
        return redirect('accounts:dashboard')
    
    # Date context
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)
    current_quarter_start = today.replace(month=((today.month-1)//3)*3+1, day=1)
    current_year_start = today.replace(month=1, day=1)
    
    # ==================== REVENUE OVERVIEW ====================
    
    # Monthly revenue
    monthly_revenue_data = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start,
        event_date__lte=today,
        status__in=['billed', 'approved']
    ).aggregate(
        total=Sum('total_client_amount')
    )
    
    monthly_revenue = float(monthly_revenue_data['total'] or 0) / 100000
    
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
    
    # Adhoc Billing — 1 aggregate instead of 5 queries
    _fin_adhoc_agg = AdhocBillingEntry.objects.aggregate(
        pending_count=Count('id', filter=Q(status='pending')),
        approved_count=Count('id', filter=Q(status='approved')),
        billed_count=Count('id', filter=Q(status='billed')),
        pending_amount=Sum('total_client_amount', filter=Q(status='pending')),
        approved_amount=Sum('total_client_amount', filter=Q(status='approved')),
    )
    adhoc_pending = _fin_adhoc_agg['pending_count']
    adhoc_approved = _fin_adhoc_agg['approved_count']
    adhoc_billed = _fin_adhoc_agg['billed_count']
    adhoc_pending_amount = float(_fin_adhoc_agg['pending_amount'] or 0) / 100000
    adhoc_approved_amount = float(_fin_adhoc_agg['approved_amount'] or 0) / 100000

    # Monthly Billing — 1 aggregate instead of 3 queries
    _fin_billing_agg = MonthlyBilling.objects.filter(
        billing_month__gte=current_month_start
    ).aggregate(
        generated=Count('id', filter=Q(status='generated')),
        sent=Count('id', filter=Q(status='sent')),
        paid=Count('id', filter=Q(status='paid')),
    )
    billing_generated = _fin_billing_agg['generated']
    billing_sent = _fin_billing_agg['sent']
    billing_paid = _fin_billing_agg['paid']
    
    # ==================== REVENUE BY SERIES ====================
    
    # Revenue by series — 1 batch query instead of 6
    _series_agg = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start,
        status__in=['billed', 'approved']
    ).values('project__series_type').annotate(
        total=Sum('total_client_amount')
    )
    _series_totals = {row['project__series_type']: float(row['total'] or 0) / 100000 for row in _series_agg}

    revenue_by_series = []
    for series in ['WAAS', 'SAAS', 'GW']:
        series_amount = _series_totals.get(series, 0)
        series_percentage = round((series_amount / monthly_revenue * 100), 1) if monthly_revenue > 0 else 0
        revenue_by_series.append({
            'series': series,
            'amount': series_amount,
            'percentage': series_percentage
        })
    
    # ==================== TOP CLIENTS ====================
    
    # Top clients by revenue
    top_clients_revenue = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start,
        status__in=['billed', 'approved']
    ).values('project__client_name').annotate(
        revenue=Sum('total_client_amount')
    ).order_by('-revenue')[:10]
    
    top_clients_list = []
    for idx, client in enumerate(top_clients_revenue, 1):
        amount = float(client['revenue'] or 0) / 100000
        
        top_clients_list.append({
            'rank': idx,
            'name': client['project__client_name'],
            'revenue': amount
        })
    
    # ==================== REVENUE TREND ====================
    
    # Revenue trend (last 6 months) — 1 batch query instead of 6
    _fin_six_months_ago = (today - timedelta(days=5*30)).replace(day=1)
    _fin_monthly_rev = dict(
        AdhocBillingEntry.objects.filter(
            event_date__gte=_fin_six_months_ago,
            status__in=['billed', 'approved']
        ).annotate(
            month=TruncMonth('event_date')
        ).values('month').annotate(
            total=Sum('total_client_amount')
        ).values_list('month', 'total')
    )

    revenue_trend_6months = []
    for i in range(5, -1, -1):
        month_date = (today - timedelta(days=i*30)).replace(day=1)
        month_total = _fin_monthly_rev.get(month_date, 0)
        month_amount = float(month_total or 0) / 100000
        revenue_trend_6months.append({
            'month': month_date.strftime('%b %y'),
            'amount': month_amount
        })
    
    # ==================== PROJECT METRICS ====================
    
    # Active projects
    active_projects = ProjectCode.objects.filter(project_status='Active').count()
    
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
        'billing_generated': billing_generated,
        'billing_sent': billing_sent,
        'billing_paid': billing_paid,
        
        # Revenue Distribution
        'revenue_by_series': revenue_by_series,
        'top_clients_revenue': top_clients_list,
        
        # Revenue Trend
        'revenue_trend_6months': revenue_trend_6months,
        
        # Projects
        'active_projects': active_projects,
    }

    # Add default date range for TallySync date pickers (previous month)
    first_of_current = today.replace(day=1)
    last_of_prev = first_of_current - timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    context['default_from_date'] = first_of_prev.strftime('%Y-%m-%d')
    context['default_to_date'] = last_of_prev.strftime('%Y-%m-%d')

    return render(request, 'tallysync/finance_dashboard.html', context)