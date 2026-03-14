"""
Sales Manager Dashboard View
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count, Q, F

from accounts.models import User
from projects.models import ProjectCode
from integrations.tallysync.models import TallyVoucher, TallyCostCentre
from operations.models import MonthlyBilling
from operations.models_projectcard import ProjectCard, StorageRate
from integrations.bigin.models import BiginRecord, BiginContact


@login_required
def sales_manager_dashboard(request):
    """
    Sales Manager Dashboard - Project Performance & Profitability Focus
    Access: Sales Manager role only
    Shows: Only projects where user is sales_manager (WAAS/SAAS only, no GW)
    """
    if request.user.role not in ['sales_manager', 'admin', 'director']:
        messages.error(request, "Access denied. Sales Manager role only.")
        return redirect('accounts:dashboard')

    user_full_name = request.user.get_full_name()
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)

    # ==================== MY PROJECTS (WAAS/SAAS ONLY) ====================
    my_projects = ProjectCode.objects.filter(
        sales_manager=user_full_name,
        series_type__in=['WAAS', 'SAAS']  # Exclude GW
    ).select_related('client_card', 'vendor_warehouse')

    _proj_agg = my_projects.aggregate(
        total_projects=Count('project_id'),
        active_projects_count=Count('project_id', filter=Q(project_status='Active')),
        notice_period_projects=Count('project_id', filter=Q(project_status='Notice Period')),
        not_started_projects=Count('project_id', filter=Q(project_status='Operation Not Started')),
    )
    total_projects = _proj_agg['total_projects']
    active_projects = my_projects.filter(project_status='Active')
    active_projects_count = _proj_agg['active_projects_count']
    notice_period_projects = _proj_agg['notice_period_projects']
    not_started_projects = _proj_agg['not_started_projects']

    # ==================== REVENUE & MARGIN (MTD/YTD) ====================

    # Month-to-Date (from MonthlyBilling - approved only)
    mtd_billing = MonthlyBilling.objects.filter(
        project__in=my_projects,
        billing_month__gte=current_month_start,
        status='approved'
    ).aggregate(
        revenue=Sum('client_total'),
        cost=Sum('vendor_total'),
        margin=Sum('margin_amount')
    )

    mtd_revenue = float(mtd_billing['revenue'] or 0) / 100000  # Convert to lakhs
    mtd_cost = float(mtd_billing['cost'] or 0) / 100000
    mtd_margin = float(mtd_billing['margin'] or 0) / 100000
    mtd_margin_pct = (mtd_margin / mtd_revenue * 100) if mtd_revenue > 0 else 0

    # Year-to-Date
    year_start = today.replace(month=4, day=1) if today.month >= 4 else today.replace(year=today.year-1, month=4, day=1)

    ytd_billing = MonthlyBilling.objects.filter(
        project__in=my_projects,
        billing_month__gte=year_start,
        status='approved'
    ).aggregate(
        revenue=Sum('client_total'),
        cost=Sum('vendor_total'),
        margin=Sum('margin_amount')
    )

    ytd_revenue = float(ytd_billing['revenue'] or 0) / 100000
    ytd_cost = float(ytd_billing['cost'] or 0) / 100000
    ytd_margin = float(ytd_billing['margin'] or 0) / 100000
    ytd_margin_pct = (ytd_margin / ytd_revenue * 100) if ytd_revenue > 0 else 0

    # Last Month (for growth calculation)
    lm_billing = MonthlyBilling.objects.filter(
        project__in=my_projects,
        billing_month__gte=last_month_start,
        billing_month__lte=last_month_end,
        status='approved'
    ).aggregate(
        revenue=Sum('client_total'),
        margin=Sum('margin_amount')
    )

    lm_revenue = float(lm_billing['revenue'] or 0) / 100000
    lm_margin = float(lm_billing['margin'] or 0) / 100000

    # Growth
    revenue_growth = ((mtd_revenue - lm_revenue) / lm_revenue * 100) if lm_revenue > 0 else 0
    margin_growth = ((mtd_margin - lm_margin) / lm_margin * 100) if lm_margin > 0 else 0

    # ==================== OUTSTANDING RECEIVABLES ====================

    # Get Tally vouchers for my projects (Sales invoices not fully paid)
    my_tally_cost_centres = TallyCostCentre.objects.filter(
        erp_project__in=my_projects,
        is_matched=True
    ).values_list('id', flat=True)

    # Outstanding = Sales vouchers - Receipt vouchers (simplified)
    outstanding_sales = TallyVoucher.objects.filter(
        voucher_type='Sales',
        ledger_entries__cost_allocations__cost_centre_id__in=my_tally_cost_centres
    ).aggregate(total=Sum('amount'))['total'] or 0

    outstanding_receipts = TallyVoucher.objects.filter(
        voucher_type='Receipt',
        ledger_entries__cost_allocations__cost_centre_id__in=my_tally_cost_centres
    ).aggregate(total=Sum('amount'))['total'] or 0

    total_outstanding = (float(outstanding_sales) - float(outstanding_receipts)) / 100000

    # Outstanding by project (top 5) — pre-batch cost centres to reduce N+1
    _top_active_projects = list(active_projects[:10])
    _top_pids = [p.project_id for p in _top_active_projects]
    _cc_by_project = {}
    for cc in TallyCostCentre.objects.filter(
        erp_project_id__in=_top_pids,
        is_matched=True
    ).values('erp_project_id', 'id'):
        _cc_by_project.setdefault(cc['erp_project_id'], []).append(cc['id'])

    outstanding_by_project = []
    for project in _top_active_projects:
        project_cost_centre_ids = _cc_by_project.get(project.project_id, [])
        if project_cost_centre_ids:
            proj_sales = TallyVoucher.objects.filter(
                voucher_type='Sales',
                ledger_entries__cost_allocations__cost_centre_id__in=project_cost_centre_ids
            ).aggregate(total=Sum('amount'))['total'] or 0

            proj_receipts = TallyVoucher.objects.filter(
                voucher_type='Receipt',
                ledger_entries__cost_allocations__cost_centre_id__in=project_cost_centre_ids
            ).aggregate(total=Sum('amount'))['total'] or 0

            proj_outstanding = (float(proj_sales) - float(proj_receipts)) / 100000
            if proj_outstanding > 0:
                outstanding_by_project.append({
                    'project_code': project.project_code,
                    'project_id': project.project_id,
                    'outstanding': proj_outstanding
                })

    outstanding_by_project.sort(key=lambda x: x['outstanding'], reverse=True)
    outstanding_by_project = outstanding_by_project[:5]

    # ==================== PROJECT PERFORMANCE TABLE ====================

    # Project performance — 3 batch queries instead of 3 queries per project
    _active_projects_list = list(active_projects)
    _active_project_pids = [p.project_id for p in _active_projects_list]

    # Batch 1: latest active project card per project
    _proj_cards = {}
    for pc in ProjectCard.objects.filter(
        project_id__in=_active_project_pids,
        is_active=True
    ).order_by('project_id', '-id'):
        if pc.project_id not in _proj_cards:
            _proj_cards[pc.project_id] = pc

    # Batch 2: client storage rates for all fetched project cards
    _storage_rates = {}
    if _proj_cards:
        for sr in StorageRate.objects.filter(
            project_card_id__in=[pc.id for pc in _proj_cards.values()],
            rate_for='client'
        ):
            _storage_rates[sr.project_card_id] = sr

    # Batch 3: latest approved billing per project (order_by gives latest first per project)
    _latest_billing = {}
    for billing in MonthlyBilling.objects.filter(
        project_id__in=_active_project_pids,
        status='approved'
    ).order_by('project_id', '-billing_month').only(
        'project_id', 'billing_month', 'storage_min_space', 'storage_additional_space',
        'client_total', 'vendor_total', 'margin_amount', 'margin_percentage'
    ):
        if billing.project_id not in _latest_billing:
            _latest_billing[billing.project_id] = billing

    project_performance = []
    for project in _active_projects_list:
        project_card = _proj_cards.get(project.project_id)
        contracted_sqft = 0
        if project_card:
            sr = _storage_rates.get(project_card.id)
            if sr:
                contracted_sqft = float(sr.minimum_billable_area or 0)

        last_billing = _latest_billing.get(project.project_id)
        utilized_sqft = 0
        revenue = 0
        expenses = 0
        margin_amt = 0
        margin_pct = 0
        if last_billing:
            utilized_sqft = float(last_billing.storage_min_space or 0) + float(last_billing.storage_additional_space or 0)
            revenue = float(last_billing.client_total) / 100000
            expenses = float(last_billing.vendor_total) / 100000
            margin_amt = float(last_billing.margin_amount) / 100000
            margin_pct = float(last_billing.margin_percentage)

        utilization_pct = (utilized_sqft / contracted_sqft * 100) if contracted_sqft > 0 else 0
        outstanding_days = 0
        low_margin = margin_pct < 15
        low_utilization = utilization_pct < 70

        project_performance.append({
            'project_code': project.project_code,
            'project_id': project.project_id,
            'vendor_name': project.vendor_name,
            'status': project.project_status,
            'contracted_sqft': contracted_sqft,
            'utilized_sqft': utilized_sqft,
            'utilization_pct': utilization_pct,
            'revenue': revenue,
            'expenses': expenses,
            'margin_amt': margin_amt,
            'margin_pct': margin_pct,
            'outstanding_days': outstanding_days,
            'low_margin': low_margin,
            'low_utilization': low_utilization,
        })

    # ==================== PROJECTS AT RISK ====================

    projects_at_risk = []

    # Notice Period Projects — batch billing fetch instead of 1 query per project
    _notice_projects = list(my_projects.filter(project_status='Notice Period'))
    _notice_pids = [p.project_id for p in _notice_projects]
    _notice_billing = {}
    for billing in MonthlyBilling.objects.filter(
        project_id__in=_notice_pids,
        status='approved'
    ).order_by('project_id', '-billing_month').only('project_id', 'client_total'):
        if billing.project_id not in _notice_billing:
            _notice_billing[billing.project_id] = billing

    for project in _notice_projects:
        last_billing = _notice_billing.get(project.project_id)
        monthly_revenue = float(last_billing.client_total) / 100000 if last_billing else 0
        projected_loss = monthly_revenue * 3
        projects_at_risk.append({
            'project_code': project.project_code,
            'project_id': project.project_id,
            'risk_type': 'Notice Period',
            'risk_level': 'high',
            'monthly_revenue': monthly_revenue,
            'projected_loss': projected_loss,
            'notice_end': project.notice_period_end_date
        })

    # Low Margin Projects
    for perf in project_performance:
        if perf['margin_pct'] < 10 and perf['revenue'] > 0:
            projects_at_risk.append({
                'project_code': perf['project_code'],
                'project_id': perf['project_id'],
                'risk_type': 'Low Margin',
                'risk_level': 'medium',
                'monthly_revenue': perf['revenue'],
                'margin_pct': perf['margin_pct'],
                'projected_loss': 0
            })

    # ==================== AREA BREAKDOWN (for Bigin Analytics) ====================
    # This will be populated via JavaScript fetch to match the Lead Pipeline Summary dates
    # Backend will provide the data through the existing /integrations/bigin/api/sales-lead-summary/ endpoint
    # which already filters by owner and date range

    # ==================== REVENUE TREND (Last 6 Months) ====================

    # Revenue trend — 1 batch query instead of 6 per-month queries
    from django.db.models.functions import TruncMonth
    _six_months_ago = (current_month_start - timedelta(days=150)).replace(day=1)
    _billing_by_month = {
        row['month'].date().replace(day=1): row
        for row in MonthlyBilling.objects.filter(
            project__in=my_projects,
            billing_month__gte=_six_months_ago,
            status='approved'
        ).annotate(month=TruncMonth('billing_month')).values('month').annotate(
            revenue=Sum('client_total'),
            margin=Sum('margin_amount')
        )
    }
    revenue_trend = []
    for i in range(5, -1, -1):
        month_date = (current_month_start - timedelta(days=i*30)).replace(day=1)
        month_data = _billing_by_month.get(month_date, {})
        month_revenue = float(month_data.get('revenue') or 0) / 100000
        month_margin = float(month_data.get('margin') or 0) / 100000
        revenue_trend.append({
            'month': month_date.strftime('%b'),
            'revenue': month_revenue,
            'margin': month_margin,
            'margin_pct': (month_margin / month_revenue * 100) if month_revenue > 0 else 0
        })

    # ==================== CONTEXT ====================

    context = {
        'today': today,
        'user_name': user_full_name,

        # KPI Cards
        'total_projects': total_projects,
        'active_projects_count': active_projects_count,
        'notice_period_projects': notice_period_projects,
        'not_started_projects': not_started_projects,

        # Revenue & Margin
        'mtd_revenue': round(mtd_revenue, 2),
        'mtd_cost': round(mtd_cost, 2),
        'mtd_margin': round(mtd_margin, 2),
        'mtd_margin_pct': round(mtd_margin_pct, 1),
        'ytd_revenue': round(ytd_revenue, 2),
        'ytd_cost': round(ytd_cost, 2),
        'ytd_margin': round(ytd_margin, 2),
        'ytd_margin_pct': round(ytd_margin_pct, 1),
        'revenue_growth': round(revenue_growth, 1),
        'margin_growth': round(margin_growth, 1),

        # Outstanding
        'total_outstanding': round(total_outstanding, 2),
        'outstanding_by_project': outstanding_by_project,

        # Project Performance
        'project_performance': project_performance,

        # Projects at Risk
        'projects_at_risk': projects_at_risk,
        'projects_at_risk_count': len(projects_at_risk),


        # Trends
        'revenue_trend': revenue_trend,
    }

    return render(request, 'dashboards/sales_manager_dashboard.html', context)
