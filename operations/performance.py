"""
Performance calculation helper functions for Operations Dashboard
Handles compliance rates, TAT calculations, and working day computations
"""

from django.db.models import Count, Q, F, Avg, Sum, Case, When, FloatField
from django.utils import timezone
from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple, Optional
from decimal import Decimal



def calculate_working_days(start_date: date, end_date: date, exclude_sundays: bool = True) -> int:
    """
    Calculate working days between two dates
    Excludes Sundays and holidays from WarehouseHoliday model
    
    Args:
        start_date: Start date
        end_date: End date
        exclude_sundays: Whether to exclude Sundays (default: True)
    
    Returns:
        Number of working days
    """
    from operations.models import WarehouseHoliday
    
    if start_date > end_date:
        return 0
    
    # Get all holidays in the date range
    holidays = WarehouseHoliday.objects.filter(
        holiday_date__gte=start_date,
        holiday_date__lte=end_date
    ).values_list('holiday_date', flat=True)
    
    holiday_dates = set(holidays)
    working_days = 0
    current_date = start_date
    
    while current_date <= end_date:
        # Skip if it's a holiday
        if current_date in holiday_dates:
            current_date += timedelta(days=1)
            continue
        
        # Skip if it's Sunday and exclude_sundays is True
        if exclude_sundays and current_date.weekday() == 6:  # 6 = Sunday
            current_date += timedelta(days=1)
            continue
        
        working_days += 1
        current_date += timedelta(days=1)
    
    return working_days


def is_working_day(check_date: date, exclude_sundays: bool = True) -> bool:
    """
    Check if a given date is a working day
    
    Args:
        check_date: Date to check
        exclude_sundays: Whether to exclude Sundays (default: True)
    
    Returns:
        True if working day, False otherwise
    """
    from operations.models import WarehouseHoliday
    
    # Check if it's a holiday
    if WarehouseHoliday.objects.filter(holiday_date=check_date).exists():
        return False
    
    # Check if it's Sunday
    if exclude_sundays and check_date.weekday() == 6:
        return False
    
    return True


def get_working_days_list(start_date: date, end_date: date, exclude_sundays: bool = True) -> List[date]:
    """
    Get list of all working days between two dates
    
    Args:
        start_date: Start date
        end_date: End date
        exclude_sundays: Whether to exclude Sundays (default: True)
    
    Returns:
        List of working day dates
    """
    from operations.models import WarehouseHoliday
    
    if start_date > end_date:
        return []
    
    # Get all holidays in the date range
    holidays = WarehouseHoliday.objects.filter(
        holiday_date__gte=start_date,
        holiday_date__lte=end_date
    ).values_list('holiday_date', flat=True)
    
    holiday_dates = set(holidays)
    working_days = []
    current_date = start_date
    
    while current_date <= end_date:
        # Skip holidays
        if current_date in holiday_dates:
            current_date += timedelta(days=1)
            continue
        
        # Skip Sundays if required
        if exclude_sundays and current_date.weekday() == 6:
            current_date += timedelta(days=1)
            continue
        
        working_days.append(current_date)
        current_date += timedelta(days=1)
    
    return working_days


def calculate_coordinator_performance(coordinator, target_date: date, days: int = 30) -> Dict:
    """
    Calculate comprehensive performance metrics for a coordinator
    
    Args:
        coordinator: User object with role='operation_coordinator'
        target_date: The date to calculate performance up to
        days: Number of days to look back (default: 30)
    
    Returns:
        Dictionary with performance metrics
    """
    from projects.models import ProjectCode
    from operations.models import DailySpaceUtilization, DisputeLog
    
    start_date = target_date - timedelta(days=days - 1)
    
    # Get coordinator's projects
    coordinator_name = coordinator.get_full_name()
    projects = ProjectCode.objects.filter(
        Q(operation_coordinator=coordinator_name),
        project_status='Active'
    )
    
    projects_count = projects.count()
    
    if projects_count == 0:
        return {
            'coordinator': coordinator,
            'projects_count': 0,
            'compliance_rate': 0,
            'expected_entries': 0,
            'actual_entries': 0,
            'missing_entries': 0,
            'working_days': 0,
            'open_disputes': 0,
            'resolved_disputes': 0,
            'avg_tat_days': 0
        }
    
    # Calculate working days
    working_days = calculate_working_days(start_date, target_date)
    
    # Expected entries
    expected_entries = projects_count * working_days
    
    # Actual entries
    actual_entries = DailySpaceUtilization.objects.filter(
        project__in=projects,
        entry_date__gte=start_date,
        entry_date__lte=target_date
    ).count()
    
    # Compliance rate
    compliance_rate = (actual_entries / expected_entries * 100) if expected_entries > 0 else 0
    
    # Missing entries
    missing_entries = expected_entries - actual_entries
    
    # Disputes
    open_disputes = DisputeLog.objects.filter(
        project__in=projects,
        status__in=['open', 'in_progress']
    ).count()
    
    resolved_disputes = DisputeLog.objects.filter(
        project__in=projects,
        status='resolved',
        resolved_at__gte=start_date,
        resolved_at__lte=target_date
    ).count()
    
    # Average TAT for resolved disputes
    resolved_disputes = DisputeLog.objects.filter(
        project__in=projects,
        status='resolved',
        resolved_at__gte=start_date
    )
    
    total_tat_seconds = 0
    resolved_count = 0
    
    for dispute in resolved_disputes:
        # FIX: Check if BOTH resolved_at AND opened_at exist
        if dispute.resolved_at and dispute.opened_at:
            tat = dispute.resolved_at - dispute.opened_at
            total_tat_seconds += tat.total_seconds()
            resolved_count += 1
        # Fallback: If opened_at is missing, use raised_at (creation time)
        elif dispute.resolved_at and dispute.raised_at:
            tat = dispute.resolved_at - dispute.raised_at
            total_tat_seconds += tat.total_seconds()
            resolved_count += 1
            
    avg_tat_days = round((total_tat_seconds / 86400) / resolved_count, 1) if resolved_count > 0 else 0
    
    return {
        'coordinator': coordinator,
        'projects_count': projects_count,
        'compliance_rate': round(compliance_rate, 2),
        'expected_entries': expected_entries,
        'actual_entries': actual_entries,
        'missing_entries': missing_entries,
        'working_days': working_days,
        'open_disputes': open_disputes,
        'resolved_disputes': resolved_disputes,
        'avg_tat_days': round(avg_tat_days, 2)
    }


def calculate_manager_performance(manager, target_date: date, days: int = 30) -> Dict:
    """
    Calculate comprehensive performance metrics for an operation manager
    
    Args:
        manager: User object with role='operation_manager'
        target_date: The date to calculate performance up to
        days: Number of days to look back (default: 30)
    
    Returns:
        Dictionary with performance metrics
    """
    from projects.models import ProjectCode
    from operations.models import DailySpaceUtilization, DisputeLog
    
    start_date = target_date - timedelta(days=days - 1)
    
    # Get manager's projects (using operation_coordinator field since there's no operation_manager field)
    manager_name = manager.get_full_name()
    projects = ProjectCode.objects.filter(
        operation_coordinator=manager_name,
        project_status='Active'
    )
    
    projects_count = projects.count()
    
    if projects_count == 0:
        return {
            'manager': manager,
            'projects_count': 0,
            'compliance_rate': 0,
            'expected_entries': 0,
            'actual_entries': 0,
            'missing_entries': 0,
            'working_days': 0,
            'open_disputes': 0,
            'resolved_disputes': 0,
            'avg_tat_days': 0
        }
    
    # Calculate working days
    working_days = calculate_working_days(start_date, target_date)
    
    # Expected entries
    expected_entries = projects_count * working_days
    
    # Actual entries
    actual_entries = DailySpaceUtilization.objects.filter(
        project__in=projects,
        entry_date__gte=start_date,
        entry_date__lte=target_date
    ).count()
    
    # Compliance rate
    compliance_rate = (actual_entries / expected_entries * 100) if expected_entries > 0 else 0
    
    # Missing entries
    missing_entries = expected_entries - actual_entries
    
    # Disputes
    open_disputes = DisputeLog.objects.filter(
        project__in=projects,
        status__in=['open', 'in_progress']
    ).count()
    
    resolved_disputes = DisputeLog.objects.filter(
        project__in=projects,
        status='resolved',
        resolved_at__gte=start_date,
        resolved_at__lte=target_date
    ).count()
    
    # Average TAT for resolved disputes
    resolved_disputes_qs = DisputeLog.objects.filter(
        project__in=projects,
        status='resolved',
        resolved_at__isnull=False
    )
    
    if resolved_disputes_qs.exists():
        total_tat_seconds = 0
        count = 0
        for dispute in resolved_disputes_qs:
            tat = dispute.resolved_at - dispute.opened_at
            total_tat_seconds += tat.total_seconds()
            count += 1
        
        avg_tat_days = (total_tat_seconds / count) / 86400
    else:
        avg_tat_days = 0
    
    return {
        'manager': manager,
        'projects_count': projects_count,
        'compliance_rate': round(compliance_rate, 2),
        'expected_entries': expected_entries,
        'actual_entries': actual_entries,
        'missing_entries': missing_entries,
        'working_days': working_days,
        'open_disputes': open_disputes,
        'resolved_disputes': resolved_disputes,
        'avg_tat_days': round(avg_tat_days, 2)
    }


def get_system_compliance(target_date: date) -> Dict:
    """
    Calculate system-wide compliance for a given date
    
    Args:
        target_date: The date to calculate compliance for
    
    Returns:
        Dictionary with system compliance metrics
    """
    from projects.models import ProjectCode
    from operations.models import DailySpaceUtilization
    
    # Get all active projects
    active_projects = ProjectCode.objects.filter(
        project_status='Active'
    )
    
    total_projects = active_projects.count()
    
    if total_projects == 0:
        return {
            'compliance_rate': 0,
            'entries_today': 0,
            'expected_entries': 0,
            'missing_entries': 0
        }
    
    # Check if target_date is a working day
    if not is_working_day(target_date):
        return {
            'compliance_rate': 100,  # Non-working day = 100% compliance
            'entries_today': 0,
            'expected_entries': 0,
            'missing_entries': 0
        }
    
    # Expected entries = number of active projects
    expected_entries = total_projects
    
    # Actual entries for target date
    entries_today = DailySpaceUtilization.objects.filter(
        project__in=active_projects,
        entry_date=target_date
    ).count()
    
    # Compliance rate
    compliance_rate = (entries_today / expected_entries * 100) if expected_entries > 0 else 0
    
    # Missing entries
    missing_entries = expected_entries - entries_today
    
    return {
        'compliance_rate': round(compliance_rate, 2),
        'entries_today': entries_today,
        'expected_entries': expected_entries,
        'missing_entries': missing_entries
    }


def calculate_dispute_tat(dispute) -> Optional[float]:
    """
    Calculate TAT (Turnaround Time) for a dispute in days
    
    Args:
        dispute: DisputeLog object
    
    Returns:
        TAT in days (float) or None if not resolved
    """
    if dispute.status != 'resolved' or not dispute.resolved_at:
        return None
    
    tat = dispute.resolved_at - dispute.opened_at
    tat_days = tat.total_seconds() / 86400  # Convert to days
    
    return round(tat_days, 2)


def calculate_tat_compliance(disputes_queryset, tat_threshold_days: int = 7) -> Dict:
    """
    Calculate TAT compliance for a set of disputes
    
    Args:
        disputes_queryset: QuerySet of DisputeLog objects
        tat_threshold_days: TAT threshold in days (default: 7)
    
    Returns:
        Dictionary with TAT compliance metrics
    """
    resolved_disputes = disputes_queryset.filter(
        status='resolved',
        resolved_at__isnull=False
    )
    
    total_resolved = resolved_disputes.count()
    
    if total_resolved == 0:
        return {
            'total_resolved': 0,
            'within_tat': 0,
            'exceeded_tat': 0,
            'tat_compliance_rate': 0,
            'avg_tat_days': 0
        }
    
    within_tat = 0
    total_tat_seconds = 0
    
    for dispute in resolved_disputes:
        tat = dispute.resolved_at - dispute.opened_at
        tat_days = tat.total_seconds() / 86400
        total_tat_seconds += tat.total_seconds()
        
        if tat_days <= tat_threshold_days:
            within_tat += 1
    
    exceeded_tat = total_resolved - within_tat
    tat_compliance_rate = (within_tat / total_resolved * 100) if total_resolved > 0 else 0
    avg_tat_days = (total_tat_seconds / total_resolved) / 86400
    
    return {
        'total_resolved': total_resolved,
        'within_tat': within_tat,
        'exceeded_tat': exceeded_tat,
        'tat_compliance_rate': round(tat_compliance_rate, 2),
        'avg_tat_days': round(avg_tat_days, 2)
    }


def calculate_project_health_score(project, target_date: date, days: int = 30) -> Dict:
    """
    Calculate health score for a project
    
    Health Score Formula:
    - Compliance (40%)
    - Disputes (30%)
    - Adhoc Billing (30%)
    
    Args:
        project: ProjectCode object
        target_date: Date to calculate up to
        days: Number of days to look back
    
    Returns:
        Dictionary with health score and components
    """
    from operations.models import DailySpaceUtilization, DisputeLog
    from operations.models_adhoc import AdhocBillingEntry
    
    start_date = target_date - timedelta(days=days - 1)
    
    # 1. Compliance Score (0-100)
    working_days = calculate_working_days(start_date, target_date)
    expected_entries = working_days
    
    actual_entries = DailySpaceUtilization.objects.filter(
        project=project,
        entry_date__gte=start_date,
        entry_date__lte=target_date
    ).count()
    
    compliance_score = (actual_entries / expected_entries * 100) if expected_entries > 0 else 0
    
    # 2. Dispute Score (0-100)
    open_disputes = DisputeLog.objects.filter(
        project=project,
        status__in=['open', 'in_progress']
    ).count()
    
    # Penalty: -10 points per open dispute, minimum 0
    dispute_score = max(0, 100 - (open_disputes * 10))
    
    # 3. Adhoc Score (0-100)
    pending_adhoc = AdhocBillingEntry.objects.filter(
        project=project,
        status='pending',
        event_date__gte=start_date
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Penalty: Based on pending amount (₹50K = 20 point penalty)
    adhoc_penalty = min((pending_adhoc / 50000) * 20, 100)
    adhoc_score = max(0, 100 - adhoc_penalty)
    
    # 4. Calculate weighted health score
    health_score = (
        compliance_score * 0.4 +
        dispute_score * 0.3 +
        adhoc_score * 0.3
    )
    
    return {
        'project': project,
        'health_score': round(health_score, 2),
        'compliance_score': round(compliance_score, 2),
        'dispute_score': round(dispute_score, 2),
        'adhoc_score': round(adhoc_score, 2),
        'open_disputes': open_disputes,
        'pending_adhoc': pending_adhoc,
        'actual_entries': actual_entries,
        'expected_entries': expected_entries
    }


def get_performance_trend(current_value: float, previous_value: float, threshold: float = 5.0) -> str:
    """
    Determine performance trend direction
    
    Args:
        current_value: Current period value
        previous_value: Previous period value
        threshold: Percentage threshold for "stable" (default: 5%)
    
    Returns:
        'up', 'down', or 'stable'
    """
    if previous_value == 0:
        return 'stable' if current_value == 0 else 'up'
    
    change_percent = ((current_value - previous_value) / previous_value) * 100
    
    if change_percent > threshold:
        return 'up'
    elif change_percent < -threshold:
        return 'down'
    else:
        return 'stable'


def format_tat_display(tat_days: float) -> str:
    """
    Format TAT for display
    
    Args:
        tat_days: TAT in days (float)
    
    Returns:
        Formatted string (e.g., "2.5 days", "3 days")
    """
    if tat_days == 0:
        return "N/A"
    elif tat_days < 1:
        hours = int(tat_days * 24)
        return f"{hours} hours"
    elif tat_days == int(tat_days):
        return f"{int(tat_days)} days"
    else:
        return f"{tat_days:.1f} days"


def get_compliance_color_class(compliance: float) -> str:
    """
    Get CSS color class based on compliance percentage
    
    Args:
        compliance: Compliance percentage (0-100)
    
    Returns:
        CSS class name
    """
    if compliance >= 90:
        return 'text-green-600'
    elif compliance >= 70:
        return 'text-yellow-600'
    else:
        return 'text-red-600'


def get_compliance_status(compliance: float) -> str:
    """
    Get compliance status label
    
    Args:
        compliance: Compliance percentage (0-100)
    
    Returns:
        Status string
    """
    if compliance >= 90:
        return 'excellent'
    elif compliance >= 70:
        return 'warning'
    else:
        return 'critical'
    


# ==================== DISPUTE PERFORMANCE CALCULATIONS ====================

def calculate_dispute_performance(user, end_date, days=30):
    """
    Calculate dispute handling performance for a user (coordinator/manager/controller)
    
    Returns dict with:
    - total_disputes_owned: Total disputes assigned to user
    - active_disputes: Currently open/in_progress
    - resolved_count: Resolved in the period
    - resolution_rate: Percentage resolved
    - avg_tat_days: Average TAT for resolved disputes
    - tat_compliance_rate: Percentage resolved within 7 days
    - overdue_count: Disputes overdue (>7 days)
    - overdue_rate: Percentage overdue
    - closure_velocity: Resolved/Opened ratio
    - dpi_score: Dispute Performance Index (0-100)
    - projects_with_disputes: Count of projects with disputes
    - dispute_rate: Percentage of projects with disputes
    """
    from django.db.models import Avg, Count, Q
    from django.utils import timezone
    from operations.models import DisputeLog
    from projects.models import ProjectCode
    from accounts.models import User
    
    start_date = end_date - timedelta(days=days-1)
    

    # Get disputes based on role
    if user.role in ['operation_coordinator']:
        # Coordinators own disputes on their assigned projects
        user_full_name = user.get_full_name()
        user_projects = ProjectCode.objects.filter(
            Q(operation_coordinator=user_full_name) | Q(backup_coordinator=user_full_name)
        ).filter(
            Q(project_status='Active') | Q(project_status='Operation Not Started')
        )
        all_disputes = DisputeLog.objects.filter(project__in=user_projects)
    else:
        # Managers/Controllers see disputes assigned to them
        all_disputes = DisputeLog.objects.filter(assigned_to=user)
    
    # Active disputes (open or in_progress)
    active_disputes = all_disputes.filter(
        status__in=['open', 'in_progress']
    )
    
    # Disputes resolved in the period
    resolved_in_period = all_disputes.filter(
        status='resolved',
        resolved_at__gte=start_date,
        resolved_at__lte=end_date
    )
    
    # Disputes opened in the period
    opened_in_period = all_disputes.filter(
        opened_at__gte=start_date,
        opened_at__lte=end_date
    )
    
    # Calculate metrics
    total_disputes_owned = all_disputes.count()
    active_count = active_disputes.count()
    resolved_count = resolved_in_period.count()
    opened_count = opened_in_period.count()
    
    # Resolution rate
    resolution_rate = (resolved_count / total_disputes_owned * 100) if total_disputes_owned > 0 else 0
    
    # Average TAT for resolved disputes
    resolved_with_tat = resolved_in_period.exclude(
        Q(opened_at__isnull=True) | Q(resolved_at__isnull=True)
    )
    
    tat_values = []
    within_tat_count = 0
    
    for dispute in resolved_with_tat:
        tat = dispute.get_tat_days()
        if tat is not None:
            tat_values.append(tat)
            if tat <= 7:
                within_tat_count += 1
    
    avg_tat_days = sum(tat_values) / len(tat_values) if tat_values else 0
    tat_compliance_rate = (within_tat_count / len(tat_values) * 100) if tat_values else 0
    
    # Overdue disputes
    overdue_count = 0
    for dispute in active_disputes:
        if dispute.is_overdue():
            overdue_count += 1
    
    overdue_rate = (overdue_count / active_count * 100) if active_count > 0 else 0
    
    # Closure velocity
    closure_velocity = (resolved_count / opened_count) if opened_count > 0 else 0
    
    # Projects with disputes
    projects_with_disputes = all_disputes.values('project').distinct().count()
    
    # Get user's total projects (coordinator or manager)
    user_full_name = user.get_full_name()
    from projects.models import ProjectCode
    
    if user.role in ['operation_coordinator', 'backup_coordinator']:
        total_projects = ProjectCode.objects.filter(
            Q(operation_coordinator=user_full_name) | Q(backup_coordinator=user_full_name)
        ).filter(
            Q(project_status='Active') | Q(project_status='Operation Not Started')
        ).count()
    elif user.role == 'operation_manager':
        # Managers oversee all coordinators/projects (no team structure)
        total_projects = ProjectCode.objects.filter(
            Q(project_status='Active') | Q(project_status='Operation Not Started')
        ).count()
    else:
        # Controller sees all projects
        total_projects = ProjectCode.objects.filter(
            Q(project_status='Active') | Q(project_status='Operation Not Started')
        ).count()
    
    dispute_rate = (projects_with_disputes / total_projects * 100) if total_projects > 0 else 0
    
    # Calculate DPI (Dispute Performance Index)
    # Formula: Weighted average of key metrics
    # - Resolution Rate: 30%
    # - TAT Compliance: 30%
    # - Low Dispute Rate: 20% (100 - dispute_rate)
    # - Closure Velocity: 20% (normalized to 0-100)
    
    velocity_normalized = min(closure_velocity * 50, 100)  # Normalize velocity to 0-100
    no_dispute_rate = 100 - dispute_rate
    
    dpi_score = (
        (resolution_rate * 0.30) +
        (tat_compliance_rate * 0.30) +
        (no_dispute_rate * 0.20) +
        (velocity_normalized * 0.20)
    )
    
    return {
        'total_disputes_owned': total_disputes_owned,
        'active_disputes': active_count,
        'resolved_count': resolved_count,
        'opened_count': opened_count,
        'resolution_rate': round(resolution_rate, 1),
        'avg_tat_days': round(avg_tat_days, 1),
        'tat_compliance_rate': round(tat_compliance_rate, 1),
        'overdue_count': overdue_count,
        'overdue_rate': round(overdue_rate, 1),
        'closure_velocity': round(closure_velocity, 2),
        'dpi_score': round(dpi_score, 1),
        'projects_with_disputes': projects_with_disputes,
        'total_projects': total_projects,
        'dispute_rate': round(dispute_rate, 1),
        'within_tat_count': within_tat_count,
    }


def calculate_project_dispute_metrics(project, end_date, days=30):
    """
    Calculate dispute metrics for a specific project
    
    Returns dict with:
    - disputes_opened: Count opened in period
    - active_disputes: Currently open/in_progress
    - resolved_disputes: Resolved in period
    - avg_tat_days: Average resolution time
    - health_score: Project dispute health (0-100)
    - trend: Month-over-month change
    """
    from django.db.models import Q
    from operations.models import DisputeLog
    
    start_date = end_date - timedelta(days=days-1)
    
    # Current period
    current_disputes = DisputeLog.objects.filter(project=project)
    
    disputes_opened = current_disputes.filter(
        opened_at__gte=start_date,
        opened_at__lte=end_date
    ).count()
    
    active_disputes = current_disputes.filter(
        status__in=['open', 'in_progress']
    ).count()
    
    resolved_disputes = current_disputes.filter(
        status='resolved',
        resolved_at__gte=start_date,
        resolved_at__lte=end_date
    ).count()
    
    # Calculate average TAT
    resolved_with_tat = current_disputes.filter(
        status='resolved',
        resolved_at__gte=start_date,
        resolved_at__lte=end_date
    ).exclude(
        Q(opened_at__isnull=True) | Q(resolved_at__isnull=True)
    )
    
    tat_values = []
    for dispute in resolved_with_tat:
        tat = dispute.get_tat_days()
        if tat is not None:
            tat_values.append(tat)
    
    avg_tat_days = sum(tat_values) / len(tat_values) if tat_values else 0
    
    # Count overdue disputes
    overdue_count = 0
    for dispute in current_disputes.filter(status__in=['open', 'in_progress']):
        if dispute.is_overdue():
            overdue_count += 1
    
    # Calculate health score (0-100)
    health_score = 100
    
    # Deductions
    health_score -= active_disputes * 10  # -10 per active dispute
    health_score -= overdue_count * 20    # -20 per overdue dispute
    
    # High dispute rate penalty
    if disputes_opened > 2:
        health_score -= 15
    
    # Poor TAT penalty
    if avg_tat_days > 7:
        health_score -= 10
    
    health_score = max(0, health_score)  # Don't go below 0
    
    # Calculate trend (vs previous period)
    prev_start = start_date - timedelta(days=days)
    prev_end = start_date - timedelta(days=1)
    
    prev_disputes_opened = current_disputes.filter(
        opened_at__gte=prev_start,
        opened_at__lte=prev_end
    ).count()
    
    if prev_disputes_opened > 0:
        trend_pct = ((disputes_opened - prev_disputes_opened) / prev_disputes_opened) * 100
    else:
        trend_pct = 0
    
    return {
        'disputes_opened': disputes_opened,
        'active_disputes': active_disputes,
        'resolved_disputes': resolved_disputes,
        'avg_tat_days': round(avg_tat_days, 1),
        'overdue_count': overdue_count,
        'health_score': health_score,
        'trend_pct': round(trend_pct, 1),
    }


def get_all_projects_dispute_performance(end_date, days=30):
    """
    Get dispute performance for all active projects
    Returns list of dicts sorted by health score (worst first)
    """
    from projects.models import ProjectCode
    from django.db.models import Q
    
    active_projects = ProjectCode.objects.filter(
        Q(project_status='Active') | Q(project_status='Operation Not Started')
    )
    
    project_metrics = []
    
    for project in active_projects:
        metrics = calculate_project_dispute_metrics(project, end_date, days)
        
        project_metrics.append({
            'project': project,
            'project_code': project.project_code,
            'client_name': project.client_name,
            'coordinator': project.operation_coordinator,
            **metrics
        })
    
    # Sort by health score (worst first)
    project_metrics.sort(key=lambda x: x['health_score'])
    
    return project_metrics