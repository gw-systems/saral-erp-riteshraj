from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from django.db.models import Sum, Count
from django.http import HttpResponseRedirect
from django.urls import reverse
from .models import (
    Order,
    OrderStatus,
    PaymentMode,
    FTLOrder,
    Courier,
    CourierZoneRate,
    CityRoute,
    CustomZone,
    CustomZoneRate,
    SystemConfig,
    FTLRate,
    ZoneRule,
    LocationAlias,
    Warehouse,
)


from .models_refactored import FeeStructure, ServiceConstraints, FuelConfiguration, RoutingLogic

class FeeStructureInline(admin.StackedInline):
    model = FeeStructure
    verbose_name = "Fee Structure Configuration"
    can_delete = False

class ServiceConstraintsInline(admin.StackedInline):
    model = ServiceConstraints
    verbose_name = "Service Constraints"
    can_delete = False

class FuelConfigurationInline(admin.StackedInline):
    model = FuelConfiguration
    verbose_name = "Fuel Surcharge Configuration"
    can_delete = False

class RoutingLogicInline(admin.StackedInline):
    model = RoutingLogic
    verbose_name = "Routing Logic Config"
    can_delete = False

class CourierZoneRateInline(admin.TabularInline):
    model = CourierZoneRate
    extra = 0
    fields = ['zone_code', 'rate_type', 'rate']
    verbose_name = "Standard Zone Rate"
    verbose_name_plural = "Standard Zone Rates (Zones A-F)"
    ordering = ['zone_code', 'rate_type']


class CityRouteInline(admin.TabularInline):
    model = CityRoute
    extra = 1
    fields = ['city_name', 'rate_per_kg']
    verbose_name = "City Route"
    verbose_name_plural = "City Routes (add all destination cities and their rates)"


class CustomZoneInline(admin.TabularInline):
    model = CustomZone
    extra = 1
    fields = ['location_name', 'zone_code']
    verbose_name = "Zone Mapping"
    verbose_name_plural = "Zone Mappings (map locations to zone codes)"


class CustomZoneRateInline(admin.TabularInline):
    model = CustomZoneRate
    extra = 1
    fields = ['from_zone', 'to_zone', 'rate_per_kg']
    verbose_name = "Zone Rate"
    verbose_name_plural = "Zone Matrix (rates between zone pairs)"






class BusinessSegmentFilter(admin.SimpleListFilter):
    title = 'Business Segment'
    parameter_name = 'business_segment'

    def lookups(self, request, model_admin):
        return (
            ('b2c', 'B2C (< 20kg)'),
            ('b2b', 'B2B (>= 20kg)'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'b2c':
            return queryset.filter(constraints_config__min_weight__lt=20)
        if self.value() == 'b2b':
            return queryset.filter(constraints_config__min_weight__gte=20)
        return queryset


@admin.register(Courier)
class CourierAdmin(admin.ModelAdmin):
    # Only show main fields, hide legacy big list
    list_display = ['courier_code', '__str__', 'get_business_segment', 'aggregator', 'display_name', 'service_category', 'carrier_type', 'is_active', 'updated_at']
    list_filter = [BusinessSegmentFilter, 'aggregator', 'service_category', 'is_active']
    search_fields = ['courier_code', 'name', 'display_name']
    actions = ['download_rate_card_pdf']

    def get_business_segment(self, obj):
        try:
            min_w = obj.constraints_config.min_weight
            return "B2C" if min_w < 20 else "B2B"
        except:
            return "B2C" # Default
    get_business_segment.short_description = "Segment"
    get_business_segment.admin_order_field = 'constraints_config__min_weight'
    
    inlines = [
        FeeStructureInline,
        ServiceConstraintsInline,
        FuelConfigurationInline,
        RoutingLogicInline,
        # Conditional inlines are tricky if not dynamic, but we can just add them all 
        # or keep the get_inlines logic from before but appended
    ]

    def get_inlines(self, request, obj=None):
        """Show different inlines based on routing logic"""
        default_inlines = [
            FeeStructureInline,
            ServiceConstraintsInline,
            FuelConfigurationInline,
            RoutingLogicInline
        ]
        
        # We need to check obj.routing_config.logic_type if moved, or obj.rate_logic fallback using property
        # For now assume legacy column usage for logic checking
        if obj and obj.rate_logic == 'City_To_City':
            return default_inlines + [CityRouteInline]

        elif obj and obj.rate_logic == 'Zonal_Custom':
            return default_inlines + [CustomZoneInline, CustomZoneRateInline]
        elif obj and obj.rate_logic == 'Zonal_Standard':
            return default_inlines + [CourierZoneRateInline]
        return default_inlines
    
    # We remove the fieldsets that referenced legacy fields because they will error if fields are deleted
    # Instead rely on Inlines

    def download_rate_card_pdf(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Select exactly one carrier to download a rate card PDF.",
                level=messages.WARNING,
            )
            return None

        courier = queryset.first()
        url = reverse("operations:courier:generate-rate-card", kwargs={"pk": courier.pk})
        return HttpResponseRedirect(url)

    download_rate_card_pdf.short_description = "Download Rate Card PDF"

    def changelist_view(self, request, extra_context=None):
        if request.GET.get("admin") == "1":
            return super().changelist_view(request, extra_context=extra_context)
        return HttpResponseRedirect(reverse("operations:courier:dashboard"))


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin interface for Order management"""
    list_display = [
        'order_number', 'recipient_name', 'status', 'carrier', 'courier_warehouse_display',
        'payment_mode', 'total_cost', 'created_at', 'booked_at'
    ]
    list_filter = ['status', 'carrier', 'warehouse', 'payment_mode', 'created_at']
    search_fields = ['order_number', 'external_order_id', 'recipient_name', 'awb_number', 'recipient_contact']
    readonly_fields = ['order_number', 'created_at', 'updated_at', 'volumetric_weight', 'applicable_weight']
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'external_order_id', 'status', 'carrier', 'warehouse', 'awb_number')
        }),
        ('Recipient Details', {
            'fields': (
                'recipient_name', 'recipient_contact', 'recipient_phone', 'recipient_email',
                'recipient_address', 'recipient_pincode', 'recipient_city', 'recipient_state'
            )
        }),
        ('Sender Details', {
            'fields': ('sender_name', 'sender_address', 'sender_pincode', 'sender_phone')
        }),
        ('Package Details', {
            'fields': (
                'weight', 'length', 'width', 'height', 
                'volumetric_weight', 'applicable_weight'
            )
        }),
        ('Item Details', {
            'fields': ('item_type', 'sku', 'quantity', 'item_amount')
        }),
        ('Payment & Pricing', {
            'fields': ('payment_mode', 'order_value', 'total_cost', 'cost_breakdown')
        }),
        ('Shipment Details', {
            'fields': ('zone_applied', 'mode', 'shipdaak_shipment_id', 'shipdaak_label_url')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'booked_at')
        }),
        ('Additional Info', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )

    def courier_warehouse_display(self, obj):
        return obj.warehouse
    courier_warehouse_display.short_description = "Courier Warehouse"
    courier_warehouse_display.admin_order_field = "warehouse__name"
    
    def get_readonly_fields(self, request, obj=None):
        """Make certain fields readonly based on order status"""
        readonly = list(self.readonly_fields)
        
        # If order is booked or later, make booked_at readonly too
        if obj and obj.status != OrderStatus.DRAFT:
            if 'booked_at' not in readonly:
                readonly.append('booked_at')
        
        return readonly
    
    actions = ['mark_as_booked', 'mark_as_cancelled']
    
    def mark_as_booked(self, request, queryset):
        """Mark selected orders as booked"""
        from django.utils import timezone
        count = 0
        for order in queryset:
            if order.status == OrderStatus.DRAFT:
                order.status = OrderStatus.BOOKED
                order.booked_at = timezone.now()
                order.save()
                count += 1
        self.message_user(request, f'{count} order(s) marked as booked.')
    mark_as_booked.short_description = "Mark selected orders as BOOKED"
    
    def mark_as_cancelled(self, request, queryset):
        """Mark selected orders as cancelled"""
        count = queryset.update(status=OrderStatus.CANCELLED)
        self.message_user(request, f'{count} order(s) marked as cancelled.')
    mark_as_cancelled.short_description = "Mark selected orders as CANCELLED"

    def changelist_view(self, request, extra_context=None):
        if request.GET.get("admin") == "1":
            return super().changelist_view(request, extra_context=extra_context)
        return HttpResponseRedirect(reverse("operations:courier:orders-dashboard"))


@admin.register(FTLOrder)
class FTLOrderAdmin(admin.ModelAdmin):
    """Admin interface for FTL Order management"""
    list_display = [
        'order_number', 'name', 'source_city', 'destination_city',
        'container_type', 'status', 'total_price', 'created_at', 'booked_at'
    ]
    list_filter = ['status', 'container_type', 'created_at']
    search_fields = ['order_number', 'name', 'email', 'phone', 'source_city', 'destination_city']
    readonly_fields = ['order_number', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'status')
        }),
        ('Contact Details', {
            'fields': ('name', 'email', 'phone')
        }),
        ('Source Location', {
            'fields': ('source_city', 'source_address', 'source_pincode')
        }),
        ('Destination Location', {
            'fields': ('destination_city', 'destination_address', 'destination_pincode')
        }),
        ('Container & Pricing', {
            'fields': (
                'container_type', 'base_price', 'escalation_amount',
                'price_with_escalation', 'gst_amount', 'total_price'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'booked_at')
        }),
        ('Additional Info', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_booked', 'mark_as_cancelled']
    
    def mark_as_booked(self, request, queryset):
        """Mark selected FTL orders as booked"""
        from django.utils import timezone
        count = 0
        for order in queryset:
            if order.status == OrderStatus.DRAFT:
                order.status = OrderStatus.BOOKED
                order.booked_at = timezone.now()
                order.save()
                count += 1
        self.message_user(request, f'{count} FTL order(s) marked as booked.')
    mark_as_booked.short_description = "Mark selected FTL orders as BOOKED"
    
    def mark_as_cancelled(self, request, queryset):
        """Mark selected FTL orders as cancelled"""
        count = queryset.update(status=OrderStatus.CANCELLED)
        self.message_user(request, f'{count} FTL order(s) marked as cancelled.')
    mark_as_cancelled.short_description = "Mark selected FTL orders as CANCELLED"


@admin.register(FTLRate)
class FTLRateAdmin(admin.ModelAdmin):
    list_display = ('source_city', 'destination_city', 'truck_type', 'rate', 'updated_at')
    list_filter = ('truck_type', 'source_city')
    search_fields = ('source_city', 'destination_city')
    

@admin.register(ZoneRule)
class ZoneRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'rule_type', 'is_active')
    list_filter = ('rule_type', 'is_active')
    search_fields = ('name',)
    

@admin.register(LocationAlias)
class LocationAliasAdmin(admin.ModelAdmin):
    list_display = ('alias', 'standard_name', 'category')
    list_filter = ('category',)
    search_fields = ('alias', 'standard_name')


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    """Admin interface for global system configuration"""
    list_display = ['__str__', 'escalation_rate', 'gst_rate', 'diesel_price_current']
    
    def has_add_permission(self, request):
        # Singleton pattern - only one record allowed
        if SystemConfig.objects.exists():
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = (
        "courier_warehouse_name",
        "city",
        "state",
        "pincode",
        "contact_name",
        "shipdaak_pickup_id",
        "shipdaak_rto_id",
        "is_active",
        "updated_at",
    )
    search_fields = ("name", "city", "state", "pincode", "contact_name", "contact_no")
    list_filter = ("is_active", "state", "city")

    def courier_warehouse_name(self, obj):
        return obj.name
    courier_warehouse_name.short_description = "Courier Warehouse"
    courier_warehouse_name.admin_order_field = "name"

    def changelist_view(self, request, extra_context=None):
        if request.GET.get("admin") == "1":
            return super().changelist_view(request, extra_context=extra_context)
        return HttpResponseRedirect(reverse("operations:courier:warehouses-dashboard"))


