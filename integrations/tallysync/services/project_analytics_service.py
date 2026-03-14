from django.db.models import Sum, Count, Q, DecimalField, Value, F, ExpressionWrapper
from django.db.models.functions import Coalesce, TruncMonth
from integrations.tallysync.models import (
    TallyVoucher, TallyVoucherLedgerEntry, TallyVoucherCostCentreAllocation
)
from integrations.tallysync.services.gst_utils import net_alloc_amount, voucher_gst_subquery_direct
from operations.models import MonthlyBilling
from projects.models import ProjectCode
from decimal import Decimal


class ProjectAnalyticsService:
    """Service for project-level profitability and analytics"""

    def __init__(self, start_date=None, end_date=None):
        self.start_date = start_date
        self.end_date = end_date

    def _get_bulk_erp_estimates(self, project_ids=None):
        """Get ERP billing estimates for ALL projects in a single query.
        Returns dict: {project_id: {'revenue': X, 'expenses': Y}}
        """
        billings = MonthlyBilling.objects.all()

        if project_ids:
            billings = billings.filter(project_id__in=project_ids)

        if self.start_date:
            billings = billings.filter(billing_month__gte=self.start_date)
        if self.end_date:
            billings = billings.filter(billing_month__lte=self.end_date)

        rows = billings.values('project_id').annotate(
            revenue=Coalesce(Sum('client_total'), Value(Decimal('0')), output_field=DecimalField()),
            expenses=Coalesce(Sum('vendor_total'), Value(Decimal('0')), output_field=DecimalField()),
        )

        result = {}
        for row in rows:
            rev = row['revenue']
            exp = row['expenses']
            result[row['project_id']] = {
                'revenue': rev,
                'expenses': exp,
                'profit': rev - exp,
                'margin_pct': (rev - exp) / rev * 100 if rev > 0 else 0,
            }
        return result

    def get_all_projects_summary(self, client_names=None, vendor_names=None):
        """Get profitability summary for all projects — 2 queries total.
        Optional client_names/vendor_names filters for drill-down from client/vendor dashboards.
        """

        allocations = self._get_base_allocations().exclude(
            ledger_entry__voucher__is_cancelled=True
        )

        if client_names:
            allocations = allocations.filter(
                cost_centre__erp_project__client_name__in=client_names
            )
        if vendor_names:
            allocations = allocations.filter(
                cost_centre__erp_project__vendor_name__in=vendor_names
            )

        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']
        net_amount = net_alloc_amount()

        projects = allocations.values(
            'cost_centre__erp_project__project_id',
            'cost_centre__erp_project__project_code',
            'cost_centre__erp_project__code',
            'cost_centre__erp_project__client_name',
            'cost_centre__erp_project__vendor_name',
            'cost_centre__erp_project__sales_manager'
        ).annotate(
            tally_revenue=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Sales')),
                Value(Decimal('0')),
                output_field=DecimalField()
            ),
            tally_credit_notes=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Credit Note')),
                Value(Decimal('0')),
                output_field=DecimalField()
            ),
            tally_gross_purchase=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type__in=PURCHASE_TYPES)),
                Value(Decimal('0')),
                output_field=DecimalField()
            ),
            tally_debit_notes=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Debit Note')),
                Value(Decimal('0')),
                output_field=DecimalField()
            ),
            tally_journal_expenses=Coalesce(
                Sum('amount', filter=Q(ledger_entry__voucher__voucher_type='Journal')),
                Value(Decimal('0')),
                output_field=DecimalField()
            ),
            tally_payments=Coalesce(
                Sum('amount', filter=Q(ledger_entry__voucher__voucher_type='Payment')),
                Value(Decimal('0')),
                output_field=DecimalField()
            ),
            tally_collections=Coalesce(
                Sum('amount', filter=Q(ledger_entry__voucher__voucher_type='Receipt')),
                Value(Decimal('0')),
                output_field=DecimalField()
            ),
            transaction_count=Count('ledger_entry__voucher', distinct=True)
        ).filter(
            cost_centre__erp_project__isnull=False,
            cost_centre__erp_project__series_type='WAAS'
        ).order_by('cost_centre__erp_project__client_name')

        # Force evaluation to get project IDs
        projects_list = list(projects)
        project_ids = [p['cost_centre__erp_project__project_id'] for p in projects_list]

        # Single query: ERP estimates for ALL projects
        erp_map = self._get_bulk_erp_estimates(project_ids)

        default_erp = {'revenue': Decimal('0'), 'expenses': Decimal('0'), 'profit': Decimal('0'), 'margin_pct': 0}

        result = []
        for project in projects_list:
            net_revenue = project['tally_revenue'] - project['tally_credit_notes']
            tally_purchase = project['tally_gross_purchase'] - project['tally_debit_notes']
            tally_profit = net_revenue - tally_purchase
            tally_margin = (tally_profit / net_revenue * 100) if net_revenue > 0 else 0

            pid = project['cost_centre__erp_project__project_id']
            erp_data = erp_map.get(pid, default_erp)

            result.append({
                'project_id': pid,
                'project_code': project['cost_centre__erp_project__project_code'],
                'code': project['cost_centre__erp_project__code'],
                'client_name': project['cost_centre__erp_project__client_name'],
                'vendor_name': project['cost_centre__erp_project__vendor_name'] or '',
                'sales_manager': project['cost_centre__erp_project__sales_manager'] or '',
                'tally_revenue': net_revenue,
                'tally_purchase': tally_purchase,
                'tally_expenses': project['tally_journal_expenses'],
                'tally_payments': project['tally_payments'],
                'tally_collections': project['tally_collections'],
                'tally_profit': tally_profit,
                'tally_margin_pct': tally_margin,
                'erp_revenue': erp_data['revenue'],
                'erp_expenses': erp_data['expenses'],
                'revenue_variance': net_revenue - erp_data['revenue'],
                'expense_variance': tally_purchase - erp_data['expenses'],
                'transaction_count': project['transaction_count']
            })

        return result

    def get_project_detail(self, project_id):
        """Get detailed profitability for a single project"""

        project = ProjectCode.objects.get(pk=project_id)

        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']

        # Tally summary — single query with conditional aggregation
        allocations = self._get_base_allocations().filter(
            cost_centre__erp_project_id=project_id
        ).exclude(ledger_entry__voucher__is_cancelled=True)

        net_amount = net_alloc_amount()
        tally_summary = allocations.aggregate(
            revenue=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Sales')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            credit_notes=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Credit Note')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            gross_purchase=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type__in=PURCHASE_TYPES)),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            debit_notes=Coalesce(
                Sum(net_amount, filter=Q(ledger_entry__voucher__voucher_type='Debit Note')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            journal_expenses=Coalesce(
                Sum('amount', filter=Q(ledger_entry__voucher__voucher_type='Journal')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            payments=Coalesce(
                Sum('amount', filter=Q(ledger_entry__voucher__voucher_type='Payment')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            collections=Coalesce(
                Sum('amount', filter=Q(ledger_entry__voucher__voucher_type='Receipt')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
        )
        revenue = tally_summary['revenue'] - tally_summary['credit_notes']
        purchase = tally_summary['gross_purchase'] - tally_summary['debit_notes']

        # ERP data — single query
        erp_map = self._get_bulk_erp_estimates([project_id])
        erp_data = erp_map.get(project_id, {'revenue': Decimal('0'), 'expenses': Decimal('0'), 'profit': Decimal('0'), 'margin_pct': 0})

        # Transactions list
        vouchers = TallyVoucher.objects.filter(
            ledger_entries__cost_allocations__cost_centre__erp_project_id=project_id,
            is_cancelled=False,
        ).distinct().select_related('company').order_by('-date')

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

        transactions = list(vouchers.values(
            'id', 'date', 'voucher_type', 'voucher_number',
            'party_ledger_name', 'amount', 'company__name',
            'narration', 'reference', 'billing_month',
        ))

        # Rename keys for API compatibility
        for t in transactions:
            t['party_name'] = t.pop('party_ledger_name')
            t['company'] = t.pop('company__name')

        profit = revenue - purchase
        return {
            'project': {
                'id': project.project_id,
                'code': project.code,
                'project_code': project.project_code,
                'client_name': project.client_name,
                'vendor_name': project.vendor_name,
                'location': project.location or '',
            },
            'tally_summary': {
                'revenue': revenue,
                'purchase': purchase,
                'expenses': tally_summary['journal_expenses'],
                'payments': tally_summary['payments'],
                'collections': tally_summary['collections'],
                'profit': profit,
                'margin_pct': (profit / revenue * 100) if revenue > 0 else 0
            },
            'erp_summary': erp_data,
            'variances': {
                'revenue': revenue - erp_data['revenue'],
                'expenses': purchase - erp_data['expenses'],
                'profit': profit - (erp_data['revenue'] - erp_data['expenses'])
            },
            'transactions': transactions
        }

    def get_top_profitable_projects(self, limit=10):
        """Get top N most profitable projects"""
        all_projects = self.get_all_projects_summary()
        sorted_projects = sorted(all_projects, key=lambda x: x['tally_profit'], reverse=True)
        return sorted_projects[:limit]

    def get_loss_making_projects(self):
        """Get projects making losses"""
        all_projects = self.get_all_projects_summary()
        loss_projects = [p for p in all_projects if p['tally_profit'] < 0]
        return sorted(loss_projects, key=lambda x: x['tally_profit'])

    def get_project_lifecycle_analysis(self, project_id):
        """Analyze project from start to current state — DB-level aggregation"""

        project = ProjectCode.objects.get(pk=project_id)

        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']

        # Get monthly aggregation at DB level instead of per-voucher loop
        base_vouchers = TallyVoucher.objects.filter(
            ledger_entries__cost_allocations__cost_centre__erp_project_id=project_id,
            is_cancelled=False,
        ).distinct()

        gst_sq = voucher_gst_subquery_direct()
        net_voucher_amount = ExpressionWrapper(
            F('amount') - Coalesce(gst_sq, Decimal('0'), output_field=DecimalField()),
            output_field=DecimalField()
        )

        monthly_rows = base_vouchers.annotate(
            month=TruncMonth('billing_month_date'),
            net_amount=net_voucher_amount,
        ).values('month').annotate(
            gross_revenue=Coalesce(
                Sum('net_amount', filter=Q(voucher_type='Sales')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            credit_notes=Coalesce(
                Sum('net_amount', filter=Q(voucher_type='Credit Note')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            gross_purchase=Coalesce(
                Sum('net_amount', filter=Q(voucher_type__in=PURCHASE_TYPES)),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            debit_notes=Coalesce(
                Sum('net_amount', filter=Q(voucher_type='Debit Note')),
                Value(Decimal('0')), output_field=DecimalField()
            ),
        ).order_by('month')

        # Build cumulative data in Python from aggregated rows
        cumulative_revenue = Decimal('0')
        cumulative_purchase = Decimal('0')
        monthly_data = []
        first_date = None
        last_date = None

        for row in monthly_rows:
            revenue = row['gross_revenue'] - row['credit_notes']
            purchase = row['gross_purchase'] - row['debit_notes']
            cumulative_revenue += revenue
            cumulative_purchase += purchase

            if first_date is None:
                first_date = row['month']
            last_date = row['month']

            monthly_data.append({
                'month': row['month'],
                'revenue': revenue,
                'purchase': purchase,
                'profit': revenue - purchase,
                'cumulative_revenue': cumulative_revenue,
                'cumulative_purchase': cumulative_purchase,
                'cumulative_profit': cumulative_revenue - cumulative_purchase
            })

        total_profit = cumulative_revenue - cumulative_purchase
        return {
            'project_code': project.project_code,
            'start_date': first_date,
            'end_date': last_date,
            'total_revenue': cumulative_revenue,
            'total_purchase': cumulative_purchase,
            'total_profit': total_profit,
            'monthly_breakdown': monthly_data,
            'is_profitable': total_profit > 0
        }

    def _get_base_allocations(self):
        """Get base queryset of cost centre allocations"""
        queryset = TallyVoucherCostCentreAllocation.objects.select_related(
            'cost_centre__erp_project',
            'ledger_entry__voucher__company'
        )

        if self.start_date:
            queryset = queryset.filter(
                Q(ledger_entry__voucher__billing_month_date__gte=self.start_date) |
                Q(ledger_entry__voucher__billing_month_date__isnull=True,
                  ledger_entry__voucher__date__gte=self.start_date)
            )
        if self.end_date:
            queryset = queryset.filter(
                Q(ledger_entry__voucher__billing_month_date__lte=self.end_date) |
                Q(ledger_entry__voucher__billing_month_date__isnull=True,
                  ledger_entry__voucher__date__lte=self.end_date)
            )

        return queryset
