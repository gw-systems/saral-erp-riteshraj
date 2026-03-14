# ERP/integrations/bigin/admin.py
from django.contrib import admin
from .models import BiginRecord, BiginAuthToken

@admin.register(BiginAuthToken)
class BiginAuthTokenAdmin(admin.ModelAdmin):
    list_display = ("__str__", "expires_at")

@admin.register(BiginRecord)
class BiginRecordAdmin(admin.ModelAdmin):
    list_display = ("module", "bigin_id", "modified_time", "synced_at")
    list_filter = ("module",)
    search_fields = ("bigin_id",)
