"""
Gmail Integration URLs
"""

from django.urls import path
from gmail import views, workers, actions

app_name = 'gmail'

urlpatterns = [
    # Settings
    path('settings/', views.gmail_settings, name='gmail_settings'),

    # OAuth2 Connection
    path('connect/', views.gmail_connect, name='connect'),
    path('oauth/callback/', views.gmail_oauth_callback, name='oauth_callback'),
    path('disconnect/<int:token_id>/', views.gmail_disconnect, name='disconnect'),

    # Inbox (WhatsApp-style UI)
    path('', views.inbox, name='inbox'),  # Main inbox view
    path('api/thread/<str:thread_id>/', views.thread_detail_api, name='thread_detail_api'),

    # Email Actions
    path('api/mark-read/', actions.mark_as_read, name='mark_as_read'),
    path('api/mark-unread/', actions.mark_as_unread, name='mark_as_unread'),
    path('api/archive/', actions.archive_thread, name='archive_thread'),
    path('api/unarchive/', actions.unarchive_thread, name='unarchive_thread'),
    path('api/toggle-star/', actions.toggle_star, name='toggle_star'),
    path('api/delete/', actions.delete_thread, name='delete_thread'),

    # Compose & Send
    path('api/send/', actions.send_email, name='send_email'),
    path('api/save-draft/', actions.save_draft, name='save_draft'),
    path('api/get-draft/', actions.get_draft, name='get_draft'),

    # Attachments
    path('api/attachment/<int:attachment_id>/download/', actions.download_attachment, name='download_attachment'),

    # Thread & Account API (used by JavaScript)
    path('api/threads/', views.threads_api, name='threads_api'),
    path('api/accounts/', views.get_sender_accounts, name='accounts_api'),
    path('api/sync-status/', views.sync_status_api, name='sync_status_api'),
    path('api/signature/', views.get_signature_api, name='get_signature_api'),

    # Sync logs
    path('sync-logs/', views.sync_logs, name='sync_logs'),
    path('api/sync-logs/<int:batch_id>/', views.api_sync_logs, name='api_sync_logs'),

    # Sync endpoints
    path('ajax/sender-accounts/', views.get_sender_accounts, name='get_sender_accounts'),
    path('ajax/sync/<int:token_id>/', views.sync_account, name='sync_account'),
    path('ajax/sync-all/', views.sync_all_accounts, name='sync_all_accounts'),
    path('ajax/sync-progress/<int:token_id>/', views.sync_progress, name='sync_progress'),
    path('ajax/stop-sync/<int:token_id>/', views.stop_sync, name='stop_sync'),
    path('ajax/force-stop-sync/<int:token_id>/', views.force_stop_sync, name='force_stop_sync'),

    # Cloud Tasks worker endpoints
    path('workers/sync-account/', workers.sync_gmail_account_worker, name='worker_sync_account'),
    path('workers/sync-all-accounts/', workers.sync_all_gmail_accounts_worker, name='worker_sync_all_accounts'),
]
