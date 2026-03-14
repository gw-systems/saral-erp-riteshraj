from django.conf import settings

User = None  # lazy import to avoid circular


def _get_user_model():
    from django.contrib.auth import get_user_model
    return get_user_model()


VISIBILITY_ROLES = {
    'admin': '__all__',
    'super_user': '__all_except_admin__',
    'director': '__all__',
    'operation_controller': ['operation_controller', 'operation_manager',
                             'operation_coordinator', 'warehouse_manager'],
    'operation_manager': ['operation_manager', 'operation_coordinator', 'warehouse_manager'],
    'finance_manager': '__self__',
    'sales_manager': '__self__',
    'supply_manager': '__self__',
    'operation_coordinator': '__self__',
    'warehouse_manager': '__self__',
    'backoffice': '__self__',
    'crm_executive': '__self__',
    'digital_marketing': '__self__',
}


def get_visible_users(request_user):
    User = _get_user_model()
    rule = VISIBILITY_ROLES.get(request_user.role, '__self__')
    if rule == '__all__':
        return User.objects.all()
    if rule == '__all_except_admin__':
        return User.objects.exclude(role='admin')
    if rule == '__self__':
        return User.objects.filter(pk=request_user.pk)
    return User.objects.filter(role__in=rule)


def get_visible_logs(request_user):
    from .models import ActivityLog
    visible_users = get_visible_users(request_user)
    return ActivityLog.objects.filter(user__in=visible_users)
