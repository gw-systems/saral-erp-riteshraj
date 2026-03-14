"""
Management command to refresh Bigin OAuth token.
File: integrations/bigin/management/commands/refresh_bigin_token.py

Usage:
    python manage.py refresh_bigin_token
"""

from django.core.management.base import BaseCommand
from datetime import datetime
from integrations.bigin.sync_service import run_refresh_bigin_token


class Command(BaseCommand):
    help = 'Refresh Bigin OAuth access token'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(
            "🔑 Refreshing Bigin OAuth token..."
        ))
        self.stdout.write(f"   Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # Call the refresh function
            result = run_refresh_bigin_token()

            self.stdout.write(self.style.SUCCESS(
                f"\n✅ Token refresh completed!"
            ))
            self.stdout.write(f"   Result: {result}")
            self.stdout.write(f"   Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f"\n❌ Token refresh failed: {str(e)}"
            ))
            import traceback
            traceback.print_exc()
            raise
