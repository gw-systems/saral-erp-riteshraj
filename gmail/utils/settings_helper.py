"""
Gmail Settings Helper
Resolves configuration: DB settings take priority over environment variables.
"""

from django.conf import settings


def get_gmail_config():
    """
    Get Gmail/Google OAuth configuration.
    Priority: Database settings → Environment variables → Empty string
    """
    from gmail.models import GmailSettings
    db = GmailSettings.load()

    # Gmail API scopes - REQUIRED for full functionality
    default_scopes = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.modify',
        'https://mail.google.com/',  # Full access for all operations
    ]

    return {
        'client_id': db.client_id or getattr(settings, 'GOOGLE_CLIENT_ID', ''),
        'client_secret': db.get_decrypted_client_secret() or getattr(settings, 'GOOGLE_CLIENT_SECRET', ''),
        'redirect_uri': db.redirect_uri or getattr(settings, 'GOOGLE_REDIRECT_URI', ''),
        'scopes': default_scopes,
        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
        'token_uri': 'https://oauth2.googleapis.com/token',
    }
