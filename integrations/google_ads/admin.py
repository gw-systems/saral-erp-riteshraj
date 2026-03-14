"""
Google Ads Admin Configuration
"""

from django.contrib import admin
from .models import (
    GoogleAdsToken,
    Campaign,
    CampaignPerformance,
    DevicePerformance,
    SearchTerm,
)


@admin.register(GoogleAdsToken)
class GoogleAdsTokenAdmin(admin.ModelAdmin):
    list_display = ['account_name', 'customer_id', 'user', 'is_active', 'last_synced_at', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['account_name', 'customer_id', 'user__username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['campaign_name', 'campaign_id', 'campaign_status', 'token', 'budget_amount', 'created_at']
    list_filter = ['campaign_status', 'token', 'created_at']
    search_fields = ['campaign_name', 'campaign_id']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(CampaignPerformance)
class CampaignPerformanceAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'date', 'impressions', 'clicks', 'cost', 'conversions', 'ctr']
    list_filter = ['date', 'campaign__token']
    search_fields = ['campaign__campaign_name']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'date'


@admin.register(DevicePerformance)
class DevicePerformanceAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'date', 'device', 'impressions', 'clicks', 'cost', 'conversions']
    list_filter = ['date', 'device', 'campaign__token']
    search_fields = ['campaign__campaign_name']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'date'


@admin.register(SearchTerm)
class SearchTermAdmin(admin.ModelAdmin):
    list_display = ['search_term', 'campaign', 'year', 'month', 'impressions', 'clicks', 'cost', 'conversions']
    list_filter = ['year', 'month', 'campaign__token']
    search_fields = ['search_term', 'campaign__campaign_name']
    readonly_fields = ['created_at', 'updated_at']


