"""
Django Admin configuration for Gmail app
"""

from django.contrib import admin
from gmail.models import (
    GmailSettings, GmailToken, Thread, Message, Contact,
    Draft, Attachment, Label, SyncStatus
)


@admin.register(GmailSettings)
class GmailSettingsAdmin(admin.ModelAdmin):
    list_display = ['client_id', 'redirect_uri', 'updated_at', 'updated_by']
    readonly_fields = ['updated_at']

    def has_add_permission(self, request):
        # Only allow one instance (singleton)
        return not GmailSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion
        return False


@admin.register(GmailToken)
class GmailTokenAdmin(admin.ModelAdmin):
    list_display = ['email_account', 'user', 'is_active', 'last_sync_at', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['email_account', 'user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at', 'encrypted_token_data', 'history_id']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Admin can see all, others see only their own
        if request.user.role in ['admin', 'director', 'operation_controller']:
            return qs
        return qs.filter(user=request.user)


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ['subject_preview', 'account_email', 'last_sender_name', 'message_count', 'has_unread', 'is_starred', 'last_message_date']
    list_filter = ['has_unread', 'is_starred', 'is_archived', 'account_link__email_account']
    search_fields = ['subject', 'thread_id', 'last_sender_name']
    readonly_fields = ['thread_id', 'created_at', 'updated_at', 'message_count']
    date_hierarchy = 'last_message_date'

    def subject_preview(self, obj):
        return obj.subject[:50] + '...' if len(obj.subject) > 50 else obj.subject
    subject_preview.short_description = 'Subject'

    def account_email(self, obj):
        return obj.account_link.email_account
    account_email.short_description = 'Account'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['admin', 'director', 'operation_controller']:
            return qs
        return qs.filter(account_link__user=request.user)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['subject_preview', 'from_email', 'date', 'is_read', 'is_starred', 'has_attachments']
    list_filter = ['is_read', 'is_starred', 'has_attachments', 'date']
    search_fields = ['subject', 'body_text', 'message_id']
    readonly_fields = ['message_id', 'thread', 'created_at', 'updated_at']
    date_hierarchy = 'date'

    def subject_preview(self, obj):
        return obj.subject[:50] + '...' if len(obj.subject) > 50 else obj.subject
    subject_preview.short_description = 'Subject'

    def from_email(self, obj):
        return obj.from_contact.email if obj.from_contact else 'Unknown'
    from_email.short_description = 'From'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['admin', 'director', 'operation_controller']:
            return qs
        return qs.filter(account_link__user=request.user)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'email_count', 'last_email_date', 'created_at']
    search_fields = ['name', 'email']
    readonly_fields = ['email_count', 'last_email_date', 'created_at', 'updated_at']


@admin.register(Draft)
class DraftAdmin(admin.ModelAdmin):
    list_display = ['subject_preview', 'to_emails_preview', 'account_email', 'last_saved_at']
    search_fields = ['subject', 'to_emails']
    readonly_fields = ['last_saved_at', 'created_at']
    date_hierarchy = 'last_saved_at'

    def subject_preview(self, obj):
        return obj.subject[:50] + '...' if len(obj.subject) > 50 else obj.subject
    subject_preview.short_description = 'Subject'

    def to_emails_preview(self, obj):
        return obj.to_emails[:50] + '...' if len(obj.to_emails) > 50 else obj.to_emails
    to_emails_preview.short_description = 'To'

    def account_email(self, obj):
        return obj.account_link.email_account
    account_email.short_description = 'Account'


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ['filename', 'mime_type', 'size_display', 'is_downloaded', 'message_subject']
    list_filter = ['is_downloaded', 'mime_type']
    search_fields = ['filename']
    readonly_fields = ['created_at']

    def size_display(self, obj):
        # Convert bytes to human readable
        size = obj.size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    size_display.short_description = 'Size'

    def message_subject(self, obj):
        return obj.message.subject[:30] + '...' if len(obj.message.subject) > 30 else obj.message.subject
    message_subject.short_description = 'Message'


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'account_email', 'is_visible']
    list_filter = ['type', 'is_visible']
    search_fields = ['name', 'label_id']

    def account_email(self, obj):
        return obj.account_link.email_account
    account_email.short_description = 'Account'


@admin.register(SyncStatus)
class SyncStatusAdmin(admin.ModelAdmin):
    list_display = ['account_email', 'status', 'emails_synced', 'threads_synced', 'last_sync_at']
    list_filter = ['status', 'last_sync_at']
    readonly_fields = ['created_at', 'updated_at']

    def account_email(self, obj):
        return obj.gmail_token.email_account
    account_email.short_description = 'Account'
