"""
Quotation Settings Model
Frontend-configurable settings for quotation system
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from decimal import Decimal
import re

User = get_user_model()


class QuotationSettings(models.Model):
    """
    Singleton model for quotation system settings.
    Configurable via frontend UI - NO hardcoded values in settings.py.
    """

    # Google Docs Template Configuration
    google_docs_template_url = models.URLField(
        blank=True,
        help_text="Full Google Docs URL (e.g., https://docs.google.com/document/d/DOCUMENT_ID/edit)"
    )
    google_docs_template_id = models.CharField(
        max_length=255,
        blank=True,
        editable=False,
        help_text="Auto-extracted from URL"
    )

    # Google OAuth 2.0 Configuration (replaces service account)
    client_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Google OAuth 2.0 Client ID"
    )
    client_secret = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Google OAuth 2.0 Client Secret — stored encrypted"
    )
    redirect_uri = models.URLField(
        blank=True,
        default='',
        help_text="OAuth redirect URI (e.g., https://yourdomain.com/projects/quotations/oauth-callback/)"
    )

    # Default Quotation Values
    default_gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('18.00'),
        help_text="Default GST rate in percentage"
    )
    default_validity_days = models.IntegerField(
        default=30,
        help_text="Default quotation validity in days"
    )

    # Email Templates (for quotation sending)
    email_subject_template = models.CharField(
        max_length=500,
        default="Quotation {quotation_number} - {client_company}",
        help_text="Use {quotation_number}, {client_company}, {date} as placeholders"
    )
    email_body_template = models.TextField(
        default="""Dear {client_name},

Please find attached quotation {quotation_number} for your review.

This quotation is valid until {validity_date}.

If you have any questions, please don't hesitate to contact us.

Best regards,
{created_by_name}""",
        help_text="Use {client_name}, {quotation_number}, {validity_date}, {created_by_name} as placeholders"
    )

    # Scope of Service Options (JSON array)
    scope_of_service_options = models.JSONField(
        default=list,
        blank=True,
        help_text="Predefined scope of service options (JSON array)"
    )

    # Default Terms & Conditions Templates
    default_payment_terms = models.TextField(
        default="""• Payment due within 15 days from invoice date
• One month's advance / transport payment in advance for the trip
• Payment via NEFT/RTGS in favour of "Godamwale Trading & Logistics Pvt. Ltd."
• Late payment attracts interest @ 2% per month""",
        help_text="Default payment terms (shown in quotation if not customized)"
    )

    default_sla_terms = models.TextField(
        default="""• 99% inventory accuracy
• Same-day dispatch for orders placed before 2:00 PM cut-off
• Dedicated account manager for customers over 500 pallets
• Monthly performance reports and inventory reconciliation""",
        help_text="Default SLA & service commitments"
    )

    default_contract_terms = models.TextField(
        default="""• Minimum contract period: 3 months (To be discussed)
• Auto-renewal for subsequent periods unless 30-day notice provided
• Rates subject to annual revision based on market conditions""",
        help_text="Default contract tenure terms"
    )

    default_liability_terms = models.TextField(
        default="""• Insurance coverage for goods in transit and storage (up to declared value) to be taken by customer
• Compliance with GST, FSSAI, and other applicable regulations to be taken by customer
• Liability limited to two months of rent or replacement value of damaged/lost goods, whichever is lesser
• Force majeure clause applicable for natural disasters and unforeseen events""",
        help_text="Default liability & compliance terms"
    )

    # Timestamps
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'quotation_settings'
        verbose_name = 'Quotation Settings'
        verbose_name_plural = 'Quotation Settings'

    def __str__(self):
        return "Quotation Settings"

    def clean(self):
        """Validate and extract Google Docs document ID from URL."""
        if self.google_docs_template_url:
            match = re.search(r'/d/([a-zA-Z0-9-_]+)', self.google_docs_template_url)
            if match:
                self.google_docs_template_id = match.group(1)
            else:
                raise ValidationError(
                    {'google_docs_template_url': 'Invalid Google Docs URL format. '
                     'Expected: https://docs.google.com/document/d/DOCUMENT_ID/edit'}
                )

    def save(self, *args, **kwargs):
        """Singleton pattern — only one settings instance allowed."""
        # Enforce singleton
        if not self.pk and QuotationSettings.objects.exists():
            raise ValidationError("Only one QuotationSettings instance allowed")

        # Run clean() to validate URL and extract document ID
        self.clean()

        super().save(*args, **kwargs)

    def _get_fernet(self):
        """Get Fernet cipher for encrypting/decrypting client secret."""
        from cryptography.fernet import Fernet
        from django.conf import settings as django_settings
        import base64

        if hasattr(django_settings, 'QUOTATION_ENCRYPTION_KEY'):
            key = django_settings.QUOTATION_ENCRYPTION_KEY.encode()
        else:
            # Fallback to SECRET_KEY
            key = base64.urlsafe_b64encode(
                django_settings.SECRET_KEY[:32].encode().ljust(32)[:32]
            )
        return Fernet(key)

    def get_decrypted_client_secret(self):
        """Return decrypted client secret."""
        if not self.client_secret:
            return ''
        try:
            return self._get_fernet().decrypt(self.client_secret.encode()).decode()
        except Exception:
            # If decryption fails, assume it's already plaintext (backward compatibility)
            return self.client_secret

    def set_client_secret(self, value):
        """Encrypt and store client secret."""
        if not value:
            self.client_secret = ''
            return
        try:
            self.client_secret = self._get_fernet().encrypt(value.encode()).decode()
        except Exception:
            # If encryption fails, store as plaintext (not recommended)
            self.client_secret = value

    def get_credential_source(self):
        """Return 'database', 'environment', or 'not_configured' for display."""
        from django.conf import settings as django_settings
        if self.client_id:
            return 'database'
        elif getattr(django_settings, 'QUOTATION_CLIENT_ID', ''):
            return 'environment'
        return 'not_configured'

    @classmethod
    def get_settings(cls):
        """Get or create singleton settings instance."""
        settings, created = cls.objects.get_or_create(pk=1)

        # Initialize default scope of service options if empty
        if not settings.scope_of_service_options:
            settings.scope_of_service_options = [
                {
                    "id": "warehousing",
                    "title": "Warehousing Services",
                    "points": [
                        "Dedicated warehouse space allocation as per client requirements",
                        "Security surveillance and fire safety compliance"
                    ]
                },
                {
                    "id": "inbound_outbound",
                    "title": "Inbound & Outbound Handling",
                    "points": [
                        "Goods receipt, quality inspection, and put-away",
                        "GRN (Goods Receipt Note) generation and documentation",
                        "Loading/unloading with MHE (forklifts, pallet jacks)"
                    ]
                },
                {
                    "id": "pick_pack_dispatch",
                    "title": "Pick, Pack & Dispatch",
                    "points": [
                        "Order-wise picking (FIFO/FEFO compliance)",
                        "Custom packaging and labelling services",
                        "Same-day dispatch for orders before cut-off time"
                    ]
                },
                {
                    "id": "value_added",
                    "title": "Value-Added Services",
                    "points": [
                        "Kitting and bundling services",
                        "Returns processing and refurbishment",
                        "Quality control and inventory audits"
                    ]
                },
                {
                    "id": "wms_platform",
                    "title": "Tech Platform Access (WMS)",
                    "points": [
                        "Access to Inciflo WMS for real-time inventory tracking",
                        "Dashboard for order management and reporting",
                        "API integration support for seamless system connectivity"
                    ]
                },
                {
                    "id": "transport",
                    "title": "Transport Services (if applicable)",
                    "points": []
                }
            ]
            # Use update_fields to avoid triggering the full save() chain
            # (URL validation, singleton check) when only initialising defaults.
            settings.save(update_fields=['scope_of_service_options'])

        return settings


class QuotationToken(models.Model):
    """
    OAuth2 token for Google Docs/Drive API access.
    Each user who creates quotations needs their own OAuth token.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='quotation_tokens'
    )
    email_account = models.EmailField(
        unique=True,
        help_text="Google account email used for OAuth"
    )
    encrypted_token_data = models.TextField(
        help_text="Encrypted OAuth2 token JSON"
    )

    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'quotation_tokens'
        verbose_name = 'Quotation OAuth Token'
        verbose_name_plural = 'Quotation OAuth Tokens'

    def __str__(self):
        return f"{self.email_account} ({'Active' if self.is_active else 'Inactive'})"

    def can_be_accessed_by(self, user):
        """Check if user can access this token."""
        if user.role in ['admin', 'director']:
            return True
        return self.user == user
