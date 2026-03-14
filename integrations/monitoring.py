"""
Job Monitoring & Credits Computation Module.

Provides credit computation and aggregation queries for the monitoring dashboard
and the scheduled jobs summary section.

Two tracking dimensions:
  1. GCP Cost — actual Cloud Run + Cloud Tasks billing per job run
  2. API Credits — per-integration quota consumption (% of daily limit)
"""

from datetime import timedelta
from django.conf import settings
from django.db.models import (
    Avg, Count, F, Q, Sum, Value, CharField,
)
from django.db.models.functions import TruncDate
from django.utils import timezone


def get_credits_config():
    """Read JOB_CREDITS_CONFIG from settings."""
    return getattr(settings, 'JOB_CREDITS_CONFIG', {})


# ── GCP cost helpers ──────────────────────────────────────────────


def compute_gcp_cost(duration_seconds):
    """
    Compute Cloud Run + Cloud Tasks dispatch cost for a single job run.
    Returns cost in USD (float).
    """
    cfg = get_credits_config()
    if not duration_seconds:
        duration_seconds = 0
    vcpu_cost = duration_seconds * cfg.get('COST_PER_VCPU_SECOND', 0)
    gib_cost = duration_seconds * cfg.get('COST_PER_GIB_SECOND', 0)
    dispatch_cost = cfg.get('COST_PER_TASK_DISPATCH', 0)
    return vcpu_cost + gib_cost + dispatch_cost


# ── API credit helpers ────────────────────────────────────────────


def compute_api_credits(api_calls_count, integration):
    """Return API credits consumed using per-integration rates."""
    cfg = get_credits_config()
    rate = cfg.get('API_CREDITS_PER_CALL', {}).get(integration, 0)
    return (api_calls_count or 0) * rate


def get_daily_quota(integration):
    """Return the daily API quota limit for an integration (or None)."""
    cfg = get_credits_config()
    return cfg.get('DAILY_API_QUOTA', {}).get(integration)


def get_quota_pct(api_credits, integration):
    """Return % of daily quota used, or None if no limit."""
    limit = get_daily_quota(integration)
    if not limit:
        return None
    return round(api_credits / limit * 100, 2)


# ── Aggregation queries ──────────────────────────────────────────


def _batch_logs_qs(start_date=None, end_date=None, integration=None):
    """Base queryset: batch SyncLogs in a date range, optionally filtered."""
    from integrations.models import SyncLog
    qs = SyncLog.objects.filter(log_kind='batch')
    if start_date:
        qs = qs.filter(started_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(started_at__date__lte=end_date)
    if integration:
        qs = qs.filter(integration=integration)
    return qs


def get_today_summary():
    """
    Aggregate today's batch SyncLogs into a summary dict.
    Used on the Scheduled Jobs page.
    """
    today = timezone.localdate()
    qs = _batch_logs_qs(start_date=today, end_date=today)

    agg = qs.aggregate(
        total_runs=Count('id'),
        total_duration=Sum('duration_seconds'),
        avg_duration=Avg('duration_seconds'),
        total_api_calls=Sum('api_calls_count'),
        failed_count=Count('id', filter=Q(status='failed')),
    )

    total_duration = agg['total_duration'] or 0
    total_api_calls = agg['total_api_calls'] or 0

    # GCP cost for all runs today
    gcp_cost = compute_gcp_cost(total_duration)
    # Add per-dispatch cost for each additional run beyond the first
    cfg = get_credits_config()
    dispatch_cost_per_run = cfg.get('COST_PER_TASK_DISPATCH', 0)
    total_runs = agg['total_runs'] or 0
    gcp_cost += dispatch_cost_per_run * max(total_runs - 1, 0)  # first already counted

    # Per-integration quota usage
    per_integration = (
        qs.values('integration')
        .annotate(api_calls=Sum('api_calls_count'))
        .order_by('integration')
    )
    quota_usage = {}
    for row in per_integration:
        integ = row['integration']
        credits = compute_api_credits(row['api_calls'], integ)
        pct = get_quota_pct(credits, integ)
        quota_usage[integ] = {
            'api_calls': row['api_calls'] or 0,
            'credits': credits,
            'quota_pct': pct,
        }

    # Worst-case quota %
    max_quota_pct = max(
        (v['quota_pct'] for v in quota_usage.values() if v['quota_pct'] is not None),
        default=0,
    )

    return {
        'total_runs': total_runs,
        'avg_duration': round(agg['avg_duration'] or 0, 1),
        'total_api_calls': total_api_calls,
        'max_quota_pct': max_quota_pct,
        'gcp_cost_usd': round(gcp_cost, 6),
        'failed_count': agg['failed_count'] or 0,
        'per_integration': quota_usage,
    }


def get_per_job_summary(date):
    """
    Per-ScheduledJob stats for a given date.
    Returns list of dicts with job attribution.
    """
    qs = _batch_logs_qs(start_date=date, end_date=date).filter(
        scheduled_job__isnull=False,
    )
    rows = (
        qs.values('scheduled_job_id', 'integration')
        .annotate(
            runs_today=Count('id'),
            total_duration=Sum('duration_seconds'),
            total_api_calls=Sum('api_calls_count'),
            failed=Count('id', filter=Q(status='failed')),
        )
        .order_by('scheduled_job_id')
    )
    result = []
    for r in rows:
        credits = compute_api_credits(r['total_api_calls'], r['integration'])
        gcp = compute_gcp_cost(r['total_duration'] or 0)
        result.append({
            'scheduled_job_id': r['scheduled_job_id'],
            'integration': r['integration'],
            'runs_today': r['runs_today'],
            'total_duration': r['total_duration'] or 0,
            'total_api_calls': r['total_api_calls'] or 0,
            'credits_today': credits,
            'gcp_cost': round(gcp, 6),
            'failed': r['failed'],
        })
    return result


def get_monitoring_data(start_date, end_date, integration=None):
    """
    Full dashboard data for the monitoring page.
    Returns dict with KPIs, chart series, and execution history.
    """
    qs = _batch_logs_qs(start_date=start_date, end_date=end_date, integration=integration)

    # ── KPIs ──
    agg = qs.aggregate(
        total_runs=Count('id'),
        avg_duration=Avg('duration_seconds'),
        total_api_calls=Sum('api_calls_count'),
        total_duration=Sum('duration_seconds'),
        failed_count=Count('id', filter=Q(status='failed')),
    )

    total_duration = agg['total_duration'] or 0
    gcp_cost = compute_gcp_cost(total_duration)
    cfg = get_credits_config()
    dispatch_per = cfg.get('COST_PER_TASK_DISPATCH', 0)
    total_runs = agg['total_runs'] or 0
    gcp_cost += dispatch_per * max(total_runs - 1, 0)

    # ── Per-integration API quota for the period ──
    per_integ = (
        qs.values('integration')
        .annotate(api_calls=Sum('api_calls_count'))
        .order_by('integration')
    )
    quota_summary = {}
    for row in per_integ:
        integ = row['integration']
        credits = compute_api_credits(row['api_calls'], integ)
        quota_summary[integ] = {
            'api_calls': row['api_calls'] or 0,
            'credits': credits,
            'quota_pct': get_quota_pct(credits, integ),
        }

    # ── Daily series for charts ──
    daily = (
        qs.annotate(day=TruncDate('started_at'))
        .values('day')
        .annotate(
            runs=Count('id'),
            duration=Sum('duration_seconds'),
            api_calls=Sum('api_calls_count'),
            failed=Count('id', filter=Q(status='failed')),
        )
        .order_by('day')
    )
    chart_dates = []
    chart_runs = []
    chart_duration = []
    chart_api_calls = []
    chart_gcp_cost = []
    chart_failed = []
    for d in daily:
        chart_dates.append(d['day'].isoformat() if d['day'] else '')
        chart_runs.append(d['runs'])
        chart_duration.append(d['duration'] or 0)
        chart_api_calls.append(d['api_calls'] or 0)
        chart_gcp_cost.append(round(compute_gcp_cost(d['duration'] or 0), 6))
        chart_failed.append(d['failed'])

    # ── Daily per-integration API calls (for stacked bar) ──
    daily_per_integ = (
        qs.annotate(day=TruncDate('started_at'))
        .values('day', 'integration')
        .annotate(api_calls=Sum('api_calls_count'))
        .order_by('day', 'integration')
    )
    # Build {integration: [calls_day1, calls_day2, ...]}
    integ_series = {}
    for row in daily_per_integ:
        integ = row['integration']
        if integ not in integ_series:
            integ_series[integ] = {}
        day_str = row['day'].isoformat() if row['day'] else ''
        integ_series[integ][day_str] = row['api_calls'] or 0

    # Align to chart_dates
    api_by_integration = {}
    for integ, day_map in integ_series.items():
        api_by_integration[integ] = [day_map.get(d, 0) for d in chart_dates]

    # ── Execution history (recent batch logs) ──
    history_qs = qs.select_related('scheduled_job').order_by('-started_at')[:50]
    history = []
    for log in history_qs:
        credits = compute_api_credits(log.api_calls_count, log.integration)
        history.append({
            'id': log.id,
            'started_at': log.started_at.isoformat(),
            'started_at_display': log.started_at.strftime('%Y-%m-%d %H:%M'),
            'job_name': log.scheduled_job.name if log.scheduled_job else 'Manual / Unknown',
            'integration': log.integration,
            'integration_display': log.get_integration_display(),
            'sync_type': log.get_sync_type_display(),
            'duration': log.duration_display,
            'duration_seconds': log.duration_seconds or 0,
            'api_calls': log.api_calls_count,
            'api_credits': credits,
            'gcp_cost': round(compute_gcp_cost(log.duration_seconds or 0), 6),
            'status': log.status,
            'records_synced': log.total_records_synced,
        })

    return {
        'kpis': {
            'total_runs': total_runs,
            'avg_duration': round(agg['avg_duration'] or 0, 1),
            'total_api_calls': agg['total_api_calls'] or 0,
            'gcp_cost_usd': round(gcp_cost, 6),
            'failed_count': agg['failed_count'] or 0,
        },
        'quota_summary': quota_summary,
        'chart': {
            'dates': chart_dates,
            'runs': chart_runs,
            'duration': chart_duration,
            'api_calls': chart_api_calls,
            'gcp_cost': chart_gcp_cost,
            'failed': chart_failed,
            'api_by_integration': api_by_integration,
        },
        'history': history,
    }


def get_quota_limits_table():
    """
    Per-integration daily quota status: limit, used today, remaining, % used.
    """
    today = timezone.localdate()
    qs = _batch_logs_qs(start_date=today, end_date=today)
    per_integ = (
        qs.values('integration')
        .annotate(api_calls=Sum('api_calls_count'))
        .order_by('integration')
    )

    cfg = get_credits_config()
    all_integrations = list(cfg.get('API_CREDITS_PER_CALL', {}).keys())
    usage_map = {r['integration']: r['api_calls'] or 0 for r in per_integ}

    rows = []
    for integ in all_integrations:
        api_calls = usage_map.get(integ, 0)
        credits = compute_api_credits(api_calls, integ)
        limit = get_daily_quota(integ)
        if limit is None:
            rows.append({
                'integration': integ,
                'daily_limit': None,
                'used': credits,
                'remaining': None,
                'pct': None,
            })
        else:
            pct = round(credits / limit * 100, 2) if limit else 0
            rows.append({
                'integration': integ,
                'daily_limit': limit,
                'used': credits,
                'remaining': max(limit - credits, 0),
                'pct': pct,
            })
    return rows


def forecast_credits(days_ahead=7):
    """
    Forecast API credit consumption for the next N days.
    Uses croniter to count expected fires per job, multiplied by
    avg API calls from the last 20 runs of that job.
    """
    from integrations.models import ScheduledJob, SyncLog

    try:
        from croniter import croniter
    except ImportError:
        return []

    now = timezone.now()
    end = now + timedelta(days=days_ahead)

    jobs = ScheduledJob.objects.filter(is_enabled=True)
    result = []

    for job in jobs:
        # Count expected fires in the forecast window
        try:
            cron = croniter(job.cron_schedule, now)
        except (ValueError, TypeError):
            continue

        expected_fires = 0
        while True:
            nxt = cron.get_next(type(now))
            if nxt > end:
                break
            expected_fires += 1

        if expected_fires == 0:
            continue

        # Avg API calls from the last 20 runs of this job
        recent = (
            SyncLog.objects.filter(
                log_kind='batch',
                scheduled_job=job,
            )
            .order_by('-started_at')[:20]
            .aggregate(
                avg_api=Avg('api_calls_count'),
                avg_dur=Avg('duration_seconds'),
            )
        )
        avg_api = recent['avg_api'] or 0
        avg_dur = recent['avg_dur'] or 0

        forecast_api = round(expected_fires * avg_api)
        forecast_credits_val = compute_api_credits(forecast_api, job.integration)
        forecast_gcp = round(compute_gcp_cost(avg_dur) * expected_fires, 6)

        result.append({
            'job_id': job.pk,
            'job_name': job.name,
            'integration': job.integration,
            'integration_display': job.get_integration_display(),
            'cron': job.cron_schedule,
            'expected_fires': expected_fires,
            'avg_api_per_run': round(avg_api, 1),
            'avg_duration_per_run': round(avg_dur, 1),
            'forecast_api_calls': forecast_api,
            'forecast_credits': forecast_credits_val,
            'forecast_gcp_cost': forecast_gcp,
        })

    return sorted(result, key=lambda r: r['forecast_credits'], reverse=True)
