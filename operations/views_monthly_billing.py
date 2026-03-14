"""
Monthly Billing Management Views
- AUTO-CALCULATION: Uses project card rates when available
- MANUAL ENTRY: Fallback when project card missing or user overrides
- OVERRIDE TRACKING: Tracks variance and requires reason for manual overrides
- ADHOC INTEGRATION: Shows and includes previous month's adhoc billings
- WORKFLOW: Draft → Submit → Controller → Finance → Lock

ROLES & PERMISSIONS:
- Operation Coordinator: Create/Edit/Submit for their projects only, NO margin visibility
- Operation Manager: Create/Edit/Submit for all projects (default view: their projects), sees margins
- Operation Controller: Review & Approve/Reject (1st level), sees margins
- Finance Manager: Final Approve/Reject & Lock (2nd level), sees margins
- Admin/Super User: Full access, sees margins
"""

import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count
from django.utils import timezone
from django.http import JsonResponse
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)

from .models import MonthlyBilling
from .models_monthly_billing_items import (
    MonthlyBillingStorageItem,
    MonthlyBillingHandlingItem,
    MonthlyBillingTransportItem,
    MonthlyBillingVASItem,
    MonthlyBillingInfrastructureItem
)
from projects.models import ProjectCode
from accounts.models import User
from dropdown_master_data.models import (
    StorageUnit, HandlingUnit, VehicleType,
    SalesChannel, HandlingBaseType, VASServiceType, VASUnit, OperationalCostType
)
from operations.models_projectcard import ProjectCard, StorageRate, StorageRateSlab, HandlingRate


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_user_projects(user):
    """
    Get projects accessible by user based on role.
    - Coordinator: Only their projects
    - Manager: All projects (but default filter to their projects)
    - Others: All projects
    """
    active_statuses = ['Active', 'Notice Period', 'Operation Not Started']
    
    if user.role == 'operation_coordinator':
        # Coordinators see only their projects
        return ProjectCode.objects.filter(
            operation_coordinator=user.get_full_name(),
            project_status__in=active_statuses
        ).order_by('client_name')
    else:
        # Managers, controllers, finance, admin see all
        return ProjectCode.objects.filter(
            project_status__in=active_statuses
        ).order_by('client_name')


def get_default_projects_filter(user):
    """
    Get default project filter for dashboard.
    - Coordinator: Their projects only
    - Manager: Their projects by default (can see all)
    - Others: All projects
    """
    if user.role in ['operation_coordinator', 'operation_manager']:
        return user.get_full_name()
    return None


def can_create_edit_billing(user, project):
    """
    Check if user can create/edit billing for a project.
    - Coordinator: Only their projects
    - Manager/Admin/Super User: All projects
    """
    if user.role in ['admin', 'super_user', 'operation_manager']:
        return True
    
    if user.role == 'operation_coordinator':
        return project.operation_coordinator == user.get_full_name()
    
    return False


def show_financials_to_user(user):
    """
    Check if user should see financial details (margins, costs).
    """
    return user.role in ['operation_manager', 'operation_controller', 'operation_coordinator', 'admin', 'super_user', 'finance_manager']


def create_billing_correction_notification(billing, editor, creator):
    """
    Create in-app notification when controller edits a billing.
    """
    from accounts.notifications import create_notification
    from django.urls import reverse

    if not creator:
        return

    try:
        # Create enterprise-grade notification
        create_notification(
            recipient=creator,
            notification_type='billing_corrected',
            title=f"Billing Corrected: {billing.project.project_code}",
            message=f"Your monthly billing for {billing.project.project_code} ({billing.service_month.strftime('%B %Y')}) was corrected by {editor.get_full_name()}. Please review the updated entry.",
            priority='high',
            severity='warning',
            category='billing',
            action_url=reverse('operations:monthly_billing_detail', args=[billing.id]),
            action_label='View Billing',
            monthly_billing=billing,
            project=billing.project,
            metadata={
                'editor': editor.get_full_name(),
                'editor_id': editor.id,
                'service_month': billing.service_month.strftime('%Y-%m-%d')
            },
            group_key=f'billing_{billing.id}'
        )
    except Exception as e:
        logger.warning(f"Failed to create billing correction notification: {e}")


def get_billing_month_from_request(request, default=None):
    """
    Extract billing month from request, return as date object.
    """
    month_str = request.GET.get('month') or request.POST.get('month')

    if month_str:
        try:
            # Handle both 'YYYY-MM' and 'YYYY-MM-DD' formats
            if len(month_str) == 7:  # YYYY-MM
                return date.fromisoformat(month_str + '-01')
            else:  # YYYY-MM-DD
                return date.fromisoformat(month_str).replace(day=1)
        except (ValueError, AttributeError):
            pass

    # Default to last month
    if default:
        return default

    return (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)


def get_month_options(count=12):
    """
    Generate month options for dropdown based on existing billing records.
    Falls back to last N months if no billing records exist.
    """
    # Get unique service months from existing billing records (filter out NULLs)
    existing_months = MonthlyBilling.objects.filter(
        service_month__isnull=False
    ).values_list('service_month', flat=True).distinct().order_by('-service_month')

    if existing_months:
        # Use existing billing months (filter out any None values)
        options = []
        for month in existing_months:
            if month:  # Extra safety check
                options.append({
                    'value': month.strftime('%Y-%m'),
                    'label': month.strftime('%B %Y')
                })
        return options
    else:
        # Fallback: Generate last N months if no billing records exist
        options = []
        for i in range(count):
            month = (date.today().replace(day=1) - relativedelta(months=i))
            options.append({
                'value': month.strftime('%Y-%m'),
                'label': month.strftime('%B %Y')
            })
        return options


def get_dropdown_choices(model_class):
    """Get active dropdown choices from master data as JSON"""
    return json.dumps([
        {'code': item.code, 'label': item.label}
        for item in model_class.objects.filter(is_active=True).order_by('display_order', 'code')
    ])


def _pair_transport_items(transport_qs):
    """
    Pair transport items (side='client' and side='vendor') by row_order
    into a list of dicts for edit mode pre-population.
    """
    by_row = {}
    for item in transport_qs.order_by('row_order', 'id'):
        row = by_row.setdefault(item.row_order, {'client': None, 'vendor': None, 'remarks': item.remarks})
        row[item.side] = item
    return list(by_row.values())


def safe_decimal_update(obj, field_name, post_data, default=None):
    """
    Safely update a Decimal field only if valid data is provided.
    Preserves existing value if POST data is empty/missing.

    Args:
        obj: The model instance to update
        field_name: Name of the field to update
        post_data: request.POST data
        default: Default value if field doesn't exist (optional)
    """
    value = post_data.get(field_name)
    if value is not None and value != '':
        try:
            setattr(obj, field_name, Decimal(value))
        except (ValueError, InvalidOperation):
            # Log warning but preserve existing value
            logger.warning(f"Invalid decimal value for {field_name}: '{value}' - keeping existing value")
    # If value is None or empty string, existing value is preserved


def safe_int_update(obj, field_name, post_data, default=None):
    """
    Safely update an Integer field only if valid data is provided.
    Preserves existing value if POST data is empty/missing.
    """
    value = post_data.get(field_name)
    if value is not None and value != '':
        try:
            setattr(obj, field_name, int(value))
        except (ValueError, TypeError):
            logger.warning(f"Invalid integer value for {field_name}: '{value}' - keeping existing value")


def safe_fk_update(obj, field_name, post_data):
    """
    Safely update a ForeignKey field only if valid data is provided.
    Preserves existing value if POST data is empty/missing.
    Sets to None only if explicitly cleared by user.
    """
    value = post_data.get(field_name)
    if value:  # Truthy value - update
        setattr(obj, field_name, value)
    elif value == '':  # Empty string - user explicitly cleared it
        setattr(obj, field_name, None)
    # If None (key not in POST), preserve existing value


def safe_string_update(obj, field_name, post_data):
    """
    Safely update a string field.
    Empty strings are treated as intentional clearing.
    """
    value = post_data.get(field_name)
    if value is not None:  # Key exists in POST (even if empty string)
        setattr(obj, field_name, value)
    # If None (key not in POST), preserve existing value


# ============================================================================
# AUTO-CALCULATION FUNCTIONS
# ============================================================================

def calculate_slab_storage(total_space, slabs):
    """
    Calculate storage cost using slab rates from StorageRateSlab model.
    Slabs are ordered by min_quantity and applied progressively.
    
    Args:
        total_space: Total space to calculate cost for
        slabs: QuerySet of StorageRateSlab objects
    
    Returns:
        Decimal: Total calculated cost
    """
    if not slabs.exists():
        return Decimal('0')
     
    total_cost = Decimal('0')
    remaining_space = Decimal(str(total_space))
    
    # Order slabs by min_quantity
    ordered_slabs = slabs.order_by('min_quantity')
    
    for slab in ordered_slabs:
        if remaining_space <= 0:
            break
        
        min_qty = slab.min_quantity or Decimal('0')
        max_qty = slab.max_quantity
        rate = slab.rate_per_unit or Decimal('0')
        
        if max_qty:
            # Slab has upper limit
            slab_capacity = max_qty - min_qty
            space_in_slab = min(remaining_space, slab_capacity)
        else:
            # Last slab (no upper limit) - all remaining space
            space_in_slab = remaining_space
        
        # Calculate cost for this slab
        total_cost += space_in_slab * rate
        remaining_space -= space_in_slab
    
    return total_cost


def get_applicable_storage_slab(total_space, slabs):
    """
    Get the applicable slab for given space quantity.
    Returns: dict with slab info or None
    """
    if not slabs.exists():
        return None
    
    ordered_slabs = slabs.order_by('min_quantity')
    
    for slab in ordered_slabs:
        min_qty = slab.min_quantity or Decimal('0')
        max_qty = slab.max_quantity
        
        if max_qty:
            if min_qty <= total_space <= max_qty:
                return {
                    'slab': slab,
                    'min': min_qty,
                    'max': max_qty,
                    'rate': slab.rate_per_unit,
                    'is_range': True
                }
        else:
            # Last slab (no upper limit)
            if total_space >= min_qty:
                return {
                    'slab': slab,
                    'min': min_qty,
                    'max': None,
                    'rate': slab.rate_per_unit,
                    'is_range': False
                }
    
    return None


def get_storage_calculation_context(billing, project_card):
    """
    Get complete storage calculation context for template.
    Returns dict with project card rates, slabs, and calculated values.
    """
    if not project_card:
        return None
    
    total_space = (billing.storage_min_space or Decimal('0')) + \
                  (billing.storage_additional_space or Decimal('0'))
    
    context = {
        'has_project_card': True,
        'total_space': total_space,
        'client': {},
        'vendor': {}
    }
    
    # CLIENT STORAGE
    client_slabs = StorageRateSlab.objects.filter(
        project_card=project_card,
        rate_for='client'
    )
    
    if client_slabs.exists():
        applicable = get_applicable_storage_slab(total_space, client_slabs)
        if applicable:
            calculated_cost = calculate_slab_storage(total_space, client_slabs)
            context['client'] = {
                'has_slab': True,
                'applicable_slab': applicable,
                'all_slabs': list(client_slabs.order_by('min_quantity').values(
                    'min_quantity', 'max_quantity', 'rate_per_unit'
                )),
                'calculated_rate': applicable['rate'],
                'calculated_cost': calculated_cost,
                'space_type': applicable['slab'].space_type_id,
                'minimum_billable_area': applicable['slab'].min_quantity,  # ADD THIS
            }
    else:
        client_storage = StorageRate.objects.filter(
            project_card=project_card,
            rate_for='client'
        ).first()
        
        if client_storage:
            if client_storage.flat_rate_per_unit:
                context['client'] = {
                    'has_slab': False,
                    'flat_rate': client_storage.flat_rate_per_unit,
                    'calculated_cost': total_space * client_storage.flat_rate_per_unit,
                    'space_type': client_storage.space_type_id,
                    'minimum_billable_area': client_storage.minimum_billable_area,  # ADD THIS
                }
            elif client_storage.monthly_billable_amount:
                context['client'] = {
                    'has_slab': False,
                    'fixed_monthly': client_storage.monthly_billable_amount,
                    'calculated_cost': client_storage.monthly_billable_amount,
                    'space_type': client_storage.space_type_id,
                    'minimum_billable_area': client_storage.minimum_billable_area,  # ADD THIS
                }
            
            # ADD SAAS CHARGE IF EXISTS
            if client_storage.saas_monthly_charge:
                context['client']['saas_charge'] = client_storage.saas_monthly_charge
    
    # VENDOR STORAGE (SAME PATTERN)
    vendor_slabs = StorageRateSlab.objects.filter(
        project_card=project_card,
        rate_for='vendor'
    )
    
    if vendor_slabs.exists():
        applicable = get_applicable_storage_slab(total_space, vendor_slabs)
        if applicable:
            calculated_cost = calculate_slab_storage(total_space, vendor_slabs)
            context['vendor'] = {
                'has_slab': True,
                'applicable_slab': applicable,
                'all_slabs': list(vendor_slabs.order_by('min_quantity').values(
                    'min_quantity', 'max_quantity', 'rate_per_unit'
                )),
                'calculated_rate': applicable['rate'],
                'calculated_cost': calculated_cost,
                'space_type': applicable['slab'].space_type_id,
                'minimum_billable_area': applicable['slab'].min_quantity,  # ADD THIS
            }
    else:
        vendor_storage = StorageRate.objects.filter(
            project_card=project_card,
            rate_for='vendor'
        ).first()
        
        if vendor_storage:
            if vendor_storage.flat_rate_per_unit:
                context['vendor'] = {
                    'has_slab': False,
                    'flat_rate': vendor_storage.flat_rate_per_unit,
                    'calculated_cost': total_space * vendor_storage.flat_rate_per_unit,
                    'space_type': vendor_storage.space_type_id,
                    'minimum_billable_area': vendor_storage.minimum_billable_area,  # ADD THIS
                }
            elif vendor_storage.monthly_billable_amount:
                context['vendor'] = {
                    'has_slab': False,
                    'fixed_monthly': vendor_storage.monthly_billable_amount,
                    'calculated_cost': vendor_storage.monthly_billable_amount,
                    'space_type': vendor_storage.space_type_id,
                    'minimum_billable_area': vendor_storage.minimum_billable_area,  # ADD THIS
                }
            
            # ADD SAAS CHARGE IF EXISTS
            if vendor_storage.saas_monthly_charge:
                context['vendor']['saas_charge'] = vendor_storage.saas_monthly_charge
    
    return context


def get_handling_calculation_context(billing, project_card, direction):
    """
    Get handling calculation context (IN or OUT).
    """
    if not project_card:
        return None
    
    quantity = billing.handling_in_quantity if direction == 'inbound' else billing.handling_out_quantity
    quantity = quantity or Decimal('0')
    
    context = {
        'has_project_card': True,
        'quantity': quantity,
        'direction': direction,
        'client': {},
        'vendor': {}
    }
    
    # CLIENT HANDLING
    client_handling = HandlingRate.objects.filter(
        project_card=project_card,
        rate_for='client',
        direction=direction
    ).first()
    
    if client_handling and client_handling.rate:
        context['client'] = {
            'rate': client_handling.rate,
            'calculated_cost': quantity * client_handling.rate,
            'base_type': client_handling.base_type_id,
            'channel': client_handling.channel_id,
        }
    
    # VENDOR HANDLING
    vendor_handling = HandlingRate.objects.filter(
        project_card=project_card,
        rate_for='vendor',
        direction=direction
    ).first()
    
    if vendor_handling and vendor_handling.rate:
        context['vendor'] = {
            'rate': vendor_handling.rate,
            'calculated_cost': quantity * vendor_handling.rate,
            'base_type': vendor_handling.base_type_id,
            'channel': vendor_handling.channel_id,
        }

    return context


def get_adhoc_billings_for_month(project, service_month):
    """
    Get adhoc billings from the service month for this project.
    """
    from operations.models_adhoc import AdhocBillingEntry
    
    # Get adhoc billings from the service month
    adhoc_entries = AdhocBillingEntry.objects.filter(
        project=project,
        service_month=service_month
    ).select_related('project', 'created_by').prefetch_related('line_items', 'attachments')
    
    return adhoc_entries


def get_project_card_for_project(project):
    """
    Get active project card for a project if exists.
    
    Args:
        project: ProjectCode object
    
    Returns:
        ProjectCard or None
    """
    # First try to get active card
    card = ProjectCard.objects.filter(
        project=project,
        is_active=True
    ).first()
    
    # Fallback: get any card (latest version)
    if not card:
        card = ProjectCard.objects.filter(
            project=project
        ).order_by('-version', '-created_at').first()
    
    return card


def calculate_storage_cost(billing, project_card):
    """
    Calculate storage costs from project card.
    Uses StorageRateSlab if slabs exist, otherwise uses flat rates from StorageRate.
    
    Updates billing object with:
    - vendor_storage_rate, vendor_storage_cost
    - client_storage_rate, client_storage_billing
    - storage_unit_type (if not already set)
    
    Returns:
        bool: True if any calculation was performed
    """
    if not project_card:
        return False
    
    total_space = (billing.storage_min_space or Decimal('0')) + \
                  (billing.storage_additional_space or Decimal('0'))
    
    if total_space <= 0:
        return False
    
    calculated = False
    
    # ==================== VENDOR STORAGE ====================
    # Check if slab-based rates exist for vendor
    vendor_slabs = StorageRateSlab.objects.filter(
        project_card=project_card,
        rate_for='vendor'
    )
    
    if vendor_slabs.exists():
        # Use slab-based calculation
        vendor_cost = calculate_slab_storage(total_space, vendor_slabs)
        # For slab-based, we don't have a single rate, so leave rate as None or average
        billing.vendor_storage_rate = None
        billing.vendor_storage_cost = vendor_cost
        
        # Set storage unit type from first slab if not already set
        if not billing.storage_unit_type_id:
            first_slab = vendor_slabs.first()
            if first_slab and first_slab.space_type_id:
                billing.storage_unit_type_id = first_slab.space_type_id
        
        calculated = True
    else:
        # Use flat rate from StorageRate
        vendor_storage = StorageRate.objects.filter(
            project_card=project_card,
            rate_for='vendor'
        ).first()
        
        if vendor_storage:
            if vendor_storage.monthly_billable_amount:
                # Fixed monthly amount
                billing.vendor_storage_rate = None
                billing.vendor_storage_cost = vendor_storage.monthly_billable_amount
            elif vendor_storage.flat_rate_per_unit:
                # Rate per unit calculation
                billing.vendor_storage_rate = vendor_storage.flat_rate_per_unit
                billing.vendor_storage_cost = total_space * vendor_storage.flat_rate_per_unit
            else:
                billing.vendor_storage_rate = Decimal('0')
                billing.vendor_storage_cost = Decimal('0')
            
            # Set storage unit type if not already set
            if not billing.storage_unit_type_id and vendor_storage.space_type_id:
                billing.storage_unit_type_id = vendor_storage.space_type_id
            
            calculated = True
    
    # ==================== CLIENT STORAGE ====================
    # Check if slab-based rates exist for client
    client_slabs = StorageRateSlab.objects.filter(
        project_card=project_card,
        rate_for='client'
    )
    
    if client_slabs.exists():
        # Use slab-based calculation
        client_cost = calculate_slab_storage(total_space, client_slabs)
        billing.client_storage_rate = None
        billing.client_storage_billing = client_cost
        
        # Set storage unit type from first slab if not already set
        if not billing.storage_unit_type_id:
            first_slab = client_slabs.first()
            if first_slab and first_slab.space_type_id:
                billing.storage_unit_type_id = first_slab.space_type_id
        
        calculated = True
    else:
        # Use flat rate from StorageRate
        client_storage = StorageRate.objects.filter(
            project_card=project_card,
            rate_for='client'
        ).first()
        
        if client_storage:
            if client_storage.monthly_billable_amount:
                # Fixed monthly amount
                billing.client_storage_rate = None
                billing.client_storage_billing = client_storage.monthly_billable_amount
            elif client_storage.flat_rate_per_unit:
                # Rate per unit calculation
                billing.client_storage_rate = client_storage.flat_rate_per_unit
                billing.client_storage_billing = total_space * client_storage.flat_rate_per_unit
            else:
                billing.client_storage_rate = Decimal('0')
                billing.client_storage_billing = Decimal('0')
            
            # Set storage unit type if not already set
            if not billing.storage_unit_type_id and client_storage.space_type_id:
                billing.storage_unit_type_id = client_storage.space_type_id
            
            calculated = True
    
    return calculated


def calculate_handling_cost(billing, project_card, direction):
    """
    Calculate handling costs (IN or OUT) from project card.
    
    Args:
        billing: MonthlyBilling object to update
        project_card: ProjectCard object with handling rates
        direction: 'inbound' or 'outbound'
    
    Updates billing object with:
    - vendor_handling_in/out_rate, vendor_handling_in/out_cost
    - client_handling_in/out_rate, client_handling_in/out_billing
    - handling_in/out_unit_type (if not already set)
    
    Returns:
        bool: True if any calculation was performed
    """
    if not project_card:
        return False
    
    # Get handling rates for this direction
    vendor_handling = HandlingRate.objects.filter(
        project_card=project_card,
        rate_for='vendor',
        direction=direction
    ).first()
    
    client_handling = HandlingRate.objects.filter(
        project_card=project_card,
        rate_for='client',
        direction=direction
    ).first()
    
    calculated = False
    
    if direction == 'inbound':
        quantity = billing.handling_in_quantity or Decimal('0')
        
        if vendor_handling and vendor_handling.rate:
            billing.vendor_handling_in_rate = vendor_handling.rate
            billing.vendor_handling_in_cost = quantity * vendor_handling.rate
            
            # Set unit type from project card's base_type if not already set
            if not billing.handling_in_unit_type_id and vendor_handling.base_type_id:
                # Map base_type to HandlingUnit code
                base_type = str(vendor_handling.base_type_id).lower()
                if 'box' in base_type:
                    billing.handling_in_unit_type_id = 'boxes'
                elif 'pallet' in base_type:
                    billing.handling_in_unit_type_id = 'pallets'
                elif 'ton' in base_type:
                    billing.handling_in_unit_type_id = 'tons'
                elif 'kg' in base_type:
                    billing.handling_in_unit_type_id = 'kgs'
                else:
                    billing.handling_in_unit_type_id = 'pieces'
            
            calculated = True
        
        if client_handling and client_handling.rate:
            billing.client_handling_in_rate = client_handling.rate
            billing.client_handling_in_billing = quantity * client_handling.rate
            calculated = True
    
    else:  # outbound
        quantity = billing.handling_out_quantity or Decimal('0')
        
        if vendor_handling and vendor_handling.rate:
            billing.vendor_handling_out_rate = vendor_handling.rate
            billing.vendor_handling_out_cost = quantity * vendor_handling.rate
            
            # Set unit type from project card's base_type if not already set
            if not billing.handling_out_unit_type_id and vendor_handling.base_type_id:
                base_type = str(vendor_handling.base_type_id).lower()
                if 'box' in base_type:
                    billing.handling_out_unit_type_id = 'boxes'
                elif 'pallet' in base_type:
                    billing.handling_out_unit_type_id = 'pallets'
                elif 'ton' in base_type:
                    billing.handling_out_unit_type_id = 'tons'
                elif 'kg' in base_type:
                    billing.handling_out_unit_type_id = 'kgs'
                else:
                    billing.handling_out_unit_type_id = 'pieces'
            
            calculated = True
        
        if client_handling and client_handling.rate:
            billing.client_handling_out_rate = client_handling.rate
            billing.client_handling_out_billing = quantity * client_handling.rate
            calculated = True
    
    return calculated


def auto_calculate_rates(billing, force=False):
    """
    Auto-calculate costs from project card.
    
    This function:
    1. Finds the active project card for the billing's project
    2. Calculates storage costs (slab-based or flat rate)
    3. Calculates handling IN costs
    4. Calculates handling OUT costs
    5. Transport and misc are always manual entry
    
    Args:
        billing: MonthlyBilling object to update
        force: If True, recalculate even if already calculated
    
    Returns:
        tuple: (success: bool, message: str)
    """
    project = billing.project
    
    # Get active project card for this project
    project_card = ProjectCard.objects.filter(
        project=project,
        is_active=True
    ).first()
    
    # Fallback: if no active card, try to get any card for this project
    if not project_card:
        project_card = ProjectCard.objects.filter(
            project=project
        ).order_by('-version', '-created_at').first()
    
    if not project_card:
        return False, "Project card not found. Please enter costs manually."
    
    # Store reference to project card used
    billing.project_card_used = project_card
    
    # Track which calculations were performed
    storage_calculated = calculate_storage_cost(billing, project_card)
    handling_in_calculated = calculate_handling_cost(billing, project_card, 'inbound')
    handling_out_calculated = calculate_handling_cost(billing, project_card, 'outbound')
    
    # Transport and misc are always manual entry (not in project card)
    
    if storage_calculated or handling_in_calculated or handling_out_calculated:
        results = []
        if storage_calculated:
            results.append("storage")
        if handling_in_calculated:
            results.append("handling IN")
        if handling_out_calculated:
            results.append("handling OUT")
        
        return True, f"Auto-calculated: {', '.join(results)} from project card."
    else:
        return False, "Project card found but has no rate data. Please enter costs manually."


# ============================================================================
# DASHBOARD VIEW
# ============================================================================

@login_required
def billing_dashboard(request):
    """
    Dashboard showing all billings grouped by status.
    - Coordinators see their billings only, NO margins
    - Managers see their billings by default, can see all, WITH margins
    - Controllers/Finance see all, WITH margins
    
    Note: Dashboard filters by SERVICE MONTH (when services were provided)
    """
    user = request.user
    
    # Permission check
    allowed_roles = ['operation_coordinator', 'operation_manager', 'operation_controller',
                     'finance_manager', 'admin', 'super_user', 'director']
    if user.role not in allowed_roles:
        messages.warning(request, "You don't have access to monthly billing.")
        return redirect('accounts:dashboard')
    
    # Get service month from request (when services were provided)
    service_month = get_billing_month_from_request(request)
    selected_month = service_month.strftime('%Y-%m')
    
    # Base queryset
    billings = MonthlyBilling.objects.select_related(
        'project', 'status', 'created_by',
        'controller_reviewed_by', 'finance_reviewed_by',
        'storage_unit_type', 'handling_in_unit_type', 'handling_out_unit_type'
    ).filter(service_month=service_month)
    
    # Get all active projects for this period
    active_statuses = ['Active', 'Notice Period', 'Operation Not Started']
    all_projects = ProjectCode.objects.filter(project_status__in=active_statuses)
    
    # Filter by coordinator (for coordinators: mandatory, for managers: optional)
    coordinator_filter = request.GET.get('coordinator', '')
    manager_view = request.GET.get('view', '')  # 'all' or '' (my projects)

    if user.role == 'operation_coordinator':
        # Coordinators ONLY see their projects
        user_name = user.get_full_name()
        billings = billings.filter(project__operation_coordinator=user_name)
        all_projects = all_projects.filter(operation_coordinator=user_name)
        coordinator_filter = user_name  # Lock filter to their name
    elif user.role == 'operation_manager' and manager_view != 'all':
        # Managers see their own projects by default
        user_name = user.get_full_name()
        billings = billings.filter(project__operation_coordinator=user_name)
        all_projects = all_projects.filter(operation_coordinator=user_name)
        if coordinator_filter:
            # Additional coordinator filter within my projects (not applicable, but safe)
            billings = billings.filter(project__operation_coordinator=coordinator_filter)
            all_projects = all_projects.filter(operation_coordinator=coordinator_filter)
    elif coordinator_filter:
        # Managers (all view) / controllers / others can filter by coordinator
        billings = billings.filter(project__operation_coordinator=coordinator_filter)
        all_projects = all_projects.filter(operation_coordinator=coordinator_filter)
    
    # Filter by status if requested
    status_filter = request.GET.get('status', '')
    if status_filter:
        billings = billings.filter(status__code=status_filter)

    # Universal search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        billings = billings.filter(
            Q(project__project_code__icontains=search_query) |
            Q(project__client_name__icontains=search_query) |
            Q(project__vendor_name__icontains=search_query) |
            Q(project__location__icontains=search_query) |
            Q(project__operation_coordinator__icontains=search_query) |
            Q(id__icontains=search_query)  # Billing ID/number
        )

    # Get status counts (before status filter)
    status_counts_qs = MonthlyBilling.objects.filter(service_month=service_month)
    if user.role == 'operation_coordinator':
        status_counts_qs = status_counts_qs.filter(project__operation_coordinator=user.get_full_name())
    elif user.role == 'operation_manager' and manager_view != 'all':
        status_counts_qs = status_counts_qs.filter(project__operation_coordinator=user.get_full_name())
    elif coordinator_filter:
        status_counts_qs = status_counts_qs.filter(project__operation_coordinator=coordinator_filter)
    
    # Count by status
    total_count = status_counts_qs.count()
    completed_count = status_counts_qs.filter(status__code='approved').count()
    pending_count = status_counts_qs.filter(status__code='draft').count()
    submitted_count = status_counts_qs.filter(
        status__code__in=['pending_controller', 'pending_finance']
    ).count()
    rejected_count = status_counts_qs.filter(
        status__code__in=['controller_rejected', 'finance_rejected']
    ).count()
    
    # Projects without billing for this month
    projects_with_billing = billings.values_list('project_id', flat=True)
    projects_without_billing = all_projects.exclude(
        project_id__in=projects_with_billing
    ).order_by('client_name', 'project_code')
    
    # Get all coordinators for filter dropdown
    # Show for: controllers, finance, admin, director, and managers in "All Projects" view
    all_coordinators = []
    show_coordinator_filter = (
        user.role != 'operation_coordinator' and
        not (user.role == 'operation_manager' and manager_view != 'all')
    )
    if show_coordinator_filter:
        all_coordinators = ProjectCode.objects.filter(
            project_status__in=active_statuses
        ).values_list('operation_coordinator', flat=True).distinct().order_by('operation_coordinator')
        all_coordinators = [c for c in all_coordinators if c]  # Remove None/empty
    
    # Financial summary (only for roles that can see margins)
    show_financials = show_financials_to_user(user)
    
    if show_financials:
        financial_stats = billings.aggregate(
            total_vendor=Sum('vendor_total'),
            total_client=Sum('client_total'),
            total_margin=Sum('margin_amount')
        )
        total_vendor_cost = financial_stats['total_vendor'] or Decimal('0')
        total_client_billing = financial_stats['total_client'] or Decimal('0')
        total_margin = financial_stats['total_margin'] or Decimal('0')

        # Calculate overall margin percentage
        if total_client_billing > 0:
            total_margin_percentage = (total_margin / total_client_billing) * 100
        else:
            total_margin_percentage = Decimal('0')
    else:
        total_vendor_cost = Decimal('0')
        total_client_billing = Decimal('0')
        total_margin = Decimal('0')
        total_margin_percentage = Decimal('0')
    
    # Order billings by client name alphabetically
    billings = billings.order_by('project__client_name', 'project__project_code')
    
    # Month options for dropdown
    month_options = get_month_options(12)
    
    # Check if user can create billings
    can_create = user.role in ['operation_coordinator', 'operation_manager', 'admin', 'super_user']
    
    context = {
        # Filters
        'selected_month': selected_month,
        'service_month': service_month,  # Changed from billing_month
        'billing_month': service_month,  # Keep for backward compatibility in templates
        'status_filter': status_filter,
        'coordinator_filter': coordinator_filter,
        'search_query': search_query,
        'month_options': month_options,
        'all_coordinators': all_coordinators,
        
        # Counts
        'total_projects': total_count,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'submitted_count': submitted_count,
        'rejected_count': rejected_count,
        
        # Data
        'billing_entries': billings,
        'projects_without_billing': projects_without_billing,
        
        # Financials
        'show_financials': show_financials,
        'total_vendor_cost': total_vendor_cost,
        'total_client_billing': total_client_billing,
        'total_margin': total_margin,
        'total_margin_percentage': total_margin_percentage,
        
        # Permissions
        'can_create': can_create,
        'is_manager': user.role == 'operation_manager',
        'manager_view': manager_view,
    }
    
    return render(request, 'operations/monthly_billing_dashboard.html', context)


# ============================================================================
# CREATE BILLING
# ============================================================================

@login_required
def billing_create(request, project_id):
    """
    Create new monthly billing for a specific project.
    AUTO-CALCULATES from project card when available.
    MANUAL ENTRY when project card missing.
    
    Note: service_month = when services were provided (usually last month)
          billing_month = when invoice is being sent (usually current month)
    """
    user = request.user
    
    # Permission check - only coordinators, managers, admin can create
    allowed_roles = ['operation_coordinator', 'operation_manager', 'admin', 'super_user']
    if user.role not in allowed_roles:
        messages.error(request, "You don't have permission to create billings.")
        return redirect('operations:monthly_billing_dashboard')
    
    # Get project
    project = get_object_or_404(ProjectCode, project_id=project_id)
    
    # Check if user can create for this project
    if not can_create_edit_billing(user, project):
        messages.error(request, "You don't have access to this project.")
        return redirect('operations:monthly_billing_dashboard')
    
    # Get service month from request (when services were provided)
    # Default: last month (since we typically bill in current month for last month's services)
    service_month = get_billing_month_from_request(request)
    
    # Billing month defaults to current month (when invoice is being created)
    billing_month = datetime.now().date().replace(day=1)
    
    # Get project card for auto-calculation
    project_card = get_project_card_for_project(project)
    
    # Get adhoc billings for this service month
    adhoc_entries = get_adhoc_billings_for_month(project, service_month)
    
    if request.method == 'POST':

        try:
            # Get service and billing months (YYYY-MM format from month input)
            service_month = request.POST.get('service_month')
            billing_month = request.POST.get('billing_month')

            # Convert to first day of month
            if service_month:
                service_month = datetime.strptime(service_month, '%Y-%m').date().replace(day=1)
            if billing_month:
                billing_month = datetime.strptime(billing_month, '%Y-%m').date().replace(day=1)

            # Check for duplicate on service_month (one billing per project per service month)
            existing = MonthlyBilling.objects.filter(
                project=project,
                service_month=service_month
            ).first()
            if existing:
                messages.error(request, f"Billing for {project.client_name} - service month {service_month.strftime('%B %Y')} already exists!")
                return redirect('operations:monthly_billing_detail', billing_id=existing.id)

            # Create billing object
            billing = MonthlyBilling(
                project=project,
                service_month=service_month,
                billing_month=billing_month,
                created_by=user,
                project_card_used=project_card
            )
            
            # Save billing first (needed for FK relationships)
            billing.save()

            # STORAGE SECTION - Process multiple line items
            storage_counter = 1  # JavaScript counters start at 1
            while True:
                # Check if this row exists in POST data
                client_min_key = f'storage_{storage_counter}_client_min_space'
                if client_min_key not in request.POST:
                    break

                # Get pricing type (flat, slab, or lumpsum)
                pricing_type = request.POST.get(f'storage_{storage_counter}_pricing_type', 'flat')

                # Create storage item
                storage_item = MonthlyBillingStorageItem(
                    monthly_billing=billing,
                    row_order=storage_counter,
                    pricing_type=pricing_type,
                    remarks=request.POST.get(f'storage_{storage_counter}_remarks', '')
                )

                # Client side
                storage_item.client_min_space = Decimal(request.POST.get(f'storage_{storage_counter}_client_min_space', 0) or 0)
                storage_item.client_additional_space = Decimal(request.POST.get(f'storage_{storage_counter}_client_additional_space', 0) or 0)
                storage_item.client_storage_unit_type_id = request.POST.get(f'storage_{storage_counter}_client_unit_type') or None
                storage_item.client_storage_days = int(request.POST.get(f'storage_{storage_counter}_client_days', 0) or 0)
                storage_item.client_rate = Decimal(request.POST.get(f'storage_{storage_counter}_client_rate', 0) or 0) if request.POST.get(f'storage_{storage_counter}_client_rate') else None
                storage_item.client_billing = Decimal(request.POST.get(f'storage_{storage_counter}_client_total', 0) or 0)

                # Lumpsum amount (if pricing_type='lumpsum')
                storage_item.client_lumpsum_amount = Decimal(request.POST.get(f'storage_{storage_counter}_client_lumpsum', 0) or 0) if request.POST.get(f'storage_{storage_counter}_client_lumpsum') else None

                # Vendor side
                storage_item.vendor_min_space = Decimal(request.POST.get(f'storage_{storage_counter}_vendor_min_space', 0) or 0)
                storage_item.vendor_additional_space = Decimal(request.POST.get(f'storage_{storage_counter}_vendor_additional_space', 0) or 0)
                storage_item.vendor_storage_unit_type_id = request.POST.get(f'storage_{storage_counter}_vendor_unit_type') or None
                storage_item.vendor_storage_days = int(request.POST.get(f'storage_{storage_counter}_vendor_days', 0) or 0)
                storage_item.vendor_rate = Decimal(request.POST.get(f'storage_{storage_counter}_vendor_rate', 0) or 0) if request.POST.get(f'storage_{storage_counter}_vendor_rate') else None
                storage_item.vendor_cost = Decimal(request.POST.get(f'storage_{storage_counter}_vendor_total', 0) or 0)

                # Lumpsum amount (if pricing_type='lumpsum')
                storage_item.vendor_lumpsum_amount = Decimal(request.POST.get(f'storage_{storage_counter}_vendor_lumpsum', 0) or 0) if request.POST.get(f'storage_{storage_counter}_vendor_lumpsum') else None

                storage_item.save()

                # If pricing_type is 'slab', save slabs
                if pricing_type == 'slab':
                    # Process client slabs
                    slab_counter = 1
                    while True:
                        min_key = f'storage_slab_{storage_counter}_client_{slab_counter}_min'
                        if min_key not in request.POST:
                            break

                        from operations.models_monthly_billing_items import MonthlyBillingStorageSlab
                        slab = MonthlyBillingStorageSlab(
                            storage_item=storage_item,
                            side='client',
                            row_order=slab_counter,
                            min_quantity=Decimal(request.POST.get(min_key, 0) or 0),
                            max_quantity=Decimal(request.POST.get(f'storage_slab_{storage_counter}_client_{slab_counter}_max', 0) or 0) if request.POST.get(f'storage_slab_{storage_counter}_client_{slab_counter}_max') else None,
                            rate_per_unit=Decimal(request.POST.get(f'storage_slab_{storage_counter}_client_{slab_counter}_rate', 0) or 0),
                            remarks=request.POST.get(f'storage_slab_{storage_counter}_client_{slab_counter}_remarks', '')
                        )
                        slab.save()
                        slab_counter += 1

                    # Process vendor slabs
                    slab_counter = 1
                    while True:
                        min_key = f'storage_slab_{storage_counter}_vendor_{slab_counter}_min'
                        if min_key not in request.POST:
                            break

                        from operations.models_monthly_billing_items import MonthlyBillingStorageSlab
                        slab = MonthlyBillingStorageSlab(
                            storage_item=storage_item,
                            side='vendor',
                            row_order=slab_counter,
                            min_quantity=Decimal(request.POST.get(min_key, 0) or 0),
                            max_quantity=Decimal(request.POST.get(f'storage_slab_{storage_counter}_vendor_{slab_counter}_max', 0) or 0) if request.POST.get(f'storage_slab_{storage_counter}_vendor_{slab_counter}_max') else None,
                            rate_per_unit=Decimal(request.POST.get(f'storage_slab_{storage_counter}_vendor_{slab_counter}_rate', 0) or 0),
                            remarks=request.POST.get(f'storage_slab_{storage_counter}_vendor_{slab_counter}_remarks', '')
                        )
                        slab.save()
                        slab_counter += 1

                storage_counter += 1
            
            # HANDLING IN SECTION - Process multiple line items
            handling_in_counter = 1  # JavaScript counters start at 1
            while True:
                client_qty_key = f'handling_in_{handling_in_counter}_client_quantity'
                if client_qty_key not in request.POST:
                    break

                handling_item = MonthlyBillingHandlingItem(
                    monthly_billing=billing,
                    direction='in',
                    row_order=handling_in_counter,
                    remarks=request.POST.get(f'handling_in_{handling_in_counter}_remarks', '')
                )

                # Client side
                handling_item.client_quantity = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_client_quantity', 0) or 0)
                handling_item.client_unit_type_id = request.POST.get(f'handling_in_{handling_in_counter}_client_unit_type') or None
                handling_item.client_channel_id = request.POST.get(f'handling_in_{handling_in_counter}_client_channel') or None
                handling_item.client_base_type_id = request.POST.get(f'handling_in_{handling_in_counter}_client_base_type') or None
                handling_item.client_rate = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_client_rate', 0) or 0) if request.POST.get(f'handling_in_{handling_in_counter}_client_rate') else None
                handling_item.client_billing = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_client_total', 0) or 0)

                # Vendor side
                handling_item.vendor_quantity = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_vendor_quantity', 0) or 0)
                handling_item.vendor_unit_type_id = request.POST.get(f'handling_in_{handling_in_counter}_vendor_unit_type') or None
                handling_item.vendor_channel_id = request.POST.get(f'handling_in_{handling_in_counter}_vendor_channel') or None
                handling_item.vendor_base_type_id = request.POST.get(f'handling_in_{handling_in_counter}_vendor_base_type') or None
                handling_item.vendor_rate = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_vendor_rate', 0) or 0) if request.POST.get(f'handling_in_{handling_in_counter}_vendor_rate') else None
                handling_item.vendor_cost = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_vendor_total', 0) or 0)

                handling_item.save()
                handling_in_counter += 1

            # HANDLING OUT SECTION - Process multiple line items
            handling_out_counter = 1  # JavaScript counters start at 1
            while True:
                client_qty_key = f'handling_out_{handling_out_counter}_client_quantity'
                if client_qty_key not in request.POST:
                    break

                handling_item = MonthlyBillingHandlingItem(
                    monthly_billing=billing,
                    direction='out',
                    row_order=handling_out_counter,
                    remarks=request.POST.get(f'handling_out_{handling_out_counter}_remarks', '')
                )

                # Client side
                handling_item.client_quantity = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_client_quantity', 0) or 0)
                handling_item.client_unit_type_id = request.POST.get(f'handling_out_{handling_out_counter}_client_unit_type') or None
                handling_item.client_channel_id = request.POST.get(f'handling_out_{handling_out_counter}_client_channel') or None
                handling_item.client_base_type_id = request.POST.get(f'handling_out_{handling_out_counter}_client_base_type') or None
                handling_item.client_rate = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_client_rate', 0) or 0) if request.POST.get(f'handling_out_{handling_out_counter}_client_rate') else None
                handling_item.client_billing = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_client_total', 0) or 0)

                # Vendor side
                handling_item.vendor_quantity = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_vendor_quantity', 0) or 0)
                handling_item.vendor_unit_type_id = request.POST.get(f'handling_out_{handling_out_counter}_vendor_unit_type') or None
                handling_item.vendor_channel_id = request.POST.get(f'handling_out_{handling_out_counter}_vendor_channel') or None
                handling_item.vendor_base_type_id = request.POST.get(f'handling_out_{handling_out_counter}_vendor_base_type') or None
                handling_item.vendor_rate = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_vendor_rate', 0) or 0) if request.POST.get(f'handling_out_{handling_out_counter}_vendor_rate') else None
                handling_item.vendor_cost = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_vendor_total', 0) or 0)

                handling_item.save()
                handling_out_counter += 1
            
            # TRANSPORT SECTION - Process multiple line items
            # Template generates combined entries: transport_{counter}_client_* AND transport_{counter}_vendor_*
            # We create TWO separate TransportItem records (client + vendor) from each combined entry
            transport_counter = 1  # JavaScript counters start at 1
            while True:
                # Check if this entry exists (check client side as sentinel)
                client_vehicle_key = f'transport_{transport_counter}_client_vehicle_type'
                if client_vehicle_key not in request.POST:
                    break

                # Shared remarks field for this transport entry
                shared_remarks = request.POST.get(f'transport_{transport_counter}_remarks', '')

                # Create VENDOR transport item
                vendor_vehicle_type = request.POST.get(f'transport_{transport_counter}_vendor_vehicle_type') or None
                vendor_quantity = Decimal(request.POST.get(f'transport_{transport_counter}_vendor_quantity', 0) or 0)
                vendor_amount = Decimal(request.POST.get(f'transport_{transport_counter}_vendor_amount', 0) or 0)

                if vendor_vehicle_type or vendor_quantity or vendor_amount:
                    transport_item = MonthlyBillingTransportItem(
                        monthly_billing=billing,
                        side='vendor',
                        row_order=transport_counter,
                        vehicle_type_id=vendor_vehicle_type,
                        quantity=vendor_quantity,
                        amount=vendor_amount,
                        remarks=shared_remarks
                    )
                    transport_item.save()

                # Create CLIENT transport item
                client_vehicle_type = request.POST.get(f'transport_{transport_counter}_client_vehicle_type') or None
                client_quantity = Decimal(request.POST.get(f'transport_{transport_counter}_client_quantity', 0) or 0)
                client_amount = Decimal(request.POST.get(f'transport_{transport_counter}_client_amount', 0) or 0)

                if client_vehicle_type or client_quantity or client_amount:
                    transport_item = MonthlyBillingTransportItem(
                        monthly_billing=billing,
                        side='client',
                        row_order=transport_counter,
                        vehicle_type_id=client_vehicle_type,
                        quantity=client_quantity,
                        amount=client_amount,
                        remarks=shared_remarks
                    )
                    transport_item.save()

                transport_counter += 1
            
            # MISC/VAS (always manual)
            # MISC
            billing.client_misc_amount = Decimal(request.POST.get('client_misc_amount', 0) or 0)
            billing.vendor_misc_amount = Decimal(request.POST.get('vendor_misc_amount', 0) or 0)
            billing.client_misc_description = request.POST.get('client_misc_description', '')
            billing.vendor_misc_description = request.POST.get('vendor_misc_description', '')

            # VAS SECTION - Process multiple line items
            vas_counter = 1  # JavaScript counters start at 1
            while True:
                client_service_key = f'vas_{vas_counter}_client_service_type'
                if client_service_key not in request.POST:
                    break

                vas_item = MonthlyBillingVASItem(
                    monthly_billing=billing,
                    row_order=vas_counter,
                    remarks=request.POST.get(f'vas_{vas_counter}_remarks', '')
                )

                # Client side
                vas_item.client_service_type_id = request.POST.get(f'vas_{vas_counter}_client_service_type') or None
                vas_item.client_quantity = Decimal(request.POST.get(f'vas_{vas_counter}_client_quantity', 0) or 0)
                vas_item.client_unit_id = request.POST.get(f'vas_{vas_counter}_client_unit') or None
                _client_hours_raw = request.POST.get(f'vas_{vas_counter}_client_hours')
                vas_item.client_hours = Decimal(_client_hours_raw) if _client_hours_raw else None
                vas_item.client_rate = Decimal(request.POST.get(f'vas_{vas_counter}_client_rate', 0) or 0) if request.POST.get(f'vas_{vas_counter}_client_rate') else None
                vas_item.client_billing = Decimal(request.POST.get(f'vas_{vas_counter}_client_total', 0) or 0)

                # Vendor side
                vas_item.vendor_service_type_id = request.POST.get(f'vas_{vas_counter}_vendor_service_type') or None
                vas_item.vendor_quantity = Decimal(request.POST.get(f'vas_{vas_counter}_vendor_quantity', 0) or 0)
                vas_item.vendor_unit_id = request.POST.get(f'vas_{vas_counter}_vendor_unit') or None
                _vendor_hours_raw = request.POST.get(f'vas_{vas_counter}_vendor_hours')
                vas_item.vendor_hours = Decimal(_vendor_hours_raw) if _vendor_hours_raw else None
                vas_item.vendor_rate = Decimal(request.POST.get(f'vas_{vas_counter}_vendor_rate', 0) or 0) if request.POST.get(f'vas_{vas_counter}_vendor_rate') else None
                vas_item.vendor_cost = Decimal(request.POST.get(f'vas_{vas_counter}_vendor_total', 0) or 0)

                vas_item.save()
                vas_counter += 1

            # INFRASTRUCTURE SECTION - Process multiple line items
            infra_counter = 1  # JavaScript counters start at 1
            while True:
                # Check if this row exists in POST data
                cost_type_key = f'infrastructure_{infra_counter}_cost_type'
                if cost_type_key not in request.POST:
                    break

                # Create infrastructure item
                infra_item = MonthlyBillingInfrastructureItem(
                    monthly_billing=billing,
                    row_order=infra_counter,
                    description=request.POST.get(f'infrastructure_{infra_counter}_description', '')
                )

                # Cost type
                infra_item.cost_type_id = request.POST.get(f'infrastructure_{infra_counter}_cost_type') or None

                # Client and vendor amounts
                infra_item.client_billing = Decimal(request.POST.get(f'infrastructure_{infra_counter}_client_amount', 0) or 0)
                infra_item.vendor_cost = Decimal(request.POST.get(f'infrastructure_{infra_counter}_vendor_amount', 0) or 0)

                infra_item.save()
                infra_counter += 1

            # MIS
            billing.mis_email_subject = request.POST.get('mis_email_subject', '')
            billing.mis_link = request.POST.get('mis_link', '')

            # Handle MIS document uploads
            if request.FILES.get('mis_document'):
                billing.mis_document = request.FILES['mis_document']
            if request.FILES.get('transport_document'):
                billing.transport_document = request.FILES['transport_document']
            if request.FILES.get('other_document'):
                billing.other_document = request.FILES['other_document']

            # Handle adhoc billing inclusions
            included_adhoc_ids = request.POST.getlist('include_adhoc')
            # Store as JSON array (Django JSONField handles serialization)
            billing.included_adhoc_ids = included_adhoc_ids if included_adhoc_ids else []

            # Recalculate totals from line items
            billing.recalculate_totals()

            # Check if user clicked "Save as Draft" or "Create Billing"
            action = request.POST.get('action', 'submit')

            if action == 'save_draft':
                # Keep status as 'draft' (default from model)
                billing.save()
                messages.success(request, f"📝 Billing saved as draft for {project.client_name}!")
                return redirect('operations:monthly_billing_detail', billing_id=billing.id)
            else:
                # Final save with recalculated totals
                billing.save()
                messages.success(request, f"✅ Billing created successfully for {project.client_name}!")
                return redirect('operations:monthly_billing_detail', billing_id=billing.id)
            
        except Exception as e:
            messages.error(request, f"❌ Error creating billing: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # GET request - prepare context
    storage_units = StorageUnit.objects.filter(is_active=True).order_by('display_order')
    handling_units = HandlingUnit.objects.filter(is_active=True).order_by('display_order')
    vehicle_types = VehicleType.objects.filter(is_active=True).order_by('display_order')
    sales_channels = SalesChannel.objects.filter(is_active=True).order_by('display_order')
    handling_base_types = HandlingBaseType.objects.filter(is_active=True).order_by('display_order')
    vas_service_types = VASServiceType.objects.filter(is_active=True).order_by('display_order')
    vas_units = VASUnit.objects.filter(is_active=True).order_by('display_order')
    
    # Pre-fill storage min space from project card if available
    initial_storage_min = Decimal('0')
    
    if project_card:
        from operations.models_projectcard import StorageRate
        
        # Get storage min space from client storage rate
        client_storage = StorageRate.objects.filter(
            project_card=project_card,
            rate_for='client'
        ).first()
        
        if client_storage and client_storage.minimum_billable_area:
            initial_storage_min = client_storage.minimum_billable_area
    
    # Create temp billing with initial values for calculation context
    temp_billing = MonthlyBilling(
        project=project,
        service_month=service_month,
        billing_month=billing_month,
        storage_min_space=initial_storage_min,
        storage_additional_space=Decimal('0'),
        handling_in_quantity=Decimal('0'),
        handling_out_quantity=Decimal('0'),
    )
    
    # Get calculation contexts
    storage_context = get_storage_calculation_context(temp_billing, project_card) if project_card else None
    handling_in_context = get_handling_calculation_context(temp_billing, project_card, 'inbound') if project_card else None
    handling_out_context = get_handling_calculation_context(temp_billing, project_card, 'outbound') if project_card else None

    # Serialize dropdowns for JavaScript
    def serialize_dropdown(queryset):
        """Convert QuerySet to JSON-safe list of dicts"""
        return json.dumps([
            {'code': obj.code, 'label': obj.name}
            for obj in queryset
        ])
    
    context = {
        'project': project,
        'service_month': service_month,
        'billing_month': billing_month,
        'project_card': project_card,
        'adhoc_entries': adhoc_entries,
        
        # Original QuerySets (for Django template loops - project card reference blocks)
        'storage_units': storage_units,
        'handling_units': handling_units,
        'vehicle_types': vehicle_types,
        'sales_channels': sales_channels,
        'handling_base_types': handling_base_types,
        'vas_service_types': vas_service_types,
        'vas_units': vas_units,
        
        # JSON-serialized for JavaScript (CRITICAL FIX - matches project card pattern)
        'storage_units_json': get_dropdown_choices(StorageUnit),
        'handling_units_json': get_dropdown_choices(HandlingUnit),
        'vehicle_types_json': get_dropdown_choices(VehicleType),
        'sales_channels_json': get_dropdown_choices(SalesChannel),
        'handling_base_types_json': get_dropdown_choices(HandlingBaseType),
        'vas_service_types_json': get_dropdown_choices(VASServiceType),
        'vas_units_json': get_dropdown_choices(VASUnit),
        'infra_cost_types_json': get_dropdown_choices(OperationalCostType),
        
        'storage_context': storage_context,
        'handling_in_context': handling_in_context,
        'handling_out_context': handling_out_context,
        'initial_storage_min': initial_storage_min,
        'is_create': True,
        'is_edit': False,
    }

    return render(request, 'operations/monthly_billing_create.html', context)


# ============================================================================
# DETAIL VIEW
# ============================================================================

@login_required
def billing_detail(request, billing_id):
    """
    View billing details with full workflow history.
    """
    billing = get_object_or_404(
        MonthlyBilling.objects.select_related(
            'project', 'status', 'created_by',
            'submitted_by', 'controller_reviewed_by', 'finance_reviewed_by',
            'storage_unit_type', 'handling_in_unit_type', 'handling_out_unit_type',
            'vendor_transport_vehicle_type', 'client_transport_vehicle_type',
            'project_card_used', 'controller_action', 'finance_action'
        ),
        id=billing_id
    )
    
    user = request.user
    
    # Permission check - coordinators can only see their billings
    if user.role == 'operation_coordinator':
        if billing.project.operation_coordinator != user.get_full_name():
            messages.error(request, "You can only view your own billings.")
            return redirect('operations:monthly_billing_dashboard')
    
    show_financials = show_financials_to_user(user)
    
    # Permission flags for actions
    can_edit = False
    can_submit = False
    
    # Check if billing is locked
    if not billing.is_locked():
        editable_statuses = ['draft', 'controller_rejected', 'finance_rejected']
        
        if user.role in ['admin', 'super_user']:
            # Admins can edit and submit any unlocked billing
            can_edit = billing.status.code in editable_statuses
            can_submit = billing.status.code in editable_statuses
            
        elif user.role == 'operation_manager':
            # Managers can edit and submit any unlocked billing in editable states
            can_edit = billing.status.code in editable_statuses
            can_submit = billing.status.code in editable_statuses
            
        elif user.role == 'operation_coordinator':
            # Coordinators can edit their own billings in editable states
            is_owner = (billing.created_by == user or 
                       billing.project.operation_coordinator == user.get_full_name())
            if is_owner:
                can_edit = billing.status.code in editable_statuses
                can_submit = billing.status.code in editable_statuses
    
    can_controller_review = billing.can_controller_review(user)
    can_finance_review = billing.can_finance_review(user)
    
    # Get included adhoc billings if any
    included_adhoc = []
    if billing.included_adhoc_ids:
        from operations.models_adhoc import AdhocBillingEntry
        # Handle both old format (string) and new format (list)
        if isinstance(billing.included_adhoc_ids, str):
            # Old format: comma-separated string
            adhoc_ids = [int(aid) for aid in billing.included_adhoc_ids.split(',') if aid.strip()]
        else:
            # New format: JSON array
            adhoc_ids = [int(aid) for aid in billing.included_adhoc_ids if aid]
        included_adhoc = AdhocBillingEntry.objects.filter(id__in=adhoc_ids)
    
    # Get line items for display
    storage_items = billing.storage_items.all().select_related('client_storage_unit_type', 'vendor_storage_unit_type')
    handling_in_items = billing.handling_items.filter(direction='in').select_related(
        'client_unit_type', 'vendor_unit_type', 'client_channel', 'vendor_channel',
        'client_base_type', 'vendor_base_type'
    )
    handling_out_items = billing.handling_items.filter(direction='out').select_related(
        'client_unit_type', 'vendor_unit_type', 'client_channel', 'vendor_channel',
        'client_base_type', 'vendor_base_type'
    )
    vendor_transport_items = billing.transport_items.filter(side='vendor').select_related('vehicle_type')
    client_transport_items = billing.transport_items.filter(side='client').select_related('vehicle_type')
    vas_items = billing.vas_items.all().select_related(
        'client_service_type', 'vendor_service_type', 'client_unit', 'vendor_unit'
    )
    infrastructure_items = billing.infrastructure_items.all().select_related('cost_type')

    context = {
        'billing': billing,
        'can_edit': can_edit,
        'can_submit': can_submit,
        'can_controller_review': can_controller_review,
        'can_finance_review': can_finance_review,
        'show_financials': show_financials,
        'included_adhoc': included_adhoc,
        'storage_items': storage_items,
        'handling_in_items': handling_in_items,
        'handling_out_items': handling_out_items,
        'vendor_transport_items': vendor_transport_items,
        'client_transport_items': client_transport_items,
        'vas_items': vas_items,
        'infrastructure_items': infrastructure_items,
    }

    return render(request, 'operations/monthly_billing_detail.html', context)




@login_required
def billing_recall(request, billing_id):
    """
    Recall a submitted billing back to draft state.
    Only creator can recall before it's reviewed.
    """
    if request.method != 'POST':
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)
    
    billing = get_object_or_404(MonthlyBilling, id=billing_id)
    user = request.user
    
    # Check if user can recall
    can_recall = False
    if user.role in ['admin', 'super_user']:
        can_recall = True
    elif user.role in ['operation_coordinator', 'operation_manager']:
        is_owner = (billing.created_by == user or 
                   billing.project.operation_coordinator == user.get_full_name())
        can_recall = is_owner and billing.status.code == 'pending_controller'
    
    if not can_recall:
        messages.error(request, "You cannot recall this billing.")
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)
    
    try:
        # Recall to draft
        billing.status_id = 'draft'
        billing.submitted_by = None
        billing.submitted_at = None
        billing.save()
        
        messages.success(request, "✅ Billing recalled! You can now edit it.")
        return redirect('operations:monthly_billing_edit', billing_id=billing.id)
        
    except Exception as e:
        messages.error(request, f"❌ Error recalling billing: {str(e)}")
        return redirect('operations:monthly_billing_detail', billing_id=billing.id)


# ============================================================================
# EDIT BILLING
# ============================================================================

@login_required
def billing_edit(request, billing_id):
    """
    Edit existing billing.
    Supports both AUTO and MANUAL modes with override tracking.
    """
    billing = get_object_or_404(MonthlyBilling, id=billing_id)
    user = request.user
    
    # Permission check
    can_edit = billing.can_edit(user) or (
        user.role in ['operation_manager', 'admin', 'super_user'] and 
        billing.status_id in ['draft', 'controller_rejected', 'finance_rejected']
    )
    
    if not can_edit:
        messages.error(request, "You cannot edit this billing.")
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)
    
    # Get project card for auto-calculation
    project_card = billing.project_card_used or get_project_card_for_project(billing.project)
    
    # Get adhoc billings for the service month
    adhoc_entries = get_adhoc_billings_for_month(billing.project, billing.service_month)
    
    if request.method == 'POST':

        try:
            # Get service and billing months (YYYY-MM format from month input)
            service_month = request.POST.get('service_month')
            billing_month = request.POST.get('billing_month')

            # Convert to first day of month
            if service_month:
                service_month = datetime.strptime(service_month, '%Y-%m').date().replace(day=1)
            if billing_month:
                billing_month = datetime.strptime(billing_month, '%Y-%m').date().replace(day=1)


            # Check for duplicate if service_month is changing (one billing per project per service month)
            if service_month and service_month != billing.service_month:
                existing = MonthlyBilling.objects.filter(
                    project=billing.project,
                    service_month=service_month
                ).exclude(id=billing.id).first()
                if existing:
                    messages.error(request, f"Billing for {billing.project.client_name} - service month {service_month.strftime('%B %Y')} already exists!")
                    return redirect('operations:monthly_billing_edit', billing_id=billing.id)

            # Update the billing object with new months
            billing.service_month = service_month
            if billing_month:
                billing.billing_month = billing_month

            # ═══════════════════════════════════════════════════════════════════════════
            # DISABLED: Legacy Parent Field Updates
            # 
            # These lines updated parent fields (storage_min_space, client_storage_billing, etc.)
            # which caused conflicts with the new LINE ITEMS architecture.
            # 
            # Parent totals are now auto-calculated from line items by recalculate_totals().
            # See line items processing starting at "Delete existing line items" below.
            # ═══════════════════════════════════════════════════════════════════════════

            # Skip to line items section below...
            if False:  # Disabled legacy code

                pass  # End disabled block

            # Delete existing line items (to prevent duplicates on edit)
            billing.storage_items.all().delete()
            billing.handling_items.all().delete()
            billing.transport_items.all().delete()
            billing.vas_items.all().delete()
            billing.infrastructure_items.all().delete()

            # STORAGE SECTION - Process multiple line items
            storage_counter = 1  # JavaScript counters start at 1
            while True:
                client_min_key = f'storage_{storage_counter}_client_min_space'
                if client_min_key not in request.POST:
                    break

                # Get pricing type (flat, slab, or lumpsum)
                pricing_type = request.POST.get(f'storage_{storage_counter}_pricing_type', 'flat')

                storage_item = MonthlyBillingStorageItem(
                    monthly_billing=billing,
                    row_order=storage_counter,
                    pricing_type=pricing_type,
                    remarks=request.POST.get(f'storage_{storage_counter}_remarks', '')
                )

                # Client side
                storage_item.client_min_space = Decimal(request.POST.get(f'storage_{storage_counter}_client_min_space', 0) or 0)
                storage_item.client_additional_space = Decimal(request.POST.get(f'storage_{storage_counter}_client_additional_space', 0) or 0)
                storage_item.client_storage_unit_type_id = request.POST.get(f'storage_{storage_counter}_client_unit_type') or None
                storage_item.client_storage_days = int(request.POST.get(f'storage_{storage_counter}_client_days', 0) or 0)
                storage_item.client_rate = Decimal(request.POST.get(f'storage_{storage_counter}_client_rate', 0) or 0) if request.POST.get(f'storage_{storage_counter}_client_rate') else None
                storage_item.client_billing = Decimal(request.POST.get(f'storage_{storage_counter}_client_total', 0) or 0)

                # Lumpsum amount (if pricing_type='lumpsum')
                storage_item.client_lumpsum_amount = Decimal(request.POST.get(f'storage_{storage_counter}_client_lumpsum', 0) or 0) if request.POST.get(f'storage_{storage_counter}_client_lumpsum') else None

                # Vendor side
                storage_item.vendor_min_space = Decimal(request.POST.get(f'storage_{storage_counter}_vendor_min_space', 0) or 0)
                storage_item.vendor_additional_space = Decimal(request.POST.get(f'storage_{storage_counter}_vendor_additional_space', 0) or 0)
                storage_item.vendor_storage_unit_type_id = request.POST.get(f'storage_{storage_counter}_vendor_unit_type') or None
                storage_item.vendor_storage_days = int(request.POST.get(f'storage_{storage_counter}_vendor_days', 0) or 0)
                storage_item.vendor_rate = Decimal(request.POST.get(f'storage_{storage_counter}_vendor_rate', 0) or 0) if request.POST.get(f'storage_{storage_counter}_vendor_rate') else None
                storage_item.vendor_cost = Decimal(request.POST.get(f'storage_{storage_counter}_vendor_total', 0) or 0)

                # Lumpsum amount (if pricing_type='lumpsum')
                storage_item.vendor_lumpsum_amount = Decimal(request.POST.get(f'storage_{storage_counter}_vendor_lumpsum', 0) or 0) if request.POST.get(f'storage_{storage_counter}_vendor_lumpsum') else None

                storage_item.save()

                # If pricing_type is 'slab', save slabs
                if pricing_type == 'slab':
                    # Process client slabs
                    slab_counter = 1
                    while True:
                        min_key = f'storage_slab_{storage_counter}_client_{slab_counter}_min'
                        if min_key not in request.POST:
                            break

                        from operations.models_monthly_billing_items import MonthlyBillingStorageSlab
                        slab = MonthlyBillingStorageSlab(
                            storage_item=storage_item,
                            side='client',
                            row_order=slab_counter,
                            min_quantity=Decimal(request.POST.get(min_key, 0) or 0),
                            max_quantity=Decimal(request.POST.get(f'storage_slab_{storage_counter}_client_{slab_counter}_max', 0) or 0) if request.POST.get(f'storage_slab_{storage_counter}_client_{slab_counter}_max') else None,
                            rate_per_unit=Decimal(request.POST.get(f'storage_slab_{storage_counter}_client_{slab_counter}_rate', 0) or 0),
                            remarks=request.POST.get(f'storage_slab_{storage_counter}_client_{slab_counter}_remarks', '')
                        )
                        slab.save()
                        slab_counter += 1

                    # Process vendor slabs
                    slab_counter = 1
                    while True:
                        min_key = f'storage_slab_{storage_counter}_vendor_{slab_counter}_min'
                        if min_key not in request.POST:
                            break

                        from operations.models_monthly_billing_items import MonthlyBillingStorageSlab
                        slab = MonthlyBillingStorageSlab(
                            storage_item=storage_item,
                            side='vendor',
                            row_order=slab_counter,
                            min_quantity=Decimal(request.POST.get(min_key, 0) or 0),
                            max_quantity=Decimal(request.POST.get(f'storage_slab_{storage_counter}_vendor_{slab_counter}_max', 0) or 0) if request.POST.get(f'storage_slab_{storage_counter}_vendor_{slab_counter}_max') else None,
                            rate_per_unit=Decimal(request.POST.get(f'storage_slab_{storage_counter}_vendor_{slab_counter}_rate', 0) or 0),
                            remarks=request.POST.get(f'storage_slab_{storage_counter}_vendor_{slab_counter}_remarks', '')
                        )
                        slab.save()
                        slab_counter += 1

                storage_counter += 1

            # HANDLING IN SECTION - Process multiple line items
            handling_in_counter = 1  # JavaScript counters start at 1
            while True:
                client_qty_key = f'handling_in_{handling_in_counter}_client_quantity'
                if client_qty_key not in request.POST:
                    break

                handling_item = MonthlyBillingHandlingItem(
                    monthly_billing=billing,
                    direction='in',
                    row_order=handling_in_counter,
                    remarks=request.POST.get(f'handling_in_{handling_in_counter}_remarks', '')
                )

                # Client side
                handling_item.client_quantity = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_client_quantity', 0) or 0)
                handling_item.client_unit_type_id = request.POST.get(f'handling_in_{handling_in_counter}_client_unit_type') or None
                handling_item.client_channel_id = request.POST.get(f'handling_in_{handling_in_counter}_client_channel') or None
                handling_item.client_base_type_id = request.POST.get(f'handling_in_{handling_in_counter}_client_base_type') or None
                handling_item.client_rate = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_client_rate', 0) or 0) if request.POST.get(f'handling_in_{handling_in_counter}_client_rate') else None
                handling_item.client_billing = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_client_total', 0) or 0)

                # Vendor side
                handling_item.vendor_quantity = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_vendor_quantity', 0) or 0)
                handling_item.vendor_unit_type_id = request.POST.get(f'handling_in_{handling_in_counter}_vendor_unit_type') or None
                handling_item.vendor_channel_id = request.POST.get(f'handling_in_{handling_in_counter}_vendor_channel') or None
                handling_item.vendor_base_type_id = request.POST.get(f'handling_in_{handling_in_counter}_vendor_base_type') or None
                handling_item.vendor_rate = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_vendor_rate', 0) or 0) if request.POST.get(f'handling_in_{handling_in_counter}_vendor_rate') else None
                handling_item.vendor_cost = Decimal(request.POST.get(f'handling_in_{handling_in_counter}_vendor_total', 0) or 0)

                handling_item.save()
                handling_in_counter += 1

            # HANDLING OUT SECTION - Process multiple line items
            handling_out_counter = 1  # JavaScript counters start at 1
            while True:
                client_qty_key = f'handling_out_{handling_out_counter}_client_quantity'
                if client_qty_key not in request.POST:
                    break

                handling_item = MonthlyBillingHandlingItem(
                    monthly_billing=billing,
                    direction='out',
                    row_order=handling_out_counter,
                    remarks=request.POST.get(f'handling_out_{handling_out_counter}_remarks', '')
                )

                # Client side
                handling_item.client_quantity = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_client_quantity', 0) or 0)
                handling_item.client_unit_type_id = request.POST.get(f'handling_out_{handling_out_counter}_client_unit_type') or None
                handling_item.client_channel_id = request.POST.get(f'handling_out_{handling_out_counter}_client_channel') or None
                handling_item.client_base_type_id = request.POST.get(f'handling_out_{handling_out_counter}_client_base_type') or None
                handling_item.client_rate = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_client_rate', 0) or 0) if request.POST.get(f'handling_out_{handling_out_counter}_client_rate') else None
                handling_item.client_billing = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_client_total', 0) or 0)

                # Vendor side
                handling_item.vendor_quantity = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_vendor_quantity', 0) or 0)
                handling_item.vendor_unit_type_id = request.POST.get(f'handling_out_{handling_out_counter}_vendor_unit_type') or None
                handling_item.vendor_channel_id = request.POST.get(f'handling_out_{handling_out_counter}_vendor_channel') or None
                handling_item.vendor_base_type_id = request.POST.get(f'handling_out_{handling_out_counter}_vendor_base_type') or None
                handling_item.vendor_rate = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_vendor_rate', 0) or 0) if request.POST.get(f'handling_out_{handling_out_counter}_vendor_rate') else None
                handling_item.vendor_cost = Decimal(request.POST.get(f'handling_out_{handling_out_counter}_vendor_total', 0) or 0)

                handling_item.save()
                handling_out_counter += 1

            # TRANSPORT SECTION - Process multiple line items
            # Template generates combined entries: transport_{counter}_client_* AND transport_{counter}_vendor_*
            # We create TWO separate TransportItem records (client + vendor) from each combined entry
            transport_counter = 1  # JavaScript counters start at 1
            while True:
                # Check if this entry exists (check client side as sentinel)
                client_vehicle_key = f'transport_{transport_counter}_client_vehicle_type'
                if client_vehicle_key not in request.POST:
                    break

                # Shared remarks field for this transport entry
                shared_remarks = request.POST.get(f'transport_{transport_counter}_remarks', '')

                # Create VENDOR transport item
                vendor_vehicle_type = request.POST.get(f'transport_{transport_counter}_vendor_vehicle_type') or None
                vendor_quantity = Decimal(request.POST.get(f'transport_{transport_counter}_vendor_quantity', 0) or 0)
                vendor_amount = Decimal(request.POST.get(f'transport_{transport_counter}_vendor_amount', 0) or 0)

                if vendor_vehicle_type or vendor_quantity or vendor_amount:
                    transport_item = MonthlyBillingTransportItem(
                        monthly_billing=billing,
                        side='vendor',
                        row_order=transport_counter,
                        vehicle_type_id=vendor_vehicle_type,
                        quantity=vendor_quantity,
                        amount=vendor_amount,
                        remarks=shared_remarks
                    )
                    transport_item.save()

                # Create CLIENT transport item
                client_vehicle_type = request.POST.get(f'transport_{transport_counter}_client_vehicle_type') or None
                client_quantity = Decimal(request.POST.get(f'transport_{transport_counter}_client_quantity', 0) or 0)
                client_amount = Decimal(request.POST.get(f'transport_{transport_counter}_client_amount', 0) or 0)

                if client_vehicle_type or client_quantity or client_amount:
                    transport_item = MonthlyBillingTransportItem(
                        monthly_billing=billing,
                        side='client',
                        row_order=transport_counter,
                        vehicle_type_id=client_vehicle_type,
                        quantity=client_quantity,
                        amount=client_amount,
                        remarks=shared_remarks
                    )
                    transport_item.save()

                transport_counter += 1

            # VAS SECTION - Process multiple line items
            vas_counter = 1  # JavaScript counters start at 1
            while True:
                client_service_key = f'vas_{vas_counter}_client_service_type'
                if client_service_key not in request.POST:
                    break

                vas_item = MonthlyBillingVASItem(
                    monthly_billing=billing,
                    row_order=vas_counter,
                    remarks=request.POST.get(f'vas_{vas_counter}_remarks', '')
                )

                # Client side
                vas_item.client_service_type_id = request.POST.get(f'vas_{vas_counter}_client_service_type') or None
                vas_item.client_quantity = Decimal(request.POST.get(f'vas_{vas_counter}_client_quantity', 0) or 0)
                vas_item.client_unit_id = request.POST.get(f'vas_{vas_counter}_client_unit') or None
                _client_hours_raw = request.POST.get(f'vas_{vas_counter}_client_hours')
                vas_item.client_hours = Decimal(_client_hours_raw) if _client_hours_raw else None
                vas_item.client_rate = Decimal(request.POST.get(f'vas_{vas_counter}_client_rate', 0) or 0) if request.POST.get(f'vas_{vas_counter}_client_rate') else None
                vas_item.client_billing = Decimal(request.POST.get(f'vas_{vas_counter}_client_total', 0) or 0)

                # Vendor side
                vas_item.vendor_service_type_id = request.POST.get(f'vas_{vas_counter}_vendor_service_type') or None
                vas_item.vendor_quantity = Decimal(request.POST.get(f'vas_{vas_counter}_vendor_quantity', 0) or 0)
                vas_item.vendor_unit_id = request.POST.get(f'vas_{vas_counter}_vendor_unit') or None
                _vendor_hours_raw = request.POST.get(f'vas_{vas_counter}_vendor_hours')
                vas_item.vendor_hours = Decimal(_vendor_hours_raw) if _vendor_hours_raw else None
                vas_item.vendor_rate = Decimal(request.POST.get(f'vas_{vas_counter}_vendor_rate', 0) or 0) if request.POST.get(f'vas_{vas_counter}_vendor_rate') else None
                vas_item.vendor_cost = Decimal(request.POST.get(f'vas_{vas_counter}_vendor_total', 0) or 0)

                vas_item.save()
                vas_counter += 1

            # INFRASTRUCTURE SECTION - Process multiple line items
            infra_counter = 1  # JavaScript counters start at 1
            while True:
                # Check if this row exists in POST data
                cost_type_key = f'infrastructure_{infra_counter}_cost_type'
                if cost_type_key not in request.POST:
                    break

                # Create infrastructure item
                infra_item = MonthlyBillingInfrastructureItem(
                    monthly_billing=billing,
                    row_order=infra_counter,
                    description=request.POST.get(f'infrastructure_{infra_counter}_description', '')
                )

                # Cost type
                infra_item.cost_type_id = request.POST.get(f'infrastructure_{infra_counter}_cost_type') or None

                # Client and vendor amounts
                infra_item.client_billing = Decimal(request.POST.get(f'infrastructure_{infra_counter}_client_amount', 0) or 0)
                infra_item.vendor_cost = Decimal(request.POST.get(f'infrastructure_{infra_counter}_vendor_amount', 0) or 0)

                infra_item.save()
                infra_counter += 1

            # Recalculate totals from line items
            billing.recalculate_totals()

            # Check if user clicked "Save as Draft" or "Update Billing"
            action = request.POST.get('action', 'submit')

            # Final save with recalculated totals
            billing.save()

            # Create notification if controller edited someone else's billing
            if user.role == 'operation_controller' and billing.created_by and billing.created_by != user:
                create_billing_correction_notification(billing, user, billing.created_by)
                messages.info(request, "🔔 Creator has been notified of the correction.")

            if action == 'save_draft':
                messages.success(request, "📝 Billing saved as draft!")
            else:
                messages.success(request, "✅ Billing updated successfully!")

            return redirect('operations:monthly_billing_detail', billing_id=billing.id)
            
        except Exception as e:
            messages.error(request, f"❌ Error updating billing: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # GET request
    storage_units = StorageUnit.objects.filter(is_active=True).order_by('display_order')
    handling_units = HandlingUnit.objects.filter(is_active=True).order_by('display_order')
    vehicle_types = VehicleType.objects.filter(is_active=True).order_by('display_order')
    sales_channels = SalesChannel.objects.filter(is_active=True).order_by('display_order')
    handling_base_types = HandlingBaseType.objects.filter(is_active=True).order_by('display_order')
    vas_service_types = VASServiceType.objects.filter(is_active=True).order_by('display_order')
    vas_units = VASUnit.objects.filter(is_active=True).order_by('display_order')

    # Get calculation contexts for comparison
    storage_context = get_storage_calculation_context(billing, project_card) if project_card else None
    handling_in_context = get_handling_calculation_context(billing, project_card, 'inbound') if project_card else None
    handling_out_context = get_handling_calculation_context(billing, project_card, 'outbound') if project_card else None

    context = {
        'billing': billing,
        'project': billing.project,
        'service_month': billing.service_month,
        'billing_month': billing.billing_month,

        # Original QuerySets (for Django template loops)
        'storage_units': storage_units,
        'handling_units': handling_units,
        'vehicle_types': vehicle_types,
        'sales_channels': sales_channels,
        'handling_base_types': handling_base_types,
        'vas_service_types': vas_service_types,
        'vas_units': vas_units,

        # JSON-serialized for JavaScript (CRITICAL - needed for dynamic forms)
        'storage_units_json': get_dropdown_choices(StorageUnit),
        'handling_units_json': get_dropdown_choices(HandlingUnit),
        'vehicle_types_json': get_dropdown_choices(VehicleType),
        'sales_channels_json': get_dropdown_choices(SalesChannel),
        'handling_base_types_json': get_dropdown_choices(HandlingBaseType),
        'vas_service_types_json': get_dropdown_choices(VASServiceType),
        'vas_units_json': get_dropdown_choices(VASUnit),
        'infra_cost_types_json': get_dropdown_choices(OperationalCostType),

        'project_card': project_card,
        'adhoc_entries': adhoc_entries,
        'storage_context': storage_context,
        'handling_in_context': handling_in_context,
        'handling_out_context': handling_out_context,

        # CRITICAL: Existing line items for edit mode pre-population
        'existing_storage_items': billing.storage_items.all().order_by('row_order', 'id'),
        'existing_handling_items': billing.handling_items.all().order_by('direction', 'row_order', 'id'),
        'existing_vas_items': billing.vas_items.all().order_by('row_order', 'id'),
        'existing_infrastructure_items': billing.infrastructure_items.all().order_by('row_order', 'id'),

        # Transport: pair client+vendor by row_order for combined display
        'existing_transport_pairs': _pair_transport_items(billing.transport_items.all()),

        'is_edit': True,
        'is_create': False,
    }

    return render(request, 'operations/monthly_billing_edit.html', context)


# ============================================================================
# WORKFLOW ACTIONS
# ============================================================================

@login_required
def billing_submit(request, billing_id):
    """Submit billing for controller review."""
    if request.method != 'POST':
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)
    
    billing = get_object_or_404(MonthlyBilling, id=billing_id)
    user = request.user
    
    # Check permission - coordinators for their projects, managers for all
    can_submit = billing.can_submit(user) or (
        user.role in ['operation_manager', 'admin', 'super_user'] and 
        billing.status_id in ['draft', 'controller_rejected', 'finance_rejected']
    )
    
    if not can_submit:
        messages.error(request, "You cannot submit this billing.")
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)
    
    try:
        billing.submit_for_review(user)
        messages.success(request, "✅ Billing submitted for controller review!")
    except ValueError as e:
        messages.error(request, str(e))
    
    return redirect('operations:monthly_billing_detail', billing_id=billing.id)


@login_required
def controller_review(request, billing_id):
    """Controller approve or reject billing."""
    if request.method != 'POST':
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)
    
    billing = get_object_or_404(MonthlyBilling, id=billing_id)
    user = request.user
    
    if not billing.can_controller_review(user):
        messages.error(request, "You cannot review this billing.")
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)
    
    action = request.POST.get('action')
    remarks = request.POST.get('remarks', '')
    
    try:
        if action == 'approve':
            billing.controller_approve(user, remarks)
            messages.success(request, "✅ Billing approved and sent to finance!")
            
        elif action == 'reject':
            if not remarks:
                messages.error(request, "Rejection remarks are mandatory!")
                return redirect('operations:monthly_billing_detail', billing_id=billing.id)
            
            billing.controller_reject(user, remarks)
            messages.warning(request, "⚠️ Billing rejected and sent back to coordinator.")
        else:
            messages.error(request, "Invalid action.")
            
    except ValueError as e:
        messages.error(request, str(e))
    
    return redirect('operations:monthly_billing_detail', billing_id=billing.id)


@login_required
def finance_review(request, billing_id):
    """Finance approve or reject billing. Approval LOCKS the billing."""
    if request.method != 'POST':
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)
    
    billing = get_object_or_404(MonthlyBilling, id=billing_id)
    user = request.user
    
    if not billing.can_finance_review(user):
        messages.error(request, "You cannot review this billing.")
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)
    
    action = request.POST.get('action')
    remarks = request.POST.get('remarks', '')
    
    try:
        if action == 'approve':
            billing.finance_approve(user, remarks)
            messages.success(request, "✅ Billing approved and LOCKED! No further edits allowed.")
            
        elif action == 'reject':
            if not remarks:
                messages.error(request, "Rejection remarks are mandatory!")
                return redirect('operations:monthly_billing_detail', billing_id=billing.id)
            
            billing.finance_reject(user, remarks)
            messages.warning(request, "⚠️ Billing rejected and sent back to coordinator.")
        else:
            messages.error(request, "Invalid action.")
            
    except ValueError as e:
        messages.error(request, str(e))
    
    return redirect('operations:monthly_billing_detail', billing_id=billing.id)


@login_required
def billing_delete(request, billing_id):
    """Delete billing (only in draft state by creator)."""
    if request.method != 'POST':
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)
    
    billing = get_object_or_404(MonthlyBilling, id=billing_id)
    user = request.user
    
    # Can only delete own billings in draft state (or managers can delete draft)
    can_delete = (
        (billing.created_by == user and billing.status_id == 'draft') or
        (user.role in ['operation_manager', 'admin', 'super_user'] and billing.status_id == 'draft')
    )
    
    if not can_delete:
        messages.error(request, "You cannot delete this billing.")
        return redirect('operations:monthly_billing_detail', billing_id=billing.id)
    
    project_name = billing.project.client_name
    billing_month = billing.billing_month.strftime('%B %Y')
    billing.delete()
    
    messages.success(request, f"🗑️ Billing for {project_name} - {billing_month} deleted successfully!")
    return redirect('operations:monthly_billing_dashboard')


@login_required
def monthly_billing_document_preview(request, billing_id, field_name):
    """
    Preview monthly billing document
    Works with both local storage (dev) and GCS (production)
    """
    from django.conf import settings
    from django.http import FileResponse, HttpResponse
    import mimetypes

    # Get billing
    billing = get_object_or_404(MonthlyBilling, id=billing_id)

    # Get the file field
    field_map = {
        'mis_document': billing.mis_document,
        'transport_document': billing.transport_document,
        'other_document': billing.other_document,
    }

    file_field = field_map.get(field_name)

    if not file_field:
        messages.error(request, f'Document "{field_name}" not found.')
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)

    # Check if file exists
    if not file_field.name:
        messages.error(request, 'No file uploaded for this document.')
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)

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
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)


@login_required
def monthly_billing_document_download(request, billing_id, field_name):
    """
    Download monthly billing document
    Works with both local storage (dev) and GCS (production)
    """
    from django.conf import settings
    from django.http import FileResponse, HttpResponse
    import mimetypes

    # Get billing
    billing = get_object_or_404(MonthlyBilling, id=billing_id)

    # Get the file field
    field_map = {
        'mis_document': billing.mis_document,
        'transport_document': billing.transport_document,
        'other_document': billing.other_document,
    }

    file_field = field_map.get(field_name)

    if not file_field:
        messages.error(request, f'Document "{field_name}" not found.')
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)

    # Check if file exists
    if not file_field.name:
        messages.error(request, 'No file uploaded for this document.')
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)

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
                method='GET',
                response_disposition=f'attachment; filename="{file_field.name.split("/")[-1]}"'
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

            # Get filename
            filename = file_field.name.split('/')[-1]

            # Open and serve file for download (force download)
            file_handle = open(file_path, 'rb')
            response = FileResponse(file_handle, content_type=content_type, as_attachment=True, filename=filename)

            return response

    except Exception as e:
        messages.error(request, f'Error accessing file: {str(e)}')
        return redirect('operations:monthly_billing_detail', billing_id=billing_id)