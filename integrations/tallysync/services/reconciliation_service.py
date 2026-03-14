from django.db.models import Sum, Q, F
from integrations.tallysync.models import TallyVoucher, TallyCostCentre, VarianceAlert
from operations.models import MonthlyBilling, AdhocBillingEntry
from datetime import datetime
from decimal import Decimal


class ReconciliationService:
    """Service to reconcile ERP billing with Tally vouchers"""
    
    def __init__(self, month=None, year=None):
        """Initialize with optional month/year filter"""
        if month and year:
            self.start_date = datetime(year, month, 1).date()
            if month == 12:
                self.end_date = datetime(year + 1, 1, 1).date()
            else:
                self.end_date = datetime(year, month + 1, 1).date()
        else:
            self.start_date = None
            self.end_date = None
    
    def get_reconciliation_summary(self):
        """Get high-level reconciliation summary"""
        
        # Get ERP totals
        erp_query = MonthlyBilling.objects.all()
        if self.start_date:
            erp_query = erp_query.filter(
                billing_month__gte=self.start_date,
                billing_month__lt=self.end_date
            )
        
        erp_total = erp_query.aggregate(
            total=Sum('client_total') 
        )['total'] or Decimal('0')
        
        # Get Tally totals (Sales vouchers only)
        tally_query = TallyVoucher.objects.filter(voucher_type='Sales').exclude(is_cancelled=True)
        if self.start_date:
            tally_query = tally_query.filter(
                date__gte=self.start_date,
                date__lt=self.end_date
            )
        
        tally_total = tally_query.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        # Calculate variance
        variance = abs(erp_total - tally_total)
        variance_pct = (variance / erp_total * 100) if erp_total > 0 else 0
        
        # Get matched/unmatched counts
        matched_erp = erp_query.filter(
            tally_vouchers__isnull=False
        ).distinct().count()
        
        unmatched_erp = erp_query.filter(
            tally_vouchers__isnull=True
        ).count()
        
        matched_tally = tally_query.filter(
            erp_monthly_billing__isnull=False
        ).count()
        
        unmatched_tally = tally_query.filter(
            erp_monthly_billing__isnull=True,
            erp_adhoc_billing__isnull=True
        ).count()
        
        return {
            'erp_total': erp_total,
            'tally_total': tally_total,
            'variance': variance,
            'variance_pct': variance_pct,
            'erp_count': erp_query.count(),
            'tally_count': tally_query.count(),
            'matched_erp': matched_erp,
            'unmatched_erp': unmatched_erp,
            'matched_tally': matched_tally,
            'unmatched_tally': unmatched_tally
        }
    
    def get_unmatched_erp_billings(self):
        """Get ERP billings without Tally vouchers"""
        query = MonthlyBilling.objects.filter(
            tally_vouchers__isnull=True
        )
        
        if self.start_date:
            query = query.filter(
                billing_month__gte=self.start_date,
                billing_month__lt=self.end_date
            )
        
        return query.select_related('project')
    
    def get_unmatched_tally_vouchers(self):
        """Get Tally vouchers without ERP billing"""
        query = TallyVoucher.objects.filter(
            voucher_type='Sales',
            erp_monthly_billing__isnull=True,
            erp_adhoc_billing__isnull=True
        ).exclude(is_cancelled=True)
        
        if self.start_date:
            query = query.filter(
                date__gte=self.start_date,
                date__lt=self.end_date
            )
        
        return query.select_related('company')
    
    def create_variance_alerts(self):
        """Scan for variances and create alerts"""
        alerts_created = 0
        
        # Alert for unmatched ERP billings
        for billing in self.get_unmatched_erp_billings():
            alert, created = VarianceAlert.objects.get_or_create(
                alert_type='missing_in_tally',
                erp_monthly_billing=billing,
                defaults={
                    'severity': 'high',
                    'erp_amount': billing.client_total,
                    'variance_amount': billing.client_total,
                    'description': f'ERP billing for {billing.project.project_code} not found in Tally' 
                }
            )
            if created:
                alerts_created += 1
        
        # Alert for unmatched Tally vouchers
        for voucher in self.get_unmatched_tally_vouchers():
            alert, created = VarianceAlert.objects.get_or_create(
                alert_type='missing_in_erp',
                tally_voucher=voucher,
                defaults={
                    'severity': 'medium',
                    'tally_amount': voucher.amount,
                    'variance_amount': voucher.amount,
                    'description': f'Tally voucher {voucher.voucher_number} not found in ERP'
                }
            )
            if created:
                alerts_created += 1
        
        return alerts_created