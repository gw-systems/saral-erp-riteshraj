"""
Reusable role-based access decorators for views
"""
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse


def require_role(*roles):
    """
    Decorator that restricts view access to users with specific roles.

    Usage:
        @require_role('admin', 'super_user')
        def admin_only_view(request):
            ...
    """
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                return JsonResponse({'error': 'Access denied'}, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
