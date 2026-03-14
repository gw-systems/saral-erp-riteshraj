from django.db.models import Sum, Count, Q, DecimalField, Value, F, ExpressionWrapper
from django.db.models.functions import Coalesce
from integrations.tallysync.models import TallyVoucherCostCentreAllocation
from integrations.tallysync.services.gst_utils import net_alloc_amount
from projects.models import ProjectCode
from supply.models import VendorCard
from decimal import Decimal


class VendorAnalyticsService:
    """Service for vendor-level profitability analytics"""

    def __init__(self, start_date=None, end_date=None):
        self.start_date = start_date
        self.end_date = end_date

    def _build_vendor_card_lookup(self):
        """Build lookup: vendor_short_name → {vendor_code, legal_name}
        Projects store vendor_short_name in vendor_name field.
        """
        cards = VendorCard.objects.values(
            'vendor_code', 'vendor_legal_name', 'vendor_short_name',
        )
        lookup = {}
        for c in cards:
            # Map both short_name and legal_name to the same card
            if c['vendor_short_name']:
                lookup[c['vendor_short_name']] = {
                    'vendor_code': c['vendor_code'],
                    'display_name': c['vendor_legal_name'],
                    'short_name': c['vendor_short_name'],
                }
            if c['vendor_legal_name']:
                lookup[c['vendor_legal_name']] = {
                    'vendor_code': c['vendor_code'],
                    'display_name': c['vendor_legal_name'],
                    'short_name': c['vendor_short_name'],
                }
        return lookup

    def _get_bulk_tally_data(self, project_ids=None):
        """Get Tally financials for all projects in a single query.
        Returns dict: {project_id: {'revenue': X, 'purchase': Y, 'expenses': Z, ...}}
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

        rows = allocations.values(
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
        for row in rows:
            revenue = row['gross_revenue'] - row['credit_notes']
            purchase = row['gross_purchase'] - row['debit_notes']
            result[row['cost_centre__erp_project__project_id']] = {
                'revenue': revenue,
                'purchase': purchase,
                'expenses': row['journal_expenses'],
                'payments': row['payments'],
                'collections': row['collections'],
                'profit': revenue - purchase,
            }
        return result

    def get_all_vendors_summary(self):
        """Get profitability summary for all vendors — bulk queries only.
        Uses VendorCard legal names where available, falls back to ProjectCode.vendor_name.
        """

        projects = list(ProjectCode.objects.values('project_id', 'vendor_name', 'code'))
        project_ids = [p['project_id'] for p in projects]

        tally_map = self._get_bulk_tally_data(project_ids)

        # Build VendorCard lookup for canonical names
        card_lookup = self._build_vendor_card_lookup()

        vendor_data = {}
        for project in projects:
            raw_name = project['vendor_name'] or ''
            card_info = card_lookup.get(raw_name)
            if not card_info:
                continue  # Skip projects without a VendorCard
            display_name = card_info['display_name']
            vendor_code = card_info['vendor_code']

            if display_name not in vendor_data:
                vendor_data[display_name] = {
                    'vendor_name': display_name,
                    'vendor_code': vendor_code,
                    'raw_names': set(),
                    'project_count': 0,
                    'total_revenue': Decimal('0'),
                    'total_purchase': Decimal('0'),
                    'total_expenses': Decimal('0'),
                    'total_payments': Decimal('0'),
                    'total_collections': Decimal('0'),
                    'project_codes': [],
                }

            ZERO = Decimal('0')
            tally = tally_map.get(project['project_id'], {
                'revenue': ZERO, 'purchase': ZERO, 'expenses': ZERO,
                'payments': ZERO, 'collections': ZERO, 'profit': ZERO
            })
            vendor_data[display_name]['raw_names'].add(raw_name)
            vendor_data[display_name]['project_count'] += 1
            vendor_data[display_name]['total_revenue'] += tally['revenue']
            vendor_data[display_name]['total_purchase'] += tally['purchase']
            vendor_data[display_name]['total_expenses'] += tally['expenses']
            vendor_data[display_name]['total_payments'] += tally['payments']
            vendor_data[display_name]['total_collections'] += tally['collections']
            vendor_data[display_name]['project_codes'].append(project['code'])

        result = []
        for vendor_name, data in vendor_data.items():
            profit = data['total_revenue'] - data['total_purchase']
            margin = (profit / data['total_revenue'] * 100) if data['total_revenue'] > 0 else 0

            result.append({
                'vendor_name': vendor_name,
                'vendor_code': data['vendor_code'],
                'raw_names': list(data['raw_names']),
                'project_count': data['project_count'],
                'project_codes': data['project_codes'],
                'lifetime_revenue': data['total_revenue'],
                'lifetime_purchase': data['total_purchase'],
                'lifetime_expenses': data['total_expenses'],
                'lifetime_payments': data['total_payments'],
                'lifetime_collections': data['total_collections'],
                'lifetime_profit': profit,
                'profit_margin': margin,
                'avg_revenue_per_project': data['total_revenue'] / data['project_count'] if data['project_count'] > 0 else 0,
            })

        result.sort(key=lambda x: (x['vendor_name'] or '').lower())
        return result
