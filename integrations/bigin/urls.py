from django.urls import path
from integrations.bigin import views, views_api, workers

app_name = 'bigin'

urlpatterns = [
    # OAuth
    path('oauth/start/', views.oauth_start, name='oauth_start'),
    path('oauth/callback/', views.oauth_callback, name='oauth_callback'),

    # Main views
    path('dashboard/', views.bigin_dashboard, name='bigin_dashboard'),  # Analytics summary (CRM Executive only)
    path('leads/', views.bigin_leads, name='bigin_leads'),  # Detailed table view (Sales Manager + CRM Executive)

    # Contact CRUD views
    path('contacts/create/', views.create_contact, name='create_contact'),
    path('contacts/<str:bigin_id>/', views.contact_detail, name='contact_detail'),
    path('contacts/<str:bigin_id>/edit/', views.edit_contact, name='edit_contact'),

    # Settings (Admin/Director only)
    # path('settings/', views.settings, name='settings'),  # DEPRECATED: Use integrations hub instead

    # Sync Audit (Admin only)
    path('sync-audit/', views.sync_audit, name='sync_audit'),

    # AJAX endpoints
    path('api/notes/<str:contact_id>/', views.fetch_notes_ajax, name='fetch_notes'),

    # API for Sales Dashboard
    path('api/sales-lead-summary/', views_api.api_sales_lead_summary, name='api_sales_lead_summary'),
    path('api/all-users-summary/', views_api.api_all_users_summary, name='api_all_users_summary'),
    path('api/area-breakdown/', views_api.api_area_breakdown, name='api_area_breakdown'),
    path('api/owners-list/', views_api.api_owners_list, name='api_owners_list'),

    # API for Sync Audit
    path('api/sync-history/', views_api.sync_history_api, name='sync_history_api'),
    path('api/sync-progress/', views_api.sync_progress_api, name='sync_progress_api'),
    path('api/stop-sync/', views_api.stop_sync_api, name='stop_sync_api'),
    path('api/force-stop-sync/', views_api.force_stop_sync_api, name='force_stop_sync_api'),
    path('api/sync-logs/<int:batch_id>/', views.api_sync_logs, name='api_sync_logs'),

    # Cloud Scheduler endpoints (for Option F - no Celery)
    path('api/trigger-sync/', views_api.trigger_bigin_sync, name='trigger_bigin_sync'),
    path('api/trigger-module-sync/', views_api.trigger_module_sync, name='trigger_module_sync'),
    path('api/trigger-token-refresh/', views_api.trigger_token_refresh, name='trigger_token_refresh'),
    path('api/force-token-refresh/', views_api.force_token_refresh, name='force_token_refresh'),
    path('api/manual-token-update/', views_api.manual_token_update, name='manual_token_update'),

    # CRUD Operations for Bigin Contacts
    path('api/contacts/create/', views_api.create_bigin_contact, name='create_bigin_contact'),
    path('api/contacts/<str:bigin_id>/', views_api.get_bigin_contact, name='get_bigin_contact'),
    path('api/contacts/<str:bigin_id>/update/', views_api.update_bigin_contact, name='update_bigin_contact'),
    path('api/contacts/<str:bigin_id>/delete/', views_api.delete_bigin_contact, name='delete_bigin_contact'),
    path('api/contacts/<str:bigin_id>/timeline/', views_api.get_contact_timeline, name='get_contact_timeline'),
    path('api/contacts/bulk-create/', views_api.bulk_create_bigin_contacts, name='bulk_create_bigin_contacts'),
    path('api/contacts/bulk-update/', views_api.bulk_update_bigin_contacts, name='bulk_update_bigin_contacts'),
    path('api/contacts/bulk-delete/', views_api.bulk_delete_bigin_contacts, name='bulk_delete_bigin_contacts'),

    # Field Options
    path('api/field-options/', views_api.get_field_options, name='get_field_options'),

    # Cloud Tasks worker endpoints
    path('workers/sync-all-modules/', workers.sync_all_modules_worker, name='worker_sync_all_modules'),
    path('workers/refresh-token/', workers.refresh_bigin_token_worker, name='worker_refresh_token'),
    path('workers/stale-lead-check/', workers.stale_lead_check_worker, name='worker_stale_lead_check'),
]