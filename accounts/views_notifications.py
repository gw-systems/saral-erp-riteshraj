"""
Enterprise-grade notification views for fetching and managing notifications
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q, Count
from django.contrib import messages
from accounts.models import Notification


@login_required
def notifications_list(request):
    """Full page list of all notifications with filtering"""
    # Get filter parameters
    category = request.GET.get('category', '')
    priority = request.GET.get('priority', '')
    unread_only = request.GET.get('unread', '') == 'true'

    # Base queryset
    notifications = Notification.objects.filter(
        recipient=request.user,
        is_deleted=False
    ).select_related('project', 'dispute', 'monthly_billing')

    # Apply filters
    if category:
        notifications = notifications.filter(category=category)
    if priority:
        notifications = notifications.filter(priority=priority)
    if unread_only:
        notifications = notifications.filter(is_read=False)

    # Get stats — use single base queryset for total/unread, reuse for breakdowns
    _base_notifs = Notification.objects.filter(recipient=request.user, is_deleted=False)
    _totals = _base_notifs.aggregate(
        total=Count('id'),
        unread=Count('id', filter=Q(is_read=False))
    )
    stats = {
        'total': _totals['total'],
        'unread': _totals['unread'],
        'by_category': _base_notifs.values('category').annotate(count=Count('id')),
        'by_priority': _base_notifs.values('priority').annotate(count=Count('id')),
    }

    context = {
        'notifications': notifications,
        'stats': stats,
        'category_filter': category,
        'priority_filter': priority,
        'unread_only': unread_only,
    }

    return render(request, 'accounts/notifications_list.html', context)


@login_required
def notifications_api(request):
    """AJAX endpoint to fetch recent notifications"""
    limit = int(request.GET.get('limit', 10))

    notifications = Notification.objects.filter(
        recipient=request.user,
        is_deleted=False
    ).select_related('project', 'dispute', 'monthly_billing').order_by('-is_pinned', '-created_at')[:limit]

    data = []
    for notif in notifications:
        data.append({
            'id': notif.id,
            'title': notif.title,
            'message': notif.message,
            'notification_type': notif.notification_type,
            'priority': notif.priority,
            'severity': notif.severity,
            'category': notif.category,
            'is_read': notif.is_read,
            'is_pinned': notif.is_pinned,
            'action_url': notif.action_url,
            'action_label': notif.action_label or 'View',
            'icon': notif.icon,
            'color_class': notif.color_class,
            'created_at': notif.created_at.strftime('%b %d, %Y %I:%M %p') if notif.created_at else '',
            'time_ago': get_time_ago(notif.created_at) if notif.created_at else '',
        })

    unread_count = Notification.objects.filter(
        recipient=request.user,
        is_deleted=False,
        is_read=False
    ).count()

    return JsonResponse({
        'notifications': data,
        'unread_count': unread_count,
    })


@login_required
def notification_mark_read(request, notification_id):
    """Mark a single notification as read"""
    if request.method == 'POST':
        try:
            notif = Notification.objects.get(id=notification_id, recipient=request.user)
            notif.mark_as_read()

            # If has action_url, redirect to it
            if notif.action_url:
                return JsonResponse({'success': True, 'redirect': notif.action_url})

            return JsonResponse({'success': True})
        except Notification.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)


@login_required
def notifications_mark_all_read(request):
    """Mark all notifications as read"""
    if request.method == 'POST':
        count = Notification.objects.filter(
            recipient=request.user,
            is_deleted=False,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )
        messages.success(request, f'{count} notifications marked as read')

    return redirect(request.META.get('HTTP_REFERER', 'accounts:dashboard'))


@login_required
def notification_delete(request, notification_id):
    """Soft delete a notification"""
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        recipient=request.user
    )

    notification.soft_delete()
    messages.success(request, 'Notification deleted')
    return redirect('accounts:notifications_list')


@login_required
def notification_batch_action(request):
    """Batch operations on notifications"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    action = request.POST.get('action')
    notification_ids = request.POST.getlist('notification_ids[]')

    if not action or not notification_ids:
        return JsonResponse({'success': False, 'error': 'Missing parameters'}, status=400)

    # Get notifications
    notifications = Notification.objects.filter(
        id__in=notification_ids,
        recipient=request.user,
        is_deleted=False
    )

    count = notifications.count()

    if action == 'mark_read':
        notifications.update(is_read=True, read_at=timezone.now())
        message = f'{count} notifications marked as read'
    elif action == 'mark_unread':
        notifications.update(is_read=False, read_at=None)
        message = f'{count} notifications marked as unread'
    elif action == 'delete':
        notifications.update(is_deleted=True, deleted_at=timezone.now())
        message = f'{count} notifications deleted'
    elif action == 'archive':
        notifications.update(is_archived=True, archived_at=timezone.now())
        message = f'{count} notifications archived'
    else:
        return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)

    return JsonResponse({'success': True, 'message': message, 'count': count})


def get_time_ago(dt):
    """Convert datetime to human-readable 'time ago' format"""
    if not dt:
        return ''
    from django.utils.timesince import timesince
    return timesince(dt).split(',')[0] + ' ago'