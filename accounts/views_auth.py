"""
Authentication Views - Login and Logout
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache


def _redirect_to_role_dashboard(user):
    """
    Helper function to redirect users to their appropriate dashboard based on role
    Each role gets its own dedicated URL
    """
    role_dashboard_map = {
        'admin': 'accounts:admin_dashboard',
        'super_user': 'accounts:super_user_dashboard',
        'backoffice': 'accounts:backoffice_dashboard',
        'finance_manager': 'accounts:finance_manager_dashboard',
        'operation_manager': 'accounts:operation_manager_dashboard',
        'operation_coordinator': 'accounts:operation_coordinator_dashboard',
        'operation_controller': 'accounts:operation_controller_dashboard',
        'sales_manager': 'accounts:sales_manager_dashboard',
        'crm_executive': 'accounts:crm_executive_dashboard',
        'warehouse_manager': 'accounts:warehouse_manager_dashboard',
        'supply_manager': 'accounts:supply_manager_dashboard',
    }

    dashboard_url = role_dashboard_map.get(user.role, 'accounts:dashboard')
    return redirect(dashboard_url)


def login_view(request):
    """
    User login view
    """
    # Redirect if already logged in
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        # Rate limiting: max 5 attempts per IP in 5 minutes
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')).split(',')[0].strip()
        cache_key = f'login_attempts_{ip}'
        attempts = cache.get(cache_key, 0)
        if attempts >= 5:
            messages.error(request, "Too many login attempts. Please try again in 5 minutes.")
            return render(request, 'accounts/login.html')

        username = request.POST.get('username')
        password = request.POST.get('password')

        # Authenticate user
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_active:
                cache.delete(cache_key)  # Clear rate limit on success
                login(request, user)
                messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")

                # Redirect to next parameter or dashboard (validate to prevent open redirect)
                from django.utils.http import url_has_allowed_host_and_scheme
                next_url = request.GET.get('next', '')
                if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    return redirect(next_url)
                return redirect('accounts:dashboard')
            else:
                messages.error(request, "Your account has been deactivated. Please contact administrator.")
        else:
            cache.set(cache_key, attempts + 1, 300)  # 5-minute window
            messages.error(request, "Invalid username or password.")
    
    return render(request, 'accounts/login.html')


@login_required
def logout_view(request):
    """
    User logout view
    """
    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect('accounts:login')