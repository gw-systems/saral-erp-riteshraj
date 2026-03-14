from django.urls import path
from . import views

app_name = 'dropdown_master_data'

urlpatterns = [
    path('', views.dropdown_master_list, name='master_list'),
    path('<str:model_name>/', views.dropdown_detail, name='dropdown_detail'),
    path('<str:model_name>/create/', views.dropdown_create, name='dropdown_create'),
    path('<str:model_name>/<str:entry_code>/edit/', views.dropdown_edit, name='dropdown_edit'),
    path('<str:model_name>/<str:entry_code>/toggle/', views.dropdown_toggle_active, name='dropdown_toggle_active'),
]