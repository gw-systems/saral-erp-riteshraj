"""
Utility for manually logging caught exceptions to ErrorLog.

Usage in views:
    from accounts.error_utils import log_caught_exception

    except Exception as e:
        log_caught_exception(request, e, severity='error')
        logger.exception("...")
        ...
"""
import sys
import traceback
import logging
import os

logger = logging.getLogger(__name__)


def log_caught_exception(request, exc, severity='error', notes=''):
    """
    Log a caught (handled) exception to the ErrorLog database.

    Unlike the middleware which only captures unhandled 500s, this allows
    views that catch their own exceptions to still record them for audit.

    Safe to call — if ErrorLog save fails, logs to stderr and continues.
    """
    try:
        exc_type = type(exc)
        exc_type_name = exc_type.__name__
        exc_message = str(exc)

        # Get traceback from current exception context
        exc_info = sys.exc_info()
        if exc_info[0] is not None:
            tb_lines = traceback.format_exception(*exc_info)
        else:
            tb_lines = traceback.format_exception(exc_type, exc, exc.__traceback__)
        tb_text = ''.join(tb_lines)

        request_path = request.get_full_path() if request else 'unknown'
        request_method = request.method if request else 'unknown'
        request_user = (
            request.user
            if request and hasattr(request, 'user') and request.user.is_authenticated
            else None
        )
        environment = os.environ.get('ENVIRONMENT', 'development')
        revision = os.environ.get('K_REVISION', 'unknown')

        # Sanitize POST data
        post_data = {}
        if request:
            sensitive = ['password', 'csrfmiddlewaretoken', 'token', 'api_key', 'secret']
            raw_post = dict(request.POST)
            post_data = {
                k: ['***REDACTED***'] if any(s in k.lower() for s in sensitive) else v
                for k, v in raw_post.items()
            }

        from accounts.models import ErrorLog
        ErrorLog.objects.create(
            exception_type=exc_type_name,
            exception_message=exc_message,
            traceback=tb_text,
            request_path=request_path,
            request_method=request_method,
            request_user=request_user,
            environment=environment,
            revision=revision,
            severity=severity,
            source='caught',
            notes=notes,
            request_data={
                'GET': dict(request.GET) if request else {},
                'POST': post_data,
                'FILES': list(request.FILES.keys()) if request else [],
                'headers': {
                    k: v for k, v in request.META.items()
                    if k.startswith('HTTP_')
                } if request else {},
            },
        )
    except Exception as log_err:
        logger.error(f"log_caught_exception: failed to save ErrorLog — {log_err}")
