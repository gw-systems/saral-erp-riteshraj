"""
Gmail Leads Models
Stores lead emails from CONTACT_US and SAAS_INVENTORY forms
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class GmailLeadsToken(models.Model):
    """
    OAuth2 token for Gmail Lead Fetcher account
    Separate from main gmail app - uses different Gmail account
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gmail_leads_tokens')
    email_account = models.EmailField(unique=True)
    encrypted_token_data = models.TextField(help_text="Encrypted OAuth2 token JSON")
    excluded_emails = models.TextField(
        blank=True,
        help_text="Comma-separated list of email addresses to exclude from sync (e.g., spam@example.com, test@domain.com)"
    )

    is_active = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gmail_leads_tokens'
        verbose_name = 'Gmail Leads Token'
        verbose_name_plural = 'Gmail Leads Tokens'

    def __str__(self):
        return f"{self.email_account} ({'Active' if self.is_active else 'Inactive'})"

    def can_be_accessed_by(self, user):
        """Check if user can access this token"""
        if user.role in ['admin', 'director', 'digital_marketing']:
            return True
        return self.user == user

    def get_excluded_emails_list(self):
        """Parse excluded_emails field into list of lowercase emails"""
        if not self.excluded_emails:
            return []
        return [email.strip().lower() for email in self.excluded_emails.split(',') if email.strip()]

    def is_email_excluded(self, email):
        """Check if an email address should be excluded from sync"""
        if not email:
            return False
        excluded_list = self.get_excluded_emails_list()
        return email.lower().strip() in excluded_list


class LeadEmail(models.Model):
    """
    Lead emails from Contact Us and SAAS Inventory forms
    Maps to Google Sheets structure
    """
    LEAD_TYPE_CHOICES = [
        ('CONTACT_US', 'Contact Us'),
        ('SAAS_INVENTORY', 'SAAS Inventory'),
    ]

    # Lead Type & Timing
    lead_type = models.CharField(max_length=20, choices=LEAD_TYPE_CHOICES, db_index=True)
    month_year = models.CharField(max_length=20, help_text="e.g. 'February 2026'")

    # Email Headers
    from_name = models.CharField(max_length=255, blank=True)
    from_email = models.EmailField()
    reply_to_name = models.CharField(max_length=255, blank=True)
    reply_to_email = models.EmailField(blank=True)
    to_addresses = models.TextField(help_text="Comma-separated email addresses")

    # UTM Parameters (Campaign Tracking)
    utm_term = models.CharField(max_length=255, blank=True)
    utm_campaign = models.CharField(max_length=255, blank=True, db_index=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_content = models.CharField(max_length=255, blank=True)
    gclid = models.CharField(max_length=255, blank=True, help_text="Google Click Identifier")

    # Email Metadata
    subject = models.TextField()
    date_received = models.DateField(db_index=True)
    time_received = models.TimeField()
    datetime_received = models.DateTimeField(db_index=True, help_text="Combined date+time for sorting")

    # Form Fields (extracted from email body)
    form_name = models.CharField(max_length=255, blank=True)
    form_email = models.EmailField(blank=True, db_index=True)
    form_phone = models.CharField(max_length=50, blank=True)
    form_address = models.TextField(blank=True)
    form_company_name = models.CharField(max_length=255, blank=True)

    # Message Content
    message_preview = models.TextField(blank=True, help_text="Extracted form data or message body")
    full_message_body = models.TextField(blank=True, help_text="Complete email message body (HTML/plain text)")

    # System Fields
    processed_timestamp = models.DateTimeField(auto_now_add=True)
    message_id = models.CharField(max_length=50, unique=True, db_index=True, help_text="Gmail message ID")

    # Foreign Keys
    account_link = models.ForeignKey(
        GmailLeadsToken,
        on_delete=models.CASCADE,
        related_name='lead_emails'
    )

    class Meta:
        db_table = 'gmail_lead_emails'
        verbose_name = 'Lead Email'
        verbose_name_plural = 'Lead Emails'
        ordering = ['-datetime_received']
        indexes = [
            models.Index(fields=['lead_type', '-datetime_received']),
            models.Index(fields=['utm_campaign', '-datetime_received']),
            models.Index(fields=['form_email', '-datetime_received']),
        ]

    def __str__(self):
        return f"{self.lead_type} - {self.form_email or self.reply_to_email} ({self.date_received})"

    @classmethod
    def get_leads_for_user(cls, user):
        """Get leads accessible to user (admin/director/digital_marketing sees all, others see their account's leads)"""
        if user.role in ['admin', 'director', 'digital_marketing']:
            return cls.objects.all()

        # Regular users see leads from accounts they own
        accessible_tokens = GmailLeadsToken.objects.filter(user=user, is_active=True)
        return cls.objects.filter(account_link__in=accessible_tokens)


class LastProcessedTime(models.Model):
    """
    Tracks last processed timestamp for each lead type
    Used for incremental syncing
    """
    account_link = models.ForeignKey(GmailLeadsToken, on_delete=models.CASCADE, related_name='lpt_records')
    lead_type = models.CharField(max_length=20, choices=LeadEmail.LEAD_TYPE_CHOICES)
    last_processed_time = models.DateTimeField()

    class Meta:
        db_table = 'gmail_leads_lpt'
        verbose_name = 'Last Processed Time'
        verbose_name_plural = 'Last Processed Times'
        unique_together = [['account_link', 'lead_type']]

    def __str__(self):
        return f"{self.account_link.email_account} - {self.lead_type}: {self.last_processed_time}"



class DuplicateCheckCache(models.Model):
    """
    Tracks processed emails to prevent duplicates
    Cache key format: email|date|name
    """
    account_link = models.ForeignKey(GmailLeadsToken, on_delete=models.CASCADE, related_name='duplicate_cache')
    lead_type = models.CharField(max_length=20, choices=LeadEmail.LEAD_TYPE_CHOICES)
    cache_key = models.CharField(max_length=500, db_index=True, help_text="email|date|name")
    message_id = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gmail_leads_duplicate_cache'
        verbose_name = 'Duplicate Check Cache'
        verbose_name_plural = 'Duplicate Check Cache'
        unique_together = [['account_link', 'lead_type', 'cache_key']]
        indexes = [
            models.Index(fields=['cache_key']),
            models.Index(fields=['message_id']),
        ]

    def __str__(self):
        return f"{self.lead_type}: {self.cache_key}"


class GmailLeadsSettings(models.Model):
    """
    Singleton model for Gmail Leads OAuth configuration.
    Values stored here override environment variables.
    Only one record exists (pk=1 enforced).
    """
    client_id = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Google OAuth 2.0 Client ID (overrides GMAIL_LEADS_CLIENT_ID env var)"
    )
    client_secret = models.CharField(
        max_length=500, blank=True, default='',
        help_text="Google OAuth 2.0 Client Secret — stored encrypted"
    )
    redirect_uri = models.URLField(
        blank=True, default='',
        help_text="OAuth redirect URI (overrides GMAIL_LEADS_REDIRECT_URI env var)"
    )

    # Audit
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gmail_leads_settings_updates'
    )

    class Meta:
        verbose_name = "Gmail Leads Settings"
        verbose_name_plural = "Gmail Leads Settings"

    def __str__(self):
        return "Gmail Leads OAuth Settings"

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

    def _get_fernet(self):
        from cryptography.fernet import Fernet
        from django.conf import settings as django_settings
        import base64
        if hasattr(django_settings, 'GMAIL_ENCRYPTION_KEY'):
            key = django_settings.GMAIL_ENCRYPTION_KEY.encode()
        else:
            key = base64.urlsafe_b64encode(
                django_settings.SECRET_KEY[:32].encode().ljust(32)[:32]
            )
        return Fernet(key)

    def get_decrypted_client_secret(self):
        """Return decrypted client secret"""
        if not self.client_secret:
            return ''
        try:
            return self._get_fernet().decrypt(self.client_secret.encode()).decode()
        except Exception:
            return self.client_secret

    def set_client_secret(self, value):
        """Encrypt and store client secret"""
        if not value:
            return
        try:
            self.client_secret = self._get_fernet().encrypt(value.encode()).decode()
        except Exception:
            self.client_secret = value

    def get_credential_source(self):
        """Return 'database', 'environment', or 'not_configured' for display"""
        from django.conf import settings as django_settings
        if self.client_id:
            return 'database'
        elif getattr(django_settings, 'GMAIL_LEADS_CLIENT_ID', ''):
            return 'environment'
        return 'not_configured'
