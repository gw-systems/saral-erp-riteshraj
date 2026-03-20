from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import zipfile

from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Order
from ..permissions import IsAdminToken


def _max_bulk_orders() -> int:
    raw_limit = getattr(settings, "SHIPDAAK_LIVE_BULK_MAX_ORDERS", 50)
    try:
        parsed = int(raw_limit)
    except (TypeError, ValueError):
        parsed = 50
    return parsed if parsed > 0 else 50


def _normalize_order_ids(raw_ids) -> tuple[list[int], str | None]:
    if not isinstance(raw_ids, list) or not raw_ids:
        return [], "order_ids must be a non-empty list."

    unique_ids: list[int] = []
    seen: set[int] = set()

    for value in raw_ids:
        try:
            order_id = int(value)
        except (TypeError, ValueError):
            return [], "order_ids must contain valid integer IDs."
        if order_id <= 0:
            return [], "order_ids must contain positive integer IDs."
        if order_id in seen:
            continue
        seen.add(order_id)
        unique_ids.append(order_id)

    return unique_ids, None


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None


def _resolve_shipping_components(order: Order) -> tuple[Decimal, Decimal, Decimal]:
    breakdown = order.cost_breakdown if isinstance(order.cost_breakdown, dict) else {}

    total = _to_decimal(order.total_cost)
    if total is None:
        for key in ("customer_total_cost", "total_charge", "final_total"):
            total = _to_decimal(breakdown.get(key))
            if total is not None:
                break
    if total is None:
        total = Decimal("0")

    freight = None
    for key in (
        "shipdaak_base_rate",
        "base_transport_cost",
        "freight_charge",
        "base_freight",
        "base_rate",
        "base_slab_rate",
    ):
        freight = _to_decimal(breakdown.get(key))
        if freight is not None:
            break
    if freight is None:
        freight = Decimal("0")

    if total > Decimal("0"):
        additional = total - freight
    else:
        additional = Decimal("0")
        for key in (
            "escalation_amount",
            "fuel_surcharge",
            "cod_charge",
            "docket_fee",
            "eway_bill_fee",
            "hamali_charge",
            "pickup_charge",
            "delivery_charge",
            "fod_charge",
            "dod_charge",
            "risk_charge",
            "fov_charge",
            "ecc_charge",
            "gst_amount",
            "edl_charge",
        ):
            value = _to_decimal(breakdown.get(key))
            if value is not None:
                additional += value
        total = freight + additional

    if additional < Decimal("0"):
        additional = Decimal("0")

    return (
        freight.quantize(Decimal("0.01")),
        additional.quantize(Decimal("0.01")),
        total.quantize(Decimal("0.01")),
    )


def _build_logo_flowable() -> Image | Spacer:
    logo_path = Path(settings.BASE_DIR) / "static" / "images" / "GW Logo and Name.png"
    if not logo_path.exists():
        return Spacer(1, 1)

    reader = ImageReader(str(logo_path))
    img_width, img_height = reader.getSize()
    if not img_width or not img_height:
        return Spacer(1, 1)

    max_width = 3.3 * inch
    max_height = 0.9 * inch
    width_ratio = max_width / float(img_width)
    height_ratio = max_height / float(img_height)
    scale = min(width_ratio, height_ratio)
    draw_width = float(img_width) * scale
    draw_height = float(img_height) * scale
    return Image(str(logo_path), width=draw_width, height=draw_height)


def _render_invoice_pdf(order: Order) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    elements = []
    styles = getSampleStyleSheet()
    title_style = styles["Heading1"]
    title_style.alignment = 1  # Center

    normal_style = styles["Normal"]
    bold_style = ParagraphStyle("Bold", parent=styles["Normal"], fontName="Helvetica-Bold")
    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        alignment=1,
    )

    elements.append(Paragraph("INVOICE", title_style))
    elements.append(Spacer(1, 20))

    invoice_info = [
        [Paragraph(f"<b>Invoice #:</b> {order.order_number}", normal_style)],
        [f"Date: {order.created_at.strftime('%Y-%m-%d')}"],
        [f"Status: {order.status.upper()}"],
        [f"Payment: {str(order.payment_mode or '').upper() or 'N/A'}"],
        [f"Carrier: {order.carrier.name if order.carrier else 'N/A'}"],
        [f"AWB: {order.awb_number or 'N/A'}"],
    ]

    header_data = [[
        _build_logo_flowable(),
        Table(invoice_info, style=[("LEFTPADDING", (0, 0), (-1, -1), 0)]),
    ]]

    header_table = Table(header_data, colWidths=[3.5 * inch, 3 * inch])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )
    elements.append(header_table)
    elements.append(Spacer(1, 30))

    sender_info = [
        [Paragraph("<b>Sender Details:</b>", bold_style)],
        [order.sender_name or "N/A"],
        [Paragraph(order.sender_address or "", normal_style)],
        [f"Pincode: {order.sender_pincode}"],
        [f"Phone: {order.sender_phone or 'N/A'}"],
    ]

    recipient_phone = order.recipient_phone or order.recipient_contact or "N/A"
    recipient_info = [
        [Paragraph("<b>Recipient Details:</b>", bold_style)],
        [order.recipient_name],
        [Paragraph(order.recipient_address, normal_style)],
        [f"Pincode: {order.recipient_pincode}"],
        [f"Phone: {recipient_phone}"],
        [f"Email: {order.recipient_email or 'N/A'}"],
    ]

    address_data = [[
        Table(sender_info, style=[("LEFTPADDING", (0, 0), (-1, -1), 0)]),
        Table(recipient_info, style=[("LEFTPADDING", (0, 0), (-1, -1), 0)]),
    ]]

    address_table = Table(address_data, colWidths=[3.5 * inch, 3 * inch])
    address_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (1, 0), 0.5, colors.lightgrey),
                ("BOTTOMPADDING", (0, 0), (1, 0), 20),
            ]
        )
    )
    elements.append(address_table)
    elements.append(Spacer(1, 30))

    elements.append(Paragraph("<b>Shipment Details:</b>", normal_style))
    elements.append(Spacer(1, 10))

    item_data = [[
        Paragraph("Description", table_header_style),
        Paragraph("SKU", table_header_style),
        Paragraph("Qty", table_header_style),
        Paragraph("Wt (kg)", table_header_style),
        Paragraph("Dimensions (cm)", table_header_style),
        Paragraph("Unit (Rs)", table_header_style),
        Paragraph("Line (Rs)", table_header_style),
    ]]

    item_desc = order.item_type or "Package"
    dims = f"{order.length}x{order.width}x{order.height}"
    unit_price = _to_decimal(order.item_amount) or Decimal("0")
    line_total = unit_price * Decimal(max(int(order.quantity or 1), 1))
    item_data.append(
        [
            item_desc,
            order.sku or "-",
            str(order.quantity),
            str(order.weight),
            dims,
            f"{unit_price:.2f}",
            f"{line_total:.2f}",
        ]
    )

    item_table = Table(
        item_data,
        colWidths=[1.55 * inch, 0.78 * inch, 0.45 * inch, 0.78 * inch, 1.24 * inch, 0.77 * inch, 0.73 * inch],
    )
    item_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.12, 0.23, 0.54)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTSIZE", (0, 1), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("WORDWRAP", (0, 0), (-1, -1), "CJK"),
            ]
        )
    )
    elements.append(item_table)
    elements.append(Spacer(1, 20))

    _freight, _additional, total_shipping = _resolve_shipping_components(order)
    if total_shipping > 0:
        cost_data = []
        cost_data.append(["Total Shipping Cost:", f"Rs {total_shipping:.2f}"])

        cost_table = Table(cost_data, colWidths=[5.5 * inch, 1.5 * inch])
        cost_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
                ]
            )
        )
        elements.append(cost_table)

    elements.append(Spacer(1, 40))

    footer_text = "This is a computer-generated invoice."
    elements.append(
        Paragraph(
            footer_text,
            ParagraphStyle(
                "Footer",
                parent=normal_style,
                alignment=1,
                fontSize=8,
                textColor=colors.grey,
            ),
        )
    )

    doc.build(elements)
    return buffer.getvalue()


@api_view(["GET"])
@permission_classes([IsAdminToken])
def generate_invoice_pdf(request, pk):
    """
    Generate a PDF invoice for a specific order.
    """
    order = get_object_or_404(Order, pk=pk)
    pdf_bytes = _render_invoice_pdf(order)
    filename = f"Invoice_{order.order_number}.pdf"
    return FileResponse(BytesIO(pdf_bytes), as_attachment=True, filename=filename)


@api_view(["POST"])
@permission_classes([IsAdminToken])
def download_invoices_zip(request):
    order_ids, error = _normalize_order_ids(request.data.get("order_ids"))
    if error:
        return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

    limit = _max_bulk_orders()
    if len(order_ids) > limit:
        return Response(
            {
                "detail": f"At most {limit} orders can be downloaded in one request.",
                "code": "batch_limit_exceeded",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    orders = list(Order.objects.filter(id__in=order_ids))
    found_ids = {order.id for order in orders}
    missing_ids = [order_id for order_id in order_ids if order_id not in found_ids]
    if missing_ids:
        return Response(
            {"detail": f"One or more orders not found. Missing IDs: {missing_ids}"},
            status=status.HTTP_404_NOT_FOUND,
        )

    orders_by_id = {order.id: order for order in orders}
    ordered_orders = [orders_by_id[order_id] for order_id in order_ids]

    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for order in ordered_orders:
            pdf_bytes = _render_invoice_pdf(order)
            archive.writestr(f"Invoice_{order.order_number}.pdf", pdf_bytes)

    filename = f"Invoices_{timezone.now().strftime('%Y%m%d_%H%M%S')}.zip"
    response = HttpResponse(archive_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
