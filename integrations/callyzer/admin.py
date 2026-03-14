"""
Callyzer Django Admin Configuration
"""

from django.contrib import admin
from .models import (
    CallyzerToken,
    CallSummary,
    EmployeeSummary,
    CallAnalysis,
    NeverAttendedCall,
    NotPickedUpCall,
    UniqueClient,
    HourlyAnalytic,
    DailyAnalytic,
    CallHistory,
)


@admin.register(CallyzerToken)
class CallyzerTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'account_name', 'is_active', 'last_sync_at', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('account_name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Account Info', {
            'fields': ('user', 'account_name', 'encrypted_api_key', 'is_active')
        }),
        ('Sync Info', {
            'fields': ('last_sync_at',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CallSummary)
class CallSummaryAdmin(admin.ModelAdmin):
    list_display = ('id', 'token', 'total_calls', 'total_duration_seconds', 'synced_at')
    list_filter = ('synced_at',)
    search_fields = ('token__account_name',)
    readonly_fields = ('synced_at',)


@admin.register(EmployeeSummary)
class EmployeeSummaryAdmin(admin.ModelAdmin):
    list_display = ('id', 'token', 'emp_name', 'total_calls', 'synced_at')
    list_filter = ('synced_at',)
    search_fields = ('emp_name', 'token__account_name')
    readonly_fields = ('synced_at',)


@admin.register(CallAnalysis)
class CallAnalysisAdmin(admin.ModelAdmin):
    list_display = ('id', 'token', 'answered_calls', 'missed_calls', 'synced_at')
    list_filter = ('synced_at',)
    search_fields = ('token__account_name',)
    readonly_fields = ('synced_at',)


@admin.register(NeverAttendedCall)
class NeverAttendedCallAdmin(admin.ModelAdmin):
    list_display = ('id', 'token', 'emp_name', 'client_name', 'client_number', 'call_date', 'call_time')
    list_filter = ('call_date', 'synced_at')
    search_fields = ('emp_name', 'client_name', 'client_number')
    readonly_fields = ('synced_at',)
    date_hierarchy = 'call_date'


@admin.register(NotPickedUpCall)
class NotPickedUpCallAdmin(admin.ModelAdmin):
    list_display = ('id', 'token', 'emp_name', 'client_name', 'client_number', 'call_date', 'call_time')
    list_filter = ('call_date', 'synced_at')
    search_fields = ('emp_name', 'client_name', 'client_number')
    readonly_fields = ('synced_at',)
    date_hierarchy = 'call_date'


@admin.register(UniqueClient)
class UniqueClientAdmin(admin.ModelAdmin):
    list_display = ('id', 'token', 'client_name', 'client_number', 'total_calls', 'synced_at')
    list_filter = ('synced_at',)
    search_fields = ('client_name', 'client_number')
    readonly_fields = ('synced_at',)


@admin.register(HourlyAnalytic)
class HourlyAnalyticAdmin(admin.ModelAdmin):
    list_display = ('id', 'token', 'hour', 'total_calls', 'synced_at')
    list_filter = ('hour', 'synced_at')
    readonly_fields = ('synced_at',)


@admin.register(DailyAnalytic)
class DailyAnalyticAdmin(admin.ModelAdmin):
    list_display = ('id', 'token', 'date', 'total_calls', 'synced_at')
    list_filter = ('date', 'synced_at')
    readonly_fields = ('synced_at',)
    date_hierarchy = 'date'


@admin.register(CallHistory)
class CallHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'token', 'emp_name', 'client_number', 'call_type', 'call_date', 'call_time', 'duration_seconds')
    list_filter = ('call_type', 'call_direction', 'call_date', 'synced_at')
    search_fields = ('emp_name', 'client_number', 'client_name')
    readonly_fields = ('synced_at',)
    date_hierarchy = 'call_date'


