from django.contrib import admin
from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = [
        'timestamp', 'user_display_name', 'role_snapshot',
        'action_category', 'action_type', 'module',
        'object_repr', 'is_suspicious', 'source',
    ]
    list_filter = [
        'action_category', 'module', 'role_snapshot',
        'source', 'is_suspicious', 'is_backfilled', 'date',
    ]
    search_fields = ['user_display_name', 'description', 'object_repr', 'ip_address']
    readonly_fields = [
        'timestamp', 'date', 'user', 'user_display_name', 'role_snapshot',
        'extra_data', 'ip_address', 'user_agent', 'session_key',
        'action_category', 'action_type', 'module', 'source',
        'object_type', 'object_id', 'object_repr', 'description',
        'is_backfilled', 'backfill_source', 'is_suspicious', 'anonymized',
    ]
    date_hierarchy = 'date'
    ordering = ['-timestamp']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.role == 'admin'
