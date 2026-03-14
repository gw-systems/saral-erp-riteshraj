from operations.views import get_coordinator_projects
"""
Alert system helper functions.
Creates and manages in-app notifications for coordinators and managers.
"""

from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse
from operations.views import get_coordinator_projects, get_problem_coordinators

from operations.models import InAppAlert
from operations.performance import (
    calculate_coordinator_performance,
    get_system_compliance,
    is_working_day
)

User = get_user_model()


def create_alert(user, alert_type, title, message, severity='info', related_url=''):
    """
    Create an in-app alert for a user.
    
    Args:
        user: User object who receives the alert
        alert_type: 'coordinator_reminder', 'manager_notification', or 'system_alert'
        title: Brief alert title (max 200 chars)
        message: Detailed message
        severity: 'info', 'warning', or 'critical'
        related_url: Optional URL to relevant page
    
    Returns:
        InAppAlert object
    """
    alert = InAppAlert.objects.create(
        user=user,
        alert_type=alert_type,
        title=title,
        message=message,
        severity=severity,
        related_url=related_url
    )
    
    return alert


def get_unread_alerts(user, limit=None):
    """
    Get unread alerts for a user.
    
    Args:
        user: User object
        limit: Optional limit on number of alerts returned
    
    Returns:
        QuerySet of InAppAlert objects
    """
    alerts = InAppAlert.objects.filter(
        user=user,
        is_read=False
    ).order_by('-created_at')
    
    if limit:
        alerts = alerts[:limit]
    
    return alerts


def get_unread_count(user):
    """
    Get count of unread alerts for a user.
    
    Args:
        user: User object
    
    Returns:
        int: Number of unread alerts
    """
    return InAppAlert.objects.filter(
        user=user,
        is_read=False
    ).count()


def mark_alert_read(alert_id, user):
    """
    Mark a specific alert as read.
    
    Args:
        alert_id: Alert ID
        user: User object (for security check)
    
    Returns:
        bool: True if marked, False if not found or not owned by user
    """
    try:
        alert = InAppAlert.objects.get(id=alert_id, user=user)
        alert.mark_as_read()
        return True
    except InAppAlert.DoesNotExist:
        return False


def mark_all_alerts_read(user):
    """
    Mark all alerts as read for a user.
    
    Args:
        user: User object
    
    Returns:
        int: Number of alerts marked as read
    """
    count = InAppAlert.objects.filter(
        user=user,
        is_read=False
    ).update(
        is_read=True,
        read_at=timezone.now()
    )
    
    return count


def check_coordinator_reminders():
    """
    Check all coordinators and send reminders if entries are missing.
    Should be run at 1 PM daily.
    
    Returns:
        dict: {
            'checked': int,
            'alerts_sent': int,
            'coordinators_notified': list
        }
    """
    today = timezone.now().date()
    
    coordinators = User.objects.filter(
        role__in=['operation_coordinator', 'warehouse_manager'],
        is_active=True
    )
    
    alerts_sent = 0
    notified = []
    
    for coordinator in coordinators:
        projects = get_coordinator_projects(coordinator)
        total_projects = projects.count()
        
        if total_projects == 0:
            continue  # No projects assigned, skip
        
        # Count today's entries
        from operations.models import DailySpaceUtilization
        entries_today = DailySpaceUtilization.objects.filter(
            entered_by=coordinator,
            entry_date=today,
            project__in=projects
        ).count()
        
        # If not all entries done, send reminder
        if entries_today < total_projects:
            pending = total_projects - entries_today
            
            # Check if already sent reminder today
            existing_alert = InAppAlert.objects.filter(
                user=coordinator,
                alert_type='coordinator_reminder',
                created_at__date=today
            ).exists()
            
            if not existing_alert:
                create_alert(
                    user=coordinator,
                    alert_type='coordinator_reminder',
                    title='⏰ Data Entry Reminder',
                    message=f'You have {pending} project{"s" if pending > 1 else ""} pending data entry for today. Please complete before 5 PM to avoid delays.',
                    severity='warning',
                    related_url=reverse('operations:daily_entry_bulk')
                )
                
                alerts_sent += 1
                notified.append(coordinator.get_full_name())
    
    return {
        'checked': coordinators.count(),
        'alerts_sent': alerts_sent,
        'coordinators_notified': notified
    }


def check_manager_alerts():
    """
    Check coordinator performance and alert managers about problems.
    Should be run at 3 PM daily.
    
    Returns:
        dict: {
            'managers_notified': int,
            'coordinators_behind': int,
            'details': list
        }
    """
    # Get coordinators with compliance issues
    problem_coordinators = get_problem_coordinators(threshold=100)
    
    if not problem_coordinators:
        return {
            'managers_notified': 0,
            'coordinators_behind': 0,
            'details': []
        }
    
    # Get all managers and controllers
    managers = User.objects.filter(
        role__in=['operation_manager', 'operation_controller'],
        is_active=True
    )
    
    # Categorize problems
    critical = [c for c in problem_coordinators if c['status'] == 'critical']
    warning = [c for c in problem_coordinators if c['status'] == 'warning']
    
    # Build message
    details = []
    message_parts = []
    
    if critical:
        message_parts.append(f"🚨 CRITICAL - {len(critical)} coordinator{'s' if len(critical) > 1 else ''} below 90%:")
        for c in critical:
            coord_name = c['coordinator'].get_full_name()
            message_parts.append(f"  • {coord_name}: {c['compliance']:.1f}% complete ({c['missing_count']}/{c['total_projects']} missing)")
            details.append({'name': coord_name, 'compliance': c['compliance'], 'status': 'critical'})
    
    if warning:
        message_parts.append(f"\n⚠️ WARNING - {len(warning)} coordinator{'s' if len(warning) > 1 else ''} below 100%:")
        for c in warning:
            coord_name = c['coordinator'].get_full_name()
            message_parts.append(f"  • {coord_name}: {c['compliance']:.1f}% complete ({c['missing_count']}/{c['total_projects']} missing)")
            details.append({'name': coord_name, 'compliance': c['compliance'], 'status': 'warning'})
    
    message = '\n'.join(message_parts)
    
    # Determine severity
    if critical:
        severity = 'critical'
        title = f'🚨 {len(problem_coordinators)} Coordinators Behind Schedule'
    else:
        severity = 'warning'
        title = f'⚠️ {len(problem_coordinators)} Coordinator{"s" if len(problem_coordinators) > 1 else ""} Need Attention'
    
    # Check if already sent alert today
    today = timezone.now().date()
    
    # Send to all managers
    alerts_sent = 0
    for manager in managers:
        existing_alert = InAppAlert.objects.filter(
            user=manager,
            alert_type='manager_notification',
            created_at__date=today
        ).exists()
        
        if not existing_alert:
            create_alert(
                user=manager,
                alert_type='manager_notification',
                title=title,
                message=message,
                severity=severity,
                related_url=reverse('operations:daily_entry_bulk')  # Will update to performance page later
            )
            alerts_sent += 1
    
    return {
        'managers_notified': alerts_sent,
        'coordinators_behind': len(problem_coordinators),
        'details': details
    }


def delete_old_alerts(days=30):
    """
    Delete read alerts older than specified days.
    Keeps unread alerts indefinitely.
    
    Args:
        days: Number of days to keep read alerts
    
    Returns:
        int: Number of alerts deleted
    """
    cutoff_date = timezone.now() - timezone.timedelta(days=days)
    
    count = InAppAlert.objects.filter(
        is_read=True,
        read_at__lt=cutoff_date
    ).delete()[0]
    
    return count


# Add these helper functions in alerts.py after the imports

def calculate_daily_compliance(target_date):
    """Wrapper for compatibility"""
    result = get_system_compliance(target_date)
    return result['compliance_rate']

def get_coordinator_workload(coordinator, target_date=None):
    """Wrapper for compatibility"""
    from django.utils import timezone
    if target_date is None:
        target_date = timezone.now().date()
    
    perf = calculate_coordinator_performance(coordinator, target_date, days=1)
    return {
        'coordinator': coordinator,
        'total_projects': perf['projects_count'],
        'expected_today': perf['expected_entries'],
        'actual_today': perf['actual_entries'],
        'pending_today': perf['missing_entries'],
        'completion_rate': perf['compliance_rate']
    }
