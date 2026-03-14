"""
Expense Log URL configuration.
"""
from django.urls import path
from . import views, workers

app_name = 'expense_log'

urlpatterns = [
    # OAuth callback (still needed for OAuth flow)
    path('oauth/callback/', views.oauth_callback, name='oauth_callback'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    path('transport-projectwise/excel/', views.transport_projectwise_excel, name='transport_projectwise_excel'),
    path('transport-projectwise/', views.transport_expenses_projectwise, name='transport_projectwise'),
    path('transport-project/<str:project_code>/', views.transport_project_detail, name='transport_project_detail'),

    # User Name Mappings (Admin only)
    path('user-mappings/', views.user_mappings, name='user_mappings'),
    path('user-mappings/update/<int:user_id>/', views.update_mapping, name='update_mapping'),
    path('user-mappings/delete/<int:user_id>/', views.delete_mapping, name='delete_mapping'),

    # API
    path('api/sync-progress/', views.sync_progress, name='sync_progress'),
    path('api/sync-logs/<int:batch_id>/', views.sync_logs, name='sync_logs'),
    path('api/expense/<int:expense_id>/', views.expense_detail_api, name='expense_detail_api'),

    # Cloud Tasks worker
    path('worker/sync/', workers.sync_worker, name='sync_worker'),
]
