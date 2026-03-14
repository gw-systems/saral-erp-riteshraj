"""
Cloud Tasks OIDC Authentication Middleware
Verifies that requests to worker endpoints come from Google Cloud Tasks
"""
import logging
from functools import wraps
from django.http import JsonResponse
from django.conf import settings

logger = logging.getLogger(__name__)


def verify_cloud_tasks_request(request):
    """
    Verify that the request came from Google Cloud Tasks or Cloud Scheduler.

    Uses OIDC token validation via Google's tokeninfo endpoint.
    Cloud Scheduler also adds X-CloudScheduler-JobName header as a secondary signal.

    Returns:
        bool: True if request is authenticated, False otherwise
    """
    # In development mode, skip authentication if configured
    if getattr(settings, 'DEBUG', False) and not getattr(settings, 'ENFORCE_CLOUD_TASKS_AUTH', False):
        import os
        if os.environ.get('K_SERVICE'):
            logger.error("SECURITY: DEBUG bypass refused — running on Cloud Run")
            return False
        logger.warning("Cloud Tasks authentication skipped in DEBUG mode")
        return True

    # Get Authorization header
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')

    if not auth_header or not auth_header.startswith('Bearer '):
        logger.warning(f"Missing/invalid Authorization header from {request.META.get('REMOTE_ADDR')}")
        return False

    token = auth_header[7:]  # Remove 'Bearer ' prefix

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        service_url = getattr(settings, 'CLOUD_TASKS_SERVICE_URL', None)
        if not service_url:
            logger.error("CLOUD_TASKS_SERVICE_URL not configured")
            return False

        base_url = service_url.rstrip('/')

        # Cloud Tasks uses full URL as audience; Cloud Scheduler uses base URL.
        # Try both to support either source.
        audiences = [
            f"{base_url}{request.path}",  # Cloud Tasks: full endpoint URL
            base_url,                      # Cloud Scheduler: base service URL
        ]

        claims = None
        last_error = None
        for audience in audiences:
            try:
                claims = id_token.verify_oauth2_token(
                    token,
                    google_requests.Request(),
                    audience=audience
                )
                break  # Success
            except ValueError as e:
                last_error = e
                continue

        if claims is None:
            # Fallback: try alternate cert endpoint for both audiences
            try:
                import urllib.request, json as _json
                certs_url = "https://www.googleapis.com/oauth2/v3/certs"
                with urllib.request.urlopen(certs_url) as resp:
                    certs = _json.loads(resp.read())
                import google.auth.jwt
                for audience in audiences:
                    try:
                        claims = google.auth.jwt.decode(token, certs=certs, audience=audience)
                        break
                    except (ValueError, Exception):
                        continue
            except Exception as e:
                logger.error(f"Fallback cert verification failed: {e}")

        if claims is None:
            logger.warning(f"OIDC token invalid for all audiences: {audiences}. Last error: {last_error}")
            return False

        # Verify token is from expected service account
        expected_email = getattr(settings, 'GCP_SERVICE_ACCOUNT', None)
        if expected_email:
            token_email = claims.get('email', '')
            if token_email != expected_email:
                logger.warning(f"Token email mismatch. Expected: {expected_email}, Got: {token_email}")
                return False

        logger.debug(f"Cloud Tasks/Scheduler request authenticated: {claims.get('email')}")
        return True

    except Exception as e:
        logger.error(f"Token verification failed: {e}", exc_info=True)
        return False


def require_cloud_tasks_auth(view_func):
    """
    Decorator to require Cloud Tasks authentication on worker endpoints

    Usage:
        @require_cloud_tasks_auth
        @csrf_exempt
        @require_POST
        def worker_endpoint(request):
            ...
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not verify_cloud_tasks_request(request):
            logger.warning(
                f"Unauthorized Cloud Tasks request to {request.path} from {request.META.get('REMOTE_ADDR')}"
            )
            return JsonResponse(
                {'error': 'Unauthorized. This endpoint requires Cloud Tasks authentication.'},
                status=403
            )

        return view_func(request, *args, **kwargs)

    return wrapped_view


def get_cloud_tasks_task_name(request):
    """
    Extract the Cloud Tasks task name from request headers

    Cloud Tasks includes several custom headers:
    - X-CloudTasks-TaskName: The name of the task
    - X-CloudTasks-QueueName: The name of the queue
    - X-CloudTasks-TaskRetryCount: Number of retries
    - X-CloudTasks-TaskExecutionCount: Number of executions

    Returns:
        dict: Dictionary with task metadata or empty dict if not from Cloud Tasks
    """
    return {
        'task_name': request.META.get('HTTP_X_CLOUDTASKS_TASKNAME', ''),
        'queue_name': request.META.get('HTTP_X_CLOUDTASKS_QUEUENAME', ''),
        'retry_count': request.META.get('HTTP_X_CLOUDTASKS_TASKRETRYCOUNT', '0'),
        'execution_count': request.META.get('HTTP_X_CLOUDTASKS_TASKEXECUTIONCOUNT', '0'),
    }
