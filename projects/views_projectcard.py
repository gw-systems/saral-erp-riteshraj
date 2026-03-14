"""
Project Card Management Views
For backoffice users to create and manage project cards
For operations teams to view project cards
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from decimal import Decimal, InvalidOperation
from .models import ProjectCode
from operations.models_projectcard import (
    ProjectCard,
    StorageRate,
    StorageRateSlab,
    HandlingRate,
    ValueAddedService,
    InfrastructureCost,
    TransportRate,
)
from django.db import models
import json
from django.utils import timezone
from django.db.models import Q, Count
from django.http import JsonResponse
from operations.models import ProjectCardAlert


# Import dropdown master data models
from dropdown_master_data.models import (
    StorageUnit,
    HandlingBaseType,
    HandlingDirection,
    VASServiceType,
    VASUnit,
    OperationalCostType,
    SalesChannel,
    VehicleType,
)


def get_dropdown_choices(model_class):
    """Get active dropdown choices from master data"""
    return [(item.code, item.label) for item in model_class.objects.filter(is_active=True).order_by('display_order', 'code')]


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


# ==================== HELPER FUNCTIONS ====================

def get_decimal_or_none(value):
    """
    Convert empty string to None for DecimalField
    Safely handles empty strings, None, and invalid decimal values
    """
    if value is None or value == '' or value == 'None':
        return None
    try:
        return Decimal(str(value).strip())
    except (ValueError, TypeError, InvalidOperation):
        return None


def get_int_or_none(value):
    """
    Convert empty string to None for IntegerField
    Safely handles empty strings, None, and invalid integer values
    """
    if value is None or value == '' or value == 'None':
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


# ==================== PROJECT CARD LIST & DETAIL VIEWS ====================

@login_required
def project_card_list(request):
    from django.apps import apps
    ProjectCode = apps.get_model('projects', 'ProjectCode')
    
    # Base queryset - ONLY SHOW ACTIVE, NOT STARTED, AND NOTICE PERIOD
    project_cards = ProjectCard.objects.select_related('project').prefetch_related('storage_rates').filter(
        project__project_status__in=['Active', 'Operation Not Started', 'Notice Period']
    )
    
    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        project_cards = project_cards.filter(
            Q(project__project_code__icontains=search_query) |
            Q(project__client_name__icontains=search_query) |
            Q(project__vendor_name__icontains=search_query)
        )
    
    # Filters
    current_filters = {
        'f_project': request.GET.get('f_project', ''),
        'f_status': request.GET.get('f_status', ''),
        'f_escalation': request.GET.get('f_escalation', ''),
    }
    
    if current_filters['f_project']:
        project_cards = project_cards.filter(project_id=current_filters['f_project'])
    
    if current_filters['f_status'] == 'active':
        project_cards = project_cards.filter(project__project_status='Active')
    elif current_filters['f_status'] == 'not_started':
        project_cards = project_cards.filter(project__project_status='Operation Not Started')
    elif current_filters['f_status'] == 'notice_period':
        project_cards = project_cards.filter(project__project_status='Notice Period')
    
    if current_filters['f_escalation'] == 'yes':
        project_cards = project_cards.filter(has_fixed_escalation=True)
    elif current_filters['f_escalation'] == 'no':
        project_cards = project_cards.filter(has_fixed_escalation=False)
    
    # Sorting (default: latest modified first)
    sort_param = request.GET.get('sort', 'updated_desc')
    if sort_param == 'project':
        project_cards = project_cards.order_by('project__project_code')
    elif sort_param == 'project_desc':
        project_cards = project_cards.order_by('-project__project_code')
    elif sort_param == 'updated':
        project_cards = project_cards.order_by('updated_at')
    else:  # Default: updated_desc
        project_cards = project_cards.order_by('-updated_at')
    
    # Filter options - ONLY ACTIVE PROJECTS
    filter_options = {
        'projects': ProjectCode.objects.filter(
            project_status__in=['Active', 'Operation Not Started', 'Notice Period']
        ).order_by('project_code')
    }
    
    context = {
        'project_cards': project_cards,
        'total_count': project_cards.count(),
        'search_query': search_query,
        'current_filters': current_filters,
        'filter_options': filter_options,
    }
    
    return render(request, 'operations/project_card_list.html', context)


@login_required
def project_card_detail(request, project_card_id):
    project_card = get_object_or_404(ProjectCard, id=project_card_id)

    # Get all rates
    storage_rates = project_card.storage_rates.all()
    handling_rates = project_card.handling_rates.all()
    transport_rates = project_card.transport_rates.all()
    vas_services = project_card.vas_services.all()
    infrastructure_costs = project_card.infrastructure_costs.all()
    storage_slabs = project_card.storage_slabs.all()

    # Calculate margin
    margin_percent = calculate_project_margin(storage_rates, handling_rates)

    context = {
        'project_card': project_card,
        'storage_rates': storage_rates,
        'handling_rates': handling_rates,
        'transport_rates': transport_rates,
        'vas_services': vas_services,
        'infrastructure_costs': infrastructure_costs,
        'storage_slabs': storage_slabs,
        'margin_percent': margin_percent,
    }

    return render(request, 'operations/project_card_detail.html', context)



def calculate_project_margin(storage_rates, handling_rates):
    """
    Calculate overall project margin percentage based on client vs vendor rates.
    
    Returns dict with:
    - overall: float (weighted average margin %)
    - breakdown: dict {category: margin %}
    """
    margins = []
    
    # Storage margin calculation
    client_storage = None
    vendor_storage = None
    
    for rate in storage_rates:
        if rate.rate_for == 'client':
            client_storage = rate
        elif rate.rate_for == 'vendor':
            vendor_storage = rate
    
    if client_storage and vendor_storage:
        client_monthly = client_storage.monthly_billable_amount or 0
        vendor_monthly = vendor_storage.monthly_billable_amount or 0
        
        if client_monthly > 0:
            storage_margin = ((client_monthly - vendor_monthly) / client_monthly) * 100
            margins.append(('Storage', storage_margin))
    
    # Handling margin (sample 100 units for comparison)
    client_handling = [r for r in handling_rates if r.rate_for == 'client']
    vendor_handling = [r for r in handling_rates if r.rate_for == 'vendor']
    
    if client_handling and vendor_handling:
        sample_units = 100
        client_total = sum([rate.rate * sample_units for rate in client_handling])
        vendor_total = sum([rate.rate * sample_units for rate in vendor_handling])
        
        if client_total > 0:
            handling_margin = ((client_total - vendor_total) / client_total) * 100
            margins.append(('Handling', handling_margin))
    
    # Calculate weighted average (70% storage, 30% handling)
    if len(margins) == 2:
        overall = (margins[0][1] * Decimal('0.7')) + (margins[1][1] * Decimal('0.3'))
    elif len(margins) == 1:
        overall = margins[0][1]
    else:
        overall = None
    
    return {
        'overall': round(overall, 1) if overall is not None else None,
        'breakdown': {m[0]: round(m[1], 1) for m in margins}
    }


@login_required
def project_card_by_project(request, project_id):
    """
    Smart redirect: Click on project_code -> Goes to its project card
    If no project card exists, shows friendly message
    """
    
    # Check permissions
    if request.user.role not in ['admin', 'backoffice', 'operation_controller', 'operation_manager', 'operation_coordinator', 'warehouse_manager']:
        messages.error(request, "You don't have permission to view project cards.")
        return redirect('accounts:dashboard')
    
    # Get the project
    project = get_object_or_404(ProjectCode, project_id=project_id)
    
    # Check if coordinator has access to this project
    if request.user.role in ['operation_coordinator', 'warehouse_manager']:
        if project.operation_coordinator != request.user.get_full_name():
            messages.error(request, "You don't have permission to view this project's project card.")
            return redirect('accounts:dashboard')
    
    # Try to find active project card for this project
    project_card = ProjectCard.objects.filter(
        project=project
    ).order_by('-created_at').first()
    
    if project_card:
        # Project card exists - redirect to detail page
        return redirect('projects:project_detail', project_id=project_card.project.project_id)
    else:
        # No project card - show friendly message page
        context = {
            'project': project,
            'can_create': request.user.role in ['admin', 'backoffice'],
        }
        return render(request, 'operations/project_card_not_found.html', context)


# ==================== PROJECT CARD CREATE VIEW ====================

@login_required
@transaction.atomic
def project_card_create_unified(request):
    """Create complete project card in one page - BACKOFFICE ONLY"""
    
    # Check permissions - ONLY backoffice/admin/super_user can create
    if request.user.role not in ['admin', 'super_user', 'backoffice']:
        messages.error(request, "You don't have permission to create project cards.")
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        try:
            # Get the project
            project_id = request.POST.get('project')
            project = ProjectCode.objects.get(project_id=project_id)
            
            # ==================== AUTO-LINK CLIENT CARD ====================
            client_card = None
            if project.client_name:
                from projects.models_client import ClientCard
                # Try to find matching client card by name (case-insensitive)
                client_card = ClientCard.objects.filter(
                    client_legal_name__iexact=project.client_name.strip(),
                    client_is_active=True
                ).first()
                
                if client_card:
                    # Update project with FK link
                    project.client_card = client_card
                    project.save(update_fields=['client_card'])
            
            # ==================== AUTO-LINK WAREHOUSE ====================
            vendor_warehouse = None
            if project.vendor_name:
                try:
                    from supply.models import VendorWarehouse, VendorCard

                    # Strategy 1: Try to find matching warehouse by vendor name + location
                    vendor_card = VendorCard.objects.filter(
                        vendor_short_name__iexact=project.vendor_name.strip(),
                        vendor_is_active=True
                    ).first()

                    if vendor_card and project.location:
                        # Find warehouse in the project's location
                        vendor_warehouse = VendorWarehouse.objects.filter(
                            vendor_code=vendor_card,
                            warehouse_location_id__city__iexact=project.location.strip(),
                            warehouse_is_active=True
                        ).first()

                        # If not found by exact location match, try any warehouse from this vendor
                        if not vendor_warehouse:
                            vendor_warehouse = VendorWarehouse.objects.filter(
                                vendor_code=vendor_card,
                                warehouse_is_active=True
                            ).first()

                        if vendor_warehouse:
                            # Update project with FK link
                            project.vendor_warehouse = vendor_warehouse
                            project.save(update_fields=['vendor_warehouse'])
                except Exception:
                    # Supply app tables not deployed yet, skip warehouse auto-linking
                    pass
            
            # 1. Create Project Card with FK links
            # Default valid_from to agreement_start_date or today
            from django.utils import timezone
            valid_from_date = request.POST.get('agreement_start_date') or timezone.now().date()

            project_card = ProjectCard.objects.create(
                project=project,
                client_card=client_card,
                vendor_warehouse=vendor_warehouse,
                valid_from=valid_from_date,
                agreement_start_date=request.POST.get('agreement_start_date') or None,
                agreement_end_date=request.POST.get('agreement_end_date') or None,
                yearly_escalation_date=request.POST.get('yearly_escalation_date') or None,
                has_fixed_escalation=request.POST.get('has_fixed_escalation') == 'on',
                annual_escalation_percent=get_decimal_or_none(request.POST.get('annual_escalation_percent')),
                security_deposit=get_decimal_or_none(request.POST.get('security_deposit')),
                billing_start_date=request.POST.get('billing_start_date') or None,
                operation_start_date=request.POST.get('operation_start_date') or None,
                storage_payment_days=get_int_or_none(request.POST.get('storage_payment_days')),
                handling_payment_days=get_int_or_none(request.POST.get('handling_payment_days')),
                notes=request.POST.get('notes', ''),
                created_by=request.user,
            )
            
            # 2. Create Storage Rates
            storage_count = 0
            for key in request.POST.keys():
                if key.startswith('storage_rate_for_'):
                    row_num = key.split('_')[-1]
                    rate_for = request.POST.get(f'storage_rate_for_{row_num}', '').strip()
                    
                    # Only create if rate_for has a value (row is not empty)
                    if rate_for:
                        storage_count += 1
                        
                        StorageRate.objects.create(
                            project_card=project_card,
                            rate_for=rate_for,
                            space_type_id=request.POST.get(f'storage_space_type_{row_num}'),
                            minimum_billable_area=get_decimal_or_none(request.POST.get(f'storage_min_billable_{row_num}')),
                            flat_rate_per_unit=get_decimal_or_none(request.POST.get(f'storage_rate_per_unit_{row_num}')),
                            monthly_billable_amount=get_decimal_or_none(request.POST.get(f'storage_monthly_amount_{row_num}')),
                            saas_monthly_charge=get_decimal_or_none(request.POST.get(f'storage_saas_{row_num}')),
                            remarks=request.POST.get(f'storage_remarks_{row_num}', ''),
                        )


            # 2. Create Storage Rates
            storage_count = 0
            for key in request.POST.keys():
                if key.startswith('storage_rate_for_'):
                    row_num = key.split('_')[-1]
                    rate_for = request.POST.get(f'storage_rate_for_{row_num}', '').strip()
                    
                    # Only create if rate_for has a value (row is not empty)
                    if rate_for:
                        storage_count += 1
                        
                        pricing_type = request.POST.get(f'storage_pricing_type_{row_num}', 'flat')
                        space_type = request.POST.get(f'storage_space_type_{row_num}', '')
                        
                        # Create the base StorageRate
                        storage_rate = StorageRate.objects.create(
                            project_card=project_card,
                            rate_for=rate_for,
                            space_type_id=space_type,
                            minimum_billable_area=get_decimal_or_none(request.POST.get(f'storage_min_billable_{row_num}')),
                            flat_rate_per_unit=get_decimal_or_none(request.POST.get(f'storage_rate_per_unit_{row_num}')),
                            monthly_billable_amount=get_decimal_or_none(
                                request.POST.get(f'storage_monthly_amount_{row_num}') or 
                                request.POST.get(f'storage_lumpsum_amount_{row_num}')
                            ),
                            saas_monthly_charge=get_decimal_or_none(request.POST.get(f'storage_saas_{row_num}')),
                            remarks=request.POST.get(f'storage_remarks_{row_num}', ''),
                        )
                        
                        # Handle SLABS if pricing_type is 'slab'
                        if pricing_type == 'slab':
                            # Find all slabs for this storage rate
                            slab_num = 1
                            while True:
                                min_qty_key = f'slab_min_{row_num}_{slab_num}'
                                min_qty = request.POST.get(min_qty_key)
                                
                                if not min_qty:
                                    break
                                
                                max_qty = request.POST.get(f'slab_max_{row_num}_{slab_num}')
                                rate = request.POST.get(f'slab_rate_{row_num}_{slab_num}')
                                remarks = request.POST.get(f'slab_remarks_{row_num}_{slab_num}', '')
                                
                                # Create StorageRateSlab
                                StorageRateSlab.objects.create(
                                    project_card=project_card,
                                    rate_for=rate_for,
                                    space_type_id=space_type,
                                    min_quantity=min_qty,
                                    max_quantity=max_qty if max_qty else None,
                                    rate_per_unit=rate,
                                    remarks=remarks
                                )
                                
                                slab_num += 1
                        

            # 3. Create Handling Rates
            handling_count = 0
            for key in request.POST.keys():
                if key.startswith('handling_rate_for_'):
                    row_num = key.split('_')[-1]
                    rate_for = request.POST.get(f'handling_rate_for_{row_num}', '').strip()
                    
                    handling_rate = get_decimal_or_none(request.POST.get(f'handling_rate_{row_num}'))
                    # Only create if rate_for and rate both have values
                    if rate_for and handling_rate is not None:
                        handling_count += 1

                        HandlingRate.objects.create(
                            project_card=project_card,
                            rate_for=rate_for,
                            direction=request.POST.get(f'handling_direction_{row_num}', ''),
                            channel_id=request.POST.get(f'handling_channel_{row_num}') or None,
                            base_type_id=request.POST.get(f'handling_base_type_{row_num}') or None,
                            min_weight_kg=get_decimal_or_none(request.POST.get(f'handling_min_weight_{row_num}')),
                            max_weight_kg=get_decimal_or_none(request.POST.get(f'handling_max_weight_{row_num}')),
                            rate=handling_rate,
                            remarks=request.POST.get(f'handling_remarks_{row_num}', ''),
                        )

            # 4. Create Transport Rates
            transport_count = 0
            for key in request.POST.keys():
                if key.startswith('transport_rate_for_'):
                    row_num = key.split('_')[-1]
                    rate_for = request.POST.get(f'transport_rate_for_{row_num}', '').strip()
                    
                    # Only create if rate_for has a value (row is not empty)
                    if rate_for:
                        transport_count += 1
                        
                        TransportRate.objects.create(
                            project_card=project_card,
                            rate_for=rate_for,
                            vehicle_type=request.POST.get(f'transport_vehicle_type_{row_num}', ''),
                            rate=get_decimal_or_none(request.POST.get(f'transport_rate_{row_num}')),
                            description=request.POST.get(f'transport_description_{row_num}', ''),
                            remarks=request.POST.get(f'transport_remarks_{row_num}', ''),
                        )

            # 5. Create Value Added Services
            vas_count = 0
            for key in request.POST.keys():
                if key.startswith('vas_rate_for_'):
                    row_num = key.split('_')[-1]
                    rate_for = request.POST.get(f'vas_rate_for_{row_num}', '').strip()
                    vas_service_type = request.POST.get(f'vas_service_type_{row_num}', '').strip()
                    vas_rate = get_decimal_or_none(request.POST.get(f'vas_rate_{row_num}'))

                    # Only create if rate_for, service_type, and rate all have values
                    if rate_for and vas_service_type and vas_rate is not None:
                        vas_count += 1

                        ValueAddedService.objects.create(
                            project_card=project_card,
                            rate_for=rate_for,
                            service_type_id=vas_service_type,
                            service_description=request.POST.get(f'vas_description_{row_num}', ''),
                            rate=vas_rate,
                            unit=request.POST.get(f'vas_unit_{row_num}', '') or 'per unit',
                            remarks=request.POST.get(f'vas_remarks_{row_num}', ''),
                        )

            # 6. Create Infrastructure Costs
            infra_count = 0
            for key in request.POST.keys():
                if key.startswith('infra_rate_for_'):
                    row_num = key.split('_')[-1]
                    rate_for = request.POST.get(f'infra_rate_for_{row_num}', '').strip()
                    amount = get_decimal_or_none(request.POST.get(f'infra_amount_{row_num}'))

                    # Only create if BOTH rate_for AND amount have values
                    if rate_for and amount is not None:
                        infra_count += 1

                        InfrastructureCost.objects.create(
                            project_card=project_card,
                            rate_for=rate_for,
                            cost_type_id=request.POST.get(f'infra_cost_type_{row_num}') or None,
                            description=request.POST.get(f'infra_description_{row_num}', ''),
                            amount=amount,
                            is_at_actual=f'infra_at_actual_{row_num}' in request.POST,
                            remarks=request.POST.get(f'infra_remarks_{row_num}', ''),
                        )
            
            # ==================== SUCCESS MESSAGES WITH LINKING INFO ====================
            messages.success(request, 
                f"✅ Project card created successfully with {storage_count} storage rates, "
                f"{handling_count} handling rates, {transport_count} transport rates, " # Use the variable here
                f"{vas_count} VAS, {infra_count} infra costs")
                        
            # Show linking status
            if client_card:
                messages.info(request, f"🔗 Linked to Client Card: {client_card.client_code} - {client_card.client_legal_name}")
            else:
                if project.client_name:
                    messages.warning(request, f"⚠️ No matching Client Card found for '{project.client_name}'. Create one from Master Data menu.")
            
            if vendor_warehouse:
                messages.info(request, f"🔗 Linked to Warehouse: {vendor_warehouse.warehouse_code} ({vendor_warehouse.vendor_code.vendor_short_name})")
            else:
                if project.vendor_name:
                    messages.warning(request, f"⚠️ No matching Warehouse found for '{project.vendor_name}'. Create one from Master Data menu.")
            
            return_url = get_return_url(request)
            if return_url:
                return redirect(return_url)
            return redirect('projects:project_detail', project_id=project_card.project.project_id)
            
        except Exception as e:
            messages.error(request, f"❌ Error creating project card: {str(e)}")
            import traceback
            print("=" * 80)
            print("ERROR CREATING PROJECT CARD:")
            print(traceback.format_exc())
            print("=" * 80)
            # Re-raise to trigger transaction rollback
            raise
    
    # GET request - Show form
    projects = ProjectCode.objects.filter(
        project_status__in=['Active', 'Operation Not Started']
    ).order_by('client_name', 'project_code')
    
    # Pre-select project if coming from project creation
    preselect_project = request.GET.get('project')
    
    context = {
        'projects': projects,
        'preselect_project': preselect_project,
        
        # Pass dropdown choices from master data (NO HARDCODING!)
        'storage_space_type_choices': json.dumps(get_dropdown_choices(StorageUnit)),
        'handling_direction_choices': json.dumps(get_dropdown_choices(HandlingDirection)),
        'handling_channel_choices': json.dumps(get_dropdown_choices(SalesChannel)),
        'handling_base_type_choices': json.dumps(get_dropdown_choices(HandlingBaseType)),
        'vehicle_types_json': json.dumps(get_dropdown_choices(VehicleType)),
        'vas_service_type_choices': json.dumps(get_dropdown_choices(VASServiceType)),
        'vas_unit_choices': json.dumps(get_dropdown_choices(VASUnit)),
        'infra_cost_type_choices': json.dumps(get_dropdown_choices(OperationalCostType)),
    }
    
    return render(request, 'operations/project_card_create_unified.html', context)


# ==================== PROJECT CARD EDIT VIEW ====================

@login_required
@transaction.atomic
def project_card_edit(request, project_card_id):
    """Edit existing project card - BACKOFFICE ONLY"""
    
    # Check permissions - ONLY backoffice/admin/super_user can edit
    if request.user.role not in ['admin', 'super_user', 'backoffice']:
        messages.error(request, "You don't have permission to edit project cards.")
        return redirect('accounts:dashboard')
    
    # Get the project card to edit
    project_card = get_object_or_404(ProjectCard, id=project_card_id)
    
    if request.method == 'POST':
        try:
            # 1. Update Project Card basic details
            # Update valid_from if agreement_start_date changes
            new_agreement_start = request.POST.get('agreement_start_date') or None
            if new_agreement_start:
                project_card.valid_from = new_agreement_start

            project_card.agreement_start_date = new_agreement_start
            project_card.agreement_end_date = request.POST.get('agreement_end_date') or None
            project_card.yearly_escalation_date = request.POST.get('yearly_escalation_date') or None

            # OPERATIONAL DATES
            project_card.billing_start_date = request.POST.get('billing_start_date') or None
            project_card.operation_start_date = request.POST.get('operation_start_date') or None
            
            # PAYMENT TERMS
            project_card.storage_payment_days = get_int_or_none(request.POST.get('storage_payment_days'))
            project_card.handling_payment_days = get_int_or_none(request.POST.get('handling_payment_days'))
            
            project_card.has_fixed_escalation = request.POST.get('has_fixed_escalation') == 'on'
            project_card.annual_escalation_percent = get_decimal_or_none(request.POST.get('annual_escalation_percent'))
            project_card.security_deposit = get_decimal_or_none(request.POST.get('security_deposit'))
            project_card.notes = request.POST.get('notes', '')
            project_card.last_modified_by = request.user
            project_card.save()
            
            # 2. Delete existing related rates (we'll recreate them to ensure synchronization)
            project_card.storage_rates.all().delete()
            project_card.storage_slabs.all().delete()  
            project_card.handling_rates.all().delete()
            project_card.transport_rates.all().delete() 
            project_card.vas_services.all().delete()
            project_card.infrastructure_costs.all().delete()
            
            # 3. Create Storage Rates
            storage_count = 0
            for key in request.POST.keys():
                if key.startswith('storage_rate_for_'):
                    row_num = key.split('_')[-1]
                    rate_for = request.POST.get(f'storage_rate_for_{row_num}', '').strip()
                    
                    if rate_for:
                        storage_count += 1
                        pricing_type = request.POST.get(f'storage_pricing_type_{row_num}', 'flat')
                        space_type = request.POST.get(f'storage_space_type_{row_num}', '')
                        
                        # Create the base StorageRate
                        StorageRate.objects.create(
                            project_card=project_card,
                            rate_for=rate_for,
                            space_type_id=space_type,
                            minimum_billable_area=get_decimal_or_none(request.POST.get(f'storage_min_billable_{row_num}')),
                            flat_rate_per_unit=get_decimal_or_none(request.POST.get(f'storage_rate_per_unit_{row_num}')),
                            monthly_billable_amount=get_decimal_or_none(
                                request.POST.get(f'storage_monthly_amount_{row_num}') or 
                                request.POST.get(f'storage_lumpsum_amount_{row_num}')
                            ),
                            saas_monthly_charge=get_decimal_or_none(request.POST.get(f'storage_saas_{row_num}')),
                            remarks=request.POST.get(f'storage_remarks_{row_num}', ''),
                        )
                        
                        # Handle SLABS if pricing_type is 'slab'
                        if pricing_type == 'slab':
                            slab_num = 1
                            while True:
                                min_qty_key = f'slab_min_{row_num}_{slab_num}'
                                min_qty = request.POST.get(min_qty_key)
                                if not min_qty:
                                    break
                                
                                max_qty = request.POST.get(f'slab_max_{row_num}_{slab_num}')
                                rate = request.POST.get(f'slab_rate_{row_num}_{slab_num}')
                                slab_remarks = request.POST.get(f'slab_remarks_{row_num}_{slab_num}', '')
                                
                                StorageRateSlab.objects.create(
                                    project_card=project_card,
                                    rate_for=rate_for,
                                    space_type_id=space_type,
                                    min_quantity=min_qty,
                                    max_quantity=max_qty if max_qty else None,
                                    rate_per_unit=rate,
                                    remarks=slab_remarks
                                )
                                slab_num += 1

            # 4. Create Handling Rates
            handling_count = 0
            for key in request.POST.keys():
                if key.startswith('handling_rate_for_'):
                    row_num = key.split('_')[-1]
                    rate_for = request.POST.get(f'handling_rate_for_{row_num}', '').strip()
                    handling_rate = get_decimal_or_none(request.POST.get(f'handling_rate_{row_num}'))

                    # Only create if rate_for and rate both have values
                    if rate_for and handling_rate is not None:
                        handling_count += 1
                        HandlingRate.objects.create(
                            project_card=project_card,
                            rate_for=rate_for,
                            direction=request.POST.get(f'handling_direction_{row_num}', ''),
                            channel_id=request.POST.get(f'handling_channel_{row_num}') or None,
                            base_type_id=request.POST.get(f'handling_base_type_{row_num}') or None,
                            min_weight_kg=get_decimal_or_none(request.POST.get(f'handling_min_weight_{row_num}')),
                            max_weight_kg=get_decimal_or_none(request.POST.get(f'handling_max_weight_{row_num}')),
                            rate=handling_rate,
                            remarks=request.POST.get(f'handling_remarks_{row_num}', ''),
                        )

            # 5. Create Transport Rates
            transport_count = 0
            for key in request.POST.keys():
                if key.startswith('transport_rate_for_'):
                    row_num = key.split('_')[-1]
                    rate_for = request.POST.get(f'transport_rate_for_{row_num}', '').strip()

                    if rate_for:
                        transport_count += 1
                        TransportRate.objects.create(
                            project_card=project_card,
                            rate_for=rate_for,
                            vehicle_type=request.POST.get(f'transport_vehicle_type_{row_num}', ''),
                            rate=get_decimal_or_none(request.POST.get(f'transport_rate_{row_num}')),
                            description=request.POST.get(f'transport_description_{row_num}', ''),
                            remarks=request.POST.get(f'transport_remarks_{row_num}', ''),
                        )

            # 6. Create Value Added Services
            vas_count = 0
            for key in request.POST.keys():
                if key.startswith('vas_rate_for_'):
                    row_num = key.split('_')[-1]
                    rate_for = request.POST.get(f'vas_rate_for_{row_num}', '').strip()
                    vas_service_type = request.POST.get(f'vas_service_type_{row_num}', '').strip()
                    vas_rate = get_decimal_or_none(request.POST.get(f'vas_rate_{row_num}'))

                    # Only create if rate_for, service_type, and rate all have values
                    if rate_for and vas_service_type and vas_rate is not None:
                        vas_count += 1
                        ValueAddedService.objects.create(
                            project_card=project_card,
                            rate_for=rate_for,
                            service_type_id=vas_service_type,
                            service_description=request.POST.get(f'vas_description_{row_num}', ''),
                            rate=vas_rate,
                            unit=request.POST.get(f'vas_unit_{row_num}', '') or 'per unit',
                            remarks=request.POST.get(f'vas_remarks_{row_num}', ''),
                        )

            # 7. Create Infrastructure Costs
            infra_count = 0
            for key in request.POST.keys():
                if key.startswith('infra_rate_for_'):
                    row_num = key.split('_')[-1]
                    rate_for = request.POST.get(f'infra_rate_for_{row_num}', '').strip()
                    amount = get_decimal_or_none(request.POST.get(f'infra_amount_{row_num}'))

                    if rate_for and amount is not None:
                        infra_count += 1
                        InfrastructureCost.objects.create(
                            project_card=project_card,
                            rate_for=rate_for,
                            cost_type_id=request.POST.get(f'infra_cost_type_{row_num}') or None,
                            description=request.POST.get(f'infra_description_{row_num}', ''),
                            amount=amount,
                            is_at_actual=f'infra_at_actual_{row_num}' in request.POST,
                            remarks=request.POST.get(f'infra_remarks_{row_num}', ''),
                        )
            
            messages.success(request, 
                f"✅ Project card updated successfully with {storage_count} storage rates, "
                f"{handling_count} handling rates, {transport_count} transport rates, "
                f"{vas_count} VAS, {infra_count} infra costs")
            
            return redirect('projects:project_detail', project_id=project_card.project.project_id)
            
        except Exception as e:
            messages.error(request, f"❌ Error updating project card: {str(e)}")
            import traceback
            print("=" * 80)
            print("ERROR UPDATING PROJECT CARD:")
            print(traceback.format_exc())
            print("=" * 80)
            raise
    
    # GET request - Show form with existing data
    # Serialize existing rates to JSON for JavaScript pre-population
    storage_rates_data = []
    for rate in project_card.storage_rates.all():
        storage_rates_data.append({
            'rate_for': rate.rate_for,
            'space_type': rate.space_type_id if rate.space_type else '',
            'flat_rate_per_unit': str(rate.flat_rate_per_unit) if rate.flat_rate_per_unit else '',
            'minimum_billable_area': str(rate.minimum_billable_area) if rate.minimum_billable_area else '',
            'monthly_billable_amount': str(rate.monthly_billable_amount) if rate.monthly_billable_amount else '',
        })

    handling_rates_data = []
    for rate in project_card.handling_rates.all():
        handling_rates_data.append({
            'rate_for': rate.rate_for,
            'direction': rate.direction if rate.direction else '',
            'channel': rate.channel_id if rate.channel else '',
            'base_type': rate.base_type_id if rate.base_type else '',
            'rate': str(rate.rate) if rate.rate else '',
        })

    transport_rates_data = []
    for rate in project_card.transport_rates.all():
        transport_rates_data.append({
            'rate_for': rate.rate_for,
            'vehicle_type': rate.vehicle_type if rate.vehicle_type else '',
            'rate': str(rate.rate) if rate.rate else '',
        })

    vas_services_data = []
    for service in project_card.vas_services.all():
        vas_services_data.append({
            'rate_for': service.rate_for,
            'service_type': service.service_type_id if service.service_type else '',
            'description': service.service_description,
            'unit': service.unit if service.unit else '',
            'rate': str(service.rate) if service.rate else '',
        })

    infrastructure_costs_data = []
    for cost in project_card.infrastructure_costs.all():
        infrastructure_costs_data.append({
            'rate_for': cost.rate_for,
            'cost_type': cost.cost_type_id if cost.cost_type else '',
            'description': cost.description,
            'monthly_amount': str(cost.amount) if cost.amount else '',
        })

    context = {
        'project_card': project_card,
        'storage_rates': project_card.storage_rates.all(),
        'handling_rates': project_card.handling_rates.all(),
        'transport_rates': project_card.transport_rates.all(),
        'vas_services': project_card.vas_services.all(),
        'infrastructure_costs': project_card.infrastructure_costs.all(),
        'return_url': get_return_url(request),

        # JSON-serialized rates for JavaScript pre-population
        'storage_rates_json': json.dumps(storage_rates_data),
        'handling_rates_json': json.dumps(handling_rates_data),
        'transport_rates_json': json.dumps(transport_rates_data),
        'vas_services_json': json.dumps(vas_services_data),
        'infrastructure_costs_json': json.dumps(infrastructure_costs_data),

        # Pass dropdown choices from master data (NO HARDCODING!)
        'storage_space_type_choices': json.dumps(get_dropdown_choices(StorageUnit)),
        'handling_direction_choices': json.dumps(get_dropdown_choices(HandlingDirection)),
        'handling_channel_choices': json.dumps(get_dropdown_choices(SalesChannel)),
        'handling_base_type_choices': json.dumps(get_dropdown_choices(HandlingBaseType)),
        'vehicle_types_json': json.dumps(get_dropdown_choices(VehicleType)),
        'vas_service_type_choices': json.dumps(get_dropdown_choices(VASServiceType)),
        'vas_unit_choices': json.dumps(get_dropdown_choices(VASUnit)),
        'infra_cost_type_choices': json.dumps(get_dropdown_choices(OperationalCostType)),
    }

    return render(request, 'operations/project_card_edit_unified.html', context)


# ==================== PROJECT CARD DELETE VIEW ====================

@login_required
def project_card_delete(request, project_card_id):
    """Delete project card - BACKOFFICE ONLY"""
    
    project_card = get_object_or_404(ProjectCard, id=project_card_id)
    
    # Check permissions - ONLY backoffice/admin/super_user can delete
    if request.user.role not in ['admin', 'super_user', 'backoffice']:
        messages.error(request, "You don't have permission to delete project cards.")
        return_url = get_return_url(request)
        if return_url:
            return redirect(return_url)
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        project_code = project_card.project.project_code
        project_card.delete()
        messages.success(request, f"✅ Project card for {project_code} deleted successfully.")
        
        # RETURN TO WHERE USER CAME FROM
        return_url = get_return_url(request)
        if return_url:
            return redirect(return_url)
        return redirect('operations:project_card_list')
    
    context = {
        'project_card': project_card,
        'return_url': get_return_url(request),
    }
    
    return render(request, 'operations/project_card_delete.html', context)


@login_required
def project_card_alerts_dashboard(request):
    """
    Dashboard showing all project card alerts.
    Only accessible to admin, super_user, and backoffice.
    """
    # Check permissions
    if request.user.role not in ['admin', 'super_user', 'backoffice']:
        messages.error(request, "You don't have permission to view alerts.")
        return redirect('accounts:dashboard')
    
    # Get filter parameters
    severity_filter = request.GET.get('severity', '')
    alert_type_filter = request.GET.get('alert_type', '')
    show_resolved = request.GET.get('show_resolved', '') == 'true'
    
    # Base queryset
    alerts = ProjectCardAlert.objects.select_related('project', 'project_card')
    
    if not show_resolved:
        alerts = alerts.filter(is_resolved=False)
    
    if severity_filter:
        alerts = alerts.filter(severity=severity_filter)
    
    if alert_type_filter:
        alerts = alerts.filter(alert_type=alert_type_filter)
    
    # Order by severity (critical first) then date
    severity_order = models.Case(
        models.When(severity='critical', then=0),
        models.When(severity='warning', then=1),
        models.When(severity='info', then=2),
        output_field=models.IntegerField(),
    )
    alerts = alerts.order_by(severity_order, '-created_at')
    
    # Stats — single aggregate query instead of 4 separate counts
    _unresolved = alerts.filter(is_resolved=False)
    severity_stats = _unresolved.aggregate(
        total_alerts=Count('id'),
        critical_count=Count('id', filter=models.Q(severity='critical')),
        warning_count=Count('id', filter=models.Q(severity='warning')),
        info_count=Count('id', filter=models.Q(severity='info')),
    )
    total_alerts = severity_stats['total_alerts']
    critical_count = severity_stats['critical_count']
    warning_count = severity_stats['warning_count']
    info_count = severity_stats['info_count']

    # Group by alert type — single query instead of N separate counts
    _type_counts = _unresolved.values('alert_type').annotate(
        count=Count('id')
    ).filter(count__gt=0)
    alert_type_dict = {at[0]: at[1] for at in ProjectCardAlert.ALERT_TYPES}
    alerts_by_type = {
        row['alert_type']: {
            'label': alert_type_dict.get(row['alert_type'], row['alert_type']),
            'count': row['count']
        }
        for row in _type_counts
    }
    
    context = {
        'alerts': alerts,
        'total_alerts': total_alerts,
        'critical_count': critical_count,
        'warning_count': warning_count,
        'info_count': info_count,
        'alerts_by_type': alerts_by_type,
        'severity_filter': severity_filter,
        'alert_type_filter': alert_type_filter,
        'show_resolved': show_resolved,
        'alert_types': ProjectCardAlert.ALERT_TYPES,
    }
    
    return render(request, 'operations/project_card_alerts.html', context)


@login_required
def resolve_project_card_alert(request, alert_id):
    """Mark an alert as resolved"""
    if request.user.role not in ['admin', 'super_user', 'backoffice']:
        messages.error(request, "You don't have permission to resolve alerts.")
        return redirect('accounts:dashboard')
    
    alert = get_object_or_404(ProjectCardAlert, id=alert_id)
    
    if request.method == 'POST':
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.save()
        
        messages.success(request, f"✅ Alert resolved for {alert.project.project_code}")
        return redirect('operations:project_card_alerts')
    
    return redirect('operations:project_card_alerts')


@login_required
def generate_alerts_now(request):
    """Manually trigger alert generation (admin only)"""
    if request.user.role not in ['admin', 'super_user']:
        messages.error(request, "You don't have permission to generate alerts.")
        return redirect('accounts:dashboard')
    
    from operations.alerts import generate_project_card_alerts
    
    result = generate_project_card_alerts()
    
    messages.success(
        request,
        f"✅ Alert generation complete! "
        f"Checked {result['total_projects_checked']} projects. "
        f"Generated {result['total_alerts']} alerts."
    )
    
    return redirect('operations:project_card_alerts')


@login_required
def project_card_alert_count(request):
    """
    API endpoint to get unresolved alert count
    """
    if request.user.role not in ['admin', 'backoffice']:
        return JsonResponse({'count': 0})
    
    alert_stats = ProjectCardAlert.objects.filter(is_resolved=False).aggregate(
        total=Count('id'),
        critical=Count('id', filter=models.Q(severity='critical')),
        warning=Count('id', filter=models.Q(severity='warning')),
        info=Count('id', filter=models.Q(severity='info')),
    )

    return JsonResponse({
        'count': alert_stats['total'],
        'critical': alert_stats['critical'],
        'warning': alert_stats['warning'],
        'info': alert_stats['info'],
    })


@login_required
def incomplete_project_cards_list(request):
    """
    Show list of projects with incomplete project cards.
    Only accessible to admin, super_user, and backoffice.
    """
    if request.user.role not in ['admin', 'super_user', 'backoffice']:
        messages.error(request, "You don't have permission to view this page.")
        return redirect('accounts:dashboard')

    from operations.incomplete_utils import get_incomplete_projects

    all_incomplete_projects = get_incomplete_projects()

    # Build dropdown from unfiltered list before applying filters
    all_missing_items = set()
    for item in all_incomplete_projects:
        all_missing_items.update(item['missing_items'])
    all_missing_items = sorted(list(all_missing_items))

    incomplete_projects = list(all_incomplete_projects)

    # Get search/filter parameters
    search_query = request.GET.get('search', '').strip()
    missing_item_filter = request.GET.get('missing_item', '').strip()

    # Apply filters
    if search_query:
        # Filter by project code (case-insensitive)
        incomplete_projects = [
            item for item in incomplete_projects
            if item['project'].project_code and search_query.lower() in item['project'].project_code.lower()
        ]

    if missing_item_filter:
        # Filter by specific missing item
        incomplete_projects = [
            item for item in incomplete_projects
            if missing_item_filter in item['missing_items']
        ]

    # Handle sorting
    sort_by = request.GET.get('sort', '-created_at')  # Default: newest first
    reverse = False

    if sort_by.startswith('-'):
        reverse = True
        sort_by = sort_by[1:]

    if sort_by in ['created_at', 'updated_at']:
        incomplete_projects = sorted(
            incomplete_projects,
            key=lambda x: getattr(x['project'], sort_by) or '',
            reverse=reverse
        )

    context = {
        'incomplete_projects': incomplete_projects,
        'total_count': len(incomplete_projects),
        'current_sort': request.GET.get('sort', '-created_at'),
        'search_query': search_query,
        'missing_item_filter': missing_item_filter,
        'all_missing_items': all_missing_items,
    }

    return render(request, 'operations/incomplete_project_cards.html', context)


@login_required
def incomplete_project_cards_count(request):
    """API endpoint for incomplete projects count"""
    if request.user.role not in ['admin', 'super_user', 'backoffice']:
        return JsonResponse({'count': 0})
    
    from operations.incomplete_utils import get_incomplete_projects
    
    # Use same function to ensure consistency
    incomplete_projects = get_incomplete_projects()
    count = len(incomplete_projects)
    
    return JsonResponse({'count': count})