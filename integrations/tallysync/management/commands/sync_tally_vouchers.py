from django.core.management.base import BaseCommand
from integrations.tallysync.models import TallyCompany
from integrations.tallysync.services.sync_service import TallySyncService
from datetime import datetime, timedelta
import json


class Command(BaseCommand):
    help = 'Sync vouchers from Tally for a specific date range or incrementally'

    def add_arguments(self, parser):
        parser.add_argument('company_name', type=str, nargs='?', default=None,
                            help='Company name to sync (required unless --all)')
        parser.add_argument('--all', action='store_true', help='Sync all active companies')
        parser.add_argument('--incremental', action='store_true',
                            help='Incremental sync from last voucher date (7-day overlap)')
        parser.add_argument('--from-date', type=str, help='From date (YYYY-MM-DD)')
        parser.add_argument('--to-date', type=str, help='To date (YYYY-MM-DD)')
        parser.add_argument('--days', type=int, default=30, help='Number of days to sync (default: 30)')

    def handle(self, *args, **options):
        service = TallySyncService()

        # Test connection
        self.stdout.write("Testing Tally connection...")
        connection_result = service.test_connection()
        if not connection_result['success']:
            self.stdout.write(self.style.ERROR(connection_result['message']))
            return

        self.stdout.write(self.style.SUCCESS(connection_result['message']))

        # Get companies
        if options['all']:
            companies = TallyCompany.objects.filter(is_active=True).order_by('name')
        elif options['company_name']:
            try:
                companies = [TallyCompany.objects.get(name=options['company_name'])]
            except TallyCompany.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Company not found: {options['company_name']}"))
                return
        else:
            self.stdout.write(self.style.ERROR("Provide a company name or use --all"))
            return

        for company in companies:
            state = company.name.split('-')[-1].strip()

            if options['incremental']:
                self.stdout.write(f"\nIncremental sync: {state}")
                result = service.sync_vouchers_incremental(
                    company, triggered_by_user='management_command'
                )
            else:
                # Calculate date range
                if options['from_date'] and options['to_date']:
                    from_date = datetime.strptime(options['from_date'], '%Y-%m-%d')
                    to_date = datetime.strptime(options['to_date'], '%Y-%m-%d')
                else:
                    to_date = datetime.now()
                    from_date = to_date - timedelta(days=options['days'])

                from_str = from_date.strftime('%Y%m%d')
                to_str = to_date.strftime('%Y%m%d')

                self.stdout.write(f"\nSyncing {state}: {from_date.date()} to {to_date.date()}")
                result = service.sync_vouchers(
                    company, from_str, to_str, triggered_by_user='management_command'
                )

            if result['status'] in ['success', 'partial']:
                self.stdout.write(
                    f"  {result['processed']} vouchers "
                    f"({result['created']} new, {result['updated']} updated, "
                    f"{result.get('failed', 0)} failed)"
                )
            else:
                self.stdout.write(self.style.ERROR(f"  Error: {result.get('error')}"))

        self.stdout.write(self.style.SUCCESS('\nSync completed!'))
