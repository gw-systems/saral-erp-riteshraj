"""
Django admin configuration for Expense Log models.
"""
from django.contrib import admin
from .models import (
    ExpenseLogSettings,
    GoogleSheetsToken,
    ExpenseRecord,
    UserNameMapping
)


@admin.register(ExpenseLogSettings)
class ExpenseLogSettingsAdmin(admin.ModelAdmin):
    list_display = ['id', 'client_id', 'api_version', 'updated_by', 'updated_at']
    readonly_fields = ['updated_at']
    fieldsets = (
        ('OAuth Configuration', {
            'fields': ('client_id', 'encrypted_client_secret', 'redirect_uri', 'api_version')
        }),
        ('Metadata', {
            'fields': ('updated_by', 'updated_at')
        }),
    )


@admin.register(GoogleSheetsToken)
class GoogleSheetsTokenAdmin(admin.ModelAdmin):
    list_display = ['email_account', 'sheet_id', 'sheet_name', 'is_active', 'user', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['email_account', 'sheet_id', 'user__username']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Account Info', {
            'fields': ('user', 'email_account', 'is_active')
        }),
        ('Sheet Configuration', {
            'fields': ('sheet_id', 'sheet_name')
        }),
        ('Token', {
            'fields': ('encrypted_token',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(UserNameMapping)
class UserNameMappingAdmin(admin.ModelAdmin):
    list_display = ['erp_user', 'sheet_name', 'created_by', 'created_at']
    search_fields = ['erp_user__username', 'sheet_name']
    readonly_fields = ['created_at']
    autocomplete_fields = ['erp_user', 'created_by']


@admin.register(ExpenseRecord)
class ExpenseRecordAdmin(admin.ModelAdmin):
    list_display = [
        'unique_expense_number',
        'submitted_by',
        'amount',
        'approval_status',
        'timestamp',
        'token'
    ]
    list_filter = ['approval_status', 'nature_of_expense', 'timestamp', 'token']
    search_fields = [
        'unique_expense_number',
        'submitted_by',
        'email_address',
        'client_name'
    ]
    readonly_fields = ['synced_at', 'updated_at', 'raw_data']
    date_hierarchy = 'timestamp'

    fieldsets = (
        ('Identification', {
            'fields': ('unique_expense_number', 'token')
        }),
        ('Metadata', {
            'fields': ('timestamp', 'submitted_by', 'email_address')
        }),
        ('Client Info', {
            'fields': ('client_name', 'client', 'service_month')
        }),
        ('Expense Details', {
            'fields': ('nature_of_expense', 'amount', 'payment_method', 'expenses_borne_by', 'remark')
        }),
        ('Approval', {
            'fields': ('approval_status',)
        }),
        ('Raw Data', {
            'fields': ('raw_data',),
            'classes': ('collapse',)
        }),
        ('Sync Tracking', {
            'fields': ('synced_at', 'updated_at')
        }),
    )
