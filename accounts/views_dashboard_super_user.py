"""
Super User Dashboard View
Advanced dashboard with elevated permissions but not full admin access
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Q
from collections import defaultdict

from accounts.models import User
from projects.models import ProjectCode
from operations.models import DailySpaceUtilization
from operations.models_adhoc import AdhocBillingEntry
from operations.models_projectcard import ProjectCard


@login_required
def super_user_dashboard(request):
    """
    Super User Dashboard
    Access: Super User role only
    Features: Project oversight, operational metrics, limited financial data
    """
    # Check permissions
    if request.user.role not in ['super_user', 'admin']:
        messages.error(request, "Access denied. Super User access required.")
        return redirect('accounts:dashboard')
    
    # Get current date context
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)
    
    # ==================== KPI CARDS ====================
    
    # Projects
    total_projects = ProjectCode.objects.count()
    active_projects = ProjectCode.objects.filter(project_status='Active').count()
    notice_period_projects = ProjectCode.objects.filter(project_status='Notice Period').count()
    inactive_projects = ProjectCode.objects.filter(project_status='Inactive').count()
    
    # Projects added this month
    projects_added_this_month = ProjectCode.objects.filter(
        created_at__gte=current_month_start
    ).count()
    
    # Growth calculation
    projects_last_month = ProjectCode.objects.filter(
        created_at__gte=last_month_start,
        created_at__lte=last_month_end
    ).count()
    
    if projects_last_month > 0:
        projects_growth = round(
            ((projects_added_this_month - projects_last_month) / projects_last_month) * 100, 
            1
        )
    else:
        projects_growth = 0
    
    active_percentage = round((active_projects / total_projects * 100), 1) if total_projects > 0 else 0
    
    # Users
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    
    # ==================== ALERTS ====================
    
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
    
    # Missing daily entries today
    try:
        entries_today = DailySpaceUtilization.objects.filter(
            entry_date=today
        ).values('project_id').distinct().count()
        missing_daily_entries = max(0, active_projects - entries_today)
    except:
        missing_daily_entries = 0
    
    # Adhoc billing pending > 30 days
    adhoc_pending_old = AdhocBillingEntry.objects.filter(
        status='pending',
        event_date__lt=today - timedelta(days=30)
    ).count()
    
    total_alerts = (
        projects_without_id + 
        incomplete_project_cards + 
        missing_daily_entries + 
        adhoc_pending_old
    )
    
    # ==================== PROJECTS OVERVIEW ====================
    
    # Status Distribution
    active_percentage_calc = round((active_projects / total_projects * 100), 1) if total_projects > 0 else 0
    notice_percentage = round((notice_period_projects / total_projects * 100), 1) if total_projects > 0 else 0
    inactive_percentage = round((inactive_projects / total_projects * 100), 1) if total_projects > 0 else 0
    
    # Series Distribution
    waas_projects = ProjectCode.objects.filter(series_type='WAAS').count()
    saas_projects = ProjectCode.objects.filter(series_type='SAAS').count()
    gw_projects = ProjectCode.objects.filter(series_type='GW').count()
    
    # Top States
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
    
    # Top Clients
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
    
    # ==================== OPERATIONS OVERVIEW ====================
    
    # Daily Entries Status
    try:
        daily_entries_today = DailySpaceUtilization.objects.filter(
            entry_date=today
        ).values('project_id').distinct().count()
        
        daily_entries_pending = active_projects - daily_entries_today
        
        daily_entries_completion = round(
            (daily_entries_today / active_projects * 100), 1
        ) if active_projects > 0 else 0
        
        # Monthly entries
        daily_entries_month = DailySpaceUtilization.objects.filter(
            entry_date__gte=current_month_start
        ).count()
        
        # Calculate working days
        working_days = 0
        current_date = current_month_start
        while current_date <= today:
            if current_date.weekday() != 6:  # Not Sunday
                working_days += 1
            current_date += timedelta(days=1)
        
        expected_entries = active_projects * working_days
        monthly_completion = round(
            (daily_entries_month / expected_entries * 100), 1
        ) if expected_entries > 0 else 0
        
    except:
        daily_entries_today = 0
        daily_entries_pending = 0
        daily_entries_completion = 0
        daily_entries_month = 0
        working_days = 0
        monthly_completion = 0
    
    # Adhoc Billing
    adhoc_pending = AdhocBillingEntry.objects.filter(status='pending').count()
    adhoc_approved_month = AdhocBillingEntry.objects.filter(
        status__in=['approved', 'billed'],
        event_date__gte=current_month_start
    ).count()
    
    # Adhoc amount (limited visibility for super_user)
    adhoc_pending_amount = AdhocBillingEntry.objects.filter(
        status='pending'
    ).aggregate(total=Sum('total_client_amount'))['total'] or 0
    adhoc_pending_amount = float(adhoc_pending_amount) / 100000
    
    # ==================== TEAM OVERVIEW ====================
    
    # Users by Role
    users_by_role = User.objects.values('role').annotate(
        count=Count('id'),
        active=Count('id', filter=Q(is_active=True))
    ).order_by('-count')[:5]
    
    users_by_role_list = []
    for role_data in users_by_role:
        role_display = dict(User.ROLE_CHOICES).get(role_data['role'], role_data['role'])
        users_by_role_list.append({
            'role': role_data['role'],
            'role_display': role_display,
            'count': role_data['count'],
            'active': role_data['active']
        })
    
    # Coordinator Workload (2 batch queries instead of N+1)
    coordinators = User.objects.filter(
        role='operation_coordinator',
        is_active=True
    )[:5]
    _su_coord_names = {c.get_full_name(): c for c in coordinators}

    # Single batch query for all coordinator project counts
    _su_proj_rows = ProjectCode.objects.filter(
        Q(operation_coordinator__in=_su_coord_names.keys()) | Q(backup_coordinator__in=_su_coord_names.keys()),
        project_status='Active'
    ).values_list('operation_coordinator', 'backup_coordinator')

    _su_coord_counts = defaultdict(int)
    for op_c, bk_c in _su_proj_rows:
        if op_c in _su_coord_names:
            _su_coord_counts[op_c] += 1
        if bk_c in _su_coord_names:
            _su_coord_counts[bk_c] += 1

    coordinator_workload = [
        {'name': name, 'projects': _su_coord_counts.get(name, 0)}
        for name in _su_coord_names
    ]
    
    # ==================== DATA QUALITY ====================
    
    # Projects with complete data
    projects_with_id = ProjectCode.objects.exclude(
        Q(project_id__isnull=True) | Q(project_id='')
    ).count()
    
    projects_with_id_percentage = round(
        (projects_with_id / total_projects * 100), 1
    ) if total_projects > 0 else 0
    
    # Project cards completeness
    total_project_cards = ProjectCard.objects.count()
    complete_cards = ProjectCard.objects.filter(
        agreement_start_date__isnull=False,
        agreement_end_date__isnull=False,
        billing_start_date__isnull=False
    ).count()
    
    complete_cards_percentage = round(
        (complete_cards / total_project_cards * 100), 1
    ) if total_project_cards > 0 else 0
    
    # Overall data quality score
    data_quality_score = round(
        (projects_with_id_percentage + complete_cards_percentage) / 2, 1
    )
    
    # ==================== CONTEXT ====================
    
    context = {
        # Date
        'today': today,
        'current_time': timezone.now().strftime('%I:%M %p'),
        
        # KPIs
        'total_projects': total_projects,
        'active_projects': active_projects,
        'active_percentage': active_percentage,
        'notice_period_projects': notice_period_projects,
        'inactive_projects': inactive_projects,
        'projects_added_this_month': projects_added_this_month,
        'projects_growth': projects_growth,
        'total_users': total_users,
        'active_users': active_users,
        
        # Alerts
        'total_alerts': total_alerts,
        'projects_without_id': projects_without_id,
        'incomplete_project_cards': incomplete_project_cards,
        'missing_daily_entries': missing_daily_entries,
        'adhoc_pending_old': adhoc_pending_old,
        
        # Projects
        'active_percentage_calc': active_percentage_calc,
        'notice_percentage': notice_percentage,
        'inactive_percentage': inactive_percentage,
        'waas_projects': waas_projects,
        'saas_projects': saas_projects,
        'gw_projects': gw_projects,
        'top_states': top_states_list,
        'top_clients': top_clients_list,
        
        # Operations
        'daily_entries_today': daily_entries_today,
        'daily_entries_pending': daily_entries_pending,
        'daily_entries_completion': daily_entries_completion,
        'daily_entries_month': daily_entries_month,
        'working_days': working_days,
        'monthly_completion': monthly_completion,
        'adhoc_pending': adhoc_pending,
        'adhoc_approved_month': adhoc_approved_month,
        'adhoc_pending_amount': adhoc_pending_amount,
        
        # Team
        'users_by_role': users_by_role_list,
        'coordinator_workload': coordinator_workload,
        
        # Data Quality
        'projects_with_id': projects_with_id,
        'projects_with_id_percentage': projects_with_id_percentage,
        'total_project_cards': total_project_cards,
        'complete_cards': complete_cards,
        'complete_cards_percentage': complete_cards_percentage,
        'data_quality_score': data_quality_score,
    }
    
    return render(request, 'dashboards/super_user_dashboard.html', context)