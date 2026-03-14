"""
Shared GST utility for TallySync services.

All Sales/Credit Note/Purchase/Debit Note voucher amounts in Tally include GST.
To get net-of-GST amounts, we deduct the GST ledger entries from the voucher amount.

GST is stored on separate TallyVoucherLedgerEntry rows (IGST/CGST/SGST ledger names),
with amounts in cgst_amount, sgst_amount, igst_amount fields.

Usage in CC-alloc based services:
    from integrations.tallysync.services.gst_utils import voucher_gst_subquery, net_amount_expr

    # In an .annotate() or Sum filter:
    net_sales = Sum(
        net_amount_expr('amount'),
        filter=Q(ledger_entry__voucher__voucher_type='Sales')
    )

Usage in voucher-based services (financial_analytics_service):
    from integrations.tallysync.services.gst_utils import voucher_net_amount_subquery
"""
from django.db.models import Sum, F, OuterRef, Subquery, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce
from decimal import Decimal


def voucher_gst_subquery():
    """
    Subquery: total GST (cgst + sgst + igst) for a voucher referenced via
    ledger_entry__voucher (i.e. from TallyVoucherCostCentreAllocation).
    Returns the total GST amount for the outer voucher.
    """
    from integrations.tallysync.models import TallyVoucherLedgerEntry
    return Subquery(
        TallyVoucherLedgerEntry.objects.filter(
            voucher=OuterRef('ledger_entry__voucher')
        ).values('voucher').annotate(
            total_gst=Sum(F('cgst_amount') + F('sgst_amount') + F('igst_amount'))
        ).values('total_gst'),
        output_field=DecimalField()
    )


def net_alloc_amount():
    """
    Expression: cc_alloc.amount - voucher GST.
    For use in ExpressionWrapper or Sum inside CC-alloc querysets.
    Each CC alloc row gets reduced by the full GST of its voucher
    (safe because every Sales/Purchase voucher has exactly 1 CC alloc).
    """
    return ExpressionWrapper(
        F('amount') - Coalesce(voucher_gst_subquery(), Decimal('0'), output_field=DecimalField()),
        output_field=DecimalField()
    )


def voucher_gst_subquery_direct():
    """
    Subquery: total GST for a TallyVoucher (for use in voucher-level querysets,
    i.e. from TallyVoucher directly, not via CC alloc).
    """
    from integrations.tallysync.models import TallyVoucherLedgerEntry
    return Subquery(
        TallyVoucherLedgerEntry.objects.filter(
            voucher=OuterRef('pk')
        ).values('voucher').annotate(
            total_gst=Sum(F('cgst_amount') + F('sgst_amount') + F('igst_amount'))
        ).values('total_gst'),
        output_field=DecimalField()
    )
