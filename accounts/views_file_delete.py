import logging
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.apps import apps
from django.conf import settings
import os

logger = logging.getLogger(__name__)

ALLOWED_FILE_DELETE_MODELS = {
    ('projects', 'projectdocument'),
    ('projects', 'clientdocument'),
    ('supply', 'vendorwarehousedocument'),
    ('operations', 'adhocbillingattachment'),
}


@login_required
def universal_file_delete(request, app_label, model_name, object_id, field_name):
    """
    Universal file delete endpoint
    Works for any model with FileField/ImageField
    Deletes file from storage (local or GCS) and clears DB field
    
    URL format: /files/delete/<app>/<model>/<id>/<field>/
    Example: /files/delete/projects/projectdocument/123/project_agreement/
    """
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST request required'}, status=405)
    
    try:
        # Validate model is in allowlist
        if (app_label.lower(), model_name.lower()) not in ALLOWED_FILE_DELETE_MODELS:
            return JsonResponse({'error': 'Operation not permitted'}, status=403)

        # Get the model
        Model = apps.get_model(app_label, model_name)
        
        # Get the object
        obj = Model.objects.get(pk=object_id)
        
        # Check permissions
        if not can_delete_file(request.user, obj, field_name):
            messages.error(request, 'You do not have permission to delete this file.')
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Get the file field
        if not hasattr(obj, field_name):
            messages.error(request, f'Field "{field_name}" not found.')
            return JsonResponse({'error': 'Field not found'}, status=404)
        
        file_field = getattr(obj, field_name)
        
        # Check if file exists
        if not file_field or not file_field.name:
            messages.warning(request, 'No file to delete.')
            return JsonResponse({'error': 'No file exists'}, status=404)
        
        # Store filename for message
        filename = file_field.name.split('/')[-1]
        
        # Delete the file from storage (works for both local and GCS)
        try:
            file_field.delete(save=False)  # Don't save yet
        except Exception as e:
            logger.warning(f"Error deleting file from storage: {e}")
            # Continue anyway to clear DB field
        
        # Clear the field in database
        setattr(obj, field_name, None)
        obj.save()
        
        messages.success(request, f'File "{filename}" deleted successfully.')
        return JsonResponse({
            'success': True,
            'message': f'File "{filename}" deleted successfully.'
        })
        
    except Model.DoesNotExist:
        messages.error(request, 'Record not found.')
        return JsonResponse({'error': 'Record not found'}, status=404)
    
    except Exception as e:
        logger.error(f"File delete error ({app_label}.{model_name} id={object_id}): {e}")
        messages.error(request, 'An error occurred while deleting the file.')
        return JsonResponse({'error': 'An error occurred while deleting the file.'}, status=500)


def can_delete_file(user, obj, field_name):
    """
    Check if user has permission to delete this file
    Customize permissions based on model type
    """
    
    # Admins and super users can delete anything
    if user.role in ['admin', 'super_user']:
        return True
    
    # Model-specific permissions
    model_name = obj.__class__.__name__
    
    # Project documents
    if model_name == 'ProjectDocument':
        # Sales managers can delete their own project documents
        if user.role == 'sales_manager':
            return obj.project.sales_manager == user.get_full_name()
        return False
    
    # Client documents
    if model_name == 'ClientDocument':
        # Backoffice and sales managers can delete
        return user.role in ['backoffice', 'sales_manager']
    
    # Warehouse documents
    if model_name == 'VendorWarehouseDocument':
        # Supply managers and warehouse managers can delete
        return user.role in ['supply_manager', 'warehouse_manager']
    
    # Adhoc billing attachments
    if model_name == 'AdhocBillingAttachment':
        # Operation managers and finance managers can delete
        return user.role in ['operation_manager', 'finance_manager']
    
    # Ticket attachments
    if model_name == 'TicketAttachment':
        # Ticket creator or operation managers can delete
        if hasattr(obj, 'ticket'):
            return obj.ticket.created_by == user or user.role == 'operation_manager'
        return False
    
    # Default: deny
    return False