"""
Management command to sync all Bigin modules (Contacts, Pipelines, Accounts, Products, Notes).
File: integrations/bigin/management/commands/sync_bigin_all.py

Usage:
    python manage.py sync_bigin_all                    # Incremental sync
    python manage.py sync_bigin_all --full             # Full sync (all records)
"""

from django.core.management.base import BaseCommand
from datetime import datetime
from integrations.bigin.sync_service import run_sync_all_modules


class Command(BaseCommand):
    help = 'Sync all Bigin modules (Contacts, Pipelines, Accounts, Products, Notes)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--full',
            action='store_true',
            help='Run full sync (fetch all records, ignore last modified time)'
        )

    def handle(self, *args, **options):
        run_full = options.get('full', False)

        sync_type = "FULL" if run_full else "INCREMENTAL"

        self.stdout.write(self.style.SUCCESS(
            f"🚀 Starting {sync_type} Bigin Sync..."
        ))
        self.stdout.write(f"   Modules: Contacts, Pipelines, Accounts, Products, Notes")
        self.stdout.write(f"   Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # Call the sync function
            run_sync_all_modules(run_full=run_full)

            self.stdout.write(self.style.SUCCESS(
                f"\n✅ {sync_type} sync completed successfully!"
            ))
            self.stdout.write(f"   Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f"\n❌ Sync failed: {str(e)}"
            ))
            import traceback
            traceback.print_exc()
            raise
