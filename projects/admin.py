from django.contrib import admin
from .models import GstState, ProjectCode
from supply.models import CityCode, Location
from .models_client import ClientGroup, ClientCard, ClientContact, ClientGST, ClientDocument
from .models_system import SystemSettings
from .models_quotation import Quotation, QuotationLocation, QuotationItem, QuotationAudit
from .models_quotation_settings import QuotationSettings


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['id', 'city', 'state', 'location', 'is_active']
    list_filter = ['state', 'is_active']
    search_fields = ['city', 'state', 'location']
    ordering = ['state', 'city']


@admin.register(GstState)
class GstStateAdmin(admin.ModelAdmin):
    list_display = ('state_name', 'state_code', 'gst_number', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('state_name', 'state_code')


@admin.register(ProjectCode)
class ProjectCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'project_id', 'client_name', 'project_status', 'series_type')
    list_filter = ('series_type', 'project_status', 'state')
    search_fields = ('code', 'project_id', 'client_name', 'vendor_name')
    readonly_fields = ('created_at', 'updated_at')



# === QUOTATION MODELS ===

class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 1
    fields = ['item_description', 'custom_description', 'unit_cost', 'quantity', 'storage_unit_type', 'order']


class QuotationLocationInline(admin.TabularInline):
    model = QuotationLocation
    extra = 1
    fields = ['location_name', 'order']
    show_change_link = True


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ['quotation_number', 'client_company', 'client_name', 'date', 'status', 'grand_total', 'created_by']
    list_filter = ['status', 'date', 'created_at']
    search_fields = ['quotation_number', 'client_company', 'client_name', 'client_email']
    readonly_fields = ['quotation_number', 'created_at', 'updated_at']
    inlines = [QuotationLocationInline]

    fieldsets = [
        ('Client Information', {
            'fields': ['client_name', 'client_company', 'client_email', 'client_phone', 'client_address', 'client_gst_number']
        }),
        ('Quotation Details', {
            'fields': ['quotation_number', 'date', 'validity_period', 'gst_rate', 'status']
        }),
        ('Metadata', {
            'fields': ['created_by', 'created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    def save_model(self, request, obj, form, change):
        """Set created_by when creating new quotation."""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(QuotationLocation)
class QuotationLocationAdmin(admin.ModelAdmin):
    list_display = ['location_id', 'quotation', 'location_name', 'order', 'subtotal', 'grand_total']
    list_filter = ['quotation__status']
    search_fields = ['quotation__quotation_number', 'location_name']
    readonly_fields = ['subtotal', 'gst_amount', 'grand_total']
    inlines = [QuotationItemInline]


@admin.register(QuotationItem)
class QuotationItemAdmin(admin.ModelAdmin):
    list_display = ['item_id', 'location', 'item_description', 'unit_cost', 'quantity', 'total']
    list_filter = ['item_description', 'storage_unit_type']
    search_fields = ['location__location_name', 'custom_description']
    readonly_fields = ['total', 'display_unit_cost', 'display_quantity', 'display_total']


@admin.register(QuotationAudit)
class QuotationAuditAdmin(admin.ModelAdmin):
    list_display = ['audit_id', 'quotation', 'action', 'user', 'timestamp', 'ip_address']
    list_filter = ['action', 'timestamp']
    search_fields = ['quotation__quotation_number', 'user__username']
    readonly_fields = ['quotation', 'user', 'action', 'timestamp', 'changes', 'ip_address', 'additional_metadata']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(QuotationSettings)
class QuotationSettingsAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'default_gst_rate', 'default_validity_days', 'updated_at', 'updated_by']
    readonly_fields = ['google_docs_template_id', 'updated_at']

    def has_add_permission(self, request):
        return not QuotationSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# === OTHER MODELS (SIMPLE REGISTRATION) ===

@admin.register(ClientGroup)
class ClientGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'member_count')
    search_fields = ('name',)

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Members'


@admin.register(ClientCard)
class ClientCardAdmin(admin.ModelAdmin):
    list_display = ('client_code', 'client_legal_name', 'client_group', 'client_is_active')
    list_filter = ('client_group', 'client_is_active')
    search_fields = ('client_legal_name', 'client_trade_name', 'client_code')
    list_editable = ('client_group',)


admin.site.register(ClientContact)
admin.site.register(ClientGST)
admin.site.register(ClientDocument)
admin.site.register(SystemSettings)