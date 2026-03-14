"""
Callyzer URL Configuration
"""

from django.urls import path
from . import views, workers

app_name = 'callyzer'

urlpatterns = [
    # Main views
    path('', views.dashboard, name='dashboard'),
    path('analytics/', views.analytics, name='analytics'),
    path('reports/', views.reports, name='reports'),

    # Settings (Admin only)
    # path('settings/', views.settings, name='settings'),  # DEPRECATED: Use integrations hub instead

    # Connection management
    path('connect/', views.connect, name='connect'),
    path('disconnect/<int:token_id>/', views.disconnect, name='disconnect'),

    # AJAX sync endpoints
    path('sync/<int:token_id>/', views.sync_account, name='sync_account'),
    path('sync-all/', views.sync_all_accounts, name='sync_all_accounts'),
    path('sync-progress/<int:token_id>/', views.sync_progress, name='sync_progress'),
    path('stop-sync/', views.stop_sync, name='stop_sync'),
    path('force-stop-sync/', views.force_stop_sync, name='force_stop_sync'),

    # Logs
    path('logs/', views.sync_logs, name='sync_logs'),
    path('api/sync-logs/<int:batch_id>/', views.api_sync_logs, name='api_sync_logs'),

    # Cloud Tasks worker endpoints
    path('workers/sync-account/', workers.sync_callyzer_account_worker, name='worker_sync_account'),
    path('workers/sync-all-accounts/', workers.sync_all_callyzer_accounts_worker, name='worker_sync_all_accounts'),
]
