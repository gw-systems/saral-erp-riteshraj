from django.db.models import Sum, Count, Q, Max, DecimalField, Value, F, ExpressionWrapper
from django.db.models.functions import Coalesce
from integrations.tallysync.models import TallyVoucher, TallyVoucherCostCentreAllocation
from integrations.tallysync.services.gst_utils import net_alloc_amount
from projects.models import ProjectCode
from projects.models_client import ClientCard, ClientGroup
from datetime import datetime, timedelta
from decimal import Decimal


class ClientAnalyticsService:
    """Service for client-level analytics and behavior tracking"""

    def __init__(self, start_date=None, end_date=None):
        self.start_date = start_date
        self.end_date = end_date

    def _build_client_card_lookup(self):
        """Build lookup: client_legal_name → {card_code, group_name, display_name}"""
        cards = ClientCard.objects.select_related('client_group').values(
            'client_code', 'client_legal_name', 'client_short_name',
            'client_group__name',
        )
        lookup = {}
        for c in cards:
            lookup[c['client_legal_name']] = {
                'client_code': c['client_code'],
                'display_name': c['client_legal_name'],
                'group_name': c['client_group__name'],
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
            transaction_count=Count('ledger_entry__voucher', distinct=True),
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
                'transaction_count': row['transaction_count'],
            }
        return result

    def _get_bulk_payment_stats(self, client_names):
        """Get payment behavior stats for all clients in a single query.
        Returns dict: {client_name: {'total_invoices': N, ...}}
        """
        vouchers = TallyVoucher.objects.filter(
            voucher_type='Sales',
            ledger_entries__cost_allocations__cost_centre__erp_project__client_name__in=client_names,
        ).distinct()

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

        rows = vouchers.values(
            'ledger_entries__cost_allocations__cost_centre__erp_project__client_name'
        ).annotate(
            total_invoices=Count('id', distinct=True),
        )

        result = {}
        for row in rows:
            cn = row['ledger_entries__cost_allocations__cost_centre__erp_project__client_name']
            result[cn] = {
                'total_invoices': row['total_invoices'],
                'avg_delay_days': 0,
                'payment_terms': 'N/A',
            }
        return result

    def _get_bulk_active_status(self, client_names):
        """Check which clients have recent activity in a single query.
        Returns set of active client names.
        """
        cutoff_date = datetime.now().date() - timedelta(days=90)

        active_rows = TallyVoucher.objects.filter(
            ledger_entries__cost_allocations__cost_centre__erp_project__client_name__in=client_names,
            billing_month_date__gte=cutoff_date,
        ).values(
            'ledger_entries__cost_allocations__cost_centre__erp_project__client_name'
        ).distinct()

        return {row['ledger_entries__cost_allocations__cost_centre__erp_project__client_name'] for row in active_rows}

    def get_all_clients_summary(self):
        """Get analytics for all clients — bulk queries only.
        Uses ClientCard names where available, falls back to ProjectCode.client_name.
        Includes client_group for consolidated reporting.
        """

        # Get all projects with client names
        projects = list(ProjectCode.objects.values('project_id', 'client_name', 'code'))
        project_ids = [p['project_id'] for p in projects]

        # Single query: Tally financials per project
        tally_map = self._get_bulk_tally_data(project_ids)

        # Build ClientCard lookup for canonical names + groups
        card_lookup = self._build_client_card_lookup()

        # Group by client in Python — only include projects with a matching ClientCard
        client_data = {}
        for project in projects:
            raw_name = project['client_name'] or ''
            card_info = card_lookup.get(raw_name)
            if not card_info:
                continue  # Skip projects without a ClientCard
            display_name = card_info['display_name']
            group_name = card_info['group_name']
            client_code = card_info['client_code']

            if display_name not in client_data:
                client_data[display_name] = {
                    'client_name': display_name,
                    'client_code': client_code,
                    'client_group': group_name,
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
                'payments': ZERO, 'collections': ZERO, 'profit': ZERO, 'transaction_count': 0
            })
            client_data[display_name]['raw_names'].add(raw_name)
            client_data[display_name]['project_count'] += 1
            client_data[display_name]['total_revenue'] += tally['revenue']
            client_data[display_name]['total_purchase'] += tally['purchase']
            client_data[display_name]['total_expenses'] += tally['expenses']
            client_data[display_name]['total_payments'] += tally['payments']
            client_data[display_name]['total_collections'] += tally['collections']
            client_data[display_name]['project_codes'].append(project['code'])

        client_names = list(client_data.keys())

        # Bulk queries: payment stats + active status
        payment_map = self._get_bulk_payment_stats(client_names)
        active_set = self._get_bulk_active_status(client_names)

        default_payment = {'total_invoices': 0, 'avg_delay_days': 0, 'payment_terms': 'Unknown'}

        result = []
        for client_name, data in client_data.items():
            profit = data['total_revenue'] - data['total_purchase']
            margin = (profit / data['total_revenue'] * 100) if data['total_revenue'] > 0 else 0

            payment_stats = payment_map.get(client_name, default_payment)
            is_active = client_name in active_set
            risk_score = self._calculate_risk_score_fast(data, payment_stats, is_active)

            result.append({
                'client_name': client_name,
                'client_code': data['client_code'],
                'client_group': data['client_group'],
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
                'payment_behavior': payment_stats,
                'is_active': is_active,
                'risk_score': risk_score,
            })

        result.sort(key=lambda x: (x['client_name'] or '').lower())
        return result

    def get_client_detail(self, client_name):
        """Get detailed analytics for a single client"""

        projects = list(ProjectCode.objects.filter(
            client_name=client_name
        ).exclude(
            project_status='Inactive'
        ).values('project_id', 'project_code', 'code', 'vendor_name', 'location'))

        project_ids = [p['project_id'] for p in projects]

        # Bulk tally data
        tally_map = self._get_bulk_tally_data(project_ids)

        project_details = []
        total_revenue = Decimal('0')
        total_purchase = Decimal('0')

        ZERO = Decimal('0')
        for project in projects:
            tally = tally_map.get(project['project_id'], {
                'revenue': ZERO, 'purchase': ZERO, 'expenses': ZERO,
                'payments': ZERO, 'collections': ZERO, 'profit': ZERO, 'transaction_count': 0
            })

            project_details.append({
                'project_code': project['project_code'],
                'code': project['code'],
                'vendor_name': project['vendor_name'],
                'location': project['location'],
                'revenue': tally['revenue'],
                'purchase': tally['purchase'],
                'expenses': tally['expenses'],
                'payments': tally['payments'],
                'collections': tally['collections'],
                'profit': tally['profit'],
                'transaction_count': tally['transaction_count'],
            })

            total_revenue += tally['revenue']
            total_purchase += tally['purchase']

        # Payment + transactions
        payment_stats = self._get_bulk_payment_stats([client_name]).get(
            client_name, {'total_invoices': 0, 'avg_delay_days': 0, 'payment_terms': 'Unknown'}
        )

        transactions = self._get_client_transactions(client_name)
        is_active = client_name in self._get_bulk_active_status([client_name])

        risk_factors = []
        if payment_stats['avg_delay_days'] > 30:
            risk_factors.append(f"Payment delays averaging {payment_stats['avg_delay_days']} days")
        if not is_active:
            risk_factors.append("No recent activity in last 90 days")

        total_profit = total_revenue - total_purchase
        return {
            'client_name': client_name,
            'summary': {
                'project_count': len(projects),
                'total_revenue': total_revenue,
                'total_purchase': total_purchase,
                'total_profit': total_profit,
                'profit_margin': (total_profit / total_revenue * 100) if total_revenue > 0 else 0,
            },
            'projects': project_details,
            'payment_behavior': payment_stats,
            'recent_transactions': transactions[:10],
            'risk_assessment': {
                'risk_level': 'High' if len(risk_factors) >= 2 else 'Medium' if len(risk_factors) == 1 else 'Low',
                'risk_factors': risk_factors,
            }
        }

    def get_top_clients(self, limit=10):
        """Get top N clients by revenue"""
        all_clients = self.get_all_clients_summary()
        all_clients.sort(key=lambda x: x['lifetime_revenue'], reverse=True)
        return all_clients[:limit]

    def get_clients_by_payment_behavior(self, behavior='delayed'):
        """Get clients filtered by payment behavior"""
        all_clients = self.get_all_clients_summary()

        if behavior == 'delayed':
            return [c for c in all_clients if c['payment_behavior']['avg_delay_days'] > 30]
        elif behavior == 'prompt':
            return [c for c in all_clients if c['payment_behavior']['avg_delay_days'] <= 7]
        elif behavior == 'risky':
            return [c for c in all_clients if c['risk_score'] >= 70]

        return all_clients

    def _get_client_transactions(self, client_name):
        """Get recent transaction history for a client"""
        project_ids = list(ProjectCode.objects.filter(
            client_name=client_name
        ).values_list('project_id', flat=True))

        vouchers = TallyVoucher.objects.filter(
            ledger_entries__cost_allocations__cost_centre__erp_project__project_id__in=project_ids
        ).distinct().select_related('company').order_by('-date')[:20]

        return [
            {
                'date': v.date,
                'voucher_type': v.voucher_type,
                'voucher_number': v.voucher_number,
                'amount': v.amount,
                'company': v.company.name,
            }
            for v in vouchers
        ]

    def _calculate_risk_score_fast(self, client_data, payment_stats, is_active):
        """Calculate risk score without extra DB queries"""
        risk_score = 0

        if payment_stats['avg_delay_days'] > 60:
            risk_score += 40
        elif payment_stats['avg_delay_days'] > 30:
            risk_score += 20

        if client_data['total_revenue'] > 0:
            margin = (client_data['total_revenue'] - client_data['total_purchase']) / client_data['total_revenue'] * 100
            if margin < 10:
                risk_score += 30
            elif margin < 20:
                risk_score += 15

        if not is_active:
            risk_score += 30

        return min(risk_score, 100)
