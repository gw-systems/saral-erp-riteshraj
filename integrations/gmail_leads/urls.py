"""
Gmail Leads URL Configuration
"""

from django.urls import path
from . import views, workers

app_name = 'gmail_leads'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Settings (Admin only)
    # path('settings/', views.settings, name='settings'),  # DEPRECATED: Use integrations hub instead

    # OAuth2 Connection
    path('connect/', views.connect, name='connect'),
    path('oauth/callback/', views.oauth_callback, name='oauth_callback'),
    path('oauth2callback/', views.oauth_callback),  # Matches Google Cloud Console redirect URI
    path('disconnect/<int:token_id>/', views.disconnect, name='disconnect'),

    # AJAX endpoints
    path('sync/<int:token_id>/', views.sync_account, name='sync_account'),
    path('sync-all/', views.sync_all_accounts, name='sync_all_accounts'),
    path('sync-date-range/<int:token_id>/', views.sync_date_range_view, name='sync_date_range'),
    path('sync-progress/<int:token_id>/', views.sync_progress, name='sync_progress'),
    path('stop-sync/', views.stop_sync, name='stop_sync'),
    path('force-stop-sync/', views.force_stop_sync, name='force_stop_sync'),
    path('update-exclusions/<int:token_id>/', views.update_exclusions, name='update_exclusions'),

    # Logs
    path('logs/', views.sync_logs, name='sync_logs'),
    path('api/sync-logs/<int:batch_id>/', views.api_sync_logs, name='api_sync_logs'),

    # Cloud Tasks worker endpoints
    path('workers/sync-account/', workers.sync_gmail_leads_account_worker, name='worker_sync_account'),
    path('workers/sync-all-accounts/', workers.sync_all_gmail_leads_accounts_worker, name='worker_sync_all_accounts'),
]
