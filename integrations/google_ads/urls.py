"""
Google Ads URL Configuration
"""

from django.urls import path
from . import views, workers

app_name = 'google_ads'

urlpatterns = [
    # Main views
    path('', views.dashboard, name='dashboard'),
    path('detailed-report/', views.detailed_report, name='detailed_report'),
    path('search-terms/', views.search_terms, name='search_terms'),

    # Settings (Admin only)
    # path('settings/', views.settings, name='settings'),  # DEPRECATED: Use integrations hub instead

    # OAuth2 flow
    path('oauth-start/', views.oauth_start, name='oauth_start'),
    path('oauth2callback/', views.oauth_callback, name='oauth_callback'),
    path('disconnect/<int:token_id>/', views.disconnect, name='disconnect'),

    # AJAX sync endpoints
    path('sync/<int:token_id>/', views.sync_account, name='sync_account'),
    path('sync-all/', views.sync_all_accounts, name='sync_all_accounts'),
    path('sync-historical/<int:token_id>/', views.sync_historical, name='sync_historical'),
    path('sync-date-range/<int:token_id>/', views.sync_date_range, name='sync_date_range'),
    path('sync-progress/<int:token_id>/', views.sync_progress, name='sync_progress'),
    path('stop-sync/', views.stop_sync, name='stop_sync'),
    path('force-stop-sync/', views.force_stop_sync, name='force_stop_sync'),

    # Logs
    path('logs/', views.sync_logs, name='sync_logs'),
    path('api/sync-logs/<int:batch_id>/', views.api_sync_logs, name='api_sync_logs'),

    # Export
    path('export/', views.export_data, name='export_data'),

    # Cloud Tasks worker endpoints
    path('workers/sync-account/', workers.sync_google_ads_account_worker, name='worker_sync_account'),
    path('workers/sync-all-accounts/', workers.sync_all_google_ads_accounts_worker, name='worker_sync_all_accounts'),
    path('workers/sync-historical/', workers.sync_historical_data_worker, name='worker_sync_historical'),
]
