from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    OperationsDailyUpdate,
    BillingStatement,
    DailySpaceUtilization,
    DailyEntryAuditLog,
    WarehouseHoliday,
    DailyMISLog,
    DisputeLog,
    DisputeComment,
    DisputeActivity,
    MonthlyBilling,
)

from operations.models_projectcard import (
    ProjectCard,
    StorageRate,
    StorageRateSlab,
    HandlingRate,
    ValueAddedService,
    InfrastructureCost,
    TransportRate,
)

from operations.models_agreements import (
    EscalationTracker,
    EscalationLog,
    AgreementRenewalTracker,
    AgreementRenewalLog,
)

from .models_adhoc import (
    AdhocBillingEntry,
    AdhocBillingLineItem,
    AdhocBillingAttachment,
)

from .models_lr import LorryReceipt, LRLineItem, LRAuditLog

from .models_porter_invoice import PorterInvoiceSession, PorterInvoiceFile


# ============================================================================
# EXISTING OPERATIONS MODELS
# ============================================================================

@admin.register(OperationsDailyUpdate)
class OperationsDailyUpdateAdmin(admin.ModelAdmin):
    list_display = ['project_id', 'operation_date', 'space_utilization', 'inventory_value', 'created_by']
    list_filter = ['operation_date']
    search_fields = ['project_id']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(BillingStatement)
class BillingStatementAdmin(admin.ModelAdmin):
    list_display = ['project_id', 'billing_month', 'status', 'v_total_amount', 'c_total_amount', 'margin_amount']
    list_filter = ['status', 'billing_month']
    search_fields = ['project_id']


@admin.register(DailySpaceUtilization)
class DailySpaceUtilizationAdmin(admin.ModelAdmin):
    list_display = ['project', 'entry_date', 'space_utilized', 'inventory_value', 'entered_by', 'created_at']
    list_filter = ['entry_date', 'project', 'entered_by']
    search_fields = ['project__code', 'project__client_name']
    date_hierarchy = 'entry_date'
    readonly_fields = ['created_at', 'updated_at']


@admin.register(DailyEntryAuditLog)
class DailyEntryAuditLogAdmin(admin.ModelAdmin):
    list_display = ['daily_entry', 'action', 'changed_by', 'changed_at']
    list_filter = ['action', 'changed_at']
    readonly_fields = ['daily_entry', 'action', 'changed_by', 'changed_at', 'old_values', 'new_values']


@admin.register(WarehouseHoliday)
class WarehouseHolidayAdmin(admin.ModelAdmin):
    list_display = ['warehouse_name', 'holiday_name', 'holiday_date', 'is_national', 'added_by']
    list_filter = ['is_national', 'warehouse_name', 'holiday_date']
    search_fields = ['warehouse_name', 'holiday_name']


@admin.register(DailyMISLog)
class DailyMISLogAdmin(admin.ModelAdmin):
    list_display = ['project', 'log_date', 'mis_sent', 'sent_by', 'sent_at']
    list_filter = ['mis_sent', 'log_date', 'project']
    search_fields = ['project__code', 'project__client_name']


@admin.register(DisputeLog)
class DisputeLogAdmin(admin.ModelAdmin):
    list_display = ['project', 'issue_date', 'dispute_type', 'severity', 'status', 'tat_days']
    list_filter = ['status', 'severity', 'dispute_type', 'issue_date']
    search_fields = ['project__code', 'project__client_name', 'comment']


@admin.register(DisputeComment)
class DisputeCommentAdmin(admin.ModelAdmin):
    list_display = ['dispute', 'user', 'created_at', 'has_attachment']
    list_filter = ['created_at', 'user']
    search_fields = ['dispute__title', 'comment', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at', 'updated_at']
    
    def has_attachment(self, obj):
        return bool(obj.attachment)
    has_attachment.boolean = True
    has_attachment.short_description = 'Attachment'


@admin.register(DisputeActivity)
class DisputeActivityAdmin(admin.ModelAdmin):
    list_display = ['dispute', 'activity_type', 'user', 'created_at']
    list_filter = ['activity_type', 'created_at', 'user']
    search_fields = ['dispute__title', 'description', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at']


# ============================================================================
# PROJECT CARD ADMIN (UPDATED WITH VERSIONING)
# ============================================================================

class StorageRateInline(admin.StackedInline):
    model = StorageRate
    extra = 0
    max_num = 2  # Client + Vendor
    fieldsets = (
        ('Basic Storage', {
            'fields': ('rate_for', 'space_type')
        }),
        ('Flat Rate', {
            'fields': ('minimum_billable_area', 'flat_rate_per_unit', 'monthly_billable_amount'),
        }),
        ('SAAS Charges', {
            'fields': ('saas_monthly_charge',),
        }),
        ('Notes', {
            'fields': ('remarks',),
        }),
    )


class HandlingRateInline(admin.TabularInline):
    model = HandlingRate
    extra = 1
    fields = ['rate_for', 'direction', 'channel', 'base_type', 'min_weight_kg', 'max_weight_kg', 'rate', 'condition', 'condition_value', 'remarks']


class ValueAddedServiceInline(admin.TabularInline):
    model = ValueAddedService
    extra = 1
    fields = ['rate_for', 'service_type', 'service_description', 'rate', 'unit']


class InfrastructureCostInline(admin.TabularInline):
    model = InfrastructureCost
    extra = 1
    fields = ['rate_for', 'cost_type', 'description', 'amount', 'is_at_actual']


@admin.register(ProjectCard)
class ProjectCardAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'project_link',
        'version_display',
        'status_badge',
        'agreement_period',
        'escalation_info',
        'valid_period',
        'created_at',
    ]
    
    list_filter = [
        'is_active',
        'version',
        'escalation_terms',
        'has_fixed_escalation',
        'created_at',
    ]
    
    search_fields = [
        'project__project_code',
        'project__project_id',
        'project__client_name',
    ]
    
    readonly_fields = [
        'version',
        'superseded_by',
        'created_by',
        'created_at',
        'updated_at',
        'last_modified_by',
        'escalation_display',
        'agreement_duration_months',
    ]
    
    fieldsets = (
        ('Version Info', {
            'fields': (
                'project',
                'version',
                'is_active',
                'superseded_by',
            ),
            'classes': ('wide',),
        }),
        ('Validity Period', {
            'fields': (
                'valid_from',
                'valid_to',
            ),
        }),
        ('Agreement Details', {
            'fields': (
                'agreement_start_date',
                'agreement_end_date',
                'agreement_duration_months',
                'yearly_escalation_date',
            ),
        }),
        ('Operational Dates', {
            'fields': (
                'billing_start_date',
                'operation_start_date',
            ),
        }),
        ('Escalation Terms', {
            'fields': (
                'escalation_terms',
                'has_fixed_escalation',
                'annual_escalation_percent',
                'escalation_display',
            ),
        }),
        ('Payment Terms', {
            'fields': (
                'storage_payment_days',
                'handling_payment_days',
            ),
        }),
        ('Financial', {
            'fields': (
                'security_deposit',
            ),
        }),
        ('Master Data Links', {
            'fields': (
                'client_card',
                'vendor_warehouse',
            ),
        }),
        ('Notes', {
            'fields': ('notes',),
        }),
        ('Audit Info', {
            'fields': (
                'created_by',
                'created_at',
                'last_modified_by',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    inlines = [
        StorageRateInline,
        HandlingRateInline,
        ValueAddedServiceInline,
        InfrastructureCostInline,
    ]
    
    def project_link(self, obj):
        url = reverse('admin:projects_projectcode_change', args=[obj.project.project_id])
        return format_html('<a href="{}">{}</a>', url, obj.project.project_code)
    project_link.short_description = 'Project'
    
    def version_display(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green; font-weight: bold;">v{} ✓</span>', obj.version)
        return format_html('<span style="color: gray;">v{}</span>', obj.version)
    version_display.short_description = 'Version'
    
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="background: #10b981; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">ACTIVE</span>')
        return format_html('<span style="background: #6b7280; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">ARCHIVED</span>')
    status_badge.short_description = 'Status'
    
    def agreement_period(self, obj):
        if obj.agreement_start_date and obj.agreement_end_date:
            return f"{obj.agreement_start_date.strftime('%d %b %Y')} → {obj.agreement_end_date.strftime('%d %b %Y')}"
        return "—"
    agreement_period.short_description = 'Agreement Period'
    
    def valid_period(self, obj):
        if obj.valid_from:
            if obj.valid_to:
                return f"{obj.valid_from.strftime('%d %b %Y')} → {obj.valid_to.strftime('%d %b %Y')}"
            else:
                return f"{obj.valid_from.strftime('%d %b %Y')} → Present"
        return "—"
    valid_period.short_description = 'Valid Period'
    
    def escalation_info(self, obj):
        return obj.escalation_display
    escalation_info.short_description = 'Escalation'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Creating new
            obj.created_by = request.user
        obj.last_modified_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(StorageRateSlab)
class StorageRateSlabAdmin(admin.ModelAdmin):
    list_display = ['project_card', 'rate_for', 'space_type', 'min_quantity', 'max_quantity', 'rate_per_unit']
    list_filter = ['rate_for', 'space_type']
    search_fields = ['project_card__project__project_code', 'project_card__project__client_name']
    ordering = ['project_card', 'rate_for', 'min_quantity']
    
    fieldsets = (
        ('Project Card', {
            'fields': ('project_card',)
        }),
        ('Rate Details', {
            'fields': ('rate_for', 'space_type')
        }),
        ('Slab Range', {
            'fields': ('min_quantity', 'max_quantity')
        }),
        ('Pricing', {
            'fields': ('rate_per_unit',)
        }),
        ('Notes', {
            'fields': ('remarks',)
        }),
    )


# ============================================================================
# ESCALATION TRACKER ADMIN
# ============================================================================

class EscalationLogInline(admin.TabularInline):
    model = EscalationLog
    extra = 0
    readonly_fields = ['action_type', 'action_date', 'performed_by', 'created_at']
    fields = ['action_date', 'action_type', 'notes', 'performed_by']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EscalationTracker)
class EscalationTrackerAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'project_link',
        'year_display',
        'escalation_date_display',
        'percentage_display',
        'status_badge',
        'overdue_display',
        'created_at',
    ]
    
    list_filter = [
        'status',
        'escalation_year',
        'client_acknowledged',
        'created_at',
    ]
    
    search_fields = [
        'project_card__project__project_code',
        'project_card__project__project_id',
        'project_card__project__client_name',
    ]
    
    readonly_fields = [
        'escalation_effective_date',
        'is_overdue',
        'days_overdue',
        'days_until_due',
        'created_by',
        'created_at',
        'updated_at',
        'last_updated_by',
    ]
    
    fieldsets = (
        ('Tracker Info', {
            'fields': (
                'project_card',
                'escalation_year',
                'escalation_percentage',
                'status',
            ),
        }),
        ('Calculated Dates', {
            'fields': (
                'escalation_effective_date',
                'is_overdue',
                'days_overdue',
                'days_until_due',
            ),
            'classes': ('collapse',),
        }),
        ('Email Tracking', {
            'fields': (
                'initial_intimation_sent',
                'first_reminder_sent',
                'second_reminder_sent',
                'final_notice_sent',
            ),
        }),
        ('Stakeholder Communication', {
            'fields': (
                'sales_manager_informed_date',
                'sales_manager_notes',
                'finance_team_informed_date',
                'finance_team_notes',
            ),
        }),
        ('Client Response', {
            'fields': (
                'client_acknowledged',
                'client_acknowledgment_date',
                'client_response_notes',
            ),
        }),
        ('Completion', {
            'fields': (
                'escalation_applied_date',
                'applied_percentage',
            ),
        }),
        ('Notes', {
            'fields': ('remarks',),
        }),
        ('Audit', {
            'fields': (
                'created_by',
                'created_at',
                'last_updated_by',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    inlines = [EscalationLogInline]
    
    def project_link(self, obj):
        return obj.project_card.project.project_code
    project_link.short_description = 'Project'
    
    def year_display(self, obj):
        return f"Year {obj.escalation_year}"
    year_display.short_description = 'Year'
    
    def escalation_date_display(self, obj):
        date = obj.escalation_effective_date
        if date:
            return date.strftime('%d %b %Y')
        return "—"
    escalation_date_display.short_description = 'Escalation Date'
    
    def percentage_display(self, obj):
        if obj.escalation_percentage:
            return f"{obj.escalation_percentage}%"
        return "Mutually Agreed"
    percentage_display.short_description = 'Escalation %'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#fbbf24',
            'in_progress': '#3b82f6',
            'client_acknowledged': '#10b981',
            'escalation_applied': '#059669',
            'disputed': '#ef4444',
            'cancelled': '#6b7280',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def overdue_display(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color: red; font-weight: bold;">🚨 {} days</span>', obj.days_overdue)
        elif obj.days_until_due and obj.days_until_due <= 30:
            return format_html('<span style="color: orange;">{} days</span>', obj.days_until_due)
        return "—"
    overdue_display.short_description = 'Overdue'


@admin.register(EscalationLog)
class EscalationLogAdmin(admin.ModelAdmin):
    list_display = ['action_date', 'tracker', 'action_type', 'performed_by', 'created_at']
    list_filter = ['action_type', 'action_date']
    search_fields = ['tracker__project_card__project__project_code', 'notes']
    readonly_fields = ['tracker', 'action_type', 'action_date', 'performed_by', 'created_at']
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


# ============================================================================
# RENEWAL TRACKER ADMIN
# ============================================================================

class AgreementRenewalLogInline(admin.TabularInline):
    model = AgreementRenewalLog
    extra = 0
    readonly_fields = ['action_type', 'action_date', 'performed_by', 'created_at']
    fields = ['action_date', 'action_type', 'notes', 'performed_by']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AgreementRenewalTracker)
class AgreementRenewalTrackerAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'project_link',
        'renewal_date_display',
        'status_badge',
        'overdue_display',
        'client_responded',
        'created_at',
    ]
    
    list_filter = [
        'status',
        'client_responded',
        'created_at',
    ]
    
    search_fields = [
        'project_card__project__project_code',
        'project_card__project__project_id',
        'project_card__project__client_name',
    ]
    
    readonly_fields = [
        'renewal_due_date',
        'is_overdue',
        'days_overdue',
        'days_until_due',
        'created_by',
        'created_at',
        'updated_at',
        'last_updated_by',
    ]
    
    fieldsets = (
        ('Tracker Info', {
            'fields': (
                'project_card',
                'status',
            ),
        }),
        ('Calculated Info', {
            'fields': (
                'renewal_due_date',
                'is_overdue',
                'days_overdue',
                'days_until_due',
            ),
            'classes': ('collapse',),
        }),
        ('Email Tracking', {
            'fields': (
                'initial_email_sent',
                'first_reminder_sent',
                'second_reminder_sent',
                'third_reminder_sent',
                'final_intimation_sent',
            ),
        }),
        ('Sales Manager Communication', {
            'fields': (
                'sales_manager_informed_1_date',
                'sales_manager_informed_1_notes',
                'sales_manager_informed_2_date',
                'sales_manager_informed_2_notes',
            ),
        }),
        ('Client Response', {
            'fields': (
                'client_responded',
                'client_response_date',
                'client_response_summary',
            ),
        }),
        ('Completion', {
            'fields': (
                'renewal_completed_date',
            ),
        }),
        ('Notes', {
            'fields': ('remarks',),
        }),
        ('Audit', {
            'fields': (
                'created_by',
                'created_at',
                'last_updated_by',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    inlines = [AgreementRenewalLogInline]
    
    def project_link(self, obj):
        return obj.project_card.project.project_code
    project_link.short_description = 'Project'
    
    def renewal_date_display(self, obj):
        date = obj.renewal_due_date
        if date:
            return date.strftime('%d %b %Y')
        return "—"
    renewal_date_display.short_description = 'Renewal Due'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#fbbf24',
            'in_progress': '#3b82f6',
            'client_responded': '#10b981',
            'renewed': '#059669',
            'not_renewed': '#ef4444',
            'cancelled': '#6b7280',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def overdue_display(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color: red; font-weight: bold;">🚨 {} days</span>', obj.days_overdue)
        elif obj.days_until_due and obj.days_until_due <= 30:
            return format_html('<span style="color: orange;">{} days</span>', obj.days_until_due)
        return "—"
    overdue_display.short_description = 'Overdue'


@admin.register(AgreementRenewalLog)
class AgreementRenewalLogAdmin(admin.ModelAdmin):
    list_display = ['action_date', 'tracker', 'action_type', 'performed_by', 'created_at']
    list_filter = ['action_type', 'action_date']
    search_fields = ['tracker__project_card__project__project_code', 'notes']
    readonly_fields = ['tracker', 'action_type', 'action_date', 'performed_by', 'created_at']
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


# ============================================================================
# ADHOC BILLING ADMIN
# ============================================================================

class AdhocBillingLineItemInline(admin.TabularInline):
    model = AdhocBillingLineItem
    extra = 0
    fields = ['side', 'charge_type', 'description', 'quantity', 'rate', 'unit', 'amount']
    readonly_fields = ['amount']


class AdhocBillingAttachmentInline(admin.TabularInline):
    model = AdhocBillingAttachment
    extra = 0
    fields = ['attachment_type', 'file', 'filename', 'uploaded_at']
    readonly_fields = ['uploaded_at', 'uploaded_by']
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing existing
            return self.readonly_fields + ('uploaded_by',)
        return self.readonly_fields
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AdhocBillingEntry)
class AdhocBillingEntryAdmin(admin.ModelAdmin):
    list_display = ['id', 'project', 'event_date', 'total_client_amount', 'total_vendor_amount', 'status', 'created_by']
    list_filter = ['status', 'event_date', 'service_month']
    search_fields = ['project__project_code', 'project__client_name']
    readonly_fields = ['total_client_amount', 'total_vendor_amount', 'service_month', 'created_at', 'updated_at']
    inlines = [AdhocBillingLineItemInline, AdhocBillingAttachmentInline]


@admin.register(AdhocBillingLineItem)
class AdhocBillingLineItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'entry', 'side', 'charge_type', 'quantity', 'rate', 'unit', 'amount']
    list_filter = ['side', 'charge_type']
    readonly_fields = ['amount', 'created_at']


# ============================================================================
# MONTHLY BILLING ADMIN
# ============================================================================

@admin.register(MonthlyBilling)
class MonthlyBillingAdmin(admin.ModelAdmin):
    """
    Comprehensive admin interface for Monthly Billing with workflow management
    """
    
    # List Display
    list_display = [
        'id',
        'project_link',
        'billing_month',
        'status_badge',
        'vendor_total_display',
        'client_total_display',
        'margin_display',
        'margin_percentage_display',
        'is_locked_display',
        'created_by',
        'created_at',
    ]
    
    # List Filters
    list_filter = [
        'status',
        'billing_month',
        'created_at',
        'submitted_at',
        'controller_reviewed_at',
        'finance_reviewed_at',
        'project_card_missing',
    ]
    
    # Search Fields
    search_fields = [
        'project__project_id',
        'project__project_code',
        'project__client_name',
        'created_by__username',
        'created_by__first_name',
        'created_by__last_name',
    ]
    
    # Read-only Fields
    readonly_fields = [
        'id',
        'vendor_total',
        'client_total',
        'margin_amount',
        'margin_percentage',
        'created_at',
        'updated_at',
        'submitted_at',
        'controller_reviewed_at',
        'finance_reviewed_at',
        'edit_locked_at',
        'workflow_history',
    ]
    
    # Fieldsets
    fieldsets = (
        ('📋 Basic Information', {
            'fields': (
                'id',
                'project',
                'billing_month',
                'status',
                'project_card_missing',
                'project_card_used',
            )
        }),
        ('📦 Storage', {
            'fields': (
                'storage_min_space',
                'storage_additional_space',
                'storage_unit_type',
                'storage_days',
                'storage_remarks',
                ('vendor_storage_rate', 'vendor_storage_cost'),
                ('client_storage_rate', 'client_storage_billing'),
            )
        }),
        ('📥 Handling IN', {
            'fields': (
                'handling_in_quantity',
                'handling_in_unit_type',
                'handling_in_remarks',
                ('vendor_handling_in_rate', 'vendor_handling_in_cost'),
                ('client_handling_in_rate', 'client_handling_in_billing'),
            )
        }),
        ('📤 Handling OUT', {
            'fields': (
                'handling_out_quantity',
                'handling_out_unit_type',
                'handling_out_remarks',
                ('vendor_handling_out_rate', 'vendor_handling_out_cost'),
                ('client_handling_out_rate', 'client_handling_out_billing'),
            )
        }),
        ('🚚 Transport', {
            'fields': (
                'vendor_transport_vehicle_type',
                'vendor_transport_amount',
                'vendor_transport_remarks',
                'client_transport_vehicle_type',
                'client_transport_amount',
                'client_transport_remarks',
            )
        }),
        ('⚙️ Miscellaneous', {
            'fields': (
                'vendor_misc_amount',
                'vendor_misc_description',
                'client_misc_amount',
                'client_misc_description',
            )
        }),
        ('💰 Totals & Margins', {
            'fields': (
                'vendor_total',
                'client_total',
                'margin_amount',
                'margin_percentage',
            )
        }),
        ('📧 MIS Reference', {
            'fields': (
                'mis_email_subject',
                'mis_link',
            ),
            'classes': ('collapse',),
        }),
        ('🔄 Workflow', {
            'fields': (
                'workflow_history',
                'created_by',
                'created_at',
                'updated_at',
                'submitted_by',
                'submitted_at',
                'rejection_deadline',
            )
        }),
        ('👤 Controller Review', {
            'fields': (
                'controller_reviewed_by',
                'controller_reviewed_at',
                'controller_action',
                'controller_remarks',
            ),
            'classes': ('collapse',),
        }),
        ('💼 Finance Review', {
            'fields': (
                'finance_reviewed_by',
                'finance_reviewed_at',
                'finance_action',
                'finance_remarks',
                'edit_locked_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    # Ordering
    ordering = ['-billing_month', '-created_at']
    
    # Date Hierarchy
    date_hierarchy = 'billing_month'
    
    # Actions
    actions = ['export_to_csv', 'recalculate_totals']
    
    # ============================================================================
    # CUSTOM DISPLAY METHODS
    # ============================================================================
    
    @admin.display(description='Project', ordering='project__project_code')
    def project_link(self, obj):
        """Display project as clickable link"""
        url = reverse('admin:projects_projectcode_change', args=[obj.project.pk])
        return format_html(
            '<a href="{}" target="_blank"><strong>{}</strong><br><small>{}</small></a>',
            url,
            obj.project.project_code,
            obj.project.client_name[:30]
        )
    
    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        """Display status with colored badge"""
        colors = {
            'draft': '#6B7280',
            'pending_controller': '#3B82F6',
            'controller_rejected': '#EF4444',
            'pending_finance': '#8B5CF6',
            'finance_rejected': '#DC2626',
            'approved': '#10B981',
        }
        color = colors.get(obj.status_id, '#6B7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 12px; '
            'border-radius: 12px; font-size: 11px; font-weight: 600;">{}</span>',
            color,
            obj.status.label
        )
    
    @admin.display(description='Vendor Total', ordering='vendor_total')
    def vendor_total_display(self, obj):
        """Display vendor total with currency"""
        return format_html('₹{:,.2f}', obj.vendor_total)
    
    @admin.display(description='Client Total', ordering='client_total')
    def client_total_display(self, obj):
        """Display client total with currency"""
        return format_html('₹{:,.2f}', obj.client_total)
    
    @admin.display(description='Margin (₹)', ordering='margin_amount')
    def margin_display(self, obj):
        """Display margin with color coding"""
        color = '#10B981' if obj.margin_amount > 0 else '#EF4444'
        return format_html(
            '<span style="color: {}; font-weight: 600;">₹{:,.2f}</span>',
            color,
            obj.margin_amount
        )
    
    @admin.display(description='Margin %', ordering='margin_percentage')
    def margin_percentage_display(self, obj):
        """Display margin percentage"""
        return format_html('{}%', round(obj.margin_percentage, 1))
    
    @admin.display(description='Locked', boolean=True)
    def is_locked_display(self, obj):
        """Display lock status"""
        return obj.is_locked()
    
    @admin.display(description='Workflow History')
    def workflow_history(self, obj):
        """Display complete workflow timeline"""
        history = []
        
        if obj.created_at:
            history.append(f'✏️ Created: {obj.created_at.strftime("%d %b %Y, %I:%M %p")} by {obj.created_by.get_full_name()}')
        
        if obj.submitted_at:
            history.append(f'📤 Submitted: {obj.submitted_at.strftime("%d %b %Y, %I:%M %p")} by {obj.submitted_by.get_full_name()}')
        
        if obj.controller_reviewed_at:
            action = '✅ Approved' if obj.controller_action_id == 'approved' else '❌ Rejected'
            history.append(f'{action} by Controller: {obj.controller_reviewed_at.strftime("%d %b %Y, %I:%M %p")} by {obj.controller_reviewed_by.get_full_name()}')
            if obj.controller_remarks:
                history.append(f'   Remarks: {obj.controller_remarks}')
        
        if obj.finance_reviewed_at:
            action = '✅ Approved' if obj.finance_action_id == 'approved' else '❌ Rejected'
            history.append(f'{action} by Finance: {obj.finance_reviewed_at.strftime("%d %b %Y, %I:%M %p")} by {obj.finance_reviewed_by.get_full_name()}')
            if obj.finance_remarks:
                history.append(f'   Remarks: {obj.finance_remarks}')
        
        if obj.edit_locked_at:
            history.append(f'🔒 Locked: {obj.edit_locked_at.strftime("%d %b %Y, %I:%M %p")}')
        
        return format_html('<br>'.join(history))
    
    # ============================================================================
    # CUSTOM ACTIONS
    # ============================================================================
    
    @admin.action(description='Export selected to CSV')
    def export_to_csv(self, request, queryset):
        """Export selected billings to CSV"""
        import csv
        from django.http import HttpResponse
        from datetime import datetime
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="monthly_billings_{datetime.now().strftime("%Y%m%d")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Project Code', 'Client Name', 'Billing Month', 'Status',
            'Vendor Total', 'Client Total', 'Margin Amount', 'Margin %',
            'Created By', 'Created At', 'Locked'
        ])
        
        for billing in queryset:
            writer.writerow([
                billing.id,
                billing.project.project_code,
                billing.project.client_name,
                billing.billing_month.strftime('%B %Y'),
                billing.status.label,
                billing.vendor_total,
                billing.client_total,
                billing.margin_amount,
                round(billing.margin_percentage, 2),
                billing.created_by.get_full_name(),
                billing.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'Yes' if billing.is_locked() else 'No'
            ])
        
        self.message_user(request, f'Exported {queryset.count()} billings to CSV')
        return response
    
    @admin.action(description='Recalculate totals')
    def recalculate_totals(self, request, queryset):
        """Recalculate totals for selected billings"""
        count = 0
        for billing in queryset:
            billing.calculate_totals()
            billing.save(update_fields=['vendor_total', 'client_total', 'margin_amount', 'margin_percentage'])
            count += 1
        
        self.message_user(request, f'Recalculated totals for {count} billings')
    
    # ============================================================================
    # PERMISSIONS
    # ============================================================================
    
    def has_delete_permission(self, request, obj=None):
        """Only allow delete if in draft status"""
        if obj:
            return obj.status_id == 'draft'
        return True
    
    def get_readonly_fields(self, request, obj=None):
        """Make fields readonly if locked"""
        readonly = list(self.readonly_fields)
        
        if obj and obj.is_locked():
            # If locked, make everything readonly except remarks fields
            readonly.extend([
                'storage_min_space', 'storage_additional_space', 'storage_unit_type',
                'storage_days', 'storage_remarks',
                'handling_in_quantity', 'handling_in_unit_type', 'handling_in_remarks',
                'handling_out_quantity', 'handling_out_unit_type', 'handling_out_remarks',
                'vendor_transport_vehicle_type', 'vendor_transport_amount', 'vendor_transport_remarks',
                'client_transport_vehicle_type', 'client_transport_amount', 'client_transport_remarks',
                'vendor_misc_amount', 'vendor_misc_description',
                'client_misc_amount', 'client_misc_description',
                'mis_email_subject', 'mis_link',
            ])
        
        return readonly
    
    # ============================================================================
    # LIST CUSTOMIZATION
    # ============================================================================
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related(
            'project',
            'status',
            'storage_unit_type',
            'handling_in_unit_type',
            'handling_out_unit_type',
            'vendor_transport_vehicle_type',
            'client_transport_vehicle_type',
            'created_by',
            'submitted_by',
            'controller_reviewed_by',
            'finance_reviewed_by',
        )


# ============================================================================
# LORRY RECEIPT (LR) ADMIN
# ============================================================================

class LRLineItemInline(admin.TabularInline):
    model = LRLineItem
    extra = 1
    fields = ['order', 'packages', 'description', 'actual_weight', 'charged_weight', 'amount']


class LRAuditLogInline(admin.TabularInline):
    model = LRAuditLog
    extra = 0
    readonly_fields = ['action', 'changed_by', 'changed_at', 'old_values', 'new_values', 'change_reason']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LorryReceipt)
class LorryReceiptAdmin(admin.ModelAdmin):
    list_display = ['lr_number', 'lr_date', 'from_location', 'to_location', 'vehicle_no', 'project', 'created_by', 'is_deleted']
    list_filter = ['lr_date', 'is_deleted', 'gst_paid_by']
    search_fields = ['lr_number', 'from_location', 'to_location', 'consignor_name', 'consignor_address', 'consignee_name', 'consignee_address']
    readonly_fields = ['lr_number', 'created_at', 'updated_at']
    inlines = [LRLineItemInline, LRAuditLogInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('project', 'created_by', 'last_modified_by')


@admin.register(LRAuditLog)
class LRAuditLogAdmin(admin.ModelAdmin):
    list_display = ['lr', 'action', 'changed_by', 'changed_at']
    list_filter = ['action', 'changed_at']
    readonly_fields = ['lr', 'action', 'changed_by', 'changed_at', 'old_values', 'new_values', 'change_reason']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ============================================================================
# PORTER INVOICE EDITOR ADMIN
# ============================================================================

class PorterInvoiceFileInline(admin.TabularInline):
    model = PorterInvoiceFile
    extra = 0
    fields = ['original_filename', 'crn', 'status', 'old_total', 'new_total', 'error_message']
    readonly_fields = ['original_filename', 'crn', 'status', 'old_total', 'new_total', 'error_message']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PorterInvoiceSession)
class PorterInvoiceSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'session_type', 'status', 'total_files', 'success_count', 'error_count', 'created_by', 'created_at']
    list_filter = ['session_type', 'status', 'created_at']
    search_fields = ['created_by__first_name', 'created_by__last_name']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [PorterInvoiceFileInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')


@admin.register(PorterInvoiceFile)
class PorterInvoiceFileAdmin(admin.ModelAdmin):
    list_display = ['id', 'original_filename', 'crn', 'status', 'old_total', 'new_total', 'session']
    list_filter = ['status']
    search_fields = ['original_filename', 'crn']
    readonly_fields = ['created_at']