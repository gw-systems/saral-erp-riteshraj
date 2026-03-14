"""
Dashboard Router View
"""

from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages


@login_required
def dashboard_redirect(request):
    """
    Dashboard router - redirects users to their role-specific dashboard
    This is the main entry point when users access /accounts/dashboard/
    """
    user = request.user
    role = user.role
    
    # Route to appropriate dashboard based on role
    if role == 'admin':
        return redirect('accounts:admin_dashboard')
    
    elif role == 'super_user':
        return redirect('accounts:super_user_dashboard')
    
    elif role == 'director':
        return redirect('accounts:director_home')
    
    elif role == 'finance_manager':
        return redirect('accounts:finance_manager_dashboard')
    
    elif role == 'operation_controller':
        return redirect('accounts:operation_controller_dashboard')
    
    elif role == 'operation_manager':
        return redirect('accounts:operation_manager_dashboard')
    
    elif role == 'sales_manager':
        return redirect('accounts:sales_manager_dashboard')
    
    elif role == 'supply_manager':
        return redirect('accounts:supply_manager_dashboard')
    
    elif role == 'operation_coordinator':
        return redirect('accounts:operation_coordinator_dashboard')
    
    elif role == 'warehouse_manager':
        # Warehouse manager dashboard not yet implemented
        messages.info(request, "Warehouse manager dashboard coming soon. Showing supply view.")
        return redirect('accounts:supply_manager_dashboard')
    
    elif role == 'backoffice':
        return redirect('accounts:backoffice_dashboard')
    
    elif role == 'crm_executive':
        return redirect('accounts:crm_executive_dashboard')

    elif role == 'digital_marketing':
        return redirect('accounts:digital_marketing_dashboard')

    elif role == 'client':
        # Client dashboard not yet implemented
        messages.info(request, "Client portal coming soon.")
        return redirect('accounts:login')
    
    elif role == 'vendor':
        # Vendor dashboard not yet implemented
        messages.info(request, "Vendor portal coming soon.")
        return redirect('accounts:login')
    
    else:
        # Unknown role - should not happen but handle gracefully
        messages.error(request, f"No dashboard configured for role: {role}")
        return redirect('accounts:login')


@login_required
def dashboard_view(request):
    """
    Legacy dashboard view function
    Kept for backward compatibility with existing URLs
    Redirects to dashboard_redirect
    """
    return dashboard_redirect(request)