from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Courier, CourierZoneRate, FTLRate
from ..permissions import IsAdminToken


def _fmt(value, decimals=2):
    if value is None:
        return "-"
    return f"{value:.{decimals}f}"


def _pct(value, decimals=2):
    if value is None:
        return "-"
    return f"{value:.{decimals}f}%"


def _zone_sort_key(zone_code):
    zone = (zone_code or "").lower().strip()
    if zone.startswith("z_"):
        return (0, zone)
    return (1, zone)


def _to_decimal(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _is_non_zero(value):
    dec = _to_decimal(value)
    return dec is not None and dec != Decimal("0")


def _fmt_cell(value):
    dec = _to_decimal(value)
    if dec is None:
        return "0"
    if dec == dec.to_integral_value():
        return str(int(dec))
    text = f"{dec:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _fmt_fee(value, value_type):
    if value is None:
        return ""
    text = _fmt_cell(value)
    if value_type == "percent":
        return f"{text}%"
    return text


def _normalize_text(value):
    text = "" if value is None else str(value)
    return " ".join(text.replace("_", " ").split())


def _get_carrier_family_label(courier: Courier) -> str:
    display = (courier.display_name or "").strip()
    if display:
        return display
    return (courier.name or "").strip()


def _split_token_to_fit(token, max_width, font_name, font_size):
    if not token:
        return [""]
    chunks = []
    current = ""
    for ch in token:
        candidate = f"{current}{ch}"
        if current and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width:
            chunks.append(current)
            current = ch
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [token]


def _wrap_and_clamp_lines(text, max_width, font_name, font_size, max_lines=2):
    if not text:
        return [""]

    tokens = []
    for token in text.split(" "):
        if not token:
            continue
        if pdfmetrics.stringWidth(token, font_name, font_size) > max_width:
            tokens.extend(_split_token_to_fit(token, max_width, font_name, font_size))
        else:
            tokens.append(token)

    if not tokens:
        return [""]

    lines = []
    current = tokens[0]
    for token in tokens[1:]:
        candidate = f"{current} {token}"
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = token
    lines.append(current)

    if len(lines) <= max_lines:
        return lines

    visible = lines[:max_lines]
    base = visible[-1].rstrip()
    suffix = "..."
    while base and pdfmetrics.stringWidth(f"{base}{suffix}", font_name, font_size) > max_width:
        base = base[:-1].rstrip()
    visible[-1] = f"{base}{suffix}" if base else suffix
    return visible


def _build_wrapped_cell_paragraph(value, style, width, max_lines=2):
    cleaned = _normalize_text(value)
    lines = _wrap_and_clamp_lines(
        cleaned,
        max_width=width - 4,  # keep a small inner margin
        font_name=style.fontName,
        font_size=style.fontSize,
        max_lines=max_lines,
    )
    return Paragraph("<br/>".join(escape(line) for line in lines), style)


def _resolve_rate_card_logo_path() -> Path | None:
    static_root = Path(settings.BASE_DIR) / "static" / "images"
    candidates = [
        static_root / "rate-card-logo.png",
        static_root / "GW Logo and Name.png",
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _append_rate_card_logo(elements: list, width: float = 1.8 * inch, height: float = 0.7 * inch) -> None:
    logo_path = _resolve_rate_card_logo_path()
    if not logo_path:
        return
    try:
        logo = Image(str(logo_path), width=width, height=height)
        logo.hAlign = "LEFT"
        elements.append(logo)
        elements.append(Spacer(1, 6))
    except Exception:
        # Keep PDF generation resilient even when logo is unreadable/corrupt.
        return


def _normalize_logic_type(raw_logic: str | None) -> str:
    logic = str(raw_logic or "").strip()
    mapping = {
        "City_To_City": "city_to_city",
        "Zonal_Custom": "zonal_custom",
        "Zonal_Standard": "zonal_standard",
        "Region_CSV": "region_csv",
    }
    if logic in mapping:
        return mapping[logic]
    lowered = logic.lower()
    return lowered or "zonal_standard"


def _logic_label(logic_type: str) -> str:
    labels = {
        "city_to_city": "City To City",
        "zonal_custom": "Custom Zone Matrix",
        "zonal_standard": "Standard Zonal",
        "region_csv": "Region CSV",
    }
    return labels.get(logic_type, f"Unsupported ({logic_type})")


def _resolve_courier_logic_type(courier: Courier) -> str:
    raw_logic = None
    if hasattr(courier, "routing_config") and courier.routing_config:
        raw_logic = courier.routing_config.logic_type
    if not raw_logic:
        raw_logic = getattr(courier, "rate_logic", None)
    return _normalize_logic_type(raw_logic)


def _build_basic_table(table_data, col_widths):
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ]
        )
    )
    return table


def _build_standard_zonal_table_for_courier(courier: Courier):
    grouped_zone_rates = {}
    for rate in courier.zone_rates.all():
        grouped_zone_rates.setdefault(str(rate.zone_code).lower(), {})[rate.rate_type] = rate.rate

    table_data = [
        [
            "Zone",
            "Forward",
            "Additional",
            "RTO",
            "RTO Add",
            "Reverse",
            "Reverse Add",
        ]
    ]
    for zone in sorted(grouped_zone_rates.keys(), key=_zone_sort_key):
        bucket = grouped_zone_rates[zone]
        table_data.append(
            [
                zone,
                _fmt_cell(bucket.get(CourierZoneRate.RateType.FORWARD)),
                _fmt_cell(bucket.get(CourierZoneRate.RateType.ADDITIONAL)),
                _fmt_cell(bucket.get(CourierZoneRate.RateType.RTO)),
                _fmt_cell(bucket.get(CourierZoneRate.RateType.RTO_ADDITIONAL)),
                _fmt_cell(bucket.get(CourierZoneRate.RateType.REVERSE)),
                _fmt_cell(bucket.get(CourierZoneRate.RateType.REVERSE_ADDITIONAL)),
            ]
        )
    if len(table_data) == 1:
        table_data.append(["-", "No zonal rates configured", "", "", "", "", ""])

    return _build_basic_table(
        table_data,
        [0.9 * inch, 1.0 * inch, 1.0 * inch, 0.9 * inch, 0.95 * inch, 0.9 * inch, 1.0 * inch],
    )


def _build_city_to_city_rate_table(courier: Courier):
    table_data = [["Destination City", "Rate (per kg)"]]
    for city_route in courier.city_routes.all().order_by("city_name"):
        table_data.append([_normalize_text(city_route.city_name), _fmt_cell(city_route.rate_per_kg)])
    if len(table_data) == 1:
        table_data.append(["-", "No city-to-city rates configured"])
    return _build_basic_table(table_data, [4.6 * inch, 2.8 * inch])


def _build_delivery_slab_table(courier: Courier):
    table_data = [["Min Weight", "Max Weight", "Rate"]]
    for slab in courier.delivery_slabs.all().order_by("min_weight", "max_weight"):
        max_weight = "And Above" if slab.max_weight in (None, "") else _fmt_cell(slab.max_weight)
        table_data.append([_fmt_cell(slab.min_weight), max_weight, _fmt_cell(slab.rate)])
    if len(table_data) == 1:
        table_data.append(["-", "-", "No slab rates configured"])
    return _build_basic_table(table_data, [2.4 * inch, 2.4 * inch, 2.6 * inch])


def _build_custom_zone_mapping_table(courier: Courier):
    table_data = [["Location", "Zone Code"]]
    for zone_map in courier.custom_zones.all().order_by("zone_code", "location_name"):
        table_data.append([_normalize_text(zone_map.location_name), _normalize_text(zone_map.zone_code)])
    if len(table_data) == 1:
        table_data.append(["-", "No custom zone mapping configured"])
    return _build_basic_table(table_data, [4.6 * inch, 2.8 * inch])


def _build_custom_zone_matrix_table(courier: Courier, doc_width: float):
    custom_rates = list(courier.custom_zone_rates.all().order_by("from_zone", "to_zone"))
    zones = sorted(
        {
            _normalize_text(zone_code)
            for rate in custom_rates
            for zone_code in [rate.from_zone, rate.to_zone]
            if zone_code
        }
    )

    if not zones:
        return _build_basic_table([["From \\ To", "No custom zone matrix configured"]], [2.0 * inch, max(doc_width - 2.0 * inch, 3.0 * inch)])

    matrix_lookup = {
        (_normalize_text(rate.from_zone), _normalize_text(rate.to_zone)): rate.rate_per_kg
        for rate in custom_rates
    }

    table_data = [["From \\ To", *zones]]
    for from_zone in zones:
        row = [from_zone]
        for to_zone in zones:
            row.append(_fmt_cell(matrix_lookup.get((from_zone, to_zone))))
        table_data.append(row)

    first_col = 1.5 * inch
    remaining = max(doc_width - first_col, 2.0 * inch)
    col_widths = [first_col] + [remaining / len(zones)] * len(zones)
    return _build_basic_table(table_data, col_widths)


def _append_b2b_logic_aware_sections(elements: list, couriers: list[Courier], doc_width: float, styles) -> None:
    section_style = ParagraphStyle(
        "B2BLogicSectionTitle",
        parent=styles["Heading4"],
        textColor=colors.HexColor("#1f2937"),
        spaceBefore=6,
        spaceAfter=4,
    )
    subheading_style = ParagraphStyle(
        "B2BLogicSubheading",
        parent=styles["Heading5"],
        textColor=colors.HexColor("#374151"),
        spaceBefore=4,
        spaceAfter=3,
    )
    note_style = ParagraphStyle(
        "B2BLogicNote",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#6b7280"),
        spaceAfter=6,
    )

    if not couriers:
        elements.append(Paragraph("No active B2B carriers available.", note_style))
        return

    for index, courier in enumerate(couriers):
        logic_type = _resolve_courier_logic_type(courier)
        elements.append(Paragraph(f"{_normalize_text(str(courier))} | Logic: {_logic_label(logic_type)}", section_style))

        if logic_type == "city_to_city":
            elements.append(Paragraph("City To City Rates", subheading_style))
            elements.append(_build_city_to_city_rate_table(courier))
            elements.append(Spacer(1, 6))
            elements.append(Paragraph("Weight Slabs", subheading_style))
            elements.append(_build_delivery_slab_table(courier))
            elements.append(Spacer(1, 6))
        elif logic_type == "zonal_custom":
            elements.append(Paragraph("Custom Zone Mapping", subheading_style))
            elements.append(_build_custom_zone_mapping_table(courier))
            elements.append(Spacer(1, 6))
            elements.append(Paragraph("Custom Zone Matrix", subheading_style))
            elements.append(_build_custom_zone_matrix_table(courier, doc_width))
            elements.append(Spacer(1, 6))
        elif logic_type in {"zonal_standard", "region_csv"}:
            elements.append(Paragraph("Standard Zonal Rates", subheading_style))
            elements.append(_build_standard_zonal_table_for_courier(courier))
            elements.append(Spacer(1, 6))
        else:
            elements.append(
                Paragraph(
                    f"Unsupported routing logic for rate-card export: {logic_type}.",
                    note_style,
                )
            )

        if index < len(couriers) - 1:
            elements.append(Spacer(1, 10))


@api_view(["GET"])
@permission_classes([IsAdminToken])
def generate_rate_card_pdf(request, pk):
    courier = get_object_or_404(
        Courier.objects.select_related(
            "fees_config",
            "fuel_config_obj",
            "constraints_config",
            "routing_config",
        ).prefetch_related("zone_rates"),
        pk=pk,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "RateCardTitle",
        parent=styles["Heading1"],
        alignment=1,
        textColor=colors.HexColor("#1f3b73"),
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading3"],
        spaceAfter=8,
    )
    normal_style = styles["Normal"]

    _append_rate_card_logo(elements)
    elements.append(Paragraph("<b>Courier Module Inc.</b>", normal_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("RATE CARD", title_style))
    elements.append(Spacer(1, 14))

    constraints = getattr(courier, "constraints_config", None)
    carrier_info_data = [
        ["Carrier Name", courier.name],
        ["Type", courier.carrier_type],
        ["Mode", courier.carrier_mode],
        ["Service Category", courier.service_category],
        ["Aggregator", courier.aggregator],
        ["Active", "Yes" if courier.is_active else "No"],
        ["Min Weight (kg)", _fmt(getattr(constraints, "min_weight", None))],
        ["Max Weight (kg)", _fmt(getattr(constraints, "max_weight", None))],
        ["Volumetric Divisor", str(getattr(constraints, "volumetric_divisor", "-"))],
    ]

    elements.append(Paragraph("Carrier Information", section_style))
    carrier_table = Table(carrier_info_data, colWidths=[2.3 * inch, 4.7 * inch])
    carrier_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f3fa")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f9fbff")]),
            ]
        )
    )
    elements.append(carrier_table)
    elements.append(Spacer(1, 14))

    grouped_zone_rates = {}
    for rate in courier.zone_rates.all():
        grouped_zone_rates.setdefault(rate.zone_code, {})[rate.rate_type] = rate.rate

    elements.append(Paragraph("Zonal Rates", section_style))
    zonal_data = [
        [
            "Zone",
            "Forward (INR)",
            "Additional (INR/kg)",
            "RTO (INR)",
            "RTO Add (INR/kg)",
            "Reverse (INR)",
            "Reverse Add (INR/kg)",
        ]
    ]
    for zone in sorted(grouped_zone_rates.keys(), key=_zone_sort_key):
        bucket = grouped_zone_rates[zone]
        zonal_data.append(
            [
                zone,
                _fmt(bucket.get(CourierZoneRate.RateType.FORWARD)),
                _fmt(bucket.get(CourierZoneRate.RateType.ADDITIONAL)),
                _fmt(bucket.get(CourierZoneRate.RateType.RTO)),
                _fmt(bucket.get(CourierZoneRate.RateType.RTO_ADDITIONAL)),
                _fmt(bucket.get(CourierZoneRate.RateType.REVERSE)),
                _fmt(bucket.get(CourierZoneRate.RateType.REVERSE_ADDITIONAL)),
            ]
        )
    if len(zonal_data) == 1:
        zonal_data.append(["-", "-", "-", "-", "-", "-", "-"])

    zonal_table = Table(
        zonal_data,
        colWidths=[0.8 * inch, 1.0 * inch, 1.2 * inch, 0.9 * inch, 1.1 * inch, 0.9 * inch, 1.1 * inch],
        repeatRows=1,
    )
    zonal_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b73")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fe")]),
            ]
        )
    )
    elements.append(zonal_table)
    elements.append(Spacer(1, 14))

    fees = getattr(courier, "fees_config", None)
    elements.append(Paragraph("Fees and Surcharges", section_style))
    fees_data = [
        ["Metric", "Value"],
        ["Docket Fee", _fmt(getattr(fees, "docket_fee", None))],
        ["E-Way Bill Fee", _fmt(getattr(fees, "eway_bill_fee", None))],
        ["COD Fixed", _fmt(getattr(fees, "cod_fixed", None))],
        ["Appointment Delivery", _fmt(getattr(fees, "appointment_delivery_fee", None))],
        ["COD %", _pct(getattr(fees, "cod_percent", None), 4)],
        ["Hamali/kg", _fmt(getattr(fees, "hamali_per_kg", None))],
        ["Min Hamali", _fmt(getattr(fees, "min_hamali", None))],
        ["FOV Insured %", _pct(getattr(fees, "fov_insured_percent", None), 4)],
        ["FOV Uninsured %", _pct(getattr(fees, "fov_uninsured_percent", None), 4)],
        ["FOV Min", _fmt(getattr(fees, "fov_min", None))],
        ["Damage Claim %", _pct(getattr(fees, "damage_claim_percent", None), 4)],
    ]
    fees_table = Table(fees_data, colWidths=[2.8 * inch, 4.2 * inch], repeatRows=1)
    fees_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#234f88")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbff")]),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    elements.append(fees_table)
    elements.append(Spacer(1, 14))

    fuel = getattr(courier, "fuel_config_obj", None)
    elements.append(Paragraph("Fuel Surcharge", section_style))
    fuel_data = [
        ["Metric", "Value"],
        ["Dynamic", "Yes" if getattr(fuel, "is_dynamic", False) else "No"],
        ["Flat %", _pct(getattr(fuel, "surcharge_percent", None), 4)],
        ["Base Diesel Price", _fmt(getattr(fuel, "base_price", None))],
        ["Ratio", _fmt(getattr(fuel, "ratio", None), 4)],
    ]
    fuel_table = Table(fuel_data, colWidths=[2.8 * inch, 4.2 * inch], repeatRows=1)
    fuel_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f6f4f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6fcf8")]),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    elements.append(fuel_table)
    elements.append(Spacer(1, 18))

    footer = f"This is a system-generated rate card. Valid as of {datetime.now().strftime('%Y-%m-%d')}"
    elements.append(
        Paragraph(
            footer,
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
    buffer.seek(0)

    filename = f"Rate_Card_{courier.name.replace(' ', '_')}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename)


def _list_rate_card_carriers_by_type(carrier_type: str):
    couriers = list(
        Courier.objects.filter(is_active=True, carrier_type__iexact=carrier_type)
        .only("id", "name", "display_name")
        .order_by("display_name", "name")
    )

    counts: dict[str, int] = {}
    for courier in couriers:
        label = _get_carrier_family_label(courier)
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1

    options = [
        {
            "key": label,
            "label": label,
            "carrier_count": count,
        }
        for label, count in sorted(counts.items(), key=lambda item: item[0].lower())
    ]
    return Response({"carriers": options, "total": len(options)})


@api_view(["GET"])
@permission_classes([IsAdminToken])
def list_b2c_rate_card_carriers(request):
    return _list_rate_card_carriers_by_type("B2C")


@api_view(["GET"])
@permission_classes([IsAdminToken])
def list_b2b_rate_card_carriers(request):
    return _list_rate_card_carriers_by_type("B2B")


def _generate_business_rate_card_pdf(
    request,
    *,
    carrier_type: str,
    title: str,
    filename_prefix: str,
):
    all_couriers = list(
        Courier.objects.filter(is_active=True, carrier_type__iexact=carrier_type)
        .select_related("fees_config", "constraints_config", "routing_config")
        .prefetch_related("zone_rates", "city_routes", "delivery_slabs", "custom_zones", "custom_zone_rates")
        .order_by("name")
    )
    carrier_filters_raw = request.query_params.getlist("carrier")
    carrier_filters: list[str] = []
    seen = set()
    for raw in carrier_filters_raw:
        for part in str(raw).split(","):
            candidate = part.strip()
            if not candidate:
                continue
            normalized = candidate.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            carrier_filters.append(candidate)

    if carrier_filters:
        available_labels_by_key = {
            _get_carrier_family_label(courier).casefold(): _get_carrier_family_label(courier)
            for courier in all_couriers
            if _get_carrier_family_label(courier)
        }
        invalid_filters = [name for name in carrier_filters if name.casefold() not in available_labels_by_key]
        if invalid_filters:
            return Response(
                {
                    "detail": "Invalid carrier selection.",
                    "code": "invalid_carrier",
                    "invalid_carriers": invalid_filters,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        selected_keys = {name.casefold() for name in carrier_filters}
        couriers = [
            courier
            for courier in all_couriers
            if _get_carrier_family_label(courier).casefold() in selected_keys
        ]
    else:
        couriers = all_couriers

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=24,
        leftMargin=24,
        topMargin=24,
        bottomMargin=24,
    )

    elements = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        f"{carrier_type}RateCardTitle",
        parent=styles["Heading2"],
        alignment=1,
        textColor=colors.HexColor("#1f2937"),
    )
    subtitle_style = ParagraphStyle(
        f"{carrier_type}RateCardSubtitle",
        parent=styles["Normal"],
        alignment=1,
        textColor=colors.HexColor("#6b7280"),
        fontSize=9,
    )
    cell_text_style = ParagraphStyle(
        f"{carrier_type}RateCardCellText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=8,
        alignment=1,
    )

    _append_rate_card_logo(elements)
    elements.append(Paragraph(title, title_style))
    elements.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d')}", subtitle_style))
    elements.append(Spacer(1, 10))

    if carrier_type.upper() == "B2B":
        _append_b2b_logic_aware_sections(elements, couriers, doc.width, styles)
        doc.build(elements)
        buffer.seek(0)
        filename = f"{filename_prefix}_{datetime.now().strftime('%Y-%m-%d')}.pdf"
        return FileResponse(buffer, as_attachment=True, filename=filename)

    zones = ["z_a", "z_b", "z_c", "z_d", "z_e"]
    rate_types = [
        (CourierZoneRate.RateType.FORWARD, "Forward"),
        (CourierZoneRate.RateType.ADDITIONAL, "Additional"),
        (CourierZoneRate.RateType.RTO, "RTO"),
        (CourierZoneRate.RateType.RTO_ADDITIONAL, "RTO Additional"),
        (CourierZoneRate.RateType.REVERSE, "Reverse"),
        (CourierZoneRate.RateType.REVERSE_ADDITIONAL, "Reverse Additional"),
    ]
    fee_candidates = [
        ("cod_fixed", "COD Charges", "amount"),
        ("cod_percent", "COD_Percentage", "percent"),
        ("docket_fee", "Docket Fee", "amount"),
        ("eway_bill_fee", "EWay Bill Fee", "amount"),
        ("appointment_delivery_fee", "Appointment Delivery", "amount"),
        ("hamali_per_kg", "Hamali/Kg", "amount"),
        ("min_hamali", "Min Hamali", "amount"),
        ("fov_min", "FOV Min", "amount"),
        ("fov_insured_percent", "FOV Insured %", "percent"),
        ("fov_uninsured_percent", "FOV Uninsured %", "percent"),
        ("damage_claim_percent", "Damage Claim %", "percent"),
    ]

    non_zero_fee_columns = []
    for field_name, label, value_type in fee_candidates:
        if any(_is_non_zero(getattr(getattr(courier, "fees_config", None), field_name, None)) for courier in couriers):
            non_zero_fee_columns.append((field_name, label, value_type))

    for courier in couriers:
        rates_by_type = {rate_key: {} for rate_key, _ in rate_types}
        for zone_rate in courier.zone_rates.all():
            if zone_rate.rate_type in rates_by_type:
                rates_by_type[zone_rate.rate_type][zone_rate.zone_code.lower()] = zone_rate.rate

        rows = []
        for rate_key, label in rate_types:
            zone_values = [rates_by_type[rate_key].get(zone) for zone in zones]
            has_any_zone_rate = any(value is not None for value in zone_values)
            if not has_any_zone_rate:
                continue

            row = [
                _build_wrapped_cell_paragraph(str(courier), cell_text_style, 150, max_lines=2),
                courier.carrier_mode,
                _fmt_cell(getattr(getattr(courier, "constraints_config", None), "min_weight", None)),
                label,
            ]
            row.extend(_fmt_cell(value) for value in zone_values)

            if rate_key == CourierZoneRate.RateType.FORWARD:
                fees = getattr(courier, "fees_config", None)
                row.extend(_fmt_fee(getattr(fees, field_name, None), value_type) for field_name, _, value_type in non_zero_fee_columns)
            else:
                row.extend("" for _ in non_zero_fee_columns)

            rows.append(row)

        if not rows:
            continue

        header = [
            "Courier Name",
            "Mode",
            "Min Weight",
            "Type Text",
            "z_a",
            "z_b",
            "z_c",
            "z_d",
            "z_e",
        ]
        header.extend(label for _, label, _ in non_zero_fee_columns)
        table_data = [header, *rows]

        fixed_widths = [150, 52, 58, 72, 40, 40, 40, 40, 40]
        remaining_width = max(doc.width - sum(fixed_widths), 80)
        fee_widths = [remaining_width / len(non_zero_fee_columns)] * len(non_zero_fee_columns) if non_zero_fee_columns else []
        col_widths = fixed_widths + fee_widths

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 12))

    legend_data = [
        ["Note: 18% GST Applicable Extra", ""],
        ["Metropolitan", "z_a"],
        ["Regional", "z_b"],
        ["Intercity", "z_c"],
        ["Pan-India", "z_d"],
        ["North-East and J&K.", "z_e"],
    ]
    legend_table = Table(legend_data, colWidths=[2.2 * inch, 1.1 * inch])
    legend_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#e5e7eb")),
                ("FONTNAME", (0, 0), (1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 1), (1, -1), "CENTER"),
            ]
        )
    )
    elements.append(Spacer(1, 6))
    elements.append(legend_table)

    doc.build(elements)
    buffer.seek(0)

    filename = f"{filename_prefix}_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename)


@api_view(["GET"])
@permission_classes([IsAdminToken])
def generate_b2c_rate_card_pdf(request):
    return _generate_business_rate_card_pdf(
        request,
        carrier_type="B2C",
        title="B2C Rate Card",
        filename_prefix="B2C_Rate_Card",
    )


@api_view(["GET"])
@permission_classes([IsAdminToken])
def generate_b2b_rate_card_pdf(request):
    return _generate_business_rate_card_pdf(
        request,
        carrier_type="B2B",
        title="B2B Rate Card",
        filename_prefix="B2B_Rate_Card",
    )


@api_view(["GET"])
@permission_classes([IsAdminToken])
def generate_ftl_rate_card_pdf(request):
    rates = list(FTLRate.objects.all().order_by("source_city", "destination_city", "truck_type"))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=24,
        leftMargin=24,
        topMargin=24,
        bottomMargin=24,
    )
    elements = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "FTLRateCardTitle",
        parent=styles["Heading2"],
        alignment=1,
        textColor=colors.HexColor("#1f2937"),
    )
    subtitle_style = ParagraphStyle(
        "FTLRateCardSubtitle",
        parent=styles["Normal"],
        alignment=1,
        textColor=colors.HexColor("#6b7280"),
        fontSize=9,
    )

    _append_rate_card_logo(elements)
    elements.append(Paragraph("FTL Rate Card", title_style))
    elements.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d')}", subtitle_style))
    elements.append(Spacer(1, 12))

    table_data = [["Source City", "Destination City", "Truck Type", "Rate (INR)"]]
    if rates:
        for item in rates:
            table_data.append(
                [
                    _normalize_text(item.source_city),
                    _normalize_text(item.destination_city),
                    _normalize_text(item.truck_type),
                    _fmt_cell(item.rate),
                ]
            )
    else:
        table_data.append(["-", "-", "-", "No FTL rates available"])

    table = Table(table_data, colWidths=[2.6 * inch, 2.6 * inch, 1.6 * inch, 1.6 * inch], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)

    filename = f"FTL_Rate_Card_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename)
