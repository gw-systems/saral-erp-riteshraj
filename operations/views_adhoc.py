import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.utils import timezone
from django.db import transaction, connection
from datetime import datetime, timedelta
from accounts.error_utils import log_caught_exception

logger = logging.getLogger(__name__)
from projects.models import ProjectCode
from operations.models_adhoc import AdhocBillingEntry, AdhocBillingLineItem, AdhocBillingAttachment
from dropdown_master_data.models import AdhocChargeType, AdhocBillingStatus, TransactionSide


@login_required
def adhoc_billing_create(request):
    """
    Create new adhoc billing entry with multiple line items.
    Supports dynamic client and vendor line items with attachments.
    """
    
    # 1. Check Permissions
    if request.user.role not in ['admin', 'super_user', 'operation_manager', 'operation_coordinator', 'operation_controller']:
        messages.error(request, "Access denied. You don't have permission to create adhoc billing entries.")
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # 2. Extract Common Data
                project_id = request.POST.get('project')
                event_date_str = request.POST.get('event_date')
                
                if not project_id or not event_date_str:
                    raise ValueError("Project and Event Date are required")
                
                # Parse event date
                event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
                service_month = event_date.replace(day=1)
                
                # 3. Get Project
                project = ProjectCode.objects.get(project_id=project_id)
                
                # 4. Extract Client Line Items
                client_charge_types = request.POST.getlist('client_charge_type[]')
                client_descriptions = request.POST.getlist('client_description[]')
                client_quantities = request.POST.getlist('client_quantity[]')
                client_rates = request.POST.getlist('client_rate[]')
                client_units = request.POST.getlist('client_unit[]')
                
                # 5. Extract Vendor Line Items
                vendor_charge_types = request.POST.getlist('vendor_charge_type[]')
                vendor_descriptions = request.POST.getlist('vendor_description[]')
                vendor_quantities = request.POST.getlist('vendor_quantity[]')
                vendor_rates = request.POST.getlist('vendor_rate[]')
                vendor_units = request.POST.getlist('vendor_unit[]')
                
                # 6. Validation: At least one line item in both sides
                if not client_charge_types or not vendor_charge_types:
                    raise ValueError("At least one Client and one Vendor line item are required")
                
                # 7. Validate Attachments
                client_files = request.FILES.getlist('client_attachments')
                vendor_files = request.FILES.getlist('vendor_attachments')
                
                if not client_files:
                    raise ValueError("Client approval attachment is required")
                if not vendor_files:
                    raise ValueError("Vendor bill attachment is required")
                
                # 8. Get status and transaction side objects
                pending_status = AdhocBillingStatus.objects.get(code='pending')
                client_side = TransactionSide.objects.get(code='client')
                vendor_side = TransactionSide.objects.get(code='vendor')

                # 9. Create Entry Header
                entry = AdhocBillingEntry.objects.create(
                    project=project,
                    event_date=event_date,
                    service_month=service_month,
                    created_by=request.user,
                    status=pending_status
                )

                # 9. Create Client Line Items
                for i in range(len(client_charge_types)):
                    if not all([client_charge_types[i], client_descriptions[i],
                               client_quantities[i], client_rates[i], client_units[i]]):
                        raise ValueError(f"All fields are required for client line item {i+1}")

                    # Get AdhocChargeType object
                    charge_type_obj = AdhocChargeType.objects.get(code=client_charge_types[i])

                    AdhocBillingLineItem.objects.create(
                        entry=entry,
                        side=client_side,
                        charge_type=charge_type_obj,
                        description=client_descriptions[i],
                        quantity=float(client_quantities[i]),
                        rate=float(client_rates[i]),
                        unit=client_units[i],
                        amount=float(client_quantities[i]) * float(client_rates[i])
                    )

                # 10. Create Vendor Line Items
                for i in range(len(vendor_charge_types)):
                    if not all([vendor_charge_types[i], vendor_descriptions[i],
                               vendor_quantities[i], vendor_rates[i], vendor_units[i]]):
                        raise ValueError(f"All fields are required for vendor line item {i+1}")

                    # Get AdhocChargeType object
                    charge_type_obj = AdhocChargeType.objects.get(code=vendor_charge_types[i])

                    AdhocBillingLineItem.objects.create(
                        entry=entry,
                        side=vendor_side,
                        charge_type=charge_type_obj,
                        description=vendor_descriptions[i],
                        quantity=float(vendor_quantities[i]),
                        rate=float(vendor_rates[i]),
                        unit=vendor_units[i],
                        amount=float(vendor_quantities[i]) * float(vendor_rates[i])
                    )
                
                # 11. Recalculate Totals
                entry.recalculate_totals()
                
                # 12. Save Client Attachments
                for f in client_files:
                    AdhocBillingAttachment.objects.create(
                        entry=entry,
                        file=f,
                        filename=f.name,
                        attachment_type='client_approval',
                        uploaded_by=request.user
                    )
                
                # 13. Save Vendor Attachments
                for f in vendor_files:
                    AdhocBillingAttachment.objects.create(
                        entry=entry,
                        file=f,
                        filename=f.name,
                        attachment_type='vendor_bill',
                        uploaded_by=request.user
                    )
                
                messages.success(request, f"✅ Adhoc entry created successfully for {project.project_code}")
                return redirect('operations:adhoc_billing_list')

        except ValueError as e:
            messages.error(request, f"⚠️ Validation Error: {str(e)}")
        except ProjectCode.DoesNotExist:
            messages.error(request, "Project not found.")
        except Exception as e:
            logger.exception("Adhoc billing create error")
            log_caught_exception(request, e)
            messages.error(request, f"System Error: {str(e)}")
            connection.close()
            return redirect('operations:adhoc_billing_create')

    # ========================================================
    # RENDER FORM (GET Request or POST Error)
    # ========================================================

    # Get projects based on role
    if request.user.role in ['admin', 'super_user', 'operation_controller']:
        projects = ProjectCode.objects.filter(
            series_type='WAAS',
            project_status__in=['Active', 'Operation Not Started']
        ).order_by('client_name')
        
    elif request.user.role == 'operation_manager':
        projects = ProjectCode.objects.filter(
            series_type='WAAS',
            project_status__in=['Active', 'Operation Not Started'],
            operation_coordinator=request.user.get_full_name()
        ).order_by('client_name')
        
    elif request.user.role == 'operation_coordinator':
        projects = ProjectCode.objects.filter(
            series_type='WAAS',
            project_status__in=['Active', 'Operation Not Started']
        ).filter(
            Q(operation_coordinator=request.user.get_full_name()) |
            Q(backup_coordinator=request.user.get_full_name())
        ).order_by('client_name')
    else:
        projects = ProjectCode.objects.none()
    
    context = {
        'projects': projects,
        'charge_types': AdhocChargeType.objects.filter(is_active=True).order_by('display_order'),

    }
    
    return render(request, 'operations/adhoc_billing_create.html', context)


@login_required
def adhoc_billing_list(request):
    """List all adhoc billing entries with new split totals"""
    
    # 1. Permission Check
    if request.user.role not in ['operation_coordinator', 'operation_manager', 'operation_controller', 'backoffice', 'admin']:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')
    
    # 2. Get Filters
    status_filter = request.GET.get('status', '')
    charge_type_filter = request.GET.get('charge_type', '')
    search_query = request.GET.get('search', '')
    
    # 3. Base Queryset (WAAS Only)
    if request.user.role in ['admin', 'super_user', 'operation_controller', 'backoffice']:
        entries = AdhocBillingEntry.objects.filter(
            project__series_type='WAAS'
        ).select_related('project', 'created_by')
        
    elif request.user.role == 'operation_manager':
        entries = AdhocBillingEntry.objects.filter(
            project__series_type='WAAS',
            project__operation_coordinator=request.user.get_full_name()
        ).select_related('project', 'created_by')
        
    elif request.user.role == 'operation_coordinator':
        entries = AdhocBillingEntry.objects.filter(
            project__series_type='WAAS'
        ).filter(
            Q(project__operation_coordinator=request.user.get_full_name()) |
            Q(project__backup_coordinator=request.user.get_full_name())
        ).select_related('project', 'created_by')
    else:
        entries = AdhocBillingEntry.objects.none()
    
    # 4. Apply Filters
    if status_filter:
        entries = entries.filter(status__code=status_filter)
    if charge_type_filter:
        # Filter by charge type in line items
        entries = entries.filter(line_items__charge_type__code=charge_type_filter).distinct()
    if search_query:
        entries = entries.filter(
            Q(project__project_code__icontains=search_query) |
            Q(project__client_name__icontains=search_query) |
            Q(line_items__description__icontains=search_query) |
            Q(billing_remarks__icontains=search_query)
        ).distinct()
    
    # 5. Order & Aggregate
    entries = entries.order_by('-event_date', '-created_at')
    
    # Calculate Totals (Updated for Client/Vendor split)
    total_client_amount = sum(e.total_client_amount for e in entries)
    total_vendor_amount = sum(e.total_vendor_amount for e in entries)

    pending_count = entries.filter(status__code='pending').count()
    billed_count = entries.filter(status__code='billed').count()

    # Prefetch line items to avoid N+1 queries
    from django.db.models import Prefetch, Count, Q as QAnnotate
    from operations.models_adhoc import AdhocBillingLineItem
    entries = entries.prefetch_related(
        Prefetch('line_items', queryset=AdhocBillingLineItem.objects.select_related('side', 'charge_type'))
    )

    # Annotate counts instead of querying in loop
    entries_with_counts = entries.annotate(
        client_items_count=Count('line_items', filter=QAnnotate(line_items__side__code='client')),
        vendor_items_count=Count('line_items', filter=QAnnotate(line_items__side__code='vendor'))
    )

    entries = entries_with_counts

    context = {
        'entries': entries,
        'status_filter': status_filter,
        'charge_type_filter': charge_type_filter,
        'search_query': search_query,
        'total_client_amount': total_client_amount,
        'total_vendor_amount': total_vendor_amount,
        'pending_count': pending_count,
        'billed_count': billed_count,
        'charge_types': AdhocChargeType.objects.filter(is_active=True).order_by('display_order'),
    }
    
    return render(request, 'operations/adhoc_billing_list.html', context)





@login_required
def adhoc_billing_detail(request, entry_id):
    """View adhoc billing entry details"""
    entry = get_object_or_404(AdhocBillingEntry, id=entry_id)
    
    # Permission Check
    if request.user.role == 'operation_coordinator':
        user_name = request.user.get_full_name()
        if entry.project.operation_coordinator != user_name and entry.project.backup_coordinator != user_name:
            messages.error(request, "You don't have permission to view this entry.")
            return redirect('operations:adhoc_billing_list')
    elif request.user.role not in ['operation_manager', 'backoffice', 'admin', 'operation_controller']:
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')
    
    # Separate attachments for display with signed URLs
    from datetime import timedelta
    from google.cloud import storage
    from google.oauth2 import service_account
    import json
    import os

    client_attachments = entry.attachments.filter(attachment_type='client_approval')
    vendor_attachments = entry.attachments.filter(attachment_type='vendor_bill')
    other_attachments = entry.attachments.filter(attachment_type='other')

    # Generate signed URLs for all attachments
    if os.getenv('K_SERVICE'):  # Only in production
        try:
            credentials_json = os.getenv('GCS_CREDENTIALS')
            credentials_dict = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(credentials_dict)
            
            client = storage.Client(credentials=credentials, project='saral-erp-479508')
            bucket = client.bucket('saral-erp-media-prod')
            
            # Add signed URLs to each attachment
            for attachment in list(client_attachments) + list(vendor_attachments) + list(other_attachments):
                if attachment.file:
                    # Extract blob name from file path
                    blob_name = attachment.file.name
                    blob = bucket.blob(blob_name)
                    attachment.signed_url = blob.generate_signed_url(
                        version="v4",
                        expiration=timedelta(hours=168),  # 7 days
                        method="GET"
                    )
        except Exception as e:
            logger.warning(f"Error generating signed URLs: {e}")
    
    client_items = entry.line_items.filter(side__code='client')
    vendor_items = entry.line_items.filter(side__code='vendor')

    context = {
        'entry': entry,
        'client_items': client_items,
        'vendor_items': vendor_items,
        'client_items_count': client_items.count(),
        'vendor_items_count': vendor_items.count(),
        'client_attachments': client_attachments,
        'vendor_attachments': vendor_attachments,
        'other_attachments': other_attachments,
    }
    return render(request, 'operations/adhoc_billing_detail.html', context)



@login_required
def adhoc_billing_edit(request, entry_id):
    """Edit adhoc billing entry with line items support"""
    entry = get_object_or_404(
        AdhocBillingEntry.objects.prefetch_related('line_items', 'attachments'),
        id=entry_id
    )
    
    # Permission Check
    if request.user.role == 'operation_coordinator':
        user_name = request.user.get_full_name()
        if entry.project.operation_coordinator != user_name and entry.project.backup_coordinator != user_name:
            messages.error(request, "Access denied.")
            return redirect('operations:adhoc_billing_list')
    elif request.user.role not in ['admin', 'super_user', 'operation_manager', 'operation_controller']:
        messages.error(request, "Access denied.")
        return redirect('operations:adhoc_billing_list')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # 1. Update Entry Header
                project_id = request.POST.get('project')
                event_date_str = request.POST.get('event_date')
                status_code = request.POST.get('status')
                billing_remarks = request.POST.get('billing_remarks', '')

                if not project_id or not event_date_str:
                    raise ValueError("Project and Event Date are required")

                # Update basic fields
                entry.project = ProjectCode.objects.get(project_id=project_id)
                entry.event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
                entry.service_month = entry.event_date.replace(day=1)

                # Get AdhocBillingStatus object if status is being updated
                if status_code:
                    entry.status = AdhocBillingStatus.objects.get(code=status_code)

                entry.billing_remarks = billing_remarks
                entry.save()
                
                # 2. Extract Client Line Items from POST
                client_item_ids = request.POST.getlist('client_item_id[]')
                client_charge_types = request.POST.getlist('client_charge_type[]')
                client_descriptions = request.POST.getlist('client_description[]')
                client_quantities = request.POST.getlist('client_quantity[]')
                client_rates = request.POST.getlist('client_rate[]')
                client_units = request.POST.getlist('client_unit[]')
                
                # 3. Extract Vendor Line Items from POST
                vendor_item_ids = request.POST.getlist('vendor_item_id[]')
                vendor_charge_types = request.POST.getlist('vendor_charge_type[]')
                vendor_descriptions = request.POST.getlist('vendor_description[]')
                vendor_quantities = request.POST.getlist('vendor_quantity[]')
                vendor_rates = request.POST.getlist('vendor_rate[]')
                vendor_units = request.POST.getlist('vendor_unit[]')
                
                # Validation
                if not client_charge_types or not vendor_charge_types:
                    raise ValueError("At least one Client and one Vendor line item are required")
                
                # 4. Track which line items we're keeping (to delete removed ones later)
                kept_item_ids = set()

                # Get TransactionSide objects once
                client_side = TransactionSide.objects.get(code='client')
                vendor_side = TransactionSide.objects.get(code='vendor')

                # 5. Process Client Line Items (Update existing or Create new)
                for i in range(len(client_charge_types)):
                    if not all([client_charge_types[i], client_descriptions[i],
                               client_quantities[i], client_rates[i], client_units[i]]):
                        raise ValueError(f"All fields are required for client line item {i+1}")

                    item_id = client_item_ids[i] if i < len(client_item_ids) else ''

                    # Get AdhocChargeType object
                    charge_type_obj = AdhocChargeType.objects.get(code=client_charge_types[i])

                    if item_id:  # Update existing
                        try:
                            item = AdhocBillingLineItem.objects.get(id=item_id, entry=entry)
                            item.charge_type = charge_type_obj
                            item.description = client_descriptions[i]
                            item.quantity = float(client_quantities[i])
                            item.rate = float(client_rates[i])
                            item.unit = client_units[i]
                            item.amount = float(client_quantities[i]) * float(client_rates[i])
                            item.save()
                            kept_item_ids.add(int(item_id))
                        except AdhocBillingLineItem.DoesNotExist:
                            pass  # Item was deleted, create new one below

                    if not item_id:  # Create new
                        new_item = AdhocBillingLineItem.objects.create(
                            entry=entry,
                            side=client_side,
                            charge_type=charge_type_obj,
                            description=client_descriptions[i],
                            quantity=float(client_quantities[i]),
                            rate=float(client_rates[i]),
                            unit=client_units[i],
                            amount=float(client_quantities[i]) * float(client_rates[i])
                        )
                        kept_item_ids.add(new_item.id)
                
                # 6. Process Vendor Line Items (Update existing or Create new)
                for i in range(len(vendor_charge_types)):
                    if not all([vendor_charge_types[i], vendor_descriptions[i],
                               vendor_quantities[i], vendor_rates[i], vendor_units[i]]):
                        raise ValueError(f"All fields are required for vendor line item {i+1}")

                    item_id = vendor_item_ids[i] if i < len(vendor_item_ids) else ''

                    # Get AdhocChargeType object
                    charge_type_obj = AdhocChargeType.objects.get(code=vendor_charge_types[i])

                    if item_id:  # Update existing
                        try:
                            item = AdhocBillingLineItem.objects.get(id=item_id, entry=entry)
                            item.charge_type = charge_type_obj
                            item.description = vendor_descriptions[i]
                            item.quantity = float(vendor_quantities[i])
                            item.rate = float(vendor_rates[i])
                            item.unit = vendor_units[i]
                            item.amount = float(vendor_quantities[i]) * float(vendor_rates[i])
                            item.save()
                            kept_item_ids.add(int(item_id))
                        except AdhocBillingLineItem.DoesNotExist:
                            pass  # Item was deleted, create new one below

                    if not item_id:  # Create new
                        new_item = AdhocBillingLineItem.objects.create(
                            entry=entry,
                            side=vendor_side,
                            charge_type=charge_type_obj,
                            description=vendor_descriptions[i],
                            quantity=float(vendor_quantities[i]),
                            rate=float(vendor_rates[i]),
                            unit=vendor_units[i],
                            amount=float(vendor_quantities[i]) * float(vendor_rates[i])
                        )
                        kept_item_ids.add(new_item.id)
                
                # 7. Delete line items that were removed (exist in DB but not in POST)
                all_existing_ids = set(entry.line_items.values_list('id', flat=True))
                items_to_delete = all_existing_ids - kept_item_ids
                if items_to_delete:
                    AdhocBillingLineItem.objects.filter(id__in=items_to_delete).delete()
                
                # 8. Recalculate Totals
                entry.recalculate_totals()
                
                # 9. Handle New Attachments (Client)
                client_files = request.FILES.getlist('client_attachments')
                for f in client_files:
                    AdhocBillingAttachment.objects.create(
                        entry=entry,
                        file=f,
                        filename=f.name,
                        attachment_type='client_approval',
                        uploaded_by=request.user
                    )
                
                # 10. Handle New Attachments (Vendor)
                vendor_files = request.FILES.getlist('vendor_attachments')
                for f in vendor_files:
                    AdhocBillingAttachment.objects.create(
                        entry=entry,
                        file=f,
                        filename=f.name,
                        attachment_type='vendor_bill',
                        uploaded_by=request.user
                    )
                
                messages.success(request, f"✅ Adhoc entry #{entry.id} updated successfully!")
                return redirect('operations:adhoc_billing_detail', entry_id=entry.id)

        except ValueError as e:
            messages.error(request, f"⚠️ Validation Error: {str(e)}")
        except ProjectCode.DoesNotExist:
            messages.error(request, "Project not found.")
        except Exception as e:
            logger.exception("Adhoc billing edit error")
            log_caught_exception(request, e)
            messages.error(request, f"System Error: {str(e)}")
            connection.close()
            return redirect('operations:adhoc_billing_edit', entry_id=entry.id)
    
    # ========================================================
    # RENDER FORM (GET Request or POST Error)
    # ========================================================
    
    # Get projects based on role
    if request.user.role in ['admin', 'super_user', 'operation_controller']:
        projects = ProjectCode.objects.filter(
            series_type='WAAS',
            project_status__in=['Active', 'Operation Not Started']
        ).order_by('client_name')
        
    elif request.user.role == 'operation_manager':
        projects = ProjectCode.objects.filter(
            series_type='WAAS',
            project_status__in=['Active', 'Operation Not Started'],
            operation_coordinator=request.user.get_full_name()
        ).order_by('client_name')
        
    elif request.user.role == 'operation_coordinator':
        projects = ProjectCode.objects.filter(
            series_type='WAAS',
            project_status__in=['Active', 'Operation Not Started']
        ).filter(
            Q(operation_coordinator=request.user.get_full_name()) |
            Q(backup_coordinator=request.user.get_full_name())
        ).order_by('client_name')
    else:
        projects = ProjectCode.objects.none()
    
    context = {
        'entry': entry,
        'projects': projects,
        'charge_types': AdhocChargeType.objects.filter(is_active=True).order_by('display_order'),
        'statuses': AdhocBillingStatus.objects.filter(is_active=True).order_by('display_order'),
        'client_attachments': entry.attachments.filter(attachment_type='client_approval'),
        'vendor_attachments': entry.attachments.filter(attachment_type='vendor_bill'),
    }
    
    return render(request, 'operations/adhoc_billing_edit.html', context)


@login_required
def adhoc_billing_delete(request, entry_id):
    """Delete adhoc billing entry"""
    
    entry = get_object_or_404(AdhocBillingEntry, id=entry_id)
    
    # Check permissions
    if request.user.role == 'operation_coordinator':
        if entry.project.operation_coordinator != request.user.get_full_name():
            messages.error(request, "You don't have permission to delete this entry.")
            return redirect('operations:adhoc_billing_list')
    elif request.user.role not in ['operation_manager', 'backoffice', 'admin']:
        messages.error(request, "You don't have permission to delete adhoc billing entries.")
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        project_code = entry.project.code
        entry.delete()
        messages.success(request, f"Adhoc billing entry for {project_code} deleted.")
        return redirect('operations:adhoc_billing_list')
    
    context = {
        'entry': entry,
    }
    
    return render(request, 'operations/adhoc_billing_delete.html', context)


@login_required
def adhoc_billing_mark_billed(request, entry_id):
    """Mark entry as billed"""
    
    entry = get_object_or_404(AdhocBillingEntry, id=entry_id)
    
    # Check permissions
    if request.user.role not in ['backoffice', 'admin', 'operation_manager']:
        messages.error(request, "You don't have permission to mark entries as billed.")
        return redirect('operations:adhoc_billing_detail', entry_id=entry.id)
    
    entry.mark_as_billed()
    messages.success(request, "Entry marked as billed.")
    
    return redirect('operations:adhoc_billing_detail', entry_id=entry.id)


@login_required
def adhoc_update_status(request, entry_id):
    """
    Update status via Dropdown (Pending <-> Billed <-> Cancelled)
    Allowed for Coordinators now.
    """
    entry = get_object_or_404(AdhocBillingEntry, id=entry_id)
    
    # 1. Permission Check (Explicitly allowing Coordinators now)
    allowed_roles = ['admin', 'super_user', 'backoffice', 'operation_manager', 'operation_controller', 'operation_coordinator']
    
    if request.user.role not in allowed_roles:
        messages.error(request, "Access denied.")
        return redirect(request.META.get('HTTP_REFERER', 'operations:adhoc_billing_list'))

    # Extra check: Coordinators can only modify their own assigned projects
    if request.user.role == 'operation_coordinator':
        user_name = request.user.get_full_name()
        if entry.project.operation_coordinator != user_name and entry.project.backup_coordinator != user_name:
             messages.error(request, "You can only manage your own projects.")
             return redirect(request.META.get('HTTP_REFERER', 'operations:adhoc_billing_list'))

    if request.method == 'POST':
        new_status_code = request.POST.get('status')
        if new_status_code in ['pending', 'billed', 'cancelled']:
            # Get AdhocBillingStatus object
            new_status_obj = AdhocBillingStatus.objects.get(code=new_status_code)
            entry.status = new_status_obj
            entry.save()
            messages.success(request, f"Status updated to {entry.status.label}")
        
    return redirect(request.META.get('HTTP_REFERER', 'operations:adhoc_billing_list'))

