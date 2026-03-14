"""
Google Ads Integration Models
Stores OAuth credentials, campaign data, search terms, and sync logs
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class GoogleAdsToken(models.Model):
    """
    Stores encrypted OAuth2 tokens for Google Ads accounts
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='google_ads_tokens')
    account_name = models.CharField(max_length=255, help_text="Friendly name for this account")
    customer_id = models.CharField(max_length=50, help_text="Google Ads Customer ID (e.g., 3867069282)")

    # OAuth2 credentials stored encrypted
    encrypted_token = models.TextField(help_text="Encrypted OAuth2 token (access_token, refresh_token, etc.)")

    # Developer token and client credentials (stored in settings, not here)
    # These are consistent across all accounts

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'google_ads_tokens'
        verbose_name = 'Google Ads Token'
        verbose_name_plural = 'Google Ads Tokens'
        ordering = ['-created_at']
        unique_together = [['customer_id']]

    def __str__(self):
        return f"{self.account_name} ({self.customer_id})"


class Campaign(models.Model):
    """
    Stores Google Ads campaigns
    """
    token = models.ForeignKey(GoogleAdsToken, on_delete=models.CASCADE, related_name='campaigns')

    campaign_id = models.BigIntegerField(help_text="Google Ads Campaign ID")
    campaign_name = models.CharField(max_length=500)
    campaign_status = models.CharField(max_length=50)  # ENABLED, PAUSED, REMOVED

    # Budget settings
    daily_budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Daily budget amount")
    monthly_budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Monthly budget (daily * days in month)")
    budget_delivery_method = models.CharField(max_length=50, null=True, blank=True, help_text="STANDARD or ACCELERATED")

    # Legacy budget field (kept for backwards compatibility)
    budget_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    budget_type = models.CharField(max_length=50, null=True, blank=True)

    # Bidding strategy
    bidding_strategy = models.CharField(max_length=100, null=True, blank=True)
    bidding_strategy_type = models.CharField(max_length=100, null=True, blank=True, help_text="Bidding strategy type from API")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'google_ads_campaigns'
        verbose_name = 'Campaign'
        verbose_name_plural = 'Campaigns'
        ordering = ['campaign_name']
        unique_together = [['token', 'campaign_id']]
        indexes = [
            models.Index(fields=['campaign_id']),
            models.Index(fields=['campaign_status']),
        ]

    def __str__(self):
        return f"{self.campaign_name} ({self.campaign_id})"


class CampaignPerformance(models.Model):
    """
    Stores daily performance metrics for campaigns
    """
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='performance')
    date = models.DateField(help_text="Date of the performance data")

    # Performance metrics
    impressions = models.BigIntegerField(default=0)
    clicks = models.BigIntegerField(default=0)
    cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    conversions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    conversion_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Impression share (NEW)
    impression_share = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="Search impression share (0-1)")

    # Calculated metrics
    ctr = models.DecimalField(max_digits=10, decimal_places=4, default=0, help_text="Click-through rate")
    avg_cpc = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Average cost per click")
    avg_cpm = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Average cost per mille")
    conversion_rate = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    cost_per_conversion = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Budget utilization (NEW)
    budget_utilization = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="Cost / Daily Budget ratio")

    # Raw data from API
    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'google_ads_campaign_performance'
        verbose_name = 'Campaign Performance'
        verbose_name_plural = 'Campaign Performance'
        ordering = ['-date']
        unique_together = [['campaign', 'date']]
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['campaign', 'date']),
        ]

    def __str__(self):
        return f"{self.campaign.campaign_name} - {self.date}"


class DevicePerformance(models.Model):
    """
    Stores device breakdown performance (mobile, desktop, tablet)
    """
    DEVICE_CHOICES = [
        ('MOBILE', 'Mobile'),
        ('DESKTOP', 'Desktop'),
        ('TABLET', 'Tablet'),
        ('OTHER', 'Other'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='device_performance')
    date = models.DateField(help_text="Date of the performance data")
    device = models.CharField(max_length=20, choices=DEVICE_CHOICES)

    # Performance metrics
    impressions = models.BigIntegerField(default=0)
    clicks = models.BigIntegerField(default=0)
    cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    conversions = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Calculated metrics
    ctr = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    avg_cpc = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    conversion_rate = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    # Raw data from API
    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'google_ads_device_performance'
        verbose_name = 'Device Performance'
        verbose_name_plural = 'Device Performance'
        ordering = ['-date', 'device']
        unique_together = [['campaign', 'date', 'device']]
        indexes = [
            models.Index(fields=['date', 'device']),
            models.Index(fields=['campaign', 'date']),
        ]

    def __str__(self):
        return f"{self.campaign.campaign_name} - {self.device} - {self.date}"


class SearchTerm(models.Model):
    """
    Stores search terms performance data (monthly aggregation)
    """
    STATUS_CHOICES = [
        ('ADDED', 'Added'),
        ('EXCLUDED', 'Excluded'),
        ('NONE', 'None'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='search_terms')

    # Time period (monthly)
    year = models.IntegerField()
    month = models.IntegerField()

    # Search term data
    search_term = models.CharField(max_length=500)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, null=True, blank=True, help_text="Search term status (added as keyword or excluded)")
    ad_group_id = models.BigIntegerField(null=True, blank=True)
    ad_group_name = models.CharField(max_length=500, null=True, blank=True)
    keyword_id = models.BigIntegerField(null=True, blank=True)
    keyword_text = models.CharField(max_length=500, null=True, blank=True)
    match_type = models.CharField(max_length=50, null=True, blank=True)

    # Performance metrics
    impressions = models.BigIntegerField(default=0)
    clicks = models.BigIntegerField(default=0)
    cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    conversions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    conversion_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Calculated metrics
    ctr = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    avg_cpc = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    conversion_rate = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    cost_per_conversion = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Raw data from API
    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'google_ads_search_terms'
        verbose_name = 'Search Term'
        verbose_name_plural = 'Search Terms'
        ordering = ['-year', '-month', '-clicks']
        unique_together = [['campaign', 'year', 'month', 'search_term', 'ad_group_id']]
        indexes = [
            models.Index(fields=['year', 'month']),
            models.Index(fields=['campaign', 'year', 'month']),
            models.Index(fields=['search_term']),
        ]

    def __str__(self):
        return f"{self.search_term} - {self.year}/{self.month:02d}"


class GoogleAdsSettings(models.Model):
    """
    Singleton model for Google Ads API configuration.
    Values stored here override environment variables.
    Only one record exists (pk=1 enforced).
    """
    # Account Details
    account_name = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Friendly name for the Google Ads account"
    )
    customer_id = models.CharField(
        max_length=50, blank=True, default='',
        help_text="Google Ads Customer ID (e.g., 123-456-7890 or 1234567890)"
    )

    # OAuth Credentials
    client_id = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Google OAuth 2.0 Client ID (overrides GOOGLE_ADS_CLIENT_ID env var)"
    )
    client_secret = models.CharField(
        max_length=500, blank=True, default='',
        help_text="Google OAuth 2.0 Client Secret — stored encrypted"
    )
    developer_token = models.CharField(
        max_length=500, blank=True, default='',
        help_text="Google Ads Developer Token — stored encrypted"
    )
    api_version = models.CharField(
        max_length=10, blank=True, default='v19',
        help_text="Google Ads API version (e.g., v19)"
    )
    redirect_uri = models.URLField(
        blank=True, default='',
        help_text="OAuth redirect URI (overrides GOOGLE_ADS_REDIRECT_URI env var)"
    )

    # Audit
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='google_ads_settings_updates'
    )

    class Meta:
        verbose_name = "Google Ads Settings"
        verbose_name_plural = "Google Ads Settings"

    def __str__(self):
        return "Google Ads API Settings"

    def save(self, *args, **kwargs):
        self.pk = 1  # Singleton — only one record
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
            from integrations.google_ads.utils.encryption import GoogleAdsEncryption
            from cryptography.fernet import Fernet
            key = GoogleAdsEncryption.get_encryption_key()
            f = Fernet(key)
            return f.decrypt(self.client_secret.encode()).decode()
        except Exception:
            return self.client_secret  # Fallback: return as-is if not yet encrypted

    def get_decrypted_developer_token(self):
        """Return decrypted developer token"""
        if not self.developer_token:
            return ''
        try:
            from integrations.google_ads.utils.encryption import GoogleAdsEncryption
            from cryptography.fernet import Fernet
            key = GoogleAdsEncryption.get_encryption_key()
            f = Fernet(key)
            return f.decrypt(self.developer_token.encode()).decode()
        except Exception:
            return self.developer_token

    def set_client_secret(self, value):
        """Encrypt and store client secret"""
        if not value:
            return
        try:
            from integrations.google_ads.utils.encryption import GoogleAdsEncryption
            from cryptography.fernet import Fernet
            key = GoogleAdsEncryption.get_encryption_key()
            f = Fernet(key)
            self.client_secret = f.encrypt(value.encode()).decode()
        except Exception:
            self.client_secret = value

    def set_developer_token(self, value):
        """Encrypt and store developer token"""
        if not value:
            return
        try:
            from integrations.google_ads.utils.encryption import GoogleAdsEncryption
            from cryptography.fernet import Fernet
            key = GoogleAdsEncryption.get_encryption_key()
            f = Fernet(key)
            self.developer_token = f.encrypt(value.encode()).decode()
        except Exception:
            self.developer_token = value

    def get_credential_source(self):
        """Return 'database', 'environment', or 'not_configured' for display"""
        from django.conf import settings as django_settings
        if self.client_id:
            return 'database'
        elif getattr(django_settings, 'GOOGLE_ADS_CLIENT_ID', ''):
            return 'environment'
        return 'not_configured'
