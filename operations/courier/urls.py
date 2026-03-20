"""
URL configuration for courier app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'courier'

# Create router for ViewSets
router = DefaultRouter()
router.register(r'orders', views.OrderViewSet, basename='order')
router.register(r'ftl-orders', views.FTLOrderViewSet, basename='ftl-order')
router.register(r'warehouses', views.WarehouseViewSet, basename='warehouse')

urlpatterns = [
    # ERP-native workspace
    path('', views.root_redirect, name='root'),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('rate-calculator/', views.rate_calculator_view, name='rate-calculator'),
    path('orders-dashboard/', views.orders_dashboard_view, name='orders-dashboard'),
    path('shipments/', views.shipments_dashboard_view, name='shipments-dashboard'),
    path('warehouses-dashboard/', views.warehouses_dashboard_view, name='warehouses-dashboard'),

    # Public endpoints
    path('health', views.health_check, name='health'),
    path('compare-rates', views.compare_rates, name='compare-rates'),
    path('pincode/<int:pincode>/', views.lookup_pincode, name='lookup-pincode'),
    
    # FTL endpoints
    path('ftl/routes', views.get_ftl_routes, name='get-ftl-routes'),
    path('ftl/calculate-rate', views.calculate_ftl_rate, name='calculate-ftl-rate'),

    # Order management (includes ViewSet routes)
    # IMPORTANT: Router must come BEFORE manual paths with <pk> to prevent action names being captured
    path('', include(router.urls)),
    path('orders/<str:pk>/invoice/', views.generate_invoice_pdf, name='generate-invoice'),
    path('orders/invoices/download/', views.download_invoices_zip, name='download-invoices'),
    path('carriers/<int:pk>/rate-card/', views.generate_rate_card_pdf, name='generate-rate-card'),
    path('rate-card/b2c/options/', views.list_b2c_rate_card_carriers, name='b2c-rate-card-options'),
    path('rate-card/b2c/', views.generate_b2c_rate_card_pdf, name='b2c-rate-card'),
    path('rate-card/b2b/options/', views.list_b2b_rate_card_carriers, name='b2b-rate-card-options'),
    path('rate-card/b2b/', views.generate_b2b_rate_card_pdf, name='b2b-rate-card'),
    path('rate-card/ftl/', views.generate_ftl_rate_card_pdf, name='ftl-rate-card'),

    # Admin endpoints
    path('admin/auth/login', views.admin_login, name='admin-auth-login'),
    path('admin/auth/logout', views.admin_logout, name='admin-auth-logout'),
    path('admin/rates', views.get_all_rates, name='admin-get-rates'),
    path('admin/rates/update', views.update_rates, name='admin-update-rates'),
    path('admin/rates/upload', views.upload_excel_rates, name='admin-upload-rates'),
    path('admin/ftl/upload', views.upload_ftl_excel_rates, name='admin-upload-ftl-rates'),
    path('admin/rates/add', views.add_carrier, name='admin-add-carrier'),
    path('admin/carriers/<str:carrier_name>/toggle-active', views.toggle_carrier_active, name='admin-toggle-carrier'),
    path('admin/carriers/<str:carrier_name>', views.delete_carrier, name='admin-delete-carrier'),
    path('admin/carriers/<str:carrier_name>/update', views.update_carrier, name='admin-update-carrier'),
    path('admin/orders', views.admin_orders_list, name='admin-orders-list'),
    path('admin/ftl-orders', views.admin_ftl_orders_list, name='admin-ftl-orders-list'),
    path('admin/dashboard', views.admin_dashboard_stats, name='admin-dashboard-stats'),
    path('admin/settings', views.system_settings, name='admin-settings'),

    # Shipdaak v2 operations
    path('shipdaak/warehouses/<int:pk>/import-existing', views.shipdaak_import_existing_warehouse, name='shipdaak-warehouse-import-existing'),
    path('shipdaak/warehouses/bulk-import', views.shipdaak_bulk_import_warehouses, name='shipdaak-warehouses-bulk-import'),
    path('shipdaak/warehouses/<int:pk>/sync', views.shipdaak_sync_warehouse, name='shipdaak-warehouse-sync'),
    path('shipdaak/warehouses/<int:pk>/status', views.shipdaak_warehouse_status, name='shipdaak-warehouse-status'),
    path('shipdaak/warehouses/<int:pk>/link-existing', views.shipdaak_link_existing_warehouse_id, name='shipdaak-warehouse-link-existing'),
    path('shipdaak/serviceability', views.shipdaak_serviceability, name='shipdaak-serviceability'),
    path('shipdaak/couriers', views.shipdaak_couriers, name='shipdaak-couriers'),
    path('orders/<int:pk>/shipdaak/track', views.shipdaak_track_order, name='shipdaak-order-track'),
    path('orders/<int:pk>/shipdaak/cancel', views.shipdaak_cancel_order, name='shipdaak-order-cancel'),
    path('orders/<int:pk>/shipdaak/label', views.shipdaak_order_label, name='shipdaak-order-label'),
    path('shipdaak/bulk-label', views.shipdaak_bulk_label, name='shipdaak-bulk-label'),
    path('shipdaak/manifest', views.shipdaak_manifest, name='shipdaak-manifest'),
]
