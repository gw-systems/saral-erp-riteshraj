"""
DB-driven scheduled job tick engine.

One master GCP Cloud Scheduler job fires every minute:
    POST /integrations/scheduled-jobs/tick/

This module reads the ScheduledJob table, determines which jobs are due
based on their cron expression, and fires them via Cloud Tasks.

No changes needed to existing worker endpoints.
"""
import logging
from datetime import timedelta, datetime

from croniter import croniter
from django.utils import timezone

from integration_workers import create_task
from .models import ScheduledJob

logger = logging.getLogger(__name__)


def run_tick():
    """
    Called every minute by the master Cloud Scheduler job.

    Evaluates every enabled ScheduledJob. If the job's cron expression
    matches the current minute, fires a Cloud Task to its endpoint.

    Returns:
        list[str]: Names of jobs that were fired this tick.
    """
    now = timezone.now().replace(second=0, microsecond=0)
    fired = []
    errors = []

    enabled_jobs = ScheduledJob.objects.filter(is_enabled=True)
    logger.info(f"[ScheduledTick] Tick at {now.isoformat()} — evaluating {enabled_jobs.count()} enabled jobs")

    for job in enabled_jobs:
        try:
            # croniter needs a start point just before now to compute the next run
            start = now - timedelta(minutes=1)
            cron = croniter(job.cron_schedule, start)
            next_run = cron.get_next(datetime)

            # Normalize to minute precision for comparison
            next_run_minute = next_run.replace(second=0, microsecond=0)

            # Make next_run_minute timezone-aware if now is aware
            if timezone.is_aware(now) and timezone.is_naive(next_run_minute):
                import pytz
                next_run_minute = pytz.utc.localize(next_run_minute)

            if next_run_minute == now:
                enriched_payload = {**job.payload, 'scheduled_job_id': job.pk}
                logger.info(f"[ScheduledTick] Firing job '{job.name}' → {job.endpoint} payload={enriched_payload}")
                create_task(endpoint=job.endpoint, payload=enriched_payload)

                job.last_fired_at = now
                job.last_fired_result = 'ok'
                job.save(update_fields=['last_fired_at', 'last_fired_result'])

                fired.append(job.name)
                logger.info(f"[ScheduledTick] Job '{job.name}' fired successfully")
            else:
                logger.debug(f"[ScheduledTick] Job '{job.name}' not due (next={next_run_minute.isoformat()})")

        except Exception as e:
            logger.error(f"[ScheduledTick] Error evaluating job '{job.name}': {e}", exc_info=True)
            try:
                job.last_fired_result = 'error'
                job.save(update_fields=['last_fired_result'])
            except Exception:
                pass
            errors.append(job.name)

    logger.info(
        f"[ScheduledTick] Done: {len(fired)} fired, {len(errors)} errors. "
        f"Fired: {fired or 'none'}"
    )
    return fired
