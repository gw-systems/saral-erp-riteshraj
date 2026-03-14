"""
Verify sync completeness by comparing Tally voucher counts vs DB counts per company per month.

Usage:
    python manage.py verify_sync                        # All companies, all time
    python manage.py verify_sync --from-date 2024-01-01
    python manage.py verify_sync --company "...MH"
    python manage.py verify_sync --gaps-only            # Only show months with missing data
    python manage.py verify_sync --resync-gaps          # Auto-resync any months with gaps
"""
from django.core.management.base import BaseCommand
from integrations.tallysync.models import TallyCompany, TallyVoucher
from integrations.tallysync.services.sync_service import TallySyncService
from integrations.tallysync.services.tally_connector_new import TallyConnector, TallyConnectionError
from django.db.models import Count
from datetime import date
from dateutil.relativedelta import relativedelta
from datetime import datetime
import time


class Command(BaseCommand):
    help = 'Verify sync completeness: Tally count vs DB count per company per month'

    def add_arguments(self, parser):
        parser.add_argument('--company', type=str, help='Specific company name (default: all active)')
        parser.add_argument('--from-date', type=str, default='2023-04-01', help='Start date YYYY-MM-DD')
        parser.add_argument('--to-date', type=str, help='End date YYYY-MM-DD (default: today)')
        parser.add_argument('--gaps-only', action='store_true', help='Only show months where DB < Tally')
        parser.add_argument('--resync-gaps', action='store_true', help='Automatically resync months with gaps')

    def handle(self, *args, **options):
        connector = TallyConnector()
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

        from_date = datetime.strptime(options['from_date'], '%Y-%m-%d').date()
        to_date = datetime.strptime(options['to_date'], '%Y-%m-%d').date() if options['to_date'] else date.today()
        gaps_only = options['gaps_only']
        resync_gaps = options['resync_gaps']

        self.stdout.write(f"\nVerifying {companies.count()} companies from {from_date} to {to_date}")
        if resync_gaps:
            self.stdout.write(self.style.WARNING("Auto-resync mode ON — will resync any gaps found"))
        self.stdout.write("=" * 70)

        grand_gaps = []
        grand_ok = 0
        grand_errors = 0

        for company in companies:
            state = company.name.split('-')[-1].strip()
            self.stdout.write(f"\n{'='*70}")
            self.stdout.write(self.style.HTTP_INFO(f"Company: {company.name}"))

            month_start = date(from_date.year, from_date.month, 1)
            company_gaps = 0

            while month_start <= to_date:
                month_end = month_start + relativedelta(months=1) - relativedelta(days=1)
                if month_end > to_date:
                    month_end = to_date

                from_str = month_start.strftime('%Y%m%d')
                to_str = month_end.strftime('%Y%m%d')
                label = month_start.strftime('%Y-%m')

                # DB count for this month
                db_count = TallyVoucher.objects.filter(
                    company=company,
                    date__gte=month_start,
                    date__lte=month_end,
                ).count()

                # Tally count
                try:
                    tally_count = connector.fetch_voucher_count(company.name, from_str, to_str)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  {label}: ERROR fetching from Tally — {e}"))
                    grand_errors += 1
                    month_start += relativedelta(months=1)
                    continue

                if tally_count < 0:
                    self.stdout.write(self.style.ERROR(f"  {label}: Tally parse error"))
                    grand_errors += 1
                    month_start += relativedelta(months=1)
                    continue

                diff = tally_count - db_count

                if diff > 0:
                    # Gap — Tally has more than DB
                    company_gaps += diff
                    grand_gaps.append({'company': company.name, 'month': label, 'tally': tally_count, 'db': db_count, 'missing': diff})
                    self.stdout.write(self.style.ERROR(
                        f"  {label}: Tally={tally_count:4}  DB={db_count:4}  GAP={diff:4} MISSING"
                    ))
                    if resync_gaps:
                        self.stdout.write(f"    → Resyncing {label}...")
                        try:
                            result = service.sync_vouchers(company, from_str, to_str, triggered_by_user='verify_sync_resync')
                            self.stdout.write(self.style.SUCCESS(
                                f"    ✓ Resynced: {result.get('created',0)} created, {result.get('updated',0)} updated"
                            ))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"    ✗ Resync failed: {e}"))
                elif diff < 0:
                    # DB has more than Tally (cancelled/deleted in Tally?)
                    grand_gaps.append({'company': company.name, 'month': label, 'tally': tally_count, 'db': db_count, 'missing': diff})
                    self.stdout.write(self.style.WARNING(
                        f"  {label}: Tally={tally_count:4}  DB={db_count:4}  EXTRA={-diff:4} in DB (deleted in Tally?)"
                    ))
                else:
                    grand_ok += 1
                    if not gaps_only and tally_count > 0:
                        self.stdout.write(f"  {label}: Tally={tally_count:4}  DB={db_count:4}  ✓")

                time.sleep(0.3)  # be gentle on Tally
                month_start += relativedelta(months=1)

            if company_gaps:
                self.stdout.write(self.style.ERROR(f"  {state}: {company_gaps} missing vouchers across gaps"))
            else:
                self.stdout.write(self.style.SUCCESS(f"  {state}: All months match ✓"))

        # Summary
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(self.style.SUCCESS(f"Months matched: {grand_ok}"))
        if grand_errors:
            self.stdout.write(self.style.ERROR(f"Errors: {grand_errors}"))
        if grand_gaps:
            total_missing = sum(g['missing'] for g in grand_gaps if g['missing'] > 0)
            self.stdout.write(self.style.ERROR(f"\nGAPS FOUND — {total_missing} missing vouchers across {len([g for g in grand_gaps if g['missing'] > 0])} months:"))
            for g in grand_gaps:
                if g['missing'] > 0:
                    co = g['company'][-10:]
                    self.stdout.write(self.style.ERROR(
                        f"  {co:10}  {g['month']}  Tally={g['tally']}  DB={g['db']}  missing={g['missing']}"
                    ))
            if not resync_gaps:
                self.stdout.write(f"\nRun with --resync-gaps to automatically fix these gaps.")
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ All data matches — sync is complete!"))
