"""
Admin Dashboard View
Comprehensive dashboard with full system oversight for admin role only
"""

import json
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from collections import defaultdict
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncMonth

logger = logging.getLogger(__name__)

from accounts.models import User
from projects.models import ProjectCode
from projects.models_client import ClientCard
from projects.models_document import ProjectDocument
from operations.models import DailySpaceUtilization, MonthlyBilling
from operations.models_adhoc import AdhocBillingEntry
from operations.models_projectcard import ProjectCard


@login_required
def admin_dashboard(request):
    """
    Redirect to new modular admin dashboard
    Old monolithic dashboard has been replaced with 8 hub pages
    """
    # Check permissions
    if request.user.role not in ['admin', 'director']:
        messages.error(request, "Access denied. Admin or Director access required.")
        return redirect('accounts:dashboard')

    # Redirect to new home page
    return redirect('accounts:admin_dashboard_home')

    # OLD CODE BELOW - Kept for reference but not executed due to redirect above
    # ============================================================================

    # Get current date context
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)
    current_year_start = today.replace(month=1, day=1)
    thirty_days_ago = today - timedelta(days=30)
    
    # ==================== CRITICAL ALERTS ====================
    
    # Projects without project_id
    projects_without_id = ProjectCode.objects.filter(
        Q(project_id__isnull=True) | Q(project_id='')
    ).count()
    
    # Projects without project cards (Active only)
    active_projects = ProjectCode.objects.filter(project_status='Active')
    projects_with_cards = ProjectCard.objects.filter(
        project__project_status='Active'
    ).values_list('project_id', flat=True).distinct()
    
    incomplete_project_cards = active_projects.exclude(
        project_id__in=projects_with_cards
    ).count()
    
    # Disputes open > 7 days (if DisputeLog exists)
    try:
        from operations.models import DisputeLog
        disputes_open_7days = DisputeLog.objects.filter(
            status__in=['open', 'in_progress'],
            opened_at__lt=timezone.now() - timedelta(days=7)
        ).count()
    except:
        disputes_open_7days = 0
    
    # Adhoc billing pending > 30 days
    adhoc_pending_30days = AdhocBillingEntry.objects.filter(
        status='pending',
        event_date__lt=today - timedelta(days=30)
    ).count()
    
    # Missing daily entries today
    try:
        active_projects_today = ProjectCode.objects.filter(project_status='Active').count()
        entries_today_count = DailySpaceUtilization.objects.filter(
            entry_date=today
        ).values('project_id').distinct().count()
        missing_daily_entries = max(0, active_projects_today - entries_today_count)
    except:
        missing_daily_entries = 0
    
    total_critical_alerts = (
        projects_without_id + 
        incomplete_project_cards + 
        disputes_open_7days + 
        adhoc_pending_30days +
        missing_daily_entries
    )
    
    # ==================== KPI CARDS ====================

    # All ProjectCode counts in 1 query (was 12+ separate .count() calls)
    _pc = ProjectCode.objects.aggregate(
        total_projects=Count('project_id'),
        active_projects_count=Count('project_id', filter=Q(project_status='Active')),
        notice_period_projects=Count('project_id', filter=Q(project_status='Notice Period')),
        not_started_projects=Count('project_id', filter=Q(project_status='Operation Not Started')),
        inactive_projects=Count('project_id', filter=Q(project_status='Inactive')),
        projects_added_this_month=Count('project_id', filter=Q(created_at__gte=current_month_start)),
        projects_last_month=Count('project_id', filter=Q(created_at__gte=last_month_start, created_at__lte=last_month_end)),
        waas_projects=Count('project_id', filter=Q(series_type='WAAS')),
        saas_projects=Count('project_id', filter=Q(series_type='SAAS')),
        gw_projects=Count('project_id', filter=Q(series_type='GW')),
        projects_with_id=Count('project_id', filter=Q(project_id__isnull=False) & ~Q(project_id='')),
        projects_missing_coordinator=Count('project_id', filter=Q(operation_coordinator__isnull=True, project_status='Active')),
    )
    total_projects = _pc['total_projects']
    active_projects_count = _pc['active_projects_count']
    notice_period_projects = _pc['notice_period_projects']
    not_started_projects = _pc['not_started_projects']
    inactive_projects = _pc['inactive_projects']
    projects_added_this_month = _pc['projects_added_this_month']
    projects_last_month = _pc['projects_last_month']
    waas_projects = _pc['waas_projects']
    saas_projects = _pc['saas_projects']
    gw_projects = _pc['gw_projects']
    projects_with_id = _pc['projects_with_id']
    projects_missing_coordinator = _pc['projects_missing_coordinator']

    # ProjectCard counts in 1 query (was 2 separate .count() calls)
    _card = ProjectCard.objects.aggregate(
        total_project_cards=Count('id'),
        complete_cards=Count('id', filter=Q(
            agreement_start_date__isnull=False,
            agreement_end_date__isnull=False,
            billing_start_date__isnull=False,
        ))
    )
    total_project_cards = _card['total_project_cards']
    complete_cards = _card['complete_cards']

    if projects_last_month > 0:
        projects_growth_percentage = round(
            ((projects_added_this_month - projects_last_month) / projects_last_month) * 100,
            1
        )
    else:
        projects_growth_percentage = 0

    active_percentage = round((active_projects_count / total_projects * 100), 1) if total_projects > 0 else 0

    # All User counts in 1 query (was 3 separate .count() calls)
    _u = User.objects.aggregate(
        total_users=Count('id'),
        active_users=Count('id', filter=Q(is_active=True)),
        users_logged_in_today=Count('id', filter=Q(last_login__date=today)),
    )
    total_users = _u['total_users']
    active_users = _u['active_users']
    inactive_users = total_users - active_users
    users_logged_in_today = _u['users_logged_in_today']
    
    # Monthly Revenue (from Adhoc Billing - since MonthlyBilling under development)
    monthly_revenue_data = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start,
        event_date__lte=today,
        status__in=['billed', 'approved']
    ).aggregate(
        total=Sum('total_client_amount')
    )
    
    monthly_revenue = float(monthly_revenue_data['total'] or 0) / 100000  # Convert to lakhs
    
    # Last month revenue
    last_month_revenue_data = AdhocBillingEntry.objects.filter(
        event_date__gte=last_month_start,
        event_date__lte=last_month_end,
        status__in=['billed', 'approved']
    ).aggregate(
        total=Sum('total_client_amount')
    )
    
    last_month_revenue = float(last_month_revenue_data['total'] or 0) / 100000
    
    if last_month_revenue > 0:
        revenue_growth = round(
            ((monthly_revenue - last_month_revenue) / last_month_revenue) * 100, 
            1
        )
    else:
        revenue_growth = 0
    
    # ==================== OVERVIEW TAB DATA ====================
    
    # Status percentages
    active_projects_percentage = round((active_projects_count / total_projects * 100), 1) if total_projects > 0 else 0
    not_started_projects_percentage = round((not_started_projects / total_projects * 100), 1) if total_projects > 0 else 0
    notice_period_projects_percentage = round((notice_period_projects / total_projects * 100), 1) if total_projects > 0 else 0
    inactive_projects_percentage = round((inactive_projects / total_projects * 100), 1) if total_projects > 0 else 0
    
    # Series Distribution
    waas_percentage = round((waas_projects / total_projects * 100), 1) if total_projects > 0 else 0
    saas_percentage = round((saas_projects / total_projects * 100), 1) if total_projects > 0 else 0
    gw_percentage = round((gw_projects / total_projects * 100), 1) if total_projects > 0 else 0

    # Data Quality Score
    projects_with_id_percentage = round((projects_with_id / total_projects * 100), 1) if total_projects > 0 else 0
    complete_cards_percentage = round((complete_cards / total_project_cards * 100), 1) if total_project_cards > 0 else 0

    data_quality_score = round((projects_with_id_percentage + complete_cards_percentage) / 2, 1)

    data_issues_count = projects_without_id + incomplete_project_cards + projects_missing_coordinator
    
    # Monthly Trends (Last 6 Months) — 1 batch query instead of 6
    _six_months_ago = (today - timedelta(days=5*30)).replace(day=1)
    _monthly_counts = dict(
        ProjectCode.objects.filter(
            created_at__gte=_six_months_ago
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            cnt=Count('project_id')
        ).values_list('month', 'cnt')
    )

    monthly_trends = []
    for i in range(5, -1, -1):
        month_date = (today - timedelta(days=i*30)).replace(day=1)
        projects_count = _monthly_counts.get(
            timezone.make_aware(timezone.datetime(month_date.year, month_date.month, 1)),
            0
        )
        # Also check naive datetime key (depends on DB backend)
        if projects_count == 0:
            from datetime import datetime as _dt
            projects_count = _monthly_counts.get(
                _dt(month_date.year, month_date.month, 1), 0
            )

        max_count = 50
        height_percentage = min((projects_count / max_count * 100), 100) if max_count > 0 else 0

        monthly_trends.append({
            'month_short': month_date.strftime('%b'),
            'value': projects_count,
            'percentage': height_percentage,
            'label': month_date.strftime('%B %Y')
        })
    
    # Live Metrics
    today_activity_count = projects_added_this_month
    pending_actions_count = adhoc_pending_30days + disputes_open_7days
    users_online_now = User.objects.filter(
        last_login__gte=timezone.now() - timedelta(minutes=15)
    ).count()
    
    # ==================== PROJECTS TAB DATA ====================
    
    # All States for filter
    all_states = ProjectCode.objects.values('state').distinct().order_by('state')
    
    # Top States by Active Projects
    top_states = ProjectCode.objects.filter(
        project_status='Active',
        state__isnull=False
    ).values('state').annotate(
        count=Count('project_id')
    ).order_by('-count')[:5]
    
    max_state_count = top_states[0]['count'] if top_states else 1
    
    top_states_data = []
    for state in top_states:
        top_states_data.append({
            'name': state['state'],
            'code': state['state'][:2].upper(),
            'count': state['count'],
            'percentage': round((state['count'] / max_state_count * 100), 1)
        })
    
    # Top Clients by Project Count
    top_clients_by_projects = ProjectCode.objects.filter(
        project_status__in=['Active', 'Operation Not Started']
    ).values('client_name').annotate(
        active_projects=Count('project_id', filter=Q(project_status='Active')),
        total_projects=Count('project_id')
    ).order_by('-active_projects')[:10]
    
    top_clients_list = []
    for idx, client in enumerate(top_clients_by_projects, 1):
        top_clients_list.append({
            'rank': idx,
            'name': client['client_name'],
            'active_projects': client['active_projects'],
            'total_projects': client['total_projects']
        })
    
    # ==================== OPERATIONS TAB DATA ====================
    
    # Daily Entries Status
    try:
        daily_entries_today = DailySpaceUtilization.objects.filter(
            entry_date=today
        ).values('project_id').distinct().count()
        
        daily_entries_pending = active_projects_count - daily_entries_today
        
        daily_entries_this_month = DailySpaceUtilization.objects.filter(
            entry_date__gte=current_month_start,
            entry_date__lte=today
        ).count()
        
        # Calculate working days in month
        working_days = 0
        current_date = current_month_start
        while current_date <= today:
            if current_date.weekday() != 6:  # Not Sunday
                working_days += 1
            current_date += timedelta(days=1)
        
        expected_entries = active_projects_count * working_days
        daily_entries_completion_rate = round(
            (daily_entries_this_month / expected_entries * 100), 1
        ) if expected_entries > 0 else 0
        
        daily_entries_days_in_month = working_days
        daily_entries_avg_per_day = round(daily_entries_this_month / working_days, 1) if working_days > 0 else 0
        expected_daily_entries = active_projects_count
        
        # Daily entries completion rate today
        daily_entries_completion_rate_today = round(
            (daily_entries_today / active_projects_count * 100), 1
        ) if active_projects_count > 0 else 0
        
    except:
        daily_entries_today = 0
        daily_entries_pending = 0
        daily_entries_this_month = 0
        daily_entries_completion_rate = 0
        daily_entries_days_in_month = 0
        daily_entries_avg_per_day = 0
        expected_daily_entries = 0
        daily_entries_completion_rate_today = 0
    
    # Top Coordinators by Entries — 3 batch queries instead of N+1
    try:
        coordinators = User.objects.filter(
            role='operation_coordinator',
            is_active=True
        )[:5]
        _admin_coord_names = {c.get_full_name(): c for c in coordinators}

        # Batch 1: All projects for these coordinators
        _admin_coord_proj_rows = ProjectCode.objects.filter(
            Q(operation_coordinator__in=_admin_coord_names.keys()) | Q(backup_coordinator__in=_admin_coord_names.keys()),
            project_status='Active'
        ).values_list('project_id', 'operation_coordinator', 'backup_coordinator')

        _admin_coord_proj_sets = defaultdict(set)
        _admin_all_pids = set()
        for pid, op_c, bk_c in _admin_coord_proj_rows:
            _admin_all_pids.add(pid)
            if op_c in _admin_coord_names:
                _admin_coord_proj_sets[op_c].add(pid)
            if bk_c in _admin_coord_names:
                _admin_coord_proj_sets[bk_c].add(pid)

        # Batch 2: Entry counts per project this month
        _admin_entry_counts = dict(
            DailySpaceUtilization.objects.filter(
                project_id__in=_admin_all_pids,
                entry_date__gte=current_month_start
            ).values('project_id').annotate(cnt=Count('id')).values_list('project_id', 'cnt')
        )

        top_coordinators_entries = []
        for name in _admin_coord_names:
            proj_set = _admin_coord_proj_sets.get(name, set())
            proj_count = len(proj_set)
            coord_entries = sum(_admin_entry_counts.get(pid, 0) for pid in proj_set)
            expected = proj_count * working_days
            completion_rate = round((coord_entries / expected * 100), 1) if expected > 0 else 0

            top_coordinators_entries.append({
                'name': name,
                'initials': ''.join([n[0] for n in name.split()[:2]]),
                'projects': proj_count,
                'entries': coord_entries,
                'completion_rate': completion_rate
            })
    except:
        top_coordinators_entries = []
    
    # Adhoc Billing
    adhoc_pending = AdhocBillingEntry.objects.filter(status='pending').count()
    adhoc_approved_month = AdhocBillingEntry.objects.filter(
        status__in=['approved', 'billed'],
        event_date__gte=current_month_start
    ).count()
    
    adhoc_pending_amount = AdhocBillingEntry.objects.filter(
        status='pending'
    ).aggregate(total=Sum('total_client_amount'))['total'] or 0
    adhoc_pending_amount = float(adhoc_pending_amount) / 100000
    
    adhoc_approved_amount_month = AdhocBillingEntry.objects.filter(
        status__in=['approved', 'billed'],
        event_date__gte=current_month_start
    ).aggregate(total=Sum('total_client_amount'))['total'] or 0
    adhoc_approved_amount_month = float(adhoc_approved_amount_month) / 100000
    
    adhoc_total_amount = adhoc_pending_amount + adhoc_approved_amount_month
    
    # Adhoc average approval days
    approved_adhoc = AdhocBillingEntry.objects.filter(
        status__in=['approved', 'billed'],
        created_at__isnull=False,
        updated_at__isnull=False
    )
    
    if approved_adhoc.exists():
        total_days = sum([
            (entry.updated_at.date() - entry.created_at.date()).days 
            for entry in approved_adhoc 
            if entry.created_at and entry.updated_at
        ])
        adhoc_avg_approval_days = round(total_days / approved_adhoc.count(), 1)
    else:
        adhoc_avg_approval_days = 0
    
    # Oldest pending adhoc
    oldest_pending = AdhocBillingEntry.objects.filter(
        status='pending'
    ).order_by('event_date').first()
    
    if oldest_pending:
        adhoc_oldest_pending_days = (today - oldest_pending.event_date).days
    else:
        adhoc_oldest_pending_days = 0
    
    # Disputes
    try:
        disputes_open = DisputeLog.objects.filter(
            status__in=['open', 'in_progress']
        ).count()
        
        disputes_open_amount = 0  # Calculate if amount field exists
        
        disputes_resolved_month = DisputeLog.objects.filter(
            status='resolved',
            resolved_at__gte=current_month_start
        ).count()
        
        disputes_resolved_amount_month = 0
        
        disputes_overdue_percentage = round(
            (disputes_open_7days / disputes_open * 100), 1
        ) if disputes_open > 0 else 0
        
        # Average resolution days
        resolved_disputes = DisputeLog.objects.filter(
            status='resolved',
            resolved_at__gte=thirty_days_ago,
            opened_at__isnull=False,
            resolved_at__isnull=False
        )
        
        if resolved_disputes.exists():
            total_resolution_days = sum([
                (dispute.resolved_at.date() - dispute.opened_at.date()).days
                for dispute in resolved_disputes
            ])
            disputes_avg_resolution_days = round(total_resolution_days / resolved_disputes.count(), 1)
        else:
            disputes_avg_resolution_days = 0
        
        disputes_resolution_rate = round(
            (disputes_resolved_month / (disputes_resolved_month + disputes_open) * 100), 1
        ) if (disputes_resolved_month + disputes_open) > 0 else 0
        
    except:
        disputes_open = 0
        disputes_open_amount = 0
        disputes_resolved_month = 0
        disputes_resolved_amount_month = 0
        disputes_overdue_percentage = 0
        disputes_avg_resolution_days = 0
        disputes_resolution_rate = 0
    
    # Monthly Billing (placeholder - under development)
    monthly_billing_generated = 0
    monthly_billing_sent = 0
    monthly_billing_pending = 0
    monthly_billing_amount = 0
    monthly_billing_generated_amount = 0
    monthly_billing_sent_amount = 0
    monthly_billing_pending_amount = 0
    monthly_billing_paid = 0
    billing_step = 1
    
    # Recent Escalations (placeholder)
    recent_escalations = []
    
    # ==================== TEAM TAB DATA ====================
    
    # Users by Role
    users_by_role = User.objects.values('role').annotate(
        count=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
        inactive=Count('id', filter=Q(is_active=False))
    ).order_by('-count')
    
    users_by_role_list = []
    for role_data in users_by_role:
        role_display = dict(User.ROLE_CHOICES).get(role_data['role'], role_data['role'])
        users_by_role_list.append({
            'role': role_data['role'],
            'role_display': role_display,
            'count': role_data['count'],
            'active': role_data['active'],
            'inactive': role_data['inactive']
        })
    
    # Coordinator Workload
    coordinator_workload = []
    coordinators = User.objects.filter(role='operation_coordinator', is_active=True)
    
    for coord in coordinators[:10]:
        coord_name = coord.get_full_name()
        projects_count = ProjectCode.objects.filter(
            Q(operation_coordinator=coord_name) | Q(backup_coordinator=coord_name),
            project_status='Active'
        ).count()
        
        max_projects = 20  # Assumed max capacity
        percentage = round((projects_count / max_projects * 100), 1) if max_projects > 0 else 0
        
        coordinator_workload.append({
            'name': coord_name,
            'initials': ''.join([n[0] for n in coord_name.split()[:2]]),
            'role_display': 'Operation Coordinator',
            'projects': projects_count,
            'percentage': min(percentage, 100)
        })
    
    # Team Performance
    ontime_billing_rate = 95.0  # Placeholder
    dispute_resolution_time = disputes_avg_resolution_days
    avg_response_time = 2.5  # Placeholder hours
    
    # Team Leaderboard (placeholder)
    team_leaderboard = []
    
    # Password Expiry Alerts (placeholder)
    expiring_passwords = []
    
    # ==================== FINANCIAL TAB DATA ====================
    
    # Quarterly Revenue
    quarter_start = today.replace(month=((today.month-1)//3)*3+1, day=1)
    quarterly_revenue_data = AdhocBillingEntry.objects.filter(
        event_date__gte=quarter_start,
        event_date__lte=today,
        status__in=['billed', 'approved']
    ).aggregate(total=Sum('total_client_amount'))
    
    quarterly_revenue = float(quarterly_revenue_data['total'] or 0) / 100000
    quarterly_growth = 0  # Calculate vs last quarter if needed
    
    # Gross Margin (placeholder - needs cost data)
    gross_margin = 25.0
    
    # Pending Payments
    pending_payments = adhoc_pending_amount
    
    # Revenue by Series
    revenue_by_series = []
    for series in ['WAAS', 'SAAS', 'GW']:
        series_projects = ProjectCode.objects.filter(series_type=series)
        series_revenue_data = AdhocBillingEntry.objects.filter(
            project__in=series_projects,
            event_date__gte=current_month_start,
            status__in=['billed', 'approved']
        ).aggregate(total=Sum('total_client_amount'))
        
        series_amount = float(series_revenue_data['total'] or 0) / 100000
        series_percentage = round((series_amount / monthly_revenue * 100), 1) if monthly_revenue > 0 else 0
        
        revenue_by_series.append({
            'series': series,
            'amount': series_amount,
            'projects': series_projects.filter(project_status='Active').count(),
            'percentage': series_percentage
        })
    
    # Top Clients by Revenue
    top_clients_revenue = []
    client_revenue_data = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start,
        status__in=['billed', 'approved']
    ).values('project__client_name').annotate(
        revenue=Sum('total_client_amount'),
        projects=Count('project_id', distinct=True)
    ).order_by('-revenue')[:10]
    
    total_revenue_for_percentage = sum([float(c['revenue']) for c in client_revenue_data])
    
    for idx, client in enumerate(client_revenue_data, 1):
        amount = float(client['revenue']) / 100000
        percentage = round((float(client['revenue']) / total_revenue_for_percentage * 100), 1) if total_revenue_for_percentage > 0 else 0
        
        top_clients_revenue.append({
            'rank': idx,
            'id': idx,
            'name': client['project__client_name'],
            'revenue': amount,
            'projects': client['projects'],
            'percentage': percentage
        })
    
    # Top States by Revenue (placeholder)
    top_states_revenue = []
    
    # Revenue Trend (Last 12 Months)
    revenue_trend_12months = []
    for i in range(11, -1, -1):
        month_date = (today - timedelta(days=i*30)).replace(day=1)
        month_end = (month_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        
        month_revenue_data = AdhocBillingEntry.objects.filter(
            event_date__gte=month_date,
            event_date__lte=month_end,
            status__in=['billed', 'approved']
        ).aggregate(total=Sum('total_client_amount'))
        
        month_amount = float(month_revenue_data['total'] or 0) / 100000
        
        revenue_trend_12months.append({
            'month_short': month_date.strftime('%b'),
            'year_short': month_date.strftime('%y'),
            'amount': month_amount,
            'height_percentage': min((month_amount / 100 * 100), 100) if month_amount > 0 else 5
        })
    
    # Payment Collection Status
    payments_collected = monthly_revenue  # Simplified
    payments_pending_30 = adhoc_pending_amount
    payments_overdue = 0  # Calculate based on invoice due dates if available
    payments_collected_percentage = 60  # Placeholder
    payments_pending_30_count = adhoc_pending
    payments_overdue_count = 0
    
    # Top Overdue Invoices (placeholder)
    top_overdue_invoices = []
    
    # ==================== SYSTEM TAB DATA ====================
    
    # Database Size (placeholder - requires DB query)
    database_size_mb = 450
    database_tables = 35
    db_growth_rate = 5.2
    
    # Background Jobs (placeholder)
    background_jobs_running = 2
    background_jobs_queued = 5
    
    # API Health (placeholder)
    api_uptime = 99.8
    api_response_time = 145
    
    # Last Backup
    last_backup_time = "2 hours ago"
    backup_status = "Success"
    last_backup_size = "125 MB"
    
    # Recent System Errors (placeholder)
    recent_errors = []
    
    # Data Integrity
    orphaned_records = 0
    duplicate_records = 0
    missing_required_fields = incomplete_project_cards
    invalid_data_formats = 0
    
    # ==================== CONTEXT ====================
    
    context = {
        # Date context
        'current_time': timezone.now().strftime('%I:%M %p'),
        'today': today,
        
        # Critical Alerts
        'total_critical_alerts': total_critical_alerts,
        'projects_without_id': projects_without_id,
        'incomplete_project_cards': incomplete_project_cards,
        'disputes_open_7days': disputes_open_7days,
        'adhoc_pending_30days': adhoc_pending_30days,
        'missing_daily_entries': missing_daily_entries,
        
        # KPI Cards
        'total_projects': total_projects,
        'projects_added_this_month': projects_added_this_month,
        'projects_growth_percentage': projects_growth_percentage,
        'active_projects': active_projects_count,
        'active_percentage': active_percentage,
        'notice_period_projects': notice_period_projects,
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'users_logged_in_today': users_logged_in_today,
        'monthly_revenue': monthly_revenue,
        'revenue_growth': revenue_growth,
        
        # Overview Tab
        'active_projects_percentage': active_projects_percentage,
        'not_started_projects': not_started_projects,
        'not_started_projects_percentage': not_started_projects_percentage,
        'notice_period_projects_percentage': notice_period_projects_percentage,
        'inactive_projects': inactive_projects,
        'inactive_projects_percentage': inactive_projects_percentage,
        'waas_projects': waas_projects,
        'saas_projects': saas_projects,
        'gw_projects': gw_projects,
        'waas_percentage': waas_percentage,
        'saas_percentage': saas_percentage,
        'gw_percentage': gw_percentage,
        'data_quality_score': data_quality_score,
        'projects_with_id': projects_with_id,
        'complete_cards': complete_cards,
        'total_project_cards': total_project_cards,
        'projects_with_id_percentage': projects_with_id_percentage,
        'complete_cards_percentage': complete_cards_percentage,
        'data_issues_count': data_issues_count,
        'monthly_trends': monthly_trends,
        'today_activity_count': today_activity_count,
        'pending_actions_count': pending_actions_count,
        'users_online_now': users_online_now,
        
        # Projects Tab
        'all_states': all_states,
        'top_states': top_states_data,
        'top_clients_by_projects': top_clients_list,
        'projects_missing_coordinator': projects_missing_coordinator,
        
        # Operations Tab
        'daily_entries_today': daily_entries_today,
        'daily_entries_pending': daily_entries_pending,
        'daily_entries_this_month': daily_entries_this_month,
        'daily_entries_completion_rate': daily_entries_completion_rate,
        'daily_entries_completion_rate_today': daily_entries_completion_rate_today,
        'daily_entries_days_in_month': daily_entries_days_in_month,
        'daily_entries_avg_per_day': daily_entries_avg_per_day,
        'expected_daily_entries': expected_daily_entries,
        'top_coordinators_entries': top_coordinators_entries,
        'adhoc_pending': adhoc_pending,
        'adhoc_approved_month': adhoc_approved_month,
        'adhoc_pending_amount': adhoc_pending_amount,
        'adhoc_approved_amount_month': adhoc_approved_amount_month,
        'adhoc_total_amount': adhoc_total_amount,
        'adhoc_avg_approval_days': adhoc_avg_approval_days,
        'adhoc_oldest_pending_days': adhoc_oldest_pending_days,
        'disputes_open': disputes_open,
        'disputes_open_amount': disputes_open_amount,
        'disputes_resolved_month': disputes_resolved_month,
        'disputes_resolved_amount_month': disputes_resolved_amount_month,
        'disputes_overdue_percentage': disputes_overdue_percentage,
        'disputes_avg_resolution_days': disputes_avg_resolution_days,
        'disputes_resolution_rate': disputes_resolution_rate,
        'monthly_billing_generated': monthly_billing_generated,
        'monthly_billing_sent': monthly_billing_sent,
        'monthly_billing_pending': monthly_billing_pending,
        'monthly_billing_amount': monthly_billing_amount,
        'monthly_billing_generated_amount': monthly_billing_generated_amount,
        'monthly_billing_sent_amount': monthly_billing_sent_amount,
        'monthly_billing_pending_amount': monthly_billing_pending_amount,
        'monthly_billing_paid': monthly_billing_paid,
        'billing_step': billing_step,
        'recent_escalations': recent_escalations,
        
        # Team Tab
        'users_by_role': users_by_role_list,
        'coordinator_workload': coordinator_workload,
        'ontime_billing_rate': ontime_billing_rate,
        'dispute_resolution_time': dispute_resolution_time,
        'avg_response_time': avg_response_time,
        'team_leaderboard': team_leaderboard,
        'expiring_passwords': expiring_passwords,
        
        # Financial Tab
        'quarterly_revenue': quarterly_revenue,
        'quarterly_growth': quarterly_growth,
        'gross_margin': gross_margin,
        'pending_payments': pending_payments,
        'revenue_by_series': revenue_by_series,
        'top_clients_revenue': top_clients_revenue,
        'top_states_revenue': top_states_revenue,
        'revenue_trend_12months': revenue_trend_12months,
        'payments_collected': payments_collected,
        'payments_pending_30': payments_pending_30,
        'payments_overdue': payments_overdue,
        'payments_collected_percentage': payments_collected_percentage,
        'payments_pending_30_count': payments_pending_30_count,
        'payments_overdue_count': payments_overdue_count,
        'top_overdue_invoices': top_overdue_invoices,
        
        # System Tab
        'database_size_mb': database_size_mb,
        'database_tables': database_tables,
        'db_growth_rate': db_growth_rate,
        'background_jobs_running': background_jobs_running,
        'background_jobs_queued': background_jobs_queued,
        'api_uptime': api_uptime,
        'api_response_time': api_response_time,
        'last_backup_time': last_backup_time,
        'backup_status': backup_status,
        'last_backup_size': last_backup_size,
        'recent_errors': recent_errors,
        'orphaned_records': orphaned_records,
        'duplicate_records': duplicate_records,
        'missing_required_fields': missing_required_fields,
        'invalid_data_formats': invalid_data_formats,
        
        # Activity
        'recent_activities': [],  # Placeholder
    }

    return render(request, 'dashboards/admin_dashboard.html', context)


# ==================== NEW MODULAR DASHBOARD VIEWS ====================

@login_required
def admin_dashboard_home(request):
    """
    Admin Dashboard Home/Overview Page
    Landing page with KPIs and quick navigation
    """
    if request.user.role not in ['admin', 'director']:
        messages.error(request, "Access denied. Admin or Director access required.")
        return redirect('accounts:dashboard')

    today = timezone.now().date()
    current_month_start = today.replace(day=1)

    # Critical Alerts
    projects_without_id = ProjectCode.objects.filter(
        Q(project_id__isnull=True) | Q(project_id='')
    ).count()

    active_projects = ProjectCode.objects.filter(project_status='Active')
    projects_with_cards = ProjectCard.objects.filter(
        project__project_status='Active'
    ).values_list('project_id', flat=True).distinct()

    incomplete_project_cards = active_projects.exclude(
        project_id__in=projects_with_cards
    ).count()

    try:
        from operations.models import DisputeLog
        disputes_open_7days = DisputeLog.objects.filter(
            status__in=['open', 'in_progress'],
            opened_at__lt=timezone.now() - timedelta(days=7)
        ).count()
    except:
        disputes_open_7days = 0

    total_critical_alerts = projects_without_id + incomplete_project_cards + disputes_open_7days

    # KPIs — single aggregate per model instead of separate count calls
    total_projects = ProjectCode.objects.count()
    active_projects_count = active_projects.count()  # reuse queryset from above
    _user_home_agg = User.objects.aggregate(
        total_users=Count('id'),
        active_users=Count('id', filter=Q(is_active=True)),
    )
    total_users = _user_home_agg['total_users']
    active_users = _user_home_agg['active_users']

    # Monthly Revenue
    monthly_revenue_data = AdhocBillingEntry.objects.filter(
        event_date__gte=current_month_start,
        event_date__lte=today,
        status__in=['billed', 'approved']
    ).aggregate(total=Sum('total_client_amount'))
    monthly_revenue = float(monthly_revenue_data['total'] or 0) / 100000

    # Daily entries
    daily_entries_today = DailySpaceUtilization.objects.filter(
        entry_date=today
    ).values('project_id').distinct().count()

    # Active projects with daily entries today
    active_project_ids = ProjectCode.objects.filter(project_status='Active').values_list('project_id', flat=True)
    projects_with_entry_today = DailySpaceUtilization.objects.filter(
        entry_date=today
    ).values_list('project_id', flat=True).distinct()
    missing_daily_entries = active_projects.exclude(project_id__in=projects_with_entry_today).count()

    # Adhoc entries pending for more than 30 days
    adhoc_pending_30days = AdhocBillingEntry.objects.filter(
        status='pending',
        event_date__lte=today - timedelta(days=30)
    ).count()

    # System health metrics
    current_time = timezone.now().strftime('%b %d, %Y %I:%M %p')
    total_records = total_projects + total_users
    records_with_issues = projects_without_id
    data_quality_score = round(((total_records - records_with_issues) / total_records * 100), 1) if total_records > 0 else 100

    users_online_now = User.objects.filter(
        last_login__gte=timezone.now() - timedelta(minutes=30)
    ).count()

    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_database_size(current_database()) / (1024*1024)")
            database_size_mb = cursor.fetchone()[0]
    except Exception:
        database_size_mb = 0

    total_critical_alerts = projects_without_id + incomplete_project_cards + disputes_open_7days + adhoc_pending_30days + missing_daily_entries

    # Notification stats — single aggregate instead of 3 counts
    from accounts.models import Notification
    _notif_home_agg = Notification.objects.filter(recipient=request.user, is_deleted=False).aggregate(
        notifications_total=Count('id'),
        notifications_unread=Count('id', filter=Q(is_read=False)),
        notifications_urgent=Count('id', filter=Q(priority='urgent')),
    )
    notifications_total = _notif_home_agg['notifications_total']
    notifications_unread = _notif_home_agg['notifications_unread']
    notifications_urgent = _notif_home_agg['notifications_urgent']
    recent_notifications = Notification.objects.filter(
        recipient=request.user,
        is_deleted=False
    ).select_related('project', 'dispute', 'monthly_billing').order_by('-is_pinned', '-created_at')[:5]

    context = {
        'total_critical_alerts': total_critical_alerts,
        'projects_without_id': projects_without_id,
        'incomplete_project_cards': incomplete_project_cards,
        'disputes_open_7days': disputes_open_7days,
        'adhoc_pending_30days': adhoc_pending_30days,
        'missing_daily_entries': missing_daily_entries,
        'total_projects': total_projects,
        'active_projects': active_projects_count,
        'total_users': total_users,
        'active_users': active_users,
        'monthly_revenue': monthly_revenue,
        'daily_entries_today': daily_entries_today,
        'pending_adhoc': AdhocBillingEntry.objects.filter(status='pending').count(),
        'system_health': 'Healthy',
        'current_time': current_time,
        'data_quality_score': data_quality_score,
        'users_online_now': users_online_now,
        'database_size_mb': database_size_mb,
        # Notifications
        'notifications_total': notifications_total,
        'notifications_unread': notifications_unread,
        'notifications_urgent': notifications_urgent,
        'recent_notifications': recent_notifications,
    }

    return render(request, 'dashboards/admin/home.html', context)


@login_required
def admin_dashboard_projects(request):
    """
    Admin Dashboard Projects Hub
    Comprehensive project management and analytics
    """
    if request.user.role not in ['admin', 'director', 'super_user']:
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')

    # Projects by status + series — 2 aggregates instead of 8 separate counts
    _proj_status_agg = ProjectCode.objects.aggregate(
        total_projects=Count('project_id'),
        active_projects=Count('project_id', filter=Q(project_status='Active')),
        not_started_projects=Count('project_id', filter=Q(project_status='Operation Not Started')),
        notice_period_projects=Count('project_id', filter=Q(project_status='Notice Period')),
        inactive_projects=Count('project_id', filter=Q(project_status='Inactive')),
        waas_projects=Count('project_id', filter=Q(series_type='WAAS')),
        saas_projects=Count('project_id', filter=Q(series_type='SAAS')),
        gw_projects=Count('project_id', filter=Q(series_type='GW')),
    )
    total_projects = _proj_status_agg['total_projects']
    active_projects = _proj_status_agg['active_projects']
    not_started_projects = _proj_status_agg['not_started_projects']
    notice_period_projects = _proj_status_agg['notice_period_projects']
    inactive_projects = _proj_status_agg['inactive_projects']
    waas_projects = _proj_status_agg['waas_projects']
    saas_projects = _proj_status_agg['saas_projects']
    gw_projects = _proj_status_agg['gw_projects']

    # Percentages
    active_percentage = round((active_projects / total_projects * 100), 1) if total_projects > 0 else 0
    not_started_percentage = round((not_started_projects / total_projects * 100), 1) if total_projects > 0 else 0
    notice_period_percentage = round((notice_period_projects / total_projects * 100), 1) if total_projects > 0 else 0
    inactive_percentage = round((inactive_projects / total_projects * 100), 1) if total_projects > 0 else 0

    # Top states
    top_states = ProjectCode.objects.filter(
        project_status='Active',
        state__isnull=False
    ).values('state').annotate(
        count=Count('project_id')
    ).order_by('-count')[:5]

    max_state_count = top_states[0]['count'] if top_states else 1
    top_states_data = [{
        'name': state['state'],
        'count': state['count'],
        'percentage': round((state['count'] / max_state_count * 100), 1)
    } for state in top_states]

    # Data quality
    projects_without_id = ProjectCode.objects.filter(
        Q(project_id__isnull=True) | Q(project_id='')
    ).count()

    projects_with_cards = ProjectCard.objects.filter(
        project__project_status='Active'
    ).values_list('project_id', flat=True).distinct()

    incomplete_project_cards = ProjectCode.objects.filter(
        project_status='Active'
    ).exclude(project_id__in=projects_with_cards).count()

    projects_missing_coordinator = ProjectCode.objects.filter(
        operation_coordinator__isnull=True,
        project_status='Active'
    ).count()

    total_clients = ClientCard.objects.count()
    total_project_cards = ProjectCard.objects.count()

    try:
        from supply.models import CityCode
        total_locations = CityCode.objects.filter(is_active=True).count()
    except Exception:
        total_locations = 0

    # WAAS projects (not inactive) missing Main Agreement or Addendum (Vendor Commercial)
    waas_not_inactive_ids = ProjectCode.objects.filter(
        series_type='WAAS'
    ).exclude(project_status='Inactive').values_list('project_id', flat=True)

    projects_with_agreement = ProjectDocument.objects.filter(
        project_id__in=waas_not_inactive_ids
    ).exclude(project_agreement='').exclude(project_agreement__isnull=True).values_list('project_id', flat=True)
    projects_missing_agreement = len(waas_not_inactive_ids) - len(list(projects_with_agreement))

    projects_with_addendum_vendor = ProjectDocument.objects.filter(
        project_id__in=waas_not_inactive_ids
    ).exclude(project_addendum_vendor='').exclude(project_addendum_vendor__isnull=True).values_list('project_id', flat=True)
    projects_missing_addendum_vendor = len(waas_not_inactive_ids) - len(list(projects_with_addendum_vendor))

    context = {
        'total_projects': total_projects,
        'active_projects': active_projects,
        'not_started_projects': not_started_projects,
        'notice_period_projects': notice_period_projects,
        'inactive_projects': inactive_projects,
        'active_percentage': active_percentage,
        'not_started_percentage': not_started_percentage,
        'notice_period_percentage': notice_period_percentage,
        'inactive_percentage': inactive_percentage,
        'waas_projects': waas_projects,
        'saas_projects': saas_projects,
        'gw_projects': gw_projects,
        'top_states': top_states_data,
        'projects_without_id': projects_without_id,
        'incomplete_project_cards': incomplete_project_cards,
        'projects_missing_coordinator': projects_missing_coordinator,
        'total_clients': total_clients,
        'total_project_cards': total_project_cards,
        'total_locations': total_locations,
        'projects_missing_agreement': projects_missing_agreement,
        'projects_missing_addendum_vendor': projects_missing_addendum_vendor,
    }

    return render(request, 'dashboards/admin/projects.html', context)


@login_required
def admin_dashboard_operations(request):
    """
    Admin Dashboard Operations Hub
    Daily entries, billing, disputes, and operations management
    """
    if request.user.role not in ['admin', 'director', 'super_user']:
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')

    today = timezone.now().date()
    current_month_start = today.replace(day=1)

    # Daily entries
    active_projects_count = ProjectCode.objects.filter(project_status='Active').count()
    today_entries_count = DailySpaceUtilization.objects.filter(
        entry_date=today
    ).values('project_id').distinct().count()

    pending_entries_count = max(0, active_projects_count - today_entries_count)

    month_entries_count = DailySpaceUtilization.objects.filter(
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

    expected_entries = active_projects_count * working_days
    entry_completion_rate = round(
        (month_entries_count / expected_entries * 100), 1
    ) if expected_entries > 0 else 0

    # Monthly billing — single aggregate instead of 4 queries
    try:
        _bills_agg = MonthlyBilling.objects.filter(
            billing_month__month=today.month
        ).aggregate(
            bills_generated=Count('id'),
            bills_sent=Count('id', filter=Q(status='sent')),
            bills_pending=Count('id', filter=Q(status='pending')),
            bills_paid=Count('id', filter=Q(status='paid')),
        )
        bills_generated = _bills_agg['bills_generated']
        bills_sent = _bills_agg['bills_sent']
        bills_pending = _bills_agg['bills_pending']
        bills_paid = _bills_agg['bills_paid']
    except Exception:
        bills_generated = 0
        bills_sent = 0
        bills_pending = 0
        bills_paid = 0

    monthly_bills_count = bills_generated

    # Disputes — single aggregate instead of 2 queries
    try:
        from operations.models import DisputeLog
        _disputes_ops_agg = DisputeLog.objects.aggregate(
            open_disputes_count=Count('id', filter=Q(status__in=['open', 'in_progress'])),
            disputes_overdue=Count('id', filter=Q(
                status__in=['open', 'in_progress'],
                opened_at__lt=timezone.now() - timedelta(days=7)
            )),
        )
        open_disputes_count = _disputes_ops_agg['open_disputes_count']
        disputes_overdue = _disputes_ops_agg['disputes_overdue']
    except Exception:
        open_disputes_count = 0
        disputes_overdue = 0

    # Adhoc billing — single aggregate instead of 2 queries
    _adhoc_ops_agg = AdhocBillingEntry.objects.aggregate(
        pending_adhoc_count=Count('id', filter=Q(status='pending')),
        adhoc_overdue=Count('id', filter=Q(
            status='pending',
            event_date__lt=today - timedelta(days=30)
        )),
    )
    pending_adhoc_count = _adhoc_ops_agg['pending_adhoc_count']
    adhoc_overdue = _adhoc_ops_agg['adhoc_overdue']

    # Escalations and holidays
    total_escalations = 0  # Placeholder
    upcoming_holidays = 0  # Placeholder

    context = {
        'today_entries_count': today_entries_count,
        'pending_entries_count': pending_entries_count,
        'month_entries_count': month_entries_count,
        'entry_completion_rate': entry_completion_rate,
        'monthly_bills_count': monthly_bills_count,
        'open_disputes_count': open_disputes_count,
        'pending_adhoc_count': pending_adhoc_count,
        'bills_generated': bills_generated,
        'bills_sent': bills_sent,
        'bills_pending': bills_pending,
        'bills_paid': bills_paid,
        'disputes_overdue': disputes_overdue,
        'adhoc_overdue': adhoc_overdue,
        'total_escalations': total_escalations,
        'upcoming_holidays': upcoming_holidays,
    }

    return render(request, 'dashboards/admin/operations.html', context)


@login_required
def admin_dashboard_supply(request):
    """
    Admin Dashboard Supply Chain Hub
    Vendor and warehouse management
    """
    if request.user.role not in ['admin', 'director', 'super_user']:
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')

    try:
        from supply.models import VendorCard, VendorWarehouse, CityCode

        # Vendors
        total_vendors = VendorCard.objects.count()
        active_vendors = VendorCard.objects.filter(is_active=True).count()
        inactive_vendors = total_vendors - active_vendors

        # Warehouses
        total_warehouses = VendorWarehouse.objects.count()
        active_warehouses = VendorWarehouse.objects.filter(is_active=True).count()

        # Locations
        total_locations = CityCode.objects.filter(is_active=True).count()

        # Top location
        top_location = VendorWarehouse.objects.values('city__city').annotate(
            count=Count('warehouse_id')
        ).order_by('-count').first()

        top_location_name = top_location['city__city'] if top_location else 'N/A'
        top_location_count = top_location['count'] if top_location else 0

        # Warehouse capacity
        from supply.models import WarehouseCapacity
        from django.db.models import Sum as _Sum
        capacity_data = WarehouseCapacity.objects.aggregate(
            total=_Sum('total_capacity'),
            available=_Sum('available_capacity')
        )
        total_capacity = capacity_data['total'] or 0
        available_space = capacity_data['available'] or 0
        occupied_space = total_capacity - available_space
        utilization_rate = round((occupied_space / total_capacity * 100), 1) if total_capacity > 0 else 0
        performance_score = 0

    except:
        # Supply app not installed
        total_vendors = 0
        active_vendors = 0
        inactive_vendors = 0
        total_warehouses = 0
        active_warehouses = 0
        total_locations = 0
        top_location_name = 'N/A'
        top_location_count = 0
        available_space = 0
        occupied_space = 0
        utilization_rate = 0
        performance_score = 0

    context = {
        'total_vendors': total_vendors,
        'active_vendors': active_vendors,
        'inactive_vendors': inactive_vendors,
        'total_warehouses': total_warehouses,
        'active_warehouses': active_warehouses,
        'total_locations': total_locations,
        'top_location_name': top_location_name,
        'top_location_count': top_location_count,
        'available_space': available_space,
        'occupied_space': occupied_space,
        'utilization_rate': utilization_rate,
        'performance_score': performance_score,
    }

    return render(request, 'dashboards/admin/supply.html', context)


@login_required
def admin_dashboard_finance(request):
    """
    Admin Dashboard Finance Hub
    Links to TallySync finance dashboards and ERP billing tools
    """
    if request.user.role not in ['admin', 'director']:
        messages.error(request, "Access denied. Admin or Director access required.")
        return redirect('accounts:dashboard')

    return render(request, 'dashboards/admin/finance.html')


@login_required
def admin_dashboard_integrations(request):
    """
    Admin Dashboard Integrations Hub
    External system integrations and API management
    Handles credential management for all integrations (POST).
    """
    if request.user.role not in ['admin', 'director', 'super_user']:
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')

    # Handle credential save and token management (POST)
    if request.method == 'POST':
        logger.debug(f"Integrations hub POST: action={request.POST.get('action')}, integration={request.POST.get('integration')}")

        integration = request.POST.get('integration')
        action = request.POST.get('action', 'save_credentials')  # Default action

        # ========================================
        # Expense Log OAuth Connection (handle early - no integration param)
        # ========================================
        if action == 'connect_expense_log':
            logger.debug(f"Expense Log OAuth: sheet_id={request.POST.get('sheet_id')}, sheet_name={request.POST.get('sheet_name')}")

            sheet_id = request.POST.get('sheet_id', '').strip()
            sheet_name = request.POST.get('sheet_name', 'Sheet1').strip()

            if not sheet_id:
                logger.warning("Expense Log OAuth: No sheet ID provided")
                messages.error(request, "Sheet ID is required")
                return redirect('accounts:admin_dashboard_integrations')

            # Clear any old OAuth state to avoid scope mismatch
            request.session.pop('expense_log_oauth_state', None)

            # Store sheet info in session for OAuth callback
            request.session['expense_log_sheet_id'] = sheet_id
            request.session['expense_log_sheet_name'] = sheet_name

            try:
                from integrations.expense_log.utils.sheets_auth import SheetsOAuthManager
                oauth_manager = SheetsOAuthManager()
                auth_url, state = oauth_manager.get_authorization_url()
                logger.debug(f"Expense Log OAuth URL generated, state={state}")
                request.session['expense_log_oauth_state'] = state
                request.session.modified = True  # Ensure session is saved
                return redirect(auth_url)
            except Exception as e:
                logger.error(f"Expense Log OAuth error: {e}", exc_info=True)
                messages.error(request, f"OAuth error: {str(e)}")
                return redirect('accounts:admin_dashboard_integrations')

        # Expense Log Disconnect
        if action == 'disconnect_expense_log':
            try:
                from integrations.expense_log.models import GoogleSheetsToken
                token_id = request.POST.get('token_id')
                token = GoogleSheetsToken.objects.get(pk=token_id)
                token.delete()
                messages.success(request, f"Disconnected Expense Log account: {token.email_account}")
            except Exception as e:
                messages.error(request, f"Failed to disconnect: {str(e)}")
            return redirect('accounts:admin_dashboard_integrations')

        # ========================================
        # NEW: Token Management Actions
        # ========================================

        if action == 'delete_token':
            token_id = request.POST.get('token_id')
            try:
                if integration == 'google_ads':
                    from integrations.google_ads.models import GoogleAdsToken
                    token = GoogleAdsToken.objects.get(id=token_id)
                    token.delete()
                    messages.success(request, f"Deleted Google Ads token: {token.account_name}")

                elif integration == 'gmail_leads':
                    from integrations.gmail_leads.models import GmailLeadsToken
                    token = GmailLeadsToken.objects.get(id=token_id)
                    token.delete()
                    messages.success(request, f"Deleted Gmail Leads token: {token.email_account}")

                elif integration == 'callyzer':
                    from integrations.callyzer.models import CallyzerToken
                    token = CallyzerToken.objects.get(id=token_id)
                    token.delete()
                    messages.success(request, f"Deleted Callyzer token: {token.account_name}")

            except Exception as e:
                messages.error(request, f"Failed to delete token: {str(e)}")

            return redirect('accounts:admin_dashboard_integrations')

        # Bigin Disconnect
        if action == 'disconnect' and integration == 'bigin':
            try:
                from integrations.bigin.models import BiginAuthToken
                token = BiginAuthToken.objects.order_by('-created_at').first()
                if token:
                    token.delete()
                    messages.success(request, "Disconnected Bigin CRM account.")
                else:
                    messages.warning(request, "No Bigin account found to disconnect.")
            except Exception as e:
                messages.error(request, f"Failed to disconnect Bigin: {str(e)}")
            return redirect('accounts:admin_dashboard_integrations')

        # ========================================
        # Sync Actions - Redirect to Integration Views
        # ========================================

        if action in ['sync_now', 'full_sync', 'incremental_sync', 'date_range_sync', 'sync_campaigns', 'sync_search_terms']:
            account_id = request.POST.get('account_id') or request.POST.get('token_id')

            if integration == 'google_ads' and account_id:
                from integrations.google_ads import views as gads_views
                from django.http import HttpRequest

                # Create a fake POST request
                sync_request = HttpRequest()
                sync_request.method = 'POST'
                sync_request.user = request.user
                sync_request.POST = request.POST.copy()

                try:
                    if action == 'sync_campaigns':
                        # Sync only campaign performance data
                        sync_request.POST['sync_type'] = 'campaigns'
                        gads_views.sync_account(sync_request, token_id=account_id)
                        messages.success(request, "Campaign sync started successfully")
                    elif action == 'sync_search_terms':
                        # Sync only search term data
                        sync_request.POST['sync_type'] = 'search_terms'
                        gads_views.sync_account(sync_request, token_id=account_id)
                        messages.success(request, "Search Terms sync started successfully")
                    elif action == 'date_range_sync':
                        # Date range sync with optional sync_type
                        sync_type = request.POST.get('sync_type', 'all')
                        sync_request.POST['sync_type'] = sync_type
                        gads_views.sync_date_range(sync_request, token_id=account_id)
                        messages.success(request, f"Date range sync started for {sync_type}")
                    elif action == 'full_sync':
                        # Full historical sync (all types)
                        sync_request.POST['sync_type'] = 'all'
                        gads_views.sync_historical(sync_request, token_id=account_id)
                        messages.success(request, "Full sync started successfully")
                    else:  # sync_now
                        gads_views.sync_account(sync_request, token_id=account_id)
                        messages.success(request, "Google Ads sync started successfully")
                except Exception as e:
                    messages.error(request, f"Failed to start sync: {str(e)}")

                return redirect('/accounts/dashboard/admin/integrations/?tab=google_ads')

            elif integration == 'gmail_leads' and account_id:
                from integrations.gmail_leads import views as gmail_views
                from django.http import HttpRequest

                # Create a fake POST request to pass to the sync view
                sync_request = HttpRequest()
                sync_request.method = 'POST'
                sync_request.user = request.user
                sync_request.POST = request.POST.copy()

                # Set force_full parameter for full sync
                if action == 'full_sync':
                    sync_request.POST['force_full'] = '1'

                # Call the sync view directly
                try:
                    if action == 'date_range_sync':
                        gmail_views.sync_date_range_view(sync_request, token_id=account_id)
                    else:
                        gmail_views.sync_account(sync_request, token_id=account_id)
                    messages.success(request, "Gmail Leads sync started successfully")
                except Exception as e:
                    messages.error(request, f"Failed to start sync: {str(e)}")

                return redirect('/accounts/dashboard/admin/integrations/?tab=gmail_leads')

            elif integration == 'callyzer' and account_id:
                from integrations.callyzer import views as callyzer_views
                from django.http import HttpRequest

                sync_request = HttpRequest()
                sync_request.method = 'POST'
                sync_request.user = request.user
                sync_request.POST = request.POST.copy()

                try:
                    callyzer_views.sync_account(sync_request, token_id=account_id)
                    messages.success(request, "Callyzer sync started successfully")
                except Exception as e:
                    messages.error(request, f"Failed to start sync: {str(e)}")

                return redirect('/accounts/dashboard/admin/integrations/?tab=callyzer')

            elif integration == 'bigin':
                # Bigin sync via Cloud Tasks worker
                try:
                    run_full = action == 'full_sync'

                    from integration_workers import create_task
                    create_task(
                        endpoint='/integrations/bigin/workers/sync-all-modules/',
                        payload={'run_full': run_full, 'triggered_by_user': request.user.username},
                    )
                    messages.success(request, f"Bigin {'full' if run_full else 'incremental'} sync started")
                except Exception as e:
                    logger.exception(f"Failed to start Bigin sync: {e}")
                    messages.error(request, f"Failed to start Bigin sync: {str(e)}")
                return redirect('accounts:admin_dashboard_integrations')

            elif integration == 'tallysync':
                # TallySync uses worker
                from integration_workers import create_task
                company_id = request.POST.get('company_id') or None
                company_label = ''
                if company_id:
                    from integrations.tallysync.models import TallyCompany
                    try:
                        co = TallyCompany.objects.get(id=company_id)
                        company_label = f' ({co.name})'
                    except TallyCompany.DoesNotExist:
                        company_id = None

                if action == 'full_sync':
                    payload = {
                        'sync_type': 'all',
                        'full_sync': True,
                        'triggered_by_user': request.user.username,
                    }
                    if company_id:
                        payload['company_id'] = int(company_id)
                    create_task('/tallysync/workers/sync-tally-data/', payload)
                    messages.success(request, f"TallySync full history sync started{company_label} (2023 to today, monthly batches)")
                else:
                    payload = {
                        'sync_type': 'vouchers',
                        'triggered_by_user': request.user.username,
                    }
                    if company_id:
                        payload['company_id'] = int(company_id)
                    create_task('/tallysync/workers/sync-tally-data/', payload)
                    messages.success(request, f"TallySync incremental sync started{company_label}")
                return redirect('/accounts/dashboard/admin/integrations/#tallysync')

            elif integration == 'expense_log' and account_id:
                from integrations.expense_log import views as expense_views
                from django.http import HttpRequest

                sync_request = HttpRequest()
                sync_request.method = 'POST'
                sync_request.user = request.user
                sync_request.POST = request.POST.copy()

                try:
                    # Call the internal sync trigger function
                    from integrations.expense_log.views import _trigger_sync_task
                    sync_type = 'full' if action == 'full_sync' else 'incremental'
                    _trigger_sync_task(account_id, sync_type)
                    messages.success(request, f"Expense Log {sync_type} sync started successfully")
                except Exception as e:
                    messages.error(request, f"Failed to start sync: {str(e)}")

                return redirect('/accounts/dashboard/admin/integrations/?tab=expense_log')

        # ========================================
        # Stop Sync Actions (Graceful Stop)
        # ========================================
        if action == 'stop_sync':
            account_id = request.POST.get('account_id') or request.POST.get('token_id')

            try:
                from integrations.models import SyncLog

                # Find the active sync batch log for this integration/account
                if integration == 'google_ads':
                    sync_types = ['google_ads', 'google_ads_historical', 'google_ads_full']
                elif integration == 'gmail_leads':
                    sync_types = ['gmail_leads_full', 'gmail_leads_incremental']
                elif integration == 'bigin':
                    sync_types = ['bigin_full', 'bigin_incremental', 'bigin_module']
                elif integration == 'callyzer':
                    sync_types = ['callyzer']
                elif integration == 'tallysync':
                    sync_types = ['tally_vouchers', 'tally_companies', 'tally_ledgers']
                elif integration == 'expense_log':
                    sync_types = ['expense_log_full', 'expense_log_incremental']
                else:
                    messages.error(request, f"Unknown integration: {integration}")
                    return redirect('accounts:admin_dashboard_integrations')

                # Find running batch log
                batch_log = SyncLog.objects.filter(
                    integration=integration,
                    sync_type__in=sync_types,
                    log_kind='batch',
                    status='running'
                ).order_by('-started_at').first()

                if batch_log:
                    batch_log.stop_requested = True
                    batch_log.status = 'stopping'
                    batch_log.save(update_fields=['stop_requested', 'status'])

                    SyncLog.log(
                        integration=integration,
                        sync_type=batch_log.sync_type,
                        level='WARNING',
                        operation='Stop Requested',
                        message=f'Stop requested by {request.user.username}',
                        batch=batch_log
                    )

                    messages.success(request, f"{integration.title()} sync stop requested. Finishing current operation...")
                else:
                    messages.warning(request, f"No active {integration} sync found")

            except Exception as e:
                logger.exception(f"Failed to stop {integration} sync: {e}")
                messages.error(request, f"Failed to stop sync: {str(e)}")

            return redirect(f'/accounts/dashboard/admin/integrations/?tab={integration}')

        # ========================================
        # Force Stop Sync Actions (Immediate Stop)
        # ========================================
        if action == 'force_stop_sync':
            account_id = request.POST.get('account_id') or request.POST.get('token_id')

            try:
                from integrations.models import SyncLog

                # Find the active sync batch log for this integration/account
                if integration == 'google_ads':
                    sync_types = ['google_ads', 'google_ads_historical', 'google_ads_full']
                elif integration == 'gmail_leads':
                    sync_types = ['gmail_leads_full', 'gmail_leads_incremental']
                elif integration == 'bigin':
                    sync_types = ['bigin_full', 'bigin_incremental', 'bigin_module']
                elif integration == 'callyzer':
                    sync_types = ['callyzer']
                elif integration == 'tallysync':
                    sync_types = ['tally_vouchers', 'tally_companies', 'tally_ledgers']
                elif integration == 'expense_log':
                    sync_types = ['expense_log_full', 'expense_log_incremental']
                else:
                    messages.error(request, f"Unknown integration: {integration}")
                    return redirect('accounts:admin_dashboard_integrations')

                # Find most recent batch log regardless of status — force stop works on any state
                batch_log = SyncLog.objects.filter(
                    integration=integration,
                    log_kind='batch',
                ).order_by('-started_at').first()

                if batch_log:
                    duration = (timezone.now() - batch_log.started_at).total_seconds()
                    batch_log.status = 'stopped'
                    batch_log.stop_requested = True
                    batch_log.completed_at = timezone.now()
                    batch_log.duration_seconds = int(duration)
                    batch_log.error_message = f'Force stopped by {request.user.username}'
                    batch_log.save()

                    SyncLog.log(
                        integration=integration,
                        sync_type=batch_log.sync_type,
                        level='CRITICAL',
                        operation='Force Stopped',
                        message=f'Sync force stopped by {request.user.username}',
                        batch=batch_log
                    )

                    messages.warning(request, f"{integration.title()} sync force stopped.")
                else:
                    messages.warning(request, f"No sync log found for {integration}")

            except Exception as e:
                logger.exception(f"Failed to force stop {integration} sync: {e}")
                messages.error(request, f"Failed to force stop sync: {str(e)}")

            return redirect(f'/accounts/dashboard/admin/integrations/?tab={integration}')

        # Callyzer API key connection (add new account)
        # Form sends action='add_token' and field 'api_token'; also support 'connect_callyzer'/'api_key'
        if action in ('connect_callyzer', 'add_token') and integration == 'callyzer':
            try:
                from integrations.callyzer.models import CallyzerToken
                from integrations.callyzer.utils.encryption import CallyzerEncryption

                account_name = request.POST.get('account_name', '').strip()
                # Form uses 'api_token'; older code path uses 'api_key'
                api_key = (request.POST.get('api_token') or request.POST.get('api_key', '')).strip()

                if not account_name or not api_key:
                    messages.error(request, "Account name and API key are required")
                else:
                    if CallyzerToken.objects.filter(account_name=account_name).exists():
                        messages.error(request, f"Account '{account_name}' already exists")
                    else:
                        CallyzerToken.objects.create(
                            account_name=account_name,
                            encrypted_api_key=CallyzerEncryption.encrypt(api_key),
                            user=request.user,
                            is_active=True
                        )
                        messages.success(request, f"Connected Callyzer account: {account_name}")
            except Exception as e:
                messages.error(request, f"Failed to connect Callyzer: {str(e)}")
            return redirect('accounts:admin_dashboard_integrations')

        # Existing credential save logic
        if integration == 'google_ads':
            from integrations.google_ads.models import GoogleAdsSettings
            s = GoogleAdsSettings.load()
            s.account_name = request.POST.get('account_name', '').strip()
            s.customer_id = request.POST.get('customer_id', '').strip()
            s.client_id = request.POST.get('client_id', '').strip()
            if request.POST.get('client_secret', '').strip():
                s.set_client_secret(request.POST.get('client_secret').strip())
            if request.POST.get('developer_token', '').strip():
                s.set_developer_token(request.POST.get('developer_token').strip())
            s.api_version = request.POST.get('api_version', 'v19').strip() or 'v19'
            s.redirect_uri = request.POST.get('redirect_uri', '').strip()
            s.updated_by = request.user
            s.save()
            messages.success(request, "Google Ads credentials updated successfully.")

        elif integration == 'gmail_leads':
            from integrations.gmail_leads.models import GmailLeadsSettings
            s = GmailLeadsSettings.load()
            s.client_id = request.POST.get('client_id', '').strip()
            if request.POST.get('client_secret', '').strip():
                s.set_client_secret(request.POST.get('client_secret').strip())
            s.redirect_uri = request.POST.get('redirect_uri', '').strip()
            s.updated_by = request.user
            s.save()
            messages.success(request, "Gmail Leads credentials updated successfully.")

        elif integration == 'bigin':
            from integrations.bigin.models import BiginSettings
            s = BiginSettings.load()
            s.client_id = request.POST.get('client_id', '').strip()
            if request.POST.get('client_secret', '').strip():
                s.set_client_secret(request.POST.get('client_secret').strip())
            s.redirect_uri = request.POST.get('redirect_uri', '').strip()
            s.auth_url = request.POST.get('auth_url', '').strip() or 'https://accounts.zoho.com/oauth/v2/auth'
            s.token_url = request.POST.get('token_url', '').strip() or 'https://accounts.zoho.com/oauth/v2/token'
            s.updated_by = request.user
            s.save()
            messages.success(request, "Bigin credentials updated successfully.")

        elif integration == 'adobe_sign':
            from integrations.adobe_sign.models import AdobeSignSettings
            s = AdobeSignSettings.get_settings()
            if request.POST.get('integration_key', '').strip():
                s.set_integration_key(request.POST.get('integration_key').strip())
            s.api_base_url = request.POST.get('api_base_url', '').strip() or s.api_base_url
            s.save()
            messages.success(request, "Adobe Sign credentials updated successfully.")

        elif integration == 'tallysync':
            from integrations.tallysync.models import TallySyncSettings
            s = TallySyncSettings.load()
            s.server_ip = request.POST.get('server_ip', '').strip()
            s.server_port = request.POST.get('server_port', '').strip() or '9000'
            s.company_name = request.POST.get('company_name', '').strip()
            s.tunnel_url = request.POST.get('tunnel_url', '').strip()
            s.updated_by = request.user
            s.save()
            conn_info = s.tunnel_url if s.tunnel_url else f"{s.server_ip}:{s.server_port}"
            messages.success(request, f"TallySync connection settings updated: {conn_info}")

        elif integration == 'expense_log':
            from integrations.expense_log.models import ExpenseLogSettings
            from integrations.expense_log.utils.encryption import ExpenseLogEncryption
            s = ExpenseLogSettings.load()
            s.client_id = request.POST.get('client_id', '').strip()
            if request.POST.get('client_secret', '').strip():
                s.encrypted_client_secret = ExpenseLogEncryption.encrypt(request.POST.get('client_secret').strip())
            s.redirect_uri = request.POST.get('redirect_uri', '').strip()
            s.api_version = request.POST.get('api_version', 'v4').strip() or 'v4'
            s.updated_by = request.user
            s.save()
            messages.success(request, "Expense Log credentials updated successfully.")

        return redirect('accounts:admin_dashboard_integrations')

    # ========================================
    # Additional POST Handlers
    # ========================================

    # Note: OAuth connections, sync triggers, disconnect handled by individual app views
    # Gmail excluded emails filter update
    if request.method == 'POST' and request.POST.get('action') == 'update_gmail_filters':
        try:
            from integrations.gmail_leads.models import GmailLeadsToken
            token_id = request.POST.get('token_id')
            excluded_emails = request.POST.get('excluded_emails', '').strip()
            token = GmailLeadsToken.objects.get(id=token_id)
            token.excluded_emails = excluded_emails
            token.save()
            messages.success(request, f"Updated excluded emails for {token.email_account}")
        except Exception as e:
            messages.error(request, f"Failed to update filters: {str(e)}")
        return redirect('accounts:admin_dashboard_integrations')

    # Adobe Sign director configuration
    if request.method == 'POST' and request.POST.get('action') == 'save_adobe_director':
        try:
            from integrations.adobe_sign.models import AdobeSignSettings
            s = AdobeSignSettings.get_settings()
            s.director_name = request.POST.get('director_name', '').strip()
            s.director_email = request.POST.get('director_email', '').strip()
            s.director_title = request.POST.get('director_title', '').strip()
            s.save()
            messages.success(request, "Adobe Sign director information updated successfully")
        except Exception as e:
            messages.error(request, f"Failed to update Adobe Sign settings: {str(e)}")
        return redirect('accounts:admin_dashboard_integrations')

    # Gmail App (standalone inbox)
    try:
        from gmail.models import GmailToken, Thread, GmailSettings
        from integrations.models import SyncLog as _SyncLog
        gmail_app_tokens = GmailToken.objects.filter(is_active=True)
        gmail_app_token_count = gmail_app_tokens.count()
        gmail_app_thread_count = Thread.objects.count()
        gmail_app_unread = Thread.objects.filter(has_unread=True).count()
        gmail_app_status = 'Connected' if gmail_app_token_count > 0 else 'Not Connected'
        gmail_app_settings = GmailSettings.load()
        last_gmail_thread = Thread.objects.order_by('-last_message_date').first()
        gmail_app_last_sync = last_gmail_thread.last_message_date.strftime('%b %d, %I:%M %p') if last_gmail_thread else 'Never'
        gmail_app_sync_logs = _SyncLog.objects.filter(
            integration='gmail', log_kind='batch'
        ).order_by('-started_at')[:20]
        gmail_app_tokens_list = gmail_app_tokens.select_related('user')
    except Exception:
        gmail_app_token_count = 0
        gmail_app_thread_count = 0
        gmail_app_unread = 0
        gmail_app_status = 'Not Connected'
        gmail_app_sync_logs = []
        gmail_app_tokens_list = []
        gmail_app_settings = None
        gmail_app_tokens = []
        gmail_app_last_sync = 'Never'

    # Gmail Leads Integration
    try:
        from integrations.gmail_leads.models import LeadEmail, GmailLeadsToken
        gmail_leads_count = LeadEmail.objects.count()
        gmail_leads_tokens = GmailLeadsToken.objects.filter(is_active=True).count()
        gmail_leads_unread = LeadEmail.objects.filter(is_read=False).count()
        gmail_leads_status = 'Connected' if gmail_leads_tokens > 0 else 'Not Connected'
        last_gmail_lead = LeadEmail.objects.order_by('-datetime_received').first()
        gmail_leads_last_sync = last_gmail_lead.datetime_received.strftime('%b %d, %I:%M %p') if last_gmail_lead else 'Never'
    except Exception:
        gmail_leads_count = 0
        gmail_leads_tokens = 0
        gmail_leads_unread = 0
        gmail_leads_status = 'Not Connected'
        gmail_leads_last_sync = 'Never'

    # Google Ads Integration
    try:
        from integrations.google_ads.models import GoogleAdsToken, GoogleAdsCampaign
        google_ads_count = GoogleAdsCampaign.objects.count()
        google_ads_tokens = GoogleAdsToken.objects.filter(is_active=True).count()
        google_ads_active_campaigns = GoogleAdsCampaign.objects.filter(status='ENABLED').count()
        google_ads_status = 'Connected' if google_ads_tokens > 0 else 'Not Connected'
        last_google_sync = GoogleAdsCampaign.objects.order_by('-last_synced_at').first()
        google_ads_last_sync = last_google_sync.last_synced_at.strftime('%b %d, %I:%M %p') if last_google_sync else 'Never'
    except Exception:
        google_ads_count = 0
        google_ads_tokens = 0
        google_ads_active_campaigns = 0
        google_ads_status = 'Not Connected'
        google_ads_last_sync = 'Never'

    # Callyzer Integration
    try:
        from integrations.callyzer.models import CallRecord, CallyzerToken
        callyzer_calls_count = CallRecord.objects.count()
        callyzer_tokens = CallyzerToken.objects.filter(is_active=True).count()
        callyzer_missed_calls = CallRecord.objects.filter(call_type='MISSED').count()
        callyzer_status = 'Connected' if callyzer_tokens > 0 else 'Not Connected'
        last_callyzer_call = CallRecord.objects.order_by('-call_datetime').first()
        callyzer_last_sync = last_callyzer_call.call_datetime.strftime('%b %d, %I:%M %p') if last_callyzer_call else 'Never'
    except Exception:
        callyzer_calls_count = 0
        callyzer_tokens = 0
        callyzer_missed_calls = 0
        callyzer_status = 'Not Connected'
        callyzer_last_sync = 'Never'

    # Bigin CRM Integration
    try:
        from integrations.bigin.models import BiginContact, BiginDeal
        bigin_contacts = BiginContact.objects.count()
        bigin_deals = BiginDeal.objects.count()
        bigin_synced_count = bigin_contacts + bigin_deals
        bigin_status = 'Active' if bigin_synced_count > 0 else 'Not Connected'
        last_bigin_sync = BiginContact.objects.order_by('-Modified_Time').first()
        bigin_last_sync = last_bigin_sync.Modified_Time.strftime('%b %d, %I:%M %p') if last_bigin_sync else 'Never'
    except Exception:
        bigin_synced_count = 0
        bigin_status = 'Not Connected'
        bigin_contacts = 0
        bigin_deals = 0
        bigin_last_sync = 'Never'

    # TallySync Integration
    try:
        from integrations.tallysync.models import TallyInvoice, TallyPayment
        tally_invoices = TallyInvoice.objects.count()
        tally_payments = TallyPayment.objects.count()
        tally_synced_count = tally_invoices + tally_payments
        tally_status = 'Active' if tally_synced_count > 0 else 'Not Connected'
        last_tally_sync = TallyInvoice.objects.order_by('-synced_at').first()
        tally_last_sync = last_tally_sync.synced_at.strftime('%b %d, %I:%M %p') if last_tally_sync else 'Never'
    except Exception:
        tally_synced_count = 0
        tally_status = 'Not Connected'
        tally_invoices = 0
        tally_payments = 0
        tally_last_sync = 'Never'

    # Adobe Sign Integration
    try:
        from integrations.adobe_sign.models import AdobeAgreement
        adobe_total = AdobeAgreement.objects.count()
        adobe_sent = AdobeAgreement.objects.filter(
            approval_status__in=['APPROVED_SENT', 'IN_PROCESS']
        ).count()
        adobe_pending = AdobeAgreement.objects.filter(
            approval_status='PENDING_APPROVAL'
        ).count()
        adobe_completed = AdobeAgreement.objects.filter(
            approval_status='COMPLETED'
        ).count()
        adobe_documents_count = adobe_total
        adobe_status = 'Active' if adobe_total > 0 else 'Configured'
    except Exception:
        adobe_documents_count = 0
        adobe_status = 'Not Configured'
        adobe_sent = 0
        adobe_pending = 0
        adobe_completed = 0

    # Expense Log Integration
    try:
        from integrations.expense_log.models import ExpenseRecord, GoogleSheetsToken
        expense_log_count = ExpenseRecord.objects.count()
        expense_log_tokens = GoogleSheetsToken.objects.filter(is_active=True).count()
        expense_log_approved = ExpenseRecord.objects.filter(approval_status='Approved').count()
        expense_log_pending = ExpenseRecord.objects.filter(approval_status='Pending').count()
        expense_log_status = 'Connected' if expense_log_tokens > 0 else 'Not Connected'
        last_expense_record = ExpenseRecord.objects.order_by('-updated_at').first()
        expense_log_last_sync = last_expense_record.updated_at.strftime('%b %d, %I:%M %p') if last_expense_record else 'Never'
    except Exception:
        expense_log_count = 0
        expense_log_tokens = 0
        expense_log_approved = 0
        expense_log_pending = 0
        expense_log_status = 'Not Connected'
        expense_log_last_sync = 'Never'

    # Total API calls (sum of all integrations)
    total_api_calls = gmail_leads_count + google_ads_count + callyzer_calls_count + bigin_synced_count + tally_synced_count

    # API health metrics (placeholder - can be enhanced with actual monitoring)
    api_uptime = 99.5
    api_calls_growth = 0
    failed_requests = 0
    failure_rate = 0

    recent_syncs = []

    # Load credential settings for Tab 2 (Credentials panel)
    try:
        from integrations.google_ads.models import GoogleAdsSettings
        google_ads_settings = GoogleAdsSettings.load()
    except Exception:
        google_ads_settings = None

    try:
        from integrations.gmail_leads.models import GmailLeadsSettings
        gmail_leads_settings = GmailLeadsSettings.load()
    except Exception:
        gmail_leads_settings = None

    try:
        from integrations.bigin.models import BiginSettings
        bigin_settings = BiginSettings.load()
    except Exception:
        bigin_settings = None

    try:
        from integrations.adobe_sign.models import AdobeSignSettings
        adobe_sign_settings = AdobeSignSettings.get_settings()
    except Exception:
        adobe_sign_settings = None

    try:
        from integrations.expense_log.models import ExpenseLogSettings
        expense_log_settings = ExpenseLogSettings.load()
    except Exception:
        expense_log_settings = None

    # Callyzer tokens for credentials tab
    try:
        from integrations.callyzer.models import CallyzerToken
        callyzer_token_list = CallyzerToken.objects.filter(is_active=True).values(
            'id', 'account_name', 'encrypted_api_key', 'is_active'
        )
        callyzer_token_count = callyzer_token_list.count()
    except Exception:
        callyzer_token_list = []
        callyzer_token_count = 0

    # TallySync server config (from database)
    from integrations.tallysync.models import TallySyncSettings
    from django.conf import settings
    tallysync_settings = TallySyncSettings.load()
    # Fallback to env if DB is empty
    tally_host = tallysync_settings.server_ip or getattr(settings, 'TALLY_HOST', '')
    tally_port = tallysync_settings.server_port or getattr(settings, 'TALLY_PORT', '')

    # ========================================
    # NEW: Token lists for Tab 2 (Credentials & Connections)
    # ========================================

    # Google Ads tokens
    try:
        from integrations.google_ads.models import GoogleAdsToken
        google_ads_tokens_list = GoogleAdsToken.objects.filter(is_active=True).values(
            'id', 'account_name', 'customer_id', 'last_synced_at', 'created_at'
        )
    except Exception:
        google_ads_tokens_list = []

    # Gmail Leads tokens
    try:
        from integrations.gmail_leads.models import GmailLeadsToken
        gmail_leads_tokens_list = GmailLeadsToken.objects.filter(is_active=True).values(
            'id', 'email_account', 'last_sync_at', 'excluded_emails', 'created_at'
        )
    except Exception:
        gmail_leads_tokens_list = []

    # Bigin token (single token system)
    try:
        from integrations.bigin.models import BiginAuthToken
        bigin_token = BiginAuthToken.objects.order_by('-created_at').first()
    except Exception:
        bigin_token = None

    # Expense Log tokens
    try:
        from integrations.expense_log.models import GoogleSheetsToken, ExpenseLogSettings
        expense_log_tokens_list = GoogleSheetsToken.objects.filter(is_active=True)
        expense_log_settings = ExpenseLogSettings.load()
    except Exception:
        expense_log_tokens_list = []
        expense_log_settings = None

    # ========================================
    # NEW: Sync status for Tab 3 (Sync Configuration) & Tab 5 (Activity)
    # ========================================

    from integrations.models import SyncLog

    # Recent sync per integration (for Tab 3 - last sync status)
    recent_syncs_per_integration = {}
    for integration_name in ['google_ads', 'gmail_leads', 'bigin', 'callyzer', 'tallysync', 'adobe_sign', 'expense_log']:
        try:
            recent_syncs_per_integration[integration_name] = SyncLog.objects.filter(
                integration=integration_name,
                log_kind='batch'
            ).order_by('-started_at').first()
        except:
            recent_syncs_per_integration[integration_name] = None

    # Running syncs (for Tab 3 - real-time progress)
    try:
        running_syncs = SyncLog.objects.filter(
            status='running',
            log_kind='batch'
        ).select_related('user').values(
            'id', 'integration', 'started_at', 'overall_progress_percent',
            'total_records_synced', 'current_module', 'sub_type'
        )
    except:
        running_syncs = []

    # Last 10 syncs for Tab 5 (Sync Activity)
    try:
        recent_syncs_detailed = SyncLog.objects.filter(
            log_kind='batch'
        ).order_by('-started_at')[:10].values(
            'id', 'integration', 'status', 'started_at', 'completed_at',
            'total_records_synced', 'sub_type'
        )
    except:
        recent_syncs_detailed = []

    # ========================================
    # NEW: Additional data counts for Tab 4 (Data & Overview)
    # ========================================

    # Google Ads additional counts
    try:
        from integrations.google_ads.models import GoogleAdsAd, GoogleAdsKeyword
        google_ads_ads_count = GoogleAdsAd.objects.count()
        google_ads_keywords_count = GoogleAdsKeyword.objects.count()
    except:
        google_ads_ads_count = 0
        google_ads_keywords_count = 0

    # Gmail Leads by type
    try:
        from integrations.gmail_leads.models import LeadEmail
        gmail_leads_contact_us = LeadEmail.objects.filter(lead_type='CONTACT_US').count()
        gmail_leads_saas_inventory = LeadEmail.objects.filter(lead_type='SAAS_INVENTORY').count()
    except:
        gmail_leads_contact_us = 0
        gmail_leads_saas_inventory = 0

    # TallySync additional counts
    try:
        from integrations.tallysync.models import TallyVoucher, TallyLedger, TallyCostCentre
        tally_vouchers_count = TallyVoucher.objects.count()
        tally_ledgers_count = TallyLedger.objects.count()
        tally_cost_centres_count = TallyCostCentre.objects.count()
    except:
        tally_vouchers_count = 0
        tally_ledgers_count = 0
        tally_cost_centres_count = 0

    # Callyzer by call type
    try:
        from integrations.callyzer.models import CallHistory
        callyzer_incoming_count = CallHistory.objects.filter(call_type='incoming').count()
        callyzer_outgoing_count = CallHistory.objects.filter(call_type='outgoing').count()
    except:
        callyzer_incoming_count = 0
        callyzer_outgoing_count = 0

    # ========================================
    # Per-Integration Recent Syncs (for Live Logs & History)
    # ========================================

    # Google Ads recent syncs
    try:
        google_ads_recent_syncs = SyncLog.objects.filter(
            integration='google_ads',
            log_kind='batch'
        ).order_by('-started_at')[:10]
        # Add duration_display property
        for sync in google_ads_recent_syncs:
            if sync.completed_at and sync.started_at:
                duration = sync.completed_at - sync.started_at
                sync.duration_display = f"{duration.seconds // 60}m {duration.seconds % 60}s"
            else:
                sync.duration_display = "In progress"
    except:
        google_ads_recent_syncs = []

    # Gmail Leads recent syncs
    try:
        gmail_leads_recent_syncs = SyncLog.objects.filter(
            integration='gmail_leads',
            log_kind='batch'
        ).order_by('-started_at')[:10]
        for sync in gmail_leads_recent_syncs:
            if sync.completed_at and sync.started_at:
                duration = sync.completed_at - sync.started_at
                sync.duration_display = f"{duration.seconds // 60}m {duration.seconds % 60}s"
            else:
                sync.duration_display = "In progress"
    except:
        gmail_leads_recent_syncs = []

    # Bigin recent syncs
    try:
        bigin_recent_syncs = SyncLog.objects.filter(
            integration='bigin',
            log_kind='batch'
        ).order_by('-started_at')[:10]
        for sync in bigin_recent_syncs:
            if sync.completed_at and sync.started_at:
                duration = sync.completed_at - sync.started_at
                sync.duration_display = f"{duration.seconds // 60}m {duration.seconds % 60}s"
            else:
                sync.duration_display = "In progress"
    except:
        bigin_recent_syncs = []

    # Callyzer recent syncs
    try:
        callyzer_recent_syncs = SyncLog.objects.filter(
            integration='callyzer',
            log_kind='batch'
        ).order_by('-started_at')[:10]
        for sync in callyzer_recent_syncs:
            if sync.completed_at and sync.started_at:
                duration = sync.completed_at - sync.started_at
                sync.duration_display = f"{duration.seconds // 60}m {duration.seconds % 60}s"
            else:
                sync.duration_display = "In progress"
    except:
        callyzer_recent_syncs = []

    # TallySync recent syncs
    try:
        tallysync_recent_syncs = SyncLog.objects.filter(
            integration='tallysync',
            log_kind='batch'
        ).order_by('-started_at')[:10]
        for sync in tallysync_recent_syncs:
            if sync.completed_at and sync.started_at:
                duration = sync.completed_at - sync.started_at
                sync.duration_display = f"{duration.seconds // 60}m {duration.seconds % 60}s"
            else:
                sync.duration_display = "In progress"
    except:
        tallysync_recent_syncs = []

    # ========================================
    # SYNC MONITOR: Unified data for Sync Monitor tab
    # (mirrors integrations/views_sync_audit.py but embedded here)
    # ========================================
    sync_audit_integrations = []
    _sync_audit_today = timezone.now().date()

    # Gmail Leads
    try:
        from integrations.gmail_leads.models import LeadEmail, GmailLeadsToken
        _gl_tokens = GmailLeadsToken.objects.filter(is_active=True)
        _gl_token = _gl_tokens.first()
        _gl_total = LeadEmail.objects.count()
        _gl_today = LeadEmail.objects.filter(datetime_received__date=_sync_audit_today).count()
        _gl_contact_us = LeadEmail.objects.filter(lead_type='CONTACT_US').count()
        _gl_saas = LeadEmail.objects.filter(lead_type='SAAS_INVENTORY').count()
        _gl_running = SyncLog.objects.filter(integration='gmail_leads', log_kind='batch', status='running').order_by('-started_at').first()
        _gl_last = SyncLog.objects.filter(integration='gmail_leads', log_kind='batch', status='completed').order_by('-completed_at').first()
        sync_audit_integrations.append({
            'name': 'Gmail Leads', 'key': 'gmail_leads', 'icon': 'mail', 'color': 'blue',
            'status': 'connected' if _gl_token else 'disconnected',
            'total_records': _gl_total, 'today_records': _gl_today,
            'contact_us_count': _gl_contact_us, 'saas_count': _gl_saas,
            'accounts_count': _gl_tokens.count(),
            'last_sync': _gl_last.completed_at if _gl_last else None,
            'is_syncing': _gl_running is not None,
            'sync_progress': _gl_running.overall_progress_percent if _gl_running else 0,
            'sync_id': _gl_running.id if _gl_running else None,
            'has_full_sync': True, 'has_incremental_sync': True,
            'dashboard_url': 'gmail_leads:dashboard',
            'sync_audit_url': 'gmail_leads:sync_logs',
        })
    except Exception as _e:
        logger.error(f"Sync Monitor Gmail Leads error: {_e}")
        sync_audit_integrations.append({'name': 'Gmail Leads', 'key': 'gmail_leads', 'icon': 'mail', 'color': 'blue', 'status': 'error', 'error_message': str(_e)})

    # Google Ads
    try:
        from integrations.google_ads.models import Campaign, GoogleAdsToken
        _ga_token = GoogleAdsToken.objects.filter(is_active=True).first()
        _ga_total = Campaign.objects.count()
        _ga_today = Campaign.objects.filter(created_at__date=_sync_audit_today).count()
        _ga_active = Campaign.objects.filter(campaign_status='ENABLED').count()
        _ga_running = SyncLog.objects.filter(integration='google_ads', log_kind='batch', status='running').order_by('-started_at').first()
        _ga_last = SyncLog.objects.filter(integration='google_ads', log_kind='batch', status='completed').order_by('-completed_at').first()
        sync_audit_integrations.append({
            'name': 'Google Ads', 'key': 'google_ads', 'icon': 'trending-up', 'color': 'red',
            'status': 'connected' if _ga_token else 'disconnected',
            'total_records': _ga_total, 'today_records': _ga_today, 'active_count': _ga_active,
            'last_sync': _ga_last.completed_at if _ga_last else None,
            'is_syncing': _ga_running is not None,
            'sync_progress': _ga_running.overall_progress_percent if _ga_running else 0,
            'sync_id': _ga_running.id if _ga_running else None,
            'has_full_sync': True, 'has_incremental_sync': True,
            'dashboard_url': 'google_ads:dashboard',
            'sync_audit_url': 'google_ads:sync_logs',
        })
    except Exception as _e:
        logger.error(f"Sync Monitor Google Ads error: {_e}")
        sync_audit_integrations.append({'name': 'Google Ads', 'key': 'google_ads', 'icon': 'trending-up', 'color': 'red', 'status': 'error', 'error_message': str(_e)})

    # Callyzer
    try:
        from integrations.callyzer.models import CallHistory, CallyzerToken
        _ca_token = CallyzerToken.objects.filter(is_active=True).first()
        _ca_total = CallHistory.objects.count()
        _ca_today = CallHistory.objects.filter(call_date=_sync_audit_today).count()
        _ca_missed = CallHistory.objects.filter(call_type='missed').count()
        _ca_running = SyncLog.objects.filter(integration='callyzer', log_kind='batch', status='running').order_by('-started_at').first()
        _ca_last = SyncLog.objects.filter(integration='callyzer', log_kind='batch', status='completed').order_by('-completed_at').first()
        sync_audit_integrations.append({
            'name': 'Callyzer', 'key': 'callyzer', 'icon': 'phone', 'color': 'orange',
            'status': 'connected' if _ca_token else 'disconnected',
            'total_records': _ca_total, 'today_records': _ca_today, 'missed_count': _ca_missed,
            'last_sync': _ca_last.completed_at if _ca_last else None,
            'is_syncing': _ca_running is not None,
            'sync_progress': _ca_running.overall_progress_percent if _ca_running else 0,
            'sync_id': _ca_running.id if _ca_running else None,
            'has_full_sync': True, 'has_incremental_sync': False,
            'dashboard_url': 'callyzer:dashboard',
            'sync_audit_url': 'callyzer:sync_logs',
        })
    except Exception as _e:
        logger.error(f"Sync Monitor Callyzer error: {_e}")
        sync_audit_integrations.append({'name': 'Callyzer', 'key': 'callyzer', 'icon': 'phone', 'color': 'orange', 'status': 'error', 'error_message': str(_e)})

    # Bigin CRM
    try:
        from integrations.bigin.models import BiginRecord, BiginAuthToken
        _bi_contacts = BiginRecord.objects.filter(module='Contacts').count()
        _bi_deals = BiginRecord.objects.filter(module='Pipelines').count()
        _bi_total = BiginRecord.objects.count()
        _bi_today = BiginRecord.objects.filter(module='Contacts', created_time__date=_sync_audit_today).count() + BiginRecord.objects.filter(module='Pipelines', created_time__date=_sync_audit_today).count()
        _bi_running = SyncLog.objects.filter(integration='bigin', log_kind='batch', status='running').order_by('-started_at').first()
        _bi_last = SyncLog.objects.filter(integration='bigin', log_kind='batch', status='completed').order_by('-completed_at').first()
        _bi_token = BiginAuthToken.objects.order_by('-created_at').first()
        _bi_connected = _bi_token is not None and not _bi_token.is_expired()
        sync_audit_integrations.append({
            'name': 'Bigin CRM', 'key': 'bigin', 'icon': 'users', 'color': 'indigo',
            'status': 'connected' if _bi_connected else 'disconnected',
            'total_records': _bi_total, 'today_records': _bi_today,
            'contacts_count': _bi_contacts, 'deals_count': _bi_deals,
            'last_sync': _bi_last.completed_at if _bi_last else None,
            'is_syncing': _bi_running is not None,
            'sync_progress': _bi_running.overall_progress_percent if _bi_running else 0,
            'sync_id': _bi_running.id if _bi_running else None,
            'has_full_sync': True, 'has_incremental_sync': True,
            'dashboard_url': 'bigin:bigin_dashboard',
            'sync_audit_url': 'bigin:sync_audit',
        })
    except Exception as _e:
        logger.error(f"Sync Monitor Bigin error: {_e}")
        sync_audit_integrations.append({'name': 'Bigin CRM', 'key': 'bigin', 'icon': 'users', 'color': 'indigo', 'status': 'error', 'error_message': str(_e)})

    # TallySync
    try:
        from integrations.tallysync.models import TallyVoucher as _TV
        _ta_invoices = _TV.objects.filter(is_invoice=True).count()
        _ta_payments = _TV.objects.filter(voucher_type='Payment').count()
        _ta_total = _TV.objects.count()
        _ta_today = _TV.objects.filter(created_at__date=_sync_audit_today).count()
        _ta_running = SyncLog.objects.filter(integration='tallysync', log_kind='batch', status='running').order_by('-started_at').first()
        _ta_last = SyncLog.objects.filter(integration='tallysync', log_kind='batch', status='completed').order_by('-completed_at').first()
        sync_audit_integrations.append({
            'name': 'TallySync', 'key': 'tallysync', 'icon': 'calculator', 'color': 'green',
            'status': 'connected' if _ta_total > 0 else 'disconnected',
            'total_records': _ta_total, 'today_records': _ta_today,
            'invoices_count': _ta_invoices, 'payments_count': _ta_payments,
            'last_sync': _ta_last.completed_at if _ta_last else None,
            'is_syncing': _ta_running is not None,
            'sync_progress': _ta_running.overall_progress_percent if _ta_running else 0,
            'sync_id': _ta_running.id if _ta_running else None,
            'has_full_sync': True, 'has_incremental_sync': False,
            'dashboard_url': 'tallysync:reconciliation_dashboard',
        })
    except Exception as _e:
        logger.error(f"Sync Monitor TallySync error: {_e}")
        sync_audit_integrations.append({'name': 'TallySync', 'key': 'tallysync', 'icon': 'calculator', 'color': 'green', 'status': 'error', 'error_message': str(_e)})

    # Adobe Sign
    try:
        from integrations.adobe_sign.models import AdobeAgreement, AdobeSignSettings
        _ab_settings = AdobeSignSettings.objects.first()
        _ab_total = AdobeAgreement.objects.count()
        _ab_today = AdobeAgreement.objects.filter(created_at__date=_sync_audit_today).count()
        _ab_pending = AdobeAgreement.objects.filter(adobe_status__in=['OUT_FOR_SIGNATURE', 'AUTHORING']).count()
        _ab_signed = AdobeAgreement.objects.filter(adobe_status='SIGNED').count()
        _ab_last = AdobeAgreement.objects.order_by('-created_at').first()
        sync_audit_integrations.append({
            'name': 'Adobe Sign', 'key': 'adobe_sign', 'icon': 'file-text', 'color': 'pink',
            'status': 'connected' if _ab_settings and _ab_settings.integration_key else 'disconnected',
            'total_records': _ab_total, 'today_records': _ab_today,
            'pending_count': _ab_pending, 'signed_count': _ab_signed,
            'last_sync': _ab_last.created_at if _ab_last else None,
            'is_syncing': False, 'has_full_sync': False, 'has_incremental_sync': False,
            'dashboard_url': 'adobe_sign:dashboard',
        })
    except Exception as _e:
        logger.error(f"Sync Monitor Adobe Sign error: {_e}")
        sync_audit_integrations.append({'name': 'Adobe Sign', 'key': 'adobe_sign', 'icon': 'file-text', 'color': 'pink', 'status': 'error', 'error_message': str(_e)})

    # Unified sync history (last 50 batch logs across all integrations)
    sync_audit_recent_batch_logs = SyncLog.objects.filter(log_kind='batch').order_by('-started_at')[:50]

    # Summary stats
    sync_audit_total_integrations = len(sync_audit_integrations)
    sync_audit_connected_count = len([i for i in sync_audit_integrations if i.get('status') == 'connected'])
    sync_audit_syncing_count = len([i for i in sync_audit_integrations if i.get('is_syncing', False)])
    sync_audit_total_records_today = sum(i.get('today_records', 0) for i in sync_audit_integrations)
    sync_audit_current_time = timezone.now()

    context = {
        # Gmail App (standalone inbox)
        'gmail_app_token_count': gmail_app_token_count,
        'gmail_app_thread_count': gmail_app_thread_count,
        'gmail_app_unread': gmail_app_unread,
        'gmail_app_status': gmail_app_status,
        'gmail_app_settings': gmail_app_settings,
        'gmail_app_tokens': gmail_app_tokens,
        'gmail_app_tokens_list': gmail_app_tokens_list,
        'gmail_app_last_sync': gmail_app_last_sync,
        'gmail_app_sync_logs': gmail_app_sync_logs,

        # Gmail Leads
        'gmail_leads_count': gmail_leads_count,
        'gmail_leads_status': gmail_leads_status,
        'gmail_leads_tokens': gmail_leads_tokens,
        'gmail_leads_unread': gmail_leads_unread,
        'gmail_leads_last_sync': gmail_leads_last_sync,

        # Google Ads
        'google_ads_count': google_ads_count,
        'google_ads_status': google_ads_status,
        'google_ads_tokens': google_ads_tokens,
        'google_ads_active_campaigns': google_ads_active_campaigns,
        'google_ads_last_sync': google_ads_last_sync,

        # Callyzer
        'callyzer_calls_count': callyzer_calls_count,
        'callyzer_status': callyzer_status,
        'callyzer_tokens': callyzer_tokens,
        'callyzer_missed_calls': callyzer_missed_calls,
        'callyzer_last_sync': callyzer_last_sync,

        # Bigin
        'bigin_synced_count': bigin_synced_count,
        'bigin_status': bigin_status,
        'bigin_contacts': bigin_contacts,
        'bigin_deals': bigin_deals,
        'bigin_last_sync': bigin_last_sync,

        # TallySync
        'tally_synced_count': tally_synced_count,
        'tally_status': tally_status,
        'tally_invoices': tally_invoices,
        'tally_payments': tally_payments,
        'tally_last_sync': tally_last_sync,

        # Adobe Sign
        'adobe_documents_count': adobe_documents_count,
        'adobe_status': adobe_status,
        'adobe_sent': adobe_sent,
        'adobe_pending': adobe_pending,
        'adobe_completed': adobe_completed,

        # Expense Log
        'expense_log_count': expense_log_count,
        'expense_log_status': expense_log_status,
        'expense_log_tokens': expense_log_tokens,
        'expense_log_approved': expense_log_approved,
        'expense_log_pending': expense_log_pending,
        'expense_log_last_sync': expense_log_last_sync,

        # API Health
        'total_api_calls': total_api_calls,
        'api_uptime': api_uptime,
        'api_calls_growth': api_calls_growth,
        'failed_requests': failed_requests,
        'failure_rate': failure_rate,
        'recent_syncs': recent_syncs,

        # Credential Settings (for Tab 2 - Credentials)
        'google_ads_settings': google_ads_settings,
        'gmail_leads_settings': gmail_leads_settings,
        'bigin_settings': bigin_settings,
        'adobe_sign_settings': adobe_sign_settings,
        'expense_log_settings': expense_log_settings,
        'callyzer_tokens': callyzer_token_list,
        'callyzer_token_count': callyzer_token_count,
        'tallysync_settings': tallysync_settings,
        'tally_host': tally_host,
        'tally_port': tally_port,

        # NEW: Tab 2 - Token lists
        'google_ads_tokens_list': google_ads_tokens_list,
        'gmail_leads_tokens_list': gmail_leads_tokens_list,
        'expense_log_tokens_list': expense_log_tokens_list,
        'expense_log_settings': expense_log_settings,
        'expense_log_sync_logs': SyncLog.objects.filter(
            integration='expense_log',
            log_kind='batch'
        ).order_by('-started_at')[:20],
        'bigin_token': bigin_token,

        # NEW: Sync logs for all integrations (for history tables)
        'google_ads_sync_logs': SyncLog.objects.filter(
            integration='google_ads',
            log_kind='batch'
        ).order_by('-started_at')[:20],
        'gmail_leads_sync_logs': SyncLog.objects.filter(
            integration='gmail_leads',
            log_kind='batch'
        ).order_by('-started_at')[:20],
        'bigin_sync_logs': SyncLog.objects.filter(
            integration='bigin',
            log_kind='batch'
        ).order_by('-started_at')[:20],
        'callyzer_sync_logs': SyncLog.objects.filter(
            integration='callyzer',
            log_kind='batch'
        ).order_by('-started_at')[:20],
        'tallysync_sync_logs': SyncLog.objects.filter(
            integration='tallysync',
            log_kind='batch'
        ).order_by('-started_at')[:20],

        # NEW: Tab 3 & Tab 5 - Sync status
        'recent_syncs_per_integration': recent_syncs_per_integration,
        'running_syncs': running_syncs,
        'recent_syncs_detailed': recent_syncs_detailed,

        # NEW: Tab 4 - Additional data counts
        'google_ads_ads_count': google_ads_ads_count,
        'google_ads_keywords_count': google_ads_keywords_count,
        'gmail_leads_contact_us': gmail_leads_contact_us,
        'gmail_leads_saas_inventory': gmail_leads_saas_inventory,
        'tally_vouchers_count': tally_vouchers_count,
        'tally_ledgers_count': tally_ledgers_count,
        'tally_cost_centres_count': tally_cost_centres_count,
        'callyzer_incoming_count': callyzer_incoming_count,
        'callyzer_outgoing_count': callyzer_outgoing_count,

        # NEW: Additional context for overview cards
        'gmail_token_count': gmail_leads_tokens,
        'google_ads_token_count': google_ads_tokens,
        'callyzer_token_count': callyzer_token_count,
        'bigin_is_connected': bigin_synced_count > 0,
        'bigin_contacts_count': bigin_contacts,
        'bigin_deals_count': bigin_deals,
        'tallysync_is_connected': tally_synced_count > 0,
        'tallysync_vouchers_count': tally_vouchers_count if 'tally_vouchers_count' in locals() else tally_invoices,
        'tallysync_invoices_count': tally_invoices,
        'adobe_sign_configured': adobe_sign_settings is not None and bool(adobe_sign_settings.integration_key) if adobe_sign_settings else False,
        'adobe_sign_agreements_count': adobe_documents_count,
        'adobe_sign_director_email': adobe_sign_settings.director_email if adobe_sign_settings else None,
        'google_ads_campaigns_count': google_ads_count,

        # Optional template variables (with defaults)
        'sync_logs': recent_syncs_detailed if 'recent_syncs_detailed' in locals() else [],
        'active_integrations_count': 6,  # Total integrations available
        'system_uptime': '99.9%',  # Can be enhanced with actual monitoring
        'gmail_api_response_time': 'N/A',  # Placeholder for future API monitoring
        'gmail_api_quota': 'N/A',
        'google_ads_api_response_time': 'N/A',
        'bigin_api_response_time': 'N/A',
        'callyzer_last_health_check': 'N/A',

        # Per-integration sync history (for live logs + history sections in each tab)
        'google_ads_recent_syncs': google_ads_recent_syncs if 'google_ads_recent_syncs' in locals() else [],
        'gmail_leads_recent_syncs': gmail_leads_recent_syncs if 'gmail_leads_recent_syncs' in locals() else [],
        'bigin_recent_syncs': bigin_recent_syncs if 'bigin_recent_syncs' in locals() else [],
        'callyzer_recent_syncs': callyzer_recent_syncs if 'callyzer_recent_syncs' in locals() else [],
        'tallysync_recent_syncs': tallysync_recent_syncs if 'tallysync_recent_syncs' in locals() else [],

        # Sync Monitor tab data
        'sync_audit_integrations': sync_audit_integrations,
        'sync_audit_total_integrations': sync_audit_total_integrations,
        'sync_audit_connected_count': sync_audit_connected_count,
        'sync_audit_syncing_count': sync_audit_syncing_count,
        'sync_audit_total_records_today': sync_audit_total_records_today,
        'sync_audit_current_time': sync_audit_current_time,
        'sync_audit_recent_batch_logs': sync_audit_recent_batch_logs,
    }

    return render(request, 'dashboards/admin/integrations.html', context)


@login_required
def integration_sync_status_api(request):
    """
    AJAX endpoint for real-time sync progress monitoring
    Returns JSON with current sync status for all integrations
    """
    from django.http import JsonResponse
    from django.core.cache import cache

    if request.user.role not in ['admin', 'director', 'super_user']:
        return JsonResponse({'error': 'Access denied'}, status=403)

    # Get running syncs from cache
    running_syncs = []

    # Check Google Ads syncs
    google_ads_sync_key = cache.get('google_ads_sync_in_progress')
    if google_ads_sync_key:
        sync_data = cache.get(google_ads_sync_key)
        if sync_data:
            running_syncs.append({
                'integration': 'google_ads',
                'integration_name': 'Google Ads',
                'status': 'running',
                'progress': sync_data.get('progress', 0),
                'current_step': sync_data.get('current_step', 'Processing...'),
                'records_synced': sync_data.get('records_synced', 0),
                'started_at': sync_data.get('started_at'),
            })

    # Check Gmail Leads syncs
    gmail_sync_key = cache.get('gmail_leads_sync_in_progress')
    if gmail_sync_key:
        sync_data = cache.get(gmail_sync_key)
        if sync_data:
            running_syncs.append({
                'integration': 'gmail_leads',
                'integration_name': 'Gmail Leads',
                'status': 'running',
                'progress': sync_data.get('progress', 0),
                'current_step': sync_data.get('current_step', 'Processing...'),
                'records_synced': sync_data.get('records_synced', 0),
                'started_at': sync_data.get('started_at'),
            })

    # Check Bigin syncs
    bigin_sync_key = cache.get('bigin_sync_in_progress')
    if bigin_sync_key:
        sync_data = cache.get(bigin_sync_key)
        if sync_data:
            running_syncs.append({
                'integration': 'bigin',
                'integration_name': 'Bigin CRM',
                'status': 'running',
                'progress': sync_data.get('progress', 0),
                'current_step': sync_data.get('current_step', 'Processing...'),
                'records_synced': sync_data.get('records_synced', 0),
                'started_at': sync_data.get('started_at'),
            })

    # Check Callyzer syncs
    callyzer_sync_key = cache.get('callyzer_sync_in_progress')
    if callyzer_sync_key:
        sync_data = cache.get(callyzer_sync_key)
        if sync_data:
            running_syncs.append({
                'integration': 'callyzer',
                'integration_name': 'Callyzer',
                'status': 'running',
                'progress': sync_data.get('progress', 0),
                'current_step': sync_data.get('current_step', 'Processing...'),
                'records_synced': sync_data.get('records_synced', 0),
                'started_at': sync_data.get('started_at'),
            })

    # Check TallySync syncs
    tally_sync_key = cache.get('tallysync_sync_in_progress')
    if tally_sync_key:
        sync_data = cache.get(tally_sync_key)
        if sync_data:
            running_syncs.append({
                'integration': 'tallysync',
                'integration_name': 'TallySync',
                'status': 'running',
                'progress': sync_data.get('progress', 0),
                'current_step': sync_data.get('current_step', 'Processing...'),
                'records_synced': sync_data.get('records_synced', 0),
                'started_at': sync_data.get('started_at'),
            })

    # Get recent completed syncs (last 10)
    from integrations.models import SyncLog
    recent_syncs = SyncLog.objects.filter(
        log_kind='batch'
    ).order_by('-started_at')[:10].values(
        'integration',
        'status',
        'total_records_synced',
        'started_at',
        'completed_at',
        'error_message'
    )

    # Calculate duration and format for JSON
    recent_syncs_list = []
    for sync in recent_syncs:
        duration_seconds = None
        if sync['started_at'] and sync['completed_at']:
            duration_seconds = int((sync['completed_at'] - sync['started_at']).total_seconds())

        recent_syncs_list.append({
            'integration': sync['integration'],
            'status': sync['status'],
            'records_synced': sync['total_records_synced'],
            'started_at': sync['started_at'].isoformat() if sync['started_at'] else None,
            'ended_at': sync['completed_at'].isoformat() if sync['completed_at'] else None,
            'duration_seconds': duration_seconds,
            'error_message': sync['error_message'],
        })

    return JsonResponse({
        'running_syncs': running_syncs,
        'recent_syncs': recent_syncs_list,
        'timestamp': timezone.now().isoformat(),
    })


@login_required
def admin_dashboard_team(request):
    """
    Admin Dashboard Team Hub
    User management, roles, and team performance
    """
    if request.user.role not in ['admin', 'director', 'super_user']:
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')

    today = timezone.now().date()

    # Users — single aggregate instead of 7 separate count queries
    _user_team_agg = User.objects.aggregate(
        total_users=Count('id'),
        active_users=Count('id', filter=Q(is_active=True)),
        admin_users=Count('id', filter=Q(role='admin', is_active=True)),
        coordinator_users=Count('id', filter=Q(role='operation_coordinator', is_active=True)),
        field_staff_users=Count('id', filter=Q(
            role__in=['operation_controller', 'finance', 'supply_manager'], is_active=True
        )),
        users_active_today=Count('id', filter=Q(last_login__date=today)),
        users_active_week=Count('id', filter=Q(last_login__gte=today - timedelta(days=7))),
    )
    total_users = _user_team_agg['total_users']
    active_users = _user_team_agg['active_users']
    inactive_users = total_users - active_users
    active_percentage = round((active_users / total_users * 100), 1) if total_users > 0 else 0
    total_roles = len(User.ROLE_CHOICES)
    admin_users = _user_team_agg['admin_users']
    coordinator_users = _user_team_agg['coordinator_users']
    field_staff_users = _user_team_agg['field_staff_users']
    users_active_today = _user_team_agg['users_active_today']
    users_active_week = _user_team_agg['users_active_week']

    # Performance
    active_projects_count = ProjectCode.objects.filter(project_status='Active').count()
    avg_workload = round(active_projects_count / coordinator_users, 1) if coordinator_users > 0 else 0

    # Top performer — batch project counts instead of N+1 per coordinator
    coordinators = User.objects.filter(role='operation_coordinator', is_active=True)
    _coord_full_names = [c.get_full_name() for c in coordinators]
    _coord_primary_counts = dict(
        ProjectCode.objects.filter(
            project_status='Active',
            operation_coordinator__in=_coord_full_names
        ).values('operation_coordinator').annotate(cnt=Count('project_id')).values_list('operation_coordinator', 'cnt')
    )
    _coord_backup_counts = dict(
        ProjectCode.objects.filter(
            project_status='Active',
            backup_coordinator__in=_coord_full_names
        ).values('backup_coordinator').annotate(cnt=Count('project_id')).values_list('backup_coordinator', 'cnt')
    )
    top_performer = None
    top_performer_projects = 0
    for coord in coordinators:
        cname = coord.get_full_name()
        proj_count = _coord_primary_counts.get(cname, 0) + _coord_backup_counts.get(cname, 0)
        if proj_count > top_performer_projects:
            top_performer = coord
            top_performer_projects = proj_count
    top_performer_name = top_performer.get_full_name() if top_performer else 'N/A'

    # Recent logins
    recent_logins = []
    recent_login_users = User.objects.filter(
        last_login__isnull=False
    ).order_by('-last_login')[:10]

    for user in recent_login_users:
        recent_logins.append({
            'initials': ''.join([n[0] for n in user.get_full_name().split()[:2]]),
            'user_name': user.get_full_name(),
            'role': dict(User.ROLE_CHOICES).get(user.role, user.role),
            'time_ago': 'Recently',
            'location': 'N/A'
        })

    # Placeholder values
    completion_rate = 85
    avg_session_time = 6.5
    passwords_expiring = 0
    locked_accounts = 0
    failed_logins = 0

    context = {
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'active_percentage': active_percentage,
        'total_roles': total_roles,
        'admin_users': admin_users,
        'coordinator_users': coordinator_users,
        'field_staff_users': field_staff_users,
        'users_active_today': users_active_today,
        'users_active_week': users_active_week,
        'avg_workload': avg_workload,
        'top_performer_name': top_performer_name,
        'top_performer_projects': top_performer_projects,
        'completion_rate': completion_rate,
        'avg_session_time': avg_session_time,
        'recent_logins': recent_logins,
        'passwords_expiring': passwords_expiring,
        'locked_accounts': locked_accounts,
        'failed_logins': failed_logins,
    }

    return render(request, 'dashboards/admin/team.html', context)


@login_required
def admin_dashboard_system(request):
    """
    Admin Dashboard System Hub
    System health, configuration, and master data management
    """
    if request.user.role not in ['admin', 'director', 'super_user']:
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')

    from accounts.models import ErrorLog
    from django.utils import timezone as tz
    from django.db import connection as db_conn
    from django.core.cache import cache
    from integrations.models import SyncLog

    _today = tz.now().date()

    # --- Database health check ---
    try:
        with db_conn.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_healthy = True
        system_status = 'Healthy'
    except Exception:
        db_healthy = False
        system_status = 'Degraded'

    # --- Error logs (real) ---
    critical_errors = ErrorLog.objects.filter(resolved=False).count()
    warnings = ErrorLog.objects.filter(timestamp__date=_today).count()
    info_logs = ErrorLog.objects.count()

    # --- Active background syncs (from cache progress keys) ---
    active_sync_keys = [
        'gmail_leads_sync_progress',
        'google_ads_sync_progress',
        'bigin_sync_progress',
        'callyzer_sync_progress',
        'tally_sync_progress',
    ]
    active_jobs = sum(1 for k in active_sync_keys if cache.get(k) is not None)
    pending_jobs = 0

    # --- Recent sync activity from SyncLog ---
    recent_syncs = SyncLog.objects.filter(
        log_kind='batch'
    ).order_by('-started_at')[:10]

    total_syncs = SyncLog.objects.filter(log_kind='batch').count()
    successful_syncs = SyncLog.objects.filter(
        log_kind='batch', status='completed'
    ).count()
    api_health = round((successful_syncs / total_syncs * 100), 1) if total_syncs > 0 else 100.0

    # Total records synced across all integrations
    from django.db.models import Sum as DbSum
    total_records_synced = SyncLog.objects.filter(
        log_kind='batch'
    ).aggregate(total=DbSum('total_records_synced'))['total'] or 0

    # --- Master data (real) ---
    try:
        from dropdown_master_data.models import MasterDropdown
        total_masters = MasterDropdown.objects.count()
        active_master_entries = MasterDropdown.objects.filter(is_active=True).count()
        last_master = MasterDropdown.objects.order_by('-updated_at').first()
        master_last_updated = last_master.updated_at.strftime('%b %d') if last_master else 'N/A'
    except Exception:
        total_masters = 0
        active_master_entries = 0
        master_last_updated = 'N/A'

    # --- GCS storage stats (cached for 1 hour — expensive to iterate) ---
    gcs_cache_key = 'admin_dashboard_gcs_stats'
    gcs_stats = cache.get(gcs_cache_key)

    if gcs_stats is None:
        # Cache miss — compute GCS stats
        gcs_total_files = 0
        gcs_used_bytes = 0
        gcs_bucket_name = ''
        gcs_bucket_location = ''
        gcs_storage_class = ''
        gcs_error = None
        try:
            from django.conf import settings as dj_settings
            if getattr(dj_settings, 'GS_BUCKET_NAME', None):
                from google.cloud import storage as gcs_storage
                gcs_client = gcs_storage.Client(
                    project=getattr(dj_settings, 'GS_PROJECT_ID', None),
                    credentials=getattr(dj_settings, 'GS_CREDENTIALS', None),
                )
                gcs_bucket_name = dj_settings.GS_BUCKET_NAME
                bucket_obj = gcs_client.bucket(gcs_bucket_name)
                try:
                    bucket_obj.reload()  # Fetch metadata (needs storage.buckets.get)
                    gcs_bucket_location = bucket_obj.location or ''
                    gcs_storage_class = bucket_obj.storage_class or ''
                except Exception:
                    gcs_bucket_location = ''
                    gcs_storage_class = ''
                for blob in gcs_client.list_blobs(gcs_bucket_name):
                    gcs_total_files += 1
                    gcs_used_bytes += blob.size or 0
            else:
                gcs_error = 'local'
        except Exception as _e:
            gcs_error = str(_e)

        gcs_used_gb = round(gcs_used_bytes / (1024 ** 3), 3)
        gcs_used_mb = round(gcs_used_bytes / (1024 ** 2), 1)
        # Human-readable size
        if gcs_used_bytes >= 1024 ** 3:
            gcs_used_display = f"{gcs_used_gb} GB"
        else:
            gcs_used_display = f"{gcs_used_mb} MB"

        # Cache for 1 hour (3600 seconds)
        gcs_stats = {
            'gcs_total_files': gcs_total_files,
            'gcs_used_bytes': gcs_used_bytes,
            'gcs_bucket_name': gcs_bucket_name,
            'gcs_bucket_location': gcs_bucket_location,
            'gcs_storage_class': gcs_storage_class,
            'gcs_error': gcs_error,
            'gcs_used_gb': gcs_used_gb,
            'gcs_used_mb': gcs_used_mb,
            'gcs_used_display': gcs_used_display,
        }
        cache.set(gcs_cache_key, gcs_stats, 3600)
    else:
        # Cache hit — extract values
        gcs_total_files = gcs_stats['gcs_total_files']
        gcs_used_bytes = gcs_stats['gcs_used_bytes']
        gcs_bucket_name = gcs_stats['gcs_bucket_name']
        gcs_bucket_location = gcs_stats['gcs_bucket_location']
        gcs_storage_class = gcs_stats['gcs_storage_class']
        gcs_error = gcs_stats['gcs_error']
        gcs_used_gb = gcs_stats['gcs_used_gb']
        gcs_used_mb = gcs_stats['gcs_used_mb']
        gcs_used_display = gcs_stats['gcs_used_display']

    # Legacy fallback for template vars
    total_files = gcs_total_files
    storage_used = gcs_used_gb
    files_uploaded_today = 0

    # --- Cloud Run / system monitoring (not available — show N/A) ---
    cpu_usage = 'N/A'
    memory_usage = 'N/A'
    disk_usage = 'N/A'

    # --- Backups (config-driven) ---
    import os
    backup_frequency = os.environ.get('BACKUP_FREQUENCY', 'Daily')
    backup_retention = os.environ.get('BACKUP_RETENTION', '30 days')
    last_backup_time = 'Managed by Cloud SQL'
    last_backup_size = 'See Cloud Console'
    last_backup_hours = 'Auto'
    db_size = 'N/A'
    db_growth = 'N/A'
    db_connections = 'N/A'
    avg_query_time = 'N/A'
    uptime = '99.9%'
    response_time = 'N/A'

    context = {
        'system_status': system_status,
        'db_healthy': db_healthy,
        'uptime': uptime,
        'db_size': db_size,
        'db_growth': db_growth,
        'active_jobs': active_jobs,
        'pending_jobs': pending_jobs,
        'api_health': api_health,
        'response_time': response_time,
        'total_masters': total_masters,
        'active_master_entries': active_master_entries,
        'master_last_updated': master_last_updated,
        'total_files': total_files,
        'storage_used': storage_used,
        'files_uploaded_today': files_uploaded_today,
        'gcs_used_display': gcs_used_display,
        'gcs_used_gb': gcs_used_gb,
        'gcs_bucket_name': gcs_bucket_name,
        'gcs_bucket_location': gcs_bucket_location,
        'gcs_storage_class': gcs_storage_class,
        'gcs_error': gcs_error,
        'db_connections': db_connections,
        'avg_query_time': avg_query_time,
        'last_backup_hours': last_backup_hours,
        'critical_errors': critical_errors,
        'warnings': warnings,
        'info_logs': info_logs,
        'cpu_usage': cpu_usage,
        'memory_usage': memory_usage,
        'disk_usage': disk_usage,
        'last_backup_time': last_backup_time,
        'last_backup_size': last_backup_size,
        'backup_frequency': backup_frequency,
        'backup_retention': backup_retention,
        'recent_syncs': recent_syncs,
        'total_records_synced': total_records_synced,
        'total_syncs': total_syncs,
        'successful_syncs': successful_syncs,
    }

    return render(request, 'dashboards/admin/system.html', context)


@login_required
def admin_file_manager(request):
    """
    Enhanced File Manager - Browse all uploaded files across the entire system
    Shows files from projects, operations, supply chain, clients with filtering and search
    Access: Admin only
    """
    from django.core.paginator import Paginator
    from django.conf import settings
    import os

    # Check permissions
    if request.user.role not in ['admin', 'director']:
        messages.error(request, "Access denied. Admin or Director access required.")
        return redirect('accounts:dashboard')

    # Determine if using local or cloud storage
    storage_backend = settings.STORAGES.get('default', {}).get('BACKEND', '')
    is_local = 'FileSystemStorage' in storage_backend

    # Collect all files from different models
    all_files = []

    # Helper function to add files
    def add_file_info(file_field, category, uploader=None, related_obj=None, related_type=None, attachment_type=None):
        if file_field and file_field.name:
            try:
                file_size = file_field.size if hasattr(file_field, 'size') else 0
                file_url = file_field.url if hasattr(file_field, 'url') else ''

                # Get file extension and type
                file_extension = os.path.splitext(file_field.name)[1].lower()
                if file_extension in ['.pdf']:
                    file_type = 'PDF Document'
                elif file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                    file_type = 'Image'
                elif file_extension in ['.doc', '.docx']:
                    file_type = 'Word Document'
                elif file_extension in ['.xls', '.xlsx']:
                    file_type = 'Excel Spreadsheet'
                elif file_extension in ['.mp4', '.avi', '.mov']:
                    file_type = 'Video'
                else:
                    file_type = 'Other'

                # Format file size
                if file_size < 1024:
                    size_display = f"{file_size} B"
                elif file_size < 1024 * 1024:
                    size_display = f"{file_size / 1024:.1f} KB"
                else:
                    size_display = f"{file_size / (1024 * 1024):.2f} MB"

                # Get display name (last part of path)
                display_name = os.path.basename(file_field.name)
                path = os.path.dirname(file_field.name)

                # Get created datetime and ensure it's timezone-aware
                created_dt = getattr(related_obj, 'created_at', None) or getattr(related_obj, 'uploaded_at', None) or timezone.now()
                if created_dt and timezone.is_naive(created_dt):
                    created_dt = timezone.make_aware(created_dt)

                # Get updated datetime and ensure it's timezone-aware
                updated_dt = getattr(related_obj, 'updated_at', None) or timezone.now()
                if updated_dt and timezone.is_naive(updated_dt):
                    updated_dt = timezone.make_aware(updated_dt)

                all_files.append({
                    'name': file_field.name,
                    'display_name': display_name,
                    'path': path,
                    'category': category,
                    'type': file_type,
                    'size': file_size,
                    'size_display': size_display,
                    'url': file_url,
                    'uploader': uploader or 'Unknown',
                    'created': created_dt,
                    'updated': updated_dt,
                    'related_record': {
                        'type': related_type,
                        'project_code': getattr(related_obj, 'project_id', None) or getattr(related_obj, 'project_code', None),
                        'attachment_type': attachment_type
                    } if related_obj else None
                })
            except Exception as e:
                pass  # Skip files that can't be accessed

    # 1. Project Documents
    from projects.models_document import ProjectDocument
    for doc in ProjectDocument.objects.select_related('project').all():
        if doc.project_agreement:
            add_file_info(doc.project_agreement, 'Project Documents', related_obj=doc.project, related_type='Project', attachment_type='Agreement')
        if doc.project_addendum_vendor:
            add_file_info(doc.project_addendum_vendor, 'Project Documents', related_obj=doc.project, related_type='Project', attachment_type='Vendor Addendum')
        if doc.project_addendum_client:
            add_file_info(doc.project_addendum_client, 'Project Documents', related_obj=doc.project, related_type='Project', attachment_type='Client Addendum')
        if doc.project_handover:
            add_file_info(doc.project_handover, 'Project Documents', related_obj=doc.project, related_type='Project', attachment_type='Handover')

    # 2. Client Documents
    from projects.models_client import ClientDocument
    for doc in ClientDocument.objects.select_related('client_code').all():
        if doc.client_doc_certificate_of_incorporation:
            add_file_info(doc.client_doc_certificate_of_incorporation, 'Client Documents', related_obj=doc.client_code, related_type='Client', attachment_type='Certificate of Incorporation')
        if doc.client_doc_board_resolution:
            add_file_info(doc.client_doc_board_resolution, 'Client Documents', related_obj=doc.client_code, related_type='Client', attachment_type='Board Resolution')
        if doc.client_doc_authorized_signatory:
            add_file_info(doc.client_doc_authorized_signatory, 'Client Documents', related_obj=doc.client_code, related_type='Client', attachment_type='Authorized Signatory')

    # 3. Monthly Billing Documents (files are directly on MonthlyBilling model)
    from operations.models import MonthlyBilling
    for billing in MonthlyBilling.objects.select_related('project').all():
        if billing.mis_document:
            add_file_info(billing.mis_document, 'Monthly Billing',
                         related_obj=billing, related_type='Monthly Billing', attachment_type='MIS Document')
        if billing.transport_document:
            add_file_info(billing.transport_document, 'Monthly Billing',
                         related_obj=billing, related_type='Monthly Billing', attachment_type='Transport Document')
        if billing.other_document:
            add_file_info(billing.other_document, 'Monthly Billing',
                         related_obj=billing, related_type='Monthly Billing', attachment_type='Other Document')

    # 4. Dispute Comment Attachments
    from operations.models import DisputeComment
    for comment in DisputeComment.objects.select_related('user', 'dispute').all():
        if comment.attachment:
            add_file_info(comment.attachment, 'Dispute Attachments', uploader=str(comment.user) if comment.user else None,
                         related_obj=comment, related_type='Dispute', attachment_type='Comment Attachment')

    # 5. Adhoc Billing Attachments
    from operations.models_adhoc import AdhocBillingAttachment
    for attachment in AdhocBillingAttachment.objects.select_related('entry', 'entry__project', 'uploaded_by').all():
        add_file_info(attachment.file, 'Adhoc Billing', uploader=str(attachment.uploaded_by) if attachment.uploaded_by else None,
                     related_obj=attachment.entry, related_type='Adhoc Billing', attachment_type=attachment.get_attachment_type_display())

    # 6. Warehouse Documents
    from supply.models import VendorWarehouseDocument
    for doc in VendorWarehouseDocument.objects.select_related('warehouse_code', 'vendor_code').all():
        add_file_info(doc.warehouse_electricity_bill, 'Warehouse Documents', related_obj=doc.warehouse_code, related_type='Warehouse', attachment_type='Electricity Bill')
        add_file_info(doc.warehouse_property_tax_receipt, 'Warehouse Documents', related_obj=doc.warehouse_code, related_type='Warehouse', attachment_type='Property Tax Receipt')
        add_file_info(doc.warehouse_poc_aadhar, 'Warehouse Documents', related_obj=doc.warehouse_code, related_type='Warehouse', attachment_type='POC Aadhar')
        add_file_info(doc.warehouse_poc_pan, 'Warehouse Documents', related_obj=doc.warehouse_code, related_type='Warehouse', attachment_type='POC PAN')
        add_file_info(doc.warehouse_noc_owner, 'Warehouse Documents', related_obj=doc.warehouse_code, related_type='Warehouse', attachment_type='NOC Owner')
        add_file_info(doc.warehouse_owner_pan, 'Warehouse Documents', related_obj=doc.warehouse_code, related_type='Warehouse', attachment_type='Owner PAN')
        add_file_info(doc.warehouse_owner_aadhar, 'Warehouse Documents', related_obj=doc.warehouse_code, related_type='Warehouse', attachment_type='Owner Aadhar')

    # 7. Warehouse Photos
    from supply.models import WarehousePhoto
    for photo in WarehousePhoto.objects.select_related('warehouse_code', 'uploaded_by').all():
        if photo.file:
            add_file_info(photo.file, 'Warehouse Photos', uploader=str(photo.uploaded_by) if photo.uploaded_by else None,
                         related_obj=photo.warehouse_code, related_type='Warehouse', attachment_type=photo.file_type)

    # Filter by category
    category_filter = request.GET.get('category', '').strip()
    if category_filter:
        all_files = [f for f in all_files if f['category'] == category_filter]

    # Filter by type
    type_filter = request.GET.get('type', '').strip()
    if type_filter:
        all_files = [f for f in all_files if f['type'] == type_filter]

    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        all_files = [f for f in all_files if
                     search_query.lower() in f['display_name'].lower() or
                     search_query.lower() in f['category'].lower() or
                     (f['related_record'] and f['related_record'].get('project_code') and
                      search_query.lower() in str(f['related_record']['project_code']).lower())]

    # Sort files by created date (newest first)
    all_files.sort(key=lambda x: x['created'], reverse=True)

    # Calculate statistics
    total_files = len(all_files)
    total_size = sum(f['size'] for f in all_files)
    total_size_mb = round(total_size / (1024 * 1024), 2) if total_size > 0 else 0
    total_size_gb = round(total_size / (1024 * 1024 * 1024), 2) if total_size > 0 else 0

    # Calculate by category
    by_category = {}
    for file in all_files:
        cat = file['category']
        if cat not in by_category:
            by_category[cat] = {'count': 0, 'size': 0}
        by_category[cat]['count'] += 1
        by_category[cat]['size'] += file['size']

    stats = {
        'total_files': total_files,
        'total_size_mb': total_size_mb,
        'total_size_gb': total_size_gb,
        'by_category': by_category
    }

    # Pagination
    paginator = Paginator(all_files, 50)  # 50 files per page
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)

    # Get unique categories and types for filters
    all_categories = sorted(set(f['category'] for f in all_files))
    all_types = sorted(set(f['type'] for f in all_files))

    # --- GCS bucket metadata (location, storage class, bucket name) ---
    gcs_bucket_name = ''
    gcs_bucket_location = ''
    gcs_storage_class = ''
    gcs_error = None
    if not is_local:
        try:
            from google.cloud import storage as gcs_storage
            _gcs_client = gcs_storage.Client(
                project=getattr(settings, 'GS_PROJECT_ID', None),
                credentials=getattr(settings, 'GS_CREDENTIALS', None),
            )
            gcs_bucket_name = getattr(settings, 'GS_BUCKET_NAME', '')
            _bucket_obj = _gcs_client.bucket(gcs_bucket_name)
            try:
                _bucket_obj.reload()  # Fetch metadata (needs storage.buckets.get)
                gcs_bucket_location = _bucket_obj.location or ''
                gcs_storage_class = _bucket_obj.storage_class or ''
            except Exception:
                gcs_bucket_location = ''
                gcs_storage_class = ''
        except Exception as _e:
            gcs_error = str(_e)

    context = {
        'page_obj': page_obj,
        'stats': stats,
        'is_local': is_local,
        'all_categories': all_categories,
        'all_types': all_types,
        'category_filter': category_filter,
        'type_filter': type_filter,
        'search_query': search_query,
        'gcs_bucket_name': gcs_bucket_name,
        'gcs_bucket_location': gcs_bucket_location,
        'gcs_storage_class': gcs_storage_class,
        'gcs_error': gcs_error,
    }

    return render(request, 'dashboards/admin/file_manager.html', context)