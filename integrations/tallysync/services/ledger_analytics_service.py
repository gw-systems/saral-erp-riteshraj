from django.db.models import Sum, Count, Q, Avg, F, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce
from integrations.tallysync.models import TallyVoucher, TallyVoucherLedgerEntry
from integrations.tallysync.services.gst_utils import net_alloc_amount
from datetime import datetime
from decimal import Decimal
from django.db.models.functions import TruncMonth


class LedgerAnalyticsService:
    """Service for detailed ledger-level analytics (TDS, Banks, Vendors)"""
    
    def __init__(self, start_date=None, end_date=None, company_id=None):
        self.start_date = start_date
        self.end_date = end_date
        self.company_id = company_id
    
    def get_tds_summary(self):
        """Get TDS deduction summary"""
        
        ledger_entries = self._get_base_ledger_entries()
        
        # Get TDS ledger entries
        tds_entries = ledger_entries.filter(
            Q(ledger_name__icontains='tds') | 
            Q(tds_amount__gt=0)
        ).select_related('voucher')
        
        # Group by TDS nature/section
        tds_by_section = tds_entries.values('tds_section', 'tds_nature_of_payment').annotate(
            total_tds=Coalesce(Sum('tds_amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        ).order_by('-total_tds')
        
        # Total TDS
        total_tds = tds_entries.aggregate(
            total=Coalesce(Sum('tds_amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        
        # Monthly TDS - use voucher__date instead of date
        from django.db.models.functions import TruncMonth

        monthly_tds = tds_entries.annotate(
            month=TruncMonth('voucher__billing_month_date')
        ).values('month').annotate(
            total=Coalesce(Sum('tds_amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        ).order_by('month')[:12]  # Limit to last 12 months
        
        return {
            'total_tds_deducted': total_tds,
            'total_transactions': tds_entries.count(),
            'by_section': list(tds_by_section),
            'monthly_trend': list(monthly_tds)
        }
    
    def get_bank_transactions_summary(self):
        """Get bank-wise transaction summary"""
        
        ledger_entries = self._get_base_ledger_entries()
        
        # Get bank ledgers (contains 'bank' in name)
        bank_entries = ledger_entries.filter(
            Q(ledger_name__icontains='bank') | 
            Q(ledger_name__icontains='hdfc') |
            Q(ledger_name__icontains='icici') |
            Q(ledger_name__icontains='axis') |
            Q(ledger_name__icontains='sbi')
        ).select_related('voucher')
        
        # Group by bank/ledger name
        by_bank = bank_entries.values('ledger_name').annotate(
            total_debit=Coalesce(
                Sum('amount', filter=Q(is_debit=True)),
                Decimal('0'),
                output_field=DecimalField()
            ),
            total_credit=Coalesce(
                Sum('amount', filter=Q(is_debit=False)),
                Decimal('0'),
                output_field=DecimalField()
            ),
            transaction_count=Count('id')
        ).order_by('-transaction_count')
        
        # Calculate net position for each bank
        result = []
        for bank in by_bank:
            net_position = abs(bank['total_debit']) - abs(bank['total_credit'])
            
            result.append({
                'bank_name': bank['ledger_name'],
                'total_debit': abs(bank['total_debit']),
                'total_credit': abs(bank['total_credit']),
                'net_position': net_position,
                'transaction_count': bank['transaction_count']
            })
        
        # Total across all banks
        total_debit = sum(b['total_debit'] for b in result)
        total_credit = sum(b['total_credit'] for b in result)
        
        return {
            'banks': result,
            'summary': {
                'total_debit': total_debit,
                'total_credit': total_credit,
                'net_position': total_debit - total_credit,
                'bank_count': len(result)
            }
        }
    
    def get_vendor_expense_summary(self):
        """Get vendor-wise expense summary.
        Vendor list = ProjectCode.vendor_name (ERP warehouse operators).
        Both Purchase and Revenue come from CC allocations on projects for each vendor.
        """
        from integrations.tallysync.models import TallyVoucherCostCentreAllocation

        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']

        alloc_base = TallyVoucherCostCentreAllocation.objects.filter(
            cost_centre__erp_project__isnull=False,
            cost_centre__erp_project__vendor_name__isnull=False,
        ).exclude(
            cost_centre__erp_project__vendor_name=''
        ).exclude(
            ledger_entry__voucher__is_cancelled=True
        )

        if self.start_date:
            alloc_base = alloc_base.filter(
                Q(ledger_entry__voucher__billing_month_date__gte=self.start_date) |
                Q(ledger_entry__voucher__billing_month_date__isnull=True,
                  ledger_entry__voucher__date__gte=self.start_date)
            )
        if self.end_date:
            alloc_base = alloc_base.filter(
                Q(ledger_entry__voucher__billing_month_date__lte=self.end_date) |
                Q(ledger_entry__voucher__billing_month_date__isnull=True,
                  ledger_entry__voucher__date__lte=self.end_date)
            )

        if self.company_id:
            alloc_base = alloc_base.filter(ledger_entry__voucher__company_id=self.company_id)

        net_amount = net_alloc_amount()
        summary_qs = alloc_base.values(
            'cost_centre__erp_project__vendor_name'
        ).annotate(
            gross_sales=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Sales')),
                Decimal('0'), output_field=DecimalField()
            ),
            credit_notes=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Credit Note')),
                Decimal('0'), output_field=DecimalField()
            ),
            gross_purchase=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type__in=PURCHASE_TYPES)),
                Decimal('0'), output_field=DecimalField()
            ),
            debit_notes=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Debit Note')),
                Decimal('0'), output_field=DecimalField()
            ),
            voucher_count=Count('ledger_entry__voucher', distinct=True),
        )

        result = []
        for row in summary_qs:
            name = row['cost_centre__erp_project__vendor_name']
            if not name:
                continue
            net_purchase = row['gross_purchase'] - row['debit_notes']
            net_revenue = row['gross_sales'] - row['credit_notes']
            result.append({
                'vendor_name': name,
                'total_purchases': net_purchase,
                'total_revenue': net_revenue,
                'transaction_count': row['voucher_count'],
                'avg_transaction_value': net_purchase / row['voucher_count'] if row['voucher_count'] > 0 else Decimal('0')
            })

        result.sort(key=lambda v: v['total_purchases'], reverse=True)

        top_vendors = result[:10]
        total_purchases = sum(v['total_purchases'] for v in result)
        total_revenue = sum(v['total_revenue'] for v in result)

        return {
            'top_vendors': top_vendors,
            'all_vendors': result,
            'summary': {
                'total_vendors': len(result),
                'total_purchases': total_purchases,
                'total_revenue': total_revenue,
                'avg_per_vendor': total_purchases / len(result) if len(result) > 0 else Decimal('0')
            }
        }
    
    def get_vendor_detail(self, vendor_name):
        """Get project-wise breakdown for a single vendor.
        Both Purchase and Revenue come from CC allocations on projects where
        ProjectCode.vendor_name = vendor_name. No party_ledger_name matching.
        """
        from integrations.tallysync.models import TallyVoucherCostCentreAllocation

        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']

        alloc_base = TallyVoucherCostCentreAllocation.objects.filter(
            cost_centre__erp_project__vendor_name=vendor_name,
            cost_centre__erp_project__isnull=False,
        ).exclude(ledger_entry__voucher__is_cancelled=True)

        if self.start_date:
            alloc_base = alloc_base.filter(
                Q(ledger_entry__voucher__billing_month_date__gte=self.start_date) |
                Q(ledger_entry__voucher__billing_month_date__isnull=True,
                  ledger_entry__voucher__date__gte=self.start_date)
            )
        if self.end_date:
            alloc_base = alloc_base.filter(
                Q(ledger_entry__voucher__billing_month_date__lte=self.end_date) |
                Q(ledger_entry__voucher__billing_month_date__isnull=True,
                  ledger_entry__voucher__date__lte=self.end_date)
            )

        if self.company_id:
            alloc_base = alloc_base.filter(ledger_entry__voucher__company_id=self.company_id)

        net_amount = net_alloc_amount()
        project_qs = alloc_base.values(
            'cost_centre__erp_project__project_id',
            'cost_centre__erp_project__project_code',
            'cost_centre__erp_project__code',
            'cost_centre__erp_project__client_name',
        ).annotate(
            gross_revenue=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Sales')),
                Decimal('0'), output_field=DecimalField()
            ),
            credit_notes=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Credit Note')),
                Decimal('0'), output_field=DecimalField()
            ),
            gross_purchase=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type__in=PURCHASE_TYPES)),
                Decimal('0'), output_field=DecimalField()
            ),
            debit_notes=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Debit Note')),
                Decimal('0'), output_field=DecimalField()
            ),
        )

        projects = []
        total_purchase = Decimal('0')
        total_revenue = Decimal('0')

        for row in project_qs:
            pid = row['cost_centre__erp_project__project_id']
            net_revenue = row['gross_revenue'] - row['credit_notes']
            net_purchase = row['gross_purchase'] - row['debit_notes']
            profit = net_revenue - net_purchase

            projects.append({
                'project_id': pid,
                'project_code': row['cost_centre__erp_project__project_code'] or '',
                'code': row['cost_centre__erp_project__code'] or '',
                'client_name': row['cost_centre__erp_project__client_name'] or '',
                'purchase': net_purchase,
                'revenue': net_revenue,
                'profit': profit,
                'margin': float(profit / net_revenue * 100) if net_revenue > 0 else 0.0,
            })
            total_purchase += net_purchase
            total_revenue += net_revenue

        projects.sort(key=lambda x: x['revenue'], reverse=True)

        # --- All vouchers on this vendor's projects (purchase + sales for context) ---
        project_ids = [p['project_id'] for p in projects]
        voucher_allocs = alloc_base.filter(
            cost_centre__erp_project__project_id__in=project_ids
        ).select_related('ledger_entry__voucher', 'ledger_entry__voucher__company').order_by(
            '-ledger_entry__voucher__date'
        ).values(
            'ledger_entry__voucher__id',
            'ledger_entry__voucher__date',
            'ledger_entry__voucher__billing_month_date',
            'ledger_entry__voucher__voucher_type',
            'ledger_entry__voucher__voucher_number',
            'ledger_entry__voucher__party_ledger_name',
            'ledger_entry__voucher__narration',
            'ledger_entry__voucher__amount',
            'ledger_entry__voucher__company__name',
        ).distinct()[:200]

        vouchers = []
        seen_ids = set()
        for v in voucher_allocs:
            vid = v['ledger_entry__voucher__id']
            if vid in seen_ids:
                continue
            seen_ids.add(vid)
            vouchers.append({
                'id': vid,
                'date': str(v['ledger_entry__voucher__date']) if v['ledger_entry__voucher__date'] else None,
                'billing_month': str(v['ledger_entry__voucher__billing_month_date']) if v['ledger_entry__voucher__billing_month_date'] else None,
                'voucher_type': v['ledger_entry__voucher__voucher_type'],
                'voucher_number': v['ledger_entry__voucher__voucher_number'],
                'party_name': v['ledger_entry__voucher__party_ledger_name'],
                'narration': v['ledger_entry__voucher__narration'] or '',
                'amount': v['ledger_entry__voucher__amount'],
                'company': v['ledger_entry__voucher__company__name'] or '',
            })

        total_profit = total_revenue - total_purchase

        return {
            'vendor_name': vendor_name,
            'projects': projects,
            'vouchers': vouchers,
            'summary': {
                'total_purchases': total_purchase,
                'total_revenue': total_revenue,
                'total_profit': total_profit,
                'project_count': len(projects),
                'voucher_count': len(vouchers),
            }
        }

    def get_customer_revenue_summary(self):
        """Get customer-wise revenue summary from sales vouchers"""
        
        vouchers = self._get_base_vouchers().filter(
            voucher_type='Sales'
        )
        
        # Group by party (customer)
        by_customer = vouchers.values('party_ledger_name').annotate(
            total_amount=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            transaction_count=Count('id')
        ).order_by('-total_amount')
        
        result = []
        for customer in by_customer:
            if customer['party_ledger_name']:
                result.append({
                    'customer_name': customer['party_ledger_name'],
                    'total_revenue': customer['total_amount'],
                    'transaction_count': customer['transaction_count'],
                    'avg_invoice_value': customer['total_amount'] / customer['transaction_count'] if customer['transaction_count'] > 0 else Decimal('0')
                })
        
        # Top customers
        top_customers = result[:10]
        
        # Total
        total_revenue = sum(c['total_revenue'] for c in result)
        
        return {
            'top_customers': top_customers,
            'all_customers': result,
            'summary': {
                'total_customers': len(result),
                'total_revenue': total_revenue,
                'avg_per_customer': total_revenue / len(result) if len(result) > 0 else Decimal('0')
            }
        }
    
    def get_payment_mode_analysis(self):
        """Analyze transactions by payment mode (enhanced)"""
        
        vouchers = self._get_base_vouchers().filter(
            voucher_type__in=['Payment', 'Receipt']
        )
        
        # By payment mode
        by_mode = vouchers.values('payment_mode', 'voucher_type').annotate(
            total_amount=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        ).order_by('-total_amount')
        
        # Cheque analysis
        cheque_vouchers = vouchers.filter(
            cheque_number__isnull=False
        ).exclude(cheque_number='')
        
        cheque_summary = cheque_vouchers.aggregate(
            total_amount=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        )
        
        # Get cheque details
        cheque_details = []
        for voucher in cheque_vouchers.order_by('-amount')[:20]:
            cheque_details.append({
                'date': voucher.date,
                'voucher_number': voucher.voucher_number,
                'party_name': voucher.party_ledger_name,
                'cheque_number': voucher.cheque_number,
                'cheque_date': voucher.cheque_date,
                'amount': voucher.amount,
                'company': voucher.company.name
            })
        
        # Summary by voucher type
        payment_summary = vouchers.filter(voucher_type='Payment').aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        )
        
        receipt_summary = vouchers.filter(voucher_type='Receipt').aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        )
        
        return {
            'by_mode': list(by_mode),
            'cheque_summary': {
                'total_amount': cheque_summary['total_amount'],
                'cheque_count': cheque_summary['count'],
                'recent_cheques': cheque_details
            },
            'summary': {
                'total_payments': payment_summary['total'],
                'payment_count': payment_summary['count'],
                'total_receipts': receipt_summary['total'],
                'receipt_count': receipt_summary['count'],
                'total_transactions': vouchers.count(),
                'total_amount': payment_summary['total'] + receipt_summary['total']
            }
        }
    
    def get_ledger_detail(self, ledger_name):
        """Get detailed transactions for a specific ledger"""
        
        ledger_entries = self._get_base_ledger_entries().filter(
            ledger_name__icontains=ledger_name
        ).select_related('voucher', 'voucher__company').order_by('-voucher__date')
        
        transactions = []
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        for entry in ledger_entries[:100]:  # Limit to 100 recent transactions
            amount = abs(entry.amount)
            
            if entry.is_debit:
                total_debit += amount
            else:
                total_credit += amount
            
            transactions.append({
                'date': entry.voucher.date,
                'voucher_type': entry.voucher.voucher_type,
                'voucher_number': entry.voucher.voucher_number,
                'amount': entry.amount,
                'is_debit': entry.is_debit,
                'company': entry.voucher.company.name
            })
        
        return {
            'ledger_name': ledger_name,
            'transactions': transactions,
            'summary': {
                'total_debit': total_debit,
                'total_credit': total_credit,
                'net_balance': total_debit - total_credit,
                'transaction_count': len(transactions)
            }
        }
    
    def _get_base_vouchers(self):
        """Get base voucher queryset with filters"""

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

    def _get_base_ledger_entries(self):
        """Get base ledger entry queryset with filters"""

        queryset = TallyVoucherLedgerEntry.objects.exclude(voucher__is_cancelled=True)

        if self.start_date:
            queryset = queryset.filter(
                Q(voucher__billing_month_date__gte=self.start_date) |
                Q(voucher__billing_month_date__isnull=True, voucher__date__gte=self.start_date)
            )
        if self.end_date:
            queryset = queryset.filter(
                Q(voucher__billing_month_date__lte=self.end_date) |
                Q(voucher__billing_month_date__isnull=True, voucher__date__lte=self.end_date)
            )

        if self.company_id:
            queryset = queryset.filter(voucher__company_id=self.company_id)

        return queryset