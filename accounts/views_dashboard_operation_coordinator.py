"""
Operation Coordinator Dashboard View
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Q

from accounts.models import User
from projects.models import ProjectCode
from operations.models import DailySpaceUtilization, DisputeLog, MonthlyBilling
from operations.models_adhoc import AdhocBillingEntry
from operations.models_projectcard import ProjectCard


@login_required
def operation_coordinator_dashboard(request):
    """
    Operation Coordinator Dashboard
    Focused on coordinator's assigned projects and daily operational tasks
    """
    # Role check
    if request.user.role not in ['operation_coordinator', 'operation_manager', 'operation_controller', 'admin', 'director']:
        messages.error(request, "Access denied. Operation Coordinator access required.")
        return redirect('accounts:dashboard')
    
    # Date context
    today = timezone.now().date()
    current_month_start = today.replace(day=1)

    # Previous month for billing (service month = when services were provided)
    previous_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    
    # Get coordinator name
    coordinator_name = request.user.get_full_name()
    
    # ==================== MY PROJECTS ====================
    
    # Projects assigned to this coordinator
    my_projects = ProjectCode.objects.filter(
        Q(operation_coordinator=coordinator_name) | Q(backup_coordinator=coordinator_name)
    )
    
    # Project counts by status
    total_my_projects = my_projects.count()
    active_projects = my_projects.filter(project_status='Active').count()
    notice_period_projects = my_projects.filter(project_status='Notice Period').count()
    not_started_projects = my_projects.filter(project_status='Operation Not Started').count()
    inactive_projects = my_projects.filter(project_status='Inactive').count()
    
    # ==================== DAILY ENTRIES ====================
    
    # Today's entries for my projects
    my_active_projects = my_projects.filter(project_status='Active')
    
    entries_today = DailySpaceUtilization.objects.filter(
        project__in=my_active_projects,
        entry_date=today
    ).values('project_id').distinct().count()
    
    entries_pending_today = active_projects - entries_today
    
    completion_rate_today = round(
        (entries_today / active_projects * 100), 1
    ) if active_projects > 0 else 0
    
    # This week's entries
    week_start = today - timedelta(days=today.weekday())
    
    entries_this_week = DailySpaceUtilization.objects.filter(
        project__in=my_active_projects,
        entry_date__gte=week_start,
        entry_date__lte=today
    ).count()
    
    # Calculate working days in week
    working_days_week = 0
    current_date = week_start
    while current_date <= today:
        if current_date.weekday() != 6:  # Not Sunday
            working_days_week += 1
        current_date += timedelta(days=1)
    
    expected_entries_week = active_projects * working_days_week
    weekly_completion_rate = round(
        (entries_this_week / expected_entries_week * 100), 1
    ) if expected_entries_week > 0 else 0
    
    # This month's entries
    entries_this_month = DailySpaceUtilization.objects.filter(
        project__in=my_active_projects,
        entry_date__gte=current_month_start,
        entry_date__lte=today
    ).count()
    
    # Calculate working days in month
    working_days_month = 0
    current_date = current_month_start
    while current_date <= today:
        if current_date.weekday() != 6:  # Not Sunday
            working_days_month += 1
        current_date += timedelta(days=1)
    
    expected_entries_month = active_projects * working_days_month
    monthly_completion_rate = round(
        (entries_this_month / expected_entries_month * 100), 1
    ) if expected_entries_month > 0 else 0
    
    # ==================== PROJECTS NEEDING ATTENTION ====================
    
    # Projects without entries today
    projects_without_entry_today = my_active_projects.exclude(
        project_id__in=DailySpaceUtilization.objects.filter(
            entry_date=today
        ).values_list('project_id', flat=True)
    )
    
    projects_needing_entry = []
    for project in projects_without_entry_today[:10]:
        projects_needing_entry.append({
            'project_id': project.project_id,
            'client_name': project.client_name,
            'warehouse_location': project.location,
            'state': project.state
        })
    
    # ==================== MY PROJECT DETAILS ====================
    
    # Projects by series
    waas_projects = my_projects.filter(series_type='WAAS').count()
    saas_projects = my_projects.filter(series_type='SAAS').count()
    gw_projects = my_projects.filter(series_type='GW').count()
    
    # Projects by state
    projects_by_state = my_projects.values('state').annotate(
        count=Count('project_id')
    ).order_by('-count')[:5]
    
    state_distribution = []
    for state in projects_by_state:
        state_distribution.append({
            'state': state['state'],
            'count': state['count']
        })
    
    # ==================== ADHOC BILLING (MY PROJECTS) ====================
    
    # Adhoc entries for my projects
    my_adhoc_pending = AdhocBillingEntry.objects.filter(
        project__in=my_projects,
        status='pending'
    ).count()
    
    my_adhoc_approved_month = AdhocBillingEntry.objects.filter(
        project__in=my_projects,
        status='approved',
        event_date__gte=current_month_start
    ).count()
    
    # Recent adhoc entries
    recent_adhoc = AdhocBillingEntry.objects.filter(
        project__in=my_projects
    ).select_related('project', 'status').order_by('-created_at')[:5]

    recent_adhoc_list = []
    for adhoc in recent_adhoc:
        recent_adhoc_list.append({
            'id': adhoc.id,
            'project': adhoc.project,
            'project_code': adhoc.project.project_code if adhoc.project else 'N/A',
            'event_date': adhoc.event_date,
            'status': adhoc.status,  # Pass the full status object, not just the code
            'total_client_amount': adhoc.total_client_amount or 0,
        })

    # Adhoc amounts for stats (1 aggregate query instead of 4 queries + Python iteration)
    _adhoc_agg = AdhocBillingEntry.objects.filter(
        project__in=my_projects,
    ).aggregate(
        pending_count=Count('id', filter=Q(status__code='pending')),
        pending_amount=Sum('total_client_amount', filter=Q(status__code='pending')),
        billed_count=Count('id', filter=Q(status__code='billed', event_date__gte=current_month_start)),
        billed_amount=Sum('total_client_amount', filter=Q(status__code='billed', event_date__gte=current_month_start)),
    )
    my_pending_adhoc_count = _adhoc_agg['pending_count']
    my_pending_adhoc_amount = _adhoc_agg['pending_amount'] or 0
    my_billed_adhoc_count = _adhoc_agg['billed_count']
    my_billed_adhoc_amount = _adhoc_agg['billed_amount'] or 0

    # ==================== DISPUTES (MY PROJECTS) ====================

    # My disputes counts
    my_open_disputes = DisputeLog.objects.filter(
        project__in=my_projects,
        status__code='open'
    ).count()

    my_resolved_disputes = DisputeLog.objects.filter(
        project__in=my_projects,
        status__code='resolved'
    ).count()

    # Recent disputes
    recent_disputes_qs = DisputeLog.objects.filter(
        project__in=my_projects
    ).select_related('project', 'status').order_by('-raised_at')[:5]

    recent_disputes = []
    for dispute in recent_disputes_qs:
        days_open = (today - dispute.raised_at.date()).days if dispute.raised_at else 0
        recent_disputes.append({
            'dispute_id': dispute.dispute_id,
            'title': dispute.title,
            'project': dispute.project,
            'status': dispute.status,  # Pass the full status object, not just the code
            'days_open': days_open,
        })

    # ==================== MONTHLY BILLING (MY PROJECTS) ====================

    # Current billing month (use previous month for service month)
    current_billing_month = previous_month_start

    # Monthly billing counts by status
    my_monthly_billings = MonthlyBilling.objects.filter(
        project__in=my_projects,
        service_month=previous_month_start
    )

    billing_draft_count = my_monthly_billings.filter(status__code='draft').count()
    billing_submitted_count = my_monthly_billings.filter(
        status__code__in=['pending_controller', 'pending_finance']
    ).count()
    billing_approved_count = my_monthly_billings.filter(status__code='approved').count()

    # Projects without billing this month
    projects_with_billing = my_monthly_billings.values_list('project_id', flat=True)
    billing_missing_projects = my_active_projects.exclude(project_id__in=projects_with_billing)

    # Pending count for top card
    billing_pending_count = billing_missing_projects.count()

    # Recent billings
    recent_billings = my_monthly_billings.select_related('project', 'status').order_by('-created_at')[:5]

    # ==================== MIS PENDING ====================

    # MIS pending count (placeholder - implement based on your MIS tracking logic)
    # For now, using a simple heuristic: projects that need entries today
    mis_pending_count = entries_pending_today

    # ==================== PROJECT HEALTH OVERVIEW (4 batch queries instead of 4N) ====================

    _health_projects = list(my_active_projects[:10])  # Limit to top 10 for performance
    _health_pids = [p.project_id for p in _health_projects]

    # Batch query 1: last entry date per project
    from django.db.models import Max
    _last_entries = dict(
        DailySpaceUtilization.objects.filter(
            project_id__in=_health_pids
        ).values('project_id').annotate(last_date=Max('entry_date')).values_list('project_id', 'last_date')
    )

    # Batch query 2: open disputes count per project
    _dispute_counts = dict(
        DisputeLog.objects.filter(
            project_id__in=_health_pids,
            status__code='open'
        ).values('project_id').annotate(cnt=Count('dispute_id')).values_list('project_id', 'cnt')
    )

    # Batch query 3: pending adhoc amount per project
    _adhoc_amounts = dict(
        AdhocBillingEntry.objects.filter(
            project_id__in=_health_pids,
            status__code='pending'
        ).values('project_id').annotate(total=Sum('total_client_amount')).values_list('project_id', 'total')
    )

    # Batch query 4: billing status per project for previous month
    _billing_map = {}
    for b in MonthlyBilling.objects.filter(
        project_id__in=_health_pids,
        service_month=previous_month_start
    ).select_related('status'):
        _billing_map[b.project_id] = b

    projects_by_health = []
    for project in _health_projects:
        pid = project.project_id
        last_entry_date = _last_entries.get(pid)
        days_since_entry = (today - last_entry_date).days if last_entry_date else 999
        open_disputes = _dispute_counts.get(pid, 0)
        pending_adhoc = _adhoc_amounts.get(pid, 0) or 0
        billing = _billing_map.get(pid)
        billing_status = billing.status.code if billing and hasattr(billing, 'status') and billing.status else None
        billing_status_display = billing.status.label if billing and hasattr(billing, 'status') and billing.status else None

        # Health score calculation (same logic, no changes)
        health_score = 100
        if days_since_entry > 7:
            health_score -= 40
        elif days_since_entry > 3:
            health_score -= 20
        elif days_since_entry > 1:
            health_score -= 10

        if open_disputes > 0:
            health_score -= (open_disputes * 10)

        if pending_adhoc > 0:
            health_score -= 10

        if not billing_status:
            health_score -= 20

        health_score = max(0, health_score)  # Ensure non-negative

        projects_by_health.append({
            'project_id': pid,
            'project_code': project.project_code,
            'client_name': project.client_name,
            'last_entry_date': last_entry_date,
            'days_since_entry': days_since_entry,
            'open_disputes': open_disputes,
            'pending_adhoc': pending_adhoc,
            'billing_status': billing_status,
            'billing_status_display': billing_status_display,
            'health_score': health_score,
        })

    # Sort by health score (worst first)
    projects_by_health.sort(key=lambda x: x['health_score'])

    # ==================== DATA QUALITY (MY PROJECTS) ====================
    
    # My projects without project_id
    my_projects_without_id = my_projects.filter(
        Q(project_id__isnull=True) | Q(project_id='')
    ).count()
    
    # My projects without project cards (Active only)
    my_active_project_ids = my_active_projects.values_list('project_id', flat=True)
    
    my_projects_with_cards = ProjectCard.objects.filter(
        project_id__in=my_active_project_ids
    ).values_list('project_id', flat=True).distinct()
    
    my_incomplete_project_cards = len(set(my_active_project_ids) - set(my_projects_with_cards))
    
    # ==================== RECENT ACTIVITY ====================
    
    # Recent entries by me
    recent_entries = DailySpaceUtilization.objects.filter(
        project__in=my_projects
    ).order_by('-created_at')[:10]
    
    recent_entries_list = []
    for entry in recent_entries:
        recent_entries_list.append({
            'project_id': entry.project.project_id if entry.project else None,
            'entry_date': entry.entry_date,
            'space_utilized': entry.space_utilized or 0,
            'inventory_value': entry.inventory_value or 0,
            'unit': entry.unit.label if hasattr(entry, 'unit') and entry.unit else 'N/A',
            'created_at': entry.created_at
        })
    
    # ==================== ALERTS ====================
    
    total_alerts = (
        entries_pending_today +
        my_projects_without_id +
        my_incomplete_project_cards +
        my_adhoc_pending
    )
    
    # ==================== QUICK STATS ====================

    # Average entries per day this month
    avg_entries_per_day = round(
        entries_this_month / working_days_month, 1
    ) if working_days_month > 0 else 0

    # Best performing project (single aggregate query instead of O(N) loop)
    best_project_data = None
    if working_days_month > 0:
        _best = DailySpaceUtilization.objects.filter(
            project__in=my_active_projects,
            entry_date__gte=current_month_start,
        ).values('project_id', 'project__client_name').annotate(
            cnt=Count('id')
        ).order_by('-cnt').first()

        if _best:
            best_project_data = {
                'project_id': _best['project_id'],
                'client_name': _best['project__client_name'],
                'completion_rate': round((_best['cnt'] / working_days_month * 100), 1)
            }

    # ==================== WEEK CALENDAR DATA (3 batch queries instead of 21) ====================

    _week_end = week_start + timedelta(days=6)
    _wk_cutoff = min(today, _week_end)

    # Pre-fetch all week data in 3 queries
    _wk_entries = dict(
        DailySpaceUtilization.objects.filter(
            project__in=my_active_projects,
            entry_date__gte=week_start, entry_date__lte=_wk_cutoff,
        ).values('entry_date').annotate(cnt=Count('project_id', distinct=True)).values_list('entry_date', 'cnt')
    )
    _wk_disputes = dict(
        DisputeLog.objects.filter(
            project__in=my_projects,
            raised_at__date__gte=week_start, raised_at__date__lte=_wk_cutoff,
        ).values('raised_at__date').annotate(cnt=Count('dispute_id')).values_list('raised_at__date', 'cnt')
    )
    _wk_adhoc = dict(
        AdhocBillingEntry.objects.filter(
            project__in=my_projects,
            event_date__gte=week_start, event_date__lte=_wk_cutoff,
        ).values('event_date').annotate(cnt=Count('id')).values_list('event_date', 'cnt')
    )

    week_data = []
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        is_today = (day_date == today)
        is_future = (day_date > today)
        is_sunday = (day_date.weekday() == 6)

        day_entries = _wk_entries.get(day_date, 0)
        expected = active_projects if not is_sunday and not is_future else 0
        compliance = round((day_entries / expected * 100), 0) if expected > 0 else 0

        # Determine color
        if is_future or is_sunday:
            color = 'gray'
        elif compliance >= 90:
            color = 'green'
        elif compliance >= 70:
            color = 'yellow'
        else:
            color = 'red'

        week_data.append({
            'date': day_date,
            'day': day_date.day,
            'is_today': is_today,
            'is_future': is_future,
            'is_sunday': is_sunday,
            'is_holiday': False,
            'entries': day_entries,
            'expected': expected,
            'compliance': compliance,
            'disputes_count': _wk_disputes.get(day_date, 0),
            'adhoc_count': _wk_adhoc.get(day_date, 0),
            'color': color,
        })
    
    # ==================== CONTEXT ====================
    
    context = {
        # Date
        'today': today,
        'current_time': timezone.now().strftime('%I:%M %p'),
        'coordinator_name': coordinator_name,

        # My Projects (for top cards - template expects these names)
        'total_projects': total_my_projects,  # Template uses 'total_projects'
        'total_my_projects': total_my_projects,
        'active_projects': active_projects,
        'notice_period_projects': notice_period_projects,
        'not_started_projects': not_started_projects,
        'inactive_projects': inactive_projects,
        'waas_projects': waas_projects,
        'saas_projects': saas_projects,
        'gw_projects': gw_projects,
        'state_distribution': state_distribution,

        # Daily Entries (template expects 'entries_today_count')
        'entries_today': entries_today,
        'entries_today_count': entries_today,  # Template uses this name
        'entries_pending_today': entries_pending_today,
        'completion_rate_today': completion_rate_today,
        'entries_this_week': entries_this_week,
        'working_days_week': working_days_week,
        'weekly_completion_rate': weekly_completion_rate,
        'entries_this_month': entries_this_month,
        'working_days_month': working_days_month,
        'monthly_completion_rate': monthly_completion_rate,
        'avg_entries_per_day': avg_entries_per_day,

        # MIS
        'mis_pending_count': mis_pending_count,

        # Attention Needed
        'projects_needing_entry': projects_needing_entry,

        # Disputes
        'my_open_disputes': my_open_disputes,
        'my_resolved_disputes': my_resolved_disputes,
        'recent_disputes': recent_disputes,

        # Adhoc
        'my_adhoc_pending': my_adhoc_pending,
        'my_adhoc_approved_month': my_adhoc_approved_month,
        'recent_adhoc': recent_adhoc_list,
        'my_pending_adhoc_count': my_pending_adhoc_count,
        'my_pending_adhoc_amount': my_pending_adhoc_amount,
        'my_billed_adhoc_count': my_billed_adhoc_count,
        'my_billed_adhoc_amount': my_billed_adhoc_amount,

        # Monthly Billing
        'current_billing_month': current_billing_month,
        'billing_draft_count': billing_draft_count,
        'billing_submitted_count': billing_submitted_count,
        'billing_approved_count': billing_approved_count,
        'billing_pending_count': billing_pending_count,
        'billing_missing_projects': billing_missing_projects,
        'recent_billings': recent_billings,

        # Project Health
        'projects_by_health': projects_by_health,

        # Data Quality
        'my_projects_without_id': my_projects_without_id,
        'my_incomplete_project_cards': my_incomplete_project_cards,

        # Recent Activity
        'recent_entries': recent_entries_list,

        # Alerts
        'total_alerts': total_alerts,

        # Quick Stats
        'best_project': best_project_data,

        # Week Calendar
        'week_data': week_data,
    }

    return render(request, 'dashboards/operation_coordinator_dashboard.html', context)