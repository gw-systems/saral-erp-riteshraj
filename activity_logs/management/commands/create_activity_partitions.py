from django.core.management.base import BaseCommand
from django.db import connection
from datetime import date
from dateutil.relativedelta import relativedelta


class Command(BaseCommand):
    help = 'Create monthly PostgreSQL partitions for activity_logs table'

    def add_arguments(self, parser):
        parser.add_argument('--months', type=int, default=3,
                            help='Number of future months to create partitions for')

    def handle(self, *args, **options):
        months_ahead = options['months']
        today = date.today()

        with connection.cursor() as cursor:
            for i in range(months_ahead):
                target = today + relativedelta(months=i)
                start = target.replace(day=1)
                end = start + relativedelta(months=1)

                partition_name = f"activity_logs_{start.strftime('%Y_%m')}"
                start_str = start.strftime('%Y-%m-%d')
                end_str = end.strftime('%Y-%m-%d')

                sql = f"""
                    CREATE TABLE IF NOT EXISTS {partition_name}
                    PARTITION OF activity_logs
                    FOR VALUES FROM ('{start_str} 00:00:00+00') TO ('{end_str} 00:00:00+00');
                """
                try:
                    cursor.execute(sql)
                    self.stdout.write(
                        self.style.SUCCESS(f'Created partition: {partition_name}')
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'Partition {partition_name} may already exist: {e}')
                    )
