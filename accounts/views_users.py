"""
User Management Views
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count

from accounts.models import User, PasswordHistory, ImpersonationLog


@login_required
def user_list_view(request):
    """
    Display list of all users
    Access: Admin, Super User, Director
    """
    # Check permissions
    if request.user.role not in ['admin', 'super_user', 'director']:
        messages.error(request, "You don't have permission to view users.")
        return redirect('accounts:dashboard')
    
    # Get all users
    users = User.objects.all().order_by('first_name', 'last_name')
    
    # Filter by search query if provided
    search_query = request.GET.get('search', '')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Filter by role if provided
    role_filter = request.GET.get('role', '')
    if role_filter:
        users = users.filter(role=role_filter)
    
    # Filter by active status
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    
    # Get role choices for filter dropdown
    role_choices = User.ROLE_CHOICES

    # Calculate user statistics — single aggregate query
    _user_stats = User.objects.aggregate(
        total_users=Count('id'),
        active_users=Count('id', filter=Q(is_active=True))
    )
    total_users = _user_stats['total_users']
    active_users = _user_stats['active_users']

    context = {
        'users': users,
        'search_query': search_query,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'role_choices': role_choices,
        'total_users': total_users,
        'active_users': active_users,
    }

    return render(request, 'accounts/user_list.html', context)


@login_required
def user_create_view(request):
    """
    Create a new user
    """
    # Check if user has permission
    if request.user.role not in ['admin', 'super_user', 'director']:
        messages.error(request, "You don't have permission to create users.")
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        role = request.POST.get('role')
        phone = request.POST.get('phone', '')
        password = request.POST.get('password')

        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=role,
                phone=phone,
                is_active=True
            )
            messages.success(request, f"User {user.get_full_name()} created successfully!")
            return redirect('accounts:user_list')
        except Exception as e:
            messages.error(request, f"Error creating user: {str(e)}")
    
    context = {
        'role_choices': User.ROLE_CHOICES,
    }
    return render(request, 'accounts/user_create.html', context)


@login_required
def user_edit_view(request, user_id):
    """
    Edit an existing user
    """
    # Check if user has permission
    if request.user.role not in ['admin', 'super_user', 'director']:
        messages.error(request, "You don't have permission to edit users.")
        return redirect('accounts:dashboard')
    
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.role = request.POST.get('role', user.role)
        user.phone = request.POST.get('phone', user.phone)

        # Update password if provided
        new_password = request.POST.get('password')
        if new_password:
            user.set_password(new_password)

        user.save()
        
        messages.success(request, f"User {user.get_full_name()} updated successfully!")
        return redirect('accounts:user_list')
    
    context = {
        'user_obj': user,
        'role_choices': User.ROLE_CHOICES,
    }
    return render(request, 'accounts/user_edit.html', context)


@login_required
def user_delete_view(request, user_id):
    """
    Delete user (soft delete - set inactive)
    Access: Admin, Super User, Director
    """
    # Check permissions
    if request.user.role not in ['admin', 'super_user', 'director']:
        messages.error(request, "You don't have permission to delete users.")
        return redirect('accounts:dashboard')
    
    user = get_object_or_404(User, id=user_id)
    
    # Prevent self-deletion
    if user == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect('accounts:user_list')
    
    if request.method == 'POST':
        # Soft delete - set inactive
        user.is_active = False
        user.save()
        
        messages.success(request, f"User '{user.username}' has been deactivated.")
        return redirect('accounts:user_list')
    
    context = {
        'user_obj': user,
    }
    
    return render(request, 'accounts/user_delete_confirm.html', context)


@login_required
def user_reset_password_view(request, user_id):
    """
    Reset user password - Admin/Super User only with history tracking
    """
    # Check permissions
    if request.user.role not in ['admin', 'super_user', 'director']:
        messages.error(request, "You don't have permission to reset passwords.")
        return redirect('accounts:dashboard')

    user = get_object_or_404(User, id=user_id)

    # Super User cannot reset Admin passwords
    if request.user.role == 'super_user' and user.role == 'admin':
        messages.error(request, 'You cannot reset Admin passwords.')
        return redirect('accounts:user_list')

    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        if new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return redirect('accounts:user_reset_password', user_id=user_id)

        if len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return redirect('accounts:user_reset_password', user_id=user_id)

        # Helper function to get client IP
        def get_client_ip(request):
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            return ip

        # Record to history BEFORE changing
        PasswordHistory.objects.create(
            user=user,
            password_hash=user.password,
            changed_by=request.user,
            ip_address=get_client_ip(request),
            reason=f'Admin reset by {request.user.username}'
        )

        # Change password
        user.set_password(new_password)
        user.save()

        messages.success(request, f'Password reset for {user.username} successfully.')
        return redirect('accounts:user_list')

    context = {
        'reset_user': user,
    }

    return render(request, 'accounts/user_reset_password.html', context)


@login_required
def user_permissions_view(request, user_id):
    """
    Manage specific user permissions and roles
    """
    # Check if user has permission
    if request.user.role not in ['admin', 'super_user', 'director']:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('accounts:dashboard')

    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        # Handle role change
        new_role = request.POST.get('role')
        if new_role in dict(User.ROLE_CHOICES).keys():
            user.role = new_role
            user.save()
            messages.success(request, f"Role updated for {user.get_full_name()}")
            return redirect('accounts:user_list')

    context = {
        'user_obj': user,
        'role_choices': User.ROLE_CHOICES,
    }

    return render(request, 'accounts/user_permissions.html', context)


@login_required
def password_history_view(request, user_id=None):
    """
    View password history for a user
    Access: Admin, Super User, Director
    """
    # Check permissions
    if request.user.role not in ['admin', 'super_user', 'director']:
        messages.error(request, "You don't have permission to view password history.")
        return redirect('accounts:dashboard')

    if user_id:
        user = get_object_or_404(User, id=user_id)
        password_history = PasswordHistory.objects.filter(user=user).select_related('changed_by').order_by('-changed_at')
        context = {
            'target_user': user,
            'history': password_history,
        }
        return render(request, 'accounts/password_history.html', context)
    else:
        # Show all password history
        password_history = PasswordHistory.objects.all().select_related('user', 'changed_by').order_by('-changed_at')[:100]
        context = {
            'history': password_history,
        }
        return render(request, 'accounts/password_history_all.html', context)


@login_required
def impersonate_user(request, user_id):
    """
    Impersonate another user (admin access to user account without password)
    Access: Admin, Super User only
    """
    from django.contrib.auth import login

    # Check permissions
    if request.user.role not in ['admin', 'super_user']:
        messages.error(request, "You don't have permission to impersonate users.")
        return redirect('accounts:dashboard')

    # Get the user to impersonate
    target_user = get_object_or_404(User, id=user_id)

    # Don't allow impersonating yourself
    if target_user == request.user:
        messages.error(request, "You cannot impersonate yourself.")
        return redirect('accounts:user_list')

    # Store admin details before login() rotates the session
    admin_id = request.user.id
    started_at = timezone.now().isoformat()

    # Get reason if provided
    reason = request.POST.get('reason', 'Admin testing/support')

    # Log the impersonation
    ip_address = request.META.get('REMOTE_ADDR')
    impersonation = ImpersonationLog.objects.create(
        admin=request.user,
        impersonated_user=target_user,
        ip_address=ip_address,
        reason=reason
    )

    # Login as the target user (switches the session key)
    login(request, target_user, backend='django.contrib.auth.backends.ModelBackend')

    # Set session values AFTER login() so they survive the session cycle
    request.session['impersonate_admin_id'] = admin_id
    request.session['impersonate_started_at'] = started_at
    request.session['impersonation_log_id'] = impersonation.id

    messages.success(
        request,
        f"🎭 You are now impersonating {target_user.get_full_name()}. Click 'Stop Impersonation' to return to your account."
    )

    return redirect('accounts:dashboard')


@login_required
def stop_impersonation(request):
    """
    Stop impersonating and return to admin account
    """
    from django.contrib.auth import login

    admin_id = request.session.get('impersonate_admin_id')
    impersonation_log_id = request.session.get('impersonation_log_id')

    if not admin_id:
        messages.error(request, "You are not currently impersonating anyone.")
        return redirect('accounts:dashboard')

    # Get the admin user
    admin_user = get_object_or_404(User, id=admin_id)

    # Update the impersonation log with end time
    if impersonation_log_id:
        try:
            impersonation = ImpersonationLog.objects.get(id=impersonation_log_id)
            impersonation.ended_at = timezone.now()
            impersonation.save()
        except ImpersonationLog.DoesNotExist:
            pass

    # Clear session variables
    del request.session['impersonate_admin_id']
    del request.session['impersonation_log_id']
    if 'impersonate_started_at' in request.session:
        del request.session['impersonate_started_at']

    # Login back as admin
    login(request, admin_user, backend='django.contrib.auth.backends.ModelBackend')

    messages.success(request, f"✅ Stopped impersonation. Welcome back, {admin_user.get_full_name()}!")

    return redirect('accounts:user_list')


@login_required
def impersonation_logs_view(request):
    """
    View all impersonation logs
    Access: Admin, Super User only
    """
    # Check permissions
    if request.user.role not in ['admin', 'super_user']:
        messages.error(request, "You don't have permission to view impersonation logs.")
        return redirect('accounts:dashboard')

    logs = ImpersonationLog.objects.all().select_related('admin', 'impersonated_user').order_by('-started_at')[:100]

    context = {
        'logs': logs,
    }

    return render(request, 'accounts/impersonation_logs.html', context)