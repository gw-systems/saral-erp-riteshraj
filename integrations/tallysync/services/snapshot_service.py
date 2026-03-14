import logging
from django.db.models import Sum, Count, Q, DecimalField, Value as V
from django.db.models.functions import Coalesce
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from integrations.tallysync.models import TallyVoucher, TallyVoucherLedgerEntry
from integrations.tallysync.snapshot_models import ProjectFinancialSnapshot, SalespersonSnapshot
from projects.models import ProjectCode
from operations.models import ProjectCard


class SnapshotService:
    """
    Service to populate snapshot tables after Tally sync
    Called automatically by Celery task after voucher sync
    """
    
    def populate_project_snapshots(self, date=None):
        """
        Populate ProjectFinancialSnapshot for all projects — bulk version.
        Replaces N×8 queries with ~6 bulk queries total.
        """
        if date is None:
            date = timezone.now().date()

        logger.info(f"Populating project snapshots for {date}...")

        from integrations.tallysync.models import TallyVoucherCostCentreAllocation, TallyCostCentre
        from django.db.models import Value as V, OuterRef, Subquery
        from operations.models import StorageRate

        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']

        projects = ProjectCode.objects.filter(
            project_status__in=['Active', 'Operation Not Started', 'Notice Period']
        )
        project_ids = list(projects.values_list('project_id', flat=True))

        # --- 1. Bulk aggregate financials by project via cost centre ---
        # One query: group allocations by erp_project, then aggregate voucher amounts by type
        financials_qs = (
            TallyVoucherCostCentreAllocation.objects
            .filter(
                cost_centre__erp_project_id__in=project_ids,
                ledger_entry__voucher__date__lte=date,
            )
            .exclude(ledger_entry__voucher__is_cancelled=True)
            .values('cost_centre__erp_project_id')
            .annotate(
                sales=Coalesce(Sum('ledger_entry__voucher__amount', filter=Q(ledger_entry__voucher__voucher_type='Sales')), V(Decimal('0')), output_field=DecimalField()),
                credit_notes=Coalesce(Sum('ledger_entry__voucher__amount', filter=Q(ledger_entry__voucher__voucher_type='Credit Note')), V(Decimal('0')), output_field=DecimalField()),
                purchases=Coalesce(Sum('ledger_entry__voucher__amount', filter=Q(ledger_entry__voucher__voucher_type__in=PURCHASE_TYPES)), V(Decimal('0')), output_field=DecimalField()),
                debit_notes=Coalesce(Sum('ledger_entry__voucher__amount', filter=Q(ledger_entry__voucher__voucher_type='Debit Note')), V(Decimal('0')), output_field=DecimalField()),
                receipts=Coalesce(Sum('ledger_entry__voucher__amount', filter=Q(ledger_entry__voucher__voucher_type='Receipt')), V(Decimal('0')), output_field=DecimalField()),
                payments=Coalesce(Sum('ledger_entry__voucher__amount', filter=Q(ledger_entry__voucher__voucher_type='Payment')), V(Decimal('0')), output_field=DecimalField()),
                sales_count=Count('ledger_entry__voucher__id', filter=Q(ledger_entry__voucher__voucher_type='Sales'), distinct=True),
                purchase_count=Count('ledger_entry__voucher__id', filter=Q(ledger_entry__voucher__voucher_type__in=PURCHASE_TYPES), distinct=True),
                receipt_count=Count('ledger_entry__voucher__id', filter=Q(ledger_entry__voucher__voucher_type='Receipt'), distinct=True),
                payment_count=Count('ledger_entry__voucher__id', filter=Q(ledger_entry__voucher__voucher_type='Payment'), distinct=True),
            )
        )
        financials_by_project = {row['cost_centre__erp_project_id']: row for row in financials_qs}

        # --- 2. Bulk load contracted_area via StorageRate ---
        area_by_project = {}
        for rate in StorageRate.objects.filter(
            project_card__project_id__in=project_ids,
            minimum_billable_area__isnull=False,
        ).select_related('project_card').order_by('project_card__project_id', 'id'):
            pid = rate.project_card.project_id
            if pid not in area_by_project:
                area_by_project[pid] = rate.minimum_billable_area

        # --- 3. Compute snapshot dicts in Python ---
        snapshots_by_project = {}
        for project in projects:
            fin = financials_by_project.get(project.project_id)
            if not fin:
                data = self._empty_snapshot()
            else:
                revenue = abs(fin['sales']) - abs(fin['credit_notes'])
                expenses = abs(fin['purchases']) - abs(fin['debit_notes'])
                profit = revenue - expenses
                margin_pct = (profit / revenue * 100) if revenue > 0 else Decimal('0')
                total_received = abs(fin['receipts'])
                contracted_area = area_by_project.get(project.project_id, Decimal('0')) or Decimal('0')
                revenue_per_sqft = (revenue / contracted_area) if contracted_area > 0 else Decimal('0')
                profit_per_sqft = (profit / contracted_area) if contracted_area > 0 else Decimal('0')
                data = {
                    'tally_revenue': revenue,
                    'tally_expenses': expenses,
                    'tally_profit': profit,
                    'tally_margin_pct': margin_pct,
                    'total_billed': revenue,
                    'total_received': total_received,
                    'outstanding': revenue - total_received,
                    'contracted_area': contracted_area,
                    'revenue_per_sqft': revenue_per_sqft,
                    'profit_per_sqft': profit_per_sqft,
                    'sales_count': fin['sales_count'],
                    'purchase_count': fin['purchase_count'],
                    'receipt_count': fin['receipt_count'],
                    'payment_count': fin['payment_count'],
                }
            snapshots_by_project[project.project_id] = (project, data)

        # --- 4. Bulk create/update snapshots ---
        existing = {
            s.project_id: s
            for s in ProjectFinancialSnapshot.objects.filter(
                project_id__in=project_ids,
                snapshot_date=date,
            )
        }

        to_create = []
        to_update = []
        update_fields = [
            'tally_revenue', 'tally_expenses', 'tally_profit', 'tally_margin_pct',
            'total_billed', 'total_received', 'outstanding', 'contracted_area',
            'revenue_per_sqft', 'profit_per_sqft',
            'sales_count', 'purchase_count', 'receipt_count', 'payment_count',
        ]

        for project_id, (project, data) in snapshots_by_project.items():
            if project_id in existing:
                snap = existing[project_id]
                for field, val in data.items():
                    setattr(snap, field, val)
                to_update.append(snap)
            else:
                to_create.append(ProjectFinancialSnapshot(
                    project=project,
                    snapshot_date=date,
                    **data,
                ))

        if to_create:
            ProjectFinancialSnapshot.objects.bulk_create(to_create, ignore_conflicts=False)
        if to_update:
            ProjectFinancialSnapshot.objects.bulk_update(to_update, update_fields, batch_size=200)

        created_count = len(to_create)
        updated_count = len(to_update)
        logger.info(f"Snapshots — Created: {created_count}, Updated: {updated_count}")

        return {
            'created': created_count,
            'updated': updated_count,
            'total': created_count + updated_count
        }
    
    def _calculate_project_snapshot(self, project, date):
        """
        Calculate all financial metrics for a single project
        
        Args:
            project: ProjectCode instance
            date: Snapshot date
        
        Returns:
            dict: Snapshot data
        """
        # Get matched Tally cost centre
        from integrations.tallysync.models import TallyCostCentre, TallyVoucherCostCentreAllocation
        
        cost_centre = TallyCostCentre.objects.filter(
            erp_project=project
        ).first()
        
        if not cost_centre:
            # No Tally data for this project
            return self._empty_snapshot()
        
        # Get all voucher allocations for this cost centre up to snapshot date
        allocations = TallyVoucherCostCentreAllocation.objects.filter(
            cost_centre=cost_centre,
            ledger_entry__voucher__date__lte=date
        ).exclude(ledger_entry__voucher__is_cancelled=True).select_related('ledger_entry__voucher')

        # Extract voucher IDs
        voucher_ids = allocations.values_list('ledger_entry__voucher_id', flat=True)
        
        # Get vouchers
        from integrations.tallysync.models import TallyVoucher
        vouchers = TallyVoucher.objects.filter(id__in=voucher_ids)
        
        PURCHASE_TYPES = ['Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm']

        # Revenue = Sales - Credit Notes
        sales_data = vouchers.filter(
            voucher_type='Sales'
        ).exclude(is_cancelled=True).aggregate(
            revenue=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        )
        credit_note_data = vouchers.filter(
            voucher_type='Credit Note'
        ).exclude(is_cancelled=True).aggregate(
            amount=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )

        # Purchase = Purchase types - Debit Notes
        purchase_data = vouchers.filter(
            voucher_type__in=PURCHASE_TYPES
        ).exclude(is_cancelled=True).aggregate(
            expenses=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        )
        debit_note_data = vouchers.filter(
            voucher_type='Debit Note'
        ).exclude(is_cancelled=True).aggregate(
            amount=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )

        # Receipts (for receivables calculation)
        receipt_data = vouchers.filter(
            voucher_type='Receipt'
        ).exclude(is_cancelled=True).aggregate(
            received=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        )

        # Payments (for payables calculation)
        payment_data = vouchers.filter(
            voucher_type='Payment'
        ).exclude(is_cancelled=True).aggregate(
            paid=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id')
        )
        
        # Calculate metrics — net revenue and net purchase
        revenue = abs(sales_data['revenue']) - abs(credit_note_data['amount'])
        expenses = abs(purchase_data['expenses']) - abs(debit_note_data['amount'])
        profit = revenue - expenses
        margin_pct = (profit / revenue * 100) if revenue > 0 else Decimal('0')
        
        # Receivables
        total_billed = revenue
        total_received = abs(receipt_data['received'])
        outstanding = total_billed - total_received
        
        # Get contracted area from ProjectCard → StorageRate
        contracted_area = Decimal('0')
        try:
            card = project.project_cards.first()
            if card:
                rate = card.storage_rates.first()
                if rate and rate.minimum_billable_area:
                    contracted_area = rate.minimum_billable_area
        except Exception:
            pass
        
        # Calculate per-sqft metrics
        revenue_per_sqft = (revenue / contracted_area) if contracted_area > 0 else Decimal('0')
        profit_per_sqft = (profit / contracted_area) if contracted_area > 0 else Decimal('0')
        
        return {
            'tally_revenue': revenue,
            'tally_expenses': expenses,
            'tally_profit': profit,
            'tally_margin_pct': margin_pct,
            'total_billed': total_billed,
            'total_received': total_received,
            'outstanding': outstanding,
            'contracted_area': contracted_area,
            'revenue_per_sqft': revenue_per_sqft,
            'profit_per_sqft': profit_per_sqft,
            'sales_count': sales_data['count'],
            'purchase_count': purchase_data['count'],
            'receipt_count': receipt_data['count'],
            'payment_count': payment_data['count'],
        }
    
    def _empty_snapshot(self):
        """Return empty snapshot data when no Tally data exists"""
        return {
            'tally_revenue': Decimal('0'),
            'tally_expenses': Decimal('0'),
            'tally_profit': Decimal('0'),
            'tally_margin_pct': Decimal('0'),
            'total_billed': Decimal('0'),
            'total_received': Decimal('0'),
            'outstanding': Decimal('0'),
            'contracted_area': Decimal('0'),
            'revenue_per_sqft': Decimal('0'),
            'profit_per_sqft': Decimal('0'),
            'sales_count': 0,
            'purchase_count': 0,
            'receipt_count': 0,
            'payment_count': 0,
        }
    
    def populate_salesperson_snapshots(self, month=None):
        """
        Populate SalespersonSnapshot for all salespeople — bulk version.
        Replaces N×4 queries with ~4 bulk queries total.
        """
        if month is None:
            today = timezone.now().date()
            month = today.replace(day=1)

        logger.info(f"Populating salesperson snapshots for {month.strftime('%B %Y')}...")

        # --- 1. Project counts per salesperson ---
        project_counts = {
            row['sales_manager']: row
            for row in ProjectCode.objects.filter(
                project_status__in=['Active', 'Operation Not Started', 'Notice Period'],
                sales_manager__isnull=False,
            ).exclude(sales_manager='').values('sales_manager').annotate(
                total_projects=Count('id'),
                active_projects=Count('id', filter=Q(project_status='Active')),
            )
        }

        salespeople = list(project_counts.keys())
        if not salespeople:
            return {'created': 0, 'updated': 0, 'total': 0}

        # --- 2. Aggregate project snapshots per salesperson in one query ---
        agg = (
            ProjectFinancialSnapshot.objects
            .filter(
                project__sales_manager__in=salespeople,
                project__project_status__in=['Active', 'Operation Not Started', 'Notice Period'],
                snapshot_date__year=month.year,
                snapshot_date__month=month.month,
            )
            .values('project__sales_manager')
            .annotate(
                revenue=Coalesce(Sum('tally_revenue'), V(Decimal('0')), output_field=DecimalField()),
                expenses=Coalesce(Sum('tally_expenses'), V(Decimal('0')), output_field=DecimalField()),
                profit=Coalesce(Sum('tally_profit'), V(Decimal('0')), output_field=DecimalField()),
                outstanding=Coalesce(Sum('outstanding'), V(Decimal('0')), output_field=DecimalField()),
            )
        )
        financials_by_sp = {row['project__sales_manager']: row for row in agg}

        # --- 3. Compute snapshot dicts ---
        snapshots_data = {}
        for name, counts in project_counts.items():
            fin = financials_by_sp.get(name, {})
            total_projects = counts['total_projects']
            total_revenue = fin.get('revenue', Decimal('0'))
            total_expenses = fin.get('expenses', Decimal('0'))
            total_profit = fin.get('profit', Decimal('0'))
            total_outstanding = fin.get('outstanding', Decimal('0'))
            snapshots_data[name] = {
                'total_projects': total_projects,
                'active_projects': counts['active_projects'],
                'total_revenue': total_revenue,
                'total_expenses': total_expenses,
                'total_profit': total_profit,
                'avg_margin_pct': (total_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0'),
                'total_outstanding': total_outstanding,
                'avg_revenue_per_project': (total_revenue / total_projects) if total_projects > 0 else Decimal('0'),
                'avg_profit_per_project': (total_profit / total_projects) if total_projects > 0 else Decimal('0'),
            }

        # --- 4. Bulk create/update ---
        existing = {
            s.salesperson_name: s
            for s in SalespersonSnapshot.objects.filter(
                salesperson_name__in=salespeople,
                snapshot_month=month,
            )
        }

        update_fields = [
            'total_projects', 'active_projects', 'total_revenue', 'total_expenses',
            'total_profit', 'avg_margin_pct', 'total_outstanding',
            'avg_revenue_per_project', 'avg_profit_per_project',
        ]
        to_create = []
        to_update = []

        for name, data in snapshots_data.items():
            if name in existing:
                snap = existing[name]
                for field, val in data.items():
                    setattr(snap, field, val)
                to_update.append(snap)
            else:
                to_create.append(SalespersonSnapshot(
                    salesperson_name=name,
                    snapshot_month=month,
                    **data,
                ))

        if to_create:
            SalespersonSnapshot.objects.bulk_create(to_create, ignore_conflicts=False)
        if to_update:
            SalespersonSnapshot.objects.bulk_update(to_update, update_fields, batch_size=200)

        created_count = len(to_create)
        updated_count = len(to_update)
        logger.info(f"Salesperson snapshots — Created: {created_count}, Updated: {updated_count}")

        return {
            'created': created_count,
            'updated': updated_count,
            'total': created_count + updated_count
        }
    
    def _calculate_salesperson_snapshot(self, salesperson_name, month):
        """Calculate metrics for a salesperson for given month"""
        
        # Get their projects
        projects = ProjectCode.objects.filter(sales_manager=salesperson_name)
        
        total_projects = projects.count()
        active_projects = projects.filter(project_status='Active').count()
        
        # Get latest snapshots for all their projects
        latest_snapshots = ProjectFinancialSnapshot.objects.filter(
            project__in=projects,
            snapshot_date__year=month.year,
            snapshot_date__month=month.month
        ).order_by('project', '-snapshot_date').distinct('project')
        
        # Aggregate
        totals = latest_snapshots.aggregate(
            revenue=Coalesce(Sum('tally_revenue'), Decimal('0'), output_field=DecimalField()),
            expenses=Coalesce(Sum('tally_expenses'), Decimal('0'), output_field=DecimalField()),
            profit=Coalesce(Sum('tally_profit'), Decimal('0'), output_field=DecimalField()),
            outstanding=Coalesce(Sum('outstanding'), Decimal('0'), output_field=DecimalField()),
        )
        
        total_revenue = totals['revenue']
        total_expenses = totals['expenses']
        total_profit = totals['profit']
        total_outstanding = totals['outstanding']
        
        avg_margin_pct = (total_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0')
        avg_revenue_per_project = (total_revenue / total_projects) if total_projects > 0 else Decimal('0')
        avg_profit_per_project = (total_profit / total_projects) if total_projects > 0 else Decimal('0')
        
        return {
            'total_projects': total_projects,
            'active_projects': active_projects,
            'total_revenue': total_revenue,
            'total_expenses': total_expenses,
            'total_profit': total_profit,
            'avg_margin_pct': avg_margin_pct,
            'total_outstanding': total_outstanding,
            'avg_revenue_per_project': avg_revenue_per_project,
            'avg_profit_per_project': avg_profit_per_project,
        }