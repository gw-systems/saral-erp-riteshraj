"""
Courier Views Package.
Re-exports all view functions and classes for URL routing.
"""

# Public API endpoints
from .public import (
    health_check,
    compare_rates,
    lookup_pincode,
)
from .ui import (
    root_redirect,
    login_view,
    dashboard_view,
    rate_calculator_view,
    orders_dashboard_view,
    shipments_dashboard_view,
    warehouses_dashboard_view,
)

# Order management
from .orders import OrderViewSet
from .warehouses import WarehouseViewSet

# Admin endpoints
from .admin import (
    admin_login,
    admin_logout,
    get_all_rates,
    update_rates,
    upload_excel_rates,
    upload_ftl_excel_rates,
    add_carrier,
    toggle_carrier_active,
    delete_carrier,
    update_carrier,
    admin_orders_list,
    admin_ftl_orders_list,
    admin_dashboard_stats,
    system_settings,
)

# FTL endpoints
from .ftl import (
    get_ftl_routes,
    calculate_ftl_rate,
    FTLOrderViewSet,
)

# Utility functions (for direct access if needed)
from .base import (
    load_rates,
    load_ftl_rates,
    invalidate_rates_cache,
    generate_order_number,
    generate_ftl_order_number,
    calculate_ftl_price,
)

# Invoice generation
from .invoices import generate_invoice_pdf, download_invoices_zip
from .rate_card import (
    generate_rate_card_pdf,
    generate_b2c_rate_card_pdf,
    list_b2c_rate_card_carriers,
    generate_b2b_rate_card_pdf,
    list_b2b_rate_card_carriers,
    generate_ftl_rate_card_pdf,
)
from .shipdaak import (
    shipdaak_import_existing_warehouse,
    shipdaak_bulk_import_warehouses,
    shipdaak_sync_warehouse,
    shipdaak_warehouse_status,
    shipdaak_link_existing_warehouse_id,
    shipdaak_serviceability,
    shipdaak_couriers,
    shipdaak_track_order,
    shipdaak_cancel_order,
    shipdaak_order_label,
    shipdaak_bulk_label,
    shipdaak_manifest,
)

__all__ = [
    # Public
    'health_check',
    'root_redirect',
    'login_view',
    'dashboard_view',
    'rate_calculator_view',
    'orders_dashboard_view',
    'shipments_dashboard_view',
    'warehouses_dashboard_view',
    'compare_rates',
    'lookup_pincode',
    # Orders
    'OrderViewSet',
    'WarehouseViewSet',
    # Admin
    'admin_login',
    'admin_logout',
    'get_all_rates',
    'update_rates',
    'upload_excel_rates',
    'upload_ftl_excel_rates',
    'add_carrier',
    'toggle_carrier_active',
    'delete_carrier',
    'update_carrier',
    'admin_orders_list',
    'admin_ftl_orders_list',
    'admin_dashboard_stats',
    'system_settings',
    # FTL
    'get_ftl_routes',
    'calculate_ftl_rate',
    'FTLOrderViewSet',
    # Utilities
    'load_rates',
    'load_ftl_rates',
    'invalidate_rates_cache',
    'generate_order_number',
    'generate_ftl_order_number',
    'calculate_ftl_price',
    # Invoices
    'generate_invoice_pdf',
    'download_invoices_zip',
    'generate_rate_card_pdf',
    'generate_b2c_rate_card_pdf',
    'list_b2c_rate_card_carriers',
    'generate_b2b_rate_card_pdf',
    'list_b2b_rate_card_carriers',
    'generate_ftl_rate_card_pdf',
    # Shipdaak
    'shipdaak_import_existing_warehouse',
    'shipdaak_bulk_import_warehouses',
    'shipdaak_sync_warehouse',
    'shipdaak_warehouse_status',
    'shipdaak_link_existing_warehouse_id',
    'shipdaak_serviceability',
    'shipdaak_couriers',
    'shipdaak_track_order',
    'shipdaak_cancel_order',
    'shipdaak_order_label',
    'shipdaak_bulk_label',
    'shipdaak_manifest',
]
