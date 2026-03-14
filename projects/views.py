from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse
from .models import ProjectCode, GstState
from .forms import ProjectCreateForm
from .utils import (
    get_next_sequence_number, 
    get_next_state_code, 
    generate_project_code_string,
    get_next_temp_sequence,
)
from accounts.models import User
from accounts.permissions import get_accessible_projects
from django.db.models import Count
from .forms import LocationForm
from .forms import ProjectCodeForm
from operations.models_projectcard import TransportRate
from supply.models import Location, VendorCard, VendorWarehouse


def get_return_url(request):
    """
    Get the URL to return to after an action.
    Priority: 1) POST data, 2) GET param, 3) HTTP_REFERER, 4) None
    """
    from django.utils.http import url_has_allowed_host_and_scheme
    for src in [request.POST.get('return_url'), request.GET.get('return_url'), request.META.get('HTTP_REFERER')]:
        if src and url_has_allowed_host_and_scheme(src, allowed_hosts={request.get_host()}):
            return src
    return None

@login_required
def location_create_view(request):
    """
    Create a new Location.
    Restricted to: Admin, Super User, Backoffice.
    """
    # 1. PERMISSION CHECK
    allowed_roles = ['admin', 'super_user', 'backoffice']
    if request.user.role not in allowed_roles:
        messages.error(request, '⛔ Access Denied: Only Admin or Backoffice can create locations.')
        return redirect('projects:project_create')

    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid():
            # Save the new location
            form.save()
            messages.success(request, f"✅ Location '{form.cleaned_data['city']}' added successfully!")
            return redirect('projects:project_create')
        else:
            # Form is invalid (duplicate found), messages will be shown in template
            messages.error(request, "Please correct the errors below.")
    else:
        form = LocationForm()

    context = {
        'form': form,
        'title': 'Add New Location',
        'back_url': 'projects:project_create'
    }
    return render(request, 'projects/master_create.html', context)


@login_required
def project_list_view(request, filter_type='all'):
    user = request.user
    role = user.role
    
    # 1. Base Access
    projects = get_accessible_projects(user)
    
    # 2. Tabs Logic
    if filter_type == 'active':
        projects = projects.filter(Q(project_status='Active') | Q(project_status='Notice Period'))
        filter_title = 'Active Projects'
    elif filter_type == 'pending':
        projects = projects.filter(project_status='Operation Not Started')
        filter_title = 'Operation Not Started'
    elif filter_type == 'unassigned':
        if role in ['admin', 'super_user', 'operation_controller', 'operation_manager']:
            projects = projects.filter(project_status='Active', operation_coordinator__isnull=True)
            filter_title = 'Unassigned Active Projects'
        else:
            filter_title = 'All Projects'
    elif filter_type == 'missing_agreement':
        from projects.models_document import ProjectDocument
        projects_with_agreement = ProjectDocument.objects.exclude(
            project_agreement=''
        ).exclude(
            project_agreement__isnull=True
        ).values_list('project_id', flat=True)
        projects = projects.filter(
            series_type='WAAS'
        ).exclude(
            project_status='Inactive'
        ).exclude(
            project_id__in=projects_with_agreement
        )
        filter_title = 'Missing Main Agreement (WAAS)'
    elif filter_type == 'missing_addendum_vendor':
        from projects.models_document import ProjectDocument
        projects_with_addendum = ProjectDocument.objects.exclude(
            project_addendum_vendor=''
        ).exclude(
            project_addendum_vendor__isnull=True
        ).values_list('project_id', flat=True)
        projects = projects.filter(
            series_type='WAAS'
        ).exclude(
            project_status='Inactive'
        ).exclude(
            project_id__in=projects_with_addendum
        )
        filter_title = 'Missing Vendor Addendum (WAAS)'
    else:
        projects = projects.filter(
            Q(project_status='Active') | Q(project_status='Operation Not Started') | Q(project_status='Notice Period')
        )
        filter_title = 'All Projects'

    # 3. Get filter parameters (with empty string defaults)
    f_status = request.GET.get('f_status', '')
    f_coordinator = request.GET.get('f_coordinator', '')
    f_mode = request.GET.get('f_mode', '')
    f_mis = request.GET.get('f_mis', '')
    f_sales = request.GET.get('f_sales', '')
    search_query = request.GET.get('search', '')

    # 4. Search (apply first)
    if search_query:
        projects = projects.filter(
            Q(project_code__icontains=search_query) |
            Q(project_id__icontains=search_query) |
            Q(client_name__icontains=search_query) |
            Q(vendor_name__icontains=search_query) |
            Q(location__icontains=search_query)
        )

    # 5. Apply filters (only if not empty)
    if f_status:
        projects = projects.filter(project_status=f_status)
    
    if f_coordinator:
        projects = projects.filter(
            Q(operation_coordinator__icontains=f_coordinator) | 
            Q(backup_coordinator__icontains=f_coordinator)
        )
    
    if f_mode:
        # Map filter values to database values
        mode_mapping = {
            'auto_mode': 'Auto Mode',
            'data_sharing': 'Data Sharing',
            'active_engagement': 'Active Engagement',
        }
        db_value = mode_mapping.get(f_mode, f_mode)
        projects = projects.filter(operation_mode=db_value)
    
    if f_mis:
        projects = projects.filter(mis_status=f_mis)
    
    if f_sales:
        projects = projects.filter(sales_manager__icontains=f_sales)
    
    # 6. Filter Options (Populate dropdowns dynamically)
    base_qs = get_accessible_projects(user)
    
    filter_options = {
        'statuses': ['Active', 'Operation Not Started', 'Notice Period', 'Inactive'],
        'modes': ['auto_mode', 'data_sharing', 'active_engagement'],
        'coordinators': base_qs.exclude(
            operation_coordinator__isnull=True
        ).exclude(
            operation_coordinator=''
        ).values_list('operation_coordinator', flat=True).distinct().order_by('operation_coordinator'),
        'sales_managers': base_qs.exclude(
            sales_manager__isnull=True
        ).exclude(
            sales_manager=''
        ).values_list('sales_manager', flat=True).distinct().order_by('sales_manager'),
    }

    # Get sort parameter
    sort_by = request.GET.get('sort', '')

    # Apply sorting
    if sort_by == 'created':
        projects = projects.order_by('created_at')
    elif sort_by == 'created_desc':
        projects = projects.order_by('-created_at')
    elif sort_by == 'updated':
        projects = projects.order_by('updated_at')
    elif sort_by == 'updated_desc':
        projects = projects.order_by('-updated_at')
    elif sort_by == 'project_code':
        projects = projects.order_by('code')
    elif sort_by == 'project_code_desc':
        projects = projects.order_by('-code')
    else:
        # Default: Order by client name
        projects = projects.order_by('client_name')

    # Annotate with operation_start_date from active ProjectCard
    from django.db.models import OuterRef, Subquery
    from operations.models_projectcard import ProjectCard as PC
    active_card_qs = PC.objects.filter(
        project=OuterRef('pk'), is_active=True
    ).order_by('-version').values('operation_start_date')[:1]
    projects = projects.annotate(operation_start_date=Subquery(active_card_qs))

    # Pagination - add before rendering
    from django.core.paginator import Paginator
    total_count = projects.count()
    paginator = Paginator(projects, 50)  # 50 projects per page
    page = request.GET.get('page', 1)
    projects_page = paginator.get_page(page)

    context = {
        'projects': projects_page,
        'page_obj': projects_page,
        'filter_type': filter_type,
        'filter_title': filter_title,
        'search_query': search_query,
        'total_count': total_count,
        'role': role,
        'filter_options': filter_options,
        'current_filters': {
            'f_status': f_status,
            'f_coordinator': f_coordinator,
            'f_mode': f_mode,
            'f_mis': f_mis,
            'f_sales': f_sales,
        }
    }
    
    return render(request, 'projects/project_list.html', context)


@login_required
def project_edit_view(request, project_id):
    """
    Edit existing project - allows updating client, vendor, warehouse, and other fields
    """
    # Check permissions
    if request.user.role not in ['backoffice', 'admin', 'director', 'superuser']:
        messages.error(request, "Access denied. You don't have permission to edit projects.")
        return_url = get_return_url(request)
        if return_url:
            return redirect(return_url)
        return redirect('accounts:dashboard')

    # Get the project
    project = get_object_or_404(ProjectCode, project_id=project_id)

    # Get the active ProjectCard (if exists)
    from operations.models_projectcard import ProjectCard
    active_project_card = project.project_cards.filter(is_active=True).first()

    if request.method == 'POST':
        form = ProjectCodeForm(request.POST, instance=project)
        if form.is_valid():
            try:
                updated_project = form.save()

                # Save ProjectCard fields (billing_start_date and operation_start_date)
                billing_start_date = form.cleaned_data.get('billing_start_date')
                operation_start_date = form.cleaned_data.get('operation_start_date')

                if active_project_card:
                    # Update existing ProjectCard
                    active_project_card.billing_start_date = billing_start_date
                    active_project_card.operation_start_date = operation_start_date
                    active_project_card.save()
                    print(f"DEBUG: Updated ProjectCard - billing: {billing_start_date}, operation: {operation_start_date}")
                elif billing_start_date or operation_start_date:
                    # Create new ProjectCard if dates are provided but no card exists
                    from datetime import date
                    new_card = ProjectCard.objects.create(
                        project=updated_project,
                        version=1,
                        is_active=True,
                        valid_from=billing_start_date or operation_start_date or date.today(),
                        billing_start_date=billing_start_date,
                        operation_start_date=operation_start_date,
                    )
                    print(f"DEBUG: Created new ProjectCard - billing: {billing_start_date}, operation: {operation_start_date}")
                else:
                    print("DEBUG: No ProjectCard and no dates provided")

                messages.success(request, f"✅ Project {updated_project.project_code} updated successfully!")

                 # DEBUG: Check return_url
                return_url = get_return_url(request)
                print(f"DEBUG return_url from POST: {request.POST.get('return_url')}")
                print(f"DEBUG return_url from GET: {request.GET.get('return_url')}")
                print(f"DEBUG return_url from REFERER: {request.META.get('HTTP_REFERER')}")
                print(f"DEBUG final return_url: {return_url}")

                # RETURN TO WHERE USER CAME FROM
                return_url = get_return_url(request)
                if return_url:
                    return redirect(return_url)
                return redirect('projects:project_detail', project_id=updated_project.project_id)
            except Exception as e:
                messages.error(request, f"❌ Error updating project: {str(e)}")
        else:
            messages.error(request, "❌ Please fix the errors below.")
    else:
        form = ProjectCodeForm(instance=project)
        # Pre-populate ProjectCard fields
        if active_project_card:
            form.initial['billing_start_date'] = active_project_card.billing_start_date
            form.initial['operation_start_date'] = active_project_card.operation_start_date

    context = {
        'form': form,
        'project': project,
        'page_title': f'Edit Project - {project.project_code}',
        'return_url': get_return_url(request),  # Pass to template
    }

    return render(request, 'projects/project_edit.html', context)


# --- NEW FILTER & UPDATE LOGIC ---

@login_required
def get_sales_managers_api(request):
    """
    API to fetch sales managers for the dropdown.
    Matches logic in ProjectCreateForm.
    """
    # Includes: sales_manager, crm_executive, director, admin
    sales_users = User.objects.filter(
        role__in=['sales_manager', 'crm_executive', 'director', 'admin'],
        is_active=True
    ).order_by('first_name', 'last_name')
    
    managers_list = []
    for u in sales_users:
        name = f"{u.first_name} {u.last_name}".strip() if u.first_name else u.username
        role_label = f" ({u.get_role_display()})"
        
        managers_list.append({
            'id': u.id,
            'name': name + role_label,
            'clean_name': name # For saving to DB without role label if needed
        })
        
    return JsonResponse({'sales_managers': managers_list})

@login_required
def update_project_sales_manager(request, project_id):
    """
    Update Sales Manager via AJAX.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    
    # Permission check
    if request.user.role not in ['admin', 'super_user', 'director']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
        
    try:
        project = ProjectCode.objects.get(project_id=project_id)
        new_manager_id = request.POST.get('sales_manager_id')
        
        if not new_manager_id:
            project.sales_manager = ''
            project.save()
            return JsonResponse({'success': True, 'message': 'Sales Manager unassigned', 'new_value': '-'})
            
        # Get User object
        user_obj = User.objects.get(id=new_manager_id)
        # Construct name string as per your model storage (char field)
        new_name = f"{user_obj.first_name} {user_obj.last_name}".strip() if user_obj.first_name else user_obj.username
        
        project.sales_manager = new_name
        project.updated_at = timezone.now()
        project.save()
        
        return JsonResponse({
            'success': True, 
            'message': f'Sales Manager updated to {new_name}',
            'new_value': new_name
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})



@login_required
def project_list_not_started(request):
    """Show only projects with Operation Not Started status"""
    return project_list_view(request, filter_type='pending')


@login_required
def project_create_view(request):
    """
    Create new project with auto-generated codes.
    Only accessible by admin and backoffice.
    """
    user = request.user
    
    # Check permission
    if user.role not in ['admin', 'super_user', 'backoffice']:
        messages.error(request, 'You do not have permission to create projects.')
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        form = ProjectCreateForm(request.POST)
        
        if form.is_valid():
            try:
                # Extract form data
                series_type = form.cleaned_data['series_type']
                client_name = form.cleaned_data['client_name']
                vendor_name = form.cleaned_data['vendor_name']
                location_city = form.cleaned_data['location']
                sales_manager_id = form.cleaned_data.get('sales_manager')
                
                # Get location object to derive state
                location_obj = Location.objects.filter(city=location_city, is_active=True).first()
                if not location_obj:
                    raise ValueError('Location not found')
                
                state_name = location_obj.state

                # DEBUG: Print what we're looking for
                #print(f"DEBUG: Looking for state: '{state_name}'")

                # Get state_code from GstState table (only states with GST)
                state_code = None
                #print(f"DEBUG: Looking for state: '{state_name}'")

                try:
                    #print(f"DEBUG: Querying GstState with state_name='{state_name}', is_active=True")
                    gst_state = GstState.objects.get(state_name=state_name, is_active=True)
                    state_code = gst_state.state_code
                    #print(f"DEBUG: SUCCESS! Found GST state: {state_code}")
                except GstState.DoesNotExist:
                    #print(f"DEBUG: GstState.DoesNotExist exception caught")
                    # Check if form provided fallback state
                    if 'fallback_state_code' in form.cleaned_data:
                        state_code = form.cleaned_data['fallback_state_code']
                        #print(f"DEBUG: Using fallback from form: {state_code}")
                    else:
                        state_code = 'MH'
                        #print(f"DEBUG: Using default fallback: MH")
                    messages.warning(request, f'⚠️ {state_name} does not have GST certificate. Using {state_code} series.')
                except Exception as e:
                    #print(f"DEBUG: Unexpected exception: {type(e).__name__}: {e}")
                    state_code = 'MH'

                #print(f"DEBUG: Final state_code before code generation: {state_code}")

                # Check if form provided fallback state (for WAAS without GST)
                if 'fallback_state_code' in form.cleaned_data:
                    state_code = form.cleaned_data['fallback_state_code']

                # Get current year
                current_year = timezone.now().year

                # Generate project_id (e.g., WAAS-25-442)
                #sequence_num = get_next_sequence_number(series_type, current_year)
                #year_suffix = str(current_year)[-2:]
                #project_id = f"{series_type}-{year_suffix}-{sequence_num:03d}"
                temp_seq = get_next_temp_sequence()
                project_id = f"TEMP-{temp_seq:03d}"

                # Generate code (e.g., MH166, KA001, SA001, GW001)
                code = get_next_state_code(state_code, series_type)
                                
                # Generate project_code string
                project_code_str = generate_project_code_string(
                    code,
                    client_name,
                    vendor_name,
                    location_city
                )
                
                # Get sales manager name
                sales_manager_name = ''
                if sales_manager_id:
                    try:
                        sales_user = User.objects.get(id=int(sales_manager_id))
                        if sales_user.first_name:
                            sales_manager_name = f"{sales_user.first_name} {sales_user.last_name}".strip()
                        else:
                            sales_manager_name = sales_user.username
                    except (User.DoesNotExist, ValueError):
                        pass
                
                # Create project
                project = ProjectCode.objects.create(
                    project_id=project_id,
                    series_type=series_type,
                    code=code,
                    project_code=project_code_str,
                    client_name=client_name,
                    vendor_name=vendor_name,
                    warehouse_code=None,
                    location=location_city,
                    state=state_name,
                    project_status='Operation Not Started',
                    sales_manager=sales_manager_name,
                    created_at=timezone.now(),
                    updated_at=timezone.now()
                )
                
                messages.success(request, f'✅ Project {code} created successfully!')
                messages.info(request, '📋 Please create rate card for this project now.')

                # Redirect with project pre-selected
                return redirect(f'/projects/project-cards/create/?project={project.project_id}')
                
            except Exception as e:
                messages.error(request, f'Error creating project: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProjectCreateForm()
    
    context = {
        'form': form,
        'role': user.role,
    }
    
    return render(request, 'projects/project_create.html', context)


@login_required
def project_mapping_view(request):
    """
    Project Mapping - Display project assignments.
    Allows filtering and reassignment of coordinators.
    Admin, Super User, Operation Controller, and Operation Manager can access.
    """
    user = request.user
    
    # Check permission
    if user.role not in ['admin', 'super_user', 'operation_controller', 'operation_manager']:
        messages.error(request, 'You do not have permission to access code mapping.')
        return redirect('accounts:dashboard')
    
    # Get filter parameters
    sales_manager_filter = request.GET.get('sales_manager', '')
    operation_coordinator_filter = request.GET.get('operation_coordinator', '')
    backup_coordinator_filter = request.GET.get('backup_coordinator', '')
    series_filter = request.GET.get('series', 'WAAS') 
    status_filter = request.GET.get('status', '')  # No default
    search_query = request.GET.get('search', '')
    
    # Base queryset
    projects = ProjectCode.objects.all()

    # Apply status filter
    if status_filter:
        projects = projects.filter(project_status=status_filter)
    else:
        # Default: Show Active, Notice Period, Operation Not Started
        projects = projects.filter(
            Q(project_status='Active') | 
            Q(project_status='Notice Period') | 
            Q(project_status='Operation Not Started')
        )
    
    # Apply series filter
    if series_filter:
        projects = projects.filter(series_type=series_filter)
    
    # Apply sales manager filter
    if sales_manager_filter:
        if sales_manager_filter == 'unassigned':
            projects = projects.exclude(series_type='GW').filter(
                Q(sales_manager__isnull=True) | Q(sales_manager='')
            )
        else:
            projects = projects.filter(sales_manager__icontains=sales_manager_filter)
    
    # Apply operation coordinator filter
    if operation_coordinator_filter:
        if operation_coordinator_filter == 'unassigned':
            projects = projects.exclude(series_type='GW').filter(
                Q(operation_coordinator__isnull=True) | Q(operation_coordinator='')
            )
        else:
            projects = projects.filter(operation_coordinator__icontains=operation_coordinator_filter)
    
    # Apply backup coordinator filter
    if backup_coordinator_filter:
        if backup_coordinator_filter == 'unassigned':
            projects = projects.exclude(series_type='GW').filter(
                Q(backup_coordinator__isnull=True) | Q(backup_coordinator='')
            )
        else:
            projects = projects.filter(backup_coordinator__icontains=backup_coordinator_filter)
    
    # Apply search
    if search_query:
        projects = projects.filter(
            Q(code__icontains=search_query) |
            Q(client_name__icontains=search_query) |
            Q(location__icontains=search_query)
        )
    
    # Sort by client name alphabetically
    projects = projects.order_by('client_name', '-created_at')
    
    # Get sales managers from users table
    sales_users = User.objects.filter(
        role='sales_manager',
        is_active=True
    ).order_by('first_name', 'last_name')
    
    sales_managers_list = []
    for user_obj in sales_users:
        if user_obj.last_name:
            full_name = f"{user_obj.first_name} {user_obj.last_name}"
        else:
            full_name = user_obj.first_name
        sales_managers_list.append(full_name)
    

    # Get coordinators, warehouse managers, and operation managers from users table
    operations_users = User.objects.filter(
        role__in=['operation_coordinator', 'warehouse_manager', 'operation_manager'],
        is_active=True
    ).order_by('role', 'first_name', 'last_name')

    operations_coordinators_list = []
    for user_obj in operations_users:
        full_name = user_obj.get_full_name()
        operations_coordinators_list.append(full_name)
    
    # Stats - exclude GW series from unassigned counts
    total_projects = projects.count()
    unassigned_operations = projects.exclude(series_type='GW').filter(
        Q(operation_coordinator__isnull=True) | Q(operation_coordinator='')
    ).count()
    unassigned_sales = projects.exclude(series_type='GW').filter(
        Q(sales_manager__isnull=True) | Q(sales_manager='')
    ).count()
    unassigned_backup = projects.exclude(series_type='GW').filter(
        Q(backup_coordinator__isnull=True) | Q(backup_coordinator='')
    ).count()
    
    # Add pagination
    from django.core.paginator import Paginator
    paginator = Paginator(projects, 100)  # 100 projects per page
    page = request.GET.get('page', 1)
    projects_page = paginator.get_page(page)

    context = {
        'projects': projects_page,
        'page_obj': projects_page,
        'sales_managers': sales_managers_list,
        'operation_coordinators': operations_coordinators_list,
        'backup_coordinators': operations_coordinators_list,  # Same as operations
        'sales_manager_filter': sales_manager_filter,
        'operation_coordinator_filter': operation_coordinator_filter,
        'backup_coordinator_filter': backup_coordinator_filter,
        'series_filter': series_filter,
        'status_filter': status_filter,
        'search_query': search_query,
        'total_projects': total_projects,
        'unassigned_operations': unassigned_operations,
        'unassigned_sales': unassigned_sales,
        'unassigned_backup': unassigned_backup,
        'role': user.role,
    }

    return render(request, 'projects/project_mapping.html', context)


@login_required
def update_project_managers(request):
    """
    Update sales, operation coordinator, or backup coordinator for a project.
    Admin/Super User: Can update all
    Ops Controller/Manager: Can only update operations and backup
    Uses manager names directly from database.
    """
    if request.method != 'POST':
        return_url = get_return_url(request)
        if return_url:
            return redirect(return_url)
        return redirect('projects:project_mapping')
    
    if request.user.role not in ['admin', 'super_user', 'operation_controller', 'operation_manager']:
        messages.error(request, 'You do not have permission to update managers.')
        return_url = get_return_url(request)
        if return_url:
            return redirect(return_url)
        return redirect('accounts:dashboard')
    
    project_id = request.POST.get('project_id')
    manager_type = request.POST.get('manager_type')
    manager_id = request.POST.get('manager_id')  # This is actually the manager name
    
    try:
        project = ProjectCode.objects.get(project_id=project_id)
        
        # Skip GW series
        if project.series_type == 'GW':
            messages.warning(request, 'GW series projects do not require manager assignments.')
            return_url = get_return_url(request)
            if return_url:
                return redirect(return_url)
            return redirect('projects:project_mapping')
        
        if manager_type == 'sales':
            # Only admin and super_user can update sales manager
            if request.user.role not in ['admin', 'super_user']:
                messages.error(request, 'Only admin can update sales managers.')
                return_url = get_return_url(request)
                if return_url:
                    return redirect(return_url)
                return redirect('projects:project_mapping')
            
            if not manager_id:
                messages.error(request, 'Please select a sales manager.')
                return_url = get_return_url(request)
                if return_url:
                    return redirect(return_url)
                return redirect('projects:project_mapping')
            
            # Use the name directly
            project.sales_manager = manager_id
            project.save()
            messages.success(request, f'✅ Sales Manager updated to {manager_id} for {project.code}')
            
        elif manager_type == 'operations':
            if not manager_id:
                messages.error(request, 'Please select an operation coordinator.')
                return_url = get_return_url(request)
                if return_url:
                    return redirect(return_url)
                return redirect('projects:project_mapping')
            
            # Use the name directly
            project.operation_coordinator = manager_id
            project.updated_at = timezone.now()
            project.save()
            
            messages.success(request, f'✅ Operation Coordinator updated to {manager_id} for {project.code}')
            
        elif manager_type == 'backup':
            if not manager_id:
                # Allow clearing backup coordinator
                project.backup_coordinator = None
                project.save()
                messages.success(request, f'✅ Backup Coordinator cleared for {project.code}')
            else:
                # Use the name directly
                project.backup_coordinator = manager_id
                project.save()
                messages.success(request, f'✅ Backup Coordinator updated to {manager_id} for {project.code}')
        
    except ProjectCode.DoesNotExist:
        messages.error(request, 'Project not found.')
    except Exception as e:
        messages.error(request, f'Error: {str(e)}')
    
    # RETURN TO WHERE USER CAME FROM
    return_url = get_return_url(request)
    if return_url:
        return redirect(return_url)
    return redirect('projects:project_mapping')


@login_required
def bulk_update_managers(request):
    """
    Bulk update managers for multiple projects.
    Admin and Super User only.
    Uses actual manager names from database, not user IDs.
    """
    if request.method != 'POST':
        return_url = get_return_url(request)
        if return_url:
            return redirect(return_url)
        return redirect('projects:project_mapping')
    
    if request.user.role not in ['admin', 'super_user']:
        messages.error(request, 'Only admin can perform bulk updates.')
        return_url = get_return_url(request)
        if return_url:
            return redirect(return_url)
        return redirect('accounts:dashboard')
    
    try:
        import json
        updates = json.loads(request.POST.get('updates', '[]'))
        
        success_count = 0
        error_count = 0
        errors = []
        
        for update in updates:
            try:
                project_id = update.get('project_id')
                sales_manager = update.get('sales_manager')
                operations_coordinator = update.get('operations_coordinator')
                backup_coordinator = update.get('backup_coordinator')
                
                project = ProjectCode.objects.get(project_id=project_id)
                
                # Skip GW series
                if project.series_type == 'GW':
                    continue
                
                # Update sales manager (use the name directly from database)
                if sales_manager:
                    project.sales_manager = sales_manager
                
                # Update operations coordinator
                if operations_coordinator:
                    project.operation_coordinator = operations_coordinator
                
                # Update backup coordinator
                if backup_coordinator:
                    project.backup_coordinator = backup_coordinator
                
                project.updated_at = timezone.now()
                project.save()
                success_count += 1
                
            except ProjectCode.DoesNotExist:
                error_count += 1
                errors.append(f"Project ID {project_id} not found")
            except Exception as e:
                error_count += 1
                errors.append(f"Error updating project {project_id}: {str(e)}")
        
        if error_count > 0:
            messages.warning(request, f'⚠️ Bulk update completed with issues: {success_count} updated, {error_count} errors.')
            for error in errors[:5]:  # Show first 5 errors
                messages.error(request, error)
        else:
            messages.success(request, f'✅ Bulk update completed successfully! {success_count} projects updated.')
        
    except Exception as e:
        messages.error(request, f'Error in bulk update: {str(e)}')
    
    # RETURN TO WHERE USER CAME FROM
    return_url = get_return_url(request)
    if return_url:
        return redirect(return_url)
    return redirect('projects:project_mapping')


@login_required
def my_projects_view(request):
    """Show only projects where user is MAIN coordinator (not backup)"""
    user = request.user
    role = user.role
    user_name = user.get_full_name()
    
    # Only show projects where user is MAIN coordinator
    projects = ProjectCode.objects.filter(
        operation_coordinator=user_name,  # ONLY main coordinator, no backup
        project_status__in=['Active', 'Notice Period', 'Operation Not Started']
    )
    
    # Get filter parameters
    search_query = request.GET.get('search', '')
    f_status = request.GET.get('f_status', '')
    f_mode = request.GET.get('f_mode', '')
    f_mis = request.GET.get('f_mis', '')
    f_sales = request.GET.get('f_sales', '')  # ADD THIS
    
    # Apply search
    if search_query:
        projects = projects.filter(
            Q(project_code__icontains=search_query) |
            Q(project_id__icontains=search_query) |
            Q(client_name__icontains=search_query) |
            Q(vendor_name__icontains=search_query) |
            Q(location__icontains=search_query)
        )
    
    # Apply filters
    if f_status:
        projects = projects.filter(project_status=f_status)
    
    if f_mode:
        mode_mapping = {
            'auto_mode': 'Auto Mode',
            'data_sharing': 'Data Sharing',
            'active_engagement': 'Active Engagement',
        }
        db_value = mode_mapping.get(f_mode, f_mode)
        projects = projects.filter(operation_mode=db_value)
    
    if f_mis:
        projects = projects.filter(mis_status=f_mis)
    
    if f_sales:  # ADD THIS BLOCK
        projects = projects.filter(sales_manager__icontains=f_sales)
    
    # Order by client name
    projects = projects.order_by('client_name')
    
    # Filter options for dropdowns (from MY projects only)
    filter_options = {
        'statuses': projects.values_list('project_status', flat=True).distinct().order_by('project_status'),
        'modes': projects.exclude(operation_mode__isnull=True).exclude(operation_mode='').values_list('operation_mode', flat=True).distinct(),
        'mis_statuses': projects.exclude(mis_status__isnull=True).exclude(mis_status='').values_list('mis_status', flat=True).distinct().order_by('mis_status'),
        'sales_managers': projects.exclude(sales_manager__isnull=True).exclude(sales_manager='').values_list('sales_manager', flat=True).distinct().order_by('sales_manager'),  # ADD THIS
    }
    
    context = {
        'projects': projects,
        'filter_type': 'mine',
        'filter_title': 'My Projects (Main Coordinator)',
        'search_query': search_query,
        'total_count': projects.count(),
        'role': role,
        'filter_options': filter_options,
        'current_filters': {
            'f_status': f_status,
            'f_mode': f_mode,
            'f_mis': f_mis,
            'f_sales': f_sales,  # ADD THIS
        }
    }
    
    return render(request, 'projects/my_projects.html', context)


@login_required
def project_detail_view(request, project_id):
    """
    View individual project details WITH RATE CARD DATA.
    All roles can view projects they have access to.
    """
    user = request.user
    project = get_object_or_404(ProjectCode, project_id=project_id)
    
    # Check permissions
    if user.role == 'operation_coordinator':
        if project.operation_coordinator != user.get_full_name() and project.backup_coordinator != user.get_full_name():
            messages.error(request, "You don't have permission to view this project.")
            return redirect('accounts:dashboard')
    elif user.role == 'warehouse_manager':
        if project.operation_coordinator != user.get_full_name():
            messages.error(request, "You don't have permission to view this project.")
            return redirect('accounts:dashboard')
    
    # Get related rate card if exists
    from operations.models_projectcard import ProjectCard
    project_card = ProjectCard.objects.filter(
        project=project,
        project__project_status__in=['Active', 'Operation Not Started', 'Notice Period']
    ).select_related('client_card', 'vendor_warehouse').first()
    
    # Get all active coordinators for dropdown
    coordinators = User.objects.filter(
        role='operation_coordinator',
        is_active=True
    ).order_by('first_name', 'last_name')
    
    # If project card exists, get all rates and calculate margin
    storage_rates = []
    handling_rates = []
    vas_services = []
    infrastructure_costs = []
    margin_percent = None
    
    if project_card:
        storage_rates = project_card.storage_rates.all()
        handling_rates = project_card.handling_rates.all()
        vas_services = project_card.vas_services.all()
        infrastructure_costs = project_card.infrastructure_costs.all()
        
        # Calculate margin
        from projects.views_projectcard import calculate_project_margin
        margin_percent = calculate_project_margin(storage_rates, handling_rates)
    
    context = {
        'project': project,
        'project_card': project_card,
        'storage_rates': storage_rates,
        'handling_rates': handling_rates,
        'vas_services': vas_services,
        'infrastructure_costs': infrastructure_costs,
        'margin_percent': margin_percent,
        'role': user.role,
        'coordinators': coordinators,
    }
    
    return render(request, 'projects/project_detail.html', context)

@login_required
def update_operation_mode(request, project_id):
    """
    Update operation mode for a project
    Only operation_controller, operation_manager, and admin can update
    """
    if request.user.role not in ['operation_controller', 'operation_manager', 'admin', 'super_user']:
        messages.error(request, 'You do not have permission to update operation mode.')
        return_url = get_return_url(request)
        if return_url:
            return redirect(return_url)
        return redirect('accounts:dashboard')
    
    project = get_object_or_404(ProjectCode, project_id=project_id)
    
    if request.method == 'POST':
        operation_mode = request.POST.get('operation_mode')
        remarks = request.POST.get('remarks', '')
        
        if not operation_mode:
            messages.error(request, 'Please select an operation mode.')
            return_url = get_return_url(request)
            if return_url:
                return redirect(return_url)
            return redirect('projects:project_detail', project_id=project_id)
        
        # Validate operation mode
        valid_modes = ['auto_mode', 'data_sharing', 'active_engagement']
        if operation_mode not in valid_modes:
            messages.error(request, 'Invalid operation mode selected.')
            return_url = get_return_url(request)
            if return_url:
                return redirect(return_url)
            return redirect('projects:project_detail', project_id=project_id)
        
        # Update project
        project.operation_mode = operation_mode
        project.updated_at = timezone.now()
        project.save()
        
        mode_display = dict(ProjectCode._meta.get_field('operation_mode').choices).get(operation_mode, operation_mode)
        
        messages.success(
            request,
            f'✅ Operation mode updated to "{mode_display}" for {project.project_code}'
        )
        
        if remarks:
            messages.info(request, f'📝 Remarks: {remarks}')
        
        # RETURN TO WHERE USER CAME FROM
        return_url = get_return_url(request)
        if return_url:
            return redirect(return_url)
        return redirect('projects:project_detail', project_id=project_id)
    
    # GET request - redirect back
    return_url = get_return_url(request)
    if return_url:
        return redirect(return_url)
    return redirect('projects:project_detail', project_id=project_id)


@login_required
def update_mis_status(request, project_id):
    """
    Update MIS Status for a project via AJAX
    Only operation_controller, operation_manager, admin, and super_user can update
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    # Check permissions
    if request.user.role not in ['admin', 'super_user', 'operation_controller', 'operation_manager', 'operation_coordinator']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    try:
        project = ProjectCode.objects.get(project_id=project_id)
        new_mis_status = request.POST.get('mis_status')
        
        # Validate MIS status
        valid_statuses = ['mis_daily', 'mis_weekly', 'mis_monthly', 'inciflo', 'mis_not_required']
        if new_mis_status and new_mis_status not in valid_statuses:
            return JsonResponse({'success': False, 'error': 'Invalid MIS status'})
        
        # Handle empty/unassign
        if not new_mis_status or new_mis_status == '':
            project.mis_status = None
            project.updated_at = timezone.now()
            project.save()
            
            return JsonResponse({
                'success': True,
                'message': f'MIS Status cleared for {project.project_code}',
                'new_value': '',
                'display_value': 'Not Set'
            })
        
        # Get display name
        status_display = dict(ProjectCode._meta.get_field('mis_status').choices).get(new_mis_status, new_mis_status)
        
        # Update project
        project.mis_status = new_mis_status
        project.updated_at = timezone.now()
        project.save()
        
        return JsonResponse({
            'success': True,
            'message': f'MIS Status updated to "{status_display}" for {project.project_code}',
            'new_value': new_mis_status,
            'display_value': status_display
        })
        
    except ProjectCode.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Project not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def update_project_coordinator(request, project_id):
    """
    Update operation_coordinator or backup_coordinator for a project via AJAX
    Only operation_controller, operation_manager, and admin can update
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    # Check permissions
    if request.user.role not in ['admin', 'super_user', 'operation_controller', 'operation_manager']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    try:
        project = ProjectCode.objects.get(project_id=project_id)
        field = request.POST.get('field')  # 'operation_coordinator' or 'backup_coordinator'
        coordinator_id = request.POST.get('coordinator_id')

        print(f"DEBUG: project_id={project_id}")
        print(f"DEBUG: field={field}")
        print(f"DEBUG: coordinator_id={coordinator_id}")
        
        # Validate field
        if field not in ['operation_coordinator', 'backup_coordinator']:
            return JsonResponse({'success': False, 'error': 'Invalid field'})
        
        # Handle unassign (empty value)
        if not coordinator_id or coordinator_id == '':
            setattr(project, field, '')
            project.updated_at = timezone.now()
            project.save()
            
            field_display = field.replace('_', ' ').title()
            return JsonResponse({
                'success': True,
                'message': f'{field_display} unassigned from {project.project_code}',
                'new_value': '',
                'display_value': 'Unassigned'
            })
        
        # Get coordinator (includes warehouse managers and operation managers)
        coordinator = User.objects.get(
            id=coordinator_id,
            role__in=['operation_coordinator', 'warehouse_manager', 'operation_manager'],
            is_active=True
        )
        
        full_name = coordinator.get_full_name()

        print(f"DEBUG: Found coordinator: {full_name}")
        print(f"DEBUG: Updating field '{field}' to '{full_name}'")
        
        # Update project
        setattr(project, field, full_name)
        project.updated_at = timezone.now()
        project.save()

        print(f"DEBUG: After save - {field}: {getattr(project, field)}")

        # Verify it saved
        project.refresh_from_db()
        saved_value = getattr(project, field)
        print(f"DEBUG: VERIFIED - {field} is now: '{saved_value}'")
        
        field_display = field.replace('_', ' ').title()
        
        return JsonResponse({
            'success': True,
            'message': f'{field_display} updated to {full_name} for {project.project_code}',
            'new_value': full_name,
            'display_value': full_name
        })
        
    except ProjectCode.DoesNotExist:
        print("DEBUG: ERROR - Project not found")
        return JsonResponse({'success': False, 'error': 'Project not found'})
    except User.DoesNotExist:
        print("DEBUG: ERROR - Coordinator not found")
        return JsonResponse({'success': False, 'error': 'Coordinator not found'})
    except Exception as e:
        print(f"DEBUG: ERROR - Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)})
    

@login_required
def get_coordinators_api(request):
    """
    API endpoint to get all active coordinators, warehouse managers, and operation managers for dropdown
    """
    coordinators = User.objects.filter(
        role__in=['operation_coordinator', 'warehouse_manager', 'operation_manager'],
        is_active=True
    ).order_by('role', 'first_name', 'last_name')
    
    coordinator_list = []
    for coord in coordinators:
        # Add role indicator in parentheses
        role_label = {
            'operation_coordinator': 'Coordinator',
            'warehouse_manager': 'WH Manager',
            'operation_manager': 'Ops Manager'
        }.get(coord.role, coord.role)
        
        coordinator_list.append({
            'id': coord.id,
            'name': f"{coord.get_full_name()} ({role_label})"
        })
    
    return JsonResponse({'coordinators': coordinator_list})

# ============================================================================
# GST STATE MANAGEMENT (Admin Only)
# ============================================================================

@login_required
def gst_state_list(request):
    """List all GST states - Admin only"""
    if request.user.role not in ['admin', 'backoffice']:
        messages.error(request, 'Permission denied.')
        return redirect('accounts:dashboard')
    
    states = GstState.objects.all().order_by('state_name')
    
    context = {
        'states': states,
        'total_states': states.count(),
        'active_states': states.filter(is_active=True).count(),
    }
    return render(request, 'projects/gst_state_list.html', context)


@login_required
def gst_state_create(request):
    """Add new GST state - Admin only"""
    if request.user.role not in ['admin', 'backoffice']:
        messages.error(request, 'Permission denied.')
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        state_code = request.POST.get('state_code', '').strip().upper()
        state_name = request.POST.get('state_name', '').strip()
        gst_number = request.POST.get('gst_number', '').strip()
        registration_date = request.POST.get('registration_date')
        
        # Validation
        if not state_code or len(state_code) != 2:
            messages.error(request, 'State code must be 2 characters (e.g., MH, GJ)')
            return redirect('projects:gst_state_create')
        
        if not state_name:
            messages.error(request, 'State name is required')
            return redirect('projects:gst_state_create')
        
        if not gst_number or len(gst_number) != 15:
            messages.error(request, 'GST number must be 15 characters')
            return redirect('projects:gst_state_create')
        
        # Check if state code already exists
        if GstState.objects.filter(state_code=state_code).exists():
            messages.error(request, f'State code {state_code} already exists')
            return redirect('projects:gst_state_create')
        
        try:
            GstState.objects.create(
                state_code=state_code,
                state_name=state_name,
                gst_number=gst_number,
                registration_date=registration_date if registration_date else None,
                is_active=True,
                created_at=timezone.now(),
                updated_at=timezone.now()
            )
            messages.success(request, f'✅ GST State {state_name} ({state_code}) added successfully!')
            return redirect('projects:gst_state_list')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    
    return render(request, 'projects/gst_state_create.html')


@login_required
def gst_state_edit(request, state_code):
    """Edit GST state - Admin only"""
    if request.user.role not in ['admin', 'backoffice']:
        messages.error(request, 'Permission denied.')
        return redirect('accounts:dashboard')
    
    state = get_object_or_404(GstState, state_code=state_code)
    
    if request.method == 'POST':
        state.state_name = request.POST.get('state_name', '').strip()
        state.gst_number = request.POST.get('gst_number', '').strip()
        registration_date = request.POST.get('registration_date')
        state.registration_date = registration_date if registration_date else None
        state.is_active = request.POST.get('is_active') == 'on'
        state.updated_at = timezone.now()
        
        try:
            state.save()
            messages.success(request, f'✅ {state.state_name} updated successfully!')
            return redirect('projects:gst_state_list')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    
    context = {'state': state}
    return render(request, 'projects/gst_state_edit.html', context)


@login_required
def gst_state_delete(request, state_code):
    """Delete/deactivate GST state - Admin only"""
    if request.user.role not in ['admin', 'backoffice']:
        messages.error(request, 'Permission denied.')
        return redirect('accounts:dashboard')
    
    state = get_object_or_404(GstState, state_code=state_code)
    
    if request.method == 'POST':
        # Don't actually delete, just deactivate
        state.is_active = False
        state.save()
        messages.success(request, f'✅ {state.state_name} deactivated')
        return redirect('projects:gst_state_list')
    
    context = {'state': state}
    return render(request, 'projects/gst_state_delete.html', context)


@login_required
def get_mergeable_projects_api(request, temp_project_id):
    """
    Get list of projects that a source project can merge into.

    MANDATORY: Location + State + Series must match
    Cases:
    - Case 1: Client + Location match (vendor different) - vendor transition
    - Case 2: Vendor + Location match (client different) - client transition
    - Case 3: Exact match (same client + vendor + location) - correction/rebrand

    Status must be: Active, Operation Not Started, or Notice Period
    """
    try:
        source_project = ProjectCode.objects.get(project_id=temp_project_id)

        base_filter = dict(
            series_type=source_project.series_type,
            location=source_project.location,
            state=source_project.state,
            project_status__in=['Active', 'Operation Not Started', 'Notice Period'],
        )

        # Case 1: Client + Location match (vendor changed) - vendor transition
        client_location_matches = ProjectCode.objects.filter(
            **base_filter,
            client_name=source_project.client_name,
        ).exclude(
            project_id__startswith='TEMP-'
        ).exclude(
            project_id=source_project.project_id
        ).exclude(
            vendor_name=source_project.vendor_name  # Vendor must be different
        ).order_by('-created_at')[:10]

        # Case 2: Vendor + Location match (client changed) - client transition
        vendor_location_matches = ProjectCode.objects.filter(
            **base_filter,
            vendor_name=source_project.vendor_name,
        ).exclude(
            project_id__startswith='TEMP-'
        ).exclude(
            project_id=source_project.project_id
        ).exclude(
            client_name=source_project.client_name  # Client must be different
        ).order_by('-created_at')[:10]

        # Case 3: Exact match (same client + vendor + location) - for correction / duplicate merge
        exact_matches = ProjectCode.objects.filter(
            **base_filter,
            client_name=source_project.client_name,
            vendor_name=source_project.vendor_name,
        ).exclude(
            project_id__startswith='TEMP-'
        ).exclude(
            project_id=source_project.project_id
        ).order_by('-created_at')[:10]

        projects_list = []

        # Add exact matches (correction / same project)
        for proj in exact_matches:
            projects_list.append({
                'project_id': proj.project_id,
                'code': proj.code,
                'client_name': proj.client_name,
                'vendor_name': proj.vendor_name,
                'location': proj.location,
                'project_status': proj.project_status,
                'match_type': 'exact_match',
                'match_label': 'Exact Match (Same Client + Vendor + Location)',
                'match_description': f'Same client ({proj.client_name}), Same vendor ({proj.vendor_name}), Same location ({proj.location})',
                'created_at': proj.created_at.strftime('%Y-%m-%d') if proj.created_at else 'N/A'
            })

        # Add client+location matches (vendor transition)
        for proj in client_location_matches:
            vendor_change_info = f"{proj.vendor_name} \u2192 {source_project.vendor_name}"
            projects_list.append({
                'project_id': proj.project_id,
                'code': proj.code,
                'client_name': proj.client_name,
                'vendor_name': proj.vendor_name,
                'location': proj.location,
                'project_status': proj.project_status,
                'match_type': 'vendor_transition',
                'match_label': f'\u26a0\ufe0f Vendor Transition: {vendor_change_info}',
                'match_description': f'Same client ({proj.client_name}), Same location ({proj.location}), Vendor changing',
                'created_at': proj.created_at.strftime('%Y-%m-%d') if proj.created_at else 'N/A'
            })

        # Add vendor+location matches (client transition)
        for proj in vendor_location_matches:
            client_change_info = f"{proj.client_name} \u2192 {source_project.client_name}"
            projects_list.append({
                'project_id': proj.project_id,
                'code': proj.code,
                'client_name': proj.client_name,
                'vendor_name': proj.vendor_name,
                'location': proj.location,
                'project_status': proj.project_status,
                'match_type': 'client_transition',
                'match_label': f'\u26a0\ufe0f Client Transition: {client_change_info}',
                'match_description': f'Same vendor ({proj.vendor_name}), Same location ({proj.location}), Client changing',
                'created_at': proj.created_at.strftime('%Y-%m-%d') if proj.created_at else 'N/A'
            })

        return JsonResponse({
            'success': True,
            'projects': projects_list,
            'exact_match_count': len(exact_matches),
            'vendor_transition_count': len(client_location_matches),
            'client_transition_count': len(vendor_location_matches),
            'total_count': len(projects_list)
        })

    except ProjectCode.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Project not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    

# ============================================================================
# ADMIN PROJECT CODES MANAGER (Inline Editing)
# ============================================================================

@login_required
def admin_project_codes_view(request):
    """
    Admin-only page to edit all project_codes fields inline.
    Supports search, filter, expand/collapse columns.
    """
    # Check admin permission
    if request.user.role not in ['admin', 'super_user']:
        messages.error(request, '⛔ Access Denied: Admin only')
        return redirect('accounts:dashboard')
    
    # Get all projects
    projects = ProjectCode.objects.all()
    
    # Get filter parameters
    search_query = request.GET.get('search', '')
    series_filter = request.GET.get('series', '')
    status_filter = request.GET.get('status', '')
    location_filter = request.GET.get('location', '')
    
    # Apply search
    if search_query:
        projects = projects.filter(
            Q(project_id__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(project_code__icontains=search_query) |
            Q(client_name__icontains=search_query) |
            Q(vendor_name__icontains=search_query) |
            Q(location__icontains=search_query)
        )
    
    # Apply filters
    if series_filter:
        projects = projects.filter(series_type=series_filter)
    
    if status_filter:
        projects = projects.filter(project_status=status_filter)
    
    if location_filter:
        projects = projects.filter(location__icontains=location_filter)
    
    # Order by project_id
    projects = projects.order_by('project_id')
    
    # Get filter options
    filter_options = {
        'series': ['WAAS', 'SAAS', 'GW'],
        'statuses': ProjectCode.objects.values_list('project_status', flat=True).distinct().order_by('project_status'),
        'locations': ProjectCode.objects.exclude(location__isnull=True).exclude(location='').values_list('location', flat=True).distinct().order_by('location'),
    }
    
    # Calculate last used project IDs for each series
    from django.db.models import Max
    import re
    
    current_year = timezone.now().year
    year_suffix = str(current_year)[-2:]
    
    def get_last_sequence(series_type):
        """Get last used sequence number for a series type"""
        last_project = ProjectCode.objects.filter(
            series_type=series_type,
            project_id__startswith=f'{series_type}-{year_suffix}-'
        ).order_by('-project_id').first()
        
        if last_project:
            match = re.search(r'-(\d+)$', last_project.project_id)
            if match:
                return int(match.group(1))
        return 0
    
    last_ids = {
        'waas': {
            'last': f"WAAS-{year_suffix}-{get_last_sequence('WAAS'):03d}" if get_last_sequence('WAAS') > 0 else 'None',
            'next': f"WAAS-{year_suffix}-{get_last_sequence('WAAS') + 1:03d}"
        },
        'saas': {
            'last': f"SAAS-{year_suffix}-{get_last_sequence('SAAS'):03d}" if get_last_sequence('SAAS') > 0 else 'None',
            'next': f"SAAS-{year_suffix}-{get_last_sequence('SAAS') + 1:03d}"
        },
        'gw': {
            'last': f"GW-{year_suffix}-{get_last_sequence('GW'):03d}" if get_last_sequence('GW') > 0 else 'None',
            'next': f"GW-{year_suffix}-{get_last_sequence('GW') + 1:03d}"
        }
    }
    
    # Add pagination
    from django.core.paginator import Paginator
    total_count = projects.count()
    paginator = Paginator(projects, 100)  # 100 projects per page
    page = request.GET.get('page', 1)
    projects_page = paginator.get_page(page)

    context = {
        'projects': projects_page,
        'page_obj': projects_page,
        'search_query': search_query,
        'total_count': total_count,
        'filter_options': filter_options,
        'current_filters': {
            'series': series_filter,
            'status': status_filter,
            'location': location_filter,
        },
        'last_ids': last_ids,
    }

    return render(request, 'projects/admin_project_codes.html', context)


@login_required
def admin_update_project_field(request):
    """
    AJAX endpoint to update a single field in project_codes.
    Validates, saves, and logs change.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    # Check admin permission
    if request.user.role not in ['admin', 'super_user']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    try:
        project_id = request.POST.get('project_id')
        field_name = request.POST.get('field_name')
        new_value = request.POST.get('new_value', '').strip()
        
        # Get project
        project = ProjectCode.objects.get(project_id=project_id)
        
        # Get old value
        old_value = str(getattr(project, field_name)) if getattr(project, field_name) else ''
        
        # Skip if no change
        if old_value == new_value:
            return JsonResponse({'success': True, 'message': 'No change', 'changed': False})
        
        # Validate non-editable fields
        if field_name in ['created_at', 'updated_at', 'client_card_code', 'vendor_warehouse_code']:
            return JsonResponse({'success': False, 'error': f'{field_name} is not editable'})
        
        # VALIDATION LOGIC
        
        # 1. Unique constraints
        if field_name == 'code':
            if ProjectCode.objects.filter(code=new_value).exclude(project_id=project_id).exists():
                return JsonResponse({'success': False, 'error': f'Code "{new_value}" already exists'})
        
        if field_name == 'project_code':
            if ProjectCode.objects.filter(project_code=new_value).exclude(project_id=project_id).exists():
                return JsonResponse({'success': False, 'error': f'Project code "{new_value}" already exists'})
        
        if field_name == 'project_id':
            if ProjectCode.objects.filter(project_id=new_value).exists():
                return JsonResponse({'success': False, 'error': f'Project ID "{new_value}" already exists'})
        
        # 2. Series type validation
        if field_name == 'series_type':
            if new_value not in ['WAAS', 'SAAS', 'GW']:
                return JsonResponse({'success': False, 'error': 'Series must be WAAS, SAAS, or GW'})
        
        # 3. Status validation
        if field_name == 'project_status':
            valid_statuses = ['Operation Not Started', 'Active', 'Notice Period', 'Inactive']
            if new_value not in valid_statuses:
                return JsonResponse({'success': False, 'error': f'Invalid status. Must be: {", ".join(valid_statuses)}'})
        
        # 4. Operation mode validation
        if field_name == 'operation_mode':
            valid_modes = ['auto_mode', 'data_sharing', 'active_engagement', '']
            if new_value and new_value not in valid_modes:
                return JsonResponse({'success': False, 'error': 'Invalid operation mode'})
        
        # 5. MIS status validation
        if field_name == 'mis_status':
            valid_mis = ['mis_daily', 'mis_weekly', 'mis_monthly', 'inciflo', 'mis_automode', 'mis_not_required', '']
            if new_value and new_value not in valid_mis:
                return JsonResponse({'success': False, 'error': 'Invalid MIS status'})
        
        # 6. Billing unit validation
        if field_name == 'billing_unit':
            valid_units = ['sqft', 'pallet', 'unit', 'order', 'lumpsum', '']
            if new_value and new_value not in valid_units:
                return JsonResponse({'success': False, 'error': 'Invalid billing unit'})
        
        # 7. Date fields - convert to proper format
        date_fields = ['billing_start_date', 'notice_period_start_date', 'notice_period_end_date']
        if field_name in date_fields:
            if new_value:
                try:
                    from datetime import datetime
                    new_value = datetime.strptime(new_value, '%Y-%m-%d').date()
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'})
            else:
                new_value = None
        
        # 8. Integer fields
        integer_fields = ['notice_period_duration', 'minimum_billable_pallets']
        if field_name in integer_fields:
            if new_value:
                try:
                    new_value = int(new_value)
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Must be a number'})
            else:
                new_value = None
        
        # 9. Decimal fields
        if field_name == 'minimum_billable_sqft':
            if new_value:
                try:
                    from decimal import Decimal
                    new_value = Decimal(new_value)
                except:
                    return JsonResponse({'success': False, 'error': 'Invalid number format'})
            else:
                new_value = None
        
        # Special handling for project_id change
        if field_name == 'project_id':
            # Validate new project_id format
            if not new_value or len(new_value) < 3:
                return JsonResponse({'success': False, 'error': 'Project ID too short'})
            
            # Store old project_id for logging
            old_project_id = project.project_id
            
            # Use raw SQL to update project_id (bypass model validation)
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE project_codes SET project_id = %s, updated_at = NOW() WHERE project_id = %s",
                    [new_value, old_project_id]
                )
            
            # Log the change with OLD project_id
            from .models import ProjectCodeChangeLog
            ProjectCodeChangeLog.objects.create(
                project_id=old_project_id,  # Use old ID
                field_name=field_name,
                old_value=old_project_id,
                new_value=new_value,
                changed_by=request.user,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            # Also log with new ID for future reference
            ProjectCodeChangeLog.objects.create(
                project_id=new_value,
                field_name='project_id_migration',
                old_value=old_project_id,
                new_value=new_value,
                changed_by=request.user,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Project ID updated: {old_project_id} → {new_value}',
                'changed': True,
                'old_value': old_project_id,
                'new_value': new_value
            })
        
        # Update field
        setattr(project, field_name, new_value)
        project.updated_at = timezone.now()
        project.save()
        
        # Log the change
        from .models import ProjectCodeChangeLog
        ProjectCodeChangeLog.objects.create(
            project_id=project.project_id,
            field_name=field_name,
            old_value=old_value,
            new_value=str(new_value) if new_value else '',
            changed_by=request.user,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'message': f'{field_name} updated successfully',
            'changed': True,
            'old_value': old_value,
            'new_value': str(new_value) if new_value else ''
        })
        
    except ProjectCode.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Project not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def admin_project_history(request, project_id):
    """
    Get change history for a project (AJAX for modal)
    Now includes undo capability for each change
    """
    if request.user.role not in ['admin', 'super_user']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    try:
        from .models import ProjectCodeChangeLog
        
        # Get all changes for this project (including old project_ids)
        changes = ProjectCodeChangeLog.objects.filter(
            Q(project_id=project_id) | 
            Q(new_value=project_id, field_name='project_id')  # Catch renamed projects
        ).select_related('changed_by').order_by('-changed_at')[:100]  # Last 100 changes
        
        history_list = []
        for change in changes:
            history_list.append({
                'id': change.id,
                'field_name': change.field_name,
                'old_value': change.old_value or '(empty)',
                'new_value': change.new_value or '(empty)',
                'changed_by': change.changed_by.get_full_name() if change.changed_by else 'System',
                'changed_at': change.changed_at.strftime('%Y-%m-%d %H:%M:%S'),
                'changed_at_relative': get_relative_time(change.changed_at),
                'ip_address': change.ip_address or 'N/A',
                'can_undo': True  # All changes can be undone
            })
        
        return JsonResponse({
            'success': True,
            'project_id': project_id,
            'changes': history_list,
            'total': len(history_list)
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def get_relative_time(dt):
    """Convert datetime to relative time (e.g., '2 minutes ago')"""
    from django.utils.timezone import now
    delta = now() - dt
    
    if delta.days > 0:
        if delta.days == 1:
            return '1 day ago'
        elif delta.days < 7:
            return f'{delta.days} days ago'
        elif delta.days < 30:
            weeks = delta.days // 7
            return f'{weeks} week{"s" if weeks > 1 else ""} ago'
        else:
            months = delta.days // 30
            return f'{months} month{"s" if months > 1 else ""} ago'
    
    seconds = delta.seconds
    if seconds < 60:
        return f'{seconds} second{"s" if seconds != 1 else ""} ago'
    elif seconds < 3600:
        minutes = seconds // 60
        return f'{minutes} minute{"s" if minutes != 1 else ""} ago'
    else:
        hours = seconds // 3600
        return f'{hours} hour{"s" if hours != 1 else ""} ago'


@login_required
def admin_undo_last_change(request):
    """
    Undo the last change to a specific field
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    if request.user.role not in ['admin', 'super_user']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    try:
        project_id = request.POST.get('project_id')
        field_name = request.POST.get('field_name')
        
        from .models import ProjectCodeChangeLog
        
        # Get last change for this field
        last_change = ProjectCodeChangeLog.objects.filter(
            project_id=project_id,
            field_name=field_name
        ).order_by('-changed_at').first()
        
        if not last_change:
            return JsonResponse({'success': False, 'error': 'No change history found'})
        
        # Special handling for project_id field
        if field_name == 'project_id':
            # The project_id has changed, so we need to find it by the NEW value
            # The last_change.new_value IS the current project_id
            try:
                project = ProjectCode.objects.get(project_id=last_change.new_value)
            except ProjectCode.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Project not found (may have been changed again)'})
            
            # Revert to old project_id using raw SQL
            old_project_id = last_change.old_value
            
            from django.db import connection
            with connection.cursor() as cursor:
                # Check if old project_id already exists
                cursor.execute("SELECT COUNT(*) FROM project_codes WHERE project_id = %s", [old_project_id])
                if cursor.fetchone()[0] > 0:
                    return JsonResponse({'success': False, 'error': f'Cannot undo: {old_project_id} already exists'})
                
                # Update back to old value
                cursor.execute(
                    "UPDATE project_codes SET project_id = %s, updated_at = NOW() WHERE project_id = %s",
                    [old_project_id, last_change.new_value]
                )
            
            # Log the undo
            ProjectCodeChangeLog.objects.create(
                project_id=old_project_id,
                field_name=field_name,
                old_value=last_change.new_value,
                new_value=old_project_id,
                changed_by=request.user,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Reverted project_id: {last_change.new_value} → {old_project_id}',
                'reverted_value': old_project_id
            })
        
        # For all other fields, normal undo
        try:
            project = ProjectCode.objects.get(project_id=project_id)
        except ProjectCode.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Project not found'})
        
        # Revert to old value
        old_value = last_change.old_value
        
        # Handle different field types
        if field_name in ['billing_start_date', 'notice_period_start_date', 'notice_period_end_date']:
            if old_value:
                from datetime import datetime
                old_value = datetime.strptime(old_value, '%Y-%m-%d').date() if '-' in old_value else None
            else:
                old_value = None
        
        if field_name in ['notice_period_duration', 'minimum_billable_pallets']:
            old_value = int(old_value) if old_value else None
        
        if field_name == 'minimum_billable_sqft':
            from decimal import Decimal
            old_value = Decimal(old_value) if old_value else None
        
        # Set old value
        setattr(project, field_name, old_value)
        project.updated_at = timezone.now()
        project.save()
        
        # Log the undo action
        ProjectCodeChangeLog.objects.create(
            project_id=project_id,
            field_name=field_name,
            old_value=last_change.new_value,
            new_value=old_value or '',
            changed_by=request.user,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Reverted {field_name} to: {old_value or "(empty)"}',
            'reverted_value': old_value or ''
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)})
    

@login_required
def check_project_id_dependencies(request):
    """
    Check what data will be affected if project_id is changed.
    Returns counts of related records across all tables.
    """
    if request.user.role not in ['admin', 'super_user']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    project_id = request.GET.get('project_id')
    
    if not project_id:
        return JsonResponse({'success': False, 'error': 'project_id required'})
    
    try:
        from django.db import connection
        
        # Query all related tables
        dependencies = {}
        
        with connection.cursor() as cursor:
            # Monthly billings
            cursor.execute("SELECT COUNT(*) FROM monthly_billings WHERE project_id = %s", [project_id])
            dependencies['monthly_billings'] = cursor.fetchone()[0]
            
            # Project cards (rate cards)
            cursor.execute("SELECT COUNT(*) FROM operations_projectcard WHERE project_id = %s", [project_id])
            dependencies['rate_cards'] = cursor.fetchone()[0]
            
            # Daily MIS logs
            cursor.execute("SELECT COUNT(*) FROM operations_dailymislog WHERE project_id = %s", [project_id])
            dependencies['mis_logs'] = cursor.fetchone()[0]
            
            # Daily space utilization
            cursor.execute("SELECT COUNT(*) FROM operations_dailyspaceutilization WHERE project_id = %s", [project_id])
            dependencies['space_utilization'] = cursor.fetchone()[0]
            
            # Project documents
            cursor.execute("SELECT COUNT(*) FROM project_documents WHERE project_id = %s", [project_id])
            dependencies['documents'] = cursor.fetchone()[0]
            
            # Notifications
            cursor.execute("SELECT COUNT(*) FROM notifications WHERE project_id = %s", [project_id])
            dependencies['notifications'] = cursor.fetchone()[0]
            
            # Ad-hoc billing
            cursor.execute("SELECT COUNT(*) FROM operations_adhocbillingentry WHERE project_id = %s", [project_id])
            dependencies['adhoc_billing'] = cursor.fetchone()[0]
            
            # Dispute logs
            cursor.execute("SELECT COUNT(*) FROM operations_disputelog WHERE project_id = %s", [project_id])
            dependencies['disputes'] = cursor.fetchone()[0]
            
            # Project card alerts
            cursor.execute("SELECT COUNT(*) FROM operations_projectcardalert WHERE project_id = %s", [project_id])
            dependencies['alerts'] = cursor.fetchone()[0]
            
            # Warehouse holidays
            cursor.execute("SELECT COUNT(*) FROM operations_warehouseholiday WHERE project_id = %s", [project_id])
            dependencies['holidays'] = cursor.fetchone()[0]
            
            # Change history logs
            cursor.execute("SELECT COUNT(*) FROM project_code_change_logs WHERE project_id = %s", [project_id])
            dependencies['change_history'] = cursor.fetchone()[0]
            
            # Name change logs
            cursor.execute("SELECT COUNT(*) FROM project_name_change_logs WHERE project_id = %s", [project_id])
            dependencies['name_changes'] = cursor.fetchone()[0]
        
        # Calculate totals
        total_records = sum(dependencies.values())
        has_data = total_records > 0
        
        # Build warning message
        warnings = []
        if dependencies['rate_cards'] > 0:
            warnings.append(f"⚠️ {dependencies['rate_cards']} Rate Card(s)")
        if dependencies['monthly_billings'] > 0:
            warnings.append(f"💰 {dependencies['monthly_billings']} Billing Record(s)")
        if dependencies['mis_logs'] > 0:
            warnings.append(f"📊 {dependencies['mis_logs']} MIS Log(s)")
        if dependencies['documents'] > 0:
            warnings.append(f"📄 {dependencies['documents']} Document(s)")
        if dependencies['space_utilization'] > 0:
            warnings.append(f"📦 {dependencies['space_utilization']} Space Utilization Record(s)")
        
        return JsonResponse({
            'success': True,
            'project_id': project_id,
            'has_data': has_data,
            'total_records': total_records,
            'dependencies': dependencies,
            'warnings': warnings,
            'safe_to_change': not has_data,  # Only safe if no related data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    

@login_required
def admin_undo_change_by_id(request):
    """
    Undo a specific change by its log ID (from history modal)
    More flexible than undoing "last" change
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    if request.user.role not in ['admin', 'super_user']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    try:
        change_log_id = request.POST.get('change_log_id')
        
        from .models import ProjectCodeChangeLog
        
        # Get the specific change
        change = ProjectCodeChangeLog.objects.get(id=change_log_id)
        
        project_id = change.project_id
        field_name = change.field_name
        old_value = change.old_value
        
        # Special handling for project_id field
        if field_name == 'project_id':
            # Find project by NEW value (current project_id)
            try:
                project = ProjectCode.objects.get(project_id=change.new_value)
            except ProjectCode.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Project not found (may have been changed again)'})
            
            # Check if old project_id already exists
            if ProjectCode.objects.filter(project_id=old_value).exists():
                return JsonResponse({'success': False, 'error': f'Cannot undo: {old_value} already exists'})
            
            # Revert using raw SQL
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE project_codes SET project_id = %s, updated_at = NOW() WHERE project_id = %s",
                    [old_value, change.new_value]
                )
            
            # Log the undo
            ProjectCodeChangeLog.objects.create(
                project_id=old_value,
                field_name=field_name,
                old_value=change.new_value,
                new_value=old_value,
                changed_by=request.user,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            return JsonResponse({
                'success': True,
                'message': f'✅ Reverted project_id: {change.new_value} → {old_value}',
                'needs_reload': True
            })
        
        # For all other fields
        try:
            project = ProjectCode.objects.get(project_id=project_id)
        except ProjectCode.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Project not found'})
        
        # Handle different field types
        if field_name in ['billing_start_date', 'notice_period_start_date', 'notice_period_end_date']:
            if old_value:
                from datetime import datetime
                old_value = datetime.strptime(old_value, '%Y-%m-%d').date() if old_value and '-' in old_value else None
            else:
                old_value = None
        
        if field_name in ['notice_period_duration', 'minimum_billable_pallets']:
            old_value = int(old_value) if old_value else None
        
        if field_name == 'minimum_billable_sqft':
            from decimal import Decimal
            old_value = Decimal(old_value) if old_value else None
        
        # Set old value
        setattr(project, field_name, old_value if old_value != '(empty)' else '')
        project.updated_at = timezone.now()
        project.save()
        
        # Log the undo
        ProjectCodeChangeLog.objects.create(
            project_id=project_id,
            field_name=field_name,
            old_value=change.new_value,
            new_value=old_value or '',
            changed_by=request.user,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'message': f'✅ Reverted {field_name} to: {old_value or "(empty)"}',
            'needs_reload': False
        })
        
    except ProjectCodeChangeLog.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Change log not found'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)})
    


@login_required
def project_list_inactive(request):
    """Show inactive/closed projects - with role-based filtering"""
    # Apply same role-based access control as active projects
    projects = get_accessible_projects(request.user).exclude(
        project_status__in=['Active', 'Operation Not Started']
    ).select_related('client_card', 'vendor_warehouse')
    
    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        projects = projects.filter(
            Q(project_code__icontains=search_query) |
            Q(client_name__icontains=search_query) |
            Q(vendor_name__icontains=search_query) |
            Q(location__icontains=search_query)
        )
    
    # Filters
    current_filters = {
        'f_status': request.GET.get('f_status', ''),
        'f_coordinator': request.GET.get('f_coordinator', ''),
        'f_sales': request.GET.get('f_sales', ''),
        'f_mode': request.GET.get('f_mode', ''),
        'f_mis': request.GET.get('f_mis', ''),
    }
    
    if current_filters['f_status']:
        projects = projects.filter(project_status=current_filters['f_status'])
    
    if current_filters['f_coordinator']:
        projects = projects.filter(operation_coordinator=current_filters['f_coordinator'])
    
    if current_filters['f_sales']:
        projects = projects.filter(sales_manager=current_filters['f_sales'])
    
    if current_filters['f_mode']:
        projects = projects.filter(operation_mode=current_filters['f_mode'])
    
    if current_filters['f_mis']:
        projects = projects.filter(mis_status=current_filters['f_mis'])
    
    # Sorting
    sort_param = request.GET.get('sort', 'updated_desc')
    if sort_param == 'project_code':
        projects = projects.order_by('project_code')
    elif sort_param == 'project_code_desc':
        projects = projects.order_by('-project_code')
    elif sort_param == 'created':
        projects = projects.order_by('created_at')
    elif sort_param == 'created_desc':
        projects = projects.order_by('-created_at')
    elif sort_param == 'updated':
        projects = projects.order_by('updated_at')
    else:  # updated_desc (default)
        projects = projects.order_by('-updated_at')
    
    # Filter options
    filter_options = {
        'statuses': ProjectCode.objects.exclude(
            project_status__in=['Active', 'Operation Not Started']
        ).values_list('project_status', flat=True).distinct().order_by('project_status'),
        'coordinators': ProjectCode.objects.exclude(operation_coordinator__isnull=True).exclude(operation_coordinator='').values_list('operation_coordinator', flat=True).distinct().order_by('operation_coordinator'),
        'sales_managers': ProjectCode.objects.exclude(sales_manager__isnull=True).exclude(sales_manager='').values_list('sales_manager', flat=True).distinct().order_by('sales_manager'),
    }
    
    context = {
        'projects': projects,
        'total_count': projects.count(),
        'filter_type': 'inactive',
        'filter_title': 'Inactive Projects',
        'search_query': search_query,
        'current_filters': current_filters,
        'filter_options': filter_options,
        'role': request.user.role,
    }

    return render(request, 'projects/project_list.html', context)


@login_required
def all_project_change_logs(request):
    """
    View all project change logs across all projects (Admin only)
    """
    if request.user.role not in ['admin', 'super_user']:
        messages.error(request, 'Permission denied. Admin access required.')
        return redirect('accounts:dashboard')

    from .models import ProjectCodeChangeLog

    # Get all change logs, ordered by most recent
    logs = ProjectCodeChangeLog.objects.select_related('changed_by').order_by('-changed_at')[:500]

    return render(request, 'projects/all_change_logs.html', {
        'logs': logs,
        'total_logs': logs.count()
    })


@login_required
def admin_delete_project_code(request, project_id):
    """
    Admin-only: Permanently delete a project code.
    Should only be used for mistakenly created projects with no operational data.
    Checks dependencies before allowing deletion.
    """
    if request.user.role not in ['admin']:
        messages.error(request, "⛔ Access Denied: Admin only")
        return redirect('accounts:dashboard')

    try:
        project = ProjectCode.objects.get(project_id=project_id)
    except ProjectCode.DoesNotExist:
        messages.error(request, f"Project {project_id} not found")
        return redirect('projects:admin_project_codes')

    # GET request: Show confirmation page with dependency check
    if request.method == 'GET':
        from django.db import connection

        # Check all dependencies
        dependencies = {}

        with connection.cursor() as cursor:
            # Monthly billings
            cursor.execute("SELECT COUNT(*) FROM monthly_billings WHERE project_id = %s", [project_id])
            dependencies['monthly_billings'] = cursor.fetchone()[0]

            # Project cards (rate cards)
            cursor.execute("SELECT COUNT(*) FROM operations_projectcard WHERE project_id = %s", [project_id])
            dependencies['rate_cards'] = cursor.fetchone()[0]

            # Daily MIS logs
            cursor.execute("SELECT COUNT(*) FROM operations_dailymislog WHERE project_id = %s", [project_id])
            dependencies['mis_logs'] = cursor.fetchone()[0]

            # Daily space utilization
            cursor.execute("SELECT COUNT(*) FROM operations_dailyspaceutilization WHERE project_id = %s", [project_id])
            dependencies['space_utilization'] = cursor.fetchone()[0]

            # Project documents
            cursor.execute("SELECT COUNT(*) FROM project_documents WHERE project_id = %s", [project_id])
            dependencies['documents'] = cursor.fetchone()[0]

            # Notifications
            cursor.execute("SELECT COUNT(*) FROM notifications WHERE project_id = %s", [project_id])
            dependencies['notifications'] = cursor.fetchone()[0]

            # Ad-hoc billing
            cursor.execute("SELECT COUNT(*) FROM operations_adhocbillingentry WHERE project_id = %s", [project_id])
            dependencies['adhoc_billing'] = cursor.fetchone()[0]

            # Dispute logs
            cursor.execute("SELECT COUNT(*) FROM operations_disputelog WHERE project_id = %s", [project_id])
            dependencies['disputes'] = cursor.fetchone()[0]

            # Project card alerts
            cursor.execute("SELECT COUNT(*) FROM operations_projectcardalert WHERE project_id = %s", [project_id])
            dependencies['alerts'] = cursor.fetchone()[0]

            # Warehouse holidays
            cursor.execute("SELECT COUNT(*) FROM operations_warehouseholiday WHERE project_id = %s", [project_id])
            dependencies['holidays'] = cursor.fetchone()[0]

            # Change history logs
            cursor.execute("SELECT COUNT(*) FROM project_code_change_logs WHERE project_id = %s", [project_id])
            dependencies['change_logs'] = cursor.fetchone()[0]

            # Name change logs
            cursor.execute("SELECT COUNT(*) FROM project_name_change_logs WHERE project_id = %s", [project_id])
            dependencies['name_change_logs'] = cursor.fetchone()[0]

        # Calculate totals (excluding change logs which will be deleted anyway)
        operational_count = sum([
            dependencies['monthly_billings'],
            dependencies['rate_cards'],
            dependencies['mis_logs'],
            dependencies['space_utilization'],
            dependencies['documents'],
            dependencies['notifications'],
            dependencies['adhoc_billing'],
            dependencies['disputes'],
            dependencies['alerts'],
            dependencies['holidays']
        ])

        total_records = sum(dependencies.values())
        has_operational_data = operational_count > 0

        context = {
            'project': project,
            'dependencies': dependencies,
            'total_records': total_records,
            'operational_count': operational_count,
            'has_operational_data': has_operational_data,
        }

        return render(request, 'projects/admin_delete_project_confirm.html', context)

    # POST request: Perform deletion
    if request.method == 'POST':
        from django.db import transaction

        # Get user confirmation
        confirm = request.POST.get('confirm_delete')
        if confirm != 'DELETE':
            messages.error(request, "❌ Deletion cancelled: Confirmation text did not match")
            return redirect('projects:admin_delete_project', project_id=project_id)

        # Log the deletion before deleting
        from .models import ProjectCodeChangeLog
        ProjectCodeChangeLog.objects.create(
            project_id=project_id,
            field_name='project_deleted',
            old_value=f"{project.code} - {project.client_name or 'N/A'} - {project.project_status}",
            new_value='DELETED',
            changed_by=request.user,
            ip_address=request.META.get('REMOTE_ADDR')
        )

        # Store project info for success message
        deleted_info = f"{project_id} ({project.code})"

        with transaction.atomic():
            # Force-delete all operational data before deleting the project
            from operations.models import (
                MonthlyBilling, DailySpaceUtilization,
                DisputeLog, ProjectCardAlert, WarehouseHoliday, DailyMISLog
            )
            from operations.models_projectcard import ProjectCard
            from operations.models_adhoc import AdhocBillingEntry
            ProjectCard.objects.filter(project_id=project_id).delete()
            MonthlyBilling.objects.filter(project_id=project_id).delete()
            DailySpaceUtilization.objects.filter(project_id=project_id).delete()
            AdhocBillingEntry.objects.filter(project_id=project_id).delete()
            DisputeLog.objects.filter(project_id=project_id).delete()
            ProjectCardAlert.objects.filter(project_id=project_id).delete()
            WarehouseHoliday.objects.filter(project_id=project_id).delete()
            DailyMISLog.objects.filter(project_id=project_id).delete()

            # Delete the project (cascade handles change logs and name logs)
            project.delete()

        messages.success(request, f"✅ Project {deleted_info} and all its operational data have been permanently deleted")
        return redirect('projects:admin_project_codes')


@login_required
def admin_temp_project_cleanup_list(request):
    """
    List TEMP projects with "Operation Not Started" status that have operational data.
    Admin only - for cleaning up stuck TEMP projects.
    """
    if request.user.role not in ['admin', 'super_user']:
        messages.error(request, 'Access denied. Admin access required.')
        return redirect('accounts:dashboard')

    from operations.models import DailySpaceUtilization, MonthlyBilling
    from operations.models_adhoc import AdhocBillingEntry

    # Find TEMP projects with "Operation Not Started" status
    temp_projects = ProjectCode.objects.filter(
        project_id__startswith='TEMP-',
        project_status='Operation Not Started'
    )

    cleanup_candidates = []
    for project in temp_projects:
        daily_count = DailySpaceUtilization.objects.filter(project=project).count()
        adhoc_count = AdhocBillingEntry.objects.filter(project=project).count()
        monthly_count = MonthlyBilling.objects.filter(project=project).count()

        # Only include projects that have operational data
        if daily_count > 0 or adhoc_count > 0 or monthly_count > 0:
            cleanup_candidates.append({
                'project': project,
                'daily_entries': daily_count,
                'adhoc_entries': adhoc_count,
                'monthly_billings': monthly_count,
                'total_records': daily_count + adhoc_count + monthly_count
            })

    return render(request, 'projects/admin_temp_cleanup.html', {
        'cleanup_candidates': cleanup_candidates
    })


@login_required
def admin_temp_cleanup_preview(request, project_id):
    """
    Preview the proposed new permanent ID before migration
    """
    if request.user.role not in ['admin', 'super_user']:
        messages.error(request, 'Access denied')
        return redirect('accounts:dashboard')

    project = get_object_or_404(ProjectCode, project_id=project_id)

    if not project.project_id.startswith('TEMP-'):
        messages.error(request, 'Only TEMP projects can be previewed')
        return redirect('projects:admin_temp_cleanup')

    # Calculate the proposed new permanent ID (code stays the same!)
    from .utils import get_next_sequence_number
    from django.utils import timezone

    series_type = project.series_type
    year_code = timezone.now().year % 100

    # Generate proposed permanent ID (only ID changes, code stays same)
    sequence_num = get_next_sequence_number(series_type, year_code)
    proposed_project_id = f"{series_type}-{year_code:02d}-{sequence_num:03d}"

    # Get record counts
    from operations.models import DailySpaceUtilization, MonthlyBilling
    from operations.models_adhoc import AdhocBillingEntry

    daily_count = DailySpaceUtilization.objects.filter(project=project).count()
    adhoc_count = AdhocBillingEntry.objects.filter(project=project).count()
    monthly_count = MonthlyBilling.objects.filter(project=project).count()
    total_count = daily_count + adhoc_count + monthly_count

    # Find mergeable projects (Location + either Client or Vendor match)
    mergeable_projects = ProjectCode.objects.filter(
        series_type=project.series_type,
        location=project.location,
        state=project.state,
        project_status__in=['Active', 'Operation Not Started', 'Notice Period']
    ).exclude(
        project_id__startswith='TEMP-'
    ).filter(
        Q(client_name=project.client_name) | Q(vendor_name=project.vendor_name)
    ).exclude(
        # Exclude if both client AND vendor match (would be duplicate, not a transition)
        client_name=project.client_name, vendor_name=project.vendor_name
    ).order_by('-created_at')[:10]

    return render(request, 'projects/admin_temp_cleanup_preview.html', {
        'project': project,
        'proposed_project_id': proposed_project_id,
        'daily_count': daily_count,
        'adhoc_count': adhoc_count,
        'monthly_count': monthly_count,
        'total_count': total_count,
        'mergeable_projects': mergeable_projects,
    })


@login_required
def admin_temp_project_cleanup_action(request, project_id):
    """
    Handle cleanup actions for TEMP projects with operational data.
    Three options:
    1. Delete Data - Remove all operational data (clean slate)
    2. Migrate Data - Generate permanent ID and migrate all data
    3. Force Activate - Keep TEMP ID and mark as Active
    """
    if request.user.role not in ['admin', 'super_user']:
        messages.error(request, 'Access denied')
        return redirect('accounts:dashboard')

    if request.method != 'POST':
        return redirect('projects:admin_temp_cleanup')

    from django.db import transaction
    from operations.models import DailySpaceUtilization, MonthlyBilling
    from operations.models_adhoc import AdhocBillingEntry
    from operations.models_projectcard import ProjectCard
    from .models import UnusedProjectId

    project = get_object_or_404(ProjectCode, project_id=project_id)

    if not project.project_id.startswith('TEMP-'):
        messages.error(request, 'Only TEMP projects can be cleaned up')
        return redirect('projects:admin_temp_cleanup')

    action = request.POST.get('action')  # 'delete_data', 'migrate_data', or 'force_activate'

    try:
        with transaction.atomic():
            if action == 'delete_data':
                # Option 1: Delete all operational data
                daily_deleted, _ = DailySpaceUtilization.objects.filter(project=project).delete()
                adhoc_deleted, _ = AdhocBillingEntry.objects.filter(project=project).delete()
                monthly_deleted, _ = MonthlyBilling.objects.filter(project=project).delete()

                # Log the action
                from .models import ProjectCodeChangeLog
                ProjectCodeChangeLog.objects.create(
                    project_id=project.project_id,
                    field_name='admin_cleanup',
                    old_value=f"{daily_deleted + adhoc_deleted + monthly_deleted} records",
                    new_value='deleted',
                    changed_by=request.user,
                    ip_address=request.META.get('REMOTE_ADDR')
                )

                messages.success(request, f'✅ Deleted all operational data: {daily_deleted} daily entries, {adhoc_deleted} adhoc entries, {monthly_deleted} monthly billings')
                messages.info(request, 'You can now activate this project normally through the status change page.')

            elif action == 'migrate_data':
                # Option 2: Generate permanent ID and migrate all data
                # Code stays the same, only project_id changes

                # Step 1: Generate new permanent project ID
                from .utils import get_next_sequence_number

                series_type = project.series_type
                year_code = timezone.now().year % 100  # e.g., 26 for 2026

                # Get next sequence number for this series/year
                sequence_num = get_next_sequence_number(series_type, year_code)
                new_project_id = f"{series_type}-{year_code:02d}-{sequence_num:03d}"

                # Step 2: Store old project_id and all data BEFORE any changes
                old_project_id = project.project_id
                temp_created_at = project.created_at

                # Step 3: Count existing records (before migration)
                daily_count = DailySpaceUtilization.objects.filter(project=project).count()
                adhoc_count = AdhocBillingEntry.objects.filter(project=project).count()
                monthly_count = MonthlyBilling.objects.filter(project=project).count()
                projectcard_count = ProjectCard.objects.filter(project=project).count()

                from operations.models import DisputeLog
                disputes_count = DisputeLog.objects.filter(project=project).count()

                # Step 4: Create NEW project with permanent ID
                # Copy all fields from TEMP project
                new_project_data = {
                    'project_id': new_project_id,
                    'series_type': project.series_type,
                    'code': project.code,
                    'project_code': project.project_code,
                    'client_name': project.client_name,
                    'vendor_name': project.vendor_name,
                    'warehouse_code': project.warehouse_code,
                    'location': project.location,
                    'state': project.state,
                    'project_status': 'Active',
                    'sales_manager': project.sales_manager,
                    'operation_coordinator': project.operation_coordinator,
                    'backup_coordinator': project.backup_coordinator,
                    # 'billing_start_date' removed - now stored in ProjectCard only
                }

                # Add optional FK fields
                if project.client_card:
                    new_project_data['client_card'] = project.client_card
                if project.vendor_warehouse:
                    new_project_data['vendor_warehouse'] = project.vendor_warehouse
                if project.billing_unit_id:
                    new_project_data['billing_unit_id'] = project.billing_unit_id
                if project.operation_mode:
                    new_project_data['operation_mode'] = project.operation_mode
                if project.mis_status:
                    new_project_data['mis_status'] = project.mis_status
                if project.minimum_billable_sqft:
                    new_project_data['minimum_billable_sqft'] = project.minimum_billable_sqft
                if project.minimum_billable_pallets:
                    new_project_data['minimum_billable_pallets'] = project.minimum_billable_pallets

                # Create new project (but can't save yet due to unique constraints)
                # So we temporarily change TEMP's unique fields first
                project.code = f"TEMP_MIG_{old_project_id}"
                project.project_code = f"TEMP_MIGRATING_{old_project_id}"
                project.save()

                # Now create the permanent project
                new_project = ProjectCode.objects.create(**new_project_data)

                # Step 5: Migrate ALL FK references from TEMP to permanent
                DailySpaceUtilization.objects.filter(project_id=old_project_id).update(project=new_project)
                AdhocBillingEntry.objects.filter(project_id=old_project_id).update(project=new_project)
                MonthlyBilling.objects.filter(project_id=old_project_id).update(project=new_project)
                ProjectCard.objects.filter(project_id=old_project_id).update(project=new_project)
                DisputeLog.objects.filter(project_id=old_project_id).update(project=new_project)

                # Step 6: Archive old TEMP ID
                UnusedProjectId.objects.create(
                    project_id=old_project_id,
                    was_intended_for=new_project.client_name or 'Unknown',
                    intended_series=new_project.series_type,
                    merged_into=new_project_id,
                    created_at=temp_created_at,
                    deleted_by=request.user,
                    reason=f'Data migrated to permanent ID {new_project_id} via Admin Cleanup Utility'
                )

                # Step 7: Delete TEMP project
                project.delete()

                # Use counts from before migration
                daily_updated = daily_count
                adhoc_updated = adhoc_count
                monthly_updated = monthly_count
                projectcard_updated = projectcard_count
                disputes_updated = disputes_count

                # Step 8: Log the migration
                from .models import ProjectCodeChangeLog
                ProjectCodeChangeLog.objects.create(
                    project_id=new_project_id,
                    field_name='data_migration',
                    old_value=f'TEMP ID: {old_project_id}',
                    new_value=f'Permanent ID: {new_project_id}',
                    changed_by=request.user,
                    ip_address=request.META.get('REMOTE_ADDR')
                )

                # Success message with details
                total_migrated = daily_updated + adhoc_updated + monthly_updated + projectcard_updated + disputes_updated
                messages.success(request, f'✅ Successfully migrated {old_project_id} → {new_project_id}')
                messages.info(request, f'Migrated {total_migrated} operational records: {daily_updated} daily, {adhoc_updated} adhoc, {monthly_updated} monthly, {projectcard_updated} rate cards, {disputes_updated} disputes')
                messages.info(request, f'Project is now ACTIVE with permanent ID: {new_project_id}')

                # Redirect to new project detail page
                return redirect('projects:project_detail', project_id=new_project_id)

            elif action == 'merge_into_existing':
                # Option 2B: Merge TEMP project into existing project
                target_project_id = request.POST.get('target_project_id')
                if not target_project_id:
                    messages.error(request, 'No target project specified')
                    return redirect('projects:admin_temp_cleanup')

                try:
                    target_project = ProjectCode.objects.get(project_id=target_project_id)
                except ProjectCode.DoesNotExist:
                    messages.error(request, f'Target project {target_project_id} not found')
                    return redirect('projects:admin_temp_cleanup')

                # Use existing merge function from views_status
                from .views_status import merge_temp_into_existing

                success, message, updated_project = merge_temp_into_existing(
                    project, target_project, request.user,
                    reason='Admin cleanup - merged TEMP project with operational data'
                )

                if success:
                    messages.success(request, f'✅ {message}')
                    return redirect('projects:project_detail', project_id=updated_project.project_id)
                else:
                    messages.error(request, f'❌ {message}')
                    return redirect('projects:admin_temp_cleanup')

            elif action == 'force_activate':
                # Option 3: Force activate with TEMP ID
                old_status = project.project_status
                project.project_status = 'Active'
                project.save()

                # Log the action
                from .models import ProjectCodeChangeLog
                ProjectCodeChangeLog.objects.create(
                    project_id=project.project_id,
                    field_name='project_status',
                    old_value=old_status,
                    new_value='Active',
                    changed_by=request.user,
                    ip_address=request.META.get('REMOTE_ADDR')
                )

                messages.warning(request, f'⚠️ Project {project.code} forced to Active status')
                messages.info(request, 'Note: TEMP ID retained with existing operational data')

            else:
                messages.error(request, 'Invalid action')

    except Exception as e:
        messages.error(request, f'Error during cleanup: {str(e)}')

    return redirect('projects:admin_temp_cleanup')