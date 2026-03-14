from django.utils import timezone


def log_activity_direct(
    *,
    user,
    source,
    action_category,
    action_type,
    module,
    description,
    request=None,
    object_type='',
    object_id=None,
    object_repr='',
    related_object_type='',
    related_object_id=None,
    extra_data=None,
    is_suspicious=False,
    status_code=None,
    response_time_ms=None,
):
    """
    Core function to create an ActivityLog entry.
    Safe to call from signals, middleware, management commands.
    Never raises — errors are swallowed to avoid breaking the main request.
    """
    from .models import ActivityLog
    from .middleware import get_client_ip

    try:
        now = timezone.now()

        # Resolve user display info
        if user and user.is_authenticated:
            user_display = user.get_full_name() or user.username
            role = getattr(user, 'role', 'unknown')
            user_obj = user
        else:
            user_display = 'Anonymous'
            role = 'anonymous'
            user_obj = None

        # Request context
        ip = None
        ua = ''
        session_key = ''
        method = ''
        path = ''

        if request:
            ip = get_client_ip(request)
            ua = request.META.get('HTTP_USER_AGENT', '')[:500]
            session_key = request.session.session_key or ''
            method = getattr(request, 'method', '') or ''
            path = getattr(request, 'path', '') or ''

        ActivityLog.objects.create(
            user=user_obj,
            user_display_name=user_display,
            role_snapshot=role,
            source=source,
            action_category=action_category,
            action_type=action_type,
            module=module,
            object_type=object_type,
            object_id=str(object_id) if object_id is not None else '',
            object_repr=object_repr,
            related_object_type=related_object_type,
            related_object_id=str(related_object_id) if related_object_id is not None else '',
            description=description,
            ip_address=ip,
            user_agent=ua,
            session_key=session_key,
            request_method=method,
            url_path=path,
            status_code=status_code,
            response_time_ms=response_time_ms,
            extra_data=extra_data or {},
            is_suspicious=is_suspicious,
            timestamp=now,
            date=now.date(),
        )
    except Exception:
        pass  # logging must never crash the caller


def log_system_action(*, action_type, module, description, extra_data=None):
    """Convenience for cron/management command logging (no user, no request)."""
    from .models import ActivityLog

    now = timezone.now()
    try:
        ActivityLog.objects.create(
            user=None,
            user_display_name='System',
            role_snapshot='system',
            source='cron',
            action_category='system',
            action_type=action_type,
            module=module,
            description=description,
            extra_data=extra_data or {},
            timestamp=now,
            date=now.date(),
        )
    except Exception:
        pass
