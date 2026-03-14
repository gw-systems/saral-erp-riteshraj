"""
Views for the DB-driven scheduled jobs manager.

Endpoints:
  GET  /integrations/scheduled-jobs/           → Admin management page
  POST /integrations/scheduled-jobs/<id>/edit/ → Update job (cron, enabled, payload, name)
  POST /integrations/scheduled-jobs/<id>/run-now/ → Fire job immediately via create_task
  POST /integrations/scheduled-jobs/tick/      → Called by master Cloud Scheduler (auth required)
"""
import json
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from integration_workers import create_task
from integration_workers.auth import require_cloud_tasks_auth
from .models import ScheduledJob
from .monitoring import get_today_summary, get_per_job_summary
from .scheduled_jobs import run_tick

logger = logging.getLogger(__name__)


def _is_admin_or_director(user):
    return user.is_authenticated and getattr(user, 'role', None) in ('admin', 'director')


def _cron_human(expr):
    """Convert a 5-field cron expression to a human-readable string."""
    if not expr:
        return 'No schedule set'
    parts = expr.strip().split()
    if len(parts) != 5:
        return expr
    min_, hr, dom, mon, dow = parts
    if min_.startswith('*/') and hr == '*' and dom == '*' and mon == '*' and dow == '*':
        n = min_[2:]
        return f'Every {n} minutes'
    if min_ == '0' and hr == '*' and dom == '*' and mon == '*' and dow == '*':
        return 'Every hour'
    if min_ == '0' and hr.startswith('*/') and dom == '*' and mon == '*' and dow == '*':
        return f'Every {hr[2:]} hours'
    if min_ == '0' and '/' not in hr and hr != '*' and dom == '*' and mon == '*' and dow == '*':
        h = int(hr)
        ampm = 'PM' if h >= 12 else 'AM'
        h12 = h % 12 or 12
        return f'Daily at {h12}:00 {ampm}'
    if min_.startswith('*/') and dom == '*' and mon == '*' and dow == '*' and hr != '*':
        return f'Every {min_[2:]} min (hour {hr})'
    return expr


def _payload_human(payload):
    """Convert a job payload dict to a human-readable summary."""
    if not payload:
        return ''
    parts = []
    for k, v in payload.items():
        if k in ('days', 'days_back'):
            parts.append(f'{v} days back')
        elif k == 'run_full':
            parts.append('Full sync' if v else 'Incremental')
        elif k == 'force_full':
            parts.append('Force full sync' if v else 'Incremental')
        elif k == 'sync_yesterday':
            if v:
                parts.append('Sync yesterday')
        elif k == 'sync_current_month_search_terms':
            if v:
                parts.append('+ search terms')
        else:
            parts.append(f'{k.replace("_", " ")}: {v}')
    return ' · '.join(parts)


@login_required
def scheduled_jobs_list(request):
    """Render the scheduled jobs management page (admin/director only)."""
    if not _is_admin_or_director(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access restricted to admins and directors.")

    jobs = ScheduledJob.objects.all()
    # Enrich each job with display-ready fields
    for job in jobs:
        job.cron_human = _cron_human(job.cron_schedule)
        job.payload_human = _payload_human(job.payload)
        # Serialize payload as valid JSON string for Alpine.js template (escaped via |escapejs)
        job.payload_json = json.dumps(job.payload or {})
    enabled_count = sum(1 for j in jobs if j.is_enabled)

    # Monitoring summary
    from django.utils import timezone
    today_summary = get_today_summary()
    per_job_stats = get_per_job_summary(timezone.localdate())
    job_stats_map = {s['scheduled_job_id']: s for s in per_job_stats}
    for job in jobs:
        stats = job_stats_map.get(job.pk, {})
        job.runs_today = stats.get('runs_today', 0)
        job.api_calls_today = stats.get('total_api_calls', 0)
        job.credits_today = stats.get('credits_today', 0)

    return render(request, 'integrations/scheduled_jobs.html', {
        'jobs': jobs,
        'enabled_count': enabled_count,
        'paused_count': len(jobs) - enabled_count,
        'today_summary': today_summary,
    })


@login_required
@require_POST
def scheduled_job_edit(request, job_id):
    """
    Update a scheduled job's name, cron schedule, payload, and enabled state.
    Records who made the change via updated_by.
    """
    if not _is_admin_or_director(request.user):
        return JsonResponse({'error': 'Access denied.'}, status=403)

    job = get_object_or_404(ScheduledJob, pk=job_id)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    # Validate cron schedule if provided
    cron_schedule = data.get('cron_schedule', job.cron_schedule).strip()
    if cron_schedule:
        try:
            from croniter import croniter
            if not croniter.is_valid(cron_schedule):
                return JsonResponse({'error': f'Invalid cron expression: {cron_schedule}'}, status=400)
        except Exception:
            return JsonResponse({'error': f'Invalid cron expression: {cron_schedule}'}, status=400)

    # Validate payload JSON if provided as string
    payload = data.get('payload', job.payload)
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'payload must be valid JSON.'}, status=400)

    job.name = data.get('name', job.name).strip() or job.name
    job.cron_schedule = cron_schedule
    job.payload = payload
    job.is_enabled = bool(data.get('is_enabled', job.is_enabled))
    if 'endpoint' in data:
        job.endpoint = data['endpoint'].strip()
    job.updated_by = request.user.username
    job.save()

    logger.info(
        f"[ScheduledJobs] Job '{job.name}' updated by {request.user.username}: "
        f"cron={job.cron_schedule}, enabled={job.is_enabled}"
    )

    return JsonResponse({
        'status': 'ok',
        'job': {
            'id': job.pk,
            'name': job.name,
            'cron_schedule': job.cron_schedule,
            'is_enabled': job.is_enabled,
            'updated_by': job.updated_by,
        }
    })


@login_required
@require_POST
def scheduled_job_run_now(request, job_id):
    """Fire a job immediately via create_task, bypassing the cron schedule."""
    if not _is_admin_or_director(request.user):
        return JsonResponse({'error': 'Access denied.'}, status=403)

    job = get_object_or_404(ScheduledJob, pk=job_id)

    logger.info(
        f"[ScheduledJobs] Manual run of '{job.name}' triggered by {request.user.username}"
    )

    from django.utils import timezone
    enriched_payload = {**job.payload, 'scheduled_job_id': job.pk}
    task_name = create_task(endpoint=job.endpoint, payload=enriched_payload)

    job.last_fired_at = timezone.now()
    job.last_fired_result = 'ok'
    job.save(update_fields=['last_fired_at', 'last_fired_result'])

    return JsonResponse({
        'status': 'ok',
        'message': f"Job '{job.name}' fired.",
        'task_name': task_name,
    })


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def scheduled_jobs_tick(request):
    """
    Called every minute by the master GCP Cloud Scheduler job.
    Evaluates all enabled jobs and fires those whose cron expression matches now.
    """
    logger.info("[ScheduledTick] Tick received from Cloud Scheduler")

    try:
        fired = run_tick()
        return JsonResponse({
            'status': 'ok',
            'fired': fired,
            'count': len(fired),
        })
    except Exception as e:
        logger.error(f"[ScheduledTick] Tick failed: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


@require_cloud_tasks_auth
@csrf_exempt
@require_POST
def worker_cleanup_synclogs(request):
    """
    Worker endpoint for SyncLog cleanup. Deletes entries older than N days.
    Called by the scheduled job system.
    """
    from datetime import timedelta
    from django.utils import timezone
    from .models import SyncLog

    try:
        data = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    days = data.get('days', 90)
    cutoff = timezone.now() - timedelta(days=days)

    qs = SyncLog.objects.filter(started_at__lt=cutoff)
    total = qs.count()

    if total == 0:
        return JsonResponse({'status': 'ok', 'deleted': 0, 'message': 'No old logs to clean up'})

    deleted_total = 0
    batch_size = 5000
    while True:
        batch_ids = list(qs.values_list('id', flat=True)[:batch_size])
        if not batch_ids:
            break
        deleted, _ = SyncLog.objects.filter(id__in=batch_ids).delete()
        deleted_total += deleted

    logger.info(f"[SyncLog Cleanup] Deleted {deleted_total} entries older than {days} days")
    return JsonResponse({'status': 'ok', 'deleted': deleted_total, 'days': days})
