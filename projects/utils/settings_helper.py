"""
Quotation Settings Helper
Resolves configuration: DB settings take priority over environment variables.
"""

from django.conf import settings


def get_quotation_oauth_config():
    """
    Get Quotation OAuth configuration.
    Priority: Database settings → Environment variables → Empty string
    """
    from projects.models_quotation_settings import QuotationSettings
    db = QuotationSettings.get_settings()

    return {
        'client_id': db.client_id or getattr(settings, 'QUOTATION_CLIENT_ID', ''),
        'client_secret': db.get_decrypted_client_secret() or getattr(settings, 'QUOTATION_CLIENT_SECRET', ''),
        'redirect_uri': db.redirect_uri or getattr(settings, 'QUOTATION_REDIRECT_URI', ''),
    }
