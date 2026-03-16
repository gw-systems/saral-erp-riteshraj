from django.urls import path

from . import views, workers

app_name = 'apollo'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('sync/', views.trigger_sync, name='trigger_sync'),
    path('sync-progress/', views.sync_progress, name='sync_progress'),
    path('api/sync-logs/<int:batch_id>/', views.sync_logs, name='sync_logs'),
    path('workers/sync/', workers.sync_worker, name='worker_sync'),
]
