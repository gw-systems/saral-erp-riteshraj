"""
Django management command to connect a Callyzer account
Usage: python manage.py callyzer_connect <account_name> <api_key>
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from integrations.callyzer.models import CallyzerToken
from integrations.callyzer.utils.encryption import CallyzerEncryption

User = get_user_model()


class Command(BaseCommand):
    help = 'Connect a new Callyzer account'

    def add_arguments(self, parser):
        parser.add_argument(
            'account_name',
            type=str,
            help='Account name (e.g., "Sales Team")'
        )
        parser.add_argument(
            'api_key',
            type=str,
            help='Callyzer API key'
        )
        parser.add_argument(
            '--user',
            type=str,
            default='admin',
            help='Username to associate with this account (default: admin)'
        )

    def handle(self, *args, **options):
        account_name = options['account_name']
        api_key = options['api_key']
        username = options['user']

        # Get user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist')

        # Check if account already exists
        if CallyzerToken.objects.filter(account_name=account_name).exists():
            raise CommandError(f'Account "{account_name}" already exists')

        # Encrypt API key
        try:
            encrypted_api_key = CallyzerEncryption.encrypt(api_key)
        except Exception as e:
            raise CommandError(f'Failed to encrypt API key: {e}')

        # Create token
        try:
            token = CallyzerToken.objects.create(
                user=user,
                account_name=account_name,
                encrypted_api_key=encrypted_api_key,
                is_active=True
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Successfully connected Callyzer account "{account_name}" (ID: {token.id})'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    f'\nNext step: Run initial sync with:\n'
                    f'  python manage.py callyzer_sync --token-id {token.id}'
                )
            )
        except Exception as e:
            raise CommandError(f'Failed to create token: {e}')
