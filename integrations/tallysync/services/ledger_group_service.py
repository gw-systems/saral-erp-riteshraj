from django.db.models import Sum, Count, Q, DecimalField, Value
from django.db.models.functions import Coalesce
from integrations.tallysync.models import TallyGroup, TallyVoucherLedgerEntry
from decimal import Decimal


class LedgerGroupService:
    """Service for ledger group hierarchy analysis"""

    def __init__(self, start_date=None, end_date=None, company_id=None):
        self.start_date = start_date
        self.end_date = end_date
        self.company_id = company_id

    def _base_entry_filters(self):
        """Return Q objects for date/company filtering"""
        filters = Q()
        if self.start_date:
            filters &= (
                Q(voucher__billing_month_date__gte=self.start_date) |
                Q(voucher__billing_month_date__isnull=True, voucher__date__gte=self.start_date)
            )
        if self.end_date:
            filters &= (
                Q(voucher__billing_month_date__lte=self.end_date) |
                Q(voucher__billing_month_date__isnull=True, voucher__date__lte=self.end_date)
            )
        if self.company_id:
            filters &= Q(voucher__company_id=self.company_id)
        return filters

    def _bulk_group_financials(self):
        """Get debit/credit totals per group in a SINGLE query using ledger FK.
        Returns dict: {group_name: {'debit': X, 'credit': Y, 'count': N}}
        """
        base_filters = self._base_entry_filters()

        rows = TallyVoucherLedgerEntry.objects.filter(
            base_filters,
            ledger__group__isnull=False,
        ).exclude(voucher__is_cancelled=True).values(
            'ledger__group__name'
        ).annotate(
            debit_total=Coalesce(
                Sum('amount', filter=Q(is_debit=True)),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            credit_total=Coalesce(
                Sum('amount', filter=Q(is_debit=False)),
                Value(Decimal('0')), output_field=DecimalField()
            ),
            transaction_count=Count('id'),
        )

        result = {}
        for row in rows:
            gname = row['ledger__group__name']
            result[gname] = {
                'debit': abs(row['debit_total']),
                'credit': abs(row['credit_total']),
                'count': row['transaction_count'],
            }
        return result

    def get_all_groups_summary(self):
        """Get financial summary for all ledger groups — single query"""

        # Bulk fetch all group financials
        financials = self._bulk_group_financials()

        # Get all groups with company info
        groups = TallyGroup.objects.select_related('company').all()

        result = []
        for group in groups:
            fin = financials.get(group.name)
            if not fin or fin['count'] == 0:
                continue

            net_balance = fin['debit'] - fin['credit']

            result.append({
                'group_id': group.id,
                'group_name': group.name,
                'company': group.company.name,
                'parent_group': group.parent,
                'is_revenue': group.is_revenue,
                'debit_total': fin['debit'],
                'credit_total': fin['credit'],
                'net_balance': net_balance,
                'transaction_count': fin['count'],
            })

        result.sort(key=lambda x: abs(x['net_balance']), reverse=True)
        return result

    def get_group_hierarchy(self):
        """Get hierarchical group structure with financials — prefetched"""

        # Load ALL groups in one query
        all_groups = list(TallyGroup.objects.all())

        # Build parent→children mapping in memory
        children_map = {}
        roots = []
        for g in all_groups:
            parent = g.parent or ''
            if not parent:
                roots.append(g)
            else:
                children_map.setdefault(parent, []).append(g)

        # Bulk fetch financials
        financials = self._bulk_group_financials()

        # Build tree recursively from in-memory data
        hierarchy = []
        for root in roots:
            hierarchy.append(self._build_tree_from_memory(root, children_map, financials))

        return hierarchy

    def _build_tree_from_memory(self, group, children_map, financials):
        """Build group tree from pre-loaded data (no DB queries)"""
        fin = financials.get(group.name, {'debit': Decimal('0'), 'credit': Decimal('0'), 'count': 0})

        node = {
            'group_name': group.name,
            'is_revenue': group.is_revenue,
            'debit_total': fin['debit'],
            'credit_total': fin['credit'],
            'net_balance': fin['debit'] - fin['credit'],
            'children': [],
        }

        for child in children_map.get(group.name, []):
            node['children'].append(self._build_tree_from_memory(child, children_map, financials))

        return node

    def get_income_statement_groups(self):
        """Get groups organized as income statement (P&L) — single query"""

        financials = self._bulk_group_financials()

        # Get groups categorized
        all_groups = TallyGroup.objects.all()

        revenue_total = Decimal('0')
        revenue_breakdown = []
        expense_total = Decimal('0')
        expense_breakdown = []

        for group in all_groups:
            fin = financials.get(group.name)
            if not fin or fin['count'] == 0:
                continue

            amount = abs(fin['credit'] - fin['debit']) if group.is_revenue else abs(fin['debit'] - fin['credit'])

            if group.is_revenue:
                revenue_breakdown.append({'group_name': group.name, 'amount': amount})
                revenue_total += amount
            elif not any(kw in group.name.lower() for kw in ['asset', 'liability', 'capital']):
                expense_breakdown.append({'group_name': group.name, 'amount': amount})
                expense_total += amount

        net_profit = revenue_total - expense_total

        return {
            'revenue': {
                'total': revenue_total,
                'breakdown': sorted(revenue_breakdown, key=lambda x: x['amount'], reverse=True)
            },
            'expenses': {
                'total': expense_total,
                'breakdown': sorted(expense_breakdown, key=lambda x: x['amount'], reverse=True)
            },
            'net_profit': net_profit,
            'margin_pct': (net_profit / revenue_total * 100) if revenue_total > 0 else 0
        }

    def get_top_expense_groups(self, limit=10):
        """Get top expense groups by amount"""
        all_groups = self.get_all_groups_summary()
        expense_groups = [
            g for g in all_groups
            if g['debit_total'] > g['credit_total'] and not g['is_revenue']
        ]
        expense_groups.sort(key=lambda x: x['debit_total'], reverse=True)
        return expense_groups[:limit]

    def get_top_revenue_groups(self, limit=10):
        """Get top revenue groups by amount"""
        all_groups = self.get_all_groups_summary()
        revenue_groups = [g for g in all_groups if g['is_revenue']]
        revenue_groups.sort(key=lambda x: x['credit_total'], reverse=True)
        return revenue_groups[:limit]
