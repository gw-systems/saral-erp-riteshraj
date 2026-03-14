from django.core.management.base import BaseCommand

from integrations.transport_sheet.sync_engine import TransportSheetSyncEngine


class Command(BaseCommand):
    help = 'Sync manual transport Google Sheet into ExpenseRecord'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            default='management_command',
            help='Username to attribute the sync to (default: management_command)',
        )

    def handle(self, *args, **options):
        self.stdout.write('Starting transport sheet sync...')
        try:
            engine = TransportSheetSyncEngine(triggered_by_user=options['user'])
            stats = engine.sync()
            self.stdout.write(self.style.SUCCESS(
                f"Sync complete: {stats['created']} created, "
                f"{stats['updated']} updated, "
                f"{stats['skipped']} skipped, "
                f"{stats['errors']} errors "
                f"(total: {stats['total_rows']} rows)"
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Sync failed: {e}"))
            raise
