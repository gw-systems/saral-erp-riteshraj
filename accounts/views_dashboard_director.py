"""
Director Dashboard Views
Comprehensive executive dashboard with full ERP analytics and integrations
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, Avg, F, Max, Subquery, OuterRef
from django.db.models.functions import TruncMonth, TruncDate
from django.utils import timezone
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import json

# Import models from all modules
from projects.models import ProjectCode
from projects.models_client import ClientCard
from operations.models import MonthlyBilling, DisputeLog, DailySpaceUtilization
from operations.models_adhoc import AdhocBillingEntry
from operations.models_projectcard import ProjectCard
from operations.models_agreements import AgreementRenewalTracker
from supply.models import VendorWarehouse, WarehouseCapacity, WarehouseCommercial, VendorCard
from integrations.adobe_sign.models import AdobeAgreement
from integrations.bigin.models import BiginDeal
from integrations.callyzer.models import CallHistory
from integrations.google_ads.models import CampaignPerformance
from integrations.gmail_leads.models import LeadEmail
from accounts.models import User


def director_required(view_func):
    """Decorator to ensure only directors and super users can access"""
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ['director', 'super_user']:
            messages.error(request, "Access denied. Director access required.")
            return redirect('accounts:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@director_required
def director_home(request):
    """
    Main director dashboard with comprehensive ERP analytics
    Shows: Executive KPIs, Integrations, Operations, Quick Access
    """

    current_year = timezone.now().year
    current_time = timezone.now().strftime('%b %d, %Y %H:%M')
    ytd_start = datetime(current_year, 1, 1).date()
    current_month = timezone.now().replace(day=1).date()

    # ============== KEY METRICS ==============

    # Revenue YTD - To be calculated from Tally data (not synced yet)
    total_revenue_ytd = 0  # Placeholder until Tally sync is implemented

    # MRR (Monthly Recurring Revenue) - To be calculated from Tally data (not synced yet)
    mrr = 0  # Placeholder until Tally sync is implemented

    # Active Projects
    total_active_projects = ProjectCode.objects.filter(
        project_status='Active'
    ).count()

    # Warehouses
    total_warehouses = VendorWarehouse.objects.filter(
        warehouse_is_active=True
    ).count()

    # Clients
    total_clients = ClientCard.objects.filter(
        client_is_active=True
    ).count()

    # Vendors
    total_vendors = VendorCard.objects.count()

    # ============== OPERATIONS & APPROVALS ==============

    # Adobe Sign Approvals — 1 aggregate instead of 5 queries
    _adobe_agg = AdobeAgreement.objects.filter(
        approval_status='PENDING_APPROVAL'
    ).aggregate(
        total=Count('id'),
        client_agreement=Count('id', filter=Q(agreement_type__code='client_agreement')),
        sla_agreement=Count('id', filter=Q(agreement_type__code='sla_agreement')),
        addendum_client=Count('id', filter=Q(agreement_type__code='addendum_client')),
        addendum_3pl=Count('id', filter=Q(agreement_type__code='addendum_3pl')),
    )
    pending_approvals = _adobe_agg['total']
    adobe_client_agreement_pending = _adobe_agg['client_agreement']
    adobe_sla_agreement_pending = _adobe_agg['sla_agreement']
    adobe_addendum_client_pending = _adobe_agg['addendum_client']
    adobe_addendum_3pl_pending = _adobe_agg['addendum_3pl']

    # Disputes
    outstanding_disputes = DisputeLog.objects.exclude(
        status__code__in=['resolved', 'closed']
    ).count()

    # Adhoc Billing Pending
    adhoc_pending = AdhocBillingEntry.objects.filter(
        status__code__in=['pending', 'submitted']
    ).count()

    # Renewals - Pending/In Progress
    upcoming_renewals = AgreementRenewalTracker.objects.filter(
        status__code__in=['pending', 'in_progress', 'awaiting_client']
    ).count()

    # Capacity Utilization
    capacity_data = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True
    ).aggregate(
        total=Sum('total_capacity'),
        available=Sum('available_capacity')
    )

    total_capacity = capacity_data['total'] or 0
    available_capacity = capacity_data['available'] or 0

    if total_capacity > 0:
        capacity_utilization = round(((total_capacity - available_capacity) / total_capacity) * 100, 1)
    else:
        capacity_utilization = 0

    # ============== INTEGRATIONS ==============

    # Bigin CRM - Count all deals
    bigin_leads_count = BiginDeal.objects.count()

    # Callyzer - Calls Today
    today_date = timezone.now().date()
    callyzer_calls_today = CallHistory.objects.filter(
        call_date=today_date
    ).count()

    # Google Ads - Clicks This Month (sum of all campaign clicks)
    google_ads_clicks_month = CampaignPerformance.objects.filter(
        date__gte=current_month
    ).aggregate(total=Sum('clicks'))['total'] or 0

    # Gmail Leads - This Month
    gmail_leads_month = LeadEmail.objects.filter(
        date_received__gte=current_month
    ).count()

    # ============== DATE CONTEXT FOR OPS SECTIONS ==============

    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    if current_month_start.month == 12:
        current_month_end = current_month_start.replace(year=current_month_start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        current_month_end = current_month_start.replace(month=current_month_start.month + 1, day=1) - timedelta(days=1)
    last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)

    # Date filter for daily operations
    selected_date_str = request.GET.get('selected_date')
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            selected_date = today
    else:
        selected_date = today

    # ============== DISPUTES OVERVIEW (6 subcards) ==============

    _dispute_counts = DisputeLog.objects.aggregate(
        open_disputes=Count('id', filter=Q(status__code='open')),
        in_progress_disputes=Count('id', filter=Q(status__code='in_progress')),
        resolved_disputes_month=Count('id', filter=Q(
            status__code='resolved',
            resolved_at__gte=current_month_start
        )),
        critical_disputes_7days=Count('id', filter=Q(
            status__code='open',
            raised_at__lt=timezone.now() - timedelta(days=7)
        )),
    )
    open_disputes = _dispute_counts['open_disputes']
    in_progress_disputes = _dispute_counts['in_progress_disputes']
    resolved_disputes_month = _dispute_counts['resolved_disputes_month']
    critical_disputes_7days = _dispute_counts['critical_disputes_7days']

    total_active_waas = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period']
    ).count()

    # Daily Dispute % = unique WAAS Active+Notice Period projects with disputes raised today / total
    waas_project_ids = set(ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period']
    ).values_list('project_id', flat=True))
    _waas_project_ids_list = list(waas_project_ids)

    projects_with_disputes_today = DisputeLog.objects.filter(
        raised_at__date=selected_date,
        project_id__in=waas_project_ids
    ).values_list('project_id', flat=True).distinct().count()

    daily_dispute_percentage = round(
        (projects_with_disputes_today / total_active_waas * 100), 1
    ) if total_active_waas > 0 else 0

    # Monthly Dispute % = average of daily dispute % for each day of the month so far
    # Single batch query grouped by date instead of 1 query per day
    days_so_far = min(today.day, (current_month_end - current_month_start).days + 1)
    _dispute_day_counts = dict(
        DisputeLog.objects.filter(
            raised_at__date__gte=current_month_start,
            raised_at__date__lte=today,
            project_id__in=waas_project_ids
        ).annotate(
            day=TruncDate('raised_at')
        ).values('day').annotate(
            proj_count=Count('project_id', distinct=True)
        ).values_list('day', 'proj_count')
    )
    daily_percentages = []
    for day_offset in range(days_so_far):
        day = current_month_start + timedelta(days=day_offset)
        if day > today:
            break
        day_projects = _dispute_day_counts.get(day, 0)
        day_pct = (day_projects / total_active_waas * 100) if total_active_waas > 0 else 0
        daily_percentages.append(day_pct)

    monthly_dispute_percentage = round(
        sum(daily_percentages) / len(daily_percentages), 1
    ) if daily_percentages else 0

    # ============== DAILY OPERATIONS (6 subcards) ==============

    waas_active_projects = total_active_waas

    entries_done_today = DailySpaceUtilization.objects.filter(
        entry_date=selected_date,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).values('project_id').distinct().count()

    entries_missing_today = waas_active_projects - entries_done_today

    data_quality_score_daily = round(
        (entries_done_today / waas_active_projects * 100), 1
    ) if waas_active_projects > 0 else 0

    today_entries = DailySpaceUtilization.objects.filter(
        entry_date=selected_date,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).select_related('project', 'unit')

    total_space_today = Decimal('0')
    for entry in today_entries:
        space_value = entry.space_utilized or Decimal('0')
        if entry.unit_id == 'sqft':
            total_space_today += space_value
        elif entry.unit_id == 'pallet':
            total_space_today += space_value * Decimal('25')

    total_space_today_lakhs = round(float(total_space_today) / 100000, 2)

    total_inventory_today = DailySpaceUtilization.objects.filter(
        entry_date=selected_date,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).aggregate(total=Sum('inventory_value'))['total'] or 0
    total_inventory_today = round(float(total_inventory_today) / 10000000, 2)

    # Space variance: pre-fetch today's entries and the most recent prior entry per project
    _today_entries_map = {
        e.project_id: e
        for e in DailySpaceUtilization.objects.filter(
            project_id__in=_waas_project_ids_list,
            entry_date=selected_date
        ).select_related('unit')
    }
    # Fetch all prior entries in the window, keep only the most recent per project
    _prior_entries_map = {}
    for e in DailySpaceUtilization.objects.filter(
        project_id__in=list(_today_entries_map.keys()),
        entry_date__lt=selected_date,
        entry_date__gte=selected_date - timedelta(days=7)
    ).select_related('unit').order_by('project_id', '-entry_date'):
        if e.project_id not in _prior_entries_map:
            _prior_entries_map[e.project_id] = e

    space_variance_alerts = 0
    space_variance_projects = []
    for project in ProjectCode.objects.filter(
        series_type='WAAS', project_status__in=['Active', 'Notice Period']
    ).only('project_id', 'project_code', 'client_name'):
        today_entry = _today_entries_map.get(project.project_id)
        if not today_entry:
            continue
        previous_entry = _prior_entries_map.get(project.project_id)
        if previous_entry:
            today_space = today_entry.space_utilized or Decimal('0')
            previous_space = previous_entry.space_utilized or Decimal('0')
            if today_entry.unit_id == 'pallet':
                today_space = today_space * Decimal('25')
            if previous_entry.unit_id == 'pallet':
                previous_space = previous_space * Decimal('25')
            if previous_space > 0:
                change_pct = abs((today_space - previous_space) / previous_space * 100)
                if change_pct > 30:
                    space_variance_alerts += 1
                    space_variance_projects.append({
                        'project_code': project.project_code,
                        'client_name': project.client_name,
                        'change_pct': round(float(change_pct), 1),
                        'yesterday_space': round(float(previous_space), 2),
                        'today_space': round(float(today_space), 2)
                    })

    inventory_turnover = 0
    inventory_turnover_previous_date = None
    today_inventory_raw = DailySpaceUtilization.objects.filter(
        entry_date=selected_date,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).aggregate(total=Sum('inventory_value'))['total'] or 0

    if today_inventory_raw > 0:
        # Fetch totals for all 7 prior days in a single query, grouped by date
        _window_start = selected_date - timedelta(days=7)
        _prior_day_totals = dict(
            DailySpaceUtilization.objects.filter(
                entry_date__gt=_window_start,
                entry_date__lt=selected_date,
                project_id__in=_waas_project_ids_list
            ).values('entry_date').annotate(
                total=Sum('inventory_value')
            ).values_list('entry_date', 'total')
        )
        for days_back in range(1, 8):
            check_date = selected_date - timedelta(days=days_back)
            previous_inventory = _prior_day_totals.get(check_date, 0) or 0
            if previous_inventory > 0:
                inventory_turnover_previous_date = check_date
                inventory_turnover = round(
                    ((float(today_inventory_raw) - float(previous_inventory)) / float(previous_inventory) * 100), 2
                )
                break

    # ============== MONTHLY OPERATIONS (6 subcards) ==============

    selected_month_str = request.GET.get('selected_month')
    if selected_month_str:
        try:
            selected_month_date = datetime.strptime(selected_month_str, '%Y-%m').date()
            selected_month_start = selected_month_date.replace(day=1)
            if selected_month_start.month == 12:
                selected_month_end = selected_month_start.replace(year=selected_month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                selected_month_end = selected_month_start.replace(month=selected_month_start.month + 1, day=1) - timedelta(days=1)
        except (ValueError, TypeError):
            selected_month_start = last_month_start
            selected_month_end = last_month_end
    else:
        selected_month_start = last_month_start
        selected_month_end = last_month_end

    _adhoc_month_agg = AdhocBillingEntry.objects.filter(
        event_date__gte=selected_month_start,
        event_date__lte=selected_month_end,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).aggregate(
        adhoc_month_count=Count('id'),
        adhoc_month_value=Sum('total_client_amount')
    )
    adhoc_month_count = _adhoc_month_agg['adhoc_month_count']
    adhoc_month_value = _adhoc_month_agg['adhoc_month_value'] or 0
    adhoc_month_value_lakhs = round(float(adhoc_month_value) / 100000, 2)

    _billing_month_agg = MonthlyBilling.objects.filter(
        service_month__gte=selected_month_start,
        service_month__lte=selected_month_end,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).aggregate(
        monthly_billing_count=Count('id'),
        monthly_billing_value=Sum('client_total'),
        avg_margin=Avg('margin_percentage')
    )
    monthly_billing_count = _billing_month_agg['monthly_billing_count']
    monthly_billing_value = _billing_month_agg['monthly_billing_value'] or 0
    monthly_billing_value_lakhs = round(float(monthly_billing_value) / 100000, 2)
    avg_margin = round(float(_billing_month_agg['avg_margin'] or 0), 2)

    _disputes_month_agg = DisputeLog.objects.filter(
        raised_at__gte=selected_month_start,
        raised_at__lte=selected_month_end,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).aggregate(
        disputes_month_count=Count('id'),
        disputes_open_month=Count('id', filter=Q(status__code='open'))
    )
    disputes_month_count = _disputes_month_agg['disputes_month_count']
    disputes_open_month = _disputes_month_agg['disputes_open_month']

    # Max space: fetch max space_utilized per project in one query, then sum in Python
    _max_space_by_project = dict(
        DailySpaceUtilization.objects.filter(
            project_id__in=_waas_project_ids_list,
            entry_date__gte=selected_month_start,
            entry_date__lte=selected_month_end
        ).values('project_id').annotate(
            max_space=Max('space_utilized')
        ).values_list('project_id', 'max_space')
    )
    # For max space we also need the unit — fetch the entry with max space per project
    _max_space_entries = {}
    if _max_space_by_project:
        for entry in DailySpaceUtilization.objects.filter(
            project_id__in=list(_max_space_by_project.keys()),
            entry_date__gte=selected_month_start,
            entry_date__lte=selected_month_end,
        ).select_related('unit').order_by('project_id', '-space_utilized'):
            if entry.project_id not in _max_space_entries:
                _max_space_entries[entry.project_id] = entry

    # Projects with no entries: fall back to minimum_billable_area from storage rates
    _projects_without_entries = set(_waas_project_ids_list) - set(_max_space_by_project.keys())
    _min_billable_by_project = {}
    if _projects_without_entries:
        from operations.models_projectcard import StorageRate
        for rate in StorageRate.objects.filter(
            project_card__project_id__in=_projects_without_entries,
            project_card__is_active=True,
            rate_for='client'
        ).select_related('project_card').order_by('project_card__project_id'):
            pid = rate.project_card.project_id
            if pid not in _min_billable_by_project and rate.minimum_billable_area:
                _min_billable_by_project[pid] = rate.minimum_billable_area

    max_space_month_sqft = Decimal('0')
    for pid in _waas_project_ids_list:
        if pid in _max_space_entries:
            entry = _max_space_entries[pid]
            space_value = entry.space_utilized or Decimal('0')
            if entry.unit_id == 'sqft':
                max_space_month_sqft += space_value
            elif entry.unit_id == 'pallet':
                max_space_month_sqft += space_value * Decimal('25')
        elif pid in _min_billable_by_project:
            max_space_month_sqft += _min_billable_by_project[pid]
    max_space_month_lakhs = round(float(max_space_month_sqft) / 100000, 2)

    # Sum of per-project max inventory — single query with values/annotate
    _max_inv_per_project = DailySpaceUtilization.objects.filter(
        project_id__in=_waas_project_ids_list,
        entry_date__gte=selected_month_start,
        entry_date__lte=selected_month_end
    ).values('project_id').annotate(
        max_inv=Max('inventory_value')
    ).aggregate(total_max_inv=Sum('max_inv'))['total_max_inv'] or 0
    max_inventory_month = Decimal(str(_max_inv_per_project))
    max_inventory_month_crores = round(float(max_inventory_month) / 10000000, 2)

    # ============== MONTHLY BILLING APPROVALS (6 subcards) ==============

    billing_month_str = request.GET.get('billing_month')
    if billing_month_str:
        try:
            billing_month_date = datetime.strptime(billing_month_str, '%Y-%m').date()
            billing_month_start = billing_month_date.replace(day=1)
            if billing_month_start.month == 12:
                billing_month_end = billing_month_start.replace(year=billing_month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                billing_month_end = billing_month_start.replace(month=billing_month_start.month + 1, day=1) - timedelta(days=1)
        except (ValueError, TypeError):
            billing_month_start = last_month_start
            billing_month_end = last_month_end
    else:
        billing_month_start = last_month_start
        billing_month_end = last_month_end

    _billing_approval_agg = MonthlyBilling.objects.filter(
        service_month__gte=billing_month_start,
        service_month__lte=billing_month_end,
    ).aggregate(
        controller_approved=Count('id', filter=Q(controller_action='approved')),
        controller_rejected=Count('id', filter=Q(controller_action='rejected')),
        controller_pending=Count('id', filter=Q(controller_action='pending')),
        finance_approved=Count('id', filter=Q(finance_action='approved')),
        finance_rejected=Count('id', filter=Q(finance_action='rejected')),
        finance_pending=Count('id', filter=Q(finance_action='pending')),
    )
    controller_approved = _billing_approval_agg['controller_approved']
    controller_rejected = _billing_approval_agg['controller_rejected']
    controller_pending = _billing_approval_agg['controller_pending']
    finance_approved = _billing_approval_agg['finance_approved']
    finance_rejected = _billing_approval_agg['finance_rejected']
    finance_pending = _billing_approval_agg['finance_pending']

    # ============== ADHOC BILLING (6 subcards) ==============

    adhoc_section_month_str = request.GET.get('adhoc_month')
    if adhoc_section_month_str:
        try:
            adhoc_section_month_date = datetime.strptime(adhoc_section_month_str, '%Y-%m').date()
            adhoc_section_month_start = adhoc_section_month_date.replace(day=1)
            if adhoc_section_month_start.month == 12:
                adhoc_section_month_end = adhoc_section_month_start.replace(year=adhoc_section_month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                adhoc_section_month_end = adhoc_section_month_start.replace(month=adhoc_section_month_start.month + 1, day=1) - timedelta(days=1)
        except (ValueError, TypeError):
            adhoc_section_month_start = current_month_start
            adhoc_section_month_end = current_month_end
    else:
        adhoc_section_month_start = current_month_start
        adhoc_section_month_end = current_month_end

    _adhoc_section_agg = AdhocBillingEntry.objects.filter(
        event_date__gte=adhoc_section_month_start,
        event_date__lte=adhoc_section_month_end
    ).aggregate(
        adhoc_total_count=Count('id'),
        adhoc_total_receivable=Sum('total_client_amount'),
        adhoc_total_payable=Sum('total_vendor_amount'),
    )
    adhoc_total_count = _adhoc_section_agg['adhoc_total_count']
    adhoc_total_receivable = _adhoc_section_agg['adhoc_total_receivable'] or Decimal('0')
    adhoc_total_receivable_lakhs = round(float(adhoc_total_receivable) / 100000, 2)
    adhoc_total_payable = _adhoc_section_agg['adhoc_total_payable'] or Decimal('0')
    adhoc_total_payable_lakhs = round(float(adhoc_total_payable) / 100000, 2)

    most_common_charge = AdhocBillingEntry.objects.filter(
        event_date__gte=adhoc_section_month_start,
        event_date__lte=adhoc_section_month_end
    ).values('line_items__charge_type__label', 'line_items__charge_type__code').annotate(
        charge_count=Count('id')
    ).order_by('-charge_count').first()

    adhoc_most_common_type = most_common_charge['line_items__charge_type__label'] if most_common_charge else 'N/A'
    adhoc_most_common_type_code = most_common_charge['line_items__charge_type__code'] if most_common_charge else ''
    adhoc_most_common_type_count = most_common_charge['charge_count'] if most_common_charge else 0

    adhoc_high_value_count = AdhocBillingEntry.objects.filter(
        event_date__gte=adhoc_section_month_start,
        event_date__lte=adhoc_section_month_end,
        total_client_amount__gt=50000
    ).count()

    adhoc_aging_count = AdhocBillingEntry.objects.filter(
        status__code='pending',
        event_date__lt=today - timedelta(days=40)
    ).count()

    # ============== MIS METRICS (6 subcards) ==============

    mis_month_str = request.GET.get('mis_month')
    if mis_month_str:
        try:
            mis_month_date = datetime.strptime(mis_month_str, '%Y-%m').date()
            mis_month_start = mis_month_date.replace(day=1)
            if mis_month_start.month == 12:
                mis_month_end = mis_month_start.replace(year=mis_month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                mis_month_end = mis_month_start.replace(month=mis_month_start.month + 1, day=1) - timedelta(days=1)
        except (ValueError, TypeError):
            mis_month_start = current_month_start
            mis_month_end = current_month_end
    else:
        mis_month_start = current_month_start
        mis_month_end = current_month_end

    mis_working_days = 0
    current_day = mis_month_start
    while current_day <= mis_month_end:
        if current_day.weekday() != 6:
            mis_working_days += 1
        current_day += timedelta(days=1)

    mis_pending_count = entries_missing_today

    _mis_status_agg = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period'],
    ).aggregate(
        mis_daily_projects=Count('id', filter=Q(mis_status='mis_daily')),
        mis_weekly_projects=Count('id', filter=Q(mis_status='mis_weekly')),
        mis_monthly_projects=Count('id', filter=Q(mis_status='mis_monthly')),
    )
    mis_daily_projects = _mis_status_agg['mis_daily_projects']
    mis_weekly_projects = _mis_status_agg['mis_weekly_projects']
    mis_monthly_projects = _mis_status_agg['mis_monthly_projects']

    # Batch count entries per project for MIS gap check — single query instead of N queries
    _entries_per_project = dict(
        DailySpaceUtilization.objects.filter(
            project_id__in=_waas_project_ids_list,
            entry_date__gte=mis_month_start,
            entry_date__lte=mis_month_end
        ).values('project_id').annotate(
            cnt=Count('id')
        ).values_list('project_id', 'cnt')
    )
    projects_with_high_mis_gaps = sum(
        1 for pid in _waas_project_ids_list
        if (mis_working_days - _entries_per_project.get(pid, 0)) > 3
    )

    total_entries_submitted = DailySpaceUtilization.objects.filter(
        entry_date__gte=mis_month_start,
        entry_date__lte=mis_month_end,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).count()

    active_waas_projects_count = waas_active_projects
    expected_total_entries = active_waas_projects_count * mis_working_days
    team_avg_mis_completion = round(
        (total_entries_submitted / expected_total_entries * 100), 1
    ) if expected_total_entries > 0 else 0

    # Adhoc pending amount for top-level card
    adhoc_pending_amount = AdhocBillingEntry.objects.filter(
        status__code='pending'
    ).aggregate(total=Sum('total_client_amount'))['total'] or 0
    adhoc_pending_amount = float(adhoc_pending_amount) / 100000

    context = {
        'current_year': current_year,
        'current_time': current_time,

        # Key Metrics
        'total_revenue_ytd': total_revenue_ytd,
        'mrr': mrr,
        'total_active_projects': total_active_projects,
        'total_warehouses': total_warehouses,
        'total_clients': total_clients,
        'total_vendors': total_vendors,

        # Operations & Approvals
        'pending_approvals': pending_approvals,
        'adobe_client_agreement_pending': adobe_client_agreement_pending,
        'adobe_sla_agreement_pending': adobe_sla_agreement_pending,
        'adobe_addendum_client_pending': adobe_addendum_client_pending,
        'adobe_addendum_3pl_pending': adobe_addendum_3pl_pending,
        'outstanding_disputes': outstanding_disputes,
        'adhoc_pending': adhoc_pending,
        'upcoming_renewals': upcoming_renewals,
        'capacity_utilization': capacity_utilization,

        # Integrations
        'bigin_leads_count': bigin_leads_count,
        'callyzer_calls_today': callyzer_calls_today,
        'google_ads_clicks_month': google_ads_clicks_month,
        'gmail_leads_month': gmail_leads_month,

        # Date context
        'today': today,
        'selected_date': selected_date,

        # Disputes Overview (6 subcards)
        'open_disputes': open_disputes,
        'in_progress_disputes': in_progress_disputes,
        'resolved_disputes_month': resolved_disputes_month,
        'critical_disputes_7days': critical_disputes_7days,
        'daily_dispute_percentage': daily_dispute_percentage,
        'monthly_dispute_percentage': monthly_dispute_percentage,

        # Daily Operations (6 subcards)
        'entries_missing_today': entries_missing_today,
        'total_space_today_lakhs': total_space_today_lakhs,
        'total_inventory_today': total_inventory_today,
        'space_variance_alerts': space_variance_alerts,
        'space_variance_projects': space_variance_projects,
        'inventory_turnover': inventory_turnover,
        'inventory_turnover_previous_date': inventory_turnover_previous_date,
        'data_quality_score_daily': data_quality_score_daily,

        # Monthly Operations (6 subcards)
        'selected_month_start': selected_month_start,
        'adhoc_month_count': adhoc_month_count,
        'adhoc_month_value_lakhs': adhoc_month_value_lakhs,
        'monthly_billing_count': monthly_billing_count,
        'monthly_billing_value_lakhs': monthly_billing_value_lakhs,
        'avg_margin': avg_margin,
        'disputes_month_count': disputes_month_count,
        'disputes_open_month': disputes_open_month,
        'max_space_month_lakhs': max_space_month_lakhs,
        'max_inventory_month_crores': max_inventory_month_crores,

        # Monthly Billing Approvals (6 subcards)
        'billing_month_start': billing_month_start,
        'controller_approved': controller_approved,
        'controller_rejected': controller_rejected,
        'controller_pending': controller_pending,
        'finance_approved': finance_approved,
        'finance_rejected': finance_rejected,
        'finance_pending': finance_pending,

        # Adhoc Billing (6 subcards)
        'adhoc_section_month_start': adhoc_section_month_start,
        'adhoc_total_count': adhoc_total_count,
        'adhoc_total_receivable_lakhs': adhoc_total_receivable_lakhs,
        'adhoc_total_payable_lakhs': adhoc_total_payable_lakhs,
        'adhoc_most_common_type': adhoc_most_common_type,
        'adhoc_most_common_type_code': adhoc_most_common_type_code,
        'adhoc_most_common_type_count': adhoc_most_common_type_count,
        'adhoc_high_value_count': adhoc_high_value_count,
        'adhoc_aging_count': adhoc_aging_count,
        'adhoc_pending_amount': adhoc_pending_amount,

        # MIS Metrics (6 subcards)
        'mis_month_start': mis_month_start,
        'mis_pending_count': mis_pending_count,
        'mis_daily_projects': mis_daily_projects,
        'mis_weekly_projects': mis_weekly_projects,
        'mis_monthly_projects': mis_monthly_projects,
        'projects_with_high_mis_gaps': projects_with_high_mis_gaps,
        'team_avg_mis_completion': team_avg_mis_completion,
    }

    return render(request, 'dashboards/director/home.html', context)


@login_required
@director_required
def director_analytics(request):
    """
    Advanced analytics page for director with detailed charts and coordinator analytics
    """

    current_year = timezone.now().year
    ytd_start = datetime(current_year, 1, 1).date()
    twelve_months_ago = timezone.now() - relativedelta(months=12)
    six_months_ago = timezone.now() - relativedelta(months=6)
    current_month = timezone.now().replace(day=1).date()

    # ============== FINANCIAL ANALYTICS ==============

    # Monthly Revenue Trend (Last 12 months)
    monthly_revenue_data = MonthlyBilling.objects.filter(
        billing_month__gte=twelve_months_ago.date()
    ).values('billing_month').annotate(
        total=Sum('client_total')
    ).order_by('billing_month')

    revenue_trend_labels = [item['billing_month'].strftime('%b %Y') for item in monthly_revenue_data]
    revenue_trend_data = [float(item['total'] or 0) for item in monthly_revenue_data]

    # Revenue by Client (Top 10)
    revenue_by_client = MonthlyBilling.objects.filter(
        billing_month__gte=ytd_start
    ).values('project__client_name').annotate(
        total=Sum('client_total')
    ).order_by('-total')[:10]

    client_revenue_labels = [item['project__client_name'] or 'Unknown' for item in revenue_by_client]
    client_revenue_data = [float(item['total'] or 0) for item in revenue_by_client]

    # Billing Status Distribution (Current Month)
    current_month_billings = MonthlyBilling.objects.filter(
        billing_month=current_month
    )
    billing_status_dist = current_month_billings.values('status').annotate(
        count=Count('id')
    ).order_by('status')

    billing_status_labels = [item['status'].replace('_', ' ').title() for item in billing_status_dist]
    billing_status_counts = [item['count'] for item in billing_status_dist]

    # Adhoc vs Monthly Split (YTD)
    monthly_revenue = MonthlyBilling.objects.filter(
        billing_month__gte=ytd_start
    ).aggregate(total=Sum('client_total'))['total'] or 0

    adhoc_revenue = AdhocBillingEntry.objects.filter(
        event_date__gte=ytd_start
    ).aggregate(total=Sum('total_client_amount'))['total'] or 0

    adhoc_vs_monthly_labels = ['Monthly Billing', 'Adhoc Billing']
    adhoc_vs_monthly_data = [float(monthly_revenue), float(adhoc_revenue)]

    # ============== OPERATIONAL ANALYTICS ==============

    # Projects by Status
    projects_by_status = ProjectCode.objects.values('project_status').annotate(
        count=Count('project_id')
    ).order_by('project_status')

    project_status_labels = [item['project_status'] for item in projects_by_status]
    project_status_counts = [item['count'] for item in projects_by_status]

    # Warehouse Capacity by City (Top 10)
    capacity_by_city = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True
    ).values('warehouse__warehouse_location_id__city').annotate(
        total=Sum('total_capacity')
    ).order_by('-total')[:10]

    city_capacity_labels = [item['warehouse__warehouse_location_id__city'] or 'Unknown' for item in capacity_by_city]
    city_capacity_data = [float(item['total'] or 0) for item in capacity_by_city]

    # Vendor Performance (Top 10 by warehouse count)
    vendor_performance = VendorWarehouse.objects.filter(
        warehouse_is_active=True
    ).values('vendor_code__vendor_short_name').annotate(
        count=Count('warehouse_code')
    ).order_by('-count')[:10]

    vendor_labels = [item['vendor_code__vendor_short_name'] or 'Unknown' for item in vendor_performance]
    vendor_counts = [item['count'] for item in vendor_performance]

    # ============== COORDINATOR ANALYTICS ==============

    # Projects by Primary Coordinator — 1 batch query instead of N
    _dir_coord_names = list(
        User.objects.filter(role='operation_coordinator', is_active=True)
        .values_list('first_name', 'last_name')
    )
    _dir_coord_fullnames = {f"{fn} {ln}".strip() for fn, ln in _dir_coord_names}

    _dir_coord_proj_rows = ProjectCode.objects.filter(
        Q(operation_coordinator__in=_dir_coord_fullnames) | Q(backup_coordinator__in=_dir_coord_fullnames),
        project_status='Active'
    ).values_list('operation_coordinator', 'backup_coordinator')

    from collections import defaultdict
    _dir_coord_counts = defaultdict(int)
    for op_c, bk_c in _dir_coord_proj_rows:
        if op_c in _dir_coord_fullnames:
            _dir_coord_counts[op_c] += 1
        if bk_c in _dir_coord_fullnames:
            _dir_coord_counts[bk_c] += 1

    coordinator_project_data = [
        {'name': name, 'projects': count}
        for name, count in _dir_coord_counts.items() if count > 0
    ]
    coordinator_project_data = sorted(coordinator_project_data, key=lambda x: x['projects'], reverse=True)[:10]
    coordinator_labels = [item['name'] for item in coordinator_project_data]
    coordinator_project_counts = [item['projects'] for item in coordinator_project_data]

    # Dispute Resolution Rate
    total_disputes = DisputeLog.objects.filter(created_at__gte=six_months_ago).count()
    resolved_disputes = DisputeLog.objects.filter(
        created_at__gte=six_months_ago,
        status__code__in=['resolved', 'closed']
    ).count()

    if total_disputes > 0:
        dispute_resolution_rate = round((resolved_disputes / total_disputes) * 100, 1)
    else:
        dispute_resolution_rate = 100

    context = {
        'current_year': current_year,

        # Financial Data
        'revenue_trend_labels': json.dumps(revenue_trend_labels),
        'revenue_trend_data': json.dumps(revenue_trend_data),
        'client_revenue_labels': json.dumps(client_revenue_labels),
        'client_revenue_data': json.dumps(client_revenue_data),
        'billing_status_labels': json.dumps(billing_status_labels),
        'billing_status_counts': json.dumps(billing_status_counts),
        'adhoc_vs_monthly_labels': json.dumps(adhoc_vs_monthly_labels),
        'adhoc_vs_monthly_data': json.dumps(adhoc_vs_monthly_data),

        # Operational Data
        'project_status_labels': json.dumps(project_status_labels),
        'project_status_counts': json.dumps(project_status_counts),
        'city_capacity_labels': json.dumps(city_capacity_labels),
        'city_capacity_data': json.dumps(city_capacity_data),
        'vendor_labels': json.dumps(vendor_labels),
        'vendor_counts': json.dumps(vendor_counts),

        # Coordinator Data
        'coordinator_labels': json.dumps(coordinator_labels),
        'coordinator_project_counts': json.dumps(coordinator_project_counts),

        # Metrics
        'dispute_resolution_rate': dispute_resolution_rate,
    }

    return render(request, 'dashboards/director/analytics.html', context)
