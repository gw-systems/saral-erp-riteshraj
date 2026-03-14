"""
Management command to clean up old SyncLog entries.

Usage:
    python manage.py cleanup_synclogs              # Delete logs older than 90 days
    python manage.py cleanup_synclogs --days 60     # Delete logs older than 60 days
    python manage.py cleanup_synclogs --dry-run     # Preview without deleting
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from integrations.models import SyncLog


class Command(BaseCommand):
    help = 'Delete SyncLog entries older than N days (default 90)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=90,
            help='Delete logs older than this many days (default: 90)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show count of records that would be deleted without deleting',
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(days=days)

        qs = SyncLog.objects.filter(started_at__lt=cutoff)
        count = qs.count()

        if dry_run:
            self.stdout.write(f'[DRY RUN] Would delete {count} SyncLog entries older than {days} days (before {cutoff:%Y-%m-%d})')
            return

        if count == 0:
            self.stdout.write('No SyncLog entries to clean up.')
            return

        # Delete in batches to avoid locking the table
        deleted_total = 0
        batch_size = 5000
        while True:
            batch_ids = list(qs.values_list('id', flat=True)[:batch_size])
            if not batch_ids:
                break
            deleted, _ = SyncLog.objects.filter(id__in=batch_ids).delete()
            deleted_total += deleted

        self.stdout.write(self.style.SUCCESS(
            f'Deleted {deleted_total} SyncLog entries older than {days} days (before {cutoff:%Y-%m-%d})'
        ))
