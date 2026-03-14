"""
Context Processor for Dropdown Master Data
Makes all dropdowns available in templates automatically.
Uses a single consolidated cache key instead of 51 individual lookups per request.
"""

from django.core.cache import cache
from .services import get_dropdown_choices, get_dropdown_map, ALL_DROPDOWNS_CACHE_KEY, CACHE_TIMEOUT


def _build_all_dropdowns():
    """Build the full dropdown dict (called on cache miss only)."""
    return {
        # Units & Measurements
        'storage_units': get_dropdown_choices('StorageUnit'),
        'billing_units': get_dropdown_choices('BillingUnit'),
        'handling_units': get_dropdown_choices('HandlingUnit'),
        'vehicle_types': get_dropdown_choices('VehicleType'),
        'vas_units': get_dropdown_choices('VASUnit'),

        # Workflow States
        'priorities': get_dropdown_choices('Priority'),
        'approval_statuses': get_dropdown_choices('ApprovalStatus'),
        'billing_statuses': get_dropdown_choices('BillingStatus'),
        'escalation_statuses': get_dropdown_choices('EscalationStatus'),
        'ticket_statuses': get_dropdown_choices('TicketStatus'),
        'monthly_billing_statuses': get_dropdown_choices('MonthlyBillingStatus'),
        'approval_actions': get_dropdown_choices('ApprovalAction'),
        'dispute_statuses': get_dropdown_choices('DisputeStatus'),

        # Categories
        'query_categories': get_dropdown_choices('QueryCategory'),
        'holiday_types': get_dropdown_choices('HolidayType'),
        'adhoc_charge_types': get_dropdown_choices('AdhocChargeType'),
        'escalation_action_types': get_dropdown_choices('EscalationActionType'),
        'alert_types': get_dropdown_choices('AlertType'),
        'severity_levels': get_dropdown_choices('Severity'),
        'activity_types': get_dropdown_choices('ActivityType'),

        # Project/Business
        'series_types': get_dropdown_choices('SeriesType'),
        'project_statuses': get_dropdown_choices('ProjectStatus'),
        'sales_channels': get_dropdown_choices('SalesChannel'),
        'handling_base_types': get_dropdown_choices('HandlingBaseType'),
        'vas_service_types': get_dropdown_choices('VASServiceType'),
        'operational_cost_types': get_dropdown_choices('OperationalCostType'),
        'escalation_terms': get_dropdown_choices('EscalationTerms'),
        'notice_period_durations': get_dropdown_choices('NoticePeriodDuration'),
        'operation_modes': get_dropdown_choices('OperationMode'),
        'mis_statuses': get_dropdown_choices('MISStatus'),
        'rate_applicability': get_dropdown_choices('RateApplicability'),
        'handling_directions': get_dropdown_choices('HandlingDirection'),
        'transaction_sides': get_dropdown_choices('TransactionSide'),

        # Tickets & Notifications
        'ticket_types': get_dropdown_choices('TicketType'),
        'user_roles': get_dropdown_choices('UserRole'),
        'notification_types': get_dropdown_choices('NotificationType'),

        # Supply/Warehouse
        'warehouse_grades': get_dropdown_choices('WarehouseGrade'),
        'business_types': get_dropdown_choices('BusinessType'),
        'property_types': get_dropdown_choices('PropertyType'),
        'sla_statuses': get_dropdown_choices('SLAStatus'),
        'warehouse_contact_departments': get_dropdown_choices('WarehouseContactDepartment'),
        'file_types': get_dropdown_choices('FileType'),

        # Maps (for display labels)
        'storage_unit_map': get_dropdown_map('StorageUnit'),
        'billing_unit_map': get_dropdown_map('BillingUnit'),
        'priority_map': get_dropdown_map('Priority'),
        'project_status_map': get_dropdown_map('ProjectStatus'),
        'monthly_billing_status_map': get_dropdown_map('MonthlyBillingStatus'),
    }


def dropdowns(request):
    """
    Add all active dropdowns to template context.

    Usage in templates:
        {% for unit in dropdowns.storage_units %}
            <option value="{{ unit.0 }}">{{ unit.1 }}</option>
        {% endfor %}

        Or for display:
        {{ dropdowns.storage_unit_map.sqft }}  -> "Square Feet"
    """
    cached = cache.get(ALL_DROPDOWNS_CACHE_KEY)
    if cached is not None:
        return {'dropdowns': cached}

    result = _build_all_dropdowns()
    cache.set(ALL_DROPDOWNS_CACHE_KEY, result, CACHE_TIMEOUT)
    return {'dropdowns': result}
