from django.urls import path
from . import views
from . import views_users
from . import views_notifications
from . import views_health
from . import views_dashboard_director
from . import views_dashboard_digital_marketing
from . import views_dashboard_admin
from . import views_errors
from .views_file_delete import universal_file_delete

app_name = 'accounts' 

urlpatterns = [
    # Health check endpoints
    path('health/', views_health.health_check, name='health_check'),
    path('health/simple/', views_health.health_check_simple, name='health_check_simple'),

    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    path('admin-tools/file-manager/', views.file_manager, name='file_manager'),
    path('admin-tools/file-delete/<path:file_path>/', views.file_delete, name='file_delete'),

    # Role-Specific Dashboards (Each role gets its own URL)
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),

    # New Modular Admin Dashboard (8 Hub Pages)
    path('dashboard/admin/home/', views.admin_dashboard_home, name='admin_dashboard_home'),
    path('dashboard/admin/projects/', views.admin_dashboard_projects, name='admin_dashboard_projects'),
    path('dashboard/admin/operations/', views.admin_dashboard_operations, name='admin_dashboard_operations'),
    path('dashboard/admin/supply/', views.admin_dashboard_supply, name='admin_dashboard_supply'),
    path('dashboard/admin/finance/', views.admin_dashboard_finance, name='admin_dashboard_finance'),
    path('dashboard/admin/integrations/', views.admin_dashboard_integrations, name='admin_dashboard_integrations'),
    path('api/integration-sync-status/', views_dashboard_admin.integration_sync_status_api, name='integration_sync_status_api'),
    path('dashboard/admin/team/', views.admin_dashboard_team, name='admin_dashboard_team'),
    path('dashboard/admin/system/', views.admin_dashboard_system, name='admin_dashboard_system'),
    path('dashboard/admin/file-manager/', views.admin_file_manager, name='admin_file_manager'),

    # Director Dashboard
    path('dashboard/director/', views_dashboard_director.director_home, name='director_home'),
    path('dashboard/director/analytics/', views_dashboard_director.director_analytics, name='director_analytics'),

    path('dashboard/super-user/', views.super_user_dashboard, name='super_user_dashboard'),
    path('backoffice-dashboard/', views.backoffice_dashboard, name='backoffice_dashboard'),
    path('operation-manager-dashboard/', views.operation_manager_dashboard, name='operation_manager_dashboard'),
    path('operation-coordinator-dashboard/', views.operation_coordinator_dashboard, name='operation_coordinator_dashboard'),
    path('operation-controller-dashboard/', views.operation_controller_dashboard, name='operation_controller_dashboard'),
    path('operation-controller-team/', views.operation_controller_team_performance, name='operation_controller_team'),
    path('operation-team/<int:user_id>/', views.operation_controller_member_detail, name='operation_controller_member_detail'),

    # Daily Operations Detail Pages
    path('operation-controller/daily/missing-entries/', views.daily_missing_entries_detail, name='daily_missing_entries_detail'),
    path('operation-controller/daily/space-inventory/', views.daily_space_utilization_detail, name='daily_space_utilization_detail'),
    path('operation-controller/daily/inventory-value/', views.daily_inventory_value_detail, name='daily_inventory_value_detail'),
    path('operation-controller/daily/variance-alerts/', views.daily_variance_alerts_detail, name='daily_variance_alerts_detail'),
    path('operation-controller/daily/inventory-turnover/', views.daily_inventory_turnover_detail, name='daily_inventory_turnover_detail'),

    # Monthly Operations Detail Pages
    path('operation-controller/monthly/max-inventory/', views.monthly_max_inventory_detail, name='monthly_max_inventory_detail'),
    path('sales-manager-dashboard/', views.sales_manager_dashboard, name='sales_manager_dashboard'),
    path('crm-executive-dashboard/', views.crm_executive_dashboard, name='crm_executive_dashboard'),
    path('digital-marketing-dashboard/', views_dashboard_digital_marketing.digital_marketing_dashboard, name='digital_marketing_dashboard'),
    path('warehouse-manager-dashboard/', views.dashboard_view, name='warehouse_manager_dashboard'),
    path('supply-manager-dashboard/', views.supply_manager_dashboard, name='supply_manager_dashboard'),
    path('finance-manager/', views.finance_manager_dashboard, name='finance_manager_dashboard'),
    path('finance/', views.finance_dashboard, name='finance_dashboard'),

    
    # Generic fallback (for roles without specific dashboards yet)
    path('dashboard/', views.dashboard_redirect, name='dashboard'),
    
    # Profile
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
    
    # User Management (Admin only)
    path('users/', views.user_list_view, name='user_list'),
    path('users/create/', views.user_create_view, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_edit_view, name='user_edit'),
    path('users/<int:user_id>/delete/', views.user_delete_view, name='user_delete'),
    path('users/<int:user_id>/reset-password/', views.user_reset_password_view, name='user_reset_password'),
    path('users/<int:user_id>/permissions/', views.user_permissions_view, name='user_permissions'),

    # Notifications
    path('notifications/', views_notifications.notifications_list, name='notifications_list'),
    path('notifications/mark-all-read/', views_notifications.notifications_mark_all_read, name='notifications_mark_all_read'),
    path('notifications/<int:notification_id>/read/', views_notifications.notification_mark_read, name='notification_mark_read'),
    path('notifications/<int:notification_id>/delete/', views_notifications.notification_delete, name='notification_delete'),
    path('notifications/batch-action/', views_notifications.notification_batch_action, name='notification_batch_action'),
    path('api/notifications/', views_notifications.notifications_api, name='notifications_api'),

    path('password-history/', views.password_history_view, name='password_history_all'),
    path('password-history/<int:user_id>/', views.password_history_view, name='password_history'),

    path('change-password/', views.change_password_view, name='change_password'),
    path('change-username/<int:user_id>/', views.change_username_view, name='change_username'),

    # Impersonation
    path('impersonate/<int:user_id>/', views_users.impersonate_user, name='impersonate_user'),
    path('stop-impersonation/', views_users.stop_impersonation, name='stop_impersonation'),
    path('impersonation-logs/', views_users.impersonation_logs_view, name='impersonation_logs'),

    path('debug/storage/', views.storage_debug, name='storage_debug'),

    # Error Log (Admin only)
    path('errors/', views_errors.error_list, name='error_list'),
    path('errors/resolve-all/', views_errors.resolve_all_errors, name='resolve_all_errors'),
    path('errors/<str:error_id>/', views_errors.error_detail, name='error_detail'),
    path('errors/<str:error_id>/resolve/', views_errors.resolve_error, name='resolve_error'),

    # Universal file delete
    path('files/delete/<str:app_label>/<str:model_name>/<str:object_id>/<str:field_name>/', universal_file_delete, name='universal_file_delete'),
]