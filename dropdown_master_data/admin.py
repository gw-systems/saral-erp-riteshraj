"""
Master Data Admin Configuration
Admin interface for managing business-configurable dropdowns.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    # Geographic
    Region,
    StateCode,
    # Storage & Capacity
    StorageUnit,
    BillingUnit,
    HandlingUnit,
    # Transport
    VehicleType,
    # Workflow
    Priority,
    ApprovalStatus,
    BillingStatus,
    EscalationStatus,
    TicketStatus,
    # Operations
    QueryCategory,
    HolidayType,
    AdhocChargeType,
    AdhocBillingStatus,
    EscalationTerms,
    # Project Card Rates
    SalesChannel,
    HandlingBaseType,
    VASServiceType,
    VASUnit,
    OperationalCostType,
    # Project Config
    NoticePeriodDuration,
    OperationMode,
    MISStatus,
    # Warehouse Supply
    WarehouseGrade,
    BusinessType,
    PropertyType,
    SLAStatus,
    # Tickets & Contacts
    TicketType,
    WarehouseContactDepartment,
    # User & Notifications
    UserRole,
    NotificationType,
    MonthlyBillingStatus,
    ApprovalAction,
    AlertType,
    Severity,
    ActivityType,
    # Transactions
    TransactionSide,
    DisputeStatus,
    SeriesType,
    ProjectStatus,
    RateApplicability,
    HandlingDirection,
    FileType,
    DisputeCategory,
    RenewalStatus,
    RenewalActionType, 
)


class MasterDropdownAdmin(admin.ModelAdmin):
    """Base admin configuration for all master dropdown models"""
    
    list_display = ['code', 'label', 'is_active_badge', 'display_order', 'updated_at', 'updated_by']
    list_filter = ['is_active', 'created_at']
    search_fields = ['code', 'label']
    readonly_fields = ['created_at', 'updated_at', 'updated_by']
    ordering = ['display_order', 'code']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'label', 'display_order')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'updated_by'),
            'classes': ('collapse',)
        }),
    )
    
    def is_active_badge(self, obj):
        """Display active status as colored badge"""
        if obj.is_active:
            return format_html(
                '<span style="color: green; font-weight: bold;">● Active</span>'
            )
        return format_html(
            '<span style="color: red; font-weight: bold;">○ Inactive</span>'
        )
    is_active_badge.short_description = 'Status'
    
    def save_model(self, request, obj, form, change):
        """Auto-populate updated_by field"""
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
    
    def has_delete_permission(self, request, obj=None):
        """
        Disable delete button in admin.
        Prevents accidental deletion of referenced values.
        """
        return False


# ============================================================================
# GEOGRAPHIC
# ============================================================================

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['label', 'code', 'is_active', 'display_order']
    list_filter = ['is_active']
    search_fields = ['label', 'code']
    ordering = ['display_order', 'label']
    list_editable = ['display_order', 'is_active']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'label')
        }),
        ('Display Settings', {
            'fields': ('is_active', 'display_order')
        }),
    )


@admin.register(StateCode)
class StateCodeAdmin(admin.ModelAdmin):
    list_display = ['state_name', 'state_code', 'is_active', 'display_order', 'created_at']
    list_filter = ['is_active']
    search_fields = ['state_name', 'state_code']
    ordering = ['display_order', 'state_name']
    list_editable = ['display_order', 'is_active']
    
    fieldsets = (
        ('State Information', {
            'fields': ('state_code', 'state_name')
        }),
        ('Settings', {
            'fields': ('is_active', 'display_order')
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']



# ============================================================================
# STORAGE & CAPACITY UNITS
# ============================================================================

@admin.register(StorageUnit)
class StorageUnitAdmin(MasterDropdownAdmin):
    pass


@admin.register(BillingUnit)
class BillingUnitAdmin(MasterDropdownAdmin):
    pass


@admin.register(HandlingUnit)
class HandlingUnitAdmin(MasterDropdownAdmin):
    pass


# ============================================================================
# TRANSPORT & LOGISTICS
# ============================================================================

@admin.register(VehicleType)
class VehicleTypeAdmin(MasterDropdownAdmin):
    pass


# ============================================================================
# WORKFLOW STATES
# ============================================================================

@admin.register(Priority)
class PriorityAdmin(MasterDropdownAdmin):
    pass


@admin.register(ApprovalStatus)
class ApprovalStatusAdmin(MasterDropdownAdmin):
    pass


@admin.register(BillingStatus)
class BillingStatusAdmin(MasterDropdownAdmin):
    pass


@admin.register(EscalationStatus)
class EscalationStatusAdmin(MasterDropdownAdmin):
    pass


@admin.register(TicketStatus)
class TicketStatusAdmin(MasterDropdownAdmin):
    pass


# ============================================================================
# OPERATIONAL CATEGORIES
# ============================================================================

@admin.register(QueryCategory)
class QueryCategoryAdmin(MasterDropdownAdmin):
    pass


@admin.register(HolidayType)
class HolidayTypeAdmin(MasterDropdownAdmin):
    pass


@admin.register(AdhocChargeType)
class AdhocChargeTypeAdmin(MasterDropdownAdmin):
    pass


@admin.register(AdhocBillingStatus)
class AdhocBillingStatusAdmin(MasterDropdownAdmin):
    pass


@admin.register(EscalationTerms)
class EscalationTermsAdmin(MasterDropdownAdmin):
    pass


# ============================================================================
# PROJECT CARD RATE DIMENSIONS
# ============================================================================

@admin.register(SalesChannel)
class SalesChannelAdmin(MasterDropdownAdmin):
    pass


@admin.register(HandlingBaseType)
class HandlingBaseTypeAdmin(MasterDropdownAdmin):
    pass


@admin.register(VASServiceType)
class VASServiceTypeAdmin(MasterDropdownAdmin):
    pass


@admin.register(VASUnit)
class VASUnitAdmin(MasterDropdownAdmin):
    pass


@admin.register(OperationalCostType)
class OperationalCostTypeAdmin(MasterDropdownAdmin):
    pass


# ============================================================================
# PROJECT & CONTRACT CONFIGURATION
# ============================================================================

@admin.register(NoticePeriodDuration)
class NoticePeriodDurationAdmin(MasterDropdownAdmin):
    pass


@admin.register(OperationMode)
class OperationModeAdmin(MasterDropdownAdmin):
    pass


@admin.register(MISStatus)
class MISStatusAdmin(MasterDropdownAdmin):
    pass


# ============================================================================
# WAREHOUSE SUPPLY
# ============================================================================

@admin.register(WarehouseGrade)
class WarehouseGradeAdmin(MasterDropdownAdmin):
    pass


@admin.register(BusinessType)
class BusinessTypeAdmin(MasterDropdownAdmin):
    pass


@admin.register(PropertyType)
class PropertyTypeAdmin(MasterDropdownAdmin):
    pass


@admin.register(SLAStatus)
class SLAStatusAdmin(MasterDropdownAdmin):
    pass


# ============================================================================
# TICKETS & CONTACTS
# ============================================================================

@admin.register(TicketType)
class TicketTypeAdmin(MasterDropdownAdmin):
    pass


@admin.register(WarehouseContactDepartment)
class WarehouseContactDepartmentAdmin(MasterDropdownAdmin):
    pass


# ============================================================================
# USER & NOTIFICATIONS
# ============================================================================

@admin.register(UserRole)
class UserRoleAdmin(MasterDropdownAdmin):
    pass


@admin.register(NotificationType)
class NotificationTypeAdmin(MasterDropdownAdmin):
    pass


@admin.register(MonthlyBillingStatus)
class MonthlyBillingStatusAdmin(MasterDropdownAdmin):
    pass


@admin.register(ApprovalAction)
class ApprovalActionAdmin(MasterDropdownAdmin):
    pass


@admin.register(AlertType)
class AlertTypeAdmin(MasterDropdownAdmin):
    pass


@admin.register(Severity)
class SeverityAdmin(MasterDropdownAdmin):
    pass


@admin.register(ActivityType)
class ActivityTypeAdmin(MasterDropdownAdmin):
    pass


# ============================================================================
# TRANSACTIONS & OPERATIONS
# ============================================================================

@admin.register(TransactionSide)
class TransactionSideAdmin(MasterDropdownAdmin):
    pass


@admin.register(DisputeStatus)
class DisputeStatusAdmin(MasterDropdownAdmin):
    pass


@admin.register(SeriesType)
class SeriesTypeAdmin(MasterDropdownAdmin):
    pass


@admin.register(ProjectStatus)
class ProjectStatusAdmin(MasterDropdownAdmin):
    pass


@admin.register(RateApplicability)
class RateApplicabilityAdmin(MasterDropdownAdmin):
    pass


@admin.register(HandlingDirection)
class HandlingDirectionAdmin(MasterDropdownAdmin):
    pass


@admin.register(FileType)
class FileTypeAdmin(MasterDropdownAdmin):
    pass


@admin.register(DisputeCategory)
class DisputeCategoryAdmin(MasterDropdownAdmin):
    pass


@admin.register(RenewalStatus)
class RenewalStatusAdmin(MasterDropdownAdmin):
    pass


@admin.register(RenewalActionType)
class RenewalActionTypeAdmin(MasterDropdownAdmin):
    pass