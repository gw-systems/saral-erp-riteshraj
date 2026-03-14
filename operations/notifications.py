"""
Notification helper functions
Easy way to create notifications from any view
"""

from operations.models import InAppAlert
from accounts.models import User
from django.utils import timezone


def create_notification(user, title, message, alert_type='system_alert', severity='info', related_url=''):
    """
    Create a notification for a single user
    
    Args:
        user: User object
        title: Brief title
        message: Detailed message
        alert_type: 'system_alert', 'coordinator_reminder', 'manager_notification'
        severity: 'info', 'warning', 'critical'
        related_url: Optional URL to link to
    
    Returns:
        InAppAlert object
    """
    return InAppAlert.objects.create(
        user=user,
        alert_type=alert_type,
        title=title,
        message=message,
        severity=severity,
        related_url=related_url
    )


def notify_managers(title, message, severity='info', related_url=''):
    """
    Send notification to all operation managers and controllers
    
    Args:
        title: Brief title
        message: Detailed message
        severity: 'info', 'warning', 'critical'
        related_url: Optional URL to link to
    
    Returns:
        Number of notifications created
    """
    recipients = User.objects.filter(
        role__in=['operation_manager', 'operation_controller', 'admin'],
        is_active=True
    )
    
    count = 0
    for user in recipients:
        create_notification(
            user=user,
            title=title,
            message=message,
            alert_type='manager_notification',
            severity=severity,
            related_url=related_url
        )
        count += 1
    
    return count


def notify_coordinators(project, title, message, severity='info', related_url=''):
    """
    Send notification to project's coordinators
    
    Args:
        project: ProjectCode object
        title: Brief title
        message: Detailed message
        severity: 'info', 'warning', 'critical'
        related_url: Optional URL to link to
    
    Returns:
        Number of notifications created
    """
    recipients = []
    
    # Get coordinators
    if project.operation_coordinator:
        try:
            coord = User.objects.get(
                first_name__icontains=project.operation_coordinator.split()[0],
                is_active=True
            )
            recipients.append(coord)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            pass
    
    if project.backup_coordinator:
        try:
            backup = User.objects.get(
                first_name__icontains=project.backup_coordinator.split()[0],
                is_active=True
            )
            recipients.append(backup)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            pass
    
    count = 0
    for user in recipients:
        create_notification(
            user=user,
            title=title,
            message=message,
            alert_type='coordinator_reminder',
            severity=severity,
            related_url=related_url
        )
        count += 1
    
    return count


def mark_all_read(user):
    """Mark all notifications as read for a user"""
    return InAppAlert.objects.filter(user=user, is_read=False).update(
        is_read=True,
        read_at=timezone.now()
    )