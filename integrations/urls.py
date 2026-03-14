"""
Integrations App URLs
Cross-integration features and sync management
"""

from django.urls import path
from integrations import views_scheduled_jobs, views_monitoring

app_name = 'integrations'

urlpatterns = [
    # Scheduled Jobs Manager (DB-driven cron)
    path('scheduled-jobs/', views_scheduled_jobs.scheduled_jobs_list, name='scheduled_jobs'),
    path('scheduled-jobs/tick/', views_scheduled_jobs.scheduled_jobs_tick, name='scheduled_jobs_tick'),
    path('scheduled-jobs/<int:job_id>/edit/', views_scheduled_jobs.scheduled_job_edit, name='scheduled_job_edit'),
    path('scheduled-jobs/<int:job_id>/run-now/', views_scheduled_jobs.scheduled_job_run_now, name='scheduled_job_run_now'),

    # Monitoring dashboard
    path('monitoring/', views_monitoring.monitoring_dashboard, name='monitoring_dashboard'),

    # Maintenance workers
    path('workers/cleanup-synclogs/', views_scheduled_jobs.worker_cleanup_synclogs, name='worker_cleanup_synclogs'),
]
