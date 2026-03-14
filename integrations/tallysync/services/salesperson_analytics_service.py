from django.db.models import Sum, Count, Q, DecimalField, Value, F, ExpressionWrapper
from django.db.models.functions import Coalesce
from integrations.tallysync.models import TallyVoucherCostCentreAllocation
from integrations.tallysync.services.gst_utils import voucher_gst_subquery, net_alloc_amount
from projects.models import ProjectCode
from decimal import Decimal


class SalespersonAnalyticsService:
    """Service for salesperson performance tracking"""

    def __init__(self, start_date=None, end_date=None):
        self.start_date = start_date
        self.end_date = end_date

    def _get_base_allocations(self):
        """Get base allocations queryset with date filters applied"""
        from django.db.models import F
        allocations = TallyVoucherCostCentreAllocation.objects.filter(
            cost_centre__erp_project__isnull=False,
            cost_centre__erp_project__sales_manager__isnull=False,
        ).exclude(
            cost_centre__erp_project__sales_manager=''
        ).exclude(
            ledger_entry__voucher__is_cancelled=True
        )

        # Use billing_month_date when set, fall back to voucher date
        if self.start_date:
            allocations = allocations.filter(
                Q(ledger_entry__voucher__billing_month_date__gte=self.start_date) |
                Q(ledger_entry__voucher__billing_month_date__isnull=True,
                  ledger_entry__voucher__date__gte=self.start_date)
            )
        if self.end_date:
            allocations = allocations.filter(
                Q(ledger_entry__voucher__billing_month_date__lte=self.end_date) |
                Q(ledger_entry__voucher__billing_month_date__isnull=True,
                  ledger_entry__voucher__date__lte=self.end_date)
            )

        return allocations

    def _get_bulk_tally_data(self, project_ids=None):
        """Get Tally revenue/purchase/expenses for all projects in a single query.
        Returns dict: {project_id: {'revenue': X, 'purchase': Y, 'expenses': Z, 'payments': W, 'collections': V, 'profit': P}}
        """
        allocations = TallyVoucherCostCentreAllocation.objects.filter(
            cost_centre__erp_project__isnull=False,
        ).exclude(ledger_entry__voucher__is_cancelled=True)

        if project_ids:
            allocations = allocations.filter(
                cost_centre__erp_project__project_id__in=project_ids
            )

        if self.start_date:
            allocations = allocations.filter(
                Q(ledger_entry__voucher__billing_month_date__gte=self.start_date) |
                Q(ledger_entry__voucher__billing_month_date__isnull=True,
                  ledger_entry__voucher__date__gte=self.start_date)
            )
        if self.end_date:
            allocations = allocations.filter(
                Q(ledger_entry__voucher__billing_month_date__lte=self.end_date) |
                Q(ledger_entry__voucher__billing_month_date__isnull=True,
                  ledger_entry__voucher__date__lte=self.end_date)
            )

        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']
        net_amount = net_alloc_amount()

        # Single query: aggregate net revenue and purchase split per project
        project_financials = allocations.values(
            'cost_centre__erp_project__project_id'
        ).annotate(
            gross_revenue=Coalesce(
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

        result = {}
        for row in project_financials:
            pid = row['cost_centre__erp_project__project_id']
            revenue = row['gross_revenue'] - row['credit_notes']
            purchase = row['gross_purchase'] - row['debit_notes']
            result[pid] = {
                'revenue': revenue,
                'purchase': purchase,
                'expenses': row['journal_expenses'],
                'payments': row['payments'],
                'collections': row['collections'],
                'profit': revenue - purchase,
            }
        return result

    def get_all_salesperson_summary(self):
        """Get performance summary for all salespeople — single aggregation query"""

        allocations = self._get_base_allocations()

        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']
        net_amount = net_alloc_amount()

        sp_data = list(allocations.values(
            'cost_centre__erp_project__sales_manager'
        ).annotate(
            project_count=Count('cost_centre__erp_project__project_id', distinct=True),
            gross_revenue=Coalesce(
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
        ).order_by('-gross_revenue'))

        # Build project_codes per salesperson in one query
        sp_names = [row['cost_centre__erp_project__sales_manager'] for row in sp_data]
        sp_projects = ProjectCode.objects.filter(
            sales_manager__in=sp_names
        ).values('sales_manager', 'code', 'client_name')
        codes_by_sp = {}
        for p in sp_projects:
            codes_by_sp.setdefault(p['sales_manager'], []).append(p['code'])

        result = []
        for row in sp_data:
            sp_name = row['cost_centre__erp_project__sales_manager']
            revenue = row['gross_revenue'] - row['credit_notes']
            purchase = row['gross_purchase'] - row['debit_notes']
            profit = revenue - purchase
            # Issue 4 fix: weighted margin (profit/revenue), not average of individual margins
            margin = (profit / revenue * 100) if revenue > 0 else Decimal('0')
            pc = row['project_count']

            result.append({
                'salesperson_name': sp_name,
                'project_count': pc,
                'project_codes': codes_by_sp.get(sp_name, []),
                'total_revenue': revenue,
                'total_purchase': purchase,
                'total_expenses': row['journal_expenses'],
                'total_payments': row['payments'],
                'total_profit': profit,
                'profit_margin': margin,
                'avg_revenue_per_project': revenue / pc if pc > 0 else Decimal('0'),
                'avg_profit_per_project': profit / pc if pc > 0 else Decimal('0'),
            })

        return result

    def get_salesperson_detail(self, salesperson_name):
        """Get detailed performance for a single salesperson"""

        projects = ProjectCode.objects.filter(sales_manager=salesperson_name)
        project_ids = list(projects.values_list('project_id', flat=True))

        # Bulk fetch tally data for all projects in ONE query
        tally_map = self._get_bulk_tally_data(project_ids)

        project_details = []
        total_revenue = Decimal('0')
        total_purchase = Decimal('0')

        default_tally = {
            'revenue': Decimal('0'),
            'purchase': Decimal('0'),
            'expenses': Decimal('0'),
            'payments': Decimal('0'),
            'collections': Decimal('0'),
            'profit': Decimal('0'),
        }

        for project in projects:
            tally_data = tally_map.get(project.project_id, default_tally)
            rev = tally_data['revenue']
            purchase = tally_data['purchase']
            profit = rev - purchase

            project_details.append({
                'project_id': project.project_id,
                'project_code': project.project_code,
                'code': project.code,
                'client_name': project.client_name,
                'vendor_name': project.vendor_name,
                'location': project.location,
                'revenue': rev,
                'purchase': purchase,
                'expenses': tally_data['expenses'],
                'payments': tally_data['payments'],
                'collections': tally_data['collections'],
                'profit': profit,
                'margin': (profit / rev * 100) if rev > 0 else 0
            })

            total_revenue += rev
            total_purchase += purchase

        project_details.sort(key=lambda x: x['revenue'], reverse=True)
        count = len(project_ids)
        total_profit = total_revenue - total_purchase

        # Group projects by client_name
        clients_map = {}
        for p in project_details:
            cname = p['client_name'] or 'Unknown Client'
            if cname not in clients_map:
                clients_map[cname] = {
                    'client_name': cname,
                    'project_count': 0,
                    'total_revenue': Decimal('0'),
                    'total_purchase': Decimal('0'),
                    'projects': [],
                }
            clients_map[cname]['project_count'] += 1
            clients_map[cname]['total_revenue'] += p['revenue']
            clients_map[cname]['total_purchase'] += p['purchase']
            clients_map[cname]['projects'].append(p)

        clients = []
        for cname, cd in clients_map.items():
            cp = cd['total_revenue'] - cd['total_purchase']
            clients.append({
                'client_name': cname,
                'project_count': cd['project_count'],
                'total_revenue': cd['total_revenue'],
                'total_purchase': cd['total_purchase'],
                'total_profit': cp,
                'profit_margin': (cp / cd['total_revenue'] * 100) if cd['total_revenue'] > 0 else Decimal('0'),
                'projects': cd['projects'],
            })
        clients.sort(key=lambda x: (x['client_name'] or '').lower())

        return {
            'salesperson': {
                'name': salesperson_name
            },
            'summary': {
                'project_count': count,
                'total_revenue': total_revenue,
                'total_purchase': total_purchase,
                'total_profit': total_profit,
                'profit_margin': (total_profit / total_revenue * 100) if total_revenue > 0 else 0,
                'avg_revenue_per_project': total_revenue / count if count > 0 else 0,
                'avg_profit_per_project': total_profit / count if count > 0 else 0,
            },
            'clients': clients,
            'projects': project_details,
        }

    def get_top_performers(self, limit=10):
        """Get top N salespeople by revenue"""
        return self.get_all_salesperson_summary()[:limit]

    def get_performance_comparison(self):
        """Compare all salespeople performance"""

        all_salespeople = self.get_all_salesperson_summary()

        if not all_salespeople:
            return {
                'avg_revenue': Decimal('0'),
                'avg_profit': Decimal('0'),
                'avg_margin': 0,
                'top_performer': None,
                'comparisons': []
            }

        n = len(all_salespeople)
        total_revenue = sum(sp['total_revenue'] for sp in all_salespeople)
        total_profit = sum(sp['total_profit'] for sp in all_salespeople)

        avg_revenue = total_revenue / n
        avg_profit = total_profit / n
        avg_margin = sum(sp['profit_margin'] for sp in all_salespeople) / n

        for sp in all_salespeople:
            sp['vs_avg_revenue'] = sp['total_revenue'] - avg_revenue
            sp['vs_avg_profit'] = sp['total_profit'] - avg_profit
            sp['vs_avg_margin'] = sp['profit_margin'] - avg_margin

        return {
            'avg_revenue': avg_revenue,
            'avg_profit': avg_profit,
            'avg_margin': avg_margin,
            'top_performer': all_salespeople[0],
            'comparisons': all_salespeople
        }
