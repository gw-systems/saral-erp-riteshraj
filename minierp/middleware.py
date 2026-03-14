"""
Custom middleware for detailed exception logging and environment-aware error handling
"""
import logging
import traceback
import sys
import os
from django.shortcuts import render
from django.utils import timezone

logger = logging.getLogger('django.request')


class DetailedExceptionLoggingMiddleware:
    """
    Environment-aware exception handler
    - Logs detailed error info to console (for Cloud Logging)
    - Stores errors in database
    - Staging: Show full traceback in browser
    - Production: Friendly error (full details for admins)
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.env = os.environ.get('ENVIRONMENT', 'development')
    
    def __call__(self, request):
        response = self.get_response(request)
        return response
    
    def process_exception(self, request, exception):
        """
        Log detailed exception information and return appropriate error page
        """
        # Get the full traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        tb_text = ''.join(tb_lines)
        
        # Get exception details
        exc_type_name = exc_type.__name__
        exc_message = str(exc_value)
        
        # Get request context
        request_path = request.get_full_path()
        request_method = request.method
        request_user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        
        # Get environment context
        revision = os.environ.get('K_REVISION', 'unknown')
        
        # Log to console (Cloud Logging will capture this)
        logger.error(
            f"\n{'='*80}\n"
            f"UNHANDLED EXCEPTION\n"
            f"{'='*80}\n"
            f"Environment: {self.env}\n"
            f"Revision: {revision}\n"
            f"URL: {request_method} {request_path}\n"
            f"User: {request_user if request_user else 'Anonymous'}\n"
            f"IP Address: {self.get_client_ip(request)}\n"
            f"User Agent: {request.META.get('HTTP_USER_AGENT', 'Unknown')}\n"
            f"Referer: {request.META.get('HTTP_REFERER', 'None')}\n"
            f"Exception Type: {exc_type_name}\n"
            f"Exception Message: {exc_message}\n"
            f"{'='*80}\n"
            f"FULL TRACEBACK:\n"
            f"{tb_text}\n"
            f"{'='*80}\n"
            f"REQUEST DATA:\n"
            f"GET: {dict(request.GET)}\n"
            f"POST: {self.sanitize_post_data(dict(request.POST))}\n"
            f"FILES: {list(request.FILES.keys())}\n"
            f"{'='*80}\n"
        )
        
        # Log to Claude error-solutions log (for AI reference)
        try:
            import subprocess, json
            logger_path = os.path.join(os.path.dirname(__file__), '..', '.claude', 'error-logger.js')
            if os.path.exists(logger_path):
                payload = {
                    'source': 'django',
                    'error_type': exc_type_name,
                    'error_message': f'{request_method} {request_path} — {exc_message}',
                    'stack_trace': tb_text,
                    'tags': ['django', '500', self.env, exc_type_name.lower()]
                }
                subprocess.Popen(
                    ['node', os.path.abspath(logger_path), json.dumps(payload)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
        except Exception:
            pass

        # Store error in database
        error_id = "unknown"
        try:
            from accounts.models import ErrorLog

            error_log = ErrorLog.objects.create(
                exception_type=exc_type_name,
                exception_message=exc_message,
                traceback=tb_text,
                request_path=request_path,
                request_method=request_method,
                request_user=request_user,
                environment=self.env,
                revision=revision,
                severity='error',
                source='unhandled',
                request_data={
                    'GET': dict(request.GET),
                    'POST': self.sanitize_post_data(dict(request.POST)),
                    'headers': {k: v for k, v in request.META.items() if k.startswith('HTTP_')},
                }
            )
            error_id = error_log.error_id
        except Exception as e:
            logger.error(f"Failed to log error to database: {e}")
        
        context = {
            'error_id': error_id,
            'timestamp': timezone.now(),
            'environment': self.env,
            'exception_type': exc_type_name,
            'exception_message': exc_message,
            'traceback': tb_text,
            'request_path': request_path,
            'request_method': request_method,
            'user': request_user,
            'revision': revision,
            'ip_address': self.get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', '—'),
            'referer': request.META.get('HTTP_REFERER', '—'),
        }
        return render(request, 'errors/error.html', context, status=500)
    
    def get_client_ip(self, request):
        """Get the client's IP address from the request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def sanitize_post_data(self, post_data):
        """Remove sensitive data from POST data before logging"""
        sensitive_keys = ['password', 'csrfmiddlewaretoken', 'token', 'api_key', 'secret']
        sanitized = post_data.copy()
        for key in list(sanitized.keys()):
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = ['***REDACTED***']
        return sanitized


class ImpersonationExpiryMiddleware:
    """
    Auto-expires impersonation sessions after 30 minutes.
    Must be placed AFTER AuthenticationMiddleware (needs request.session and request.user).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at_str = request.session.get('impersonate_started_at')
        if started_at_str and hasattr(request, 'user') and request.user.is_authenticated:
            from datetime import datetime
            try:
                started_at = datetime.fromisoformat(started_at_str)
                if started_at.tzinfo is None:
                    started_at = timezone.make_aware(started_at)
                if (timezone.now() - started_at).total_seconds() > 1800:
                    admin_id = request.session.pop('impersonate_admin_id', None)
                    request.session.pop('impersonate_started_at', None)
                    request.session.pop('impersonation_log_id', None)
                    if admin_id:
                        from accounts.models import User
                        from django.contrib.auth import login
                        from django.contrib import messages
                        try:
                            admin_user = User.objects.get(id=admin_id)
                            login(request, admin_user, backend='django.contrib.auth.backends.ModelBackend')
                            messages.warning(request, "Impersonation expired after 30 minutes.", fail_silently=True)
                        except User.DoesNotExist:
                            pass
            except (ValueError, TypeError):
                pass

        response = self.get_response(request)
        return response