"""
Gmail Leads Admin Configuration
"""

from django.contrib import admin
from .models import GmailLeadsToken, LeadEmail, LastProcessedTime, DuplicateCheckCache


@admin.register(GmailLeadsToken)
class GmailLeadsTokenAdmin(admin.ModelAdmin):
    list_display = ('email_account', 'user', 'is_active', 'last_sync_at', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('email_account', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LeadEmail)
class LeadEmailAdmin(admin.ModelAdmin):
    list_display = ('lead_type', 'form_email', 'form_name', 'utm_campaign', 'date_received', 'datetime_received')
    list_filter = ('lead_type', 'date_received', 'utm_campaign', 'utm_medium')
    search_fields = ('form_name', 'form_email', 'form_company_name', 'message_preview')
    date_hierarchy = 'date_received'
    readonly_fields = ('processed_timestamp', 'message_id')


@admin.register(LastProcessedTime)
class LastProcessedTimeAdmin(admin.ModelAdmin):
    list_display = ('account_link', 'lead_type', 'last_processed_time')
    list_filter = ('lead_type',)



@admin.register(DuplicateCheckCache)
class DuplicateCheckCacheAdmin(admin.ModelAdmin):
    list_display = ('account_link', 'lead_type', 'cache_key', 'message_id', 'created_at')
    list_filter = ('lead_type', 'created_at')
    search_fields = ('cache_key', 'message_id')
    date_hierarchy = 'created_at'
