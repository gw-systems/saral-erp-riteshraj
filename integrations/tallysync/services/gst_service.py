from django.db.models import Sum, Count, Q, DecimalField, Value
from django.db.models.functions import Coalesce
from integrations.tallysync.models import TallyVoucher, TallyVoucherLedgerEntry
from datetime import datetime
from decimal import Decimal


class GSTService:
    """Service for GST calculations and compliance tracking"""

    def __init__(self, start_date=None, end_date=None, company_id=None):
        self.start_date = start_date
        self.end_date = end_date
        self.company_id = company_id

    def get_gst_summary(self):
        """Get GST payable/receivable summary"""

        gst_collected = self._calculate_gst_from_vouchers('Sales')
        gst_paid = self._calculate_gst_from_vouchers('Purchase')

        net_gst_liability = gst_collected['total_gst'] - gst_paid['total_gst']
        itc_available = gst_paid['total_gst']

        return {
            'gst_collected': {
                'cgst': gst_collected['cgst'],
                'sgst': gst_collected['sgst'],
                'igst': gst_collected['igst'],
                'total': gst_collected['total_gst']
            },
            'gst_paid': {
                'cgst': gst_paid['cgst'],
                'sgst': gst_paid['sgst'],
                'igst': gst_paid['igst'],
                'total': gst_paid['total_gst']
            },
            'net_gst_liability': net_gst_liability,
            'itc_available': itc_available,
            'gst_to_pay': max(net_gst_liability, Decimal('0')),
            'gst_refund_due': abs(min(net_gst_liability, Decimal('0')))
        }

    def get_monthly_gst_return_data(self, month, year):
        """Get GST return data for a specific month (GSTR-1/GSTR-3B format)"""

        start_date = datetime(year, month, 1).date()
        if month == 12:
            end_date = datetime(year + 1, 1, 1).date()
        else:
            end_date = datetime(year, month + 1, 1).date()

        # Sales (outward supplies)
        sales_vouchers = self._get_base_vouchers('Sales').filter(
            billing_month_date__gte=start_date, billing_month_date__lt=end_date
        )
        sales_summary = self._calculate_gst_from_vouchers_detailed(sales_vouchers)

        # Purchases (inward supplies)
        purchase_vouchers = self._get_base_vouchers('Purchase').filter(
            billing_month_date__gte=start_date, billing_month_date__lt=end_date
        )
        purchase_summary = self._calculate_gst_from_vouchers_detailed(purchase_vouchers)

        return {
            'period': {
                'month': month, 'year': year,
                'start_date': start_date, 'end_date': end_date
            },
            'outward_supplies': {
                'taxable_value': sales_summary['taxable_value'],
                'cgst': sales_summary['cgst'],
                'sgst': sales_summary['sgst'],
                'igst': sales_summary['igst'],
                'total_tax': sales_summary['total_gst'],
                'invoice_count': sales_summary['count']
            },
            'inward_supplies': {
                'taxable_value': purchase_summary['taxable_value'],
                'cgst': purchase_summary['cgst'],
                'sgst': purchase_summary['sgst'],
                'igst': purchase_summary['igst'],
                'total_tax': purchase_summary['total_gst'],
                'invoice_count': purchase_summary['count']
            },
            'itc_claimed': purchase_summary['total_gst'],
            'net_tax_liability': sales_summary['total_gst'] - purchase_summary['total_gst']
        }

    def get_gst_by_state(self):
        """Get GST breakdown by state — single query with aggregation"""

        vouchers = self._get_base_vouchers('Sales')

        # Aggregate GST per state at DB level using ledger entries
        ledger_entries = TallyVoucherLedgerEntry.objects.filter(
            voucher__in=vouchers
        )

        # Get per-state invoice counts and amounts from vouchers
        state_voucher_data = vouchers.values('party_state').annotate(
            invoice_count=Count('id'),
            taxable_value=Coalesce(Sum('amount'), Value(Decimal('0')), output_field=DecimalField()),
        )

        # Get per-state GST from ledger entries
        state_gst_data = ledger_entries.values('voucher__party_state').annotate(
            cgst=Coalesce(
                Sum('amount', filter=Q(ledger_name__icontains='cgst')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            sgst=Coalesce(
                Sum('amount', filter=Q(ledger_name__icontains='sgst')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            igst=Coalesce(
                Sum('amount', filter=Q(ledger_name__icontains='igst')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
        )

        # Build GST map
        gst_map = {}
        for row in state_gst_data:
            state = row['voucher__party_state'] or 'Unknown'
            gst_map[state] = {
                'cgst': abs(row['cgst']),
                'sgst': abs(row['sgst']),
                'igst': abs(row['igst']),
            }

        result = []
        for row in state_voucher_data:
            state = row['party_state'] or 'Unknown'
            gst = gst_map.get(state, {'cgst': Decimal('0'), 'sgst': Decimal('0'), 'igst': Decimal('0')})
            total_gst = gst['cgst'] + gst['sgst'] + gst['igst']

            result.append({
                'state': state,
                'is_intra_state': gst['igst'] == 0 and (gst['cgst'] > 0 or gst['sgst'] > 0),
                'invoice_count': row['invoice_count'],
                'taxable_value': row['taxable_value'] - total_gst,
                'cgst': gst['cgst'],
                'sgst': gst['sgst'],
                'igst': gst['igst'],
                'total_gst': total_gst,
            })

        return result

    def get_gst_compliance_status(self):
        """Check GST compliance status — single query with conditional aggregation"""

        current_month = datetime.now().month
        current_year = datetime.now().year

        vouchers = TallyVoucher.objects.filter(
            voucher_type='Sales',
            billing_month_date__year=current_year,
            billing_month_date__month__lte=current_month,
        ).exclude(is_cancelled=True)
        if self.company_id:
            vouchers = vouchers.filter(company_id=self.company_id)

        # Single query: aggregate per month
        monthly_rows = vouchers.values('billing_month_date__month').annotate(
            invoice_count=Count('id'),
            total_amount=Coalesce(Sum('amount'), Value(Decimal('0')), output_field=DecimalField()),
        )

        month_map = {row['billing_month_date__month']: row for row in monthly_rows}

        months_status = []
        for month in range(1, current_month + 1):
            data = month_map.get(month)
            count = data['invoice_count'] if data else 0
            amount = data['total_amount'] if data else Decimal('0')

            months_status.append({
                'month': month,
                'year': current_year,
                'invoice_count': count,
                'total_amount': amount,
                'has_data': count > 0,
            })

        return months_status

    def _calculate_gst_from_vouchers(self, voucher_type):
        """Calculate total GST from vouchers — single aggregation query"""

        vouchers = self._get_base_vouchers(voucher_type)

        # Single query with conditional aggregation
        gst = TallyVoucherLedgerEntry.objects.filter(
            voucher__in=vouchers
        ).aggregate(
            cgst=Coalesce(
                Sum('amount', filter=Q(ledger_name__icontains='cgst')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            sgst=Coalesce(
                Sum('amount', filter=Q(ledger_name__icontains='sgst')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            igst=Coalesce(
                Sum('amount', filter=Q(ledger_name__icontains='igst')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
        )

        cgst = abs(gst['cgst'])
        sgst = abs(gst['sgst'])
        igst = abs(gst['igst'])

        return {
            'cgst': cgst,
            'sgst': sgst,
            'igst': igst,
            'total_gst': cgst + sgst + igst,
        }

    def _calculate_gst_from_vouchers_detailed(self, vouchers):
        """Calculate detailed GST breakdown — single aggregation query"""

        result = TallyVoucherLedgerEntry.objects.filter(
            voucher__in=vouchers
        ).aggregate(
            cgst=Coalesce(
                Sum('amount', filter=Q(ledger_name__icontains='cgst')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            sgst=Coalesce(
                Sum('amount', filter=Q(ledger_name__icontains='sgst')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            igst=Coalesce(
                Sum('amount', filter=Q(ledger_name__icontains='igst')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
        )

        total_amount = vouchers.aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0')), output_field=DecimalField())
        )['total']

        cgst = abs(result['cgst'])
        sgst = abs(result['sgst'])
        igst = abs(result['igst'])
        total_gst = cgst + sgst + igst

        return {
            'taxable_value': total_amount - total_gst,
            'cgst': cgst,
            'sgst': sgst,
            'igst': igst,
            'total_gst': total_gst,
            'count': vouchers.count(),
        }

    def _get_base_vouchers(self, voucher_type):
        """Get base voucher queryset"""
        queryset = TallyVoucher.objects.filter(voucher_type=voucher_type).exclude(is_cancelled=True)

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

    def get_detailed_gst_breakdown(self):
        """Get detailed GST breakdown using actual GST field values from ledger entries"""

        ledger_entries = self._get_base_ledger_entries()

        gst_entries = ledger_entries.filter(
            Q(cgst_amount__gt=0) | Q(sgst_amount__gt=0) | Q(igst_amount__gt=0)
        )

        by_rate = gst_entries.values(
            'cgst_rate', 'sgst_rate', 'igst_rate'
        ).annotate(
            total_cgst=Coalesce(Sum('cgst_amount'), Value(Decimal('0')), output_field=DecimalField()),
            total_sgst=Coalesce(Sum('sgst_amount'), Value(Decimal('0')), output_field=DecimalField()),
            total_igst=Coalesce(Sum('igst_amount'), Value(Decimal('0')), output_field=DecimalField()),
            total_cess=Coalesce(Sum('cess_amount'), Value(Decimal('0')), output_field=DecimalField()),
            transaction_count=Count('id')
        ).order_by('-total_cgst')

        by_hsn = gst_entries.filter(
            gst_hsn_code__isnull=False
        ).exclude(
            gst_hsn_code=''
        ).values('gst_hsn_code').annotate(
            total_cgst=Coalesce(Sum('cgst_amount'), Value(Decimal('0')), output_field=DecimalField()),
            total_sgst=Coalesce(Sum('sgst_amount'), Value(Decimal('0')), output_field=DecimalField()),
            total_igst=Coalesce(Sum('igst_amount'), Value(Decimal('0')), output_field=DecimalField()),
            transaction_count=Count('id')
        ).order_by('-total_cgst')

        total_summary = gst_entries.aggregate(
            total_cgst=Coalesce(Sum('cgst_amount'), Value(Decimal('0')), output_field=DecimalField()),
            total_sgst=Coalesce(Sum('sgst_amount'), Value(Decimal('0')), output_field=DecimalField()),
            total_igst=Coalesce(Sum('igst_amount'), Value(Decimal('0')), output_field=DecimalField()),
            total_cess=Coalesce(Sum('cess_amount'), Value(Decimal('0')), output_field=DecimalField()),
        )

        return {
            'by_rate': list(by_rate),
            'by_hsn': list(by_hsn),
            'total_summary': {
                'cgst': abs(total_summary['total_cgst']),
                'sgst': abs(total_summary['total_sgst']),
                'igst': abs(total_summary['total_igst']),
                'cess': abs(total_summary['total_cess']),
                'total_gst': abs(total_summary['total_cgst']) + abs(total_summary['total_sgst']) + abs(total_summary['total_igst']) + abs(total_summary['total_cess']),
            }
        }

    def _get_base_ledger_entries(self):
        """Get base ledger entry queryset with filters"""
        queryset = TallyVoucherLedgerEntry.objects.all()

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
