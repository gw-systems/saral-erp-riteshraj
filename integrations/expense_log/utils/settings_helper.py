"""
Settings resolution helper for Google Sheets OAuth credentials.
Follows pattern: DB settings override environment variables.
"""
from django.conf import settings
import os
import logging

logger = logging.getLogger(__name__)


class ExpenseLogSettingsHelper:
    """Resolves OAuth credentials from DB or environment variables"""

    @staticmethod
    def get_oauth_config():
        """
        Get OAuth configuration with fallback chain:
        1. Database (ExpenseLogSettings model)
        2. Environment variables
        3. Django settings.py

        Returns:
            dict: {
                'client_id': str,
                'client_secret': str,
                'redirect_uri': str,
                'api_version': str (default: 'v4')
            }
        """
        from integrations.expense_log.models import ExpenseLogSettings

        config = {
            'client_id': '',
            'client_secret': '',
            'redirect_uri': '',
            'api_version': 'v4'
        }

        try:
            # Try to load from database
            db_settings = ExpenseLogSettings.load()

            # Client ID: DB > env > settings.py
            config['client_id'] = (
                db_settings.client_id or
                os.getenv('GOOGLE_SHEETS_CLIENT_ID', '') or
                getattr(settings, 'GOOGLE_SHEETS_CLIENT_ID', '')
            )

            # Client Secret: DB (decrypted) > env > settings.py
            config['client_secret'] = (
                db_settings.get_decrypted_client_secret() or
                os.getenv('GOOGLE_SHEETS_CLIENT_SECRET', '') or
                getattr(settings, 'GOOGLE_SHEETS_CLIENT_SECRET', '')
            )

            # Redirect URI: DB > env > settings.py
            config['redirect_uri'] = (
                db_settings.redirect_uri or
                os.getenv('GOOGLE_SHEETS_REDIRECT_URI', '') or
                getattr(settings, 'GOOGLE_SHEETS_REDIRECT_URI', '')
            )

            # API version from DB
            config['api_version'] = db_settings.api_version or 'v4'

        except Exception as e:
            logger.warning(f"Failed to load DB settings, using env/settings.py: {e}")
            # Fallback to env/settings.py only
            config['client_id'] = os.getenv('GOOGLE_SHEETS_CLIENT_ID', '') or getattr(settings, 'GOOGLE_SHEETS_CLIENT_ID', '')
            config['client_secret'] = os.getenv('GOOGLE_SHEETS_CLIENT_SECRET', '') or getattr(settings, 'GOOGLE_SHEETS_CLIENT_SECRET', '')
            config['redirect_uri'] = os.getenv('GOOGLE_SHEETS_REDIRECT_URI', '') or getattr(settings, 'GOOGLE_SHEETS_REDIRECT_URI', '')

        return config

    @staticmethod
    def validate_oauth_config(config):
        """
        Validate OAuth configuration completeness.

        Args:
            config: dict from get_oauth_config()

        Returns:
            tuple: (is_valid: bool, missing_fields: list)
        """
        required_fields = ['client_id', 'client_secret', 'redirect_uri']
        missing = [field for field in required_fields if not config.get(field)]

        return (len(missing) == 0, missing)
