"""
Full historical sync of all Tally vouchers, batched by month.

Usage:
    # Sync all companies from April 2023 to today
    python manage.py sync_tally_full_history

    # Sync specific company
    python manage.py sync_tally_full_history --company "Godamwale Trading & Logistics Pvt Ltd - MH"

    # Custom start date
    python manage.py sync_tally_full_history --from-date 2024-01-01
"""
from django.core.management.base import BaseCommand
from integrations.tallysync.models import TallyCompany
from integrations.tallysync.services.sync_service import TallySyncService
from integrations.tallysync.services.tally_connector_new import TallyConnectionError
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import time


MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds between retries
COMPANY_DELAY = 5  # seconds between companies


class Command(BaseCommand):
    help = 'Full historical sync of all vouchers from Tally, batched by month'

    def add_arguments(self, parser):
        parser.add_argument('--company', type=str, help='Specific company name (default: all active)')
        parser.add_argument('--from-date', type=str, default='2024-04-01',
                            help='Start date YYYY-MM-DD (default: 2024-04-01)')
        parser.add_argument('--to-date', type=str, help='End date YYYY-MM-DD (default: today)')
        parser.add_argument('--full-history', action='store_true',
                            help='Sync from 2023-04-01 (full 3-year history, slow)')

    def _sync_month_with_retry(self, service, company, from_str, to_str, month_label):
        """Sync a single month with retry logic for timeouts."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return service.sync_vouchers(
                    company, from_str, to_str,
                    triggered_by_user='full_history_sync'
                )
            except (TallyConnectionError, RuntimeError) as e:
                err_str = str(e)
                if 'timed out' in err_str.lower() or 'connection' in err_str.lower():
                    if attempt < MAX_RETRIES:
                        wait = RETRY_DELAY * attempt
                        self.stdout.write(self.style.WARNING(
                            f"  {month_label}: Timeout (attempt {attempt}/{MAX_RETRIES}), "
                            f"retrying in {wait}s..."
                        ))
                        time.sleep(wait)
                    else:
                        raise
                elif 'already running' in err_str.lower():
                    # Stale sync lock — clean up and retry once
                    from integrations.models import SyncLog
                    SyncLog.objects.filter(
                        integration='tallysync', log_kind='batch',
                        status='running', sub_type=company.name
                    ).update(status='stopped', error_message='Cleaned by full_history_sync retry')
                    if attempt < MAX_RETRIES:
                        self.stdout.write(self.style.WARNING(
                            f"  {month_label}: Cleared stale lock, retrying..."
                        ))
                        time.sleep(2)
                    else:
                        raise
                else:
                    raise

    def handle(self, *args, **options):
        service = TallySyncService()

        # Test connection
        self.stdout.write("Testing Tally connection...")
        conn = service.test_connection()
        if not conn['success']:
            self.stdout.write(self.style.ERROR(conn['message']))
            return
        self.stdout.write(self.style.SUCCESS(conn['message']))

        # Get companies
        if options['company']:
            companies = TallyCompany.objects.filter(name=options['company'], is_active=True)
            if not companies.exists():
                self.stdout.write(self.style.ERROR(f"Company not found: {options['company']}"))
                return
        else:
            companies = TallyCompany.objects.filter(is_active=True).order_by('name')

        from_date_str = '2023-04-01' if options['full_history'] else options['from_date']
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        to_date = datetime.strptime(options['to_date'], '%Y-%m-%d').date() if options['to_date'] else date.today()

        self.stdout.write(f"\nSyncing {companies.count()} companies from {from_date} to {to_date}")
        self.stdout.write("=" * 60)

        grand_total = {'created': 0, 'updated': 0, 'failed': 0, 'skipped_months': 0}
        start_all = time.time()

        for idx, company in enumerate(companies):
            state = company.name.split('-')[-1].strip()
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(self.style.HTTP_INFO(f"Company: {company.name}"))

            # Small delay between companies to avoid overwhelming Tally
            if idx > 0:
                time.sleep(COMPANY_DELAY)

            company_total = {'created': 0, 'updated': 0, 'failed': 0}
            month_start = date(from_date.year, from_date.month, 1)

            while month_start <= to_date:
                month_end = month_start + relativedelta(months=1) - relativedelta(days=1)
                if month_end > to_date:
                    month_end = to_date

                from_str = month_start.strftime('%Y%m%d')
                to_str = month_end.strftime('%Y%m%d')
                month_label = month_start.strftime('%Y-%m')

                try:
                    result = self._sync_month_with_retry(
                        service, company, from_str, to_str, month_label
                    )

                    c = result.get('created', 0)
                    u = result.get('updated', 0)
                    f = result.get('failed', 0)
                    p = result.get('processed', 0)

                    company_total['created'] += c
                    company_total['updated'] += u
                    company_total['failed'] += f

                    verify = result.get('verify', {})
                    gap = verify.get('gap', 0)
                    healed = verify.get('healed', False)

                    if p > 0 or gap > 0:
                        verify_str = ''
                        if gap > 0:
                            verify_str = self.style.ERROR(f' ⚠ gap={gap} remaining')
                        elif healed:
                            verify_str = self.style.SUCCESS(f' ✓ healed')
                        elif verify.get('tally_count', -1) >= 0:
                            verify_str = f' ✓ verified'
                        self.stdout.write(
                            f"  {month_label}: {p} vouchers ({c} new, {u} updated, {f} failed){verify_str}"
                        )
                    else:
                        grand_total['skipped_months'] += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f"  {month_label}: ERROR - {e}"
                    ))
                    company_total['failed'] += 1

                month_start += relativedelta(months=1)

            self.stdout.write(self.style.SUCCESS(
                f"  {state} total: {company_total['created']} created, "
                f"{company_total['updated']} updated, {company_total['failed']} failed"
            ))

            grand_total['created'] += company_total['created']
            grand_total['updated'] += company_total['updated']
            grand_total['failed'] += company_total['failed']

        elapsed = time.time() - start_all
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS(
            f"DONE in {elapsed/60:.1f} minutes | "
            f"Created: {grand_total['created']}, Updated: {grand_total['updated']}, "
            f"Failed: {grand_total['failed']}, Empty months skipped: {grand_total['skipped_months']}"
        ))
