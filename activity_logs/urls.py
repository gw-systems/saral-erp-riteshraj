from django.urls import path
from . import views

app_name = 'activity_logs'

urlpatterns = [
    path('', views.activity_calendar_view, name='calendar'),
    path('api/month/', views.api_month, name='api_month'),
    path('api/week/', views.api_week, name='api_week'),
    path('api/day/<str:date_str>/', views.api_day, name='api_day'),
    path('api/feed/', views.api_feed, name='api_feed'),
    path('api/user/<int:user_id>/day/<str:date_str>/', views.api_user_day, name='api_user_day'),
]
