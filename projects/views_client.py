from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, HttpResponse
from django.db import models
import os
import zipfile
from io import BytesIO
from .forms_client import ClientCardForm, ClientContactForm, ClientGSTForm, ClientDocumentForm
from accounts.permissions import require_role


# Lazy load models to avoid circular imports
def _get_models():
    """Lazy load models to avoid circular imports"""
    from .models_client import ClientCard, ClientContact, ClientGST, ClientDocument
    return ClientCard, ClientContact, ClientGST, ClientDocument


@login_required
def client_card_create(request):
    ClientCard, _, _, _ = _get_models()
    
    if request.method == 'POST':
        form = ClientCardForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, f'Client Card created successfully! Client Code: {client.client_code}')
            return redirect('projects:client_card_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ClientCardForm()
    
    return render(request, 'clients/client_card_create.html', {
        'form': form,
        'page_title': 'Create Client Card'
    })


@login_required
def client_card_list(request):
    from django.core.paginator import Paginator
    from .models import ProjectCode
    from supply.models import VendorWarehouse, Location
    ClientCard, _, _, _ = _get_models()

    # Get all active clients ordered alphabetically
    clients = ClientCard.objects.filter(client_is_active=True).order_by('client_short_name')

    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        clients = clients.filter(
            models.Q(client_short_name__icontains=search_query) |
            models.Q(client_legal_name__icontains=search_query) |
            models.Q(client_code__icontains=search_query) |
            models.Q(client_gst_number__icontains=search_query) |
            models.Q(client_pan_number__icontains=search_query)
        )

    total_count = clients.count()

    # Pagination
    paginator = Paginator(clients, 20)
    page = request.GET.get('page', 1)
    clients_page = paginator.get_page(page)

    # Prefetch all related data in single queries to avoid N+1
    from django.db.models import Prefetch
    from operations.models_projectcard import ProjectCard, StorageRate

    clients_page.object_list = ClientCard.objects.filter(
        client_code__in=[c.client_code for c in clients_page]
    ).prefetch_related(
        Prefetch(
            'projects',
            queryset=ProjectCode.objects.exclude(project_status='Inactive').select_related(
                'vendor_warehouse__warehouse_location_id',
                'vendor_warehouse__vendor_code'
            ).prefetch_related(
                Prefetch(
                    'project_cards',
                    queryset=ProjectCard.objects.prefetch_related(
                        Prefetch(
                            'storage_rates',
                            queryset=StorageRate.objects.filter(rate_for='client').select_related('space_type')
                        )
                    )
                )
            )
        )
    )

    # Add aggregated data for each client in the current page
    for client in clients_page:
        # Get projects for this client (now from prefetched data)
        client_projects = [p for p in client.projects.all()]
        client.project_count = len(client_projects)

        # Get unique vendors from projects (through warehouse)
        vendor_ids = set()
        location_ids = set()
        for project in client_projects:
            if project.vendor_warehouse:
                if project.vendor_warehouse.vendor_code:
                    vendor_ids.add(project.vendor_warehouse.vendor_code.vendor_code)
                if project.vendor_warehouse.warehouse_location_id:
                    location_ids.add(project.vendor_warehouse.warehouse_location_id.id)

        client.vendor_count = len(vendor_ids)
        client.location_count = len(location_ids)

        # Calculate totals for minimum billable area and amount (matching client_card_detail logic)
        total_min_area = 0
        total_min_amount = 0

        for project in client_projects:
            project_cards = list(project.project_cards.all())
            if project_cards:
                project_card = project_cards[0]
                client_rates = list(project_card.storage_rates.all())
                if client_rates:
                    client_rate = client_rates[0]
                    # Add minimum billable area to total (convert pallets to sq ft if needed)
                    if client_rate.minimum_billable_area:
                        area_value = float(client_rate.minimum_billable_area)
                        # Check if space type is pallets
                        if client_rate.space_type and 'pallet' in client_rate.space_type.label.lower():
                            # Convert pallets to sq ft (1 pallet = 25 sq ft)
                            total_min_area += area_value * 25
                        else:
                            # For sq ft or other units, use value directly
                            total_min_area += area_value
                    # Add monthly billable amount to total
                    if client_rate.monthly_billable_amount:
                        total_min_amount += float(client_rate.monthly_billable_amount)

        client.min_billable_area = total_min_area
        client.min_billable_amount = total_min_amount

    return render(request, 'clients/client_card_list.html', {
        'clients': clients_page,
        'total_count': total_count,
        'search_query': search_query,
        'page_title': 'Client Cards'
    })


@login_required
def client_card_detail(request, client_code):
    ClientCard, ClientContact, ClientGST, ClientDocument = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    contacts = ClientContact.objects.filter(client_code=client, client_contact_is_active=True)
    gst_entities = ClientGST.objects.filter(client_code=client)
    
    # Get client documents if they exist
    try:
        documents = ClientDocument.objects.get(client_code=client)
    except ClientDocument.DoesNotExist:
        documents = None
    
    # Get all projects linked to this client (exclude Inactive projects)
    from .models import ProjectCode
    from django.db.models import Sum, Q

    linked_projects = ProjectCode.objects.filter(
        client_card=client
    ).exclude(
        project_status='Inactive'
    ).select_related(
        'vendor_warehouse',
        'vendor_warehouse__vendor_code',
        'vendor_warehouse__warehouse_location_id'
    ).prefetch_related(
        'project_cards',
        'project_cards__storage_rates'
    ).order_by('-created_at')
    
    # Get projects NOT linked to any client (available for linking)
    unlinked_projects = ProjectCode.objects.filter(
        client_card__isnull=True
    ).exclude(
        project_status='Inactive'
    ).select_related(
        'vendor_warehouse',
        'vendor_warehouse__vendor_code'
    ).order_by('client_name', 'project_code')
    
    # Calculate unique vendors (from vendor_warehouse FK)
    unique_vendors = linked_projects.filter(
        vendor_warehouse__isnull=False
    ).values_list(
        'vendor_warehouse__vendor_code__vendor_short_name', 
        flat=True
    ).distinct()
    
    # Calculate unique locations (from vendor_warehouse FK)
    unique_locations = linked_projects.filter(
        vendor_warehouse__isnull=False
    ).values_list(
        'vendor_warehouse__warehouse_location_id__city',
        flat=True
    ).distinct()
    
    # Calculate totals for minimum billable area and amount
    total_min_area = 0
    total_min_amount = 0
    
    for project in linked_projects:
        if project.project_cards.exists():
            project_card = project.project_cards.first()
            if project_card.storage_rates.exists():
                # Get client rate (rate_for='client')
                client_rate = project_card.storage_rates.filter(rate_for='client').first()
                if client_rate:
                    if client_rate.minimum_billable_area:
                        area_value = float(client_rate.minimum_billable_area)
                        # Check if space type is pallets
                        if client_rate.space_type and 'pallet' in client_rate.space_type.label.lower():
                            # Convert pallets to sq ft (1 pallet = 25 sq ft)
                            total_min_area += area_value * 25
                        else:
                            # For sq ft or other units, use value directly
                            total_min_area += area_value
                    if client_rate.monthly_billable_amount:
                        total_min_amount += float(client_rate.monthly_billable_amount)
    
    return render(request, 'clients/client_card_detail.html', {
        'client': client,
        'contacts': contacts,
        'gst_entities': gst_entities,
        'documents': documents,
        'linked_projects': linked_projects,
        'unlinked_projects': unlinked_projects,
        'unique_vendors': list(unique_vendors),
        'unique_locations': list(unique_locations),
        'total_min_area': total_min_area,
        'total_min_amount': total_min_amount,
        'page_title': f'Client: {client.client_short_name}'
    })


@login_required
def client_card_edit(request, client_code):
    ClientCard, _, _, _ = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    
    if request.method == 'POST':
        form = ClientCardForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, 'Client Card updated successfully!')
            return redirect('projects:client_card_detail', client_code=client_code)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ClientCardForm(instance=client)
    
    return render(request, 'clients/client_card_edit.html', {
        'form': form,
        'client': client,
        'page_title': f'Edit Client - {client.client_short_name}'
    })


@login_required
@require_role('admin')
def client_card_delete(request, client_code):
    ClientCard, _, _, _ = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    
    if request.method == 'POST':
        client.client_is_active = False
        client.save()
        messages.success(request, f'Client {client.client_short_name} has been deactivated.')
        return redirect('projects:client_card_list')
    
    return render(request, 'clients/client_card_delete_confirm.html', {
        'client': client,
        'page_title': f'Delete Client - {client.client_short_name}'
    })


@login_required
def client_contact_add(request, client_code):
    ClientCard, ClientContact, _, _ = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    
    if request.method == 'POST':
        form = ClientContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.client_code = client
            contact.save()
            messages.success(request, 'Contact added successfully!')
            return redirect('projects:client_card_detail', client_code=client_code)
    else:
        form = ClientContactForm()
    
    return render(request, 'clients/client_contact_add.html', {
        'form': form,
        'client': client,
        'page_title': f'Add Contact - {client.client_short_name}'
    })


@login_required
def client_contact_edit(request, client_code, contact_id):
    ClientCard, ClientContact, _, _ = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    contact = get_object_or_404(ClientContact, id=contact_id, client_code=client)
    
    if request.method == 'POST':
        form = ClientContactForm(request.POST, instance=contact)
        if form.is_valid():
            form.save()
            messages.success(request, 'Contact updated successfully!')
            return redirect('projects:client_card_detail', client_code=client_code)
    else:
        form = ClientContactForm(instance=contact)
    
    return render(request, 'clients/client_contact_edit.html', {
        'form': form,
        'client': client,
        'contact': contact,
        'page_title': 'Edit Contact'
    })


@login_required
@require_role('admin')
def client_contact_delete(request, client_code, contact_id):
    ClientCard, ClientContact, _, _ = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    contact = get_object_or_404(ClientContact, id=contact_id, client_code=client)
    
    if request.method == 'POST':
        contact.client_contact_is_active = False
        contact.save()
        messages.success(request, 'Contact has been deactivated.')
        return redirect('projects:client_card_detail', client_code=client_code)
    
    return render(request, 'clients/client_contact_delete_confirm.html', {
        'client': client,
        'contact': contact,
        'page_title': 'Delete Contact'
    })


@login_required
def client_gst_add(request, client_code):
    ClientCard, _, ClientGST, _ = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    
    if request.method == 'POST':
        form = ClientGSTForm(request.POST)
        if form.is_valid():
            gst = form.save(commit=False)
            gst.client_code = client
            gst.save()
            messages.success(request, 'GST entity added successfully!')
            return redirect('projects:client_card_detail', client_code=client_code)
    else:
        form = ClientGSTForm()
    
    return render(request, 'clients/client_gst_add.html', {
        'form': form,
        'client': client,
        'page_title': f'Add GST - {client.client_short_name}'
    })


@login_required
def client_gst_edit(request, client_code, gst_id):
    ClientCard, _, ClientGST, _ = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    gst = get_object_or_404(ClientGST, id=gst_id, client_code=client)
    
    if request.method == 'POST':
        form = ClientGSTForm(request.POST, instance=gst)
        if form.is_valid():
            form.save()
            messages.success(request, 'GST entity updated successfully!')
            return redirect('projects:client_card_detail', client_code=client_code)
    else:
        form = ClientGSTForm(instance=gst)
    
    return render(request, 'clients/client_gst_edit.html', {
        'form': form,
        'client': client,
        'gst': gst,
        'page_title': 'Edit GST'
    })


@login_required
@require_role('admin')
def client_gst_delete(request, client_code, gst_id):
    ClientCard, _, ClientGST, _ = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    gst = get_object_or_404(ClientGST, id=gst_id, client_code=client)
    
    if request.method == 'POST':
        gst.client_gst_is_active = False
        gst.save()
        messages.success(request, 'GST entity has been deactivated.')
        return redirect('projects:client_card_detail', client_code=client_code)
    
    return render(request, 'clients/client_gst_delete_confirm.html', {
        'client': client,
        'gst': gst,
        'page_title': 'Delete GST'
    })


@login_required
def client_document_upload(request, client_code):
    """Upload documents for a client"""
    ClientCard, _, _, ClientDocument = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    
    # Get or create document record
    document, created = ClientDocument.objects.get_or_create(
        client_code=client,
        defaults={'client_doc_uploaded_by': request.user}
    )
    
    if request.method == 'POST':
        form = ClientDocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.client_doc_uploaded_by = request.user
            doc.save()
            messages.success(request, '✅ Documents uploaded successfully!')
            return redirect('projects:client_card_detail', client_code=client_code)
        else:
            messages.error(request, '❌ Please correct the errors below.')
    else:
        form = ClientDocumentForm(instance=document)
    
    return render(request, 'clients/client_document_upload.html', {
        'form': form,
        'client': client,
        'document': document,
        'page_title': 'Upload Client Documents'
    })


@login_required
def client_document_download(request, client_code, field_name):
    """Download a specific client document"""
    ClientCard, _, _, ClientDocument = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    
    try:
        document = ClientDocument.objects.get(client_code=client)
        file_field = getattr(document, field_name, None)
        
        if not file_field:
            messages.error(request, '❌ Document not found.')
            return redirect('projects:client_card_detail', client_code=client_code)
        
        # Get the file
        file_path = file_field.path
        if not os.path.exists(file_path):
            messages.error(request, '❌ File not found on server.')
            return redirect('projects:client_card_detail', client_code=client_code)
        
        # Return file as download
        response = FileResponse(open(file_path, 'rb'))
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        return response
        
    except ClientDocument.DoesNotExist:
        messages.error(request, '❌ No documents found for this client.')
        return redirect('projects:client_card_detail', client_code=client_code)


@login_required
def client_document_download_all(request, client_code):
    """Download all client documents as a ZIP file"""
    ClientCard, _, _, ClientDocument = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    
    try:
        document = ClientDocument.objects.get(client_code=client)
        docs = document.get_all_documents()
        
        if not docs:
            messages.warning(request, '⚠️ No documents available to download.')
            return redirect('projects:client_card_detail', client_code=client_code)
        
        # Create ZIP file in memory
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for doc in docs:
                file_path = doc['file'].path
                if os.path.exists(file_path):
                    # Add file to ZIP with original filename
                    zip_file.write(file_path, os.path.basename(file_path))
        
        # Prepare response
        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{client_code}_documents.zip"'
        return response
        
    except ClientDocument.DoesNotExist:
        messages.error(request, '❌ No documents found for this client.')
        return redirect('projects:client_card_detail', client_code=client_code)


@login_required
@require_role('admin')
def client_document_delete(request, client_code, field_name):
    """Delete a specific client document"""
    ClientCard, _, _, ClientDocument = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    
    try:
        document = ClientDocument.objects.get(client_code=client)
        file_field = getattr(document, field_name, None)
        
        if file_field:
            # Delete the file from storage
            file_field.delete(save=False)
            # Clear the field
            setattr(document, field_name, None)
            document.save()
            messages.success(request, '✅ Document deleted successfully!')
        else:
            messages.warning(request, '⚠️ Document not found.')
            
    except ClientDocument.DoesNotExist:
        messages.error(request, '❌ No documents found for this client.')
    
    return redirect('projects:client_card_detail', client_code=client_code)


@login_required
def client_document_preview(request, client_code, field_name):
    """Preview a client document in browser (no download)"""
    ClientCard, _, _, ClientDocument = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    
    try:
        document = ClientDocument.objects.get(client_code=client)
        file_field = getattr(document, field_name, None)
        
        if not file_field:
            messages.error(request, '❌ Document not found.')
            return redirect('projects:client_card_detail', client_code=client_code)
        
        # Get the file
        file_path = file_field.path
        if not os.path.exists(file_path):
            messages.error(request, '❌ File not found on server.')
            return redirect('projects:client_card_detail', client_code=client_code)
        
        # Determine content type
        file_extension = os.path.splitext(file_path)[1].lower()
        content_type_map = {
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
        }
        content_type = content_type_map.get(file_extension, 'application/octet-stream')
        
        # Return file for inline viewing (not download)
        response = FileResponse(open(file_path, 'rb'), content_type=content_type)
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
        return response
        
    except ClientDocument.DoesNotExist:
        messages.error(request, '❌ No documents found for this client.')
        return redirect('projects:client_card_detail', client_code=client_code)
    

@login_required
def client_link_projects(request, client_code):
    """Link or unlink projects to/from a client"""
    ClientCard, _, _, _ = _get_models()
    client = get_object_or_404(ClientCard, client_code=client_code)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'link':
            # Link multiple projects to this client
            project_ids = request.POST.getlist('project_ids')
            if project_ids:
                from .models import ProjectCode
                updated_count = ProjectCode.objects.filter(
                    project_id__in=project_ids
                ).update(
                    client_card=client,
                    client_name=client.client_legal_name  # Auto-fill client_name
                )
                messages.success(request, f'✅ Successfully linked {updated_count} project(s) to {client.client_short_name}')
            else:
                messages.warning(request, '⚠️ No projects selected')
        
        elif action == 'unlink':
            # Unlink a single project
            project_id = request.POST.get('project_id')
            if project_id:
                from .models import ProjectCode
                try:
                    project = ProjectCode.objects.get(project_id=project_id)
                    project.client_card = None
                    # Keep client_name as is (don't clear it)
                    project.save()
                    messages.success(request, f'✅ Unlinked project {project_id} from {client.client_short_name}')
                except ProjectCode.DoesNotExist:
                    messages.error(request, f'❌ Project {project_id} not found')
        
        return redirect('projects:client_card_detail', client_code=client_code)
    
    # GET request - this shouldn't happen normally
    return redirect('projects:client_card_detail', client_code=client_code)


@login_required
def admin_delete_client_card(request, client_code):
    """
    Admin-only: Permanently delete a client card.
    Should only be used for mistakenly created clients or duplicates.
    Checks dependencies before allowing deletion.
    """
    from .models import ProjectCode
    ClientCard, ClientContact, ClientGST, ClientDocument = _get_models()

    if request.user.role not in ['admin']:
        messages.error(request, "⛔ Access Denied: Admin only")
        return redirect('accounts:dashboard')

    try:
        client = ClientCard.objects.get(client_code=client_code)
    except ClientCard.DoesNotExist:
        messages.error(request, f"Client {client_code} not found")
        return redirect('projects:client_card_list')

    # GET request: Show confirmation page with dependency check
    if request.method == 'GET':
        dependencies = {}

        # 1. Contacts
        dependencies['contacts'] = ClientContact.objects.filter(client_code=client).count()

        # 2. GST Entities
        dependencies['gst_entities'] = ClientGST.objects.filter(client_code=client).count()

        # 3. Documents
        dependencies['documents'] = 1 if hasattr(client, 'documents') and client.documents else 0

        # 4. Projects using this client card
        dependencies['projects'] = ProjectCode.objects.filter(client_card=client).count()

        # Calculate totals
        total_records = sum(dependencies.values())
        has_dependencies = total_records > 0

        context = {
            'client': client,
            'dependencies': dependencies,
            'total_records': total_records,
            'has_dependencies': has_dependencies,
        }
        return render(request, 'projects/admin_delete_client_confirm.html', context)

    # POST request: Perform deletion after validation
    if request.method == 'POST':
        confirm_text = request.POST.get('confirm_delete', '').strip()

        if confirm_text != 'DELETE':
            messages.error(request, "❌ Confirmation text must be 'DELETE' (case sensitive)")
            return redirect('projects:admin_delete_client', client_code=client_code)

        # Double-check dependencies
        project_count = ProjectCode.objects.filter(client_card=client).count()

        if project_count > 0:
            messages.error(request, f"❌ Cannot delete: Client is linked to {project_count} projects. Unlink those projects first.")
            return redirect('projects:admin_delete_client', client_code=client_code)

        # Store client info for success message
        deleted_info = f"{client.client_code} - {client.client_short_name}"

        # Delete related data first
        ClientContact.objects.filter(client_code=client).delete()
        ClientGST.objects.filter(client_code=client).delete()
        if hasattr(client, 'documents') and client.documents:
            client.documents.delete()

        # Delete the client
        client.delete()

        messages.success(request, f"✅ Client card '{deleted_info}' has been permanently deleted")
        return redirect('projects:client_card_list')