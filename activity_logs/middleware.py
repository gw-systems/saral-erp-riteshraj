import threading
import time

_thread_locals = threading.local()


def get_current_request():
    """Get HTTP request stored by middleware. Returns None for cron/signal sources."""
    return getattr(_thread_locals, 'request', None)


def get_client_ip(request):
    """Extract real IP handling proxies."""
    if not request:
        return None
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


# URLs to skip — never log these
SKIP_PREFIXES = (
    '/static/', '/media/', '/favicon',
    '/activity/api/feed/',      # feed polling — too noisy
    '/activity/api/month/',     # calendar API — read-only
    '/activity/api/week/',
    '/health', '/__debug__',
)

SKIP_EXTENSIONS = ('.js', '.css', '.png', '.jpg', '.ico', '.woff', '.woff2', '.map')


class ActivityLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Store request in thread-local so signals can access it
        _thread_locals.request = request
        _thread_locals.request_start = time.time()

        try:
            response = self.get_response(request)
        except Exception:
            _thread_locals.request = None
            raise

        elapsed_ms = int((time.time() - _thread_locals.request_start) * 1000)

        try:
            if self._should_log(request, response):
                self._log_request(request, response, elapsed_ms)
        except Exception:
            pass  # never let logging crash the response

        _thread_locals.request = None
        return response

    def process_exception(self, request, exception):
        """Log unhandled 500 errors."""
        try:
            from .utils import log_activity_direct
            log_activity_direct(
                user=getattr(request, 'user', None),
                source='web',
                action_category='system',
                action_type='unhandled_exception',
                module='system',
                description=f'Unhandled exception: {type(exception).__name__}: {str(exception)[:200]}',
                request=request,
                is_suspicious=True,
                extra_data={'exception_type': type(exception).__name__,
                            'exception_msg': str(exception)[:500]},
            )
        except Exception:
            pass

    def _should_log(self, request, response):
        path = request.path

        # Skip static/media/polling
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return False
        if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
            return False

        # Skip anonymous users (not logged in)
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            # Still log failed logins (handled by auth signal)
            return False

        # Always log state-changing requests
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return True

        # Log permission denied
        if response.status_code == 403:
            return True

        # Skip GET requests (model signals handle the interesting ones)
        return False

    def _log_request(self, request, response, elapsed_ms):
        from .utils import log_activity_direct

        # Determine category from response
        if response.status_code == 403:
            category = 'permission_denied'
            action_type = 'access_denied'
        elif request.method == 'DELETE':
            category = 'delete'
            action_type = 'record_deleted'
        elif request.method == 'POST':
            category = 'create'
            action_type = 'form_submitted'
        else:
            category = 'update'
            action_type = 'record_updated'

        # Check for file download (export)
        content_disp = response.get('Content-Disposition', '')
        if 'attachment' in content_disp:
            category = 'export'
            action_type = 'file_downloaded'

        log_activity_direct(
            user=request.user,
            source='web',
            action_category=category,
            action_type=action_type,
            module=_guess_module(request.path),
            description=f'{request.method} {request.path}',
            request=request,
            extra_data={
                'content_disposition': content_disp[:200] if content_disp else '',
            },
            status_code=response.status_code,
            response_time_ms=elapsed_ms,
        )


def _guess_module(path):
    """Infer module name from URL path."""
    parts = path.strip('/').split('/')
    if not parts or not parts[0]:
        return 'unknown'
    mapping = {
        'activity': 'activity_logs',
        'operations': 'operations',
        'projects': 'projects',
        'accounts': 'accounts',
        'supply': 'supply',
        'integrations': 'integrations',
        'billing': 'billing',
    }
    return mapping.get(parts[0], parts[0])
