import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, HttpResponse
from accounts.permissions import require_role

from .models import ProjectCode
from .models_document import ProjectDocument
from .forms_document import ProjectDocumentForm


@login_required
def project_document_upload(request, project_id):
    """Upload documents for a project"""
    project = get_object_or_404(ProjectCode, project_id=project_id)
    
    # Get or create document record
    document, created = ProjectDocument.objects.get_or_create(
        project=project,
        defaults={'uploaded_by': request.user}
    )
    
    if request.method == 'POST':
        form = ProjectDocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.uploaded_by = request.user
            doc.save()
            messages.success(request, '✅ Documents uploaded successfully!')
            return redirect('projects:project_document_upload', project_id=project_id)
        else:
            messages.error(request, '❌ Please correct the errors below.')
    else:
        form = ProjectDocumentForm(instance=document)
    
    return render(request, 'projects/project_document_upload.html', {
        'form': form,
        'project': project,
        'document': document,
        'is_new': created,
        'page_title': f'Upload Documents - {project.project_code}'
    })


@login_required
def project_document_preview(request, project_id, field_name):
    """
    Preview or download project document
    Works with both local storage (dev) and GCS (production)
    """
    from django.conf import settings
    from django.http import FileResponse, HttpResponse
    import mimetypes
    
    # Get project
    project = get_object_or_404(ProjectCode, project_id=project_id)
    doc = project.documents
    
    # Get the file field
    field_map = {
        'project_agreement': doc.project_agreement,
        'project_addendum_vendor': doc.project_addendum_vendor,
        'project_addendum_client': doc.project_addendum_client,
        'project_handover': doc.project_handover,
    }
    
    file_field = field_map.get(field_name)
    
    if not file_field:
        messages.error(request, f'Document "{field_name}" not found.')
        return redirect('projects:project_detail', project_id=project_id)
    
    # Check if file exists
    if not file_field.name:
        messages.error(request, 'No file uploaded for this document.')
        return redirect('projects:project_detail', project_id=project_id)
    
    try:
        # Check if running in production (GCS) or dev (local)
        if hasattr(settings, 'RUNNING_IN_PRODUCTION') and settings.RUNNING_IN_PRODUCTION:
            # PRODUCTION: Generate signed URL and redirect
            from datetime import timedelta
            from django.utils import timezone
            
            # Generate signed URL (valid for 1 hour)
            blob = file_field.storage.bucket.blob(file_field.name)
            url = blob.generate_signed_url(
                expiration=timedelta(hours=1),
                method='GET'
            )
            
            # Redirect to signed URL
            return redirect(url)
        
        else:
            # DEVELOPMENT: Serve file directly
            file_path = file_field.path
            
            # Guess content type
            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                content_type = 'application/octet-stream'
            
            # Open and serve file
            file_handle = open(file_path, 'rb')
            response = FileResponse(file_handle, content_type=content_type)
            
            # Set filename for download
            filename = file_field.name.split('/')[-1]
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            
            return response
    
    except Exception as e:
        messages.error(request, f'Error accessing file: {str(e)}')
        return redirect('projects:project_detail', project_id=project_id)


@login_required
def project_document_download(request, project_id, field_name):
    """
    Download project document
    Works with both local storage (dev) and GCS (production)
    """
    from django.conf import settings
    from django.http import FileResponse, HttpResponse
    import mimetypes
    
    # Get project
    project = get_object_or_404(ProjectCode, project_id=project_id)
    doc = project.documents
    
    # Get the file field
    field_map = {
        'project_agreement': doc.project_agreement,
        'project_addendum_vendor': doc.project_addendum_vendor,
        'project_addendum_client': doc.project_addendum_client,
        'project_handover': doc.project_handover,
    }
    
    file_field = field_map.get(field_name)
    
    if not file_field:
        messages.error(request, f'Document "{field_name}" not found.')
        return redirect('projects:project_detail', project_id=project_id)
    
    # Check if file exists
    if not file_field.name:
        messages.error(request, 'No file uploaded for this document.')
        return redirect('projects:project_detail', project_id=project_id)
    
    try:
        # Check if running in production (GCS) or dev (local)
        if hasattr(settings, 'RUNNING_IN_PRODUCTION') and settings.RUNNING_IN_PRODUCTION:
            # PRODUCTION: Generate signed URL for download
            from datetime import timedelta
            
            # Generate signed URL for download
            blob = file_field.storage.bucket.blob(file_field.name)
            url = blob.generate_signed_url(
                expiration=timedelta(hours=1),
                method='GET',
                response_disposition='attachment'
            )
            
            # Add download parameter to force download
            if '?' in url:
                url += '&response-content-disposition=attachment'
            else:
                url += '?response-content-disposition=attachment'
            
            # Redirect to signed URL
            return redirect(url)
        
        else:
            # DEVELOPMENT: Serve file directly with download header
            file_path = file_field.path
            
            # Guess content type
            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                content_type = 'application/octet-stream'
            
            # Open and serve file
            file_handle = open(file_path, 'rb')
            response = FileResponse(file_handle, content_type=content_type)
            
            # Force download
            filename = file_field.name.split('/')[-1]
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
    
    except Exception as e:
        messages.error(request, f'Error downloading file: {str(e)}')
        return redirect('projects:project_detail', project_id=project_id)


@login_required
@require_role('admin')
def project_document_delete(request, project_id, field_name):
    """Delete a specific project document"""
    project = get_object_or_404(ProjectCode, project_id=project_id)
    
    try:
        document = ProjectDocument.objects.get(project=project)
        file_field = getattr(document, field_name, None)
        
        if file_field:
            file_field.delete(save=False)
            setattr(document, field_name, None)
            document.save()
            messages.success(request, '✅ Document deleted successfully!')
        else:
            messages.warning(request, '⚠️ Document not found.')
            
    except ProjectDocument.DoesNotExist:
        messages.error(request, '❌ No documents found for this project.')
    
    return redirect('projects:project_document_upload', project_id=project_id)