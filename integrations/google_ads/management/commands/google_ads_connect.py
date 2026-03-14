"""
Django management command to connect a Google Ads account
Usage: python manage.py google_ads_connect
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from integrations.google_ads.models import GoogleAdsToken
from integrations.google_ads.utils.encryption import GoogleAdsEncryption
from integrations.google_ads.utils.google_ads_auth import GoogleAdsAuth

User = get_user_model()


class Command(BaseCommand):
    help = 'Connect a Google Ads account (requires manual OAuth - use web interface instead)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-mode',
            action='store_true',
            help='Create a test account for development (requires manual token)'
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                '⚠️  Google Ads requires OAuth2 authentication through a web browser.\n'
                '   Please use the Settings page in the web interface:\n'
                f'   → Navigate to: /integrations/google-ads/settings/\n'
                f'   → Click "Connect via Google OAuth"\n'
                f'   → Complete the OAuth flow\n'
            )
        )

        if options['test_mode']:
            self.stdout.write(
                self.style.WARNING(
                    '\n📝 Test Mode Instructions:\n'
                    '   1. First complete OAuth flow manually in browser\n'
                    '   2. Copy the tokens from the database\n'
                    '   3. The account will then be ready for testing\n'
                )
            )
