"""
Management command to insert Bigin OAuth refresh token.
File: integrations/bigin/management/commands/insert_bigin_token.py

Usage:
    python manage.py insert_bigin_token --refresh-token="YOUR_REFRESH_TOKEN"
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from integrations.bigin.models import BiginAuthToken


class Command(BaseCommand):
    help = 'Insert Bigin OAuth refresh token into database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--refresh-token',
            type=str,
            required=True,
            help='Bigin OAuth refresh token'
        )

    def handle(self, *args, **options):
        refresh_token = options['refresh_token']

        self.stdout.write(self.style.SUCCESS(
            "🔑 Inserting Bigin OAuth refresh token..."
        ))

        try:
            # Insert or update token (using encrypted storage)
            token, created = BiginAuthToken.objects.update_or_create(
                id=1,
                defaults={
                    'expires_at': timezone.now() + timedelta(hours=1)
                }
            )
            token.set_tokens(access_token='will-be-refreshed', refresh_token=refresh_token)
            token.save()

            if created:
                self.stdout.write(self.style.SUCCESS(
                    "✅ Token inserted successfully!"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    "✅ Token updated successfully!"
                ))

            self.stdout.write(f"   Token ID: {token.id}")
            self.stdout.write(f"   Expires at: {token.expires_at}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f"❌ Failed to insert token: {str(e)}"
            ))
            import traceback
            traceback.print_exc()
            raise
