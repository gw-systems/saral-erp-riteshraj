"""
Gmail Leads Settings Helper
Resolves configuration: DB settings take priority over environment variables.
"""

from django.conf import settings


def get_gmail_leads_config():
    """
    Get Gmail Leads OAuth configuration.
    Priority: Database settings → Environment variables → Empty string
    """
    from integrations.gmail_leads.models import GmailLeadsSettings
    db = GmailLeadsSettings.load()

    return {
        'client_id': db.client_id or getattr(settings, 'GMAIL_LEADS_CLIENT_ID', ''),
        'client_secret': db.get_decrypted_client_secret() or getattr(settings, 'GMAIL_LEADS_CLIENT_SECRET', ''),
        'redirect_uri': db.redirect_uri or getattr(settings, 'GMAIL_LEADS_REDIRECT_URI', ''),
    }
