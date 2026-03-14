from django.core.management.base import BaseCommand
from integrations.bigin.tasks import sync_module
from integrations.bigin.models import BiginRecord
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test Bigin module sync'

    def add_arguments(self, parser):
        parser.add_argument(
            '--module',
            type=str,
            default='deals',
            help='Module to sync (contacts, deals, notes, etc.)'
        )
        parser.add_argument(
            '--full',
            action='store_true',
            help='Run full sync (ignore last modified)'
        )

    def handle(self, *args, **options):
        module = options['module']
        run_full = options['full']
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Testing {module.upper()} sync")
        self.stdout.write(f"Full sync: {run_full}")
        self.stdout.write(f"{'='*60}\n")
        
        # Show counts before
        before_count = BiginRecord.objects.filter(module=module).count()
        self.stdout.write(f"Records before sync: {before_count}")
        
        try:
            # Run sync
            sync_module(module, run_full=run_full)
            
            # Show counts after
            after_count = BiginRecord.objects.filter(module=module).count()
            self.stdout.write(self.style.SUCCESS(f"\n✅ Sync completed!"))
            self.stdout.write(f"Records after sync: {after_count}")
            self.stdout.write(f"New/Updated records: {after_count - before_count}")
            
            # Show sample records
            self.stdout.write(f"\nSample {module} records:")
            for record in BiginRecord.objects.filter(module=module).order_by('-modified_time')[:5]:
                self.stdout.write(f"  - {record.bigin_id}: {record.raw.get('Deal_Name') or record.raw.get('Full_Name') or record.bigin_id}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Sync failed: {str(e)}"))
            logger.exception("Sync error")