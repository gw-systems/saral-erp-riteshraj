from django.urls import path

from . import views, workers

app_name = 'transport_sheet'

urlpatterns = [
    path('settings/', views.transport_sheet_settings, name='settings'),
    path('worker/sync/', workers.transport_sync_worker, name='sync_worker'),
]
