from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()


def _get_bigin_fernet():
    """Get Fernet instance using shared encryption key"""
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


class BiginAuthToken(models.Model):
    """
    Stores Zoho Bigin OAuth tokens for authentication.
    Only one record is typically needed.
    """
    # Legacy plain text fields — kept for data migration compatibility
    access_token = models.TextField(blank=True, default='')
    refresh_token = models.TextField(blank=True, default='')

    # Encrypted fields (new — use these going forward)
    encrypted_access_token = models.TextField(blank=True, default='')
    encrypted_refresh_token = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    expires_at = models.DateTimeField(default=timezone.now)

    def is_expired(self):
        """Returns True if the token is near expiry."""
        return timezone.now() >= self.expires_at - timedelta(minutes=5)

    def get_decrypted_access_token(self):
        """Return decrypted access token"""
        if self.encrypted_access_token:
            try:
                return _get_bigin_fernet().decrypt(self.encrypted_access_token.encode()).decode()
            except Exception:
                pass
        return self.access_token  # Fallback to legacy plain text

    def get_decrypted_refresh_token(self):
        """Return decrypted refresh token"""
        if self.encrypted_refresh_token:
            try:
                return _get_bigin_fernet().decrypt(self.encrypted_refresh_token.encode()).decode()
            except Exception:
                pass
        return self.refresh_token  # Fallback to legacy plain text

    def set_tokens(self, access_token, refresh_token):
        """Encrypt and store both tokens"""
        f = _get_bigin_fernet()
        self.encrypted_access_token = f.encrypt(access_token.encode()).decode()
        self.encrypted_refresh_token = f.encrypt(refresh_token.encode()).decode()
        # Clear legacy plain text
        self.access_token = ''
        self.refresh_token = ''

    def __str__(self):
        return f"BiginToken (expires {self.expires_at:%Y-%m-%d %H:%M})"


class BiginRecord(models.Model):
    """
    Stores all data fetched from Zoho Bigin modules (Contacts, Deals, etc.)
    Raw JSON + extracted fields for fast filtering.
    """
    bigin_id = models.CharField(max_length=64, db_index=True)
    module = models.CharField(max_length=50, db_index=True)
    raw = models.JSONField()  # Complete JSON from Zoho Bigin
    
    # Timestamps
    created_time = models.DateTimeField(null=True, blank=True, db_index=True)
    modified_time = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(auto_now=True)
    
    # Extracted fields for dashboard (populated from raw JSON during sync)
    owner = models.CharField(max_length=255, blank=True, null=True, db_index=True) 
    account_name = models.CharField(max_length=255, blank=True, null=True)
    full_name = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    first_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(max_length=255, blank=True, null=True)
    mobile = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    contact_type = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    lead_source = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    lead_stage = models.CharField(max_length=500, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    locations = models.CharField(max_length=500, blank=True, null=True)
    area_requirement = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=500, blank=True, null=True, db_index=True)
    reason = models.CharField(max_length=255, blank=True, null=True)
    industry_type = models.CharField(max_length=255, blank=True, null=True) 
    business_type = models.CharField(max_length=255, blank=True, null=True)
    business_model = models.CharField(max_length=255, blank=True, null=True)
    last_activity_time = models.DateTimeField(blank=True, null=True)
    
    # Notes (fetched separately, cached for 24 hours)
    notes = models.TextField(blank=True, null=True)
    notes_fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('bigin_id', 'module')
        indexes = [
            models.Index(fields=['module', 'modified_time']),
            models.Index(fields=['module', 'created_time']),
            models.Index(fields=['owner', 'status']),
            # Performance indexes from 0009 migration
            models.Index(fields=['module', 'owner', 'status'], name='bigin_mod_own_stat_idx'),
            models.Index(fields=['module', 'contact_type'], name='bigin_mod_type_idx'),
            models.Index(fields=['module', 'lead_stage'], name='bigin_mod_stage_idx'),
            models.Index(fields=['full_name'], name='bigin_fullname_idx'),
            models.Index(fields=['email'], name='bigin_email_idx'),
        ]

    def __str__(self):
        return f"{self.module} | {self.bigin_id}"
    
    @property
    def needs_notes_refresh(self):
        """Check if notes need re-fetching (>24 hours old)"""
        if not self.notes_fetched_at:
            return True
        return timezone.now() - self.notes_fetched_at > timedelta(hours=24)


# Proxy Models
class BiginContact(BiginRecord):
    class Meta:
        proxy = True
        verbose_name = "Bigin Contact"
        verbose_name_plural = "Bigin Contacts"

    @property
    def matched_gmail_lead(self):
        """
        Get the matched Gmail Lead via LeadAttribution
        Returns: LeadEmail instance or None
        Cached to avoid repeated queries
        """
        if not hasattr(self, '_cached_gmail_lead'):
            from integrations.models import LeadAttribution
            attribution = LeadAttribution.objects.filter(
                bigin_contact=self
            ).select_related('gmail_lead').first()
            self._cached_gmail_lead = attribution.gmail_lead if attribution else None
            self._cached_attribution = attribution
        return self._cached_gmail_lead

    @property
    def utm_campaign(self):
        """UTM Campaign from matched Gmail Lead"""
        lead = self.matched_gmail_lead
        return lead.utm_campaign if lead else ''

    @property
    def utm_medium(self):
        """UTM Medium from matched Gmail Lead"""
        lead = self.matched_gmail_lead
        return lead.utm_medium if lead else ''

    @property
    def utm_term(self):
        """UTM Term from matched Gmail Lead"""
        lead = self.matched_gmail_lead
        return lead.utm_term if lead else ''

    @property
    def utm_content(self):
        """UTM Content from matched Gmail Lead"""
        lead = self.matched_gmail_lead
        return lead.utm_content if lead else ''

    @property
    def gclid(self):
        """Google Click ID from matched Gmail Lead"""
        lead = self.matched_gmail_lead
        return lead.gclid if lead else ''

    @property
    def attribution_confidence(self):
        """Match confidence for attribution (exact_email, fuzzy_email, temporal)"""
        if not hasattr(self, '_cached_attribution'):
            _ = self.matched_gmail_lead  # populates _cached_attribution
        return self._cached_attribution.get_match_confidence_display() if self._cached_attribution else None


class BiginDeal(BiginRecord):
    class Meta:
        proxy = True
        verbose_name = "Bigin Deal"
        verbose_name_plural = "Bigin Deals"


class BiginAccount(BiginRecord):
    class Meta:
        proxy = True
        verbose_name = "Bigin Account"
        verbose_name_plural = "Bigin Accounts"


class BiginProduct(BiginRecord):
    class Meta:
        proxy = True
        verbose_name = "Bigin Product"
        verbose_name_plural = "Bigin Products"


class BiginNote(BiginRecord):
    class Meta:
        proxy = True
        verbose_name = "Bigin Note"
        verbose_name_plural = "Bigin Notes"


class BiginSettings(models.Model):
    """
    Singleton model for Bigin/Zoho OAuth configuration.
    Values stored here override environment variables.
    Only one record exists (pk=1 enforced).
    """
    client_id = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Zoho OAuth Client ID (overrides ZOHO_CLIENT_ID env var)"
    )
    client_secret = models.CharField(
        max_length=500, blank=True, default='',
        help_text="Zoho OAuth Client Secret — stored encrypted"
    )
    redirect_uri = models.URLField(
        blank=True, default='',
        help_text="OAuth redirect URI (overrides ZOHO_REDIRECT_URI env var)"
    )
    auth_url = models.URLField(
        blank=True, default='https://accounts.zoho.com/oauth/v2/auth',
        help_text="Zoho OAuth authorization URL"
    )
    token_url = models.URLField(
        blank=True, default='https://accounts.zoho.com/oauth/v2/token',
        help_text="Zoho OAuth token URL"
    )

    # Audit
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bigin_settings_updates'
    )

    class Meta:
        verbose_name = "Bigin Settings"
        verbose_name_plural = "Bigin Settings"

    def __str__(self):
        return "Bigin OAuth Settings"

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
        if not self.client_secret:
            return ''
        try:
            return _get_bigin_fernet().decrypt(self.client_secret.encode()).decode()
        except Exception:
            return self.client_secret

    def set_client_secret(self, value):
        """Encrypt and store client secret"""
        if not value:
            return
        try:
            self.client_secret = _get_bigin_fernet().encrypt(value.encode()).decode()
        except Exception:
            self.client_secret = value

    def get_credential_source(self):
        """Return 'database', 'environment', or 'not_configured' for display"""
        from django.conf import settings as django_settings
        if self.client_id:
            return 'database'
        elif getattr(django_settings, 'ZOHO_CLIENT_ID', ''):
            return 'environment'
        return 'not_configured'