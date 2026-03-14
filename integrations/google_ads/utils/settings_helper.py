"""
Google Ads Settings Helper
Resolves configuration: DB settings take priority over environment variables.
"""

from django.conf import settings


def get_google_ads_config():
    """
    Get Google Ads configuration.
    Priority: Database settings → Environment variables → Empty string
    """
    from integrations.google_ads.models import GoogleAdsSettings
    db = GoogleAdsSettings.load()

    return {
        'client_id': db.client_id or getattr(settings, 'GOOGLE_ADS_CLIENT_ID', ''),
        'client_secret': db.get_decrypted_client_secret() or getattr(settings, 'GOOGLE_ADS_CLIENT_SECRET', ''),
        'developer_token': db.get_decrypted_developer_token() or getattr(settings, 'GOOGLE_ADS_DEVELOPER_TOKEN', ''),
        'customer_id': db.customer_id or getattr(settings, 'GOOGLE_ADS_CUSTOMER_ID', ''),
        'api_version': db.api_version or getattr(settings, 'GOOGLE_ADS_API_VERSION', 'v19'),
        'redirect_uri': db.redirect_uri or getattr(settings, 'GOOGLE_ADS_REDIRECT_URI', ''),
    }
