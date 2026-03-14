"""
Supply Chain Management URLs
"""

from django.urls import path
from . import views
from . import views_rfq

app_name = 'supply'

urlpatterns = [
    # Dashboard
    path('', views.supply_dashboard, name='dashboard'),
    path('map/', views.supply_map, name='supply_map'),      
    path('analytics/', views.supply_analytics, name='supply_analytics'), 

    # Location URLs
    path('locations/', views.location_list, name='location_list'),
    path('locations/create/', views.location_create, name='location_create'),
    path('locations/<int:location_id>/edit/', views.location_edit, name='location_edit'),
    path('locations/<int:location_id>/delete/', views.location_delete, name='location_delete'),
    
    # Vendor URLs
    path('vendors/', views.vendor_list, name='vendor_list'),
    path('vendors/create/', views.vendor_create, name='vendor_create'),
    path('vendors/<str:vendor_code>/', views.vendor_detail, name='vendor_detail'),
    path('vendors/<str:vendor_code>/edit/', views.vendor_update, name='vendor_edit'),  # ← KEPT ONLY THIS
    path('vendors/<str:vendor_code>/toggle-active/', views.vendor_toggle_active, name='vendor_toggle_active'),
    path('vendors/<str:vendor_code>/contacts/manage/', views.vendor_contact_manage, name='vendor_contact_manage'),
    path('vendors/<str:vendor_code>/delete/', views.admin_delete_vendor_card, name='admin_delete_vendor'),
    path('vendors/<str:vendor_code>/link-projects/', views.vendor_link_projects, name='vendor_link_projects'),
    path('vendors/<str:vendor_code>/unlink-project/', views.vendor_unlink_project, name='vendor_unlink_project'),
    path('vendors/<str:vendor_code>/unlink-all-projects/', views.vendor_unlink_all_projects, name='vendor_unlink_all_projects'),
    
    # Warehouse URLs
    path('warehouses/', views.warehouse_list, name='warehouse_list'),
    path('warehouses/create/', views.warehouse_create, name='warehouse_create'),
    path('warehouses/<str:warehouse_code>/', views.warehouse_detail, name='warehouse_detail'),
    path('warehouses/<str:warehouse_code>/edit/', views.warehouse_update, name='warehouse_edit'),  # ← KEPT ONLY THIS
    path('warehouses/<str:warehouse_code>/documents/', views.warehouse_documents_upload, name='warehouse_documents'),
    path('warehouses/<str:warehouse_code>/photos/', views.warehouse_photos_upload, name='warehouse_photos'),
    path('warehouses/<str:warehouse_code>/toggle-active/', views.warehouse_toggle_active, name='warehouse_toggle_active'),
    path('warehouses/<str:warehouse_code>/quick-update/<str:section>/', views.warehouse_quick_update, name='warehouse_quick_update'),
    path('warehouses/<str:warehouse_code>/contacts/manage/', views.warehouse_contact_manage, name='warehouse_contact_manage'),
    path('warehouses/<str:warehouse_code>/delete/', views.admin_delete_warehouse, name='admin_delete_warehouse'),
    path('warehouses/<str:warehouse_code>/unlink-all-projects/', views.warehouse_unlink_all_projects, name='warehouse_unlink_all_projects'),
    path('warehouse-availability/', views.warehouse_availability, name='warehouse_availability'),
    
    # RFQ Management
    path('rfqs/', views_rfq.rfq_list, name='rfq_list'),
    path('rfqs/create/', views_rfq.rfq_create, name='rfq_create'),
    path('rfqs/<str:rfq_id>/', views_rfq.rfq_detail, name='rfq_detail'),
    path('rfqs/<str:rfq_id>/edit/', views_rfq.rfq_edit, name='rfq_edit'),
    path('rfqs/<str:rfq_id>/send/', views_rfq.rfq_send_to_vendors, name='rfq_send'),
    path('rfqs/<str:rfq_id>/toggle-status/', views_rfq.rfq_toggle_status, name='rfq_toggle_status'),

    # AJAX endpoints
    path('api/vendors/<str:vendor_code>/warehouses/', views.get_vendor_warehouses, name='get_vendor_warehouses'),
    path('ajax/cities/', views.get_cities_by_state, name='get_cities_by_state'),
    path('ajax/rfq-vendor-contacts/', views_rfq.get_rfq_vendor_contacts, name='get_rfq_vendor_contacts'),
]