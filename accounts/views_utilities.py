"""
Utility Views - File Manager, Storage Debug, Password Management, Username Change
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from google.cloud import storage
import os
from datetime import datetime

from accounts.models import User, PasswordHistory


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@login_required
def file_manager(request):
    """
    File Manager - Browse and manage files in GCS
    Access: Admin only
    """
    # Check permissions
    if request.user.role != 'admin':
        messages.error(request, "Access denied. Admin users only.")
        return redirect('accounts:dashboard')
    
    try:
        # Initialize GCS client
        storage_client = storage.Client()
        bucket_name = settings.GS_BUCKET_NAME
        bucket = storage_client.bucket(bucket_name)
        
        # Get folder path from query parameter
        folder_path = request.GET.get('path', '')
        
        # List blobs in the bucket
        blobs = list(bucket.list_blobs(prefix=folder_path, delimiter='/'))
        prefixes = list(bucket.list_blobs(prefix=folder_path, delimiter='/').prefixes)
        
        # Organize files and folders
        folders = []
        files = []
        
        # Add folders (prefixes)
        for prefix in prefixes:
            folder_name = prefix.rstrip('/').split('/')[-1]
            folders.append({
                'name': folder_name,
                'path': prefix,
            })
        
        # Add files (blobs)
        for blob in blobs:
            if blob.name != folder_path:  # Exclude the folder itself
                file_name = blob.name.split('/')[-1]
                if file_name:  # Exclude empty names
                    files.append({
                        'name': file_name,
                        'path': blob.name,
                        'size': blob.size,
                        'size_mb': round(blob.size / (1024 * 1024), 2),
                        'updated': blob.updated,
                        'url': blob.public_url,
                    })
        
        # Calculate total size
        total_size = sum([f['size'] for f in files])
        total_size_mb = round(total_size / (1024 * 1024), 2)
        
        context = {
            'current_path': folder_path,
            'folders': folders,
            'files': files,
            'total_files': len(files),
            'total_size_mb': total_size_mb,
            'bucket_name': bucket_name,
        }
        
        return render(request, 'accounts/file_manager.html', context)
        
    except Exception as e:
        messages.error(request, f"Error accessing file storage: {str(e)}")
        return redirect('accounts:dashboard')


@login_required
def file_delete(request, file_path):
    """
    Delete file from GCS
    Access: Admin only
    """
    # Check permissions
    if request.user.role != 'admin':
        messages.error(request, "Access denied. Admin users only.")
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        try:
            # Initialize GCS client
            storage_client = storage.Client()
            bucket_name = settings.GS_BUCKET_NAME
            bucket = storage_client.bucket(bucket_name)
            
            # Delete the blob
            blob = bucket.blob(file_path)
            blob.delete()
            
            messages.success(request, f"File '{file_path}' deleted successfully.")
            
        except Exception as e:
            messages.error(request, f"Error deleting file: {str(e)}")
    
    # Redirect back to file manager
    folder_path = '/'.join(file_path.split('/')[:-1])
    return redirect(f"{request.META.get('HTTP_REFERER', 'accounts:file_manager')}?path={folder_path}")


@login_required
def storage_debug(request):
    """
    Storage debug view - Display storage configuration and test
    Access: Admin only
    """
    # Check permissions
    if request.user.role != 'admin':
        messages.error(request, "Access denied. Admin users only.")
        return redirect('accounts:dashboard')
    
    debug_info = {
        'default_storage': settings.DEFAULT_FILE_STORAGE,
        'gs_bucket_name': getattr(settings, 'GS_BUCKET_NAME', 'Not set'),
        'gs_project_id': getattr(settings, 'GS_PROJECT_ID', 'Not set'),
        'media_url': settings.MEDIA_URL,
        'media_root': settings.MEDIA_ROOT,
        'static_url': settings.STATIC_URL,
    }
    
    # Test GCS connection
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(settings.GS_BUCKET_NAME)
        
        # Try to list blobs
        blobs = list(bucket.list_blobs(max_results=5))
        
        debug_info['gcs_connection'] = 'Success'
        debug_info['sample_files'] = [blob.name for blob in blobs]
        
        # Get bucket info
        bucket.reload()
        debug_info['bucket_location'] = bucket.location
        debug_info['bucket_storage_class'] = bucket.storage_class
        
    except Exception as e:
        debug_info['gcs_connection'] = f'Failed: {str(e)}'
        debug_info['sample_files'] = []
    
    context = {
        'debug_info': debug_info,
    }
    
    return render(request, 'accounts/storage_debug.html', context)


@login_required
def change_password_view(request):
    """
    Change password for current user
    Access: All authenticated users
    """
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            
            # Save password history
            PasswordHistory.objects.create(
                user=user,
                password_hash=user.password
            )
            
            # Update session to prevent logout
            update_session_auth_hash(request, user)
            
            messages.success(request, "Your password was successfully updated!")
            return redirect('accounts:profile')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PasswordChangeForm(request.user)
    
    context = {
        'form': form,
    }
    
    return render(request, 'accounts/change_password.html', context)


@login_required
def change_username_view(request, user_id):
    """
    Change username for a user
    Access: Admin only
    """
    # Check permissions
    if request.user.role != 'admin':
        messages.error(request, "Access denied. Admin users only.")
        return redirect('accounts:dashboard')
    
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        new_username = request.POST.get('new_username', '').strip()
        
        if not new_username:
            messages.error(request, "Username cannot be empty.")
            return redirect('accounts:user_edit', user_id=user_id)
        
        # Check if username already exists
        if User.objects.filter(username=new_username).exclude(id=user_id).exists():
            messages.error(request, f"Username '{new_username}' is already taken.")
            return redirect('accounts:user_edit', user_id=user_id)
        
        # Update username
        old_username = user.username
        user.username = new_username
        user.save()
        
        messages.success(request, f"Username changed from '{old_username}' to '{new_username}'.")
        return redirect('accounts:user_edit', user_id=user_id)
    
    context = {
        'user_obj': user,
    }
    
    return render(request, 'accounts/change_username.html', context)


@login_required
def profile_view(request):
    """
    View user profile
    Access: All authenticated users
    """
    user = request.user
    
    # Get password history
    password_history = PasswordHistory.objects.filter(user=user).order_by('-changed_at')[:5]
    
    context = {
        'user': user,
        'password_history': password_history,
    }
    
    return render(request, 'accounts/profile.html', context)


@login_required
def profile_edit_view(request):
    """
    Edit user profile
    Access: All authenticated users
    """
    user = request.user
    
    if request.method == 'POST':
        # Update basic info
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.email = request.POST.get('email', '').strip()
        
        user.save()
        
        messages.success(request, "Profile updated successfully.")
        return redirect('accounts:profile')
    
    context = {
        'user': user,
    }
    
    return render(request, 'accounts/profile_edit.html', context)