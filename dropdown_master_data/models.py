"""
Master Data Models - Business-Configurable Dropdowns
All Type-2 hardcoded dropdowns converted to DB-backed admin-managed tables.

Phase 1: Model definitions only (no FK refactor yet)
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


# ============================================================================
# ABSTRACT BASE MODEL
# ============================================================================

class MasterDropdown(models.Model):
    """
    Abstract base for all master dropdown tables.
    Provides consistent structure and behavior.
    """
    code = models.CharField(
        max_length=50,
        primary_key=True,
        help_text="Stable machine-readable identifier (lowercase, underscores)"
    )
    label = models.CharField(
        max_length=100,
        help_text="Human-readable display name"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft delete - set to False instead of deleting"
    )
    display_order = models.IntegerField(
        default=0,
        help_text="Sort order for dropdowns (lower = higher priority)"
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_updates',
        help_text="Last user who modified this record"
    )

    class Meta:
        abstract = True
        ordering = ['display_order', 'code']

    def __str__(self):
        return self.label

    def delete(self, *args, **kwargs):
        """
        Prevent hard deletion - use is_active=False instead.
        Override in concrete models if hard delete needed.
        """
        raise ValidationError(
            f"Cannot delete {self._meta.verbose_name}. "
            f"Set is_active=False instead."
        )

    def soft_delete(self, user=None):
        """Soft delete by setting is_active=False"""
        self.is_active = False
        if user:
            self.updated_by = user
        self.save()


# ============================================================================
# STORAGE & CAPACITY UNITS
# ============================================================================

class StorageUnit(MasterDropdown):
    """
    Storage/Space measurement units.
    Replaces: storage_unit_type, v_storage_type, c_storage_type, space_type, billing_unit
    Values: sqft, pallet, unit, order, lumpsum
    """
    class Meta:
        verbose_name = "Storage Unit"
        verbose_name_plural = "Storage Units"
        db_table = "master_storage_units"


class BillingUnit(MasterDropdown):
    """
    Billing measurement units (extends storage units).
    Replaces: billing_unit in projects
    Values: sqft, pallet, unit, order, lumpsum
    """
    class Meta:
        verbose_name = "Billing Unit"
        verbose_name_plural = "Billing Units"
        db_table = "master_billing_units"


class HandlingUnit(MasterDropdown):
    """
    Material handling measurement units.
    Replaces: v_handling_in_unit, v_handling_out_unit, c_handling_in_unit, c_handling_out_unit
    Values: boxes, tons, pieces
    """
    class Meta:
        verbose_name = "Handling Unit"
        verbose_name_plural = "Handling Units"
        db_table = "master_handling_units"


# ============================================================================
# TRANSPORT & LOGISTICS
# ============================================================================

class VehicleType(MasterDropdown):
    """
    Vehicle types for transport operations.
    Replaces: vendor_transport_vehicle_type, client_transport_vehicle_type
    Values: local_transport, bike, pick_up, 14_ft, 20_ft, 32_ft, tata_ace, 
            max_2mp, tata_407, tata_709, tata_909, ftl_1109, 17_ft, 3_wheeler, porter
    """
    class Meta:
        verbose_name = "Vehicle Type"
        verbose_name_plural = "Vehicle Types"
        db_table = "master_vehicle_types"


# ============================================================================
# WORKFLOW STATES
# ============================================================================

class Priority(MasterDropdown):
    """
    Priority levels for tickets, disputes, queries.
    Replaces: priority fields across operations, tickets
    Values: low, medium, high, critical
    Note: 'urgent' normalized to 'critical'
    """
    class Meta:
        verbose_name = "Priority Level"
        verbose_name_plural = "Priority Levels"
        db_table = "master_priorities"


class ApprovalStatus(MasterDropdown):
    """
    Generic approval workflow status.
    Replaces: status in ProjectRate, MonthlyBilling, etc.
    Values: draft, pending_approval, approved, rejected
    """
    class Meta:
        verbose_name = "Approval Status"
        verbose_name_plural = "Approval Statuses"
        db_table = "master_approval_statuses"


class BillingStatus(MasterDropdown):
    """
    Billing lifecycle status.
    Replaces: status in AdhocBilling
    Values: pending, billed, cancelled
    """
    class Meta:
        verbose_name = "Billing Status"
        verbose_name_plural = "Billing Statuses"
        db_table = "master_billing_statuses"


class EscalationStatus(MasterDropdown):
    """
    Annual escalation tracker status.
    Replaces: status in AnnualEscalationTracker (both client and vendor)
    Values: pending, in_progress, client_acknowledged, escalation_applied, disputed, cancelled
    """
    class Meta:
        verbose_name = "Escalation Status"
        verbose_name_plural = "Escalation Statuses"
        db_table = "master_escalation_statuses"


class TicketStatus(MasterDropdown):
    """
    Ticket lifecycle status.
    Replaces: status in Ticket model
    Values: pending, approved, rejected, in_progress, resolved, closed
    """
    class Meta:
        verbose_name = "Ticket Status"
        verbose_name_plural = "Ticket Statuses"
        db_table = "master_ticket_statuses"


# ============================================================================
# OPERATIONAL CATEGORIES
# ============================================================================

class QueryCategory(MasterDropdown):
    """
    Issue/query categorization.
    Replaces: category in Query model
    Values: storage_space, handling, manpower_ot, operations, mis_stock, billing
    """
    class Meta:
        verbose_name = "Query Category"
        verbose_name_plural = "Query Categories"
        db_table = "master_query_categories"


class HolidayType(MasterDropdown):
    """
    Holiday classification.
    Replaces: holiday_type in Holiday model
    Values: national, regional, warehouse_closure, project_specific
    """
    class Meta:
        verbose_name = "Holiday Type"
        verbose_name_plural = "Holiday Types"
        db_table = "master_holiday_types"


class AdhocChargeType(MasterDropdown):
    """
    Adhoc billing charge categories.
    Replaces: charge_type in AdhocBilling, attachment_type in AdhocAttachment
    Values: extra_storage, extra_manpower, extra_handling, overtime, vas, 
            transport, equipment, other
    """
    class Meta:
        verbose_name = "Adhoc Charge Type"
        verbose_name_plural = "Adhoc Charge Types"
        db_table = "master_adhoc_charge_types"


class AdhocBillingStatus(MasterDropdown):
    """
    Status for adhoc billing entries.
    Used in: AdhocBillingEntry.status
    Values: pending, billed, cancelled
    """
    class Meta:
        db_table = 'dropdown_adhoc_billing_statuses'
        verbose_name = 'Adhoc Billing Status'
        verbose_name_plural = 'Adhoc Billing Statuses'


class EscalationActionType(MasterDropdown):
    """
    Annual escalation workflow action types.
    Replaces: action_type in escalation trackers
    Values: tracker_created, initial_intimation, reminder_1, reminder_2, 
            final_notice, sales_informed, finance_informed, client_acknowledged, 
            status_changed, note_added, escalation_applied, cancelled
    """
    class Meta:
        verbose_name = "Escalation Action Type"
        verbose_name_plural = "Escalation Action Types"
        db_table = "master_escalation_action_types"


# ============================================================================
# PROJECT CARD RATE DIMENSIONS
# ============================================================================

class SalesChannel(MasterDropdown):
    """
    Sales/distribution channel types.
    Replaces: channel in HandlingRate
    Values: b2b, b2c, d2c, rto, rtv
    """
    class Meta:
        verbose_name = "Sales Channel"
        verbose_name_plural = "Sales Channels"
        db_table = "master_sales_channels"


class HandlingBaseType(MasterDropdown):
    """
    Handling rate calculation base units.
    Replaces: base_type in HandlingRate
    Values: per_unit, per_kg, per_tonne, per_box, per_pallet, per_order, 
            per_line_item, per_roll
    """
    class Meta:
        verbose_name = "Handling Base Type"
        verbose_name_plural = "Handling Base Types"
        db_table = "master_handling_base_types"


class VASServiceType(MasterDropdown):
    """
    Value-Added Service types.
    Replaces: service_type in VASRate
    Values: labeling, kitting, repacking, quality_check, photography, gift_wrapping, 
            manpower, forklift, hydra, barcoding, qc_inspection, other
    """
    class Meta:
        verbose_name = "VAS Service Type"
        verbose_name_plural = "VAS Service Types"
        db_table = "master_vas_service_types"


class VASUnit(MasterDropdown):
    """
    VAS billing units.
    Replaces: unit in VASRate
    Values: per_hour, per_day, per_month, per_unit, lumpsum, at_actual
    """
    class Meta:
        verbose_name = "VAS Unit"
        verbose_name_plural = "VAS Units"
        db_table = "master_vas_units"


class OperationalCostType(MasterDropdown):
    """
    Operational cost categories.
    Replaces: cost_type in OtherCost
    Values: equipment, utilities, rent, insurance, security, management_fee, 
            electricity, other
    """
    class Meta:
        verbose_name = "Operational Cost Type"
        verbose_name_plural = "Operational Cost Types"
        db_table = "master_operational_cost_types"


class EscalationTerms(MasterDropdown):
    """
    Annual escalation terms/methodology.
    Replaces: escalation_terms in ProjectCard
    Values: FIXED, MUTUALLY_AGREED
    """
    class Meta:
        verbose_name = "Escalation Terms"
        verbose_name_plural = "Escalation Terms"
        db_table = "master_escalation_terms"


# ============================================================================
# PROJECT & CONTRACT CONFIGURATION
# ============================================================================

class NoticePeriodDuration(MasterDropdown):
    """
    Contract notice period durations.
    Replaces: notice_period_duration in ProjectCode
    Values: 15_days, 30_days, 60_days, 90_days
    """
    class Meta:
        verbose_name = "Notice Period Duration"
        verbose_name_plural = "Notice Period Durations"
        db_table = "master_notice_period_durations"


class OperationMode(MasterDropdown):
    """
    Operational engagement levels.
    Replaces: operation_mode in ProjectCode
    Values: auto_mode, data_sharing, active_engagement
    """
    class Meta:
        verbose_name = "Operation Mode"
        verbose_name_plural = "Operation Modes"
        db_table = "master_operation_modes"


class MISStatus(MasterDropdown):
    """
    MIS reporting frequencies.
    Replaces: mis_status in ProjectCode
    Values: mis_daily, mis_weekly, mis_monthly, inciflo, mis_automode, mis_not_required
    """
    class Meta:
        verbose_name = "MIS Status"
        verbose_name_plural = "MIS Statuses"
        db_table = "master_mis_statuses"


# ============================================================================
# WAREHOUSE SUPPLY (NEW)
# ============================================================================

class WarehouseGrade(MasterDropdown):
    """
    Warehouse quality/grade classification.
    New for warehouse supply database.
    Values: grade_a, grade_b, grade_c
    """
    class Meta:
        verbose_name = "Warehouse Grade"
        verbose_name_plural = "Warehouse Grades"
        db_table = "master_warehouse_grades"


class BusinessType(MasterDropdown):
    """
    Business model types.
    New for warehouse supply database.
    Values: b2b, b2c, both
    """
    class Meta:
        verbose_name = "Business Type"
        verbose_name_plural = "Business Types"
        db_table = "master_business_types"


class PropertyType(MasterDropdown):
    """
    Warehouse property types.
    New for warehouse supply database.
    Values: in_shed, open, covered, temperature_controlled
    """
    class Meta:
        verbose_name = "Property Type"
        verbose_name_plural = "Property Types"
        db_table = "master_property_types"


class SLAStatus(MasterDropdown):
    """
    SLA/Agreement status.
    New for warehouse supply database.
    Values: signed, not_signed, under_negotiation, expired
    """
    class Meta:
        verbose_name = "SLA Status"
        verbose_name_plural = "SLA Statuses"
        db_table = "master_sla_statuses"


class TicketType(MasterDropdown):
    """
    Ticket categorization.
    Replaces: ticket_type in Ticket model
    Values: client_approval, client_escalation, vendor_escalation, internal
    """
    class Meta:
        verbose_name = "Ticket Type"
        verbose_name_plural = "Ticket Types"
        db_table = "master_ticket_types"


class WarehouseContactDepartment(MasterDropdown):
    """
    Warehouse contact department classification.
    Replaces: warehouse_contact_department in WarehouseContact
    Values: operations, management
    """
    class Meta:
        verbose_name = "Warehouse Contact Department"
        verbose_name_plural = "Warehouse Contact Departments"
        db_table = "master_warehouse_contact_departments"


class UserRole(MasterDropdown):
    """
    System-wide user role definitions for access control.
    Replaces: role in User model
    Values: admin, super_user, director, finance_manager, operation_controller, 
            operation_manager, sales_manager, supply_manager, operation_coordinator, 
            warehouse_manager, backoffice, crm_executive, client, vendor
    """
    class Meta:
        verbose_name = "User Role"
        verbose_name_plural = "User Roles"
        db_table = "master_user_roles"


class NotificationType(MasterDropdown):
    """
    System notification categories.
    Replaces: notification_type in Notification model
    Values: dispute_raised, dispute_assigned, dispute_resolved, query_raised, 
            query_assigned, query_resolved, data_entry_missing, daily_summary, 
            assignment, mention, system
    """
    class Meta:
        verbose_name = "Notification Type"
        verbose_name_plural = "Notification Types"
        db_table = "master_notification_types"


class MonthlyBillingStatus(MasterDropdown):
    """
    Monthly billing workflow states.
    Replaces: status in MonthlyBilling model
    Values: draft, pending_controller, controller_rejected, pending_finance, 
            finance_rejected, approved
    """
    class Meta:
        verbose_name = "Monthly Billing Status"
        verbose_name_plural = "Monthly Billing Statuses"
        db_table = "master_monthly_billing_statuses"


class ApprovalAction(MasterDropdown):
    """
    Approval workflow actions (reusable across all approval flows).
    Replaces: controller_action, finance_action in MonthlyBilling
    Values: pending, approved, rejected
    """
    class Meta:
        verbose_name = "Approval Action"
        verbose_name_plural = "Approval Actions"
        db_table = "master_approval_actions"


class AlertType(MasterDropdown):
    """
    In-app alert categorization.
    Replaces: alert_type in InAppAlert model
    Values: coordinator_reminder, manager_notification, system_alert
    """
    class Meta:
        verbose_name = "Alert Type"
        verbose_name_plural = "Alert Types"
        db_table = "master_alert_types"


class Severity(MasterDropdown):
    """
    Alert and issue severity classification.
    Replaces: severity in InAppAlert, RateCardAlert models
    Values: info, warning, critical
    """
    class Meta:
        verbose_name = "Severity Level"
        verbose_name_plural = "Severity Levels"
        db_table = "master_severity_levels"


class ActivityType(MasterDropdown):
    """
    Audit trail activity classifications.
    Replaces: activity_type in QueryActivity model
    Values: created, status_changed, assigned, priority_changed, commented, 
            attachment_added, resolved
    """
    class Meta:
        verbose_name = "Activity Type"
        verbose_name_plural = "Activity Types"
        db_table = "master_activity_types"


class TransactionSide(MasterDropdown):
    """
    Billing/transaction party classification.
    Replaces: side in AdhocBillingEntry model
    Values: client, vendor
    """
    class Meta:
        verbose_name = "Transaction Side"
        verbose_name_plural = "Transaction Sides"
        db_table = "master_transaction_sides"


class DisputeStatus(MasterDropdown):
    """
    Dispute lifecycle states.
    Replaces: status in Dispute model (from views.py conditional)
    Values: open, in_progress, resolved, dispute, closed
    """
    class Meta:
        verbose_name = "Dispute Status"
        verbose_name_plural = "Dispute Statuses"
        db_table = "master_dispute_statuses"


class SeriesType(MasterDropdown):
    """
    Project categorization by service model.
    Replaces: series_type in ProjectCode model
    Values: WAAS, SAAS, GW
    """
    class Meta:
        verbose_name = "Series Type"
        verbose_name_plural = "Series Types"
        db_table = "master_series_types"


class ProjectStatus(MasterDropdown):
    """
    Project operational lifecycle states.
    Replaces: project_status in ProjectCode model
    Values: operation_not_started, active, notice_period, inactive
    """
    class Meta:
        verbose_name = "Project Status"
        verbose_name_plural = "Project Statuses"
        db_table = "master_project_statuses"


class RateApplicability(MasterDropdown):
    """
    Defines whether rate applies to client or vendor.
    Replaces: rate_for in StorageRate, HandlingRate, VASRate, OtherCost models
    Values: client, vendor
    """
    class Meta:
        verbose_name = "Rate Applicability"
        verbose_name_plural = "Rate Applicability"
        db_table = "master_rate_applicability"


class HandlingDirection(MasterDropdown):
    """
    Material handling flow direction.
    Replaces: direction in HandlingRate model
    Values: inbound, outbound
    """
    class Meta:
        verbose_name = "Handling Direction"
        verbose_name_plural = "Handling Directions"
        db_table = "master_handling_directions"


class FileType(MasterDropdown):
    """
    Warehouse media file classifications.
    Replaces: file_type in WarehouseMedia model
    Values: photo, video
    """
    class Meta:
        verbose_name = "File Type"
        verbose_name_plural = "File Types"
        db_table = "master_file_types"

# ============================================================================
# GEOGRAPHIC MASTER DATA
# ============================================================================

class Region(MasterDropdown):
    """
    Geographic regions of India.
    Values: north, south, east, west, central
    """
    class Meta:
        verbose_name = "Region"
        verbose_name_plural = "Regions"
        db_table = "master_regions"


class StateCode(models.Model):
    """
    Indian state codes (2-letter).
    User-maintainable master data for state abbreviations.
    """
    state_code = models.CharField(
        max_length=2,
        primary_key=True,
        help_text="2-letter state code (e.g., MH)"
    )
    state_name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Full state name (e.g., Maharashtra)"
    )
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = "State Code"
        verbose_name_plural = "State Codes"
        db_table = "master_state_codes"
        ordering = ['display_order', 'state_name']

    def __str__(self):
        return f"{self.state_name} ({self.state_code})"
    


class DisputeCategory(MasterDropdown):
    """
    Dispute categorization by issue type.
    Used in: DisputeLog.category
    Values: storage_space, handling, manpower_ot, operations, mis_stock, billing
    """
    class Meta:
        db_table = 'dropdown_dispute_categories'
        verbose_name = 'Dispute Category'
        verbose_name_plural = 'Dispute Categories'


class RenewalStatus(MasterDropdown):
    """
    Agreement renewal tracker status.
    Used in: AgreementRenewalTracker.status
    Values: pending, in_progress, client_responded, renewed, not_renewed, cancelled
    """
    class Meta:
        db_table = 'dropdown_renewal_statuses'
        verbose_name = 'Renewal Status'
        verbose_name_plural = 'Renewal Statuses'


class RenewalActionType(MasterDropdown):
    """
    Agreement renewal workflow action types.
    Used in: AgreementRenewalLog.action_type
    Values: tracker_created, initial_email, reminder_1, reminder_2, reminder_3,
            final_intimation, sales_informed_1, sales_informed_2, client_response,
            status_changed, note_added, renewed, cancelled
    """
    class Meta:
        db_table = 'dropdown_renewal_action_types'
        verbose_name = 'Renewal Action Type'
        verbose_name_plural = 'Renewal Action Types'


# ============================================================================
# ADOBE SIGN E-SIGNATURE
# ============================================================================

class AgreementType(MasterDropdown):
    """
    Adobe Sign agreement document types.
    Used in: AdobeAgreement.agreement_type
    Values: client_agreement, sla_agreement, addendum_client, addendum_3pl
    """
    class Meta:
        db_table = 'dropdown_agreement_types'
        verbose_name = 'Agreement Type'
        verbose_name_plural = 'Agreement Types'


class AgreementCategory(MasterDropdown):
    """
    Adobe Sign agreement category (new vs renewal).
    Used in: AdobeAgreement.agreement_category
    Values: new, renewal
    """
    class Meta:
        db_table = 'dropdown_agreement_categories'
        verbose_name = 'Agreement Category'
        verbose_name_plural = 'Agreement Categories'


class GSTStatus(MasterDropdown):
    """
    Client GST registration status tracking.
    Used in: AdobeAgreement.gst_status
    Values: not_registered, registration_pending, registered, na
    """
    class Meta:
        db_table = 'dropdown_gst_statuses'
        verbose_name = 'GST Status'
        verbose_name_plural = 'GST Statuses'
