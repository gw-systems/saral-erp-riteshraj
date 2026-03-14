"""
Accounts Views - Core Authentication and Utilities
All dashboard views have been split into separate files by role
"""

# Import all dashboard views
from accounts.views_auth import login_view, logout_view
from accounts.views_dashboard_router import dashboard_redirect, dashboard_view
from accounts.views_dashboard_admin import (
    admin_dashboard,
    admin_dashboard_home,
    admin_dashboard_projects,
    admin_dashboard_operations,
    admin_dashboard_supply,
    admin_dashboard_finance,
    admin_dashboard_integrations,
    admin_dashboard_team,
    admin_dashboard_system,
    admin_file_manager,
)
from accounts.views_dashboard_super_user import super_user_dashboard
from accounts.views_dashboard_operation_manager import operation_manager_dashboard
from accounts.views_dashboard_operation_coordinator import operation_coordinator_dashboard
from accounts.views_dashboard_operation_controller import (
    operation_controller_dashboard,
    operation_controller_team_performance,
    operation_controller_member_detail,
    daily_missing_entries_detail,
    daily_space_utilization_detail,
    daily_inventory_value_detail,
    daily_variance_alerts_detail,
    daily_inventory_turnover_detail,
    monthly_max_inventory_detail
)
from accounts.views_dashboard_sales_manager import sales_manager_dashboard
from accounts.views_dashboard_crm_executive import crm_executive_dashboard
from accounts.views_dashboard_backoffice import backoffice_dashboard
from accounts.views_dashboard_supply_manager import supply_manager_dashboard
from accounts.views_dashboard_finance_manager import finance_manager_dashboard
from accounts.views_dashboard_finance import finance_dashboard
from accounts.views_users import (
    user_list_view,
    user_create_view,
    user_edit_view,
    user_delete_view,
    user_reset_password_view,
    user_permissions_view,
    password_history_view
)
from accounts.views_utilities import (
    file_manager,
    file_delete,
    storage_debug,
    change_password_view,
    change_username_view,
    profile_view,
    profile_edit_view,
    get_client_ip
)
from accounts.views_notifications import (
    notifications_list,
    notifications_api,
    notification_mark_read,
    notifications_mark_all_read,
    notification_delete,
    get_time_ago
)
from accounts.views_auth import _redirect_to_role_dashboard
from accounts.dashboard_helpers import get_coordinator_workload

# All views are now imported from their respective modules
# This file serves as a central import point for backwards compatibility