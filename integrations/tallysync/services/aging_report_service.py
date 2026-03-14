import re
from django.db.models import Sum, Q, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from integrations.tallysync.models import TallyBillReference
from decimal import Decimal


# Voucher types that create a new bill (receivable or payable)
RECEIVABLE_NEW_REF_TYPES = {'Sales', 'Credit Note'}
PAYABLE_NEW_REF_TYPES = {
    'Purchase', 'Purchase Expenses', 'Purchase Rcm', 'Purchae Rcm', 'Debit Note'
}


class AgingReportService:
    """
    Bill-by-bill aging using TallyBillReference (BILLALLOCATIONS.LIST).

    Logic:
      - Each bill has one or more TallyBillReference rows.
      - bill_type='New Ref'  → creates the outstanding (invoice raised).
      - bill_type='Agst Ref' → settles the outstanding (receipt/payment/journal/write-off).
      - bill_type='Advance'  → advance payment (shown separately, not in outstanding).

      Outstanding per bill = SUM(New Ref amounts) - SUM(Agst Ref amounts)

      Aging bucket is based on the invoice date (the New Ref voucher's date).
      If outstanding > 0, the bill is still open and aged from that date.

    This correctly handles:
      - Credit Notes reducing receivables (Agst Ref on Sales bills)
      - Debit Notes reducing payables (Agst Ref on Purchase bills)
      - Write-offs via Journal vouchers (Agst Ref type)
      - Partial payments
      - All purchase variants (Purchase Rcm, Purchase Expenses, etc.)
    """

    def __init__(self, company_id=None):
        self.company_id = company_id
        self.today = timezone.now().date()

    def _base_bill_refs(self):
        """Base queryset — all bill refs, optionally filtered by company."""
        qs = TallyBillReference.objects.filter(
            ledger_entry__voucher__is_cancelled=False,
        )
        if self.company_id:
            qs = qs.filter(ledger_entry__voucher__company_id=self.company_id)
        return qs

    @staticmethod
    def _get_active_receivable_parties():
        """
        Returns a set of Tally party_ledger_name values that belong to clients
        with at least one Active project in the ERP.

        Method: CC name format is "CODE - (ClientName - VendorName (Location))".
        We extract the client name from the CC, match it against ProjectCode
        entries with project_status='Active', then trace back to the
        party_ledger_name on their Sales/Credit Note vouchers.
        """
        from integrations.tallysync.models import TallyVoucherCostCentreAllocation
        from projects.models import ProjectCode

        # Active project client names (lower-cased for matching)
        active_clients = [
            c.lower() for c in
            ProjectCode.objects.filter(project_status='Active')
            .values_list('client_name', flat=True)
            .distinct()
            if c
        ]

        def _client_from_cc(cc_name):
            """Extract client name portion from CC string like 'MH165 - (AAK - Vendor)'."""
            if not cc_name:
                return None
            m = re.search(r'\(([^-\)]+)', cc_name)
            return m.group(1).strip() if m else None

        def _is_active_client(client_str):
            if not client_str:
                return False
            cl = client_str.lower()
            return any(
                ac in cl or cl in ac
                for ac in active_clients
            )

        # Map voucher_id → party_ledger_name for all Sales/Credit Note vouchers
        from django.db.models import F
        voucher_party = dict(
            TallyBillReference.objects.filter(
                bill_type='New Ref',
                ledger_entry__voucher__voucher_type__in=RECEIVABLE_NEW_REF_TYPES,
                ledger_entry__voucher__is_cancelled=False,
            ).values_list('ledger_entry__voucher__id', 'ledger_entry__voucher__party_ledger_name')
            .distinct()
        )

        # For each voucher, get its CC allocations and check if any CC maps to an active client
        cc_allocs = (
            TallyVoucherCostCentreAllocation.objects
            .filter(ledger_entry__voucher_id__in=voucher_party.keys())
            .values('ledger_entry__voucher_id', 'cost_centre_name')
        )

        active_parties = set()
        for row in cc_allocs:
            party = voucher_party.get(row['ledger_entry__voucher_id'])
            if party and party not in active_parties:
                client = _client_from_cc(row['cost_centre_name'])
                if _is_active_client(client):
                    active_parties.add(party)

        return active_parties

    def _bucket(self, days):
        if days <= 30:
            return '0-30'
        elif days <= 60:
            return '31-60'
        elif days <= 90:
            return '61-90'
        return '90+'

    def _build_aging_report(self, new_ref_types, active_only=False):
        """
        Core bill-by-bill aging engine.

        Args:
            new_ref_types: set of voucher_type strings that create New Ref
                           e.g. {'Sales', 'Credit Note'} for receivables
            active_only: if True, only include parties with Active ERP projects

        Returns:
            dict with 'summary' and 'parties' keys.
        """
        active_parties = self._get_active_receivable_parties() if active_only else None
        base = self._base_bill_refs()

        # --- Step 1: Fetch all New Ref rows for the relevant voucher types ---
        # Each row = one bill reference on an invoice voucher
        new_refs = list(
            base.filter(
                bill_type='New Ref',
                ledger_entry__voucher__voucher_type__in=new_ref_types,
            ).values(
                'bill_name',
                'amount',
                'ledger_entry__voucher__date',
                'ledger_entry__voucher__party_ledger_name',
                'ledger_entry__voucher__voucher_type',
            )
        )

        if not new_refs:
            return {'summary': self._empty_summary(), 'parties': []}

        # --- Step 2: Fetch all Agst Ref rows for those same bill_names ---
        bill_names = {r['bill_name'] for r in new_refs}

        # For bills that have a Journal New Ref (inter-company rebook transfers), we need to
        # exclude ONLY the Journal Agst Refs whose amount exactly matches a Journal New Ref amount
        # on the same bill (they are the paired cancellation of the rebook).
        # Journal Agst Refs with a DIFFERENT amount (e.g. TDS deductions) are real settlements
        # and must be included.
        journal_new_ref_amounts = {}  # bill_name -> set of amounts from Journal New Refs
        for row in base.filter(
            bill_type='New Ref',
            bill_name__in=bill_names,
            ledger_entry__voucher__voucher_type='Journal',
        ).values('bill_name', 'amount'):
            journal_new_ref_amounts.setdefault(row['bill_name'], set()).add(row['amount'])

        agst_refs = list(
            base.filter(
                bill_type='Agst Ref',
                bill_name__in=bill_names,
            ).values('bill_name', 'amount', 'ledger_entry__voucher__voucher_type')
        )

        # Build settlement map: bill_name → total settled amount
        # Exclude Journal Agst Refs only when their amount matches a Journal New Ref amount
        # on the same bill (paired inter-company rebook transfer — not a real payment).
        settled = {}
        for r in agst_refs:
            bn = r['bill_name']
            vtype = r['ledger_entry__voucher__voucher_type']
            if vtype == 'Journal' and r['amount'] in journal_new_ref_amounts.get(bn, set()):
                continue  # paired rebook cancellation, skip
            settled[bn] = settled.get(bn, Decimal('0')) + r['amount']

        # --- Step 3: Aggregate New Refs by bill_name (can have multiple rows per bill) ---
        bills = {}
        for r in new_refs:
            bn = r['bill_name']
            if bn not in bills:
                bills[bn] = {
                    'bill_name': bn,
                    'party': r['ledger_entry__voucher__party_ledger_name'] or '',
                    'invoice_date': r['ledger_entry__voucher__date'],
                    'voucher_type': r['ledger_entry__voucher__voucher_type'],
                    'invoiced': Decimal('0'),
                }
            bills[bn]['invoiced'] += r['amount']
            # Keep earliest voucher date if multiple rows per bill
            voucher_date = r['ledger_entry__voucher__date']
            if voucher_date and (
                bills[bn]['invoice_date'] is None or
                voucher_date < bills[bn]['invoice_date']
            ):
                bills[bn]['invoice_date'] = voucher_date

        # --- Step 4: Compute outstanding per bill, bucket by invoice age ---
        # Credit Notes create New Ref with positive amounts but reduce receivables —
        # treat their invoiced amount as negative (they reduce outstanding)
        REDUCING_TYPES = {'Credit Note', 'Debit Note'}

        party_bills = {}  # party_name → list of open bills

        for bn, bill in bills.items():
            invoiced = bill['invoiced']
            # Credit Notes / Debit Notes reduce the balance
            if bill['voucher_type'] in REDUCING_TYPES:
                invoiced = -invoiced

            total_settled = settled.get(bn, Decimal('0'))
            outstanding = invoiced - total_settled

            if outstanding <= Decimal('0'):
                continue  # fully settled

            invoice_date = bill['invoice_date']
            days_old = (self.today - invoice_date).days if invoice_date else 0
            bucket = self._bucket(days_old)

            party = bill['party']
            if active_only and active_parties is not None and party not in active_parties:
                continue
            if party not in party_bills:
                party_bills[party] = {
                    'invoiced': Decimal('0'),
                    'settled': Decimal('0'),
                    'outstanding': Decimal('0'),
                    'aging_0_30': Decimal('0'),
                    'aging_31_60': Decimal('0'),
                    'aging_61_90': Decimal('0'),
                    'aging_90_plus': Decimal('0'),
                    'bill_count': 0,
                    'oldest_date': None,
                }

            pb = party_bills[party]
            pb['invoiced'] += invoiced
            pb['settled'] += total_settled
            pb['outstanding'] += outstanding
            pb['bill_count'] += 1
            bucket_key = {'0-30': 'aging_0_30', '31-60': 'aging_31_60', '61-90': 'aging_61_90', '90+': 'aging_90_plus'}[bucket]
            pb[bucket_key] += outstanding

            if invoice_date and (pb['oldest_date'] is None or invoice_date < pb['oldest_date']):
                pb['oldest_date'] = invoice_date

        # --- Step 5: Build response ---
        parties = []
        summary = self._empty_summary()

        for party_name, pb in party_bills.items():
            oldest_date = pb['oldest_date']
            days_oldest = (self.today - oldest_date).days if oldest_date else 0

            parties.append({
                'party_name': party_name,
                'total_billed': pb['invoiced'],
                'total_received': pb['settled'],
                'outstanding': pb['outstanding'],
                'aging_0_30': pb['aging_0_30'],
                'aging_31_60': pb['aging_31_60'],
                'aging_61_90': pb['aging_61_90'],
                'aging_90_plus': pb['aging_90_plus'],
                'days_oldest': days_oldest,
                'bill_count': pb['bill_count'],
            })

            summary['total_outstanding'] += pb['outstanding']
            summary['aging_0_30'] += pb['aging_0_30']
            summary['aging_31_60'] += pb['aging_31_60']
            summary['aging_61_90'] += pb['aging_61_90']
            summary['aging_90_plus'] += pb['aging_90_plus']

        summary['party_count'] = len(parties)
        parties.sort(key=lambda p: p['outstanding'], reverse=True)

        return {'summary': summary, 'parties': parties}

    def _empty_summary(self):
        return {
            'total_outstanding': Decimal('0'),
            'aging_0_30': Decimal('0'),
            'aging_31_60': Decimal('0'),
            'aging_61_90': Decimal('0'),
            'aging_90_plus': Decimal('0'),
            'party_count': 0,
        }

    def get_receivables_aging(self, active_only=False):
        return self._build_aging_report(RECEIVABLE_NEW_REF_TYPES, active_only=active_only)

    def get_payables_aging(self):
        return self._build_aging_report(PAYABLE_NEW_REF_TYPES)

    def get_party_detail(self, party_name, report_type='receivables'):
        """
        Bill-level detail for a specific party.
        Shows each open bill with its invoice date, invoiced amount,
        settled amount, outstanding, and aging bucket.
        Also lists all settlement vouchers (receipts/payments/journals/write-offs).
        """
        new_ref_types = (
            RECEIVABLE_NEW_REF_TYPES if report_type == 'receivables'
            else PAYABLE_NEW_REF_TYPES
        )
        REDUCING_TYPES = {'Credit Note', 'Debit Note'}

        base = self._base_bill_refs()

        # New Refs for this party
        new_refs = list(
            base.filter(
                bill_type='New Ref',
                ledger_entry__voucher__voucher_type__in=new_ref_types,
                ledger_entry__voucher__party_ledger_name=party_name,
            ).values(
                'bill_name',
                'amount',
                'ledger_entry__voucher__id',
                'ledger_entry__voucher__voucher_number',
                'ledger_entry__voucher__date',
                'ledger_entry__voucher__billing_month',
                'ledger_entry__voucher__voucher_type',
                'ledger_entry__voucher__reference',
                'ledger_entry__voucher__narration',
            ).order_by('ledger_entry__voucher__date')
        )

        # All bill names; party is known (the filter param)
        bill_names = {r['bill_name'] for r in new_refs}

        # For bills with a Journal New Ref (inter-company rebook), exclude only the Journal Agst
        # Refs whose amount exactly matches the Journal New Ref amount (paired cancellation).
        # Different-amount Journal Agst Refs (TDS, deductions) are real settlements — include them.
        journal_new_ref_amounts = {}  # bill_name -> set of amounts
        for row in base.filter(
            bill_type='New Ref',
            bill_name__in=bill_names,
            ledger_entry__voucher__voucher_type='Journal',
        ).values('bill_name', 'amount'):
            journal_new_ref_amounts.setdefault(row['bill_name'], set()).add(row['amount'])

        # All Agst Refs for those bills
        agst_refs = list(
            base.filter(
                bill_type='Agst Ref',
                bill_name__in=bill_names,
            ).values(
                'bill_name',
                'amount',
                'ledger_entry__voucher__id',
                'ledger_entry__voucher__voucher_number',
                'ledger_entry__voucher__date',
                'ledger_entry__voucher__voucher_type',
                'ledger_entry__voucher__narration',
            ).order_by('ledger_entry__voucher__date')
        )

        # Group Agst Refs by bill_name
        # Exclude Journal Agst Refs only when amount matches a Journal New Ref amount (paired rebook)
        settlements_by_bill = {}
        for r in agst_refs:
            bn = r['bill_name']
            vtype = r['ledger_entry__voucher__voucher_type']
            if vtype == 'Journal' and r['amount'] in journal_new_ref_amounts.get(bn, set()):
                continue  # paired inter-company rebook cancellation, skip
            if bn not in settlements_by_bill:
                settlements_by_bill[bn] = []
            settlements_by_bill[bn].append({
                'voucher_id': r['ledger_entry__voucher__id'],
                'voucher_number': r['ledger_entry__voucher__voucher_number'],
                'date': r['ledger_entry__voucher__date'],
                'voucher_type': r['ledger_entry__voucher__voucher_type'],
                'narration': r['ledger_entry__voucher__narration'],
                'amount': r['amount'],
            })

        # Aggregate New Refs by bill_name
        bills_map = {}
        for r in new_refs:
            bn = r['bill_name']
            if bn not in bills_map:
                bills_map[bn] = {
                    'bill_name': bn,
                    'voucher_id': r['ledger_entry__voucher__id'],
                    'voucher_number': r['ledger_entry__voucher__voucher_number'],
                    'date': r['ledger_entry__voucher__date'],
                    'billing_month': r['ledger_entry__voucher__billing_month'] or '',
                    'voucher_type': r['ledger_entry__voucher__voucher_type'],
                    'reference': r['ledger_entry__voucher__reference'],
                    'narration': r['ledger_entry__voucher__narration'],
                    'invoiced': Decimal('0'),
                }
            bills_map[bn]['invoiced'] += r['amount']

        # Cost centre lookup: voucher_id -> primary CC name (highest allocation amount)
        from integrations.tallysync.models import TallyVoucherCostCentreAllocation
        from django.db.models import Sum as _Sum
        voucher_ids = {b['voucher_id'] for b in bills_map.values()}
        voucher_cc = {}
        for row in (
            TallyVoucherCostCentreAllocation.objects
            .filter(ledger_entry__voucher_id__in=voucher_ids)
            .values('ledger_entry__voucher_id', 'cost_centre_name')
            .annotate(cc_amount=_Sum('amount'))
            .order_by('ledger_entry__voucher_id', '-cc_amount')
        ):
            vid = row['ledger_entry__voucher_id']
            if vid not in voucher_cc:  # keep only the first (highest) CC per voucher
                voucher_cc[vid] = row['cost_centre_name'] or ''

        # Build bill list with outstanding
        bill_list = []
        total_invoiced = Decimal('0')
        total_settled = Decimal('0')
        total_outstanding = Decimal('0')

        for bn, bill in sorted(bills_map.items(), key=lambda x: x[1]['date'] or self.today):
            invoiced = bill['invoiced']
            if bill['voucher_type'] in REDUCING_TYPES:
                invoiced = -invoiced

            settled_amount = sum(s['amount'] for s in settlements_by_bill.get(bn, []))
            outstanding = invoiced - settled_amount

            invoice_date = bill['date']
            days_old = (self.today - invoice_date).days if invoice_date else 0

            bill_list.append({
                'bill_name': bn,
                'voucher_id': bill['voucher_id'],
                'voucher_number': bill['voucher_number'],
                'date': invoice_date,
                'billing_month': bill['billing_month'],
                'days_old': days_old,
                'bucket': self._bucket(days_old),
                'voucher_type': bill['voucher_type'],
                'reference': bill['reference'],
                'invoiced': invoiced,
                'settled': settled_amount,
                'outstanding': outstanding,
                'settlements': settlements_by_bill.get(bn, []),
                'cost_centre': voucher_cc.get(bill['voucher_id'], ''),
            })

            total_invoiced += invoiced
            total_settled += settled_amount
            total_outstanding += outstanding

        return {
            'party_name': party_name,
            'report_type': report_type,
            'total_billed': total_invoiced,
            'total_paid': total_settled,
            'outstanding': total_outstanding,
            'bills': bill_list,
        }

    def get_project_wise_aging(self, report_type='receivables'):
        """
        Project (cost centre) wise aging.

        For each open bill, look up the cost centre allocations on the same voucher.
        A bill may touch multiple cost centres; we apportion the outstanding amount
        proportionally to the cost allocation amounts.

        Returns a list of rows:
          project_name, party_name, bill_name, date, days_old, bucket,
          invoiced, settled, outstanding
        sorted by project_name then outstanding desc.
        """
        from integrations.tallysync.models import TallyVoucherCostCentreAllocation
        from django.db.models import Sum

        new_ref_types = (
            RECEIVABLE_NEW_REF_TYPES if report_type == 'receivables'
            else PAYABLE_NEW_REF_TYPES
        )
        REDUCING_TYPES = {'Credit Note', 'Debit Note'}

        base = self._base_bill_refs()

        # Fetch New Refs with voucher id for CC lookup
        new_refs = list(
            base.filter(
                bill_type='New Ref',
                ledger_entry__voucher__voucher_type__in=new_ref_types,
            ).values(
                'bill_name',
                'amount',
                'ledger_entry__voucher__id',
                'ledger_entry__voucher__date',
                'ledger_entry__voucher__party_ledger_name',
                'ledger_entry__voucher__voucher_type',
            )
        )

        if not new_refs:
            return []

        bill_names = {r['bill_name'] for r in new_refs}
        voucher_ids = {r['ledger_entry__voucher__id'] for r in new_refs}

        # For bills with a Journal New Ref (inter-company rebook), exclude only the Journal Agst
        # Refs whose amount exactly matches the Journal New Ref amount (paired cancellation).
        journal_new_ref_amounts = {}  # bill_name -> set of amounts
        for row in base.filter(
            bill_type='New Ref',
            bill_name__in=bill_names,
            ledger_entry__voucher__voucher_type='Journal',
        ).values('bill_name', 'amount'):
            journal_new_ref_amounts.setdefault(row['bill_name'], set()).add(row['amount'])

        agst_refs = list(
            base.filter(bill_type='Agst Ref', bill_name__in=bill_names)
            .values('bill_name', 'amount', 'ledger_entry__voucher__voucher_type')
        )
        settled = {}
        for r in agst_refs:
            bn = r['bill_name']
            vtype = r['ledger_entry__voucher__voucher_type']
            if vtype == 'Journal' and r['amount'] in journal_new_ref_amounts.get(bn, set()):
                continue  # paired inter-company rebook cancellation, skip
            settled[bn] = settled.get(bn, Decimal('0')) + r['amount']

        # Aggregate New Refs by bill_name
        bills = {}
        for r in new_refs:
            bn = r['bill_name']
            if bn not in bills:
                bills[bn] = {
                    'bill_name': bn,
                    'voucher_id': r['ledger_entry__voucher__id'],
                    'party': r['ledger_entry__voucher__party_ledger_name'] or '',
                    'invoice_date': r['ledger_entry__voucher__date'],
                    'voucher_type': r['ledger_entry__voucher__voucher_type'],
                    'invoiced': Decimal('0'),
                }
            bills[bn]['invoiced'] += r['amount']
            vdate = r['ledger_entry__voucher__date']
            if vdate and (bills[bn]['invoice_date'] is None or vdate < bills[bn]['invoice_date']):
                bills[bn]['invoice_date'] = vdate

        # Cost centre allocations per voucher
        cc_qs = (
            TallyVoucherCostCentreAllocation.objects
            .filter(ledger_entry__voucher_id__in=voucher_ids)
            .values('ledger_entry__voucher_id', 'cost_centre_name')
            .annotate(cc_amount=Sum('amount'))
        )
        # voucher_id -> list of (cc_name, cc_amount)
        voucher_cc = {}
        for row in cc_qs:
            vid = row['ledger_entry__voucher_id']
            voucher_cc.setdefault(vid, []).append((
                row['cost_centre_name'] or 'No Project',
                abs(row['cc_amount'] or Decimal('0'))
            ))

        # Build project-wise rows
        rows = []
        for bn, bill in bills.items():
            invoiced = bill['invoiced']
            if bill['voucher_type'] in REDUCING_TYPES:
                invoiced = -invoiced

            total_settled = settled.get(bn, Decimal('0'))
            outstanding = invoiced - total_settled

            if outstanding <= Decimal('0'):
                continue

            invoice_date = bill['invoice_date']
            days_old = (self.today - invoice_date).days if invoice_date else 0
            bucket = self._bucket(days_old)

            # Find cost centres for this bill's voucher
            cc_list = voucher_cc.get(bill['voucher_id'], [])
            if cc_list:
                # Apportion outstanding proportionally
                total_cc_amount = sum(a for _, a in cc_list) or Decimal('1')
                for cc_name, cc_amount in cc_list:
                    proportion = cc_amount / total_cc_amount
                    rows.append({
                        'project_name': cc_name,
                        'party_name': bill['party'],
                        'bill_name': bn,
                        'date': invoice_date,
                        'days_old': days_old,
                        'bucket': bucket,
                        'invoiced': (invoiced * proportion).quantize(Decimal('0.01')),
                        'settled': (total_settled * proportion).quantize(Decimal('0.01')),
                        'outstanding': (outstanding * proportion).quantize(Decimal('0.01')),
                    })
            else:
                rows.append({
                    'project_name': 'No Project',
                    'party_name': bill['party'],
                    'bill_name': bn,
                    'date': invoice_date,
                    'days_old': days_old,
                    'bucket': bucket,
                    'invoiced': invoiced,
                    'settled': total_settled,
                    'outstanding': outstanding,
                })

        rows.sort(key=lambda r: (r['project_name'], -float(r['outstanding'])))
        return rows

    def get_aging_summary(self):
        receivables = self.get_receivables_aging()
        payables = self.get_payables_aging()
        return {
            'receivables': receivables['summary'],
            'payables': payables['summary'],
            'net_position': (
                receivables['summary']['total_outstanding']
                - payables['summary']['total_outstanding']
            ),
        }
