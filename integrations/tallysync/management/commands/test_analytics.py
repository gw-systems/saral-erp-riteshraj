from django.core.management.base import BaseCommand
from integrations.tallysync.services.financial_analytics_service import FinancialAnalyticsService
from integrations.tallysync.services.project_analytics_service import ProjectAnalyticsService
from integrations.tallysync.services.cash_flow_service import CashFlowService
from integrations.tallysync.services.gst_service import GSTService
from integrations.tallysync.services.salesperson_analytics_service import SalespersonAnalyticsService
from integrations.tallysync.services.area_efficiency_service import AreaEfficiencyService
from integrations.tallysync.services.ledger_analytics_service import LedgerAnalyticsService


class Command(BaseCommand):
    help = 'Test all analytics services'

    def handle(self, *args, **options):
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('TESTING ALL ANALYTICS SERVICES'))
        self.stdout.write(self.style.SUCCESS('='*70))
        
        # Test Financial Analytics
        self.stdout.write(self.style.WARNING('\n📊 1. FINANCIAL ANALYTICS SERVICE'))
        self.stdout.write('-'*70)
        
        fin_service = FinancialAnalyticsService()
        exec_summary = fin_service.get_executive_summary()
        
        self.stdout.write(f"Revenue:          ₹{exec_summary['revenue']:,.2f}")
        self.stdout.write(f"Expenses:         ₹{exec_summary['expenses']:,.2f}")
        self.stdout.write(f"Net Profit:       ₹{exec_summary['net_profit']:,.2f}")
        self.stdout.write(f"Margin:           {exec_summary['margin_percentage']:.2f}%")
        self.stdout.write(f"Transactions:     {exec_summary['total_transactions']}")
        
        # Test Project Analytics
        self.stdout.write(self.style.WARNING('\n🏗️  2. PROJECT ANALYTICS SERVICE'))
        self.stdout.write('-'*70)
        
        proj_service = ProjectAnalyticsService()
        projects = proj_service.get_all_projects_summary()
        
        self.stdout.write(f"Total Projects with Data: {len(projects)}")
        
        if projects:
            self.stdout.write("\nTop 3 Projects by Revenue:")
            for p in projects[:3]:
                self.stdout.write(
                    f"  {p['code']}: ₹{p['tally_revenue']:,.2f} revenue, "
                    f"₹{p['tally_profit']:,.2f} profit ({p['tally_margin_pct']:.1f}%)"
                )
        
        # Test Cash Flow
        self.stdout.write(self.style.WARNING('\n💰 3. CASH FLOW SERVICE'))
        self.stdout.write('-'*70)
        
        cash_service = CashFlowService()
        cash_summary = cash_service.get_cash_summary()
        
        self.stdout.write(f"Cash Inflow:      ₹{cash_summary['cash_inflow']:,.2f}")
        self.stdout.write(f"Cash Outflow:     ₹{cash_summary['cash_outflow']:,.2f}")
        self.stdout.write(f"Net Cash Flow:    ₹{cash_summary['net_cash_flow']:,.2f}")
        self.stdout.write(f"Bank Balance:     ₹{cash_summary['bank_balance']:,.2f}")
        self.stdout.write(f"Cash in Hand:     ₹{cash_summary['cash_in_hand']:,.2f}")
        
        # Test GST
        self.stdout.write(self.style.WARNING('\n📋 4. GST SERVICE'))
        self.stdout.write('-'*70)
        
        gst_service = GSTService()
        gst_summary = gst_service.get_gst_summary()
        
        self.stdout.write(f"GST Collected:    ₹{gst_summary['gst_collected']['total']:,.2f}")
        self.stdout.write(f"GST Paid:         ₹{gst_summary['gst_paid']['total']:,.2f}")
        self.stdout.write(f"Net GST Liability: ₹{gst_summary['net_gst_liability']:,.2f}")
        self.stdout.write(f"ITC Available:    ₹{gst_summary['itc_available']:,.2f}")
        
        # Test Salesperson Analytics
        self.stdout.write(self.style.WARNING('\n👨‍💼 5. SALESPERSON ANALYTICS SERVICE'))
        self.stdout.write('-'*70)
        
        sp_service = SalespersonAnalyticsService()
        salespeople = sp_service.get_all_salesperson_summary()
        
        self.stdout.write(f"Total Salespeople: {len(salespeople)}")
        
        if salespeople:
            self.stdout.write("\nTop 3 Salespeople by Revenue:")
            for sp in salespeople[:3]:
                self.stdout.write(
                    f"  {sp['salesperson_name']}: {sp['project_count']} projects, "
                    f"₹{sp['total_revenue']:,.2f} revenue ({sp['profit_margin']:.1f}% margin)"
                )
        
        # Test Area Efficiency
        self.stdout.write(self.style.WARNING('\n📐 6. AREA EFFICIENCY SERVICE'))
        self.stdout.write('-'*70)
        
        area_service = AreaEfficiencyService()
        efficiency_data = area_service.get_all_projects_efficiency()
        
        self.stdout.write(f"Projects with Area Data: {len(efficiency_data)}")
        
        if efficiency_data:
            self.stdout.write("\nTop 3 Projects by Revenue/Sq.ft:")
            for proj in efficiency_data[:3]:
                self.stdout.write(
                    f"  {proj['code']}: ₹{proj['revenue_per_sqft']:.2f}/sqft, "
                    f"{proj['billable_area']:,.0f} {proj['space_type_display']}, "
                    f"Status: {proj['utilization_status']}"
                )
        
        # Test Ledger Analytics
        self.stdout.write(self.style.WARNING('\n📒 7. LEDGER ANALYTICS SERVICE'))
        self.stdout.write('-'*70)
        
        ledger_service = LedgerAnalyticsService()
        
        # TDS Summary
        tds_summary = ledger_service.get_tds_summary()
        self.stdout.write(f"Total TDS Deducted: ₹{tds_summary['total_tds_deducted']:,.2f}")
        self.stdout.write(f"TDS Transactions:   {tds_summary['total_transactions']}")
        
        # Bank Summary
        bank_summary = ledger_service.get_bank_transactions_summary()
        self.stdout.write(f"Banks Tracked:      {bank_summary['summary']['bank_count']}")
        self.stdout.write(f"Total Bank Debit:   ₹{bank_summary['summary']['total_debit']:,.2f}")
        self.stdout.write(f"Total Bank Credit:  ₹{bank_summary['summary']['total_credit']:,.2f}")
        
        # Vendor Summary
        vendor_summary = ledger_service.get_vendor_expense_summary()
        self.stdout.write(f"Total Vendors:      {vendor_summary['summary']['total_vendors']}")
        self.stdout.write(f"Total Purchases:    ₹{vendor_summary['summary']['total_purchases']:,.2f}")
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('✅ ALL 7 ANALYTICS SERVICES TESTED SUCCESSFULLY'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))