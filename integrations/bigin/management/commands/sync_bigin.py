"""
Management command to sync Bigin contacts.
File: integrations/bigin/management/commands/sync_bigin.py
"""

from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
from django.utils import timezone
from integrations.bigin.bigin_sync import download_bigin_contacts


class Command(BaseCommand):
    help = 'Download contacts from Bigin CRM with optional date filtering'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Only sync contacts from last N days (e.g., --days 1 for today only)'
        )
        
        parser.add_argument(
            '--start-date',
            type=str,
            default=None,
            help='Sync contacts from this date onwards (format: YYYY-MM-DD)'
        )
    
    def handle(self, *args, **options):
        days = options.get('days')
        start_date_str = options.get('start_date')
        start_date = None
        
        # Determine start_date based on arguments
        if start_date_str:
            try:
                # Parse the date string
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                start_date = timezone.make_aware(start_date)
                self.stdout.write(self.style.SUCCESS(
                    f"🚀 Syncing contacts from {start_date.strftime('%Y-%m-%d')} onwards..."
                ))
            except ValueError:
                self.stdout.write(self.style.ERROR(
                    f"❌ Invalid date format: {start_date_str}. Use YYYY-MM-DD"
                ))
                return
        elif days:
            start_date = timezone.now() - timedelta(days=days)
            self.stdout.write(self.style.SUCCESS(
                f"🚀 Syncing contacts from last {days} day(s) (since {start_date.strftime('%Y-%m-%d %H:%M')})"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "🚀 Starting FULL Bigin Sync (all contacts)..."
            ))
        
        # Display sync start time
        self.stdout.write(f"   Started at: {datetime.now().strftime('%H:%M:%S')}")
        
        try:
            # Perform the sync
            contacts = download_bigin_contacts(start_date=start_date)
            
            # Success message
            self.stdout.write(self.style.SUCCESS(
                f"\n✅ Sync completed successfully!"
            ))
            self.stdout.write(f"   Total contacts synced: {len(contacts)}")
            self.stdout.write(f"   Finished at: {datetime.now().strftime('%H:%M:%S')}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f"\n❌ Sync failed: {str(e)}"
            ))
            import traceback
            traceback.print_exc()