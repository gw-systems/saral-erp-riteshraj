from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce, TruncMonth
from integrations.tallysync.models import TallyVoucher, TallyVoucherLedgerEntry
from datetime import datetime, timedelta
from decimal import Decimal


class CashFlowService:
    """Service for cash flow analysis and liquidity tracking"""
    
    def __init__(self, start_date=None, end_date=None, company_id=None):
        self.start_date = start_date
        self.end_date = end_date
        self.company_id = company_id
    
    def get_cash_summary(self):
        """Get current cash position summary"""
        
        vouchers = self._get_base_queryset()
        
        # Cash inflows (Sales accruals + Receipts only; CN are balance-sheet adjustments, not cash)
        cash_inflow = vouchers.filter(
            voucher_type__in=['Sales', 'Receipt']
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']

        # Cash outflows (Purchase accruals + Payments only; DN are balance-sheet adjustments, not cash)
        cash_outflow = vouchers.filter(
            voucher_type__in=['Purchase', 'Payment']
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        
        # Net cash flow
        net_cash_flow = cash_inflow - cash_outflow
        
        # Get bank balances from ledger entries
        bank_balance = self._get_bank_balances()
        cash_in_hand = self._get_cash_in_hand()
        
        total_liquidity = bank_balance + cash_in_hand
        
        return {
            'cash_inflow': cash_inflow,
            'cash_outflow': cash_outflow,
            'net_cash_flow': net_cash_flow,
            'bank_balance': bank_balance,
            'cash_in_hand': cash_in_hand,
            'total_liquidity': total_liquidity,
            'burn_rate': self._calculate_burn_rate()
        }
    
    def get_cash_flow_trend(self, months=6):
        """Get monthly cash flow trend"""
        
        vouchers = self._get_base_queryset()
        
        # Get monthly data
        monthly_data = vouchers.annotate(
            month=TruncMonth('billing_month_date')
        ).values('month').annotate(
            inflow=Coalesce(
                Sum('amount', filter=Q(voucher_type__in=['Sales', 'Receipt'])),
                Decimal('0'),
                output_field=DecimalField()
            ),
            outflow=Coalesce(
                Sum('amount', filter=Q(voucher_type__in=['Purchase', 'Payment'])),
                Decimal('0'),
                output_field=DecimalField()
            )
        ).order_by('month')
        
        result = []
        cumulative = Decimal('0')
        
        for data in monthly_data:
            net_flow = data['inflow'] - data['outflow']
            cumulative += net_flow
            
            result.append({
                'month': data['month'],
                'inflow': data['inflow'],
                'outflow': data['outflow'],
                'net_flow': net_flow,
                'cumulative_flow': cumulative
            })
        
        return result
    
    def get_receivables_summary(self):
        """Get accounts receivable summary"""
        
        # Get all sales vouchers
        sales_vouchers = TallyVoucher.objects.filter(
            voucher_type='Sales'
        ).exclude(is_cancelled=True)
        
        if self.company_id:
            sales_vouchers = sales_vouchers.filter(company_id=self.company_id)
        
        # Apply date filters if provided
        if self.start_date:
            sales_vouchers = sales_vouchers.filter(
                Q(billing_month_date__gte=self.start_date) |
                Q(billing_month_date__isnull=True, date__gte=self.start_date)
            )
        if self.end_date:
            sales_vouchers = sales_vouchers.filter(
                Q(billing_month_date__lte=self.end_date) |
                Q(billing_month_date__isnull=True, date__lte=self.end_date)
            )
        
        # Total billed
        total_billed = sales_vouchers.aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        
        # Get receipts
        receipts = TallyVoucher.objects.filter(
            voucher_type='Receipt'
        ).exclude(is_cancelled=True)
        
        if self.company_id:
            receipts = receipts.filter(company_id=self.company_id)
        
        # Apply same date filters to receipts
        if self.start_date:
            receipts = receipts.filter(
                Q(billing_month_date__gte=self.start_date) |
                Q(billing_month_date__isnull=True, date__gte=self.start_date)
            )
        if self.end_date:
            receipts = receipts.filter(
                Q(billing_month_date__lte=self.end_date) |
                Q(billing_month_date__isnull=True, date__lte=self.end_date)
            )
        
        total_received = receipts.aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        
        # Outstanding receivables
        outstanding = total_billed - total_received
        
        # Aging analysis — single query with conditional aggregation
        current_date = datetime.now().date()
        d30 = current_date - timedelta(days=30)
        d60 = current_date - timedelta(days=60)
        d90 = current_date - timedelta(days=90)

        aging = sales_vouchers.aggregate(
            aging_0_30=Coalesce(
                Sum('amount', filter=Q(billing_month_date__gte=d30)),
                Decimal('0'), output_field=DecimalField()
            ),
            aging_31_60=Coalesce(
                Sum('amount', filter=Q(billing_month_date__gte=d60, billing_month_date__lt=d30)),
                Decimal('0'), output_field=DecimalField()
            ),
            aging_61_90=Coalesce(
                Sum('amount', filter=Q(billing_month_date__gte=d90, billing_month_date__lt=d60)),
                Decimal('0'), output_field=DecimalField()
            ),
            aging_90_plus=Coalesce(
                Sum('amount', filter=Q(billing_month_date__lt=d90)),
                Decimal('0'), output_field=DecimalField()
            ),
        )
        
        return {
            'total_billed': total_billed,
            'total_received': total_received,
            'outstanding': outstanding,
            'aging': {
                '0_30_days': aging['aging_0_30'],
                '31_60_days': aging['aging_31_60'],
                '61_90_days': aging['aging_61_90'],
                '90_plus_days': aging['aging_90_plus'],
            }
        }

    def get_payables_summary(self):
        """Get accounts payable summary"""
        
        # Get all purchase vouchers
        purchase_vouchers = TallyVoucher.objects.filter(
            voucher_type='Purchase'
        ).exclude(is_cancelled=True)
        
        if self.company_id:
            purchase_vouchers = purchase_vouchers.filter(company_id=self.company_id)

        
        # Apply date filters if provided
        if self.start_date:
            purchase_vouchers = purchase_vouchers.filter(
                Q(billing_month_date__gte=self.start_date) |
                Q(billing_month_date__isnull=True, date__gte=self.start_date)
            )
        if self.end_date:
            purchase_vouchers = purchase_vouchers.filter(
                Q(billing_month_date__lte=self.end_date) |
                Q(billing_month_date__isnull=True, date__lte=self.end_date)
            )
        
        # Total purchases
        total_purchases = purchase_vouchers.aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        
        # Get payments
        payments = TallyVoucher.objects.filter(
            voucher_type='Payment'
        ).exclude(is_cancelled=True)
        
        if self.company_id:
            payments = payments.filter(company_id=self.company_id)

        # Apply same date filters to payments
        if self.start_date:
            payments = payments.filter(
                Q(billing_month_date__gte=self.start_date) |
                Q(billing_month_date__isnull=True, date__gte=self.start_date)
            )
        if self.end_date:
            payments = payments.filter(
                Q(billing_month_date__lte=self.end_date) |
                Q(billing_month_date__isnull=True, date__lte=self.end_date)
            )
        
        total_paid = payments.aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        
        # Outstanding payables
        outstanding = total_purchases - total_paid
        
        # Aging analysis — single query with conditional aggregation
        current_date = datetime.now().date()
        d30 = current_date - timedelta(days=30)
        d60 = current_date - timedelta(days=60)
        d90 = current_date - timedelta(days=90)

        aging = purchase_vouchers.aggregate(
            aging_0_30=Coalesce(
                Sum('amount', filter=Q(billing_month_date__gte=d30)),
                Decimal('0'), output_field=DecimalField()
            ),
            aging_31_60=Coalesce(
                Sum('amount', filter=Q(billing_month_date__gte=d60, billing_month_date__lt=d30)),
                Decimal('0'), output_field=DecimalField()
            ),
            aging_61_90=Coalesce(
                Sum('amount', filter=Q(billing_month_date__gte=d90, billing_month_date__lt=d60)),
                Decimal('0'), output_field=DecimalField()
            ),
            aging_90_plus=Coalesce(
                Sum('amount', filter=Q(billing_month_date__lt=d90)),
                Decimal('0'), output_field=DecimalField()
            ),
        )

        return {
            'total_purchases': total_purchases,
            'total_paid': total_paid,
            'outstanding': outstanding,
            'aging': {
                '0_30_days': aging['aging_0_30'],
                '31_60_days': aging['aging_31_60'],
                '61_90_days': aging['aging_61_90'],
                '90_plus_days': aging['aging_90_plus'],
            }
        }
    
    def _get_bank_balances(self):
        """Get total bank balances from ledger entries"""
        
        # This is simplified - in real Tally, bank ledgers have specific names
        # Would need to identify bank ledgers by group or pattern
        
        bank_ledgers = TallyVoucherLedgerEntry.objects.filter(
            ledger_name__icontains='bank'
        )
        
        if self.company_id:
            bank_ledgers = bank_ledgers.filter(voucher__company_id=self.company_id)
        
        # Sum debit minus credit (simplified)
        balance = bank_ledgers.aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        
        return abs(balance)  # Absolute value for display
    
    def _get_cash_in_hand(self):
        """Get cash in hand from ledger entries"""
        
        cash_ledgers = TallyVoucherLedgerEntry.objects.filter(
            Q(ledger_name__icontains='cash') | Q(ledger_name__icontains='petty cash')
        )
        
        if self.company_id:
            cash_ledgers = cash_ledgers.filter(voucher__company_id=self.company_id)
        
        balance = cash_ledgers.aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        
        return abs(balance)
    
    def _calculate_burn_rate(self):
        """Calculate monthly cash burn rate"""
        
        # Get last 3 months average outflow
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=90)
        
        outflow = TallyVoucher.objects.filter(
            voucher_type__in=['Purchase', 'Payment'],
            billing_month_date__gte=start_date,
            billing_month_date__lte=end_date
        ).exclude(is_cancelled=True)
        
        if self.company_id:
            outflow = outflow.filter(company_id=self.company_id)
        
        total_outflow = outflow.aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        
        # Monthly average
        monthly_burn = total_outflow / 3
        
        return monthly_burn
    
    def _get_base_queryset(self):
        """Get base queryset with filters"""

        queryset = TallyVoucher.objects.exclude(is_cancelled=True)

        if self.start_date:
            queryset = queryset.filter(
                Q(billing_month_date__gte=self.start_date) |
                Q(billing_month_date__isnull=True, date__gte=self.start_date)
            )
        if self.end_date:
            queryset = queryset.filter(
                Q(billing_month_date__lte=self.end_date) |
                Q(billing_month_date__isnull=True, date__lte=self.end_date)
            )

        if self.company_id:
            queryset = queryset.filter(company_id=self.company_id)

        return queryset