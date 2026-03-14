from django.core.management.base import BaseCommand
from integrations.tallysync.services.reconciliation_service import ReconciliationService
from datetime import datetime


class Command(BaseCommand):
    help = 'Reconcile ERP billing with Tally vouchers'

    def add_arguments(self, parser):
        parser.add_argument('--month', type=int, help='Month (1-12)')
        parser.add_argument('--year', type=int, help='Year (e.g., 2025)')

    def handle(self, *args, **options):
        month = options.get('month')
        year = options.get('year')
        
        if month and year:
            self.stdout.write(f"\n🔍 Reconciling for {datetime(year, month, 1).strftime('%B %Y')}")
            service = ReconciliationService(month=month, year=year)
        else:
            self.stdout.write(f"\n🔍 Reconciling ALL data")
            service = ReconciliationService()
        
        # Get summary
        summary = service.get_reconciliation_summary()
        
        self.stdout.write(f"\n📊 RECONCILIATION SUMMARY")
        self.stdout.write(f"{'='*50}")
        
        self.stdout.write(f"\n💰 Amounts:")
        self.stdout.write(f"   ERP Total:        ₹{summary['erp_total']:,.2f}")
        self.stdout.write(f"   Tally Total:      ₹{summary['tally_total']:,.2f}")
        self.stdout.write(f"   Variance:         ₹{summary['variance']:,.2f} ({summary['variance_pct']:.1f}%)")
        
        self.stdout.write(f"\n📈 Counts:")
        self.stdout.write(f"   ERP Billings:     {summary['erp_count']}")
        self.stdout.write(f"   Tally Vouchers:   {summary['tally_count']}")
        
        self.stdout.write(f"\n✅ Matched:")
        self.stdout.write(f"   ERP Billings:     {summary['matched_erp']}")
        self.stdout.write(f"   Tally Vouchers:   {summary['matched_tally']}")
        
        self.stdout.write(f"\n⚠️  Unmatched:")
        self.stdout.write(self.style.WARNING(f"   ERP Billings:     {summary['unmatched_erp']}"))
        self.stdout.write(self.style.WARNING(f"   Tally Vouchers:   {summary['unmatched_tally']}"))
        
        # Show sample unmatched
        if summary['unmatched_erp'] > 0:
            self.stdout.write(f"\n❌ Sample Unmatched ERP Billings:")
            for billing in service.get_unmatched_erp_billings()[:5]:
                self.stdout.write(
                    f"   {billing.project.project_code} | " 
                    f"{billing.billing_month.strftime('%b %Y')} | "
                    f"₹{billing.client_total:,.2f}" 
                )
        
        if summary['unmatched_tally'] > 0:
            self.stdout.write(f"\n❌ Sample Unmatched Tally Vouchers:")
            for voucher in service.get_unmatched_tally_vouchers()[:5]:
                self.stdout.write(
                    f"   {voucher.voucher_number or '(no number)'} | "
                    f"{voucher.date} | "
                    f"₹{voucher.amount:,.2f}"
                )
        
        # Create variance alerts
        self.stdout.write(f"\n⚡ Creating variance alerts...")
        alerts = service.create_variance_alerts()
        self.stdout.write(self.style.SUCCESS(f"   Created {alerts} new alerts"))
        
        self.stdout.write(f"\n✅ Reconciliation complete!\n")