from django.core.management.base import BaseCommand
from integrations.tallysync.services.voucher_matching_service import VoucherBillingMatchingService


class Command(BaseCommand):
    help = 'Match Tally vouchers with ERP billings'

    def add_arguments(self, parser):
        parser.add_argument('--month', type=int, help='Month (1-12)')
        parser.add_argument('--year', type=int, help='Year (e.g., 2025)')
        parser.add_argument('--tolerance', type=int, default=5, help='Amount tolerance percentage (default 5%)')

    def handle(self, *args, **options):
        month = options.get('month')
        year = options.get('year')
        tolerance = options.get('tolerance')
        
        self.stdout.write(f"\n🔄 Starting voucher matching...")
        
        if month and year:
            self.stdout.write(f"   Filtering: {month}/{year}")
        else:
            self.stdout.write(f"   Processing: ALL vouchers")
        
        self.stdout.write(f"   Tolerance: ±{tolerance}%\n")
        
        # Run matching
        service = VoucherBillingMatchingService(tolerance_percentage=tolerance)
        results = service.match_all_vouchers(month=month, year=year)
        
        self.stdout.write(f"\n📊 MATCHING RESULTS")
        self.stdout.write(f"{'='*50}")
        self.stdout.write(f"   Total Processed:    {results['total_processed']}")
        self.stdout.write(self.style.SUCCESS(f"   ✅ Matched:         {results['matches_found']}"))
        self.stdout.write(self.style.WARNING(f"   ⚠️  Variances:       {results['variances_created']}"))
        
        # Get remaining unmatched summary
        summary = service.get_unmatched_summary()
        self.stdout.write(f"\n📋 UNMATCHED SUMMARY")
        self.stdout.write(f"{'='*50}")
        self.stdout.write(f"   Still Unmatched:    {summary['total_unmatched']}")
        self.stdout.write(f"   Total Amount:       ₹{summary['total_amount']:,.2f}")
        
        self.stdout.write(f"\n✅ Matching complete!\n")