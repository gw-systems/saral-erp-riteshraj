"""
Operation Manager Dashboard View
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Q, Avg, F
from django.db.models.functions import TruncMonth
from collections import defaultdict

from accounts.models import User
from projects.models import ProjectCode
from projects.models_client import ClientCard
from operations.models import DailySpaceUtilization, MonthlyBilling, DisputeLog
from operations.models_adhoc import AdhocBillingEntry
from operations.models_projectcard import ProjectCard
from supply.models import VendorCard


@login_required
def operation_manager_dashboard(request):
    """
    Operation Manager Dashboard
    Focused on operational metrics, project oversight, and team performance
    """
    # Role check
    if request.user.role not in ['operation_manager', 'operation_controller', 'admin', 'director']:
        messages.error(request, "Access denied. Operation Manager access required.")
        return redirect('accounts:dashboard')
    
    # Date context
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)
    
    # ==================== PROJECT METRICS (2 queries instead of 7) ====================

    # Project counts by status — single aggregate query
    _status_counts = {
        row['project_status']: row['cnt']
        for row in ProjectCode.objects.values('project_status').annotate(cnt=Count('project_id'))
    }
    active_projects = _status_counts.get('Active', 0)
    notice_period_projects = _status_counts.get('Notice Period', 0)
    not_started_projects = _status_counts.get('Operation Not Started', 0)
    inactive_projects = _status_counts.get('Inactive', 0)

    # Total projects = Active + Notice Period + Not Started (excluding Inactive)
    total_projects = active_projects + notice_period_projects + not_started_projects

    # Projects by series — single aggregate query
    _series_counts = {
        row['series_type']: row['cnt']
        for row in ProjectCode.objects.values('series_type').annotate(cnt=Count('project_id'))
    }
    waas_projects = _series_counts.get('WAAS', 0)
    saas_projects = _series_counts.get('SAAS', 0)
    gw_projects = _series_counts.get('GW', 0)

    # Manager's managed projects
    # Projects where this Operation Manager is assigned as coordinator
    manager_name = request.user.get_full_name()
    my_managed_projects = ProjectCode.objects.filter(
        Q(operation_coordinator=manager_name) | Q(backup_coordinator=manager_name),
        project_status='Active'
    ).count()

    # ==================== CLIENTS & VENDORS ====================

    # Total active clients (from ClientCard master data)
    total_clients = ClientCard.objects.filter(client_is_active=True).count()

    # Total active vendors (from VendorCard master data)
    total_vendors = VendorCard.objects.filter(vendor_is_active=True).count()

    # ==================== DISPUTES ====================

    # Open disputes
    open_disputes = DisputeLog.objects.filter(
        status__in=['open', 'in_progress']
    ).count()

    # ==================== DAILY ENTRIES ====================
    
    # Today's entries (all)
    entries_today = DailySpaceUtilization.objects.filter(
        entry_date=today
    ).values('project_id').distinct().count()

    # Manager's entries today (entered by this manager)
    my_entries_today = DailySpaceUtilization.objects.filter(
        entry_date=today,
        entered_by=request.user
    ).count()

    entries_pending_today = active_projects - entries_today
    
    completion_rate_today = round(
        (entries_today / active_projects * 100), 1
    ) if active_projects > 0 else 0
    
    # Monthly entries
    entries_this_month = DailySpaceUtilization.objects.filter(
        entry_date__gte=current_month_start,
        entry_date__lte=today
    ).count()
    
    # Calculate working days (excluding Sundays)
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
    
    # Entries by coordinator (3 batch queries instead of 3N)
    coordinators = User.objects.filter(role='operation_coordinator', is_active=True)
    _coord_names = {c.get_full_name(): c for c in coordinators}

    # Batch query 1: all active projects with coordinator assignments
    _coord_proj_rows = ProjectCode.objects.filter(
        Q(operation_coordinator__in=_coord_names.keys()) | Q(backup_coordinator__in=_coord_names.keys()),
        project_status='Active'
    ).values_list('project_id', 'operation_coordinator', 'backup_coordinator')

    _coord_proj_sets = defaultdict(set)
    _all_coord_pids = set()
    for pid, op_c, bk_c in _coord_proj_rows:
        _all_coord_pids.add(pid)
        if op_c in _coord_names:
            _coord_proj_sets[op_c].add(pid)
        if bk_c in _coord_names:
            _coord_proj_sets[bk_c].add(pid)

    # Batch query 2: entry counts per project this month
    _entry_counts_month = {}
    if _all_coord_pids:
        _entry_counts_month = dict(
            DailySpaceUtilization.objects.filter(
                project_id__in=_all_coord_pids,
                entry_date__gte=current_month_start,
            ).values('project_id').annotate(cnt=Count('id')).values_list('project_id', 'cnt')
        )

    coordinator_performance = []
    for coord_name, coord_user in _coord_names.items():
        pids = _coord_proj_sets.get(coord_name, set())
        project_count = len(pids)
        coord_entries = sum(_entry_counts_month.get(pid, 0) for pid in pids)
        expected_coord_entries = project_count * working_days
        coord_completion_rate = round(
            (coord_entries / expected_coord_entries * 100), 1
        ) if expected_coord_entries > 0 else 0

        coordinator_performance.append({
            'coordinator': coord_user,  # Add User object
            'name': coord_name,
            'initials': ''.join([n[0] for n in coord_name.split()[:2]]),
            'projects': project_count,
            'entries': coord_entries,
            'expected': expected_coord_entries,
            'completion_rate': coord_completion_rate
        })

    # Sort by completion rate
    coordinator_performance.sort(key=lambda x: x['completion_rate'], reverse=True)
    
    # ==================== ADHOC BILLING (1 query instead of 7) ====================

    _adhoc_agg = AdhocBillingEntry.objects.aggregate(
        pending_count=Count('id', filter=Q(status='pending')),
        approved_month=Count('id', filter=Q(status='approved', event_date__gte=current_month_start)),
        billed_month=Count('id', filter=Q(status='billed', event_date__gte=current_month_start)),
        pending_old=Count('id', filter=Q(status='pending', event_date__lt=today - timedelta(days=30))),
        pending_amount=Sum('total_client_amount', filter=Q(status='pending')),
        approved_amount=Sum('total_client_amount', filter=Q(status__in=['approved', 'billed'], event_date__gte=current_month_start)),
    )
    adhoc_pending = _adhoc_agg['pending_count']
    adhoc_approved_month = _adhoc_agg['approved_month']
    adhoc_billed_month = _adhoc_agg['billed_month']
    adhoc_pending_old = _adhoc_agg['pending_old']
    adhoc_pending_amount = float(_adhoc_agg['pending_amount'] or 0) / 100000  # Convert to lakhs
    adhoc_approved_amount = float(_adhoc_agg['approved_amount'] or 0) / 100000
    
    # ==================== MONTHLY BILLING (1 query instead of 9) ====================

    _billing_agg = MonthlyBilling.objects.filter(
        billing_month__gte=current_month_start
    ).aggregate(
        generated=Count('id', filter=Q(status='generated')),
        sent=Count('id', filter=Q(status='sent')),
        pending=Count('id', filter=Q(status='pending')),
        paid=Count('id', filter=Q(status='paid')),
        ctrl_approved=Count('id', filter=Q(controller_action='approved')),
        ctrl_rejected=Count('id', filter=Q(controller_action='rejected')),
        ctrl_pending=Count('id', filter=Q(controller_action='pending')),
        fin_approved=Count('id', filter=Q(finance_action='approved')),
        fin_rejected=Count('id', filter=Q(finance_action='rejected')),
        fin_pending=Count('id', filter=Q(finance_action='pending')),
    )
    billing_generated = _billing_agg['generated']
    billing_sent = _billing_agg['sent']
    billing_pending = _billing_agg['pending']
    billing_paid = _billing_agg['paid']
    controller_approved = _billing_agg['ctrl_approved']
    controller_rejected = _billing_agg['ctrl_rejected']
    controller_pending = _billing_agg['ctrl_pending']
    finance_approved = _billing_agg['fin_approved']
    finance_rejected = _billing_agg['fin_rejected']
    finance_pending = _billing_agg['fin_pending']

    # ==================== DATA QUALITY ====================
    
    # Projects without project_id
    projects_without_id = ProjectCode.objects.filter(
        Q(project_id__isnull=True) | Q(project_id='')
    ).count()
    
    # Projects without project cards (Active projects only)
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
    
    # ==================== ALERTS ====================
    
    total_alerts = (
        projects_without_id + 
        incomplete_project_cards + 
        adhoc_pending_old + 
        entries_pending_today +
        projects_without_coordinator
    )
    
    # ==================== TEAM PERFORMANCE - PROBLEM COORDINATORS ====================

    # Identify coordinators needing attention (low compliance)
    problem_coordinators = []
    for coord_data in coordinator_performance:
        if coord_data['completion_rate'] < 90 and coord_data['projects'] > 0:
            # Calculate missing entries
            missing_count = coord_data['expected'] - coord_data['entries']

            # Determine severity
            if coord_data['completion_rate'] < 70:
                status = 'critical'
            else:
                status = 'warning'

            problem_coordinators.append({
                'coordinator': coord_data['coordinator'],  # Use the coordinator object from the list
                'compliance': coord_data['completion_rate'],
                'missing_count': missing_count,
                'total_projects': coord_data['projects'],
                'status': status
            })

    # Sort by compliance (lowest first)
    problem_coordinators.sort(key=lambda x: x['compliance'])

    # Flag to show performance section
    show_performance = len(coordinators) > 0

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
    
    # Top clients by project count
    top_clients = ProjectCode.objects.filter(
        project_status__in=['Active', 'Operation Not Started']
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
    
    # ==================== RECENT PROJECTS ====================

    recent_projects = ProjectCode.objects.order_by('-created_at')[:5]

    # ==================== RECENT DISPUTES ====================

    recent_disputes = DisputeLog.objects.filter(
        status__in=['open', 'in_progress']
    ).order_by('-created_at')[:5]

    # ==================== RECENT ADHOC BILLINGS ====================

    recent_adhoc_billings = AdhocBillingEntry.objects.filter(
        status='pending'
    ).select_related('project', 'created_by').order_by('-created_at')[:5]

    # ==================== WEEKLY CALENDAR DATA (3 queries instead of 21) ====================

    # Find the Monday of current week
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)
    _week_cutoff = min(today, week_end)

    # Pre-fetch all 7 days of data in 3 batch queries
    _week_entries = dict(
        DailySpaceUtilization.objects.filter(
            entry_date__gte=week_start, entry_date__lte=_week_cutoff,
        ).values('entry_date').annotate(cnt=Count('project_id', distinct=True)).values_list('entry_date', 'cnt')
    )
    _week_disputes = dict(
        DisputeLog.objects.filter(
            created_at__date__gte=week_start, created_at__date__lte=_week_cutoff,
        ).values('created_at__date').annotate(cnt=Count('dispute_id')).values_list('created_at__date', 'cnt')
    )
    _week_adhoc = dict(
        AdhocBillingEntry.objects.filter(
            event_date__gte=week_start, event_date__lte=_week_cutoff,
        ).values('event_date').annotate(cnt=Count('id')).values_list('event_date', 'cnt')
    )

    week_data = []
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        is_today = day_date == today
        is_future = day_date > today
        is_sunday = day_date.weekday() == 6

        # Initialize day data
        day_info = {
            'date': day_date,
            'day': day_date.day,
            'is_today': is_today,
            'is_future': is_future,
            'is_sunday': is_sunday,
            'is_holiday': False,  # Can be enhanced with holiday checking
        }

        # Only calculate metrics for past days and today
        if not is_future:
            day_entries = _week_entries.get(day_date, 0)
            day_expected = 0 if is_sunday else active_projects
            day_compliance = round(
                (day_entries / day_expected * 100), 1
            ) if day_expected > 0 else 100  # 100% for Sundays/holidays

            # Determine color based on compliance
            if day_compliance >= 90:
                color = 'green'
            elif day_compliance >= 70:
                color = 'yellow'
            else:
                color = 'red'

            day_info.update({
                'entries': day_entries,
                'expected': day_expected,
                'compliance': day_compliance,
                'disputes_count': _week_disputes.get(day_date, 0),
                'adhoc_count': _week_adhoc.get(day_date, 0),
                'color': color,
            })

        week_data.append(day_info)

    # ==================== CONTEXT ====================
    
    context = {
        # Date
        'today': today,
        'current_time': timezone.now().strftime('%I:%M %p'),
        
        # Projects
        'total_projects': total_projects,
        'active_projects': active_projects,
        'notice_period_projects': notice_period_projects,
        'not_started_projects': not_started_projects,
        'inactive_projects': inactive_projects,
        'waas_projects': waas_projects,
        'saas_projects': saas_projects,
        'gw_projects': gw_projects,
        'my_managed_projects': my_managed_projects,

        # Clients & Vendors
        'total_clients': total_clients,
        'total_vendors': total_vendors,

        # Disputes
        'open_disputes': open_disputes,

        # Daily Entries
        'entries_today': entries_today,
        'my_entries_today': my_entries_today,
        'entries_pending_today': entries_pending_today,
        'completion_rate_today': completion_rate_today,
        'entries_this_month': entries_this_month,
        'working_days': working_days,
        'expected_entries_month': expected_entries_month,
        'monthly_completion_rate': monthly_completion_rate,
        'coordinator_performance': coordinator_performance,
        
        # Adhoc Billing
        'adhoc_pending': adhoc_pending,
        'adhoc_approved_month': adhoc_approved_month,
        'adhoc_billed_month': adhoc_billed_month,
        'adhoc_pending_old': adhoc_pending_old,
        'adhoc_pending_amount': adhoc_pending_amount,
        'adhoc_approved_amount': adhoc_approved_amount,
        
        # Monthly Billing
        'billing_generated': billing_generated,
        'billing_sent': billing_sent,
        'billing_pending': billing_pending,
        'billing_paid': billing_paid,
        'controller_approved': controller_approved,
        'controller_rejected': controller_rejected,
        'controller_pending': controller_pending,
        'finance_approved': finance_approved,
        'finance_rejected': finance_rejected,
        'finance_pending': finance_pending,

        # Data Quality
        'projects_without_id': projects_without_id,
        'incomplete_project_cards': incomplete_project_cards,
        'projects_without_coordinator': projects_without_coordinator,
        
        # Alerts
        'total_alerts': total_alerts,
        
        # Top Lists
        'top_states': top_states_list,
        'top_clients': top_clients_list,
        
        # Recent
        'recent_projects': recent_projects,
        'recent_disputes': recent_disputes,
        'recent_adhoc_billings': recent_adhoc_billings,

        # Calendar
        'week_data': week_data,

        # Team Performance
        'problem_coordinators': problem_coordinators,
        'show_performance': show_performance,
    }

    return render(request, 'dashboards/operation_manager_dashboard.html', context)