from django.contrib import admin

from .models import ApolloCampaign, ApolloMessage, ApolloSyncState


@admin.register(ApolloSyncState)
class ApolloSyncStateAdmin(admin.ModelAdmin):
    list_display = [
        'sync_key', 'c_year', 'c_month', 'c_camp_idx', 'c_page',
        'is_complete', 'last_checkpoint_at', 'last_api_calls',
    ]
    readonly_fields = ['created_at', 'updated_at', 'last_checkpoint_at', 'last_run_started_at', 'last_run_completed_at']


@admin.register(ApolloCampaign)
class ApolloCampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'apollo_id', 'created_at_remote', 'last_synced_at']
    list_filter = ['created_at_remote', 'last_synced_at']
    search_fields = ['name', 'apollo_id']
    readonly_fields = ['raw_data', 'last_synced_at', 'created_at', 'updated_at']


@admin.register(ApolloMessage)
class ApolloMessageAdmin(admin.ModelAdmin):
    list_display = [
        'recipient_email', 'campaign', 'subject', 'num_opens',
        'num_clicks', 'replied', 'lead_category', 'sent_at',
    ]
    list_filter = ['campaign', 'replied', 'lead_category', 'status', 'sent_at']
    search_fields = ['recipient_email', 'subject', 'apollo_id', 'first_name', 'last_name']
    readonly_fields = ['raw_message', 'raw_activity', 'last_synced_at', 'created_at', 'updated_at']
    autocomplete_fields = ['campaign']
    date_hierarchy = 'sent_at'
