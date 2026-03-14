"""
Monitoring dashboard view.

Full dashboard at /integrations/monitoring/ showing:
  - KPI cards (runs, duration, API calls, GCP cost, failures)
  - Charts: API calls over time, GCP cost trend, duration trend
  - API quota limits table
  - Forecast table
  - Execution history
"""

import json
import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone

from .monitoring import (
    get_monitoring_data,
    get_quota_limits_table,
    forecast_credits,
)

logger = logging.getLogger(__name__)

INTEGRATION_COLORS = {
    'bigin': 'rgb(99, 102, 241)',       # indigo
    'gmail_leads': 'rgb(56, 189, 248)',  # sky
    'gmail': 'rgb(236, 72, 153)',        # pink
    'google_ads': 'rgb(239, 68, 68)',    # red
    'callyzer': 'rgb(249, 115, 22)',     # orange
    'tallysync': 'rgb(52, 211, 153)',    # emerald
    'expense_log': 'rgb(234, 179, 8)',   # yellow
}

INTEGRATION_LABELS = {
    'bigin': 'Bigin CRM',
    'gmail_leads': 'Gmail Leads',
    'gmail': 'Gmail',
    'google_ads': 'Google Ads',
    'callyzer': 'Callyzer',
    'tallysync': 'TallySync',
    'expense_log': 'Expense Log',
}


def _is_admin_or_director(user):
    return user.is_authenticated and getattr(user, 'role', None) in ('admin', 'director')


@login_required
def monitoring_dashboard(request):
    """Render the full monitoring dashboard."""
    if not _is_admin_or_director(request.user):
        return HttpResponseForbidden("Access restricted to admins and directors.")

    # Parse date range from GET params (default: last 7 days)
    today = timezone.localdate()
    start_str = request.GET.get('start_date', '')
    end_str = request.GET.get('end_date', '')
    integration_filter = request.GET.get('integration', '')
    forecast_days = int(request.GET.get('forecast_days', '7'))

    from datetime import date as date_cls
    try:
        start_date = date_cls.fromisoformat(start_str) if start_str else today - timedelta(days=6)
    except ValueError:
        start_date = today - timedelta(days=6)
    try:
        end_date = date_cls.fromisoformat(end_str) if end_str else today
    except ValueError:
        end_date = today

    # Fetch data
    data = get_monitoring_data(
        start_date, end_date,
        integration=integration_filter or None,
    )
    quota_table = get_quota_limits_table()
    forecast = forecast_credits(days_ahead=forecast_days)

    # Build Chart.js datasets for per-integration stacked bar
    api_datasets = []
    for integ, values in data['chart']['api_by_integration'].items():
        api_datasets.append({
            'label': INTEGRATION_LABELS.get(integ, integ),
            'data': values,
            'backgroundColor': INTEGRATION_COLORS.get(integ, 'rgb(156, 163, 175)'),
        })

    integrations_list = [
        {'value': k, 'label': v}
        for k, v in INTEGRATION_LABELS.items()
    ]

    return render(request, 'integrations/monitoring.html', {
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'integration_filter': integration_filter,
        'forecast_days': forecast_days,
        'integrations_list': integrations_list,
        'kpis': data['kpis'],
        'quota_summary': data['quota_summary'],
        'chart_dates_json': json.dumps(data['chart']['dates']),
        'chart_runs_json': json.dumps(data['chart']['runs']),
        'chart_duration_json': json.dumps(data['chart']['duration']),
        'chart_api_calls_json': json.dumps(data['chart']['api_calls']),
        'chart_gcp_cost_json': json.dumps(data['chart']['gcp_cost']),
        'chart_failed_json': json.dumps(data['chart']['failed']),
        'api_datasets_json': json.dumps(api_datasets),
        'quota_table': quota_table,
        'forecast': forecast,
        'history': data['history'],
        'integration_colors': INTEGRATION_COLORS,
    })
