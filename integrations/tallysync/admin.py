from django.contrib import admin
from integrations.tallysync.models import (
    TallyCompany, TallyGroup, TallyLedger, TallyCostCentre,
    TallyVoucher, VarianceAlert
)


@admin.register(TallyCompany)
class TallyCompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'state', 'is_active', 'last_synced', 'created_at']
    list_filter = ['is_active', 'state']
    search_fields = ['name']


@admin.register(TallyGroup)
class TallyGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'parent', 'last_synced']
    list_filter = ['company']
    search_fields = ['name', 'parent']


@admin.register(TallyLedger)
class TallyLedgerAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'parent', 'gstin', 'last_synced']
    list_filter = ['company', 'parent']
    search_fields = ['name', 'gstin']


@admin.register(TallyCostCentre)
class TallyCostCentreAdmin(admin.ModelAdmin):
    list_display = ['code', 'client_name', 'company', 'is_matched', 'match_confidence', 'last_synced']
    list_filter = ['company', 'is_matched']
    search_fields = ['code', 'name', 'client_name']
    readonly_fields = ['match_confidence', 'match_method']



@admin.register(VarianceAlert)
class VarianceAlertAdmin(admin.ModelAdmin):
    list_display = ['alert_type', 'status', 'severity', 'variance_amount', 'created_at']
    list_filter = ['alert_type', 'status', 'severity', 'created_at']
    search_fields = ['description']