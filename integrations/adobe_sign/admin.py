"""
Adobe Sign Admin Interface
"""

from django.contrib import admin
from .models import (
    DocumentTemplate,
    Document,
    AdobeAgreement,
    Signer,
    AgreementEvent,
    AdobeSignSettings
)


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'template_type', 'is_active', 'created_at']
    list_filter = ['template_type', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('Template Information', {
            'fields': ('name', 'template_type', 'description', 'is_active')
        }),
        ('Template File', {
            'fields': ('template_file', 'field_definitions', 'default_signer_order')
        }),
        ('Metadata', {
            'fields': ('id', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'file_type', 'file_size', 'uploaded_by', 'created_at']
    list_filter = ['file_type', 'created_at']
    search_fields = ['file_name']
    readonly_fields = ['id', 'file_name', 'file_type', 'file_size', 'file_hash', 'created_at']
    fieldsets = (
        ('Document Information', {
            'fields': ('file', 'file_name', 'file_type', 'file_size', 'file_hash')
        }),
        ('Template Link', {
            'fields': ('template',)
        }),
        ('Metadata', {
            'fields': ('id', 'uploaded_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )


class SignerInline(admin.TabularInline):
    model = Signer
    extra = 0
    readonly_fields = ['id', 'status', 'signed_at', 'created_at']
    fields = ['name', 'email', 'role', 'role_label', 'order', 'status']


class AgreementEventInline(admin.TabularInline):
    model = AgreementEvent
    extra = 0
    readonly_fields = ['event_type', 'event_date', 'participant_email', 'description']
    fields = ['event_type', 'event_date', 'participant_email', 'description']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AdobeAgreement)
class AdobeAgreementAdmin(admin.ModelAdmin):
    list_display = [
        'agreement_name',
        'client_email',
        'approval_status',
        'adobe_status',
        'flow_type',
        'created_at'
    ]
    list_filter = [
        'approval_status',
        'adobe_status',
        'flow_type',
        'created_at',
        'approved_at'
    ]
    search_fields = ['agreement_name', 'client_name', 'client_email', 'adobe_agreement_id']
    readonly_fields = [
        'id',
        'adobe_agreement_id',
        'adobe_status',
        'created_at',
        'updated_at',
        'submitted_at',
        'approved_at',
        'sent_at',
        'completed_at',
        'last_synced_at'
    ]
    inlines = [SignerInline, AgreementEventInline]

    fieldsets = (
        ('Agreement Details', {
            'fields': (
                'agreement_name',
                'agreement_message',
                'document',
                'flow_type'
            )
        }),
        ('Client Information', {
            'fields': ('client_name', 'client_email', 'cc_emails')
        }),
        ('Status', {
            'fields': ('approval_status', 'adobe_status', 'adobe_agreement_id')
        }),
        ('Rejection Details', {
            'fields': ('rejection_reason', 'rejection_notes'),
            'classes': ('collapse',)
        }),
        ('Configuration', {
            'fields': (
                'days_until_signing_deadline',
                'expiration_date',
                'reminder_frequency'
            ),
            'classes': ('collapse',)
        }),
        ('Workflow Tracking', {
            'fields': (
                'prepared_by',
                'approved_by',
                'submitted_at',
                'approved_at',
                'sent_at',
                'completed_at'
            ),
            'classes': ('collapse',)
        }),
        ('Signed Document', {
            'fields': ('signed_document_url', 'signed_document_file'),
            'classes': ('collapse',)
        }),
        ('System', {
            'fields': (
                'id',
                'created_at',
                'updated_at',
                'last_synced_at',
                'sync_error'
            ),
            'classes': ('collapse',)
        }),
    )


@admin.register(Signer)
class SignerAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'role', 'role_label', 'order', 'status', 'agreement']
    list_filter = ['role', 'status']
    search_fields = ['name', 'email', 'agreement__agreement_name']
    readonly_fields = ['id', 'status', 'signed_at', 'created_at', 'updated_at']


@admin.register(AgreementEvent)
class AgreementEventAdmin(admin.ModelAdmin):
    list_display = ['agreement', 'event_type', 'event_date', 'participant_email']
    list_filter = ['event_type', 'event_date']
    search_fields = ['agreement__agreement_name', 'participant_email', 'description']
    readonly_fields = [
        'id',
        'agreement',
        'event_type',
        'event_date',
        'participant_email',
        'participant_role',
        'acting_user_email',
        'acting_user_ip',
        'description',
        'comment',
        'created_at'
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AdobeSignSettings)
class AdobeSignSettingsAdmin(admin.ModelAdmin):
    list_display = ['director_name', 'director_email', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Director Information', {
            'fields': ('director_name', 'director_email', 'director_title')
        }),
        ('API Configuration', {
            'fields': ('api_base_url',),
            'description': 'Integration Key is configured in environment variables'
        }),
        ('Default Settings', {
            'fields': (
                'default_expiration_days',
                'default_reminder_frequency'
            )
        }),
        ('Notifications', {
            'fields': ('notify_on_signature', 'notify_on_completion')
        }),
        ('System', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        # Only allow one settings instance
        return not AdobeSignSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Never allow deletion of settings
        return False
