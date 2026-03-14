from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
from datetime import date
from dateutil.relativedelta import relativedelta


class Command(BaseCommand):
    help = 'Drop activity_logs partitions older than ACTIVITY_LOG_RETENTION_DAYS'

    def handle(self, *args, **options):
        retention_days = getattr(settings, 'ACTIVITY_LOG_RETENTION_DAYS', 365)
        cutoff = date.today() - relativedelta(days=retention_days)

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT tablename FROM pg_tables
                WHERE tablename LIKE 'activity_logs_%%'
                AND schemaname = 'public'
                ORDER BY tablename;
            """)
            partitions = [row[0] for row in cursor.fetchall()]

        for partition in partitions:
            parts = partition.split('_')
            if len(parts) < 4:
                continue
            try:
                year, month = int(parts[-2]), int(parts[-1])
                partition_date = date(year, month, 1)
            except (ValueError, IndexError):
                continue

            if partition_date < cutoff.replace(day=1):
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP TABLE IF EXISTS {partition};')
                self.stdout.write(
                    self.style.SUCCESS(f'Dropped old partition: {partition}')
                )
