"""
Supply Chain Management Views
Handles vendor cards, warehouses, profiles, capacities, commercials, contacts, documents, and locations
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction, connection
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count, Prefetch, Sum, F
from django.utils import timezone
from datetime import timedelta
from django.urls import reverse
from functools import wraps
import json

from .models import (
    VendorCard,
    VendorContact,
    VendorWarehouse,
    VendorWarehouseDocument,
    WarehouseProfile,
    WarehouseCapacity,
    WarehouseCommercial,
    WarehouseContact,
    WarehousePhoto,
    Location,
    CityCode,
    RFQ,
    RFQVendorMapping
)
from .forms import (
    VendorCardForm,
    VendorContactForm,
    VendorContactFormSet,
    VendorWarehouseForm,
    WarehouseProfileForm,
    WarehouseCapacityForm,
    WarehouseCommercialForm,
    WarehouseContactFormSet,
    VendorWarehouseDocumentForm,
    LocationForm
)
from projects.models import ProjectCode
from accounts.permissions import require_role
from dropdown_master_data.models import StateCode, SLAStatus


# ============================================================================
# SUPPLY APP AVAILABILITY CHECK
# ============================================================================

def require_supply_tables(view_func):
    """
    Decorator that checks if supply app tables exist before allowing access.
    Shows a friendly "coming soon" message if tables haven't been deployed yet.
    Production-grade: works automatically without manual intervention.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            # Check if vendor_cards table exists
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name = 'vendor_cards'
                """)
                table_exists = cursor.fetchone() is not None

            if not table_exists:
                # Tables don't exist yet - show friendly message
                return render(request, 'supply/coming_soon.html', {
                    'message': 'Supply Chain Management module is being deployed.',
                    'detail': 'The vendor and warehouse management features will be available shortly.'
                }, status=503)

            # Tables exist, proceed with the view
            return view_func(request, *args, **kwargs)

        except Exception as e:
            # Fallback for any other errors
            return render(request, 'supply/coming_soon.html', {
                'message': 'Supply Chain Management module is temporarily unavailable.',
                'detail': str(e)
            }, status=503)

    return wrapper


# ============================================================================
# DASHBOARD & ANALYTICS
# ============================================================================

@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager')
def supply_dashboard(request):
    """
    Supply Manager Dashboard - Mission Control for Supply-Side Operations
    """

    # ========================================================================
    # 1️⃣ GLOBAL KPIs
    # ========================================================================

    # Total Warehouses (active only)
    total_warehouses = VendorWarehouse.objects.filter(
        warehouse_is_active=True
    ).count()

    # Active Vendors (vendors with at least 1 active warehouse)
    active_vendors = VendorCard.objects.filter(
        warehouses__warehouse_is_active=True,
        vendor_is_active=True
    ).distinct().count()

    # SLA Signed Percentage
    total_wh_with_commercial = WarehouseCommercial.objects.count()
    try:
        # Use .first() to handle potential multiple records
        sla_signed_status = SLAStatus.objects.filter(code='signed').first()
        if sla_signed_status:
            sla_signed_count = WarehouseCommercial.objects.filter(
                sla_status=sla_signed_status
            ).count()
            sla_signed_percentage = round(
                (sla_signed_count / total_wh_with_commercial * 100) if total_wh_with_commercial > 0 else 0,
                1
            )
        else:
            sla_signed_count = 0
            sla_signed_percentage = 0
    except Exception:
        sla_signed_count = 0
        sla_signed_percentage = 0
    
    # Available Capacity (sum of available capacity in sqft)
    capacity_data = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True
    ).aggregate(
        total=Sum('total_capacity'),
        available=Sum('available_capacity')
    )
    total_capacity = capacity_data['total'] or 0
    available_capacity = capacity_data['available'] or 0
    utilized_capacity = total_capacity - available_capacity
    utilization_percent = round(
        (utilized_capacity / total_capacity * 100) if total_capacity > 0 else 0,
        1
    )
    
    # Warehouses 24×7
    warehouses_24x7_count = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        is_24x7=True
    ).count()
    
    # Temperature Controlled Warehouses
    temp_controlled_count = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        temperature_controlled=True
    ).count()
    
    # ========================================================================
    # 2️⃣ ACTION ALERTS (Critical & Time-Sensitive)
    # ========================================================================
    
    # Alert 1: SLA Not Signed
    try:
        sla_not_signed_statuses = SLAStatus.objects.filter(
            code__in=['not_signed', 'under_negotiation']
        )
        alert_sla_not_signed = WarehouseCommercial.objects.filter(
            sla_status__in=sla_not_signed_statuses,
            warehouse__warehouse_is_active=True
        ).select_related('warehouse', 'warehouse__vendor_code')
        alert_sla_not_signed_count = alert_sla_not_signed.count()
    except:
        alert_sla_not_signed = WarehouseCommercial.objects.none()
        alert_sla_not_signed_count = 0
    
    # Alert 2: Contract Expiring (≤60 days)
    today = timezone.now().date()
    expiry_threshold = today + timedelta(days=60)
    alert_expiring = WarehouseCommercial.objects.filter(
        warehouse__warehouse_is_active=True,
        contract_end_date__lte=expiry_threshold,
        contract_end_date__gte=today
    ).select_related('warehouse', 'warehouse__vendor_code').order_by('contract_end_date')
    alert_expiring_count = alert_expiring.count()
    
    # Alert 3: Low Available Capacity (<15%)
    alert_low_capacity = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        total_capacity__gt=0
    ).annotate(
        utilization=F('available_capacity') * 100.0 / F('total_capacity')
    ).filter(
        utilization__lt=15
    ).select_related('warehouse', 'warehouse__vendor_code')
    alert_low_capacity_count = alert_low_capacity.count()
    
    # Alert 4: Missing Mandatory Documents
    # Warehouses without any commercial data or with null SLA status
    alert_missing_docs = VendorWarehouse.objects.filter(
        warehouse_is_active=True
    ).filter(
        Q(commercial__isnull=True) |
        Q(commercial__sla_status__isnull=True)
    ).select_related('vendor_code').distinct()
    alert_missing_docs_count = alert_missing_docs.count()
    
    # Alert 5: Inactive but Linked to Active Projects
    # This requires checking if warehouse is linked to active projects
    # For now, we'll get inactive warehouses with project count > 0
    alert_inactive_linked = VendorWarehouse.objects.filter(
        warehouse_is_active=False
    ).annotate(
        project_count=Count('projects')
    ).filter(
        project_count__gt=0
    ).select_related('vendor_code')
    alert_inactive_linked_count = alert_inactive_linked.count()
    
    # ========================================================================
    # 3️⃣ SLA & CONTRACT RISK PANEL (Top 10)
    # ========================================================================
    
    # Combine expiring contracts and unsigned SLAs
    contract_risks = []
    
    # Add expiring contracts
    for comm in alert_expiring[:5]:  # Top 5 expiring
        days_left = (comm.contract_end_date - today).days
        contract_risks.append({
            'warehouse': comm.warehouse,
            'vendor': comm.warehouse.vendor_code,
            'sla_status': comm.sla_status.label if comm.sla_status else 'Unknown',
            'contract_end_date': comm.contract_end_date,
            'days_left': days_left,
            'escalation_percentage': comm.escalation_percentage or 0,
            'risk_level': 'critical' if days_left <= 30 else 'warning'
        })
    
    # Add unsigned SLAs
    for comm in alert_sla_not_signed[:5]:  # Top 5 unsigned
        contract_risks.append({
            'warehouse': comm.warehouse,
            'vendor': comm.warehouse.vendor_code,
            'sla_status': comm.sla_status.label if comm.sla_status else 'Not Signed',
            'contract_end_date': comm.contract_end_date,
            'days_left': (comm.contract_end_date - today).days if comm.contract_end_date else None,
            'escalation_percentage': comm.escalation_percentage or 0,
            'risk_level': 'critical'
        })
    
    # Sort by risk level and days left
    contract_risks = sorted(contract_risks, key=lambda x: (
        0 if x['risk_level'] == 'critical' else 1,
        x['days_left'] if x['days_left'] is not None else 999
    ))[:10]
    
    # ========================================================================
    # 4️⃣ CAPACITY UTILIZATION BREAKDOWN
    # ========================================================================
    
    # By Grade — 1 query instead of 3 (one per grade)
    capacity_by_grade = {}
    _grade_rows = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        warehouse__profile__warehouse_grade__code__in=['grade_a', 'grade_b', 'grade_c']
    ).values('warehouse__profile__warehouse_grade__code').annotate(
        total=Sum('total_capacity'),
        available=Sum('available_capacity')
    )
    for row in _grade_rows:
        grade_code = row['warehouse__profile__warehouse_grade__code']
        total = row['total'] or 0
        available = row['available'] or 0
        if total:
            capacity_by_grade[grade_code] = {
                'total': total,
                'available': available,
                'utilized': total - available,
                'utilization_percent': round(((total - available) / total * 100), 1)
            }
    
    # By Top 5 Cities
    capacity_by_city = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        warehouse__warehouse_location_id__isnull=False
    ).values(
        'warehouse__warehouse_location_id__city'
    ).annotate(
        total=Sum('total_capacity'),
        available=Sum('available_capacity')
    ).order_by('-total')[:5]
    
    for city in capacity_by_city:
        city['utilized'] = (city['total'] or 0) - (city['available'] or 0)
        city['utilization_percent'] = round(
            (city['utilized'] / city['total'] * 100) if city['total'] and city['total'] > 0 else 0,
            1
        )
    
    # ========================================================================
    # 5️⃣ RECENT ACTIVITY (Last 10)
    # ========================================================================
    
    # Get recently created/updated warehouses
    recent_warehouses = VendorWarehouse.objects.filter(
        warehouse_is_active=True
    ).select_related('vendor_code').order_by('-warehouse_created_at')[:5]
    
    # Get recently updated vendors
    recent_vendors = VendorCard.objects.filter(
        vendor_is_active=True
    ).order_by('-vendor_created_at')[:5]
    
    # Combine and format activities
    recent_activities = []
    
    for wh in recent_warehouses:
        recent_activities.append({
            'type': 'warehouse_created',
            'icon': 'warehouse',
            'description': f'Warehouse {wh.warehouse_code} created',
            'detail': f'Vendor: {wh.vendor_code.vendor_short_name}',
            'timestamp': wh.warehouse_created_at,
            'link': f'/supply/warehouses/{wh.warehouse_code}/'
        })
    
    for vendor in recent_vendors:
        recent_activities.append({
            'type': 'vendor_created',
            'icon': 'vendor',
            'description': f'Vendor {vendor.vendor_code} added',
            'detail': vendor.vendor_short_name,
            'timestamp': vendor.vendor_created_at,
            'link': f'/supply/vendors/{vendor.vendor_code}/'
        })
    
    # Sort by timestamp and take last 10
    recent_activities = sorted(
        recent_activities,
        key=lambda x: x['timestamp'],
        reverse=True
    )[:10]

    # ========================================================================
    # 6️⃣ RFQ METRICS
    # ========================================================================

    # Open RFQs count
    open_rfqs_count = RFQ.objects.filter(status='open').count()

    # ========================================================================
    # CONTEXT
    # ========================================================================

    context = {
        # 1️⃣ Global KPIs
        'total_warehouses': total_warehouses,
        'active_vendors': active_vendors,
        'sla_signed_percentage': sla_signed_percentage,
        'sla_signed_count': sla_signed_count,
        'total_wh_with_commercial': total_wh_with_commercial,
        'available_capacity': available_capacity,
        'total_capacity': total_capacity,
        'utilized_capacity': utilized_capacity,
        'utilization_percent': utilization_percent,
        'warehouses_24x7_count': warehouses_24x7_count,
        'temp_controlled_count': temp_controlled_count,
        
        # 2️⃣ Action Alerts
        'alert_sla_not_signed_count': alert_sla_not_signed_count,
        'alert_expiring_count': alert_expiring_count,
        'alert_low_capacity_count': alert_low_capacity_count,
        'alert_missing_docs_count': alert_missing_docs_count,
        'alert_inactive_linked_count': alert_inactive_linked_count,
        
        # 3️⃣ Contract Risks
        'contract_risks': contract_risks,
        
        # 4️⃣ Capacity Utilization
        'capacity_by_grade': capacity_by_grade,
        'capacity_by_city': capacity_by_city,
        
        # 5️⃣ Recent Activity
        'recent_activities': recent_activities,

        # 6️⃣ RFQ Metrics
        'open_rfqs_count': open_rfqs_count,
    }

    return render(request, 'dashboards/supply_manager_dashboard.html', context)


# ============================================================================
# LOCATION VIEWS
# ============================================================================

@login_required
def location_list(request):
    """List all locations with warehouse and project counts"""
    # Materialise once; use batch counts instead of N+1 per location
    _locations_list = list(Location.objects.filter(is_active=True).order_by('state', 'city'))
    _location_ids = [loc.id for loc in _locations_list]

    # Batch warehouse counts per location (1 query)
    _wh_counts = dict(
        VendorWarehouse.objects.filter(
            warehouse_is_active=True,
            warehouse_location_id__in=_location_ids
        ).values('warehouse_location_id').annotate(
            cnt=Count('id')
        ).values_list('warehouse_location_id', 'cnt')
    )
    # Batch project counts per location (1 query)
    _proj_counts = dict(
        ProjectCode.objects.filter(
            vendor_warehouse__warehouse_location_id__in=_location_ids
        ).values('vendor_warehouse__warehouse_location_id').annotate(
            cnt=Count('project_id', distinct=True)
        ).values_list('vendor_warehouse__warehouse_location_id', 'cnt')
    )
    for location in _locations_list:
        location.warehouse_count = _wh_counts.get(location.id, 0)
        location.project_count = _proj_counts.get(location.id, 0)

    locations = _locations_list
    total_locations = len(_locations_list)
    states_count = len({loc.state for loc in _locations_list if loc.state})
    warehouses_count = VendorWarehouse.objects.filter(warehouse_is_active=True).count()
    
    return render(request, 'supply/location_list.html', {
        'locations': locations,
        'total_locations': total_locations,
        'states_count': states_count,
        'warehouses_count': warehouses_count,
        'page_title': 'Locations'
    })


@login_required
def location_create(request):
    """Create new location"""
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid():
            location = form.save()
            messages.success(
                request, 
                f'Location "{location.city}, {location.state}" created successfully!'
            )
            return redirect('supply:location_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = LocationForm()
    
    return render(request, 'supply/location_form.html', {
        'form': form,
        'action': 'Create',
        'page_title': 'Add New Location'
    })


@login_required
def location_edit(request, location_id):
    """Edit existing location"""
    location = get_object_or_404(Location, id=location_id)
    
    if request.method == 'POST':
        form = LocationForm(request.POST, instance=location)
        if form.is_valid():
            form.save()
            messages.success(request, 'Location updated successfully!')
            return redirect('supply:location_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = LocationForm(instance=location)
    
    return render(request, 'supply/location_form.html', {
        'form': form,
        'location': location,
        'action': 'Update',
        'page_title': f'Edit Location - {location.city}, {location.state}'
    })


@login_required
@require_role('admin', 'super_user')
def location_delete(request, location_id):
    """Delete/deactivate location"""
    location = get_object_or_404(Location, id=location_id)
    
    # Check if location is being used
    warehouse_count = VendorWarehouse.objects.filter(warehouse_location_id=location).count()
    project_count = ProjectCode.objects.filter(
        vendor_warehouse_code__warehouse_location_id=location
    ).distinct().count()
    
    if request.method == 'POST':
        if warehouse_count > 0 or project_count > 0:
            messages.error(
                request, 
                f'Cannot delete location. It is being used by {warehouse_count} warehouse(s) and {project_count} project(s).'
            )
            return redirect('supply:location_list')
        
        location.is_active = False
        location.save()
        messages.success(request, f'Location "{location.city}, {location.state}" has been deactivated.')
        return redirect('supply:location_list')
    
    return render(request, 'supply/location_delete_confirm.html', {
        'location': location,
        'warehouse_count': warehouse_count,
        'project_count': project_count,
        'page_title': f'Delete Location - {location.city}, {location.state}'
    })



def get_cities_by_state(request):
    """AJAX endpoint to get cities for selected state"""
    state_name = request.GET.get('state', None)
    
    if not state_name:
        return JsonResponse({'cities': []})
    
    try:
        state_obj = StateCode.objects.get(state_name=state_name)
        cities = CityCode.objects.filter(
            state_code=state_obj.state_code,
            is_active=True
        ).order_by('city_name').values('city_name')
        
        city_list = [{'value': city['city_name'], 'label': city['city_name']} for city in cities]
        return JsonResponse({'cities': city_list})
    except StateCode.DoesNotExist:
        return JsonResponse({'cities': []})

# ============================================================================
# VENDOR CARD VIEWS
# ============================================================================

@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice', 'operation_controller', 'operation_manager')
def vendor_list(request):
    """List all vendor cards with search and filtering"""

    from projects.models import ProjectCode

    vendors = VendorCard.objects.annotate(
        warehouse_count=Count('warehouses', filter=Q(warehouses__warehouse_is_active=True))
    ).prefetch_related(
        Prefetch('contacts', queryset=VendorContact.objects.filter(vendor_contact_is_active=True).order_by('-vendor_contact_is_primary'))
    ).order_by('vendor_short_name')

    # Search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        vendors = vendors.filter(
            Q(vendor_code__icontains=search_query) |
            Q(vendor_legal_name__icontains=search_query) |
            Q(vendor_short_name__icontains=search_query) |
            Q(vendor_gstin__icontains=search_query)
        )

    # Active/Inactive filter
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        vendors = vendors.filter(vendor_is_active=True)
    elif status_filter == 'inactive':
        vendors = vendors.filter(vendor_is_active=False)

    # Stats — 3 queries instead of 4
    _vc_agg = VendorCard.objects.aggregate(
        total=Count('vendor_code'),
        active=Count('vendor_code', filter=Q(vendor_is_active=True)),
    )
    stats = {
        'total': _vc_agg['total'],
        'active': _vc_agg['active'],
        'warehouses': VendorWarehouse.objects.filter(warehouse_is_active=True).count(),
        'locations': Location.objects.filter(is_active=True).count(),
    }

    # Pagination
    paginator = Paginator(vendors, 20)
    page = request.GET.get('page', 1)
    vendors_page = paginator.get_page(page)

    # Batch-fetch projects for all vendors on this page (1 query) instead of N+1
    _page_vendor_names = [v.vendor_short_name for v in vendors_page]
    _all_vendor_projects = list(
        ProjectCode.objects.filter(
            vendor_name__in=_page_vendor_names
        ).exclude(
            project_status='Inactive'
        ).prefetch_related(
            'project_cards',
            'project_cards__storage_rates',
            'project_cards__storage_rates__space_type',
        )
    )
    # Group by vendor_name
    from collections import defaultdict
    _projects_by_vendor = defaultdict(list)
    for _p in _all_vendor_projects:
        _projects_by_vendor[_p.vendor_name].append(_p)

    # Annotate each vendor from the pre-fetched data
    for vendor in vendors_page:
        vendor_projects = _projects_by_vendor.get(vendor.vendor_short_name, [])
        vendor.project_count = len(vendor_projects)

        # Calculate total min billable area and amount for VENDOR side
        total_min_area_vendor = 0
        total_min_amount_vendor = 0

        for project in vendor_projects:
            if project.project_cards.exists():
                project_card = project.project_cards.first()
                if project_card.storage_rates.exists():
                    # Get vendor rate (rate_for='vendor')
                    vendor_rate = next(
                        (r for r in project_card.storage_rates.all() if r.rate_for == 'vendor'),
                        None
                    )
                    if vendor_rate:
                        if vendor_rate.minimum_billable_area:
                            area_value = float(vendor_rate.minimum_billable_area)
                            # Check if space type is pallets
                            if vendor_rate.space_type and 'pallet' in vendor_rate.space_type.label.lower():
                                # Convert pallets to sq ft (1 pallet = 25 sq ft)
                                total_min_area_vendor += area_value * 25
                            else:
                                # For sq ft or other units, use value directly
                                total_min_area_vendor += area_value
                        if vendor_rate.monthly_billable_amount:
                            total_min_amount_vendor += float(vendor_rate.monthly_billable_amount)

        vendor.total_min_area_vendor = total_min_area_vendor
        vendor.total_min_amount_vendor = total_min_amount_vendor

    context = {
        'vendors': vendors_page,
        'stats': stats,
        'search_query': search_query,
        'status_filter': status_filter,
        'filtered_count': vendors.count(),
        'page_obj': vendors_page,
    }

    return render(request, 'supply/vendor_list.html', context)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice', 'operation_controller', 'operation_manager')
def vendor_detail(request, vendor_code):
    """View vendor card details with related data"""

    vendor = get_object_or_404(VendorCard, vendor_code=vendor_code)

    # Get contacts using the correct related name
    contacts = VendorContact.objects.filter(
        vendor_code_id=vendor.vendor_code,
        vendor_contact_is_active=True
    ).order_by('-vendor_contact_is_primary', 'vendor_contact_person')

    # Get warehouses using the correct related name
    warehouses = VendorWarehouse.objects.filter(
        vendor_code=vendor,
        warehouse_is_active=True
    ).select_related('warehouse_location_id')

    # Calculate stats
    active_warehouses = warehouses.count()
    # Accurate locations count - distinct cities from active warehouses
    locations_count = warehouses.values('warehouse_location_id__city').exclude(
        warehouse_location_id__city__isnull=True
    ).distinct().count()

    # Get projects using this vendor (exclude Inactive projects)
    from projects.models import ProjectCode
    from operations.models_projectcard import ProjectCard, StorageRate
    from decimal import Decimal

    projects = ProjectCode.objects.filter(
        vendor_name=vendor.vendor_short_name
    ).exclude(
        project_status='Inactive'
    ).select_related('client_card').order_by('-created_at')

    # Calculate total space occupied by linked projects + summary metrics
    total_space_sqft = Decimal('0')
    total_min_area = Decimal('0')
    total_min_amount = Decimal('0')
    unique_clients = set()

    for project in projects:
        try:
            # Collect unique clients
            if project.client_card:
                unique_clients.add(project.client_card.client_short_name)

            # Get the active project card
            project_card = ProjectCard.objects.filter(
                project=project,
                is_active=True
            ).select_related('project').first()

            if project_card:
                # Get vendor-side storage rates with space_type
                storage_rates = StorageRate.objects.filter(
                    project_card=project_card,
                    rate_for='vendor'
                ).select_related('space_type')

                for rate in storage_rates:
                    # Check if minimum_billable_area exists
                    if rate.minimum_billable_area and rate.minimum_billable_area > 0:
                        if rate.space_type:
                            # Check space type label to determine if it's pallets
                            space_type_label = rate.space_type.label.lower()

                            # If space type is pallets, convert to sq ft (1 pallet = 25 sq ft)
                            if 'pallet' in space_type_label:
                                total_space_sqft += rate.minimum_billable_area * Decimal('25')
                            else:
                                # For sq ft, sq meter, etc., use the value directly
                                total_space_sqft += rate.minimum_billable_area
                        else:
                            # If no space type specified, assume it's sq ft
                            total_space_sqft += rate.minimum_billable_area

                        # Add to total min area (for summary)
                        total_min_area += rate.minimum_billable_area

                    # Add to total min amount (for summary)
                    if rate.monthly_billable_amount and rate.monthly_billable_amount > 0:
                        total_min_amount += rate.monthly_billable_amount
        except Exception as e:
            # Log the error but continue with other projects
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error calculating space for project {project.project_id}: {str(e)}")
            continue

    # Get all projects that can be linked (not already linked to this vendor)
    unlinked_projects = ProjectCode.objects.exclude(
        vendor_name=vendor.vendor_short_name
    ).filter(
        series_type='WAAS',
        project_status__in=['Active', 'Operation Not Started', 'Notice Period']
    ).select_related('client_card').order_by('project_code')

    context = {
        'vendor': vendor,
        'contacts': contacts,
        'warehouses': warehouses,
        'projects': projects,
        'unlinked_projects': unlinked_projects,
        'active_warehouses': active_warehouses,
        'locations_count': locations_count,
        'projects_count': projects.count(),
        'total_space_sqft': total_space_sqft,
        # Summary metrics for projects section
        'unique_clients': unique_clients,
        'total_min_area': total_min_area,
        'total_min_amount': total_min_amount,
    }

    return render(request, 'supply/vendor_detail.html', context)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice')
@transaction.atomic
def vendor_create(request):
    """Create new vendor card with contacts"""
    
    if request.method == 'POST':
        form = VendorCardForm(request.POST)
        contact_formset = VendorContactFormSet(request.POST, prefix='contacts')
        
        print(f"Form valid: {form.is_valid()}")
        print(f"Form errors: {form.errors}")
        print(f"Formset valid: {contact_formset.is_valid()}")
        print(f"Formset errors: {contact_formset.errors}")
        print(f"POST data: {request.POST}")
        if form.is_valid() and contact_formset.is_valid():
            # Save vendor
            vendor = form.save()
            
            # Save contacts
            contacts = contact_formset.save(commit=False)
            for contact in contacts:
                if contact.vendor_contact_person:  # Only save if contact has data
                    contact.vendor_code = vendor
                    contact.save()
            
            messages.success(request, f'Vendor {vendor.vendor_short_name} created successfully!')
            return redirect('supply:vendor_detail', vendor_code=vendor.vendor_code)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = VendorCardForm()
        contact_formset = VendorContactFormSet(prefix='contacts')
    
    context = {
        'form': form,
        'contact_formset': contact_formset,
        'action': 'Create'
    }
    
    return render(request, 'supply/vendor_form.html', context)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice')
@transaction.atomic
def vendor_update(request, vendor_code):
    """Update vendor card and contacts"""
    
    vendor = get_object_or_404(VendorCard, vendor_code=vendor_code)
    
    if request.method == 'POST':
        form = VendorCardForm(request.POST, instance=vendor)
        contact_formset = VendorContactFormSet(
            request.POST,
            instance=vendor,
            prefix='contacts'
        )
        
        if form.is_valid() and contact_formset.is_valid():
            vendor = form.save()
            contacts = contact_formset.save(commit=False)
            for contact in contacts:
                if contact.vendor_contact_person:
                    contact.save()
            for contact in contact_formset.deleted_objects:
                contact.delete()
            
            messages.success(request, f'Vendor {vendor.vendor_short_name} updated successfully!')
            return redirect('supply:vendor_detail', vendor_code=vendor.vendor_code)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = VendorCardForm(instance=vendor)
        contact_formset = VendorContactFormSet(instance=vendor, prefix='contacts')
    
    context = {
        'form': form,
        'contact_formset': contact_formset,
        'vendor': vendor,
        'action': 'Update'
    }
    
    return render(request, 'supply/vendor_form.html', context)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice')
def vendor_toggle_active(request, vendor_code):
    """Toggle vendor active status"""
    
    if request.method == 'POST':
        vendor = get_object_or_404(VendorCard, vendor_code=vendor_code)
        vendor.vendor_is_active = not vendor.vendor_is_active
        vendor.save()
        
        status = 'activated' if vendor.vendor_is_active else 'deactivated'
        messages.success(request, f'Vendor {vendor.vendor_short_name} {status}!')
        
        return redirect('supply:vendor_detail', vendor_code=vendor_code)
    
    return redirect('supply:vendor_list')


# ============================================================================
# WAREHOUSE VIEWS
# ============================================================================

@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice', 'operation_controller')
def warehouse_list(request):
    """List all warehouses with search and filtering"""
    from projects.models import ProjectCode

    warehouses = VendorWarehouse.objects.select_related(
        'vendor_code',
        'warehouse_location_id'
    ).prefetch_related(
        'capacity',
        'projects'
    ).order_by('-warehouse_created_at')

    # Search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        warehouses = warehouses.filter(
            Q(warehouse_code__icontains=search_query) |
            Q(warehouse_name__icontains=search_query) |
            Q(vendor_code__vendor_short_name__icontains=search_query) |
            Q(warehouse_location_id__city__icontains=search_query)
        )

    # Vendor filter
    vendor_filter = request.GET.get('vendor', '')
    if vendor_filter:
        warehouses = warehouses.filter(vendor_code__vendor_code=vendor_filter)

    # Location filter
    location_filter = request.GET.get('location', '')
    if location_filter:
        warehouses = warehouses.filter(warehouse_location_id=location_filter)

    # Active/Inactive filter
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        warehouses = warehouses.filter(warehouse_is_active=True)
    elif status_filter == 'inactive':
        warehouses = warehouses.filter(warehouse_is_active=False)

    # Calculate stats from all warehouses (1 query instead of 4)
    _wh_stats = VendorWarehouse.objects.aggregate(
        total_warehouses=Count('id'),
        active_warehouses=Count('id', filter=Q(warehouse_is_active=True)),
        locations_count=Count('warehouse_location_id', distinct=True),
        vendors_count=Count('vendor_code', distinct=True),
    )
    total_warehouses = _wh_stats['total_warehouses']
    active_warehouses = _wh_stats['active_warehouses']
    locations_count = _wh_stats['locations_count']
    vendors_count = _wh_stats['vendors_count']

    # Pagination
    paginator = Paginator(warehouses, 20)
    page = request.GET.get('page', 1)
    warehouses_page = paginator.get_page(page)

    # Batch-fetch capacities and projects for all warehouses on this page
    _page_wh_ids = [w.id for w in warehouses_page]

    # Batch capacity lookup (1 query instead of N)
    _capacity_map = {
        c.warehouse_id: c
        for c in WarehouseCapacity.objects.filter(warehouse_id__in=_page_wh_ids)
    }

    # Batch project lookup (1 query instead of N)
    _all_wh_projects = list(
        ProjectCode.objects.filter(
            vendor_warehouse__in=_page_wh_ids
        ).exclude(
            project_status='Inactive'
        ).prefetch_related(
            'project_cards',
            'project_cards__storage_rates',
            'project_cards__storage_rates__space_type',
        )
    )
    from collections import defaultdict
    _projects_by_wh = defaultdict(list)
    for _p in _all_wh_projects:
        if _p.vendor_warehouse_id:
            _projects_by_wh[_p.vendor_warehouse_id].append(_p)

    # Annotate each warehouse from pre-fetched data
    for warehouse in warehouses_page:
        cap = _capacity_map.get(warehouse.id)
        warehouse.available_capacity = cap.available_capacity or 0 if cap else 0

        warehouse_projects = _projects_by_wh.get(warehouse.id, [])
        warehouse.projects_count = len(warehouse_projects)

        # Calculate total min billable area and amount for VENDOR side
        total_min_area_vendor = 0
        total_min_amount_vendor = 0

        for project in warehouse_projects:
            if project.project_cards.exists():
                project_card = project.project_cards.first()
                if project_card.storage_rates.exists():
                    # Get vendor rate (rate_for='vendor')
                    vendor_rate = next(
                        (r for r in project_card.storage_rates.all() if r.rate_for == 'vendor'),
                        None
                    )
                    if vendor_rate:
                        if vendor_rate.minimum_billable_area:
                            area_value = float(vendor_rate.minimum_billable_area)
                            # Check if space type is pallets
                            if vendor_rate.space_type and 'pallet' in vendor_rate.space_type.label.lower():
                                # Convert pallets to sq ft (1 pallet = 25 sq ft)
                                total_min_area_vendor += area_value * 25
                            else:
                                # For sq ft or other units, use value directly
                                total_min_area_vendor += area_value
                        if vendor_rate.monthly_billable_amount:
                            total_min_amount_vendor += float(vendor_rate.monthly_billable_amount)

        warehouse.total_min_area_vendor = total_min_area_vendor
        warehouse.total_min_amount_vendor = total_min_amount_vendor

    # Get filter options
    all_vendors = VendorCard.objects.filter(vendor_is_active=True).order_by('vendor_short_name')

    context = {
        'warehouses': warehouses_page,
        'search_query': search_query,
        'vendor_filter': vendor_filter,
        'location_filter': location_filter,
        'status_filter': status_filter,
        'all_vendors': all_vendors,
        'total_warehouses': total_warehouses,
        'active_warehouses': active_warehouses,
        'locations_count': locations_count,
        'vendors_count': vendors_count,
        'filtered_count': warehouses.count(),
        'page_obj': warehouses_page,
    }

    return render(request, 'supply/warehouse_list.html', context)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice', 'operation_controller')
def warehouse_detail(request, warehouse_code):
    """View warehouse details with inline editing and project linking"""
    
    warehouse = get_object_or_404(
        VendorWarehouse.objects.select_related(
            'vendor_code',
            'warehouse_location_id'
        ),
        warehouse_code=warehouse_code
    )
    
    # Get or create related objects
    profile, _ = WarehouseProfile.objects.get_or_create(warehouse_id=warehouse.id)
    capacity, _ = WarehouseCapacity.objects.get_or_create(warehouse_id=warehouse.id)
    commercial, _ = WarehouseCommercial.objects.get_or_create(warehouse_id=warehouse.id)
    
    # Assign to warehouse object for template access
    warehouse.profile = profile
    warehouse.capacity = capacity
    warehouse.commercial = commercial
    
    # Get contacts
    warehouse_contacts = WarehouseContact.objects.filter(
        warehouse_code_id=warehouse.warehouse_code
    ).order_by('-warehouse_contact_is_primary', 'warehouse_contact_person')
    
    # Get documents
    try:
        warehouse_documents = VendorWarehouseDocument.objects.get(
            warehouse_code_id=warehouse.warehouse_code
        )
    except VendorWarehouseDocument.DoesNotExist:
        warehouse_documents = None
    
    # Get photos
    warehouse_photos = WarehousePhoto.objects.filter(
        warehouse_code_id=warehouse.warehouse_code
    ).order_by('-uploaded_at')
    
    # Get linked projects with vendor rates (exclude Inactive projects)
    # Get linked projects
    from projects.models import ProjectCode

    linked_projects = ProjectCode.objects.filter(
        vendor_warehouse__warehouse_code=warehouse_code,
        series_type='WAAS'
    ).exclude(
        project_status='Inactive'
    ).select_related(
        'client_card',
        'vendor_warehouse'
    ).order_by('-created_at')
    
    # Get unlinked WAAS projects (only Active, Operation Not Started, Notice Period)
    unlinked_projects = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Operation Not Started', 'Notice Period']
    ).exclude(
        vendor_warehouse__warehouse_code=warehouse_code
    ).filter(
        vendor_warehouse__isnull=True
    ).select_related('client_card').order_by('client_name', 'project_code')
    
    # Calculate summary stats
    total_min_area = 0
    total_min_amount = 0

    # Calculate total min billable area and amount for VENDOR side
    for project in linked_projects:
        if project.project_cards.exists():
            project_card = project.project_cards.first()
            if project_card.storage_rates.exists():
                # Get vendor rate (rate_for='vendor')
                vendor_rate = project_card.storage_rates.filter(rate_for='vendor').first()
                if vendor_rate:
                    if vendor_rate.minimum_billable_area:
                        area_value = float(vendor_rate.minimum_billable_area)
                        # Check if space type is pallets
                        if vendor_rate.space_type and 'pallet' in vendor_rate.space_type.label.lower():
                            # Convert pallets to sq ft (1 pallet = 25 sq ft)
                            total_min_area += area_value * 25
                        else:
                            # For sq ft or other units, use value directly
                            total_min_area += area_value
                    if vendor_rate.monthly_billable_amount:
                        total_min_amount += float(vendor_rate.monthly_billable_amount)

    unique_clients = set(
        p.client_card.client_short_name
        for p in linked_projects
        if p.client_card
    )
    
    # Handle project linking/unlinking
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'link':
            project_ids = request.POST.getlist('project_ids')
            if project_ids:
                projects = ProjectCode.objects.filter(project_id__in=project_ids)
                for project in projects:
                    project.vendor_warehouse = warehouse
                    project.save()
                messages.success(request, f'{len(project_ids)} project(s) linked successfully!')
            else:
                messages.warning(request, 'No projects selected to link.')
                
        elif action == 'unlink':
            project_id = request.POST.get('project_id')
            if project_id:
                try:
                    project = ProjectCode.objects.get(project_id=project_id)
                    project.vendor_warehouse = None
                    project.save()
                    messages.success(request, f'Project {project.project_code} unlinked successfully!')
                except ProjectCode.DoesNotExist:
                    messages.error(request, 'Project not found.')
        
        return redirect('supply:warehouse_detail', warehouse_code=warehouse_code)
    
    # Get dropdown data for inline editing
    from dropdown_master_data.models import (
        WarehouseGrade, PropertyType, BusinessType, StorageUnit, SLAStatus
    )
    from supply.models import Location

    warehouse_grades = WarehouseGrade.objects.filter(is_active=True).order_by('display_order')
    property_types = PropertyType.objects.filter(is_active=True).order_by('display_order')
    business_types = BusinessType.objects.filter(is_active=True).order_by('display_order')
    storage_units = StorageUnit.objects.filter(is_active=True).order_by('label')
    sla_statuses = SLAStatus.objects.filter(is_active=True).order_by('display_order')
    warehouse_locations = Location.objects.filter(is_active=True).order_by('state', 'city')

    context = {
        'warehouse': warehouse,
        'warehouse_contacts': warehouse_contacts,
        'warehouse_documents': warehouse_documents,
        'warehouse_photos': warehouse_photos,
        'linked_projects': linked_projects,
        'unlinked_projects': unlinked_projects,
        'linked_projects_count': linked_projects.count(),
        'total_min_area': total_min_area,
        'total_min_amount': total_min_amount,
        'unique_clients': unique_clients,
        'warehouse_grades': warehouse_grades,
        'property_types': property_types,
        'business_types': business_types,
        'storage_units': storage_units,
        'sla_statuses': sla_statuses,
        'warehouse_locations': warehouse_locations,
    }
    
    return render(request, 'supply/warehouse_detail.html', context)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice')
@transaction.atomic
def warehouse_create(request):
    """Create new warehouse with all related data - single page form"""
    from dropdown_master_data.models import WarehouseGrade, PropertyType, BusinessType, StorageUnit, SLAStatus

    if request.method == 'POST':
        warehouse_form = VendorWarehouseForm(request.POST, request.FILES)
        profile_form = WarehouseProfileForm(request.POST)
        capacity_form = WarehouseCapacityForm(request.POST)
        commercial_form = WarehouseCommercialForm(request.POST)
        contact_formset = WarehouseContactFormSet(request.POST, prefix='contacts')
        document_form = VendorWarehouseDocumentForm(request.POST, request.FILES)

        if (warehouse_form.is_valid() and profile_form.is_valid() and
            capacity_form.is_valid() and commercial_form.is_valid() and
            contact_formset.is_valid() and
            document_form.is_valid()):

            # Save warehouse
            warehouse = warehouse_form.save()
            warehouse.refresh_from_db()  # Ensure we have the latest data including auto-generated code

            # Validate warehouse code was generated
            if not warehouse.warehouse_code:
                messages.error(request, 'Failed to generate warehouse code. Please ensure warehouse location is selected.')
                return redirect('supply:warehouse_create')

            # Save profile
            profile = profile_form.save(commit=False)
            profile.warehouse_id = warehouse.id
            profile.save()

            # Save capacity
            capacity = capacity_form.save(commit=False)
            capacity.warehouse_id = warehouse.id
            capacity.save()

            # Save commercial
            commercial = commercial_form.save(commit=False)
            commercial.warehouse_id = warehouse.id
            commercial.save()

            # Save contacts
            contacts = contact_formset.save(commit=False)
            for contact in contacts:
                if contact.warehouse_contact_person:
                    contact.warehouse_code_id = warehouse.warehouse_code
                    contact.save()

            # Delete marked contacts
            for contact in contact_formset.deleted_objects:
                contact.delete()

            # Note: Photos are now uploaded separately via warehouse_photos_upload view

            # Save documents
            if any([document_form.cleaned_data.get(field) for field in document_form.fields]):
                document = document_form.save(commit=False)
                document.vendor_code = warehouse.vendor_code
                document.warehouse_code_id = warehouse.warehouse_code
                document.warehouse_doc_uploaded_by = request.user

                # Handle Legal & Compliance Documents (multiple files)
                import uuid
                from django.core.files.storage import default_storage

                # Rent Agreements
                rent_agreement_files = request.FILES.getlist('rent_agreements')
                if rent_agreement_files:
                    rent_agreements_data = {}
                    for idx, file in enumerate(rent_agreement_files):
                        file_id = str(uuid.uuid4())
                        file_path = f'warehouse_docs/legal/rent_agreements/{warehouse.warehouse_code}/{file_id}_{file.name}'
                        saved_path = default_storage.save(file_path, file)
                        rent_agreements_data[file_id] = {
                            'filename': file.name,
                            'path': saved_path,
                            'uploaded_at': str(timezone.now())
                        }
                    document.warehouse_owner_agreements = rent_agreements_data

                # SLA Documents
                sla_files = request.FILES.getlist('sla_documents')
                if sla_files:
                    sla_docs_data = {}
                    for idx, file in enumerate(sla_files):
                        file_id = str(uuid.uuid4())
                        file_path = f'warehouse_docs/legal/sla/{warehouse.warehouse_code}/{file_id}_{file.name}'
                        saved_path = default_storage.save(file_path, file)
                        sla_docs_data[file_id] = {
                            'filename': file.name,
                            'path': saved_path,
                            'uploaded_at': str(timezone.now())
                        }
                    document.warehouse_sla_documents = sla_docs_data

                # Other Legal Documents
                other_legal_files = request.FILES.getlist('other_legal_docs')
                if other_legal_files:
                    other_docs_data = {}
                    for idx, file in enumerate(other_legal_files):
                        file_id = str(uuid.uuid4())
                        file_path = f'warehouse_docs/legal/other/{warehouse.warehouse_code}/{file_id}_{file.name}'
                        saved_path = default_storage.save(file_path, file)
                        other_docs_data[file_id] = {
                            'filename': file.name,
                            'path': saved_path,
                            'uploaded_at': str(timezone.now())
                        }
                    document.warehouse_other_legal_docs = other_docs_data

                document.save()

            messages.success(request, f'Warehouse {warehouse.warehouse_code} created successfully!')
            return redirect('supply:warehouse_detail', warehouse_code=warehouse.warehouse_code)
        else:
            messages.error(request, 'Please correct the errors below.')

    else:
        warehouse_form = VendorWarehouseForm()
        profile_form = WarehouseProfileForm()
        capacity_form = WarehouseCapacityForm()
        commercial_form = WarehouseCommercialForm()
        contact_formset = WarehouseContactFormSet(prefix='contacts')
        document_form = VendorWarehouseDocumentForm()

    # Add dropdown master data to context
    context = {
        'form': warehouse_form,
        'profile_form': profile_form,
        'capacity_form': capacity_form,
        'commercial_form': commercial_form,
        'contact_formset': contact_formset,
        'document_form': document_form,
        # Dropdown master data
        'grades': WarehouseGrade.objects.filter(is_active=True).order_by('label'),
        'property_types': PropertyType.objects.filter(is_active=True).order_by('label'),
        'business_types': BusinessType.objects.filter(is_active=True).order_by('label'),
        'storage_units': StorageUnit.objects.filter(is_active=True).order_by('label'),
        'sla_statuses': SLAStatus.objects.filter(is_active=True).order_by('label'),
    }

    return render(request, 'supply/warehouse_create.html', context)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice')
@transaction.atomic
def warehouse_update(request, warehouse_code):
    """Update warehouse and all related data - full-page edit form"""
    from dropdown_master_data.models import WarehouseGrade, PropertyType, BusinessType, StorageUnit, SLAStatus

    warehouse = get_object_or_404(VendorWarehouse, warehouse_code=warehouse_code)

    # Get or create related objects
    profile, _ = WarehouseProfile.objects.get_or_create(warehouse_id=warehouse.id)
    capacity, _ = WarehouseCapacity.objects.get_or_create(warehouse_id=warehouse.id)
    commercial, _ = WarehouseCommercial.objects.get_or_create(warehouse_id=warehouse.id)

    # Get documents if exist
    try:
        documents = VendorWarehouseDocument.objects.get(warehouse_code_id=warehouse.warehouse_code)
    except VendorWarehouseDocument.DoesNotExist:
        documents = None

    if request.method == 'POST':
        warehouse_form = VendorWarehouseForm(request.POST, request.FILES, instance=warehouse)
        profile_form = WarehouseProfileForm(request.POST, instance=profile)
        capacity_form = WarehouseCapacityForm(request.POST, instance=capacity)
        commercial_form = WarehouseCommercialForm(request.POST, instance=commercial)
        contact_formset = WarehouseContactFormSet(request.POST, instance=warehouse, prefix='contacts')

        if documents:
            document_form = VendorWarehouseDocumentForm(request.POST, request.FILES, instance=documents)
        else:
            document_form = VendorWarehouseDocumentForm(request.POST, request.FILES)

        if (warehouse_form.is_valid() and profile_form.is_valid() and
            capacity_form.is_valid() and commercial_form.is_valid() and
            contact_formset.is_valid() and document_form.is_valid()):

            # Save warehouse
            warehouse = warehouse_form.save()

            # Save profile, capacity, commercial
            profile_form.save()
            capacity_form.save()
            commercial_form.save()

            # Save contacts
            contacts = contact_formset.save(commit=False)
            for contact in contacts:
                if contact.warehouse_contact_person:
                    contact.warehouse_code_id = warehouse.warehouse_code
                    contact.save()

            for contact in contact_formset.deleted_objects:
                contact.delete()

            # Note: Photos are now uploaded separately via warehouse_photos_upload view

            # Save documents
            if any([document_form.cleaned_data.get(field) for field in document_form.fields]):
                document = document_form.save(commit=False)
                if not document.pk:
                    document.vendor_code = warehouse.vendor_code
                    document.warehouse_code_id = warehouse.warehouse_code
                document.warehouse_doc_uploaded_by = request.user

                # Handle Legal & Compliance Documents (multiple files) - ADD to existing
                import uuid
                from django.core.files.storage import default_storage
                from django.utils import timezone

                # Rent Agreements - Append to existing
                rent_agreement_files = request.FILES.getlist('rent_agreements')
                if rent_agreement_files:
                    existing_rent = document.warehouse_owner_agreements or {}
                    for idx, file in enumerate(rent_agreement_files):
                        file_id = str(uuid.uuid4())
                        file_path = f'warehouse_docs/legal/rent_agreements/{warehouse.warehouse_code}/{file_id}_{file.name}'
                        saved_path = default_storage.save(file_path, file)
                        existing_rent[file_id] = {
                            'filename': file.name,
                            'path': saved_path,
                            'uploaded_at': str(timezone.now())
                        }
                    document.warehouse_owner_agreements = existing_rent

                # SLA Documents - Append to existing
                sla_files = request.FILES.getlist('sla_documents')
                if sla_files:
                    existing_sla = document.warehouse_sla_documents or {}
                    for idx, file in enumerate(sla_files):
                        file_id = str(uuid.uuid4())
                        file_path = f'warehouse_docs/legal/sla/{warehouse.warehouse_code}/{file_id}_{file.name}'
                        saved_path = default_storage.save(file_path, file)
                        existing_sla[file_id] = {
                            'filename': file.name,
                            'path': saved_path,
                            'uploaded_at': str(timezone.now())
                        }
                    document.warehouse_sla_documents = existing_sla

                # Other Legal Documents - Append to existing
                other_legal_files = request.FILES.getlist('other_legal_docs')
                if other_legal_files:
                    existing_other = document.warehouse_other_legal_docs or {}
                    for idx, file in enumerate(other_legal_files):
                        file_id = str(uuid.uuid4())
                        file_path = f'warehouse_docs/legal/other/{warehouse.warehouse_code}/{file_id}_{file.name}'
                        saved_path = default_storage.save(file_path, file)
                        existing_other[file_id] = {
                            'filename': file.name,
                            'path': saved_path,
                            'uploaded_at': str(timezone.now())
                        }
                    document.warehouse_other_legal_docs = existing_other

                document.save()

            messages.success(request, f'Warehouse {warehouse.warehouse_code} updated successfully!')
            return redirect('supply:warehouse_detail', warehouse_code=warehouse.warehouse_code)
        else:
            messages.error(request, 'Please correct the errors below.')

    else:
        warehouse_form = VendorWarehouseForm(instance=warehouse)
        profile_form = WarehouseProfileForm(instance=profile)
        capacity_form = WarehouseCapacityForm(instance=capacity)
        commercial_form = WarehouseCommercialForm(instance=commercial)
        contact_formset = WarehouseContactFormSet(instance=warehouse, prefix='contacts')

        if documents:
            document_form = VendorWarehouseDocumentForm(instance=documents)
        else:
            document_form = VendorWarehouseDocumentForm()

    # Get existing photos for display
    existing_photos = WarehousePhoto.objects.filter(warehouse_code=warehouse).order_by('-uploaded_at')

    # Add dropdown master data to context
    context = {
        'warehouse': warehouse,
        'form': warehouse_form,
        'profile_form': profile_form,
        'capacity_form': capacity_form,
        'commercial_form': commercial_form,
        'contact_formset': contact_formset,
        'existing_photos': existing_photos,
        'document_form': document_form,
        # Dropdown master data
        'grades': WarehouseGrade.objects.filter(is_active=True).order_by('label'),
        'property_types': PropertyType.objects.filter(is_active=True).order_by('label'),
        'business_types': BusinessType.objects.filter(is_active=True).order_by('label'),
        'storage_units': StorageUnit.objects.filter(is_active=True).order_by('label'),
        'sla_statuses': SLAStatus.objects.filter(is_active=True).order_by('label'),
    }

    return render(request, 'supply/warehouse_edit.html', context)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice')
@transaction.atomic
def warehouse_documents_upload(request, warehouse_code):
    """Upload/update warehouse documents"""
    
    warehouse = get_object_or_404(VendorWarehouse, warehouse_code=warehouse_code)
    
    # Get or create document record
    try:
        documents = VendorWarehouseDocument.objects.get(warehouse_code_id=warehouse.warehouse_code)
    except VendorWarehouseDocument.DoesNotExist:
        documents = VendorWarehouseDocument(
            warehouse_code_id=warehouse.warehouse_code,
            vendor_code=warehouse.vendor_code
        )
    
    if request.method == 'POST':
        form = VendorWarehouseDocumentForm(
            request.POST,
            request.FILES,
            instance=documents
        )
        
        if form.is_valid():
            doc = form.save(commit=False)
            doc.warehouse_code_id = warehouse.warehouse_code
            doc.vendor_code = warehouse.vendor_code
            doc.warehouse_doc_uploaded_by = request.user
            doc.save()

            # Handle legal & compliance documents (multi-file uploads)
            from django.core.files.storage import default_storage
            from django.utils import timezone
            import uuid

            # Rent Agreements
            rent_agreement_files = request.FILES.getlist('rent_agreements')
            if rent_agreement_files:
                existing_rent = doc.warehouse_owner_agreements or {}
                for file in rent_agreement_files:
                    file_id = str(uuid.uuid4())
                    file_path = f'warehouse_docs/legal/rent_agreements/{warehouse.warehouse_code}/{file_id}_{file.name}'
                    saved_path = default_storage.save(file_path, file)
                    existing_rent[file_id] = {
                        'filename': file.name,
                        'path': saved_path,
                        'uploaded_at': str(timezone.now())
                    }
                doc.warehouse_owner_agreements = existing_rent

            # SLA Documents
            sla_files = request.FILES.getlist('sla_documents')
            if sla_files:
                existing_sla = doc.warehouse_sla_documents or {}
                for file in sla_files:
                    file_id = str(uuid.uuid4())
                    file_path = f'warehouse_docs/legal/sla/{warehouse.warehouse_code}/{file_id}_{file.name}'
                    saved_path = default_storage.save(file_path, file)
                    existing_sla[file_id] = {
                        'filename': file.name,
                        'path': saved_path,
                        'uploaded_at': str(timezone.now())
                    }
                doc.warehouse_sla_documents = existing_sla

            # Other Legal Documents
            other_legal_files = request.FILES.getlist('other_legal_docs')
            if other_legal_files:
                existing_other = doc.warehouse_other_legal_docs or {}
                for file in other_legal_files:
                    file_id = str(uuid.uuid4())
                    file_path = f'warehouse_docs/legal/other/{warehouse.warehouse_code}/{file_id}_{file.name}'
                    saved_path = default_storage.save(file_path, file)
                    existing_other[file_id] = {
                        'filename': file.name,
                        'path': saved_path,
                        'uploaded_at': str(timezone.now())
                    }
                doc.warehouse_other_legal_docs = existing_other

            # Save again if legal documents were added
            if rent_agreement_files or sla_files or other_legal_files:
                doc.save()

            messages.success(request, 'Documents uploaded successfully!')
            return redirect('supply:warehouse_detail', warehouse_code=warehouse_code)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = VendorWarehouseDocumentForm(instance=documents)
    
    context = {
        'form': form,
        'warehouse': warehouse,
        'documents': documents
    }
    
    return render(request, 'supply/warehouse_documents_form.html', context)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice')
@transaction.atomic
def warehouse_photos_upload(request, warehouse_code):
    """Upload multiple warehouse photos/videos at once"""

    warehouse = get_object_or_404(VendorWarehouse, warehouse_code=warehouse_code)

    if request.method == 'POST':
        files = request.FILES.getlist('files')

        if not files:
            messages.error(request, 'Please select at least one file to upload.')
            return redirect('supply:warehouse_photos', warehouse_code=warehouse_code)

        # Auto-detect file type and save
        uploaded_count = 0
        for file in files:
            # Detect file type from extension
            file_ext = file.name.lower().split('.')[-1]
            if file_ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                file_type = 'photo'
            elif file_ext in ['mp4', 'mov', 'avi', 'webm']:
                file_type = 'video'
            else:
                continue  # Skip unsupported files

            # Create photo record
            WarehousePhoto.objects.create(
                warehouse_code=warehouse,
                file=file,
                file_type=file_type,
                uploaded_by=request.user
            )
            uploaded_count += 1

        if uploaded_count > 0:
            messages.success(request, f'{uploaded_count} file(s) uploaded successfully!')
        else:
            messages.warning(request, 'No valid image or video files found.')

        return redirect('supply:warehouse_detail', warehouse_code=warehouse_code)

    # GET request - show existing photos
    existing_photos = WarehousePhoto.objects.filter(warehouse_code=warehouse).order_by('-uploaded_at')

    context = {
        'warehouse': warehouse,
        'existing_photos': existing_photos
    }

    return render(request, 'supply/warehouse_photos_form.html', context)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice')
@transaction.atomic
def warehouse_quick_update(request, warehouse_code, section):
    """Quick update specific section of warehouse"""
    
    warehouse = get_object_or_404(VendorWarehouse, warehouse_code=warehouse_code)
    
    if request.method == 'POST':
        if section == 'identity':
            warehouse.warehouse_name = request.POST.get('warehouse_name', '')
            warehouse.warehouse_digipin = request.POST.get('warehouse_digipin', '')
            warehouse_location_id = request.POST.get('warehouse_location_id')
            if warehouse_location_id:
                warehouse.warehouse_location_id_id = warehouse_location_id
            warehouse.warehouse_address = request.POST.get('warehouse_address', '')
            warehouse.warehouse_pincode = request.POST.get('warehouse_pincode', '')
            warehouse.google_map_location = request.POST.get('google_map_location', '')
            warehouse.save()
            messages.success(request, 'Identity & location updated successfully!')
            
        elif section == 'owner':
            warehouse.warehouse_owner_name = request.POST.get('warehouse_owner_name', '')
            warehouse.warehouse_owner_contact = request.POST.get('warehouse_owner_contact', '')
            warehouse.save()
            messages.success(request, 'Owner information updated successfully!')
            
        elif section == 'profile':
            profile, _ = WarehouseProfile.objects.get_or_create(warehouse_id=warehouse.id)
            profile.warehouse_grade_id = request.POST.get('warehouse_grade') or None
            profile.property_type_id = request.POST.get('property_type') or None
            profile.business_type_id = request.POST.get('business_type') or None
            profile.fire_safety_compliant = request.POST.get('fire_safety_compliant') == 'on'
            profile.security_features = request.POST.get('security_features', '')
            profile.certifications = request.POST.get('certifications', '')
            profile.remarks = request.POST.get('remarks', '')
            profile.save()
            messages.success(request, 'Profile & classification updated successfully!')
            
        elif section == 'capacity':
            capacity, _ = WarehouseCapacity.objects.get_or_create(warehouse_id=warehouse.id)
            capacity.total_area_sqft = request.POST.get('total_area_sqft') or None
            capacity_unit_type_id = request.POST.get('capacity_unit_type')
            if capacity_unit_type_id:
                capacity.capacity_unit_type_id = capacity_unit_type_id
            capacity.total_capacity = request.POST.get('total_capacity') or None
            capacity.available_capacity = request.POST.get('available_capacity') or None
            capacity.pallets_available = request.POST.get('pallets_available') or None
            capacity.forklifts_count = request.POST.get('forklifts_count') or None
            capacity.loading_bays_count = request.POST.get('loading_bays_count') or None
            capacity.operating_hours = request.POST.get('operating_hours', '')
            capacity.racking_available = request.POST.get('racking_available') == 'on'
            capacity.is_24x7 = request.POST.get('is_24x7') == 'on'
            capacity.temperature_controlled = request.POST.get('temperature_controlled') == 'on'
            capacity.hazmat_supported = request.POST.get('hazmat_supported') == 'on'
            capacity.racking_details = request.POST.get('racking_details', '')
            capacity.save()
            messages.success(request, 'Capacity & operations updated successfully!')

        elif section == 'commercial':
            commercial, _ = WarehouseCommercial.objects.get_or_create(warehouse_id=warehouse.id)
            commercial.sla_status_id = request.POST.get('sla_status') or None
            commercial.rate_unit_type_id = request.POST.get('rate_unit_type') or None
            commercial.indicative_rate = request.POST.get('indicative_rate') or None
            commercial.minimum_commitment_months = request.POST.get('minimum_commitment_months') or None
            commercial.security_deposit = request.POST.get('security_deposit') or None
            commercial.notice_period_days = request.POST.get('notice_period_days') or None

            # Handle date fields
            contract_start = request.POST.get('contract_start_date')
            if contract_start:
                commercial.contract_start_date = contract_start
            contract_end = request.POST.get('contract_end_date')
            if contract_end:
                commercial.contract_end_date = contract_end

            commercial.escalation_percentage = request.POST.get('escalation_percentage') or None
            commercial.payment_terms = request.POST.get('payment_terms', '')
            commercial.escalation_terms = request.POST.get('escalation_terms', '')
            commercial.remarks = request.POST.get('remarks', '')
            commercial.save()
            messages.success(request, 'Commercial & contracts updated successfully!')

    return redirect('supply:warehouse_detail', warehouse_code=warehouse_code)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice')
def warehouse_toggle_active(request, warehouse_code):
    """Toggle warehouse active status"""
    
    if request.method == 'POST':
        warehouse = get_object_or_404(VendorWarehouse, warehouse_code=warehouse_code)
        warehouse.warehouse_is_active = not warehouse.warehouse_is_active
        warehouse.save()
        
        status = 'activated' if warehouse.warehouse_is_active else 'deactivated'
        messages.success(request, f'Warehouse {warehouse.warehouse_code} {status}!')
        
        return redirect('supply:warehouse_detail', warehouse_code=warehouse_code)
    
    return redirect('supply:warehouse_list')


# ============================================================================
# AJAX ENDPOINTS
# ============================================================================

@login_required
def get_vendor_warehouses(request, vendor_code):
    """Get warehouses for a specific vendor (AJAX)"""
    
    warehouses = VendorWarehouse.objects.filter(
        vendor_code__vendor_code=vendor_code,
        warehouse_is_active=True
    ).select_related('warehouse_location_id').values(
        'warehouse_code',
        'warehouse_name',
        'warehouse_location_id__city',
        'warehouse_location_id__state'
    )
    
    data = list(warehouses)
    return JsonResponse({'warehouses': data})


@login_required
def supply_map(request):
    """Supply chain map view"""
    from dropdown_master_data.models import SLAStatus

    context = {
        'sla_statuses': SLAStatus.objects.filter(is_active=True).order_by('label'),
    }
    return render(request, 'supply/map.html', context)

@login_required
def supply_analytics(request):
    """Supply analytics view with comprehensive KPIs and chart data"""

    # ========================================================================
    # STEP 1: KPI CALCULATIONS (5 metrics)
    # ========================================================================

    # KPI 1: Total Active Warehouses
    total_warehouses = VendorWarehouse.objects.filter(warehouse_is_active=True).count()

    # KPI 2 & 3: Total Capacity and Available Capacity
    capacity_aggregates = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True
    ).aggregate(
        total_capacity_sum=Sum('total_capacity'),
        available_capacity_sum=Sum('available_capacity')
    )
    total_capacity_sqft = capacity_aggregates['total_capacity_sum'] or 0
    total_available_capacity = capacity_aggregates['available_capacity_sum'] or 0

    # KPI 4: Utilization Rate
    utilized_capacity = total_capacity_sqft - total_available_capacity
    utilization_rate = round(
        (utilized_capacity / total_capacity_sqft * 100) if total_capacity_sqft > 0 else 0,
        1
    )

    # KPI 5: SLA Signed Count
    try:
        sla_signed_status = SLAStatus.objects.filter(code='signed').first()
        if sla_signed_status:
            sla_signed_count = WarehouseCommercial.objects.filter(
                warehouse__warehouse_is_active=True,
                sla_status=sla_signed_status
            ).count()
        else:
            sla_signed_count = 0
    except Exception:
        sla_signed_count = 0

    # ========================================================================
    # STEP 2: CHART DATA AGGREGATIONS (7 charts)
    # ========================================================================

    # CHART 1: Capacity by City (Top 10 cities by total capacity)
    city_capacity_data = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        warehouse__warehouse_location_id__isnull=False
    ).values(
        'warehouse__warehouse_location_id__city'
    ).annotate(
        total_cap=Sum('total_capacity')
    ).order_by('-total_cap')[:10]

    city_labels = [item['warehouse__warehouse_location_id__city'] for item in city_capacity_data]
    city_capacity = [float(item['total_cap'] or 0) for item in city_capacity_data]

    # CHART 2: Grade Distribution (count by grade)
    grade_data = WarehouseProfile.objects.filter(
        warehouse__warehouse_is_active=True,
        warehouse_grade__isnull=False
    ).values(
        'warehouse_grade__label'
    ).annotate(
        count=Count('warehouse_grade')
    ).order_by('-count')

    # Include "Not Set" for warehouses without grade
    grade_not_set_count = WarehouseProfile.objects.filter(
        warehouse__warehouse_is_active=True,
        warehouse_grade__isnull=True
    ).count()

    grade_labels = [item['warehouse_grade__label'] for item in grade_data]
    grade_counts = [item['count'] for item in grade_data]

    if grade_not_set_count > 0:
        grade_labels.append('Not Set')
        grade_counts.append(grade_not_set_count)

    # CHART 3: SLA Status Distribution (count by status)
    sla_data = WarehouseCommercial.objects.filter(
        warehouse__warehouse_is_active=True,
        sla_status__isnull=False
    ).values(
        'sla_status__label'
    ).annotate(
        count=Count('sla_status')
    ).order_by('-count')

    # Include "Not Set" for warehouses without SLA status
    sla_not_set_count = VendorWarehouse.objects.filter(
        warehouse_is_active=True
    ).filter(
        Q(commercial__isnull=True) | Q(commercial__sla_status__isnull=True)
    ).count()

    sla_labels = [item['sla_status__label'] for item in sla_data]
    sla_counts = [item['count'] for item in sla_data]

    if sla_not_set_count > 0:
        sla_labels.append('Not Set')
        sla_counts.append(sla_not_set_count)

    # CHART 4: Warehouses by State (Top 10 states by warehouse count)
    state_data = VendorWarehouse.objects.filter(
        warehouse_is_active=True,
        warehouse_location_id__isnull=False
    ).values(
        'warehouse_location_id__state'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    state_labels = [item['warehouse_location_id__state'] for item in state_data]
    state_counts = [item['count'] for item in state_data]

    # CHART 5: Top 10 Vendors by Warehouse Count
    vendor_data = VendorWarehouse.objects.filter(
        warehouse_is_active=True
    ).values(
        'vendor_code__vendor_short_name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    vendor_labels = [item['vendor_code__vendor_short_name'] for item in vendor_data]
    vendor_counts = [item['count'] for item in vendor_data]

    # CHART 6: Capacity Utilization by City (Top 10 cities)
    city_utilization_data = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        warehouse__warehouse_location_id__isnull=False
    ).values(
        'warehouse__warehouse_location_id__city'
    ).annotate(
        total_cap=Sum('total_capacity'),
        available_cap=Sum('available_capacity')
    ).order_by('-total_cap')[:10]

    utilization_labels = []
    utilization_percentages = []

    for item in city_utilization_data:
        city_name = item['warehouse__warehouse_location_id__city']
        total = float(item['total_cap'] or 0)
        available = float(item['available_cap'] or 0)

        if total > 0:
            utilization_pct = round(((total - available) / total * 100), 1)
        else:
            utilization_pct = 0

        utilization_labels.append(city_name)
        utilization_percentages.append(utilization_pct)

    # CHART 7: Property Type Distribution (count by property type)
    property_data = WarehouseProfile.objects.filter(
        warehouse__warehouse_is_active=True,
        property_type__isnull=False
    ).values(
        'property_type__label'
    ).annotate(
        count=Count('property_type')
    ).order_by('-count')

    # Include "Not Set" for warehouses without property type
    property_not_set_count = WarehouseProfile.objects.filter(
        warehouse__warehouse_is_active=True,
        property_type__isnull=True
    ).count()

    property_labels = [item['property_type__label'] for item in property_data]
    property_counts = [item['count'] for item in property_data]

    if property_not_set_count > 0:
        property_labels.append('Not Set')
        property_counts.append(property_not_set_count)

    # ========================================================================
    # STEP 3: BUILD CONTEXT with JSON serialization
    # ========================================================================
    context = {
        # KPIs
        'total_warehouses': total_warehouses,
        'total_capacity_sqft': total_capacity_sqft,
        'total_available_capacity': total_available_capacity,
        'utilization_rate': utilization_rate,
        'sla_signed_count': sla_signed_count,

        # Chart Data (JSON serialized for JavaScript)
        'city_labels': json.dumps(city_labels),
        'city_capacity': json.dumps(city_capacity),
        'grade_labels': json.dumps(grade_labels),
        'grade_counts': json.dumps(grade_counts),
        'sla_labels': json.dumps(sla_labels),
        'sla_counts': json.dumps(sla_counts),
        'state_labels': json.dumps(state_labels),
        'state_counts': json.dumps(state_counts),
        'vendor_labels': json.dumps(vendor_labels),
        'vendor_counts': json.dumps(vendor_counts),
        'utilization_labels': json.dumps(utilization_labels),
        'utilization_percentages': json.dumps(utilization_percentages),
        'property_labels': json.dumps(property_labels),
        'property_counts': json.dumps(property_counts),
    }

    return render(request, 'supply/analytics.html', context)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice')
@transaction.atomic
def warehouse_contact_manage(request, warehouse_code):
    """Manage warehouse contacts inline from detail page"""
    
    warehouse = get_object_or_404(VendorWarehouse, warehouse_code=warehouse_code)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            contact = WarehouseContact(
                warehouse_code_id=warehouse_code,
                warehouse_contact_person=request.POST.get('warehouse_contact_person') or '',
                warehouse_contact_designation=request.POST.get('warehouse_contact_designation') or '',
                warehouse_contact_department=request.POST.get('warehouse_contact_department') or '',
                warehouse_contact_phone=request.POST.get('warehouse_contact_phone') or '',
                warehouse_contact_email=request.POST.get('warehouse_contact_email') or '',
                warehouse_contact_is_primary=request.POST.get('warehouse_contact_is_primary') == 'on',
                warehouse_contact_is_active=True
            )
            contact.save()
            messages.success(request, 'Contact added successfully!')
            
        elif action == 'edit':
            contact_id = request.POST.get('contact_id')
            contact = get_object_or_404(WarehouseContact, id=contact_id, warehouse_code_id=warehouse_code)
            contact.warehouse_contact_person = request.POST.get('warehouse_contact_person') or ''
            contact.warehouse_contact_designation = request.POST.get('warehouse_contact_designation') or ''
            contact.warehouse_contact_phone = request.POST.get('warehouse_contact_phone') or ''
            contact.warehouse_contact_email = request.POST.get('warehouse_contact_email') or ''
            contact.warehouse_contact_is_primary = request.POST.get('warehouse_contact_is_primary') == 'on'
            contact.save()
            messages.success(request, 'Contact updated successfully!')
            
        elif action == 'delete':
            contact_id = request.POST.get('contact_id')
            contact = get_object_or_404(WarehouseContact, id=contact_id, warehouse_code_id=warehouse_code)
            contact.delete()
            messages.success(request, 'Contact deleted successfully!')
        
        return redirect('supply:warehouse_detail', warehouse_code=warehouse_code)

    return redirect('supply:warehouse_detail', warehouse_code=warehouse_code)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'backoffice')
@transaction.atomic
def vendor_contact_manage(request, vendor_code):
    """Manage vendor contacts inline from detail page"""

    vendor = get_object_or_404(VendorCard, vendor_code=vendor_code)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            contact = VendorContact(
                vendor_code_id=vendor_code,
                vendor_contact_person=request.POST.get('vendor_contact_person') or '',
                vendor_contact_designation=request.POST.get('vendor_contact_designation') or '',
                vendor_contact_department=request.POST.get('vendor_contact_department') or '',
                vendor_contact_phone=request.POST.get('vendor_contact_phone') or '',
                vendor_contact_email=request.POST.get('vendor_contact_email') or '',
                vendor_contact_is_primary=request.POST.get('vendor_contact_is_primary') == 'on',
                vendor_contact_is_active=True,
                is_rfq_contact=request.POST.get('is_rfq_contact') == 'on',
                rfq_cities=request.POST.get('rfq_cities', ''),
                rfq_contact_number=request.POST.get('rfq_contact_number', '')
            )
            # Handle RFQ CC emails (JSON array)
            rfq_cc_emails = request.POST.get('rfq_cc_emails', '')
            if rfq_cc_emails:
                # Split by comma and clean up
                cc_list = [email.strip() for email in rfq_cc_emails.split(',') if email.strip()]
                contact.rfq_cc_emails = cc_list
            contact.save()
            messages.success(request, 'Contact added successfully!')

        elif action == 'edit':
            contact_id = request.POST.get('contact_id')
            contact = get_object_or_404(VendorContact, id=contact_id, vendor_code_id=vendor_code)
            contact.vendor_contact_person = request.POST.get('vendor_contact_person') or ''
            contact.vendor_contact_designation = request.POST.get('vendor_contact_designation') or ''
            contact.vendor_contact_department = request.POST.get('vendor_contact_department') or ''
            contact.vendor_contact_phone = request.POST.get('vendor_contact_phone') or ''
            contact.vendor_contact_email = request.POST.get('vendor_contact_email') or ''
            contact.vendor_contact_is_primary = request.POST.get('vendor_contact_is_primary') == 'on'
            contact.is_rfq_contact = request.POST.get('is_rfq_contact') == 'on'
            contact.rfq_cities = request.POST.get('rfq_cities', '')
            contact.rfq_contact_number = request.POST.get('rfq_contact_number', '')
            # Handle RFQ CC emails (JSON array)
            rfq_cc_emails = request.POST.get('rfq_cc_emails', '')
            if rfq_cc_emails:
                cc_list = [email.strip() for email in rfq_cc_emails.split(',') if email.strip()]
                contact.rfq_cc_emails = cc_list
            else:
                contact.rfq_cc_emails = []
            contact.save()
            messages.success(request, 'Contact updated successfully!')

        elif action == 'delete':
            contact_id = request.POST.get('contact_id')
            contact = get_object_or_404(VendorContact, id=contact_id, vendor_code_id=vendor_code)
            contact.delete()
            messages.success(request, 'Contact deleted successfully!')

        return redirect('supply:vendor_detail', vendor_code=vendor_code)

    return redirect('supply:vendor_detail', vendor_code=vendor_code)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager', 'sales_manager', 'crm_executive')
@login_required
def warehouse_availability(request):
    """
    Warehouse Availability Search - For Sales, CRM & Supply Manager
    Search warehouses by location, capacity, grade
    """
    from django.db.models import Q, F, Sum
    from projects.models import ProjectCode
    from operations.models_projectcard import ProjectCard, StorageRate

    # Access control handled by decorator - no additional check needed here
    
    # Get filter parameters
    state = request.GET.get('state', '')
    city = request.GET.get('city', '')
    min_capacity = request.GET.get('min_capacity', '')
    grade = request.GET.get('grade', '')
    available_only = request.GET.get('available_only', '') == 'on'
    
    # Base queryset - active warehouses only
    warehouses = VendorWarehouse.objects.filter(
        warehouse_is_active=True
    ).select_related(
        'vendor_code',
        'warehouse_location_id',
        'capacity',
        'profile',
        'commercial'
    ).prefetch_related('contacts').order_by('vendor_code__vendor_short_name')
    
    # Apply filters
    if state:
        warehouses = warehouses.filter(warehouse_location_id__state__icontains=state)
    
    if city:
        warehouses = warehouses.filter(warehouse_location_id__city__icontains=city)
    
    if grade:
        warehouses = warehouses.filter(profile__warehouse_grade__code=grade)
    
    # Calculate availability for each warehouse
    results = []
    
    for warehouse in warehouses:
        # Get capacity directly from database field
        total_capacity = float(warehouse.capacity.total_capacity or 0) if hasattr(warehouse, 'capacity') and warehouse.capacity else 0
        available_capacity = float(warehouse.capacity.available_capacity or 0) if hasattr(warehouse, 'capacity') and warehouse.capacity else 0

        # Calculate contracted space (for display purposes)
        contracted_space = total_capacity - available_capacity
        utilization_pct = (contracted_space / total_capacity * 100) if total_capacity > 0 else 0
        
        # Apply minimum capacity filter
        if min_capacity:
            try:
                min_cap = float(min_capacity)
                if available_capacity < min_cap:
                    continue
            except ValueError:
                pass
        
        # Apply available only filter
        if available_only and available_capacity <= 0:
            continue

        # Get primary contact
        primary_contact = warehouse.contacts.filter(
            warehouse_contact_is_primary=True,
            warehouse_contact_is_active=True
        ).first()

        results.append({
            'warehouse': warehouse,
            'total_capacity': total_capacity,
            'contracted_space': contracted_space,
            'available_capacity': available_capacity,
            'utilization_pct': utilization_pct,
            'is_available': available_capacity > 0,
            'primary_contact': primary_contact,
            'indicative_rate': float(warehouse.commercial.indicative_rate or 0) if hasattr(warehouse, 'commercial') and warehouse.commercial else 0,
            'capacity_unit': warehouse.capacity.capacity_unit_type.label if hasattr(warehouse, 'capacity') and warehouse.capacity and warehouse.capacity.capacity_unit_type else 'sqft',
            'grade': warehouse.profile.warehouse_grade.label if hasattr(warehouse, 'profile') and warehouse.profile and warehouse.profile.warehouse_grade else 'N/A',
        })
    
    # Get filter options for dropdowns
    all_warehouses = VendorWarehouse.objects.filter(warehouse_is_active=True)
    
    states = all_warehouses.filter(
        warehouse_location_id__isnull=False
    ).values_list('warehouse_location_id__state', flat=True).distinct().order_by('warehouse_location_id__state')
    
    cities = all_warehouses.filter(
        warehouse_location_id__isnull=False
    ).values_list('warehouse_location_id__city', flat=True).distinct().order_by('warehouse_location_id__city')
    
    from dropdown_master_data.models import WarehouseGrade
    grades = WarehouseGrade.objects.filter(is_active=True)

    # Calculate aggregate capacity sums
    sum_total_capacity = sum(r['total_capacity'] for r in results)
    sum_available_capacity = sum(r['available_capacity'] for r in results)
    sum_contracted_space = sum(r['contracted_space'] for r in results)

    context = {
        'results': results,
        'total_results': len(results),
        'sum_total_capacity': sum_total_capacity,
        'sum_available_capacity': sum_available_capacity,
        'sum_contracted_space': sum_contracted_space,
        'states': states,
        'cities': cities,
        'grades': grades,
        'filters': {
            'state': state,
            'city': city,
            'min_capacity': min_capacity,
            'grade': grade,
            'available_only': available_only,
        }
    }

    return render(request, 'supply/warehouse_availability.html', context)


@login_required
def admin_delete_vendor_card(request, vendor_code):
    """
    Admin-only: Permanently delete a vendor card.
    Should only be used for mistakenly created vendors or duplicates.
    Checks dependencies before allowing deletion.
    """
    if request.user.role not in ['admin']:
        messages.error(request, "⛔ Access Denied: Admin only")
        return redirect('accounts:dashboard')

    try:
        vendor = VendorCard.objects.get(vendor_code=vendor_code)
    except VendorCard.DoesNotExist:
        messages.error(request, f"Vendor {vendor_code} not found")
        return redirect('supply:vendor_list')

    # GET request: Show confirmation page with dependency check
    if request.method == 'GET':
        from django.db import connection

        # Check all dependencies
        dependencies = {}

        # 1. Warehouses
        dependencies['warehouses'] = VendorWarehouse.objects.filter(vendor_code=vendor).count()

        # 2. Contacts
        dependencies['contacts'] = VendorContact.objects.filter(vendor_code=vendor).count()

        # 3. RFQ Mappings (through vendor_contact)
        dependencies['rfq_mappings'] = RFQVendorMapping.objects.filter(vendor_contact__vendor_code=vendor).count()

        # 4. Projects using this vendor
        from projects.models import ProjectCode
        dependencies['projects'] = ProjectCode.objects.filter(vendor_name=vendor.vendor_short_name).count()

        # Calculate totals
        total_records = sum(dependencies.values())
        has_dependencies = total_records > 0

        context = {
            'vendor': vendor,
            'dependencies': dependencies,
            'total_records': total_records,
            'has_dependencies': has_dependencies,
        }
        return render(request, 'supply/admin_delete_vendor_confirm.html', context)

    # POST request: Perform deletion after validation
    if request.method == 'POST':
        confirm_text = request.POST.get('confirm_delete', '').strip()

        if confirm_text != 'DELETE':
            messages.error(request, "❌ Confirmation text must be 'DELETE' (case sensitive)")
            return redirect('supply:admin_delete_vendor', vendor_code=vendor_code)

        # Double-check dependencies
        warehouse_count = VendorWarehouse.objects.filter(vendor_code=vendor).count()
        contact_count = VendorContact.objects.filter(vendor_code=vendor).count()
        rfq_count = RFQVendorMapping.objects.filter(vendor_contact__vendor_code=vendor).count()

        from projects.models import ProjectCode
        project_count = ProjectCode.objects.filter(vendor_name=vendor.vendor_short_name).count()

        if warehouse_count > 0 or contact_count > 0 or rfq_count > 0 or project_count > 0:
            messages.error(request, f"❌ Cannot delete: Vendor has {warehouse_count + contact_count + rfq_count + project_count} related records. Delete those first.")
            return redirect('supply:admin_delete_vendor', vendor_code=vendor_code)

        # Store vendor info for success message
        deleted_info = f"{vendor.vendor_code} - {vendor.vendor_short_name}"

        # Delete the vendor
        vendor.delete()

        messages.success(request, f"✅ Vendor card '{deleted_info}' has been permanently deleted")
        return redirect('supply:vendor_list')


@login_required
def admin_delete_warehouse(request, warehouse_code):
    """
    Admin-only: Permanently delete a warehouse.
    Should only be used for mistakenly created warehouses.
    Checks dependencies before allowing deletion.
    """
    if request.user.role not in ['admin']:
        messages.error(request, "⛔ Access Denied: Admin only")
        return redirect('accounts:dashboard')

    try:
        warehouse = VendorWarehouse.objects.get(warehouse_code=warehouse_code)
    except VendorWarehouse.DoesNotExist:
        messages.error(request, f"Warehouse {warehouse_code} not found")
        return redirect('supply:warehouse_list')

    # GET request: Show confirmation page with dependency check
    if request.method == 'GET':
        dependencies = {}

        # 1. Profile data
        dependencies['profile'] = 1 if hasattr(warehouse, 'profile') and warehouse.profile else 0

        # 2. Capacity data
        dependencies['capacity'] = 1 if hasattr(warehouse, 'capacity') and warehouse.capacity else 0

        # 3. Commercial data
        dependencies['commercial'] = 1 if hasattr(warehouse, 'commercial') and warehouse.commercial else 0

        # 4. Documents
        dependencies['documents'] = VendorWarehouseDocument.objects.filter(warehouse=warehouse).count()

        # 5. Photos
        dependencies['photos'] = WarehousePhoto.objects.filter(warehouse=warehouse).count()

        # 6. Projects using this warehouse
        from projects.models import ProjectCode
        dependencies['projects'] = ProjectCode.objects.filter(vendor_warehouse=warehouse).count()

        # Calculate totals
        total_records = sum(dependencies.values())
        has_dependencies = total_records > 0

        context = {
            'warehouse': warehouse,
            'dependencies': dependencies,
            'total_records': total_records,
            'has_dependencies': has_dependencies,
        }
        return render(request, 'supply/admin_delete_warehouse_confirm.html', context)

    # POST request: Perform deletion after validation
    if request.method == 'POST':
        confirm_text = request.POST.get('confirm_delete', '').strip()

        if confirm_text != 'DELETE':
            messages.error(request, "❌ Confirmation text must be 'DELETE' (case sensitive)")
            return redirect('supply:admin_delete_warehouse', warehouse_code=warehouse_code)

        # Double-check dependencies
        from projects.models import ProjectCode
        project_count = ProjectCode.objects.filter(vendor_warehouse=warehouse).count()

        if project_count > 0:
            messages.error(request, f"❌ Cannot delete: Warehouse is used in {project_count} projects. Unlink those projects first.")
            return redirect('supply:admin_delete_warehouse', warehouse_code=warehouse_code)

        # Store warehouse info for success message
        deleted_info = f"{warehouse.warehouse_code} - {warehouse.warehouse_name}"

        # Delete related data first (OneToOne relationships)
        if hasattr(warehouse, 'profile') and warehouse.profile:
            warehouse.profile.delete()
        if hasattr(warehouse, 'capacity') and warehouse.capacity:
            warehouse.capacity.delete()
        if hasattr(warehouse, 'commercial') and warehouse.commercial:
            warehouse.commercial.delete()

        # Delete documents and photos
        VendorWarehouseDocument.objects.filter(warehouse=warehouse).delete()
        WarehousePhoto.objects.filter(warehouse=warehouse).delete()

        # Delete the warehouse
        warehouse.delete()

        messages.success(request, f"✅ Warehouse '{deleted_info}' has been permanently deleted")
        return redirect('supply:warehouse_list')


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager')
def vendor_link_projects(request, vendor_code):
    """Link multiple projects to a vendor"""
    if request.method != 'POST':
        return redirect('supply:vendor_detail', vendor_code=vendor_code)

    vendor = get_object_or_404(VendorCard, vendor_code=vendor_code)
    project_ids = request.POST.getlist('project_ids')

    if not project_ids:
        messages.warning(request, "No projects selected to link")
        return redirect('supply:vendor_detail', vendor_code=vendor_code)

    from projects.models import ProjectCode
    linked_count = 0

    for project_id in project_ids:
        try:
            project = ProjectCode.objects.get(project_id=project_id)
            project.vendor_name = vendor.vendor_short_name
            project.save()
            linked_count += 1
        except ProjectCode.DoesNotExist:
            continue

    if linked_count > 0:
        messages.success(request, f"✅ Linked {linked_count} project(s) to {vendor.vendor_short_name}")
    else:
        messages.error(request, "❌ No projects were linked")

    return redirect('supply:vendor_detail', vendor_code=vendor_code)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager')
def vendor_unlink_project(request, vendor_code):
    """Unlink a project from a vendor"""
    if request.method != 'POST':
        return redirect('supply:vendor_detail', vendor_code=vendor_code)

    vendor = get_object_or_404(VendorCard, vendor_code=vendor_code)
    project_id = request.POST.get('project_id')

    if not project_id:
        messages.error(request, "❌ No project specified")
        return redirect('supply:vendor_detail', vendor_code=vendor_code)

    from projects.models import ProjectCode
    try:
        project = ProjectCode.objects.get(project_id=project_id)
        project.vendor_name = None
        project.save()
        messages.success(request, f"✅ Unlinked {project_id} from {vendor.vendor_short_name}")
    except ProjectCode.DoesNotExist:
        messages.error(request, f"❌ Project {project_id} not found")

    return redirect('supply:vendor_detail', vendor_code=vendor_code)


@login_required
def vendor_unlink_all_projects(request, vendor_code):
    """Unlink all projects from a vendor"""
    if request.method != 'POST':
        return redirect('supply:vendor_detail', vendor_code=vendor_code)

    vendor = get_object_or_404(VendorCard, vendor_code=vendor_code)

    from projects.models import ProjectCode
    # Find all projects linked to this vendor
    projects = ProjectCode.objects.filter(vendor_name=vendor.vendor_short_name)
    project_count = projects.count()

    if project_count == 0:
        messages.warning(request, "⚠️ No projects are linked to this vendor")
        return redirect('supply:vendor_detail', vendor_code=vendor_code)

    # Unlink all projects
    projects.update(vendor_name=None)

    messages.success(request, f"✅ Successfully unlinked {project_count} project(s) from {vendor.vendor_short_name}")
    return redirect('supply:vendor_detail', vendor_code=vendor_code)


@login_required
@require_role('admin', 'super_user', 'director', 'supply_manager')
def warehouse_unlink_all_projects(request, warehouse_code):
    """Unlink all projects from a warehouse"""
    if request.method != 'POST':
        return redirect('supply:warehouse_detail', warehouse_code=warehouse_code)

    warehouse = get_object_or_404(VendorWarehouse, warehouse_code=warehouse_code)

    from projects.models import ProjectCode
    # Find all projects linked to this warehouse
    projects = ProjectCode.objects.filter(vendor_warehouse=warehouse)
    project_count = projects.count()

    if project_count == 0:
        messages.warning(request, "⚠️ No projects are linked to this warehouse")
        return redirect('supply:warehouse_detail', warehouse_code=warehouse_code)

    # Unlink all projects
    projects.update(vendor_warehouse=None)

    messages.success(request, f"✅ Successfully unlinked {project_count} project(s) from {warehouse.warehouse_name}")
    return redirect('supply:warehouse_detail', warehouse_code=warehouse_code)