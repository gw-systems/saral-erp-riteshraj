"""
Cloud Tasks client for creating and managing async tasks
Production-grade async task queue for Google Cloud Run
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class CloudTasksClient:
    """
    Client for Google Cloud Tasks - production-grade async task queue

    Features:
    - Native GCP integration (no external broker needed)
    - Auto-scaling with Cloud Run
    - Automatic retries with exponential backoff
    - Up to 30-minute task execution
    - Cost-effective for 500-600 syncs/day workload
    """

    def __init__(self):
        self.project_id = getattr(settings, 'GCP_PROJECT_ID', None)
        self.location = getattr(settings, 'GCP_LOCATION', 'us-central1')
        self.queue_name = getattr(settings, 'CLOUD_TASKS_QUEUE', 'default')
        self.service_url = getattr(settings, 'CLOUD_TASKS_SERVICE_URL', None)

        # Initialize Cloud Tasks client only in production
        self.client = None
        self.use_cloud_tasks = getattr(settings, 'USE_CLOUD_TASKS', False)

        if self.use_cloud_tasks:
            try:
                from google.cloud import tasks_v2
                self.client = tasks_v2.CloudTasksClient()
                self.parent = self.client.queue_path(
                    self.project_id,
                    self.location,
                    self.queue_name
                )
                logger.info(f"[Cloud Tasks] Initialized: {self.parent}")
            except Exception as e:
                logger.warning(f"[Cloud Tasks] Not available: {e}")
                self.use_cloud_tasks = False

    def create_task(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        task_name: Optional[str] = None,
        schedule_time: Optional[datetime] = None,
        max_retries: int = 3,
        timeout: int = 1800  # 30 minutes default
    ) -> Optional[str]:
        """
        Create a Cloud Task

        Args:
            endpoint: Worker endpoint path (e.g., '/workers/google-ads/sync/')
            payload: JSON-serializable task data
            task_name: Optional unique task name (for deduplication)
            schedule_time: Optional future execution time
            max_retries: Maximum retry attempts (default 3)
            timeout: Task timeout in seconds (default 1800 = 30 min)

        Returns:
            Task name if created, None if local execution
        """

        # Local development: resolve endpoint to Django view and call directly in background thread
        if not self.use_cloud_tasks:
            logger.info(f"[Local Dev] Executing task locally: {endpoint}")
            import threading
            import json as _json
            from django.test import RequestFactory
            from django.urls import resolve

            def _run_local():
                try:
                    factory = RequestFactory()
                    fake_request = factory.post(
                        endpoint,
                        data=_json.dumps(payload),
                        content_type='application/json',
                    )
                    match = resolve(endpoint)
                    response = match.func(fake_request, *match.args, **match.kwargs)
                    logger.info(f"[Local Dev] Task completed: {endpoint} → status {response.status_code}")
                except Exception as e:
                    import traceback as _tb
                    tb_text = _tb.format_exc()
                    logger.error(f"[Local Dev] Task execution failed: {e}\n{tb_text}")
                    try:
                        from accounts.models import ErrorLog
                        ErrorLog.objects.create(
                            exception_type=type(e).__name__,
                            exception_message=f"[Worker] {endpoint} — {e}",
                            traceback=tb_text,
                            request_path=endpoint,
                            request_method='POST',
                            environment=settings.ENVIRONMENT if hasattr(settings, 'ENVIRONMENT') else 'development',
                            severity='error',
                            source='worker_thread',
                        )
                    except Exception:
                        pass

            thread = threading.Thread(target=_run_local, daemon=True)
            thread.start()
            return None

        try:
            # Build task request
            task = {
                'http_request': {
                    'http_method': 'POST',
                    'url': f"{self.service_url}{endpoint}",
                    'headers': {
                        'Content-Type': 'application/json',
                        'X-CloudTasks-TaskName': task_name or f"task-{datetime.now().timestamp()}"
                    },
                    'body': json.dumps(payload).encode(),
                    'oidc_token': {
                        'service_account_email': getattr(settings, 'GCP_SERVICE_ACCOUNT', None)
                    }
                },
                'dispatch_deadline': f"{timeout}s"
            }

            # Add custom task name if provided (for deduplication)
            if task_name:
                task['name'] = f"{self.parent}/tasks/{task_name}"

            # Schedule for future if specified
            if schedule_time:
                timestamp = int(schedule_time.timestamp())
                task['schedule_time'] = {'seconds': timestamp}

            # Create the task
            response = self.client.create_task(
                request={'parent': self.parent, 'task': task}
            )

            logger.info(f"[Cloud Tasks] Created: {response.name}")
            return response.name

        except Exception as e:
            logger.error(f"[Cloud Tasks] Failed to create task: {e}")
            # In production, you might want to fallback or raise
            return None


# Singleton instance — reset when settings change (e.g. USE_CLOUD_TASKS toggles)
_cloud_tasks_client = None
_cloud_tasks_client_use_flag = None

def get_client() -> CloudTasksClient:
    """Get or create the Cloud Tasks client singleton.
    Recreates if USE_CLOUD_TASKS setting has changed since last init."""
    global _cloud_tasks_client, _cloud_tasks_client_use_flag
    current_flag = getattr(settings, 'USE_CLOUD_TASKS', False)
    if _cloud_tasks_client is None or _cloud_tasks_client_use_flag != current_flag:
        _cloud_tasks_client = CloudTasksClient()
        _cloud_tasks_client_use_flag = current_flag
    return _cloud_tasks_client


def create_task(
    endpoint: str,
    payload: Dict[str, Any],
    task_name: Optional[str] = None,
    schedule_time: Optional[datetime] = None,
    max_retries: int = 3,
    timeout: int = 1800
) -> Optional[str]:
    """
    Convenience function to create a Cloud Task

    Usage:
        from integration_workers import create_task

        create_task(
            endpoint='/workers/google-ads/sync/',
            payload={'token_id': 123, 'sync_type': 'yesterday'},
            max_retries=3
        )
    """
    client = get_client()
    return client.create_task(
        endpoint=endpoint,
        payload=payload,
        task_name=task_name,
        schedule_time=schedule_time,
        max_retries=max_retries,
        timeout=timeout
    )
