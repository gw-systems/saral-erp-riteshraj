import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pydantic import BaseModel, Field, ValidationError, field_validator

from integration_workers.auth import get_cloud_tasks_task_name, require_cloud_tasks_auth

from .sync_service import ApolloSyncEngine

logger = logging.getLogger(__name__)


class ApolloSyncPayload(BaseModel):
    sync_type: str = Field(default='incremental')
    start_date: str | None = None
    end_date: str | None = None
    triggered_by_user: str | None = None
    batch_log_id: int | None = None
    scheduled_job_id: int | None = None
    reset_checkpoint: bool = False

    @field_validator('sync_type')
    @classmethod
    def validate_sync_type(cls, value):
        if value not in {'incremental', 'full'}:
            raise ValueError("sync_type must be 'incremental' or 'full'")
        return value


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def sync_worker(request):
    task_info = get_cloud_tasks_task_name(request)
    try:
        raw_payload = json.loads(request.body or '{}')
        payload = ApolloSyncPayload(**raw_payload)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'error': 'Invalid JSON payload'}, status=400)
    except ValidationError as exc:
        return JsonResponse({'status': 'error', 'error': str(exc)}, status=400)

    try:
        engine = ApolloSyncEngine(
            sync_type=payload.sync_type,
            batch_log_id=payload.batch_log_id,
            triggered_by_user=payload.triggered_by_user,
            scheduled_job_id=payload.scheduled_job_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            reset_checkpoint=payload.reset_checkpoint,
        )
        stats = engine.sync()
        return JsonResponse({
            'status': 'success',
            'task_name': task_info.get('task_name'),
            'retry_count': task_info.get('retry_count'),
            'stats': stats,
            'batch_log_id': engine.batch_log.id,
        })
    except Exception as exc:
        logger.error(f'[Apollo] Worker sync failed: {exc}', exc_info=True)
        return JsonResponse({'status': 'error', 'error': str(exc)}, status=500)
