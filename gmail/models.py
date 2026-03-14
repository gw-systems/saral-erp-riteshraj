"""
Gmail Integration Models
Enterprise-grade email management with thread-centric architecture
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from cryptography.fernet import Fernet
from django.conf import settings as django_settings
import base64
import json

User = get_user_model()


def _get_gmail_fernet():
    """Get Fernet instance using shared encryption key"""
    if hasattr(django_settings, 'GMAIL_ENCRYPTION_KEY'):
        key = django_settings.GMAIL_ENCRYPTION_KEY.encode()
    else:
        key = base64.urlsafe_b64encode(
            django_settings.SECRET_KEY[:32].encode().ljust(32)[:32]
        )
    return Fernet(key)


class GmailSettings(models.Model):
    """
    Singleton model for Gmail OAuth configuration.
    Values stored here override environment variables.
    Only one record exists (pk=1 enforced).
    """
    client_id = models.CharField(
        max_length=500, blank=True, default='',
        help_text="Google OAuth Client ID"
    )
    encrypted_client_secret = models.TextField(
        blank=True, default='',
        help_text="Google OAuth Client Secret — stored encrypted"
    )
    redirect_uri = models.URLField(
        blank=True, default='',
        help_text="OAuth redirect URI (e.g., https://yourdomain.com/gmail/oauth/callback/)"
    )

    # Audit
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gmail_settings_updates'
    )

    class Meta:
        db_table = 'gmail_settings'
        verbose_name = "Gmail Settings"
        verbose_name_plural = "Gmail Settings"

    def __str__(self):
        return "Gmail OAuth Settings"

    def save(self, *args, **kwargs):
        self.pk = 1  # Singleton
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # Prevent deletion

    @classmethod
    def load(cls):
        """Get or create singleton instance"""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def get_decrypted_client_secret(self):
        """Return decrypted client secret"""
        if not self.encrypted_client_secret:
            return ''
        try:
            return _get_gmail_fernet().decrypt(self.encrypted_client_secret.encode()).decode()
        except Exception:
            return self.encrypted_client_secret

    def set_client_secret(self, value):
        """Encrypt and store client secret"""
        if not value:
            return
        try:
            self.encrypted_client_secret = _get_gmail_fernet().encrypt(value.encode()).decode()
        except Exception:
            self.encrypted_client_secret = value

    def get_credential_source(self):
        """Return 'database', 'environment', or 'not_configured' for display"""
        if self.client_id:
            return 'database'
        elif getattr(django_settings, 'GOOGLE_CLIENT_ID', ''):
            return 'environment'
        return 'not_configured'


class GmailToken(models.Model):
    """
    Stores OAuth2 tokens for Gmail accounts
    Multi-account support: each user can connect multiple Gmail accounts
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='gmail_tokens'
    )
    email_account = models.EmailField()
    encrypted_token_data = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    history_id = models.CharField(max_length=50, blank=True)  # For incremental sync

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gmail_tokens'
        unique_together = [['user', 'email_account']]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.email_account}"

    def can_be_accessed_by(self, requesting_user):
        """Check if requesting user has access to this token"""
        # Admin, Director, Operation Controller can access all
        if requesting_user.role in ['admin', 'director', 'operation_controller']:
            return True
        # Regular users can only access their own
        return self.user == requesting_user

    def get_decrypted_token(self):
        """Return decrypted token data as dict"""
        if not self.encrypted_token_data:
            return {}
        try:
            decrypted = _get_gmail_fernet().decrypt(self.encrypted_token_data.encode()).decode()
            return json.loads(decrypted)
        except Exception:
            return {}

    def set_token(self, token_data):
        """Encrypt and store token data"""
        try:
            encrypted = _get_gmail_fernet().encrypt(json.dumps(token_data).encode()).decode()
            self.encrypted_token_data = encrypted
        except Exception:
            pass


class Contact(models.Model):
    """Email contact with profile enrichment"""
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)

    # Enrichment
    avatar_url = models.URLField(blank=True)
    organization = models.CharField(max_length=255, blank=True)

    # Analytics
    email_count = models.IntegerField(default=0)
    last_email_date = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gmail_contacts'
        ordering = ['email']

    def __str__(self):
        return f"{self.name} <{self.email}>" if self.name else self.email

    def get_initial(self):
        """Get first letter for avatar"""
        if self.name:
            return self.name[0].upper()
        return self.email[0].upper()


class Thread(models.Model):
    """
    Email conversation thread.
    Central entity for WhatsApp-style grouping.
    """
    thread_id = models.CharField(max_length=50, unique=True, db_index=True)
    account_link = models.ForeignKey(
        GmailToken,
        on_delete=models.CASCADE,
        related_name='threads'
    )

    # Thread metadata
    subject = models.TextField()
    participants = models.ManyToManyField(Contact, related_name='threads')

    # Status
    is_starred = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    is_muted = models.BooleanField(default=False)
    has_unread = models.BooleanField(default=False, db_index=True)

    # Timestamps
    last_message_date = models.DateTimeField(db_index=True)
    first_message_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Cached fields for performance
    message_count = models.IntegerField(default=0)
    last_sender_name = models.CharField(max_length=255, blank=True)
    snippet = models.TextField(blank=True)

    class Meta:
        db_table = 'gmail_threads'
        ordering = ['-last_message_date']
        indexes = [
            models.Index(fields=['account_link', '-last_message_date']),
            models.Index(fields=['account_link', 'has_unread']),
            models.Index(fields=['is_starred', '-last_message_date']),
        ]

    def __str__(self):
        return f"{self.subject[:50]} - {self.last_sender_name}"

    @staticmethod
    def get_threads_for_user(user):
        """Get threads accessible by user based on permissions"""
        if user.role in ['admin', 'director', 'operation_controller']:
            return Thread.objects.all()
        return Thread.objects.filter(account_link__user=user)


class Message(models.Model):
    """
    Individual email message within a thread.
    """
    message_id = models.CharField(max_length=50, unique=True, db_index=True)
    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    account_link = models.ForeignKey(
        GmailToken,
        on_delete=models.CASCADE,
        related_name='messages'
    )

    # Headers
    subject = models.TextField()
    from_contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_messages'
    )
    to_contacts = models.ManyToManyField(
        Contact,
        related_name='received_messages'
    )
    cc_contacts = models.ManyToManyField(
        Contact,
        related_name='cc_messages',
        blank=True
    )
    bcc_contacts = models.ManyToManyField(
        Contact,
        related_name='bcc_messages',
        blank=True
    )

    # Content
    body_text = models.TextField(blank=True)
    body_html = models.TextField(blank=True)
    snippet = models.TextField(blank=True)

    # Metadata
    date = models.DateTimeField(db_index=True)
    labels = models.JSONField(default=list)
    is_read = models.BooleanField(default=False, db_index=True)
    is_starred = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)

    # Attachments
    has_attachments = models.BooleanField(default=False)
    attachments_meta = models.JSONField(default=list)  # [{filename, size, mime_type, attachment_id}]

    # Gmail-specific
    history_id = models.CharField(max_length=50, blank=True)
    internal_date = models.BigIntegerField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gmail_messages'
        ordering = ['date']
        indexes = [
            models.Index(fields=['thread', 'date']),
            models.Index(fields=['account_link', '-date']),
            models.Index(fields=['from_contact', '-date']),
            models.Index(fields=['is_read']),
        ]

    def __str__(self):
        return f"{self.subject[:50]} - {self.date}"

    @staticmethod
    def get_messages_for_user(user):
        """Get messages accessible by user"""
        if user.role in ['admin', 'director', 'operation_controller']:
            return Message.objects.all()
        return Message.objects.filter(account_link__user=user)


class Draft(models.Model):
    """
    Email draft with auto-save support.
    """
    account_link = models.ForeignKey(
        GmailToken,
        on_delete=models.CASCADE,
        related_name='drafts'
    )
    thread = models.ForeignKey(
        Thread,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='drafts'
    )

    # Draft content
    to_emails = models.TextField()  # Comma-separated
    cc_emails = models.TextField(blank=True)
    bcc_emails = models.TextField(blank=True)
    subject = models.TextField()
    body_html = models.TextField()
    body_text = models.TextField(blank=True)

    # Attachments (pending upload)
    pending_attachments = models.JSONField(default=list)

    # Gmail draft ID (if synced)
    gmail_draft_id = models.CharField(max_length=50, blank=True)

    # Auto-save tracking
    last_saved_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gmail_drafts'
        ordering = ['-last_saved_at']

    def __str__(self):
        return f"Draft: {self.subject[:50]}"


class Attachment(models.Model):
    """
    Email attachment storage and metadata.
    """
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='stored_attachments'
    )

    # Gmail metadata
    attachment_id = models.CharField(max_length=255)
    filename = models.CharField(max_length=500)
    mime_type = models.CharField(max_length=100)
    size = models.BigIntegerField()  # bytes

    # Local storage
    file = models.FileField(
        upload_to='gmail_attachments/%Y/%m/%d/',
        blank=True,
        null=True
    )
    is_downloaded = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gmail_attachments'
        unique_together = [['message', 'attachment_id']]

    def __str__(self):
        return f"{self.filename} ({self.size} bytes)"


class Label(models.Model):
    """
    Gmail labels (system + user-created).
    """
    account_link = models.ForeignKey(
        GmailToken,
        on_delete=models.CASCADE,
        related_name='labels'
    )
    label_id = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    type = models.CharField(
        max_length=20,
        choices=[('system', 'System'), ('user', 'User')]
    )

    # Display
    color = models.CharField(max_length=20, blank=True)
    is_visible = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gmail_labels'
        unique_together = [['account_link', 'label_id']]

    def __str__(self):
        return f"{self.name} ({self.type})"


class SyncStatus(models.Model):
    """Track sync status for each Gmail account"""
    gmail_token = models.ForeignKey(
        GmailToken,
        on_delete=models.CASCADE,
        related_name='sync_statuses',
        null=True,  # Allow null for migration compatibility
        blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Success'),
            ('error', 'Error'),
            ('in_progress', 'In Progress'),
        ],
        default='success'
    )
    last_sync_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    emails_synced = models.IntegerField(default=0)
    threads_synced = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gmail_sync_status'
        verbose_name_plural = 'Sync statuses'

    def __str__(self):
        return f"{self.gmail_token.email_account} - {self.status}"
