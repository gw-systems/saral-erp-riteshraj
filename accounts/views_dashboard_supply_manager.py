"""
Supply Manager Dashboard View
Fixed version - queries actual warehouse/vendor/capacity data from supply models
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Q, F, DecimalField
from django.db.models.functions import Coalesce

from accounts.models import User
from supply.models import (
    VendorCard,
    VendorWarehouse,
    WarehouseProfile,
    WarehouseCapacity,
    WarehouseCommercial,
    VendorWarehouseDocument,
    RFQ
)


@login_required
def supply_manager_dashboard(request):
    """
    Supply Manager Dashboard
    Focused on supply chain, vendor management, and warehouse operations
    """
    # Role check
    if request.user.role not in ['supply_manager', 'admin', 'director']:
        messages.error(request, "Access denied. Supply Manager access required.")
        return redirect('accounts:dashboard')

    # Date context
    today = timezone.now().date()

    # ==================== WAREHOUSE & VENDOR COUNTS ====================

    # Total active warehouses
    total_warehouses = VendorWarehouse.objects.filter(warehouse_is_active=True).count()

    # Active vendors (with at least one active warehouse)
    active_vendors = VendorCard.objects.filter(
        vendor_is_active=True,
        warehouses__warehouse_is_active=True
    ).distinct().count()

    # ==================== SLA STATUS ====================

    # Get warehouses with commercial terms (those that can have SLA)
    warehouses_with_commercial = WarehouseCommercial.objects.filter(
        warehouse__warehouse_is_active=True
    ).count()

    # Count signed SLAs (assuming SLA status code 'signed' or similar)
    sla_signed_count = WarehouseCommercial.objects.filter(
        warehouse__warehouse_is_active=True,
        sla_status__code='signed'  # Adjust based on actual SLA status codes
    ).count()

    # SLA not signed
    alert_sla_not_signed_count = warehouses_with_commercial - sla_signed_count

    # SLA signed percentage
    sla_signed_percentage = (sla_signed_count / warehouses_with_commercial * 100) if warehouses_with_commercial > 0 else 0

    # ==================== CAPACITY & UTILIZATION ====================

    # Aggregate capacity data
    capacity_data = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True
    ).aggregate(
        total_capacity=Coalesce(Sum('total_capacity'), 0),
        total_available=Coalesce(Sum('available_capacity'), 0),
        total_area=Coalesce(Sum('total_area_sqft'), 0)
    )

    total_capacity = capacity_data['total_capacity'] or 0
    available_capacity = capacity_data['total_available'] or 0
    used_capacity = total_capacity - available_capacity

    # Utilization percentage
    utilization_percent = (used_capacity / total_capacity * 100) if total_capacity > 0 else 0

    # ==================== WAREHOUSE FEATURES ====================

    # 24x7 operations
    warehouses_24x7_count = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        is_24x7=True
    ).count()

    # Temperature controlled (cold chain)
    temp_controlled_count = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        temperature_controlled=True
    ).count()

    # ==================== CONTRACT ALERTS ====================

    # Contracts expiring within 60 days
    expiring_threshold = today + timedelta(days=60)
    alert_expiring_count = WarehouseCommercial.objects.filter(
        warehouse__warehouse_is_active=True,
        contract_end_date__isnull=False,
        contract_end_date__lte=expiring_threshold,
        contract_end_date__gte=today
    ).count()

    # ==================== CAPACITY ALERTS ====================

    # Low capacity warehouses (<15% free)
    alert_low_capacity_count = 0
    low_capacity_warehouses = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        total_capacity__gt=0
    ).only('total_capacity', 'available_capacity')

    for wh in low_capacity_warehouses:
        total = wh.total_capacity or 0
        available = wh.available_capacity or 0
        if total > 0 and ((total - available) / total * 100) > 85:
            alert_low_capacity_count += 1

    # ==================== DOCUMENT ALERTS ====================

    # Warehouses with missing critical documents
    alert_missing_docs_count = 0
    all_warehouse_docs = VendorWarehouseDocument.objects.filter(
        warehouse_code__warehouse_is_active=True
    )

    for doc in all_warehouse_docs:
        # Check if critical documents are missing
        critical_docs_missing = (
            not doc.warehouse_electricity_bill or
            not doc.warehouse_property_tax_receipt or
            not doc.warehouse_noc_owner
        )
        if critical_docs_missing:
            alert_missing_docs_count += 1

    # ==================== INACTIVE LINKS ALERT ====================

    # Warehouses that are active but linked to inactive projects
    # (This requires checking projects.ProjectCode model)
    from projects.models import ProjectCode

    alert_inactive_linked_count = ProjectCode.objects.filter(
        vendor_warehouse__isnull=False,
        vendor_warehouse__warehouse_is_active=False,
        project_status='Active'
    ).count()

    # ==================== OPEN RFQs ====================

    open_rfqs_count = RFQ.objects.filter(status='open').count()

    # ==================== CAPACITY BY GRADE ====================

    capacity_by_grade = {}

    # Grade A
    grade_a_data = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        warehouse__profile__warehouse_grade__code='grade_a'
    ).aggregate(
        total=Coalesce(Sum('total_capacity'), 0),
        available=Coalesce(Sum('available_capacity'), 0)
    )

    if grade_a_data['total'] and grade_a_data['total'] > 0:
        used = grade_a_data['total'] - (grade_a_data['available'] or 0)
        capacity_by_grade['grade_a'] = {
            'total': grade_a_data['total'],
            'used': used,
            'available': grade_a_data['available'] or 0,
            'utilization_percent': (used / grade_a_data['total'] * 100) if grade_a_data['total'] > 0 else 0
        }

    # Grade B
    grade_b_data = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        warehouse__profile__warehouse_grade__code='grade_b'
    ).aggregate(
        total=Coalesce(Sum('total_capacity'), 0),
        available=Coalesce(Sum('available_capacity'), 0)
    )

    if grade_b_data['total'] and grade_b_data['total'] > 0:
        used = grade_b_data['total'] - (grade_b_data['available'] or 0)
        capacity_by_grade['grade_b'] = {
            'total': grade_b_data['total'],
            'used': used,
            'available': grade_b_data['available'] or 0,
            'utilization_percent': (used / grade_b_data['total'] * 100) if grade_b_data['total'] > 0 else 0
        }

    # Grade C
    grade_c_data = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        warehouse__profile__warehouse_grade__code='grade_c'
    ).aggregate(
        total=Coalesce(Sum('total_capacity'), 0),
        available=Coalesce(Sum('available_capacity'), 0)
    )

    if grade_c_data['total'] and grade_c_data['total'] > 0:
        used = grade_c_data['total'] - (grade_c_data['available'] or 0)
        capacity_by_grade['grade_c'] = {
            'total': grade_c_data['total'],
            'used': used,
            'available': grade_c_data['available'] or 0,
            'utilization_percent': (used / grade_c_data['total'] * 100) if grade_c_data['total'] > 0 else 0
        }

    # ==================== CAPACITY BY CITY (TOP 10) ====================

    capacity_by_city = []
    city_data = WarehouseCapacity.objects.filter(
        warehouse__warehouse_is_active=True,
        warehouse__warehouse_location_id__isnull=False
    ).values('warehouse__warehouse_location_id__city').annotate(
        total=Coalesce(Sum('total_capacity'), 0),
        available=Coalesce(Sum('available_capacity'), 0)
    ).order_by('-total')[:10]

    for city in city_data:
        if city['total'] and city['total'] > 0:
            used = city['total'] - (city['available'] or 0)
            capacity_by_city.append({
                'warehouse__warehouse_location_id__city': city['warehouse__warehouse_location_id__city'],
                'total': city['total'],
                'used': used,
                'available': city['available'] or 0,
                'utilization_percent': (used / city['total'] * 100) if city['total'] > 0 else 0
            })

    # ==================== CONTRACT RISKS (TOP 10) ====================

    contract_risks = []

    # Get warehouses with contracts expiring soon or SLA not signed
    risky_warehouses = WarehouseCommercial.objects.filter(
        warehouse__warehouse_is_active=True
    ).select_related(
        'warehouse',
        'warehouse__vendor_code',
        'sla_status'
    ).order_by('contract_end_date')[:10]

    for wh_comm in risky_warehouses:
        # Calculate days left
        days_left = None
        if wh_comm.contract_end_date:
            days_left = (wh_comm.contract_end_date - today).days

        # Determine SLA status
        sla_status = 'Not Signed'
        if wh_comm.sla_status and wh_comm.sla_status.code == 'signed':
            sla_status = 'Signed'

        # Risk level
        risk_level = 'low'
        if sla_status == 'Not Signed':
            risk_level = 'critical'
        elif days_left is not None and days_left <= 30:
            risk_level = 'critical'
        elif days_left is not None and days_left <= 60:
            risk_level = 'high'

        contract_risks.append({
            'warehouse': wh_comm.warehouse,
            'vendor': wh_comm.warehouse.vendor_code,
            'sla_status': sla_status,
            'days_left': days_left,
            'escalation_percentage': wh_comm.escalation_percentage or 0,
            'risk_level': risk_level
        })

    # ==================== RECENT ACTIVITY ====================

    recent_activities = []

    # Recently added warehouses
    recent_warehouses = VendorWarehouse.objects.filter(
        warehouse_is_active=True
    ).order_by('-warehouse_created_at')[:5]

    for wh in recent_warehouses:
        recent_activities.append({
            'type': 'warehouse_created',
            'description': f"New warehouse added: {wh.warehouse_code}",
            'detail': f"{wh.warehouse_name or 'Unnamed'} - {wh.warehouse_location_id.city if wh.warehouse_location_id else 'No location'}",
            'timestamp': wh.warehouse_created_at,
            'link': f"/supply/warehouse/{wh.warehouse_code}/"
        })

    # Recently added vendors
    recent_vendors = VendorCard.objects.filter(
        vendor_is_active=True
    ).order_by('-vendor_created_at')[:5]

    for vendor in recent_vendors:
        recent_activities.append({
            'type': 'vendor_created',
            'description': f"New vendor added: {vendor.vendor_code}",
            'detail': f"{vendor.vendor_short_name}",
            'timestamp': vendor.vendor_created_at,
            'link': f"/supply/vendor/{vendor.vendor_code}/"
        })

    # Sort by timestamp (most recent first)
    recent_activities.sort(key=lambda x: x['timestamp'] if x['timestamp'] else timezone.now(), reverse=True)
    recent_activities = recent_activities[:10]  # Limit to 10 most recent

    # ==================== CONTEXT ====================

    context = {
        # Date
        'today': today,
        'current_time': timezone.now().strftime('%I:%M %p'),

        # Warehouses & Vendors
        'total_warehouses': total_warehouses,
        'active_vendors': active_vendors,

        # SLA Status
        'sla_signed_count': sla_signed_count,
        'sla_signed_percentage': sla_signed_percentage,
        'total_wh_with_commercial': warehouses_with_commercial,
        'alert_sla_not_signed_count': alert_sla_not_signed_count,

        # Capacity & Utilization
        'total_capacity': total_capacity,
        'available_capacity': available_capacity,
        'used_capacity': used_capacity,
        'utilization_percent': utilization_percent,

        # Warehouse Features
        'warehouses_24x7_count': warehouses_24x7_count,
        'temp_controlled_count': temp_controlled_count,

        # Alerts
        'alert_expiring_count': alert_expiring_count,
        'alert_low_capacity_count': alert_low_capacity_count,
        'alert_missing_docs_count': alert_missing_docs_count,
        'alert_inactive_linked_count': alert_inactive_linked_count,

        # RFQs
        'open_rfqs_count': open_rfqs_count,

        # Capacity Breakdown
        'capacity_by_grade': capacity_by_grade,
        'capacity_by_city': capacity_by_city,

        # Contract Risks
        'contract_risks': contract_risks,

        # Recent Activity
        'recent_activities': recent_activities,
    }

    return render(request, 'dashboards/supply_manager_dashboard.html', context)
