from django.db.models import Sum, Count, Q, F, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce, TruncMonth
from integrations.tallysync.models import TallyVoucher, TallyCompany
from integrations.tallysync.services.gst_utils import voucher_gst_subquery_direct
from datetime import datetime, timedelta
from decimal import Decimal


class FinancialAnalyticsService:
    """Service for financial aggregations and analytics from Tally data"""
    
    def __init__(self, start_date=None, end_date=None, company_id=None):
        self.start_date = start_date
        self.end_date = end_date
        self.company_id = company_id
    
    def get_executive_summary(self):
        """Get executive financial overview"""

        # Base queryset
        vouchers = self._get_base_queryset()

        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']
        net_voucher_amount = self._net_voucher_amount_expr()

        # Revenue (Sales - Credit Notes) — net of GST
        gross_revenue = vouchers.filter(voucher_type='Sales').aggregate(
            total=Coalesce(Sum(net_voucher_amount), Decimal('0'), output_field=DecimalField())
        )['total']
        credit_notes = vouchers.filter(voucher_type='Credit Note').aggregate(
            total=Coalesce(Sum(net_voucher_amount), Decimal('0'), output_field=DecimalField())
        )['total']
        revenue = gross_revenue - credit_notes

        # Purchase split — net of GST
        gross_purchase = vouchers.filter(voucher_type__in=PURCHASE_TYPES).aggregate(
            total=Coalesce(Sum(net_voucher_amount), Decimal('0'), output_field=DecimalField())
        )['total']
        debit_notes = vouchers.filter(voucher_type='Debit Note').aggregate(
            total=Coalesce(Sum(net_voucher_amount), Decimal('0'), output_field=DecimalField())
        )['total']
        journal_expenses = vouchers.filter(voucher_type='Journal').aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        payments = vouchers.filter(voucher_type='Payment').aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        collections = vouchers.filter(voucher_type='Receipt').aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']

        net_purchase = gross_purchase - debit_notes
        net_profit = revenue - net_purchase
        margin_pct = (net_profit / revenue * 100) if revenue > 0 else 0

        # Count of transactions
        sales_count = vouchers.filter(voucher_type='Sales').count()
        purchase_count = vouchers.filter(voucher_type__in=PURCHASE_TYPES).count()

        return {
            'revenue': revenue,
            'purchase': net_purchase,
            'expenses': journal_expenses,
            'payments': payments,
            'collections': collections,
            'net_profit': net_profit,
            'margin_percentage': margin_pct,
            'sales_count': sales_count,
            'purchase_count': purchase_count,
            'total_transactions': vouchers.count()
        }
    
    def get_revenue_breakdown(self):
        """Get revenue breakdown by voucher type"""
        
        vouchers = self._get_base_queryset()
        
        breakdown = vouchers.filter(
            voucher_type__in=['Sales', 'Credit Note', 'Debit Note']
        ).values('voucher_type').annotate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        ).order_by('-total')
        
        return list(breakdown)
    
    def get_expense_breakdown(self):
        """Get breakdown of all cost types by voucher type"""

        vouchers = self._get_base_queryset()

        breakdown = vouchers.filter(
            voucher_type__in=['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm', 'Debit Note', 'Journal', 'Payment']
        ).values('voucher_type').annotate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        ).order_by('-total')

        return list(breakdown)
    
    def get_company_wise_summary(self):
        """Get financial summary by company"""

        vouchers = self._get_base_queryset()

        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']
        net_voucher_amount = self._net_voucher_amount_expr()

        companies = vouchers.annotate(
            _net_amount=net_voucher_amount
        ).values('company__name').annotate(
            gross_revenue=Coalesce(
                Sum('_net_amount', filter=Q(voucher_type='Sales')),
                Decimal('0'),
                output_field=DecimalField()
            ),
            credit_notes=Coalesce(
                Sum('_net_amount', filter=Q(voucher_type='Credit Note')),
                Decimal('0'),
                output_field=DecimalField()
            ),
            gross_purchase=Coalesce(
                Sum('_net_amount', filter=Q(voucher_type__in=PURCHASE_TYPES)),
                Decimal('0'),
                output_field=DecimalField()
            ),
            debit_notes=Coalesce(
                Sum('_net_amount', filter=Q(voucher_type='Debit Note')),
                Decimal('0'),
                output_field=DecimalField()
            ),
            journal_expenses=Coalesce(
                Sum('amount', filter=Q(voucher_type='Journal')),
                Decimal('0'),
                output_field=DecimalField()
            ),
            payments=Coalesce(
                Sum('amount', filter=Q(voucher_type='Payment')),
                Decimal('0'),
                output_field=DecimalField()
            ),
            collections=Coalesce(
                Sum('amount', filter=Q(voucher_type='Receipt')),
                Decimal('0'),
                output_field=DecimalField()
            ),
            transaction_count=Count('id')
        ).order_by('-gross_revenue')

        result = []
        for company in companies:
            revenue = company['gross_revenue'] - company['credit_notes']
            purchase = company['gross_purchase'] - company['debit_notes']
            profit = revenue - purchase
            margin = (profit / revenue * 100) if revenue > 0 else 0

            result.append({
                'company_name': company['company__name'],
                'revenue': revenue,
                'purchase': purchase,
                'expenses': company['journal_expenses'],
                'payments': company['payments'],
                'collections': company['collections'],
                'profit': profit,
                'margin_percentage': margin,
                'transaction_count': company['transaction_count']
            })

        return result
    
    def get_monthly_trend(self, months=6):
        """Get monthly financial trend"""

        # Get data for last N months
        end_date = self.end_date or datetime.now().date()
        start_date = end_date - timedelta(days=months * 31)

        # Create queryset with date filters
        vouchers = TallyVoucher.objects.exclude(is_cancelled=True)

        if self.company_id:
            vouchers = vouchers.filter(company_id=self.company_id)

        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']
        net_voucher_amount = self._net_voucher_amount_expr()

        monthly_data = vouchers.filter(
            Q(billing_month_date__gte=start_date, billing_month_date__lte=end_date) |
            Q(billing_month_date__isnull=True, date__gte=start_date, date__lte=end_date)
        ).annotate(
            month=TruncMonth('billing_month_date'),
            _net_amount=net_voucher_amount,
        ).values('month').annotate(
            gross_revenue=Coalesce(
                Sum('_net_amount', filter=Q(voucher_type='Sales')),
                Decimal('0'),
                output_field=DecimalField()
            ),
            credit_notes=Coalesce(
                Sum('_net_amount', filter=Q(voucher_type='Credit Note')),
                Decimal('0'),
                output_field=DecimalField()
            ),
            gross_purchase=Coalesce(
                Sum('_net_amount', filter=Q(voucher_type__in=PURCHASE_TYPES)),
                Decimal('0'),
                output_field=DecimalField()
            ),
            debit_notes=Coalesce(
                Sum('_net_amount', filter=Q(voucher_type='Debit Note')),
                Decimal('0'),
                output_field=DecimalField()
            ),
            journal_expenses=Coalesce(
                Sum('amount', filter=Q(voucher_type='Journal')),
                Decimal('0'),
                output_field=DecimalField()
            ),
            transaction_count=Count('id')
        ).order_by('month')

        result = []
        for data in monthly_data:
            revenue = data['gross_revenue'] - data['credit_notes']
            purchase = data['gross_purchase'] - data['debit_notes']
            profit = revenue - purchase

            result.append({
                'month': data['month'],
                'revenue': revenue,
                'purchase': purchase,
                'expenses': data['journal_expenses'],
                'profit': profit,
                'transaction_count': data['transaction_count']
            })

        return result
    
    def _net_voucher_amount_expr(self):
        """ExpressionWrapper: voucher.amount - total GST for use in voucher-level annotations."""
        gst_sq = voucher_gst_subquery_direct()
        return ExpressionWrapper(
            F('amount') - Coalesce(gst_sq, Decimal('0'), output_field=DecimalField()),
            output_field=DecimalField()
        )

    def _get_base_queryset(self):
        vouchers = TallyVoucher.objects.exclude(is_cancelled=True)

        if self.company_id:
            vouchers = vouchers.filter(company_id=self.company_id)

        if self.start_date:
            vouchers = vouchers.filter(
                Q(billing_month_date__gte=self.start_date) |
                Q(billing_month_date__isnull=True, date__gte=self.start_date)
            )
        if self.end_date:
            vouchers = vouchers.filter(
                Q(billing_month_date__lte=self.end_date) |
                Q(billing_month_date__isnull=True, date__lte=self.end_date)
            )

        return vouchers