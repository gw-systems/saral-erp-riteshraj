"""
Required Settings for Adobe Sign Integration
Add these to your settings.py or environment variables
"""

# ============================================================================
# CRITICAL: Webhook Security (C2 Fix)
# ============================================================================

# Generate a strong random secret for webhook signature verification
# Example: import secrets; secrets.token_urlsafe(32)
ADOBE_SIGN_WEBHOOK_SECRET = 'your-webhook-secret-here-generate-with-secrets-module'

# ============================================================================
# Adobe Sign API Configuration
# ============================================================================

# OAuth Configuration
ADOBE_SIGN_CLIENT_ID = 'your-adobe-client-id'
ADOBE_SIGN_CLIENT_SECRET = 'your-adobe-client-secret'
ADOBE_SIGN_REFRESH_TOKEN = 'your-refresh-token'

# API Base URL (region-specific)
ADOBE_SIGN_BASE_URL = 'https://api.in1.adobesign.com/api/rest/v6'

# Director Configuration (H6 Fix - must be valid email)
ADOBE_SIGN_DIRECTOR_EMAIL = 'director@yourcompany.com'
ADOBE_SIGN_DIRECTOR_NAME = 'Vivek Tiwari'

# ============================================================================
# Optional: Webhook IP Whitelist (Additional Security)
# ============================================================================

# Adobe Sign webhook source IPs (update with actual Adobe IPs)
ADOBE_SIGN_WEBHOOK_ALLOWED_IPS = [
    '13.52.0.0/16',  # Example: Update with real Adobe Sign IPs
    '54.0.0.0/8',
]

# ============================================================================
# Django Settings Updates
# ============================================================================

# Add to INSTALLED_APPS if not already there
# INSTALLED_APPS = [
#     ...
#     'integrations.adobe_sign',
#     ...
# ]

# ============================================================================
# Environment Variable Examples (.env file)
# ============================================================================

"""
# Adobe Sign Configuration
ADOBE_SIGN_CLIENT_ID=CBJ...
ADOBE_SIGN_CLIENT_SECRET=xxx...
ADOBE_SIGN_REFRESH_TOKEN=3AAABLbl...
ADOBE_SIGN_BASE_URL=https://api.in1.adobesign.com/api/rest/v6
ADOBE_SIGN_DIRECTOR_EMAIL=director@company.com
ADOBE_SIGN_DIRECTOR_NAME=Vivek Tiwari
ADOBE_SIGN_WEBHOOK_SECRET=generate-random-32-char-secret-here
"""

# ============================================================================
# Startup Validation (Add to apps.py)
# ============================================================================

"""
from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class AdobeSignConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations.adobe_sign'

    def ready(self):
        # Validate critical settings on startup
        required_settings = [
            'ADOBE_SIGN_CLIENT_ID',
            'ADOBE_SIGN_CLIENT_SECRET',
            'ADOBE_SIGN_DIRECTOR_EMAIL',
            'ADOBE_SIGN_WEBHOOK_SECRET',
        ]

        for setting in required_settings:
            if not getattr(settings, setting, None):
                raise ImproperlyConfigured(
                    f'{setting} is required for Adobe Sign integration'
                )

        # Validate email format
        from django.core.validators import validate_email
        try:
            validate_email(settings.ADOBE_SIGN_DIRECTOR_EMAIL)
        except:
            raise ImproperlyConfigured(
                f'ADOBE_SIGN_DIRECTOR_EMAIL is not a valid email'
            )
"""
