"""
Management command to update Bigin OAuth tokens (access + refresh).
File: integrations/bigin/management/commands/update_bigin_token.py

Usage:
    python manage.py update_bigin_token --access-token="ACCESS_TOKEN" --refresh-token="REFRESH_TOKEN"
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from integrations.bigin.models import BiginAuthToken


class Command(BaseCommand):
    help = 'Update Bigin OAuth tokens (access + refresh)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--access-token',
            type=str,
            required=True,
            help='Bigin OAuth access token'
        )
        parser.add_argument(
            '--refresh-token',
            type=str,
            required=True,
            help='Bigin OAuth refresh token'
        )
        parser.add_argument(
            '--expires-hours',
            type=int,
            default=1,
            help='Hours until token expires (default: 1)'
        )

    def handle(self, *args, **options):
        access_token = options['access_token']
        refresh_token = options['refresh_token']
        expires_hours = options['expires_hours']

        self.stdout.write(self.style.SUCCESS(
            "🔑 Updating Bigin OAuth tokens..."
        ))

        try:
            # Insert or update token
            token, created = BiginAuthToken.objects.update_or_create(
                id=1,
                defaults={
                    'access_token': access_token,
                    'refresh_token': refresh_token,
                    'expires_at': timezone.now() + timedelta(hours=expires_hours)
                }
            )

            if created:
                self.stdout.write(self.style.SUCCESS(
                    "✅ Token created successfully!"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    "✅ Token updated successfully!"
                ))

            self.stdout.write(f"   Token ID: {token.id}")
            self.stdout.write(f"   Access Token (first 20 chars): {token.access_token[:20]}...")
            self.stdout.write(f"   Refresh Token (first 20 chars): {token.refresh_token[:20]}...")
            self.stdout.write(f"   Expires at: {token.expires_at}")
            self.stdout.write(f"   Is Expired: {token.is_expired()}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f"❌ Failed to update token: {str(e)}"
            ))
            import traceback
            traceback.print_exc()
            raise
