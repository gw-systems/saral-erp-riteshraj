import logging
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Notification

logger = logging.getLogger(__name__)

User = get_user_model()


def create_notification(recipient, title, message, notification_type,
                       priority='normal', severity='info', category='system',
                       action_url=None, action_label=None, metadata=None,
                       dispute=None, query=None, project=None, monthly_billing=None, group_key=None):
    """
    Enterprise-grade notification creation utility.
    Kept 'query' parameter for backward compatibility (though not stored in model).
    """
    try:
        # Auto-determine category from notification_type if not provided
        if category == 'system':
            if 'dispute' in notification_type:
                category = 'operations'
                severity = severity if severity != 'info' else 'warning'
            elif 'query' in notification_type or 'billing' in notification_type:
                category = 'billing'
                severity = severity if severity != 'info' else 'warning'
            elif 'data_entry' in notification_type or 'coordinator' in notification_type:
                category = 'operations'
            elif 'reminder' in notification_type:
                category = 'reminder'
                severity = severity if severity != 'info' else 'warning'

        # Auto-determine priority from notification_type
        if priority == 'normal':
            if notification_type in ['dispute_raised', 'query_raised', 'data_entry_missing']:
                priority = 'high'
            elif notification_type in ['billing_corrected', 'coordinator_reminder']:
                priority = 'high'
            elif 'resolved' in notification_type or 'assigned' in notification_type:
                priority = 'normal'

        # Use the enterprise-grade create_notification class method
        notification = Notification.create_notification(
            recipient=recipient,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
            severity=severity,
            category=category,
            action_url=action_url,
            action_label=action_label,
            metadata=metadata or {},
            dispute=dispute,
            project=project,
            monthly_billing=monthly_billing,
            group_key=group_key
        )
        return notification
    except Exception as e:
        logger.error(f"Error creating notification: {e}", exc_info=True)
        return None


def notify_dispute_raised(dispute):
    """Notify manager when coordinator raises a dispute"""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Get all managers and controllers
    recipients = User.objects.filter(
        role__in=['operation_manager', 'operation_controller', 'admin'],
        is_active=True
    )

    for recipient in recipients:
        create_notification(
            recipient=recipient,
            notification_type='dispute_raised',
            title=f'New Dispute Raised',
            message=f'{dispute.raised_by.get_full_name()} raised a dispute: {dispute.title}',
            priority='high',
            severity='warning',
            category='operations',
            action_url=f'/operations/disputes/{dispute.dispute_id}/',
            action_label='View Dispute',
            dispute=dispute,
            project=dispute.project,
            group_key=f'dispute_{dispute.dispute_id}'
        )


def notify_dispute_assigned(dispute):
    """Notify user when dispute is assigned to them"""
    if dispute.assigned_to:
        create_notification(
            recipient=dispute.assigned_to,
            notification_type='dispute_assigned',
            title=f'Dispute Assigned to You',
            message=f'You have been assigned dispute: {dispute.title}',
            priority='high',
            severity='warning',
            category='operations',
            action_url=f'/operations/disputes/{dispute.dispute_id}/',
            action_label='View Dispute',
            dispute=dispute,
            project=dispute.project,
            group_key=f'dispute_{dispute.dispute_id}'
        )


def notify_dispute_resolved(dispute):
    """Notify coordinator when their dispute is resolved"""
    if dispute.raised_by:
        create_notification(
            recipient=dispute.raised_by,
            notification_type='dispute_resolved',
            title=f'Dispute Resolved',
            message=f'Your dispute has been resolved: {dispute.title}',
            priority='normal',
            severity='success',
            category='operations',
            action_url=f'/operations/disputes/{dispute.dispute_id}/',
            action_label='View Dispute',
            dispute=dispute,
            project=dispute.project,
            group_key=f'dispute_{dispute.dispute_id}'
        )


def notify_query_raised(query):
    """Notify manager when coordinator raises a billing query"""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Get all managers and controllers
    recipients = User.objects.filter(
        role__in=['operation_manager', 'operation_controller', 'admin'],
        is_active=True
    )

    for recipient in recipients:
        create_notification(
            recipient=recipient,
            notification_type='query_raised',
            title=f'New Billing Query Raised',
            message=f'{query.raised_by.get_full_name()} raised a query: {query.subject}',
            priority='high',
            severity='warning',
            category='billing',
            action_url=f'/operations/billing-queries/{query.query_id}/',
            action_label='View Query',
            project=query.project,
            group_key=f'query_{query.query_id}'
        )


def notify_query_assigned(query):
    """Notify user when query is assigned to them"""
    if query.assigned_to:
        create_notification(
            recipient=query.assigned_to,
            notification_type='query_assigned',
            title=f'Query Assigned to You',
            message=f'You have been assigned query: {query.subject}',
            priority='high',
            severity='warning',
            category='billing',
            action_url=f'/operations/billing-queries/{query.query_id}/',
            action_label='View Query',
            project=query.project,
            group_key=f'query_{query.query_id}'
        )


def notify_query_resolved(query):
    """Notify coordinator when their query is resolved"""
    if query.raised_by:
        create_notification(
            recipient=query.raised_by,
            notification_type='query_resolved',
            title=f'Query Resolved',
            message=f'Your billing query has been resolved: {query.subject}',
            priority='normal',
            severity='success',
            category='billing',
            action_url=f'/operations/billing-queries/{query.query_id}/',
            action_label='View Query',
            project=query.project,
            group_key=f'query_{query.query_id}'
        )


def notify_missing_data_entry(user, missing_count, projects):
    """Notify coordinator about missing data entries"""
    project_list = ', '.join([p.code for p in projects[:3]])
    if len(projects) > 3:
        project_list += f' and {len(projects) - 3} more'

    create_notification(
        recipient=user,
        notification_type='data_entry_missing',
        title=f'Missing Data Entry',
        message=f'You have {missing_count} projects with missing entries: {project_list}',
        priority='urgent',
        severity='warning',
        category='operations',
        action_url='/operations/daily-entry/bulk/',
        action_label='Add Entries',
        metadata={'missing_count': missing_count, 'project_count': len(projects)}
    )


def get_unread_count(user):
    """Get count of unread notifications for a user"""
    return Notification.objects.filter(
        recipient=user,
        is_read=False,
        is_deleted=False
    ).count()


def get_recent_notifications(user, limit=10):
    """Get recent notifications for a user"""
    return Notification.objects.filter(
        recipient=user,
        is_deleted=False
    ).select_related('dispute', 'query', 'project')[:limit]


def mark_all_as_read(user):
    """Mark all notifications as read for a user"""
    Notification.objects.filter(
        recipient=user,
        is_read=False
    ).update(is_read=True, read_at=timezone.now())