"""
Operation Controller Dashboard View
"""

import json
from functools import wraps
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta, date
from django.db.models import Count, Sum, Q, Avg, Max, Subquery, OuterRef, F, ExpressionWrapper, DurationField
from django.db.models.functions import TruncDate

from accounts.models import User
from projects.models import ProjectCode
from projects.models_client import ClientCard
from operations.models import DailySpaceUtilization, MonthlyBilling, DisputeLog
from operations.models_adhoc import AdhocBillingEntry
from operations.models_projectcard import ProjectCard
from supply.models import VendorCard, VendorWarehouse
from integrations.models import SyncLog


# Role-based access decorator
def role_required(allowed_roles):
    """
    Decorator to restrict view access to specific roles.
    Usage: @role_required(['operation_controller', 'operation_manager', 'admin', 'director'])
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                messages.error(request, f"Access denied. Required role: {' or '.join(allowed_roles)}.")
                return redirect('accounts:dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


@login_required
def operation_controller_dashboard(request):
    """
    Operation Controller Dashboard
    Comprehensive single-page dashboard for operational oversight, quality control, and compliance
    """
    # Role check
    if request.user.role not in ['operation_controller', 'admin', 'director']:
        messages.error(request, "Access denied. Operation Controller access required.")
        return redirect('accounts:dashboard')

    # Date context - Support date filtering for daily operations
    selected_date_str = request.GET.get('selected_date')
    if selected_date_str:
        try:
            from datetime import datetime
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    # Calculate current month end
    if current_month_start.month == 12:
        current_month_end = current_month_start.replace(year=current_month_start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        current_month_end = current_month_start.replace(month=current_month_start.month + 1, day=1) - timedelta(days=1)

    last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)

    # ==================== PROJECT OVERVIEW ====================

    # Project counts — single aggregate query instead of 6 separate queries
    _project_agg = ProjectCode.objects.aggregate(
        active_projects=Count('project_id', filter=Q(project_status='Active')),
        not_started_projects=Count('project_id', filter=Q(project_status='Operation Not Started')),
        notice_period_projects=Count('project_id', filter=Q(project_status='Notice Period')),
        total_projects=Count('project_id'),
        inactive_projects=Count('project_id', filter=Q(project_status='Inactive')),
        saas_projects=Count('project_id', filter=Q(series_type='SAAS')),
        gw_projects=Count('project_id', filter=Q(series_type='GW')),
    )
    active_projects = _project_agg['active_projects']
    not_started_projects = _project_agg['not_started_projects']
    notice_period_projects = _project_agg['notice_period_projects']
    total_projects_card = active_projects + not_started_projects + notice_period_projects
    total_projects = _project_agg['total_projects']
    inactive_projects = _project_agg['inactive_projects']
    saas_projects = _project_agg['saas_projects']
    gw_projects = _project_agg['gw_projects']

    # WAAS projects with transport expenses (for transport card)
    from integrations.expense_log.models import ExpenseRecord
    from collections import defaultdict

    current_month = timezone.now().strftime('%B %Y')
    transport_expenses = ExpenseRecord.get_expenses_for_user(request.user).filter(
        Q(nature_of_expense__icontains='transport') |
        Q(raw_data__Transport__isnull=False),
        service_month=current_month
    ).exclude(
        client_name__isnull=True
    ).exclude(
        client_name=''
    )

    # Get all WAAS project codes
    waas_project_codes = set(ProjectCode.objects.filter(series_type='WAAS').values_list('code', flat=True))

    # Count unique WAAS projects with transport expenses and calculate approved amount
    waas_projects_with_transport = set()
    transport_approved_amount = Decimal('0')

    for expense in transport_expenses:
        if expense.client_name:
            project_code = expense.client_name.split(' - ')[0]
            if project_code in waas_project_codes:
                waas_projects_with_transport.add(project_code)
                # Sum approved amounts only
                if expense.approval_status == 'Approved':
                    transport_approved_amount += expense.amount or Decimal('0')

    waas_projects_count = len(waas_projects_with_transport)

    # ==================== CLIENTS & VENDORS & WAREHOUSES ====================

    # Total active clients (from ClientCard master data)
    total_clients = ClientCard.objects.filter(client_is_active=True).count()

    # Total active vendors (from VendorCard master data)
    total_vendors = VendorCard.objects.filter(vendor_is_active=True).count()

    # Total active warehouses (from VendorWarehouse master data)
    total_warehouses = VendorWarehouse.objects.filter(warehouse_is_active=True).count()

    # ==================== TALLY SYNC STATUS ====================

    # Get latest sync log
    latest_sync = SyncLog.objects.filter(integration='tallysync', log_kind='batch').order_by('-started_at').first()

    if latest_sync:
        sync_status = latest_sync.status
        sync_last_time = latest_sync.started_at
        sync_records = latest_sync.total_records_synced or 0
        sync_errors = latest_sync.records_failed or 0
    else:
        sync_status = 'never'
        sync_last_time = None
        sync_records = 0
        sync_errors = 0

    # Check if Tally is actually connected (recent successful sync within 24 hours)
    from datetime import datetime

    # Default: Not Connected (set to False for now)
    tally_connected = False

    # Uncomment below to enable automatic connection detection based on sync logs
    # if latest_sync and latest_sync.status == 'success':
    #     hours_since_sync = (timezone.now() - latest_sync.started_at).total_seconds() / 3600
    #     if hours_since_sync <= 24:
    #         tally_connected = True

    # ==================== DATA QUALITY & COMPLIANCE ====================

    # Projects without project_id
    projects_without_id = ProjectCode.objects.filter(
        Q(project_id__isnull=True) | Q(project_id='')
    ).count()

    # Projects without project cards (Active only)
    active_project_ids = ProjectCode.objects.filter(
        project_status='Active'
    ).values_list('project_id', flat=True)

    projects_with_cards = ProjectCard.objects.filter(
        project_id__in=active_project_ids
    ).values_list('project_id', flat=True).distinct()

    incomplete_project_cards = len(set(active_project_ids) - set(projects_with_cards))

    # Projects without coordinators
    projects_without_coordinator = ProjectCode.objects.filter(
        operation_coordinator__isnull=True,
        project_status='Active'
    ).count()

    # Incomplete project cards (missing key fields)
    incomplete_cards_detail = ProjectCard.objects.filter(
        Q(agreement_start_date__isnull=True) |
        Q(agreement_end_date__isnull=True) |
        Q(billing_start_date__isnull=True)
    ).count()

    # Data quality score
    projects_with_id = ProjectCode.objects.exclude(
        Q(project_id__isnull=True) | Q(project_id='')
    ).count()

    total_project_cards = ProjectCard.objects.count()
    complete_cards = ProjectCard.objects.filter(
        agreement_start_date__isnull=False,
        agreement_end_date__isnull=False,
        billing_start_date__isnull=False
    ).count()

    projects_with_id_percentage = round(
        (projects_with_id / total_projects * 100), 1
    ) if total_projects > 0 else 0

    complete_cards_percentage = round(
        (complete_cards / total_project_cards * 100), 1
    ) if total_project_cards > 0 else 0

    data_quality_score = round(
        (projects_with_id_percentage + complete_cards_percentage) / 2, 1
    )

    # ==================== DAILY OPERATIONS MONITORING ====================

    # Get WAAS projects with Active & Notice Period status only
    waas_active_projects = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period']
    ).count()

    # 1) Today's Done Entries - WAAS projects (Active & Notice Period) that submitted entry for selected date
    entries_done_today = DailySpaceUtilization.objects.filter(
        entry_date=selected_date,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).values('project_id').distinct().count()

    # 2) Today's Missing Entries - WAAS active projects that haven't submitted entry for selected date
    entries_missing_today = waas_active_projects - entries_done_today

    # 6) Data Quality Score - Entry compliance percentage
    data_quality_score_daily = round(
        (entries_done_today / waas_active_projects * 100), 1
    ) if waas_active_projects > 0 else 0

    # 3) Today's Total Space Utilized - Sum of all space utilized on selected date (convert pallets to sqft)
    today_entries = DailySpaceUtilization.objects.filter(
        entry_date=selected_date,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).select_related('project', 'unit')

    total_space_today = Decimal('0')
    for entry in today_entries:
        space_value = entry.space_utilized or Decimal('0')

        # Only count sqft and pallet units (exclude order, unit, lumpsum)
        if entry.unit_id == 'sqft':
            total_space_today += space_value
        elif entry.unit_id == 'pallet':
            total_space_today += space_value * Decimal('25')
        # order, unit, lumpsum do not contribute to sq ft total

    total_space_today_sqft = round(float(total_space_today), 2)
    total_space_today_lakhs = round(float(total_space_today) / 100000, 2)

    # 4) Today's Total Inventory Value - Sum of all inventory values on selected date (WAAS Active & Notice Period)
    total_inventory_today = DailySpaceUtilization.objects.filter(
        entry_date=selected_date,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).aggregate(total=Sum('inventory_value'))['total'] or 0
    total_inventory_today = round(float(total_inventory_today) / 10000000, 2)  # Convert to crores

    # 5) Space Variance Alerts — pre-fetch all entries in 2 queries instead of N+1
    _waas_project_ids_list = list(
        ProjectCode.objects.filter(
            series_type='WAAS',
            project_status__in=['Active', 'Notice Period']
        ).values_list('project_id', flat=True)
    )
    _sv_today_map = {
        e.project_id: e
        for e in DailySpaceUtilization.objects.filter(
            project_id__in=_waas_project_ids_list,
            entry_date=selected_date
        ).select_related('unit')
    }
    _sv_prior_map = {}
    for e in DailySpaceUtilization.objects.filter(
        project_id__in=list(_sv_today_map.keys()),
        entry_date__lt=selected_date,
        entry_date__gte=selected_date - timedelta(days=7)
    ).select_related('unit').order_by('project_id', '-entry_date'):
        if e.project_id not in _sv_prior_map:
            _sv_prior_map[e.project_id] = e

    space_variance_alerts = 0
    space_variance_projects = []
    for project in ProjectCode.objects.filter(
        series_type='WAAS', project_status__in=['Active', 'Notice Period']
    ).only('project_id', 'project_code', 'client_name'):
        today_entry = _sv_today_map.get(project.project_id)
        if not today_entry:
            continue
        previous_entry = _sv_prior_map.get(project.project_id)
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

    # 6) Today's Inventory Turnover - Percentage change in inventory value vs most recent previous data (WAAS Active & Notice Period)
    inventory_turnover = 0
    inventory_turnover_previous_date = None

    # Get today's total inventory value
    today_inventory_raw = DailySpaceUtilization.objects.filter(
        entry_date=selected_date,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).aggregate(total=Sum('inventory_value'))['total'] or 0

    if today_inventory_raw > 0:
        # Fetch all 7 prior day totals in one query instead of looping per day
        _inv_window_start = selected_date - timedelta(days=7)
        _prior_inv_totals = dict(
            DailySpaceUtilization.objects.filter(
                entry_date__gt=_inv_window_start,
                entry_date__lt=selected_date,
                project_id__in=_waas_project_ids_list
            ).values('entry_date').annotate(
                total=Sum('inventory_value')
            ).values_list('entry_date', 'total')
        )
        for days_back in range(1, 8):
            check_date = selected_date - timedelta(days=days_back)
            previous_inventory = _prior_inv_totals.get(check_date, 0) or 0
            if previous_inventory > 0:
                inventory_turnover_previous_date = check_date
                inventory_turnover = round(
                    ((float(today_inventory_raw) - float(previous_inventory)) / float(previous_inventory) * 100), 2
                )
                break

    # ==================== MONTHLY OPERATIONS ====================

    # Month filtering for monthly operations (default to previous month)
    selected_month_str = request.GET.get('selected_month')
    if selected_month_str:
        try:
            from datetime import datetime
            selected_month_date = datetime.strptime(selected_month_str, '%Y-%m').date()
            selected_month_start = selected_month_date.replace(day=1)
            # Get last day of selected month
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

    # 1) Adhoc Billing — single aggregate instead of 2 queries
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

    # 2+3) Monthly Billing count, value, margin — single aggregate instead of 3 queries
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

    # 4) Disputes — single aggregate instead of 3 queries
    _disputes_month_agg = DisputeLog.objects.filter(
        raised_at__gte=selected_month_start,
        raised_at__lte=selected_month_end,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).aggregate(
        disputes_month_count=Count('dispute_id'),
        disputes_open_month=Count('dispute_id', filter=Q(status__code='open')),
        disputes_resolved_in_month=Count('dispute_id', filter=Q(status__code='resolved')),
    )
    disputes_month_count = _disputes_month_agg['disputes_month_count']
    disputes_open_month = _disputes_month_agg['disputes_open_month']
    disputes_resolved_in_month = _disputes_month_agg['disputes_resolved_in_month']

    # 5) Max Space Utilization — batch queries instead of N+1 per project
    _max_space_by_project = dict(
        DailySpaceUtilization.objects.filter(
            project_id__in=_waas_project_ids_list,
            entry_date__gte=selected_month_start,
            entry_date__lte=selected_month_end
        ).values('project_id').annotate(
            max_space=Max('space_utilized')
        ).values_list('project_id', 'max_space')
    )
    # Fetch the entry with max space per project to get unit type
    _max_space_entries = {}
    if _max_space_by_project:
        for entry in DailySpaceUtilization.objects.filter(
            project_id__in=list(_max_space_by_project.keys()),
            entry_date__gte=selected_month_start,
            entry_date__lte=selected_month_end,
        ).select_related('unit').order_by('project_id', '-space_utilized'):
            if entry.project_id not in _max_space_entries:
                _max_space_entries[entry.project_id] = entry

    # Projects without entries: fall back to minimum_billable_area from StorageRate
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

    # 6) Max Inventory Value — single query with values/annotate chain
    _max_inv_result = DailySpaceUtilization.objects.filter(
        project_id__in=_waas_project_ids_list,
        entry_date__gte=selected_month_start,
        entry_date__lte=selected_month_end
    ).values('project_id').annotate(
        max_inv=Max('inventory_value')
    ).aggregate(total_max_inv=Sum('max_inv'))['total_max_inv'] or 0
    max_inventory_month = Decimal(str(_max_inv_result))
    max_inventory_month_crores = round(float(max_inventory_month) / 10000000, 2)

    # ==================== MONTHLY METRICS (for other sections) ====================

    # This month's entries
    entries_this_month = DailySpaceUtilization.objects.filter(
        entry_date__gte=current_month_start,
        entry_date__lte=today
    ).count()

    # Calculate working days
    working_days = 0
    current_date = current_month_start
    while current_date <= today:
        if current_date.weekday() != 6:  # Not Sunday
            working_days += 1
        current_date += timedelta(days=1)

    expected_entries_month = active_projects * working_days
    monthly_completion_rate = round(
        (entries_this_month / expected_entries_month * 100), 1
    ) if expected_entries_month > 0 else 0

    # Missing entries tracking — batch count per project instead of N+1
    _active_projects_for_missing = list(
        ProjectCode.objects.filter(project_status='Active')
        .only('project_id', 'project_code', 'client_name', 'operation_coordinator')
    )
    _missing_pids = [p.project_id for p in _active_projects_for_missing]
    _missing_entry_counts = dict(
        DailySpaceUtilization.objects.filter(
            project_id__in=_missing_pids,
            entry_date__gte=current_month_start
        ).values('project_id').annotate(cnt=Count('id')).values_list('project_id', 'cnt')
    )
    projects_missing_entries = []
    for project in _active_projects_for_missing:
        project_entries = _missing_entry_counts.get(project.project_id, 0)
        missing = working_days - project_entries
        if missing > 3:  # More than 3 missing entries
            projects_missing_entries.append({
                'project_code': project.project_code,
                'client_name': project.client_name,
                'coordinator': project.operation_coordinator,
                'missing_count': missing,
                'completion_rate': round((project_entries / working_days * 100), 1) if working_days > 0 else 0
            })

    # Sort by missing count
    projects_missing_entries.sort(key=lambda x: x['missing_count'], reverse=True)
    projects_missing_entries = projects_missing_entries[:10]

    # ==================== COORDINATOR PERFORMANCE ====================

    # Coordinators with performance metrics — batch all queries instead of N+1 per coordinator
    coordinators = User.objects.filter(role='operation_coordinator', is_active=True)
    _coord_names = [c.get_full_name() for c in coordinators]

    # Batch: all active projects assigned to any coordinator (primary or backup)
    _coord_projects_qs = list(
        ProjectCode.objects.filter(
            Q(operation_coordinator__in=_coord_names) | Q(backup_coordinator__in=_coord_names),
            project_status='Active'
        ).only('project_id', 'operation_coordinator', 'backup_coordinator')
    )
    _coord_projects_map = {}   # coord_name -> list of project_ids (primary or backup)
    _coord_primary_map = {}    # coord_name -> list of project_ids (primary only, for low compliance)
    for proj in _coord_projects_qs:
        for cname in _coord_names:
            if proj.operation_coordinator == cname:
                _coord_projects_map.setdefault(cname, []).append(proj.project_id)
                _coord_primary_map.setdefault(cname, []).append(proj.project_id)
            elif proj.backup_coordinator == cname:
                _coord_projects_map.setdefault(cname, []).append(proj.project_id)

    _all_coord_project_ids = list({pid for pids in _coord_projects_map.values() for pid in pids})

    # Batch entry counts per project for this month
    _entry_counts_by_proj = dict(
        DailySpaceUtilization.objects.filter(
            project_id__in=_all_coord_project_ids,
            entry_date__gte=current_month_start
        ).values('project_id').annotate(cnt=Count('id')).values_list('project_id', 'cnt')
    )
    # Batch adhoc pending counts per project
    _adhoc_pending_by_proj = dict(
        AdhocBillingEntry.objects.filter(
            project_id__in=_all_coord_project_ids,
            status__code='pending'
        ).values('project_id').annotate(cnt=Count('id')).values_list('project_id', 'cnt')
    )

    coordinator_performance = []
    for coord in coordinators:
        coord_name = coord.get_full_name()
        proj_ids = _coord_projects_map.get(coord_name, [])
        proj_count = len(proj_ids)
        coord_entries = sum(_entry_counts_by_proj.get(pid, 0) for pid in proj_ids)
        expected_coord_entries = proj_count * working_days
        coord_completion_rate = round(
            (coord_entries / expected_coord_entries * 100), 1
        ) if expected_coord_entries > 0 else 0
        coord_adhoc_pending = sum(_adhoc_pending_by_proj.get(pid, 0) for pid in proj_ids)
        coordinator_performance.append({
            'coordinator': coord,
            'name': coord_name,
            'initials': ''.join([n[0] for n in coord_name.split()[:2]]),
            'projects': proj_count,
            'entries': coord_entries,
            'expected': expected_coord_entries,
            'completion_rate': coord_completion_rate,
            'adhoc_pending': coord_adhoc_pending
        })

    # Sort by completion rate
    coordinator_performance.sort(key=lambda x: x['completion_rate'])

    # ==================== ADHOC BILLING OVERSIGHT ====================

    # Month filtering for adhoc billing (independent, default to current month)
    adhoc_month_str = request.GET.get('adhoc_month')
    if adhoc_month_str:
        try:
            from datetime import datetime
            adhoc_month_date = datetime.strptime(adhoc_month_str, '%Y-%m').date()
            adhoc_month_start = adhoc_month_date.replace(day=1)
            # Get last day of selected month
            if adhoc_month_start.month == 12:
                adhoc_month_end = adhoc_month_start.replace(year=adhoc_month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                adhoc_month_end = adhoc_month_start.replace(month=adhoc_month_start.month + 1, day=1) - timedelta(days=1)
        except (ValueError, TypeError):
            adhoc_month_start = current_month_start
            adhoc_month_end = current_month_end
    else:
        adhoc_month_start = current_month_start
        adhoc_month_end = current_month_end

    # Adhoc billing counts for selected month — single aggregate instead of 5 queries
    _adhoc_billing_agg = AdhocBillingEntry.objects.filter(
        event_date__gte=adhoc_month_start,
        event_date__lte=adhoc_month_end
    ).aggregate(
        total_count=Count('id'),
        total_receivable=Sum('total_client_amount'),
        total_payable=Sum('total_vendor_amount'),
        high_value_count=Count('id', filter=Q(total_client_amount__gt=50000)),
    )
    adhoc_total_count = _adhoc_billing_agg['total_count']
    adhoc_total_receivable = _adhoc_billing_agg['total_receivable'] or Decimal('0')
    adhoc_total_payable = _adhoc_billing_agg['total_payable'] or Decimal('0')
    adhoc_high_value_count = _adhoc_billing_agg['high_value_count']
    adhoc_total_receivable_lakhs = round(float(adhoc_total_receivable) / 100000, 2)
    adhoc_total_payable_lakhs = round(float(adhoc_total_payable) / 100000, 2)

    # Most common charge type — separate group-by query (can't combine with simple aggregate)
    most_common_charge = AdhocBillingEntry.objects.filter(
        event_date__gte=adhoc_month_start,
        event_date__lte=adhoc_month_end
    ).values('line_items__charge_type__label', 'line_items__charge_type__code').annotate(
        count=Count('id')
    ).order_by('-count').first()

    adhoc_most_common_type = most_common_charge['line_items__charge_type__label'] if most_common_charge else 'N/A'
    adhoc_most_common_type_code = most_common_charge['line_items__charge_type__code'] if most_common_charge else ''
    adhoc_most_common_type_count = most_common_charge['count'] if most_common_charge else 0

    # Aging - pending entries older than 40 days (separate filter, keep as 1 query)
    adhoc_aging_count = AdhocBillingEntry.objects.filter(
        status__code='pending',
        event_date__lt=today - timedelta(days=40)
    ).count()

    # Legacy adhoc counts — 2 aggregates instead of 5 queries
    _adhoc_pending_agg = AdhocBillingEntry.objects.filter(
        status__code='pending'
    ).aggregate(
        adhoc_pending=Count('id'),
        adhoc_pending_old=Count('id', filter=Q(event_date__lt=today - timedelta(days=30))),
        adhoc_pending_total=Sum('total_client_amount'),
    )
    adhoc_pending = _adhoc_pending_agg['adhoc_pending']
    adhoc_pending_old = _adhoc_pending_agg['adhoc_pending_old']
    adhoc_pending_amount = float(_adhoc_pending_agg['adhoc_pending_total'] or 0) / 100000

    _adhoc_month_status_agg = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start
    ).aggregate(
        adhoc_approved_month=Count('id', filter=Q(status__code='approved')),
        adhoc_billed_month=Count('id', filter=Q(status__code='billed')),
    )
    adhoc_approved_month = _adhoc_month_status_agg['adhoc_approved_month']
    adhoc_billed_month = _adhoc_month_status_agg['adhoc_billed_month']

    # Recent pending adhoc entries
    recent_adhoc_pending = AdhocBillingEntry.objects.filter(
        status__code='pending'
    ).order_by('event_date')[:10]

    adhoc_pending_list = []
    for adhoc in recent_adhoc_pending:
        days_pending = (today - adhoc.event_date).days
        adhoc_pending_list.append({
            'id': adhoc.id,
            'project_id': adhoc.project.project_id if adhoc.project else None,
            'event_date': adhoc.event_date,
            'days_pending': days_pending,
            'amount': float(adhoc.total_client_amount or 0) / 100000
        })

    # ==================== MONTHLY BILLING STATUS ====================

    # Monthly billing status — single aggregate instead of 6 queries
    _billing_status_agg = MonthlyBilling.objects.filter(
        service_month__gte=current_month_start
    ).aggregate(
        billing_pending_controller=Count('id', filter=Q(status__code='pending_controller')),
        billing_approved_controller=Count('id', filter=Q(status__code__in=['pending_finance', 'approved'])),
        billing_rejected_controller=Count('id', filter=Q(status__code='controller_rejected')),
        billing_generated=Count('id', filter=Q(status__code='draft')),
        billing_paid=Count('id', filter=Q(status__code='approved')),
    )
    billing_pending_controller = _billing_status_agg['billing_pending_controller']
    billing_approved_controller = _billing_status_agg['billing_approved_controller']
    billing_rejected_controller = _billing_status_agg['billing_rejected_controller']
    billing_generated = _billing_status_agg['billing_generated']
    billing_sent = billing_approved_controller  # same filter: pending_finance | approved
    billing_pending = billing_pending_controller  # Alias for consistency
    billing_paid = _billing_status_agg['billing_paid']

    # ==================== BILLING APPROVAL BREAKDOWN ====================

    # Month filtering for billing approvals (independent from monthly operations filter, default to previous month)
    billing_month_str = request.GET.get('billing_month')
    if billing_month_str:
        try:
            from datetime import datetime
            billing_month_date = datetime.strptime(billing_month_str, '%Y-%m').date()
            billing_month_start = billing_month_date.replace(day=1)
            # Get last day of selected month
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

    # Controller + finance approval breakdown — single aggregate instead of 6 queries
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

    # ==================== DISPUTES OVERVIEW ====================

    # Disputes counts — single aggregate instead of 4 queries
    _disputes_agg = DisputeLog.objects.aggregate(
        open_disputes=Count('dispute_id', filter=Q(status__code='open')),
        in_progress_disputes=Count('dispute_id', filter=Q(status__code='in_progress')),
        resolved_disputes_month=Count('dispute_id', filter=Q(
            status__code='resolved', resolved_at__gte=current_month_start
        )),
        critical_disputes_7days=Count('dispute_id', filter=Q(
            status__code='open', raised_at__lt=timezone.now() - timedelta(days=7)
        )),
    )
    open_disputes = _disputes_agg['open_disputes']
    in_progress_disputes = _disputes_agg['in_progress_disputes']
    resolved_disputes_month = _disputes_agg['resolved_disputes_month']
    critical_disputes_7days = _disputes_agg['critical_disputes_7days']

    # Reuse _waas_project_ids_list already fetched in space variance section
    total_active_waas = len(_waas_project_ids_list)
    waas_project_ids = set(_waas_project_ids_list)

    projects_with_disputes_today = DisputeLog.objects.filter(
        raised_at__date=selected_date,
        project_id__in=waas_project_ids
    ).values_list('project_id', flat=True).distinct().count()

    daily_dispute_percentage = round(
        (projects_with_disputes_today / total_active_waas * 100), 1
    ) if total_active_waas > 0 else 0

    # Monthly Dispute % — batch all days in one query instead of 1 query per day
    _dispute_daily_counts = {}
    if total_active_waas > 0:
        _dispute_daily_data = DisputeLog.objects.filter(
            raised_at__date__gte=current_month_start,
            raised_at__date__lte=today,
            project_id__in=waas_project_ids,
        ).values(day=TruncDate('raised_at')).annotate(
            project_count=Count('project_id', distinct=True)
        )
        _dispute_daily_counts = {row['day']: row['project_count'] for row in _dispute_daily_data}

    days_so_far = min(today.day, (current_month_end - current_month_start).days + 1)
    daily_percentages = []
    for day_offset in range(days_so_far):
        loop_day = current_month_start + timedelta(days=day_offset)
        if loop_day > today:
            break
        day_projects = _dispute_daily_counts.get(loop_day, 0)
        day_pct = (day_projects / total_active_waas * 100) if total_active_waas > 0 else 0
        daily_percentages.append(day_pct)

    monthly_dispute_percentage = round(
        sum(daily_percentages) / len(daily_percentages), 1
    ) if daily_percentages else 0

    # Dispute resolution rate
    total_disputes_all_time = open_disputes + in_progress_disputes + resolved_disputes_month
    dispute_resolution_rate = round(
        (resolved_disputes_month / total_disputes_all_time * 100), 1
    ) if total_disputes_all_time > 0 else 0

    # Average resolution time — DB-level aggregate instead of Python iteration
    _resolution_agg = DisputeLog.objects.filter(
        status__code='resolved',
        resolved_at__gte=current_month_start,
        raised_at__isnull=False,
        resolved_at__isnull=False,
    ).annotate(
        resolution_duration=ExpressionWrapper(
            F('resolved_at') - F('raised_at'),
            output_field=DurationField()
        )
    ).aggregate(
        avg_duration=Avg('resolution_duration'),
        resolution_count=Count('dispute_id'),
    )
    if _resolution_agg['avg_duration'] and _resolution_agg['resolution_count']:
        avg_resolution_time = round(_resolution_agg['avg_duration'].days, 1)
    else:
        avg_resolution_time = 0

    # ==================== MIS METRICS ====================

    # Month filtering for MIS metrics (independent, default to current month)
    mis_month_str = request.GET.get('mis_month')
    if mis_month_str:
        try:
            from datetime import datetime
            mis_month_date = datetime.strptime(mis_month_str, '%Y-%m').date()
            mis_month_start = mis_month_date.replace(day=1)
            # Get last day of selected month
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

    # Calculate working days for MIS month (excluding Sundays)
    mis_working_days = 0
    current_day = mis_month_start
    while current_day <= mis_month_end:
        if current_day.weekday() != 6:  # 6 = Sunday
            mis_working_days += 1
        current_day += timedelta(days=1)

    # MIS pending today (always current day, not month-filtered)
    mis_pending_count = entries_missing_today

    # Count projects by MIS frequency — single aggregate instead of 3 queries
    _mis_status_agg = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period'],
    ).aggregate(
        mis_daily_projects=Count('project_id', filter=Q(mis_status='mis_daily')),
        mis_weekly_projects=Count('project_id', filter=Q(mis_status='mis_weekly')),
        mis_monthly_projects=Count('project_id', filter=Q(mis_status='mis_monthly')),
    )
    mis_daily_projects = _mis_status_agg['mis_daily_projects']
    mis_weekly_projects = _mis_status_agg['mis_weekly_projects']
    mis_monthly_projects = _mis_status_agg['mis_monthly_projects']

    # Projects with >3 missing entries — batch annotate instead of N+1
    _mis_entry_counts = dict(
        DailySpaceUtilization.objects.filter(
            project_id__in=_waas_project_ids_list,
            entry_date__gte=mis_month_start,
            entry_date__lte=mis_month_end,
        ).values('project_id').annotate(cnt=Count('id')).values_list('project_id', 'cnt')
    )
    projects_with_high_mis_gaps = sum(
        1 for pid in _waas_project_ids_list
        if (mis_working_days - _mis_entry_counts.get(pid, 0)) > 3
    )

    # Team-wide average MIS completion rate for selected month
    total_entries_submitted = DailySpaceUtilization.objects.filter(
        entry_date__gte=mis_month_start,
        entry_date__lte=mis_month_end,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).count()

    active_waas_projects_count = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period']
    ).count()

    expected_total_entries = active_waas_projects_count * mis_working_days
    team_avg_mis_completion = round(
        (total_entries_submitted / expected_total_entries * 100), 1
    ) if expected_total_entries > 0 else 0

    # Low compliance coordinators — reuse batched data from coordinator performance section
    low_compliance_coordinators = 0
    for coord in coordinators:
        coord_name = coord.get_full_name()
        proj_ids = _coord_primary_map.get(coord_name, [])
        if not proj_ids:
            continue
        coord_entries = sum(_entry_counts_by_proj.get(pid, 0) for pid in proj_ids)
        expected_coord_entries = len(proj_ids) * working_days
        coord_completion = (coord_entries / expected_coord_entries * 100) if expected_coord_entries > 0 else 0
        if coord_completion < 90:
            low_compliance_coordinators += 1

    # Consecutive missing days (using space variance alerts as placeholder)
    consecutive_missing_days = space_variance_alerts

    # ==================== ALERTS & ISSUES ====================

    total_alerts = (
        projects_without_id +
        incomplete_project_cards +
        projects_without_coordinator +
        adhoc_pending_old +
        entries_missing_today
    )

    # Critical issues list
    critical_issues = []

    if projects_without_id > 0:
        critical_issues.append({
            'type': 'data_quality',
            'severity': 'high',
            'title': f'{projects_without_id} projects without Project ID',
            'count': projects_without_id
        })

    if incomplete_project_cards > 0:
        critical_issues.append({
            'type': 'data_quality',
            'severity': 'high',
            'title': f'{incomplete_project_cards} active projects without Project Cards',
            'count': incomplete_project_cards
        })

    if adhoc_pending_old > 0:
        critical_issues.append({
            'type': 'billing',
            'severity': 'medium',
            'title': f'{adhoc_pending_old} adhoc entries pending > 30 days',
            'count': adhoc_pending_old
        })

    if entries_missing_today > 0:
        critical_issues.append({
            'type': 'operations',
            'severity': 'medium',
            'title': f'{entries_missing_today} projects missing today\'s entries',
            'count': entries_missing_today
        })

    # ==================== TOP STATES & CLIENTS ====================

    # Top states by active projects
    top_states = ProjectCode.objects.filter(
        project_status='Active'
    ).values('state').annotate(
        count=Count('project_id')
    ).order_by('-count')[:5]

    top_states_list = []
    for state in top_states:
        top_states_list.append({
            'name': state['state'],
            'count': state['count']
        })

    # Top clients (excluding Godamwale)
    top_clients = ProjectCode.objects.filter(
        project_status__in=['Active', 'Operation Not Started']
    ).exclude(
        client_name='Godamwale'
    ).values('client_name').annotate(
        project_count=Count('project_id')
    ).order_by('-project_count')[:5]

    top_clients_list = []
    for idx, client in enumerate(top_clients, 1):
        top_clients_list.append({
            'rank': idx,
            'name': client['client_name'],
            'projects': client['project_count']
        })

    # ==================== TRENDS ====================

    # Entry completion trend (last 7 days) — 1 batch query instead of 7 queries
    _trend_start = today - timedelta(days=6)
    _trend_counts = dict(
        DailySpaceUtilization.objects.filter(
            entry_date__gte=_trend_start,
            entry_date__lte=today,
        ).values('entry_date').annotate(
            cnt=Count('project_id', distinct=True)
        ).values_list('entry_date', 'cnt')
    )
    entry_trend = []
    for i in range(6, -1, -1):
        trend_date = today - timedelta(days=i)
        if trend_date.weekday() != 6:  # Not Sunday
            entries_count = _trend_counts.get(trend_date, 0)
            completion = round((entries_count / active_projects * 100), 1) if active_projects > 0 else 0
            entry_trend.append({
                'date': trend_date.strftime('%b %d'),
                'entries': entries_count,
                'completion': completion
            })

    # ==================== MIS TRACKING ====================

    # MIS pending count (projects missing today's entries)
    mis_pending_count = entries_missing_today

    # ==================== TEAM PERFORMANCE ====================

    # Get all managers
    managers = User.objects.filter(role='operation_manager', is_active=True)

    # Team members with projects assigned
    team_with_projects = coordinators.count() + managers.count()

    # Team performance stats
    team_avg_completion = round(
        sum([coord['completion_rate'] for coord in coordinator_performance]) / len(coordinator_performance), 1
    ) if coordinator_performance else 0

    # ==================== CONTEXT ====================

    context = {
        # Date
        'today': today,
        'selected_date': selected_date,
        'current_time': timezone.now().strftime('%I:%M %p'),

        # Projects (for cards)
        'total_projects_card': total_projects_card,  # Active + Not Started + Notice Period
        'active_projects': active_projects,
        'not_started_projects': not_started_projects,
        'notice_period_projects': notice_period_projects,

        # All Projects
        'total_projects': total_projects,
        'inactive_projects': inactive_projects,
        'waas_projects_count': waas_projects_count,
        'transport_approved_amount': transport_approved_amount,
        'saas_projects': saas_projects,
        'gw_projects': gw_projects,

        # Clients & Vendors & Warehouses
        'total_clients': total_clients,
        'total_vendors': total_vendors,
        'total_warehouses': total_warehouses,

        # Tally Sync
        'sync_status': sync_status,
        'sync_last_time': sync_last_time,
        'sync_records': sync_records,
        'sync_errors': sync_errors,
        'tally_connected': tally_connected,

        # Data Quality
        'projects_without_id': projects_without_id,
        'incomplete_project_cards': incomplete_project_cards,
        'projects_without_coordinator': projects_without_coordinator,
        'incomplete_cards_detail': incomplete_cards_detail,
        'data_quality_score': data_quality_score,
        'projects_with_id_percentage': projects_with_id_percentage,
        'complete_cards_percentage': complete_cards_percentage,

        # Daily Operations (6 Key Metrics)
        'entries_done_today': entries_done_today,
        'entries_missing_today': entries_missing_today,
        'total_space_today': total_space_today_sqft,
        'total_space_today_lakhs': total_space_today_lakhs,
        'total_inventory_today': total_inventory_today,
        'space_variance_alerts': space_variance_alerts,
        'space_variance_projects': space_variance_projects,
        'inventory_turnover': inventory_turnover,
        'inventory_turnover_previous_date': inventory_turnover_previous_date,
        'data_quality_score_daily': data_quality_score_daily,

        # Monthly Operations (6 Key Metrics)
        'selected_month_start': selected_month_start,
        'selected_month_end': selected_month_end,
        'billing_month_start': billing_month_start,
        'billing_month_end': billing_month_end,
        'adhoc_month_count': adhoc_month_count,
        'adhoc_month_value_lakhs': adhoc_month_value_lakhs,
        'monthly_billing_count': monthly_billing_count,
        'monthly_billing_value_lakhs': monthly_billing_value_lakhs,
        'avg_margin': avg_margin,
        'disputes_month_count': disputes_month_count,
        'disputes_open_month': disputes_open_month,
        'disputes_resolved_in_month': disputes_resolved_in_month,
        'max_space_month_lakhs': max_space_month_lakhs,
        'max_inventory_month_crores': max_inventory_month_crores,

        # Monthly Metrics
        'entries_this_month': entries_this_month,
        'working_days': working_days,
        'monthly_completion_rate': monthly_completion_rate,
        'projects_missing_entries': projects_missing_entries,
        'entry_trend': entry_trend,

        # Coordinator Performance
        'coordinator_performance': coordinator_performance,
        'coordinators_count': coordinators.count(),

        # Adhoc Billing
        'adhoc_pending': adhoc_pending,
        'adhoc_approved_month': adhoc_approved_month,
        'adhoc_billed_month': adhoc_billed_month,
        'adhoc_pending_old': adhoc_pending_old,
        'adhoc_pending_amount': adhoc_pending_amount,
        'adhoc_pending_list': adhoc_pending_list,

        # Adhoc Billing - 6 Card Metrics
        'adhoc_month_start': adhoc_month_start,
        'adhoc_month_end': adhoc_month_end,
        'adhoc_total_count': adhoc_total_count,
        'adhoc_total_receivable_lakhs': adhoc_total_receivable_lakhs,
        'adhoc_total_payable_lakhs': adhoc_total_payable_lakhs,
        'adhoc_most_common_type': adhoc_most_common_type,
        'adhoc_most_common_type_code': adhoc_most_common_type_code,
        'adhoc_most_common_type_count': adhoc_most_common_type_count,
        'adhoc_high_value_count': adhoc_high_value_count,
        'adhoc_aging_count': adhoc_aging_count,

        # Monthly Billing
        'billing_generated': billing_generated,
        'billing_sent': billing_sent,
        'billing_pending': billing_pending,
        'billing_paid': billing_paid,
        'billing_pending_controller': billing_pending_controller,
        'billing_approved_controller': billing_approved_controller,
        'billing_rejected_controller': billing_rejected_controller,
        'controller_approved': controller_approved,
        'controller_rejected': controller_rejected,
        'controller_pending': controller_pending,
        'finance_approved': finance_approved,
        'finance_rejected': finance_rejected,
        'finance_pending': finance_pending,

        # Disputes
        'open_disputes': open_disputes,
        'in_progress_disputes': in_progress_disputes,
        'resolved_disputes_month': resolved_disputes_month,
        'critical_disputes_7days': critical_disputes_7days,
        'daily_dispute_percentage': daily_dispute_percentage,
        'monthly_dispute_percentage': monthly_dispute_percentage,
        'dispute_resolution_rate': dispute_resolution_rate,
        'avg_resolution_time': avg_resolution_time,

        # MIS Metrics (for Row 5)
        'projects_with_high_mis_gaps': projects_with_high_mis_gaps,
        'low_compliance_coordinators': low_compliance_coordinators,
        'team_avg_mis_completion': team_avg_mis_completion,
        'consecutive_missing_days': consecutive_missing_days,
        'mis_pending_count': mis_pending_count,

        # MIS - 6 Card Metrics
        'mis_month_start': mis_month_start,
        'mis_month_end': mis_month_end,
        'mis_working_days': mis_working_days,
        'mis_daily_projects': mis_daily_projects,
        'mis_weekly_projects': mis_weekly_projects,
        'mis_monthly_projects': mis_monthly_projects,
        'total_entries_submitted': total_entries_submitted,

        # Alerts
        'total_alerts': total_alerts,
        'critical_issues': critical_issues,

        # MIS
        'mis_pending_count': mis_pending_count,

        # Team
        'team_with_projects': team_with_projects,
        'team_avg_completion': team_avg_completion,
        'managers_count': managers.count(),

        # Top Lists
        'top_states': top_states_list,
        'top_clients': top_clients_list,
    }

    return render(request, 'dashboards/operations_controller/dashboard.html', context)


@role_required(['operation_controller', 'operation_manager', 'admin', 'director'])
def operation_controller_team_performance(request):
    """
    Team Performance Analysis
    Detailed KPI dashboard for coordinators and managers with project assignments
    """

    # Date context
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)

    # Calculate working days this month
    working_days = 0
    current_date = current_month_start
    while current_date <= today:
        if current_date.weekday() != 6:  # Not Sunday
            working_days += 1
        current_date += timedelta(days=1)

    # Get all coordinators and managers
    coordinators = User.objects.filter(role='operation_coordinator', is_active=True)
    managers = User.objects.filter(role='operation_manager', is_active=True)

    # Combine both roles for unified processing
    team_members = list(coordinators) + list(managers)

    # ==================== INDIVIDUAL PERFORMANCE ====================

    team_performance = []

    for member in team_members:
        member_name = member.get_full_name()

        # Primary projects (where they are the main coordinator/manager)
        primary_projects = ProjectCode.objects.filter(
            operation_coordinator=member_name,
            project_status='Active',
            series_type='WAAS'
        )
        primary_count = primary_projects.count()

        # Backup projects
        backup_projects = ProjectCode.objects.filter(
            backup_coordinator=member_name,
            project_status='Active',
            series_type='WAAS'
        )
        backup_count = backup_projects.count()

        # All projects (primary + backup)
        all_projects = primary_projects | backup_projects
        all_projects = all_projects.distinct()
        total_projects = all_projects.count()

        # Skip if no projects assigned
        if total_projects == 0:
            continue

        # Entry completion - Today
        entries_today = DailySpaceUtilization.objects.filter(
            project__in=all_projects,
            entry_date=today
        ).values('project_id').distinct().count()

        completion_today = round(
            (entries_today / total_projects * 100), 1
        ) if total_projects > 0 else 0

        # Entry completion - This month
        entries_this_month = DailySpaceUtilization.objects.filter(
            project__in=all_projects,
            entry_date__gte=current_month_start
        ).count()

        expected_entries = total_projects * working_days
        completion_month = round(
            (entries_this_month / expected_entries * 100), 1
        ) if expected_entries > 0 else 0

        # Missing entries count
        missing_entries = expected_entries - entries_this_month

        # MIS Pending (projects missing today's entries)
        mis_pending = total_projects - entries_today

        # Adhoc billing pending
        adhoc_pending = AdhocBillingEntry.objects.filter(
            project__in=all_projects,
            status__code='pending'
        ).count()

        adhoc_pending_amount = AdhocBillingEntry.objects.filter(
            project__in=all_projects,
            status__code='pending'
        ).aggregate(total=Sum('total_client_amount'))['total'] or 0
        adhoc_pending_amount = float(adhoc_pending_amount) / 100000

        # Adhoc approved this month
        adhoc_approved_month = AdhocBillingEntry.objects.filter(
            project__in=all_projects,
            status__code='approved',
            event_date__gte=current_month_start
        ).count()

        # Monthly billing
        billing_generated = MonthlyBilling.objects.filter(
            project__in=all_projects,
            service_month__gte=current_month_start,
            status__code='generated'
        ).count()

        billing_sent = MonthlyBilling.objects.filter(
            project__in=all_projects,
            service_month__gte=current_month_start,
            status__code='sent'
        ).count()

        billing_paid = MonthlyBilling.objects.filter(
            project__in=all_projects,
            service_month__gte=current_month_start,
            status__code='paid'
        ).count()

        billing_pending = MonthlyBilling.objects.filter(
            project__in=all_projects,
            service_month__gte=current_month_start,
            status__code='pending'
        ).count()

        # Disputes
        disputes_open = DisputeLog.objects.filter(
            project__in=all_projects,
            status__code='open'
        ).count()

        disputes_in_progress = DisputeLog.objects.filter(
            project__in=all_projects,
            status__code='in_progress'
        ).count()

        disputes_resolved_month = DisputeLog.objects.filter(
            project__in=all_projects,
            status__code='resolved',
            resolved_at__gte=current_month_start
        ).count()

        disputes_total = disputes_open + disputes_in_progress

        # Dispute resolution percentage
        total_disputes_ever = disputes_open + disputes_in_progress + disputes_resolved_month
        dispute_resolution_rate = round(
            (disputes_resolved_month / total_disputes_ever * 100), 1
        ) if total_disputes_ever > 0 else 0

        # Calculate 7-day trend
        trend_data = []
        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            if date.weekday() != 6:  # Not Sunday
                day_entries = DailySpaceUtilization.objects.filter(
                    project__in=all_projects,
                    entry_date=date
                ).values('project_id').distinct().count()

                day_completion = round(
                    (day_entries / total_projects * 100), 1
                ) if total_projects > 0 else 0

                trend_data.append({
                    'date': date.strftime('%b %d'),
                    'completion': day_completion
                })

        # Performance score (weighted average)
        # 40% monthly completion + 30% today's completion + 20% low adhoc pending + 10% low disputes
        score_completion_month = completion_month * 0.4
        score_completion_today = completion_today * 0.3
        score_adhoc = (100 - min(adhoc_pending * 10, 100)) * 0.2  # Penalty for pending adhoc
        score_disputes = (100 - min(disputes_total * 20, 100)) * 0.1  # Penalty for disputes

        performance_score = round(
            score_completion_month + score_completion_today + score_adhoc + score_disputes,
            1
        )

        # Performance grade (Updated thresholds)
        if performance_score >= 99:
            grade = 'A'
            grade_color = 'green'
        elif performance_score >= 95:
            grade = 'B'
            grade_color = 'blue'
        elif performance_score >= 90:
            grade = 'C'
            grade_color = 'amber'
        else:
            grade = 'D'
            grade_color = 'red'

        # Completion color
        if completion_month >= 80:
            completion_color = 'green'
        elif completion_month >= 60:
            completion_color = 'amber'
        else:
            completion_color = 'red'

        team_performance.append({
            'member': member,
            'name': member_name,
            'role': 'Coordinator' if member.role == 'operation_coordinator' else 'Manager',
            'initials': ''.join([n[0] for n in member_name.split()[:2]]),
            'primary_projects': primary_count,
            'backup_projects': backup_count,
            'total_projects': total_projects,
            'entries_today': entries_today,
            'completion_today': completion_today,
            'entries_this_month': entries_this_month,
            'expected_entries': expected_entries,
            'completion_month': completion_month,
            'missing_entries': missing_entries,
            'mis_pending': mis_pending,
            'adhoc_pending': adhoc_pending,
            'adhoc_pending_amount': adhoc_pending_amount,
            'adhoc_approved_month': adhoc_approved_month,
            'disputes_open': disputes_open,
            'disputes_in_progress': disputes_in_progress,
            'disputes_resolved_month': disputes_resolved_month,
            'disputes_total': disputes_total,
            'dispute_resolution_rate': dispute_resolution_rate,
            'billing_generated': billing_generated,
            'billing_sent': billing_sent,
            'billing_paid': billing_paid,
            'billing_pending': billing_pending,
            'trend_data': trend_data,
            'performance_score': performance_score,
            'grade': grade,
            'grade_color': grade_color,
            'completion_color': completion_color,
        })

    # Sort alphabetically by name (default)
    team_performance.sort(key=lambda x: x['name'])

    # ==================== OVERVIEW STATS ====================

    total_team_members = len(team_performance)

    avg_performance = round(
        sum([m['performance_score'] for m in team_performance]) / total_team_members,
        1
    ) if total_team_members > 0 else 0

    total_waas_projects = sum([m['total_projects'] for m in team_performance])

    # Critical alerts
    low_performers = [m for m in team_performance if m['completion_month'] < 90]
    high_adhoc_pending = [m for m in team_performance if m['adhoc_pending'] > 5]
    mis_delays = [m for m in team_performance if m['mis_pending'] > 3]
    old_disputes = [m for m in team_performance if m['disputes_open'] > 0]

    critical_alerts = len(low_performers) + len(high_adhoc_pending) + len(mis_delays) + len(old_disputes)

    # Sort lists for adhoc and billing sections (alphabetically)
    adhoc_by_user = sorted(team_performance, key=lambda x: x['name'])
    billing_by_user = sorted(team_performance, key=lambda x: x['name'])

    # Performance distribution
    grade_a = len([m for m in team_performance if m['grade'] == 'A'])
    grade_b = len([m for m in team_performance if m['grade'] == 'B'])
    grade_c = len([m for m in team_performance if m['grade'] == 'C'])
    grade_d = len([m for m in team_performance if m['grade'] == 'D'])

    # ==================== CONTEXT ====================

    context = {
        'today': today,
        'current_time': timezone.now().strftime('%I:%M %p'),
        'working_days': working_days,

        # Overview
        'total_team_members': total_team_members,
        'avg_performance': avg_performance,
        'total_waas_projects': total_waas_projects,
        'critical_alerts': critical_alerts,

        # Team performance
        'team_performance': team_performance,

        # Performance distribution
        'grade_a': grade_a,
        'grade_b': grade_b,
        'grade_c': grade_c,
        'grade_d': grade_d,

        # Action items
        'low_performers': low_performers,
        'high_adhoc_pending': high_adhoc_pending,
        'mis_delays': mis_delays,
        'old_disputes': old_disputes,

        # User-wise lists
        'adhoc_by_user': adhoc_by_user,
        'billing_by_user': billing_by_user,
    }

    return render(request, 'dashboards/operations_controller/team_performance.html', context)


@role_required(['operation_controller', 'operation_manager', 'admin', 'director'])
def operation_controller_member_detail(request, user_id):
    """
    Individual Member Detailed Analysis
    Comprehensive performance analysis with visualizations for a specific team member
    """

    # Get the team member
    try:
        member = User.objects.get(id=user_id, is_active=True)
        if member.role not in ['operation_coordinator', 'operation_manager']:
            messages.error(request, "Invalid team member.")
            return redirect('accounts:operation_controller_team')
    except User.DoesNotExist:
        messages.error(request, "Team member not found.")
        return redirect('accounts:operation_controller_team')

    member_name = member.get_full_name()

    # Date context
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)

    # Calculate working days (this month)
    working_days_this_month = 0
    current_date = current_month_start
    while current_date <= today:
        if current_date.weekday() != 6:  # Not Sunday
            working_days_this_month += 1
        current_date += timedelta(days=1)

    # Calculate working days (last month)
    working_days_last_month = 0
    current_date = last_month_start
    while current_date <= last_month_end:
        if current_date.weekday() != 6:
            working_days_last_month += 1
        current_date += timedelta(days=1)

    # ==================== PROJECTS ====================

    # Primary projects
    primary_projects = ProjectCode.objects.filter(
        operation_coordinator=member_name,
        project_status='Active',
        series_type='WAAS'
    )
    primary_count = primary_projects.count()

    # Backup projects
    backup_projects = ProjectCode.objects.filter(
        backup_coordinator=member_name,
        project_status='Active',
        series_type='WAAS'
    )
    backup_count = backup_projects.count()

    # All projects
    all_projects = (primary_projects | backup_projects).distinct()
    total_projects = all_projects.count()

    # ==================== ENTRY COMPLETION ====================

    # Today's entries
    entries_today = DailySpaceUtilization.objects.filter(
        project__in=all_projects,
        entry_date=today
    ).values('project_id').distinct().count()

    completion_today = round(
        (entries_today / total_projects * 100), 1
    ) if total_projects > 0 else 0

    # This month's entries
    entries_this_month = DailySpaceUtilization.objects.filter(
        project__in=all_projects,
        entry_date__gte=current_month_start
    ).count()

    expected_entries_month = total_projects * working_days_this_month
    completion_month = round(
        (entries_this_month / expected_entries_month * 100), 1
    ) if expected_entries_month > 0 else 0

    # Last month's entries
    entries_last_month = DailySpaceUtilization.objects.filter(
        project__in=all_projects,
        entry_date__gte=last_month_start,
        entry_date__lte=last_month_end
    ).count()

    expected_entries_last_month = total_projects * working_days_last_month
    completion_last_month = round(
        (entries_last_month / expected_entries_last_month * 100), 1
    ) if expected_entries_last_month > 0 else 0

    # 30-day trend
    entry_trend_30_days = []
    trend_labels = []
    trend_data = []

    for i in range(29, -1, -1):
        date = today - timedelta(days=i)
        if date.weekday() != 6:  # Not Sunday
            day_entries = DailySpaceUtilization.objects.filter(
                project__in=all_projects,
                entry_date=date
            ).values('project_id').distinct().count()

            day_completion = round(
                (day_entries / total_projects * 100), 1
            ) if total_projects > 0 else 0

            entry_trend_30_days.append({
                'date': date.strftime('%b %d'),
                'completion': day_completion,
                'entries': day_entries
            })

            trend_labels.append(date.strftime('%b %d'))
            trend_data.append(day_completion)

    # ==================== ADHOC BILLING ====================

    # Pending adhoc
    adhoc_pending = AdhocBillingEntry.objects.filter(
        project__in=all_projects,
        status__code='pending'
    ).count()

    adhoc_pending_amount = AdhocBillingEntry.objects.filter(
        project__in=all_projects,
        status__code='pending'
    ).aggregate(total=Sum('total_client_amount'))['total'] or 0
    adhoc_pending_amount = float(adhoc_pending_amount) / 100000

    # Approved this month
    adhoc_approved_month = AdhocBillingEntry.objects.filter(
        project__in=all_projects,
        status__code='approved',
        event_date__gte=current_month_start
    ).count()

    # Approved last month
    adhoc_approved_last_month = AdhocBillingEntry.objects.filter(
        project__in=all_projects,
        status__code='approved',
        event_date__gte=last_month_start,
        event_date__lte=last_month_end
    ).count()

    # Billed this month
    adhoc_billed_month = AdhocBillingEntry.objects.filter(
        project__in=all_projects,
        status__code='billed',
        event_date__gte=current_month_start
    ).count()

    # ==================== MONTHLY BILLING ====================

    # Monthly billing statuses are: draft, pending_controller, pending_finance, approved, controller_rejected, finance_rejected
    billing_generated = MonthlyBilling.objects.filter(
        project__in=all_projects,
        service_month__gte=current_month_start,
        status_id__in=['pending_controller', 'pending_finance']
    ).count()

    billing_sent = MonthlyBilling.objects.filter(
        project__in=all_projects,
        service_month__gte=current_month_start,
        status_id='approved'
    ).count()

    billing_paid = billing_sent  # For now, approved = paid (can be changed later if payment tracking is added)

    billing_pending = MonthlyBilling.objects.filter(
        project__in=all_projects,
        service_month__gte=current_month_start,
        status_id='draft'
    ).count()

    # ==================== DISPUTES ====================

    disputes_open = DisputeLog.objects.filter(
        project__in=all_projects,
        status__code='open'
    ).count()

    disputes_in_progress = DisputeLog.objects.filter(
        project__in=all_projects,
        status__code='in_progress'
    ).count()

    disputes_resolved_month = DisputeLog.objects.filter(
        project__in=all_projects,
        status__code='resolved',
        resolved_at__gte=current_month_start
    ).count()

    disputes_resolved_last_month = DisputeLog.objects.filter(
        project__in=all_projects,
        status__code='resolved',
        resolved_at__gte=last_month_start,
        resolved_at__lte=last_month_end
    ).count()

    disputes_total = disputes_open + disputes_in_progress

    # Dispute resolution rate
    total_disputes_ever = disputes_open + disputes_in_progress + disputes_resolved_month
    dispute_resolution_rate = round(
        (disputes_resolved_month / total_disputes_ever * 100), 1
    ) if total_disputes_ever > 0 else 0

    # ==================== MIS ====================

    mis_pending_today = total_projects - entries_today

    # ==================== PERFORMANCE SCORE ====================

    # Calculate performance score
    score_completion_month = completion_month * 0.4
    score_completion_today = completion_today * 0.3
    score_adhoc = (100 - min(adhoc_pending * 10, 100)) * 0.2
    score_disputes = (100 - min(disputes_total * 20, 100)) * 0.1

    performance_score = round(
        score_completion_month + score_completion_today + score_adhoc + score_disputes,
        1
    )

    # Last month's performance score
    score_completion_last_month = completion_last_month * 0.4
    adhoc_pending_last_month = AdhocBillingEntry.objects.filter(
        project__in=all_projects,
        status__code='pending',
        event_date__lte=last_month_end
    ).count()
    score_adhoc_last = (100 - min(adhoc_pending_last_month * 10, 100)) * 0.2

    disputes_last_month = disputes_open + disputes_in_progress  # Simplified
    score_disputes_last = (100 - min(disputes_last_month * 20, 100)) * 0.1

    performance_score_last_month = round(
        score_completion_last_month + score_adhoc_last + score_disputes_last,
        1
    )

    # Performance grade
    if performance_score >= 99:
        grade = 'A'
        grade_color = 'green'
    elif performance_score >= 95:
        grade = 'B'
        grade_color = 'blue'
    elif performance_score >= 90:
        grade = 'C'
        grade_color = 'amber'
    else:
        grade = 'D'
        grade_color = 'red'

    # ==================== TEAM COMPARISON ====================

    # Get all team members for comparison
    all_coordinators = User.objects.filter(role='operation_coordinator', is_active=True)
    all_managers = User.objects.filter(role='operation_manager', is_active=True)
    all_team_members = list(all_coordinators) + list(all_managers)

    team_scores = []
    for tm in all_team_members:
        tm_projects = ProjectCode.objects.filter(
            Q(operation_coordinator=tm.get_full_name()) | Q(backup_coordinator=tm.get_full_name()),
            project_status='Active',
            series_type='WAAS'
        ).distinct().count()

        if tm_projects > 0:
            tm_entries = DailySpaceUtilization.objects.filter(
                project__operation_coordinator=tm.get_full_name(),
                entry_date__gte=current_month_start
            ).count()
            tm_expected = tm_projects * working_days_this_month
            tm_completion = round((tm_entries / tm_expected * 100), 1) if tm_expected > 0 else 0

            # Simplified score for comparison
            tm_score = tm_completion * 0.7  # Just use completion as proxy
            team_scores.append(tm_score)

    team_avg_score = round(sum(team_scores) / len(team_scores), 1) if team_scores else 0

    # Calculate rank
    team_scores_sorted = sorted(team_scores, reverse=True)
    try:
        rank = team_scores_sorted.index(performance_score * 0.7) + 1
    except ValueError:
        rank = len(team_scores_sorted) + 1

    percentile = round(((len(team_scores) - rank + 1) / len(team_scores) * 100), 1) if len(team_scores) > 0 else 0

    # ==================== PROJECT-WISE BREAKDOWN ====================

    project_breakdown = []
    for project in all_projects:
        # Entry completion for this project
        project_entries = DailySpaceUtilization.objects.filter(
            project=project,
            entry_date__gte=current_month_start
        ).count()

        project_expected = working_days_this_month
        project_completion = round(
            (project_entries / project_expected * 100), 1
        ) if project_expected > 0 else 0

        # Adhoc for this project
        project_adhoc = AdhocBillingEntry.objects.filter(
            project=project,
            status__code='pending'
        ).count()

        # Billing for this project
        project_billing = MonthlyBilling.objects.filter(
            project=project,
            service_month__gte=current_month_start
        ).first()

        # Disputes for this project
        project_disputes = DisputeLog.objects.filter(
            project=project,
            status__code__in=['open', 'in_progress']
        ).count()

        project_breakdown.append({
            'project_code': project.project_code,
            'client_name': project.client_name,
            'is_primary': project.operation_coordinator == member_name,
            'entry_completion': project_completion,
            'adhoc_pending': project_adhoc,
            'billing_status': project_billing.status.label if project_billing else 'Not Generated',
            'disputes': project_disputes,
        })

    # Sort by completion rate (ascending to show problems first)
    project_breakdown.sort(key=lambda x: x['entry_completion'])

    # ==================== ADHOC BILLING DETAILS ====================

    # Get all adhoc entries (sorted by latest to oldest)
    adhoc_entries_list = AdhocBillingEntry.objects.filter(
        project__in=all_projects
    ).select_related('project', 'status').prefetch_related('line_items').order_by('-event_date', '-created_at')[:50]

    adhoc_details = []
    for adhoc in adhoc_entries_list:
        # Get line item descriptions (concatenate all line items)
        line_items_desc = []
        for item in adhoc.line_items.all()[:3]:  # First 3 items only
            line_items_desc.append(f"{item.charge_type.label}: {item.description[:50]}")

        description = '; '.join(line_items_desc) if line_items_desc else adhoc.billing_remarks or 'No details'

        adhoc_details.append({
            'id': adhoc.id,
            'project_code': adhoc.project.project_code,
            'client_name': adhoc.project.client_name,
            'event_date': adhoc.event_date,
            'description': description,
            'billing_remarks': adhoc.billing_remarks or '',
            'status': adhoc.status.label,
            'status_code': adhoc.status.code,
            'client_amount': float(adhoc.total_client_amount or 0) / 100000,
            'vendor_amount': float(adhoc.total_vendor_amount or 0) / 100000,
            'created_at': adhoc.created_at,
            'updated_at': adhoc.updated_at,
            'line_items_count': adhoc.line_items.count(),
        })

    # ==================== DISPUTES DETAILS ====================

    # Get all disputes (sorted by latest to oldest)
    disputes_list = DisputeLog.objects.filter(
        project__in=all_projects
    ).select_related('project', 'status', 'category', 'priority').order_by('-raised_at')[:50]

    disputes_details = []
    for dispute in disputes_list:
        # Calculate days open/resolved
        if dispute.status.code == 'resolved' and dispute.resolved_at:
            days_to_resolve = (dispute.resolved_at.date() - dispute.raised_at.date()).days
            days_display = f"{days_to_resolve} days"
        else:
            days_open = (today - dispute.raised_at.date()).days
            days_display = f"{days_open} days open"

        disputes_details.append({
            'id': dispute.dispute_id,
            'project_code': dispute.project.project_code,
            'client_name': dispute.project.client_name,
            'raised_at': dispute.raised_at,
            'resolved_at': dispute.resolved_at,
            'status': dispute.status.label,
            'status_code': dispute.status.code,
            'category': dispute.category.label,
            'title': dispute.title or 'Untitled',
            'description': dispute.description,
            'resolution': dispute.resolution,
            'priority': dispute.priority.label,
            'days_display': days_display,
        })

    # ==================== CONTEXT ====================

    context = {
        # Member info
        'member': member,
        'member_name': member_name,
        'member_role': 'Coordinator' if member.role == 'operation_coordinator' else 'Manager',
        'member_initials': ''.join([n[0] for n in member_name.split()[:2]]),

        # Date
        'today': today,
        'current_time': timezone.now().strftime('%I:%M %p'),
        'working_days_this_month': working_days_this_month,
        'working_days_last_month': working_days_last_month,

        # Projects
        'primary_count': primary_count,
        'backup_count': backup_count,
        'total_projects': total_projects,

        # Entry completion
        'entries_today': entries_today,
        'completion_today': completion_today,
        'entries_this_month': entries_this_month,
        'expected_entries_month': expected_entries_month,
        'completion_month': completion_month,
        'completion_last_month': completion_last_month,
        'entry_trend_30_days': entry_trend_30_days,
        'trend_labels': json.dumps(trend_labels),
        'trend_data': json.dumps(trend_data),

        # Adhoc billing
        'adhoc_pending': adhoc_pending,
        'adhoc_pending_amount': adhoc_pending_amount,
        'adhoc_approved_month': adhoc_approved_month,
        'adhoc_approved_last_month': adhoc_approved_last_month,
        'adhoc_billed_month': adhoc_billed_month,

        # Monthly billing
        'billing_generated': billing_generated,
        'billing_sent': billing_sent,
        'billing_paid': billing_paid,
        'billing_pending': billing_pending,

        # Disputes
        'disputes_open': disputes_open,
        'disputes_in_progress': disputes_in_progress,
        'disputes_total': disputes_total,
        'disputes_resolved_month': disputes_resolved_month,
        'disputes_resolved_last_month': disputes_resolved_last_month,
        'dispute_resolution_rate': dispute_resolution_rate,

        # MIS
        'mis_pending_today': mis_pending_today,

        # Performance
        'performance_score': performance_score,
        'performance_score_last_month': performance_score_last_month,
        'grade': grade,
        'grade_color': grade_color,

        # Team comparison
        'team_avg_score': team_avg_score,
        'rank': rank,
        'total_team_members': len(team_scores),
        'percentile': percentile,

        # Project breakdown
        'project_breakdown': project_breakdown,

        # Adhoc & Disputes details
        'adhoc_details': adhoc_details,
        'disputes_details': disputes_details,
    }

    return render(request, 'dashboards/operations_controller/member_detail.html', context)


# ==================== DAILY OPERATIONS DETAIL PAGES ====================

@login_required
def daily_missing_entries_detail(request):
    """
    Detail page for Missing Entries - Shows all active projects without entries for selected date
    """
    # Role check
    if request.user.role not in ['operation_controller', 'admin', 'director']:
        messages.error(request, "Access denied. Operation Controller access required.")
        return redirect('accounts:dashboard')

    # Date filtering
    selected_date_str = request.GET.get('selected_date')
    if selected_date_str:
        try:
            from datetime import datetime
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    today = timezone.now().date()

    # Coordinator filtering
    selected_coordinator = request.GET.get('coordinator', '')

    # Get WAAS projects (Active & Notice Period) with entries for selected date
    projects_with_entries = DailySpaceUtilization.objects.filter(
        entry_date=selected_date,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).values_list('project_id', flat=True).distinct()

    # Get WAAS projects (Active & Notice Period) without entries
    missing_projects_query = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period']
    ).exclude(
        project_id__in=projects_with_entries
    )

    # Apply coordinator filter
    if selected_coordinator:
        missing_projects_query = missing_projects_query.filter(operation_coordinator=selected_coordinator)

    missing_projects = missing_projects_query.order_by('client_name', 'project_code')

    # Get all coordinators for dropdown
    all_coordinators = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period']
    ).exclude(
        operation_coordinator__isnull=True
    ).exclude(
        operation_coordinator=''
    ).values_list('operation_coordinator', flat=True).distinct().order_by('operation_coordinator')

    # Calculate consecutive missing days for each project (excluding Sundays)
    projects_data = []
    for project in missing_projects:
        # Find last entry date
        last_entry = DailySpaceUtilization.objects.filter(
            project=project
        ).order_by('-entry_date').first()

        consecutive_days = 0
        if last_entry:
            # Count only non-Sunday days between last entry and selected date
            current_date = last_entry.entry_date + timedelta(days=1)
            while current_date <= selected_date:
                if current_date.weekday() != 6:  # 6 = Sunday
                    consecutive_days += 1
                current_date += timedelta(days=1)

        projects_data.append({
            'project': project,
            'last_entry_date': last_entry.entry_date if last_entry else None,
            'consecutive_days': consecutive_days,
        })

    context = {
        'today': today,
        'selected_date': selected_date,
        'projects_data': projects_data,
        'total_missing': len(projects_data),
        'all_coordinators': all_coordinators,
        'selected_coordinator': selected_coordinator,
    }

    return render(request, 'dashboards/operations_controller/daily_missing_entries.html', context)


@login_required
def daily_space_utilization_detail(request):
    """
    Unified detail page for Space & Inventory - Shows combined breakdown by project
    """
    # Role check
    if request.user.role not in ['operation_controller', 'admin', 'director']:
        messages.error(request, "Access denied. Operation Controller access required.")
        return redirect('accounts:dashboard')

    # Date filtering
    selected_date_str = request.GET.get('selected_date')
    if selected_date_str:
        try:
            from datetime import datetime
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    today = timezone.now().date()

    # Coordinator filtering
    selected_coordinator = request.GET.get('coordinator', '')

    # Get all WAAS entries (Active & Notice Period) for selected date - ordered by client name
    entries_query = DailySpaceUtilization.objects.filter(
        entry_date=selected_date,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period']
    ).select_related('project', 'unit')

    # Apply coordinator filter
    if selected_coordinator:
        entries_query = entries_query.filter(project__operation_coordinator=selected_coordinator)

    entries = entries_query.order_by('project__client_name', 'project__project_code')

    # Get all coordinators for dropdown
    all_coordinators = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period']
    ).exclude(
        operation_coordinator__isnull=True
    ).exclude(
        operation_coordinator=''
    ).values_list('operation_coordinator', flat=True).distinct().order_by('operation_coordinator')

    # Calculate space and inventory breakdown with dynamic unit tracking
    projects_data = []
    unit_totals = {}  # Dynamic tracking: {unit_name: {'value': total, 'in_sqft': total_sqft}}
    total_space_combined_sqft = Decimal('0')
    total_inventory = Decimal('0')

    for entry in entries:
        space_value = entry.space_utilized or Decimal('0')
        inventory_value = entry.inventory_value or Decimal('0')
        unit_name = entry.unit.label if entry.unit else 'Unknown'
        unit_id = entry.unit_id

        # Calculate space in sq ft (only for sqft and pallet)
        space_in_sqft = Decimal('0')
        if unit_id == 'sqft':
            space_in_sqft = space_value
        elif unit_id == 'pallet':
            space_in_sqft = space_value * Decimal('25')
        # order, unit, lumpsum do not contribute to sq ft total

        # Track unit totals dynamically
        if unit_name not in unit_totals:
            unit_totals[unit_name] = {'value': Decimal('0'), 'in_sqft': Decimal('0')}

        unit_totals[unit_name]['value'] += space_value
        unit_totals[unit_name]['in_sqft'] += space_in_sqft

        # Add to combined total (only sqft and pallet converted units)
        total_space_combined_sqft += space_in_sqft
        total_inventory += inventory_value

        projects_data.append({
            'project': entry.project,
            'space_utilized': round(float(space_value), 2),
            'unit_name': unit_name,
            'inventory_value': round(float(inventory_value), 2),
            'inventory_in_crores': round(float(inventory_value) / 10000000, 2),
        })

    # Convert unit_totals to rounded floats for template
    unit_totals_display = {
        name: {
            'value': round(float(data['value']), 2),
            'in_sqft': round(float(data['in_sqft']), 2)
        }
        for name, data in unit_totals.items()
    }

    context = {
        'today': today,
        'selected_date': selected_date,
        'projects_data': projects_data,
        'total_projects': len(projects_data),
        'total_space_combined_sqft': round(float(total_space_combined_sqft), 2),
        'total_space_combined_lakhs': round(float(total_space_combined_sqft) / 100000, 2),
        'unit_totals': unit_totals_display,
        'total_inventory_crores': round(float(total_inventory) / 10000000, 2),
        'all_coordinators': all_coordinators,
        'selected_coordinator': selected_coordinator,
    }

    return render(request, 'dashboards/operations_controller/daily_space_inventory.html', context)


@login_required
def daily_inventory_value_detail(request):
    """
    Redirect to unified Space & Inventory page
    """
    # Redirect to the unified view with preserved query parameters
    return redirect('accounts:daily_space_utilization_detail' + ('?' + request.GET.urlencode() if request.GET else ''))


@login_required
def daily_variance_alerts_detail(request):
    """
    Detail page for Variance Alerts - Shows projects with >30% space change
    """
    # Role check
    if request.user.role not in ['operation_controller', 'admin', 'director']:
        messages.error(request, "Access denied. Operation Controller access required.")
        return redirect('accounts:dashboard')

    # Date filtering
    selected_date_str = request.GET.get('selected_date')
    if selected_date_str:
        try:
            from datetime import datetime
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    today = timezone.now().date()

    # Coordinator filtering
    selected_coordinator = request.GET.get('coordinator', '')

    # Get project queryset
    projects_query = ProjectCode.objects.filter(series_type='WAAS', project_status__in=['Active', 'Notice Period'])

    # Apply coordinator filter
    if selected_coordinator:
        projects_query = projects_query.filter(operation_coordinator=selected_coordinator)

    # Get all coordinators for dropdown
    all_coordinators = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period']
    ).exclude(
        operation_coordinator__isnull=True
    ).exclude(
        operation_coordinator=''
    ).values_list('operation_coordinator', flat=True).distinct().order_by('operation_coordinator')

    # Calculate variance alerts (WAAS Active & Notice Period)
    variance_projects = []

    for project in projects_query:
        try:
            # Get today's entry
            today_entry = DailySpaceUtilization.objects.get(project=project, entry_date=selected_date)

            # Find the most recent previous entry (within last 7 days)
            previous_entry = DailySpaceUtilization.objects.filter(
                project=project,
                entry_date__lt=selected_date,
                entry_date__gte=selected_date - timedelta(days=7)
            ).order_by('-entry_date').first()

            if previous_entry:
                # Convert to sqft
                today_space = today_entry.space_utilized or Decimal('0')
                previous_space = previous_entry.space_utilized or Decimal('0')

                if today_entry.unit_id == 'pallet':
                    today_space = today_space * Decimal('25')
                if previous_entry.unit_id == 'pallet':
                    previous_space = previous_space * Decimal('25')

                # Calculate percentage change
                if previous_space > 0:
                    change_pct = ((today_space - previous_space) / previous_space * 100)
                    abs_change_pct = abs(change_pct)

                    if abs_change_pct > 30:
                        variance_projects.append({
                            'project': project,
                            'previous_date': previous_entry.entry_date,
                            'previous_space': round(float(previous_space), 2),
                            'today_space': round(float(today_space), 2),
                            'change_pct': round(float(change_pct), 1),
                            'abs_change_pct': round(float(abs_change_pct), 1),
                            'change_direction': 'increase' if change_pct > 0 else 'decrease',
                        })
        except DailySpaceUtilization.DoesNotExist:
            pass

    # Sort by client name, then project code
    variance_projects.sort(key=lambda x: (x['project'].client_name, x['project'].project_code))

    context = {
        'today': today,
        'selected_date': selected_date,
        'variance_projects': variance_projects,
        'total_alerts': len(variance_projects),
        'all_coordinators': all_coordinators,
        'selected_coordinator': selected_coordinator,
    }

    return render(request, 'dashboards/operations_controller/daily_variance_alerts.html', context)


@login_required
def daily_inventory_turnover_detail(request):
    """
    Detail page for Inventory Turnover - Shows inventory change analysis
    """
    # Role check
    if request.user.role not in ['operation_controller', 'admin', 'director']:
        messages.error(request, "Access denied. Operation Controller access required.")
        return redirect('accounts:dashboard')

    # Date filtering
    selected_date_str = request.GET.get('selected_date')
    if selected_date_str:
        try:
            from datetime import datetime
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    today = timezone.now().date()

    # Coordinator filtering
    selected_coordinator = request.GET.get('coordinator', '')

    # Build coordinator filters
    coordinator_filter = {}
    if selected_coordinator:
        coordinator_filter['project__operation_coordinator'] = selected_coordinator

    # Get today's inventory (WAAS Active & Notice Period)
    today_inventory = DailySpaceUtilization.objects.filter(
        entry_date=selected_date,
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period'],
        **coordinator_filter
    ).aggregate(total=Sum('inventory_value'))['total'] or 0

    # Find most recent previous date with data (check day-by-day up to 7 days back)
    # This checks Saturday before Friday if today is Monday, ensuring proper sequential comparison
    previous_date = None
    previous_inventory = 0
    inventory_change = 0
    inventory_turnover_pct = 0

    for days_back in range(1, 8):
        check_date = selected_date - timedelta(days=days_back)
        check_inventory = DailySpaceUtilization.objects.filter(
            entry_date=check_date,
            project__series_type='WAAS',
            project__project_status__in=['Active', 'Notice Period'],
            **coordinator_filter
        ).aggregate(total=Sum('inventory_value'))['total'] or 0

        if check_inventory > 0:
            previous_date = check_date
            previous_inventory = check_inventory
            inventory_change = float(today_inventory) - float(previous_inventory)
            inventory_turnover_pct = round((inventory_change / float(previous_inventory) * 100), 2)
            break

    # Get project queryset
    projects_query = ProjectCode.objects.filter(series_type='WAAS', project_status__in=['Active', 'Notice Period'])
    if selected_coordinator:
        projects_query = projects_query.filter(operation_coordinator=selected_coordinator)

    # Get all coordinators for dropdown
    all_coordinators = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period']
    ).exclude(
        operation_coordinator__isnull=True
    ).exclude(
        operation_coordinator=''
    ).values_list('operation_coordinator', flat=True).distinct().order_by('operation_coordinator')

    # Get project-wise breakdown (WAAS Active & Notice Period)
    projects_data = []

    for project in projects_query:
        try:
            today_entry = DailySpaceUtilization.objects.get(project=project, entry_date=selected_date)
            today_inv = today_entry.inventory_value or Decimal('0')

            previous_inv = Decimal('0')
            if previous_date:
                try:
                    prev_entry = DailySpaceUtilization.objects.get(project=project, entry_date=previous_date)
                    previous_inv = prev_entry.inventory_value or Decimal('0')
                except DailySpaceUtilization.DoesNotExist:
                    pass

            if previous_inv > 0:
                change = float(today_inv) - float(previous_inv)
                change_pct = round((change / float(previous_inv) * 100), 1)

                # Only include projects where actual change occurred (not zero)
                if change != 0:
                    projects_data.append({
                        'project': project,
                        'previous_inventory': round(float(previous_inv), 2),
                        'today_inventory': round(float(today_inv), 2),
                        'change': round(change, 2),
                        'change_pct': change_pct,
                        'abs_change_pct': abs(change_pct),
                        'change_direction': 'increase' if change > 0 else 'decrease',
                    })
        except DailySpaceUtilization.DoesNotExist:
            pass

    # Sort by client name, then project code
    projects_data.sort(key=lambda x: (x['project'].client_name, x['project'].project_code))

    context = {
        'today': today,
        'selected_date': selected_date,
        'previous_date': previous_date,
        'today_inventory': round(float(today_inventory) / 10000000, 2),  # Convert to crores
        'previous_inventory': round(float(previous_inventory) / 10000000, 2),  # Convert to crores
        'inventory_change': round(inventory_change / 10000000, 2),  # Convert to crores
        'inventory_turnover_pct': inventory_turnover_pct,
        'projects_data': projects_data,
        'total_projects': len(projects_data),
        'all_coordinators': all_coordinators,
        'selected_coordinator': selected_coordinator,
    }

    return render(request, 'dashboards/operations_controller/daily_inventory_turnover.html', context)


@login_required
def monthly_max_inventory_detail(request):
    """
    Detailed breakdown of max inventory and space per project for the selected month
    """
    from datetime import datetime
    from calendar import monthrange

    # Get selected month from query params
    selected_month_str = request.GET.get('selected_month')
    today = date.today()

    if selected_month_str:
        try:
            selected_month_date = datetime.strptime(selected_month_str, '%Y-%m').date()
            selected_month_start = selected_month_date.replace(day=1)
            # Get last day of selected month
            if selected_month_start.month == 12:
                selected_month_end = selected_month_start.replace(year=selected_month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                selected_month_end = selected_month_start.replace(month=selected_month_start.month + 1, day=1) - timedelta(days=1)
        except (ValueError, TypeError):
            selected_month_start = today.replace(day=1)
            if selected_month_start.month == 12:
                selected_month_end = selected_month_start.replace(year=selected_month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                selected_month_end = selected_month_start.replace(month=selected_month_start.month + 1, day=1) - timedelta(days=1)
    else:
        selected_month_start = today.replace(day=1)
        if selected_month_start.month == 12:
            selected_month_end = selected_month_start.replace(year=selected_month_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            selected_month_end = selected_month_start.replace(month=selected_month_start.month + 1, day=1) - timedelta(days=1)

    # Filter by coordinator
    selected_coordinator = request.GET.get('coordinator', '')

    # Get all coordinators for dropdown
    all_coordinators = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period']
    ).exclude(
        operation_coordinator__isnull=True
    ).exclude(
        operation_coordinator=''
    ).values_list('operation_coordinator', flat=True).distinct().order_by('operation_coordinator')

    # Build project data with max values for the month
    projects_data = []
    total_max_inventory = Decimal('0')
    total_max_space = Decimal('0')

    projects_query = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Notice Period']
    )

    if selected_coordinator:
        projects_query = projects_query.filter(operation_coordinator=selected_coordinator)

    for project in projects_query.order_by('client_name'):
        # Get max inventory for this project in the month
        max_inventory_entry = DailySpaceUtilization.objects.filter(
            project=project,
            entry_date__gte=selected_month_start,
            entry_date__lte=selected_month_end
        ).aggregate(max_inv=Max('inventory_value'))['max_inv']

        # Get max space for this project in the month
        max_space_entry = DailySpaceUtilization.objects.filter(
            project=project,
            entry_date__gte=selected_month_start,
            entry_date__lte=selected_month_end
        ).aggregate(max_space=Max('space_utilized'))['max_space']

        # Get the entry with max inventory to find the date and unit
        if max_inventory_entry:
            max_inv_record = DailySpaceUtilization.objects.filter(
                project=project,
                entry_date__gte=selected_month_start,
                entry_date__lte=selected_month_end,
                inventory_value=max_inventory_entry
            ).select_related('unit').first()
        else:
            max_inv_record = None

        # Get the entry with max space to find the unit
        if max_space_entry:
            max_space_record = DailySpaceUtilization.objects.filter(
                project=project,
                entry_date__gte=selected_month_start,
                entry_date__lte=selected_month_end,
                space_utilized=max_space_entry
            ).select_related('unit').first()
        else:
            max_space_record = None

        # Calculate space in sqft
        space_in_sqft = Decimal('0')
        space_value = max_space_entry or Decimal('0')
        unit_name = 'N/A'

        if max_space_record:
            if max_space_record.unit_id == 'sqft':
                space_in_sqft = space_value
                unit_name = 'Sq. Ft.'
            elif max_space_record.unit_id == 'pallet':
                space_in_sqft = space_value * Decimal('25')
                unit_name = 'Pallet'
            else:
                unit_name = max_space_record.unit.label if max_space_record.unit else 'N/A'
        elif not max_space_entry:
            # Fallback to minimum_billable_area from ProjectCard
            try:
                project_card = ProjectCard.objects.filter(
                    project_id=project.project_id,
                    is_active=True
                ).first()
                if project_card:
                    storage_rate = project_card.storage_rates.filter(rate_for='client').first()
                    if storage_rate and storage_rate.minimum_billable_area:
                        space_in_sqft = storage_rate.minimum_billable_area
                        unit_name = 'Sq. Ft. (Min)'
            except Exception:
                pass

        inventory_value = max_inventory_entry or Decimal('0')

        # Only include projects with data
        if max_inventory_entry or max_space_entry or space_in_sqft > 0:
            projects_data.append({
                'project': project,
                'max_inventory': inventory_value,
                'max_inventory_crores': round(float(inventory_value) / 10000000, 2),
                'max_inventory_date': max_inv_record.entry_date if max_inv_record else None,
                'max_space': space_value,
                'max_space_sqft': space_in_sqft,
                'max_space_lakhs': round(float(space_in_sqft) / 100000, 2),
                'max_space_date': max_space_record.entry_date if max_space_record else None,
                'unit_name': unit_name,
            })

            total_max_inventory += inventory_value
            total_max_space += space_in_sqft

    # Convert totals
    total_max_inventory_crores = round(float(total_max_inventory) / 10000000, 2)
    total_max_space_lakhs = round(float(total_max_space) / 100000, 2)

    context = {
        'selected_month_start': selected_month_start,
        'selected_month_end': selected_month_end,
        'today': today,
        'projects_data': projects_data,
        'total_projects': len(projects_data),
        'total_max_inventory_crores': total_max_inventory_crores,
        'total_max_space_lakhs': total_max_space_lakhs,
        'all_coordinators': all_coordinators,
        'selected_coordinator': selected_coordinator,
    }

    return render(request, 'dashboards/operations_controller/monthly_max_inventory.html', context)
