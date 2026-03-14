from django.db.models import Q, Sum, Count
from integrations.tallysync.models import TallyVoucher, VarianceAlert
from operations.models import MonthlyBilling
from decimal import Decimal


class VoucherBillingMatchingService:
    """Service to match Tally vouchers with ERP billings"""
    
    def __init__(self, tolerance_percentage=5):
        self.tolerance_percentage = tolerance_percentage
        self.matches_found = 0
        self.variances_created = 0
    
    def match_all_vouchers(self, month=None, year=None):
        """Match all unmatched vouchers to ERP billings"""
        
        # Get unmatched sales vouchers with cost centre allocations
        vouchers = TallyVoucher.objects.filter(
            voucher_type='Sales',
            erp_monthly_billing__isnull=True,
            erp_adhoc_billing__isnull=True,
            ledger_entries__cost_allocations__cost_centre__erp_project__isnull=False
        ).distinct().prefetch_related('ledger_entries__cost_allocations__cost_centre__erp_project')
        
        # Apply date filter
        if month and year:
            vouchers = vouchers.filter(date__year=year, date__month=month)
        
        for voucher in vouchers:
            self._match_voucher(voucher)
        
        return {
            'matches_found': self.matches_found,
            'variances_created': self.variances_created,
            'total_processed': vouchers.count()
        }
    
    def _match_voucher(self, voucher):
        """Match a single voucher to ERP billing"""
        
        # Get cost centre allocation from ledger entries
        allocation = None
        for ledger_entry in voucher.ledger_entries.all():
            allocation = ledger_entry.cost_allocations.first()
            if allocation:
                break
        if not allocation or not allocation.cost_centre or not allocation.cost_centre.erp_project:
            self._create_alert(voucher, 'no_project_link')
            return
        
        erp_project = allocation.cost_centre.erp_project
        billing_month = voucher.date.replace(day=1)
        
        # Find ERP billing for same project and month
        billing = MonthlyBilling.objects.filter(
            project=erp_project,
            billing_month=billing_month
        ).first()
        
        if not billing:
            self._create_alert(voucher, 'missing_erp_billing', erp_project=erp_project)
            return
        
        # Check amount match
        if billing.client_total == 0 and voucher.amount == 0:
            # Both zero - match
            voucher.erp_monthly_billing = billing
            voucher.save()
            self.matches_found += 1
            return
        
        if billing.client_total > 0:
            variance_pct = abs(billing.client_total - voucher.amount) / billing.client_total * 100
        else:
            variance_pct = 100
        
        if variance_pct <= self.tolerance_percentage:
            # Within tolerance - auto match
            voucher.erp_monthly_billing = billing
            voucher.save()
            self.matches_found += 1
        else:
            # Amount mismatch - create variance alert
            self._create_variance_alert(voucher, billing, variance_pct)
    
    def _create_alert(self, voucher, alert_type, erp_project=None):
        """Create alert for unmatched voucher"""
        
        descriptions = {
            'no_project_link': f'Voucher {voucher.voucher_number or voucher.guid[:8]} has no linked ERP project',
            'missing_erp_billing': f'No ERP billing found for {erp_project.project_code if erp_project else "project"} in {voucher.date.strftime("%b %Y")}'
        }
        
        alert, created = VarianceAlert.objects.get_or_create(
            alert_type='missing_in_erp',
            tally_voucher=voucher,
            defaults={
                'severity': 'medium',
                'tally_amount': voucher.amount,
                'variance_amount': voucher.amount,
                'description': descriptions.get(alert_type, 'Unknown issue')
            }
        )
        
        if created:
            self.variances_created += 1
    
    def _create_variance_alert(self, voucher, billing, variance_pct):
        """Create alert for amount mismatch"""
        
        variance_amount = abs(billing.client_total - voucher.amount)
        
        alert, created = VarianceAlert.objects.get_or_create(
            alert_type='amount_mismatch',
            tally_voucher=voucher,
            erp_monthly_billing=billing,
            defaults={
                'severity': 'high' if variance_pct > 10 else 'medium',
                'tally_amount': voucher.amount,
                'erp_amount': billing.client_total,
                'variance_amount': variance_amount,
                'variance_percentage': variance_pct,
                'description': f'Amount mismatch for {voucher.voucher_number or "voucher"}: Tally ₹{voucher.amount:,.2f} vs ERP ₹{billing.client_total:,.2f} ({variance_pct:.1f}% difference)'
            }
        )
        
        if created:
            self.variances_created += 1
    
    def get_unmatched_summary(self):
        """Get summary of unmatched vouchers"""
        
        unmatched = TallyVoucher.objects.filter(
            voucher_type='Sales',
            erp_monthly_billing__isnull=True,
            erp_adhoc_billing__isnull=True
        )
        
        return {
            'total_unmatched': unmatched.count(),
            'total_amount': unmatched.aggregate(total=Sum('amount'))['total'] or 0,
            'by_company': list(unmatched.values('company__name').annotate(
                count=Count('id'),
                total=Sum('amount')
            ))
        }