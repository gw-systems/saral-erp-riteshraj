"""
Role-based permissions for Godamwale ERP
Defines granular permissions for each role across all modules
"""

# ============================================================================
# ROLE PERMISSIONS MATRIX
# ============================================================================

ROLE_PERMISSIONS = {
    
    # ========================================================================
    # TIER 1: ADMIN ACCESS
    # ========================================================================
    
    'admin': {
        'billing': {
            'create': True,
            'view_all': True,
            'view_assigned': True,
            'edit': True,
            'delete': True,
            'approve': True,
            'reject': True,
            'export': True,
            'see_vendor_costs': True,
            'see_client_rates': True,
            'see_margins': True,
        },
        'projects': {
            'create': True,
            'view_all': True,
            'view_assigned': True,
            'edit': True,
            'delete': True,
            'assign_coordinator': True,
            'change_status': True,
        },
        'users': {
            'create': True,
            'view_all': True,
            'edit': True,
            'delete': True,
            'change_roles': True,
            'reset_password': True,
        },
        'rate_cards': {
            'create': True,
            'view_all': True,
            'edit': True,
            'delete': True,
            'apply_escalation': True,
            'view_history': True,
            'update_operation_start_date': True,
        },
        'approvals': {
            'create': True,
            'view_all': True,
            'respond': True,
            'internal_approve': True,
        },
        'contacts': {
            'create': True,
            'view_all': True,
            'edit': True,
            'delete': True,
        },
        'reports': {
            'view_all': True,
            'export': True,
            'financial': True,
            'operations': True,
        },
        'master_data': {
            'create': True,
            'edit': True,
            'delete': True,
            'view': True,
        },
        'system': {
            'view_audit_logs': True,
            'settings': True,
            'backup_restore': True,
        },
    },
    
    'super_user': {
        'billing': {
            'create': False,  # View only in billing
            'view_all': True,
            'view_assigned': True,
            'edit': False,
            'delete': False,  # Cannot delete
            'approve': False,  # View only
            'reject': False,
            'export': True,
            'see_vendor_costs': True,
            'see_client_rates': True,
            'see_margins': True,
        },
        'projects': {
            'create': True,
            'view_all': True,
            'view_assigned': True,
            'edit': True,
            'delete': False,  # Cannot delete
            'assign_coordinator': True,
            'change_status': True,
        },
        'users': {
            'create': True,
            'view_all': True,
            'edit': True,
            'delete': False,  # Cannot delete
            'change_roles': True,
            'reset_password': True,
        },
        'rate_cards': {
            'create': True,
            'view_all': True,
            'edit': True,
            'delete': False,  # Cannot delete
            'apply_escalation': True,
            'view_history': True,
            'update_operation_start_date': True,
        },
        'approvals': {
            'create': True,
            'view_all': True,
            'respond': True,
            'internal_approve': True,
        },
        'contacts': {
            'create': True,
            'view_all': True,
            'edit': True,
            'delete': False,  # Cannot delete
        },
        'reports': {
            'view_all': True,
            'export': True,
            'financial': True,
            'operations': True,
        },
        'master_data': {
            'create': True,
            'edit': True,
            'delete': False,  # Cannot delete
            'view': True,
        },
        'system': {
            'view_audit_logs': True,
            'settings': True,
            'backup_restore': True,
        },
    },
    
    # ========================================================================
    # TIER 2: EXECUTIVE VIEW
    # ========================================================================
    
    'director': {
        'billing': {
            'create': False,
            'view_all': True,
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'approve': False,
            'reject': False,
            'export': True,
            'see_vendor_costs': True,
            'see_client_rates': True,
            'see_margins': True,
        },
        'projects': {
            'create': False,
            'view_all': True,
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'assign_coordinator': False,
            'change_status': False,
        },
        'users': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
            'apply_escalation': False,
            'view_history': True,
            'update_operation_start_date': False,
        },
        'approvals': {
            'create': False,
            'view_all': True,
            'respond': False,
            'internal_approve': False,
        },
        'contacts': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
        },
        'reports': {
            'view_all': True,
            'export': True,
            'financial': True,
            'operations': True,
        },
        'master_data': {
            'create': False,
            'edit': False,
            'delete': False,
            'view': True,
        },
        'system': {
            'view_audit_logs': True,
            'settings': False,
            'backup_restore': False,
        },
    },
    
    # ========================================================================
    # TIER 3: MANAGEMENT
    # ========================================================================
    
    'finance_manager': {
        'billing': {
            'create': False,
            'view_all': True,
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'approve': True,
            'reject': True,
            'export': True,
            'see_vendor_costs': True,
            'see_client_rates': True,
            'see_margins': True,
        },
        'projects': {
            'create': False,
            'view_all': True,
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'assign_coordinator': False,
            'change_status': False,
        },
        'users': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
            'apply_escalation': True,  # Can approve escalation
            'view_history': True,
            'update_operation_start_date': False,
        },
        'approvals': {
            'create': False,
            'view_all': True,
            'respond': False,
            'internal_approve': False,
        },
        'contacts': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
        },
        'reports': {
            'view_all': True,
            'export': True,
            'financial': True,
            'operations': True,
        },
        'master_data': {
            'create': False,
            'edit': False,
            'delete': False,
            'view': True,
        },
        'system': {
            'view_audit_logs': True,
            'settings': False,
            'backup_restore': False,
        },
    },
    
    'operation_controller': {
        'billing': {
            'create': True,  # Can create billing
            'view_all': True,
            'view_assigned': True,
            'edit': True,  # Can edit billing
            'delete': False,
            'approve': True,
            'reject': True,
            'export': True,
            'see_vendor_costs': True,
            'see_client_rates': True,
            'see_margins': True,
        },
        'projects': {
            'create': False,
            'view_all': True,
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'assign_coordinator': True,
            'change_status': True,
        },
        'users': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
            'apply_escalation': False,
            'view_history': True,
            'update_operation_start_date': False,
        },
        'approvals': {
            'create': True,
            'view_all': True,
            'respond': True,
            'internal_approve': True,
        },
        'contacts': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
        },
        'reports': {
            'view_all': True,
            'export': True,
            'financial': False,
            'operations': True,
        },
        'master_data': {
            'create': False,
            'edit': False,
            'delete': False,
            'view': True,
        },
        'system': {
            'view_audit_logs': True,
            'settings': False,
            'backup_restore': False,
        },
    },
    
    'operation_manager': {
        'billing': {
            'create': True,
            'view_all': True,  # Can see all projects
            'view_assigned': True,
            'edit': True,
            'delete': False,
            'approve': True,  # First level approval
            'reject': True,
            'export': True,
            'see_vendor_costs': True,  # Only assigned projects
            'see_client_rates': True,  # Only assigned projects
            'see_margins': False,  # Cannot see margins
        },
        'projects': {
            'create': False,
            'view_all': True,
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'assign_coordinator': True,  # Primary responsibility
            'change_status': True,
        },
        'users': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': False,
            'view_all': True,  # All projects
            'edit': False,
            'delete': False,
            'apply_escalation': False,
            'view_history': False,
            'update_operation_start_date': False,
        },
        'approvals': {
            'create': True,
            'view_all': True,
            'respond': True,
            'internal_approve': True,
        },
        'contacts': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
        },
        'reports': {
            'view_all': True,
            'export': True,
            'financial': False,
            'operations': True,
        },
        'master_data': {
            'create': False,
            'edit': False,
            'delete': False,
            'view': True,
        },
        'system': {
            'view_audit_logs': False,
            'settings': False,
            'backup_restore': False,
        },
    },
    
    'sales_manager': {
        'billing': {
            'create': False,
            'view_all': False,
            'view_assigned': True,  # Only assigned projects
            'edit': False,
            'delete': False,
            'approve': False,
            'reject': False,
            'export': False,
            'see_vendor_costs': True,  # Only assigned
            'see_client_rates': True,  # Only assigned
            'see_margins': True,  # Only assigned
        },
        'projects': {
            'create': False,  # Cannot create projects
            'view_all': False,
            'view_assigned': True,  # Only assigned
            'edit': False,
            'delete': False,
            'assign_coordinator': False,
            'change_status': False,
        },
        'users': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': False,
            'view_all': False,
            'view_assigned': True,  # Only assigned
            'edit': False,
            'delete': False,
            'apply_escalation': False,
            'view_history': False,
            'update_operation_start_date': False,
        },
        'approvals': {
            'create': False,
            'view_all': False,
            'view_assigned': True,
            'respond': False,
            'internal_approve': False,
        },
        'contacts': {
            'create': False,
            'view_all': False,
            'view_assigned': True,  # Only assigned projects
            'edit': False,
            'delete': False,
        },
        'reports': {
            'view_all': False,
            'view_assigned': True,
            'export': True,
            'financial': False,
            'operations': False,
        },
        'master_data': {
            'create': False,
            'edit': False,
            'delete': False,
            'view': True,
        },
        'system': {
            'view_audit_logs': False,
            'settings': False,
            'backup_restore': False,
        },
    },

    'supply_manager': {
        'billing': {
            'create': False,
            'view_all': True,  # Can view all for supply chain coordination
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'approve': False,
            'reject': False,
            'export': True,
            'see_vendor_costs': True,
            'see_client_rates': False,
            'see_margins': False,
        },
        'projects': {
            'create': False,
            'view_all': True,  # Can see all projects for warehouse planning
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'assign_coordinator': False,
            'change_status': False,
        },
        'users': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': False,
            'view_all': True,  # Can view for vendor coordination
            'edit': False,
            'delete': False,
            'apply_escalation': False,
            'view_history': False,
            'update_operation_start_date': False,
        },
        'approvals': {
            'create': False,
            'view_all': True,
            'respond': False,
            'internal_approve': False,
        },
        'contacts': {
            'create': True,  # Can create vendor/warehouse contacts
            'view_all': True,
            'edit': True,  # Can edit vendor/warehouse contacts
            'delete': False,
        },
        'reports': {
            'view_all': True,
            'export': True,
            'financial': False,
            'operations': True,
        },
        'master_data': {
            'create': True,  # Can create vendors, warehouses, locations
            'edit': True,  # Can edit supply chain master data
            'delete': False,
            'view': True,
        },
        'system': {
            'view_audit_logs': False,
            'settings': False,
            'backup_restore': False,
        },
    },
    
    # ========================================================================
    # TIER 4: EXECUTION
    # ========================================================================
    
    'operation_coordinator': {
        'billing': {
            'create': True,  # Only assigned projects
            'view_all': False,
            'view_assigned': True,
            'edit': True,  # Only own billings
            'delete': False,
            'approve': False,
            'reject': False,
            'export': False,
            'see_vendor_costs': True,  # Only assigned
            'see_client_rates': True,  # Only assigned
            'see_margins': False,  # Cannot see margins
        },
        'projects': {
            'create': False,
            'view_all': False,
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'assign_coordinator': False,
            'change_status': False,
        },
        'users': {
            'create': False,
            'view_all': False,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': False,
            'view_all': False,
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'apply_escalation': False,
            'view_history': False,
            'update_operation_start_date': True,  # Can update this field
        },
        'approvals': {
            'create': True,
            'view_all': False,
            'view_assigned': True,
            'respond': True,
            'internal_approve': False,
        },
        'contacts': {
            'create': False,
            'view_all': False,
            'view_assigned': True,  # Only assigned projects
            'edit': False,
            'delete': False,
        },
        'reports': {
            'view_all': False,
            'view_assigned': True,
            'export': False,
            'financial': False,
            'operations': True,
        },
        'master_data': {
            'create': False,
            'edit': False,
            'delete': False,
            'view': True,
        },
        'system': {
            'view_audit_logs': False,
            'settings': False,
            'backup_restore': False,
        },
    },
    
    'warehouse_manager': {
        'billing': {
            'create': True,  # Only assigned warehouses
            'view_all': False,
            'view_assigned': True,
            'edit': True,
            'delete': False,
            'approve': False,
            'reject': False,
            'export': False,
            'see_vendor_costs': False,
            'see_client_rates': True,  # Only assigned
            'see_margins': False,
        },
        'projects': {
            'create': False,
            'view_all': False,
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'assign_coordinator': False,
            'change_status': False,
        },
        'users': {
            'create': False,
            'view_all': False,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': False,
            'view_all': False,
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'apply_escalation': False,
            'view_history': False,
            'update_operation_start_date': False,
        },
        'approvals': {
            'create': True,
            'view_all': False,
            'view_assigned': True,
            'respond': True,
            'internal_approve': False,
        },
        'contacts': {
            'create': False,
            'view_all': False,
            'view_assigned': True,
            'edit': False,
            'delete': False,
        },
        'reports': {
            'view_all': False,
            'view_assigned': True,
            'export': False,
            'financial': False,
            'operations': True,
        },
        'master_data': {
            'create': False,
            'edit': False,
            'delete': False,
            'view': True,
        },
        'system': {
            'view_audit_logs': False,
            'settings': False,
            'backup_restore': False,
        },
    },
    
    'backoffice': {
        'billing': {
            'create': False,  # No access to billing module
            'view_all': False,
            'view_assigned': False,
            'edit': False,
            'delete': False,
            'approve': False,
            'reject': False,
            'export': False,
            'see_vendor_costs': False,
            'see_client_rates': False,
            'see_margins': False,
        },
        'projects': {
            'create': True,
            'view_all': True,
            'view_assigned': True,
            'edit': True,  # Can edit anytime, any project
            'delete': False,
            'assign_coordinator': False,
            'change_status': True,
        },
        'users': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': True,  # Manages all rate cards
            'view_all': True,
            'edit': True,
            'delete': False,
            'apply_escalation': True,
            'view_history': True,
            'update_operation_start_date': True,
        },
        'approvals': {
            'create': False,
            'view_all': True,
            'view_assigned': True,
            'respond': False,
            'internal_approve': False,
        },
        'contacts': {
            'create': True,  # Manages client/vendor contacts
            'view_all': True,
            'edit': True,
            'delete': False,
        },
        'reports': {
            'view_all': True,
            'export': True,
            'financial': False,
            'operations': True,
        },
        'master_data': {
            'create': False,
            'edit': False,
            'delete': False,
            'view': True,
        },
        'system': {
            'view_audit_logs': False,
            'settings': False,
            'backup_restore': False,
        },
    },
    
    'crm_executive': {
        'billing': {
            'create': False,
            'view_all': False,
            'view_assigned': False,
            'edit': False,
            'delete': False,
            'approve': False,
            'reject': False,
            'export': False,
            'see_vendor_costs': False,
            'see_client_rates': False,
            'see_margins': False,
        },
        'projects': {
            'create': False,
            'view_all': True,  # Can see all projects (for reference)
            'view_assigned': True,
            'edit': False,
            'delete': False,
            'assign_coordinator': False,
            'change_status': False,
        },
        'users': {
            'create': False,
            'view_all': True,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': False,
            'view_all': True,  # View only for reference
            'edit': False,
            'delete': False,
            'apply_escalation': False,
            'view_history': False,
            'update_operation_start_date': False,
        },
        'approvals': {
            'create': False,
            'view_all': False,
            'view_assigned': False,
            'respond': False,
            'internal_approve': False,
        },
        'contacts': {
            'create': False,  # NO access to client contacts
            'view_all': False,
            'edit': False,
            'delete': False,
        },
        'reports': {
            'view_all': True,
            'export': False,
            'financial': False,
            'operations': False,
        },
        'master_data': {
            'create': False,
            'edit': False,
            'delete': False,
            'view': False,
        },
        'system': {
            'view_audit_logs': False,
            'settings': False,
            'backup_restore': False,
        },
    },
    
    # ========================================================================
    # TIER 5: EXTERNAL
    # ========================================================================
    
    'client': {
        'billing': {
            'create': False,
            'view_all': False,
            'view_assigned': True,  # Only own billings
            'edit': False,
            'delete': False,
            'approve': True,  # Can approve own billings
            'reject': True,  # Can reject own billings
            'export': True,  # Own data only
            'see_vendor_costs': False,
            'see_client_rates': True,  # Own rates only
            'see_margins': False,
        },
        'projects': {
            'create': False,
            'view_all': False,
            'view_assigned': True,  # Own projects only
            'edit': False,
            'delete': False,
            'assign_coordinator': False,
            'change_status': False,
        },
        'users': {
            'create': False,
            'view_all': False,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': False,
            'view_all': False,
            'view_assigned': False,  # Cannot see rate cards
            'edit': False,
            'delete': False,
            'apply_escalation': False,
            'view_history': False,
            'update_operation_start_date': False,
        },
        'approvals': {
            'create': True,  # Can create service requests
            'view_all': False,
            'view_assigned': True,
            'respond': True,
            'internal_approve': False,
        },
        'contacts': {
            'create': False,
            'view_all': False,
            'edit': False,
            'delete': False,
        },
        'reports': {
            'view_all': False,
            'view_assigned': True,  # Own data only
            'export': True,
            'financial': False,
            'operations': False,
        },
        'master_data': {
            'create': False,
            'edit': False,
            'delete': False,
            'view': False,
        },
        'system': {
            'view_audit_logs': False,
            'settings': False,
            'backup_restore': False,
        },
    },
    
    'vendor': {
        'billing': {
            'create': True,  # Can submit invoices
            'view_all': False,
            'view_assigned': True,  # Own data only
            'edit': False,
            'delete': False,
            'approve': False,
            'reject': False,
            'export': True,  # Own data only
            'see_vendor_costs': True,  # Own costs only
            'see_client_rates': False,
            'see_margins': False,
        },
        'projects': {
            'create': False,
            'view_all': False,
            'view_assigned': True,  # Assigned projects only
            'edit': False,
            'delete': False,
            'assign_coordinator': False,
            'change_status': False,
        },
        'users': {
            'create': False,
            'view_all': False,
            'edit': False,
            'delete': False,
            'change_roles': False,
            'reset_password': False,
        },
        'rate_cards': {
            'create': False,
            'view_all': False,
            'view_assigned': False,
            'edit': False,
            'delete': False,
            'apply_escalation': False,
            'view_history': False,
            'update_operation_start_date': False,
        },
        'approvals': {
            'create': False,
            'view_all': False,
            'view_assigned': False,
            'respond': False,
            'internal_approve': False,
        },
        'contacts': {
            'create': False,
            'view_all': False,
            'edit': False,
            'delete': False,
        },
        'reports': {
            'view_all': False,
            'view_assigned': True,  # Own data only
            'export': True,
            'financial': False,
            'operations': False,
        },
        'master_data': {
            'create': False,
            'edit': False,
            'delete': False,
            'view': False,
        },
        'system': {
            'view_audit_logs': False,
            'settings': False,
            'backup_restore': False,
        },
    },
}


# ============================================================================
# PERMISSION HELPER FUNCTIONS
# ============================================================================

def has_permission(user, module, action):
    """
    Check if user has specific permission
    
    Args:
        user: User object
        module: str - Module name (e.g., 'billing', 'projects')
        action: str - Action name (e.g., 'create', 'edit', 'view_all')
    
    Returns:
        bool: True if user has permission, False otherwise
    
    Example:
        has_permission(user, 'billing', 'create')
        has_permission(user, 'projects', 'view_all')
    """
    if not user or not user.is_authenticated:
        return False
    
    role_perms = ROLE_PERMISSIONS.get(user.role, {})
    module_perms = role_perms.get(module, {})
    
    return module_perms.get(action, False)


def get_user_permissions(user):
    """
    Get all permissions for a user
    
    Args:
        user: User object
    
    Returns:
        dict: All permissions for the user's role
    """
    if not user or not user.is_authenticated:
        return {}
    
    return ROLE_PERMISSIONS.get(user.role, {})


def can_view_project(user, project):
    """
    Check if user can view a specific project
    
    Args:
        user: User object
        project: ProjectCode object
    
    Returns:
        bool: True if user can view project
    """
    if not user or not user.is_authenticated:
        return False
    
    # Admin, Super User, Director - can view all
    if user.role in ['admin', 'super_user', 'director']:
        return True
    
    # Finance Manager, Operation Controller - can view all
    if user.role in ['finance_manager', 'operation_controller']:
        return True
    
    # Operation Manager - can view all
    if user.role == 'operation_manager':
        return True
    
    # Backoffice - can view all
    if user.role == 'backoffice':
        return True
    
    # CRM Executive - can view all (for reference)
    if user.role == 'crm_executive':
        return True
    
    # Operation Coordinator, Warehouse Manager - only assigned projects
    if user.role in ['operation_coordinator', 'warehouse_manager']:
        # Check if user is assigned to this project
        return (
            project.operation_manager == user.get_full_name() or
            project.backup_coordinator == user.get_full_name()
        )
    
    # Sales Manager - only assigned projects
    if user.role == 'sales_manager':
        return project.sales_manager == user.get_full_name()
    
    # Client - only their own projects
    if user.role == 'client':
        # TODO: Implement client project assignment logic
        return False
    
    # Vendor - only assigned projects
    if user.role == 'vendor':
        # TODO: Implement vendor project assignment logic
        return False
    
    return False


def can_see_vendor_costs(user, project=None):
    """
    Check if user can see vendor costs
    
    Args:
        user: User object
        project: ProjectCode object (optional)
    
    Returns:
        bool: True if user can see vendor costs
    """
    if not user or not user.is_authenticated:
        return False
    
    # Admin, Super User, Director, Finance Manager, Operation Controller - all projects
    if user.role in ['admin', 'super_user', 'director', 'finance_manager', 'operation_controller']:
        return True
    
    # Operation Manager, Operation Coordinator, Sales Manager - only assigned projects
    if user.role in ['operation_manager', 'operation_coordinator', 'sales_manager']:
        if project:
            return can_view_project(user, project)
        return False  # Need project context
    
    # Vendor - only own costs
    if user.role == 'vendor':
        if project:
            # TODO: Check if vendor is assigned to this project
            return False
        return False
    
    return False


def can_see_margins(user, project=None):
    """
    Check if user can see profit margins
    
    Args:
        user: User object
        project: ProjectCode object (optional)
    
    Returns:
        bool: True if user can see margins
    """
    if not user or not user.is_authenticated:
        return False
    
    # Admin, Super User, Director, Finance Manager, Operation Controller - all projects
    if user.role in ['admin', 'super_user', 'director', 'finance_manager', 'operation_controller']:
        return True
    
    # Sales Manager - only assigned projects
    if user.role == 'sales_manager':
        if project:
            return can_view_project(user, project)
        return False
    
    # Everyone else - NO
    return False


def can_delete_records(user):
    """
    Check if user can delete records
    Only Admin can delete
    
    Args:
        user: User object
    
    Returns:
        bool: True if user can delete
    """
    if not user or not user.is_authenticated:
        return False
    
    return user.role == 'admin'


def get_accessible_projects(user):
    """
    Get queryset of projects accessible to user
    UPDATED: Operations team sees WAAS only, Leadership sees all series
    
    Args:
        user: User object
    
    Returns:
        QuerySet: Filtered projects based on user role and series access
    """
    from projects.models import ProjectCode
    
    if not user or not user.is_authenticated:
        return ProjectCode.objects.none()
    
    # FULL ACCESS (All Series: WAAS + SAAS + GW)
    # Admin, Super User, Backoffice, Directors
    if user.role in ['admin', 'super_user', 'backoffice', 'director']:
        return ProjectCode.objects.all()
    
    # WAAS ONLY ACCESS
    # Operations team: Coordinator, Manager, Controller
    if user.role in ['operation_coordinator', 'operation_manager', 'operation_controller']:
        # Base filter: WAAS series only
        projects = ProjectCode.objects.filter(series_type='WAAS')
        
        # Operation Coordinator - only assigned projects
        if user.role == 'operation_coordinator':
            user_full_name = user.get_full_name()
            return projects.filter(
                models.Q(operation_coordinator=user_full_name) |
                models.Q(backup_coordinator=user_full_name)
            )
        
        # Operation Manager & Controller - all WAAS projects
        return projects
    
    # WAAS ONLY - Warehouse Manager (only assigned)
    if user.role == 'warehouse_manager':
        user_full_name = user.get_full_name()
        return ProjectCode.objects.filter(
            series_type='WAAS'
        ).filter(
            models.Q(operation_coordinator=user_full_name) |
            models.Q(backup_coordinator=user_full_name)
        )
    
    # Finance Manager - all projects (all series)
    if user.role == 'finance_manager':
        return ProjectCode.objects.all()
    
    # CRM Executive - only assigned projects (same as Sales Manager)
    if user.role == 'crm_executive':
        return ProjectCode.objects.filter(
            sales_manager=user.get_full_name()
        )

    # Sales Manager - only assigned (all series)
    if user.role == 'sales_manager':
        return ProjectCode.objects.filter(
            sales_manager=user.get_full_name()
        )

    # Client, Vendor - special handling
    if user.role in ['client', 'vendor']:
        # TODO: Implement client/vendor project filtering
        return ProjectCode.objects.none()

    return ProjectCode.objects.none()


# ============================================================================
# PERMISSION DECORATORS
# ============================================================================

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import models 


def require_permission(module, action):
    """
    Decorator to check if user has permission for specific action
    
    Usage:
        @require_permission('billing', 'create')
        def create_billing_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            if not has_permission(request.user, module, action):
                messages.error(
                    request,
                    f'You do not have permission to {action} {module}.'
                )
                raise PermissionDenied
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def require_role(*allowed_roles):
    """
    Decorator to check if user has one of the allowed roles
    
    Usage:
        @require_role('admin', 'super_user', 'finance_manager')
        def financial_report_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            if request.user.role not in allowed_roles:
                messages.error(
                    request,
                    'You do not have permission to access this page.'
                )
                raise PermissionDenied
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def admin_required(view_func):
    """
    Decorator to require admin role
    
    Usage:
        @admin_required
        def delete_project_view(request, project_id):
            ...
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if request.user.role != 'admin':
            messages.error(
                request,
                'Only Admin can perform this action.'
            )
            raise PermissionDenied
        
        return view_func(request, *args, **kwargs)
    return wrapped_view


def operations_team_required(view_func):
    """
    Decorator to require operations team role
    
    Usage:
        @operations_team_required
        def create_billing_view(request):
            ...
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if not request.user.is_operations_team:
            messages.error(
                request,
                'Only Operations team can access this page.'
            )
            raise PermissionDenied
        
        return view_func(request, *args, **kwargs)
    return wrapped_view


# ============================================================================
# TEMPLATE CONTEXT PROCESSOR
# ============================================================================

def permissions_context(request):
    """
    Add permissions to template context
    Makes permissions available in all templates
    
    Add to settings.py TEMPLATES context_processors:
        'accounts.permissions.permissions_context',
    
    Usage in templates:
        {% if perms.billing.create %}
            <a href="{% url 'create_billing' %}">Create Billing</a>
        {% endif %}
    """
    if not request.user.is_authenticated:
        return {'perms': {}}
    
    return {
        'perms': get_user_permissions(request.user),
        'can_delete': can_delete_records(request.user),
        'can_see_margins': can_see_margins(request.user),
        'is_operations_team': request.user.is_operations_team,
        'is_management': request.user.is_management,
        'is_admin_or_superuser': request.user.is_admin_or_superuser,
    }