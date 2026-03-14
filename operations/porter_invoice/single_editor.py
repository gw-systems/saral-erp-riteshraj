"""
single_editor.py — Single invoice field editor (CRN, date, vehicle, stops, pickup/drop).

Refactored from the Invoice-Editor webapp views.py into a standalone function
that can be called from Django views without any DRF dependency.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from .pdf_editor import _get_font_bytes

logger = logging.getLogger(__name__)

# OCR helpers
RENDER_SCALE = 3
OCR_PAD = 4.0

_CRN_PREFIX_RE = re.compile(r"^CRN", re.IGNORECASE)


def extract_crn_from_filename(filename: str) -> str:
    """Pull CRN/order number from a filename like 'invoice_CRN1091124414.pdf'."""
    stem = Path(filename).stem
    m = re.search(r"invoice[_\-]?([A-Za-z0-9]+)", stem, re.IGNORECASE)
    return m.group(1) if m else stem


def _get_ocr_text(page, rect, config="--oem 3 --psm 7") -> str:
    """Render a zone to image and OCR it."""
    mat = fitz.Matrix(RENDER_SCALE, RENDER_SCALE)
    clip = fitz.Rect(rect.x0 - OCR_PAD, rect.y0 - OCR_PAD, rect.x1 + OCR_PAD, rect.y1 + OCR_PAD)
    pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csRGB)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pytesseract.image_to_string(img, config=config).strip()


def _find_vehicle_pill(page):
    """Detect the vehicle pill bbox and its original line content."""
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") == 0:
            for line in b["lines"]:
                for s in line["spans"]:
                    is_blue = (s["color"] == 2712319)
                    is_right = (s["bbox"][0] > 600)
                    is_mid_y = (700 < s["bbox"][1] < 1000)
                    if is_right and is_mid_y and (is_blue or "MH" in s["text"] or "Tata" in s["text"]):
                        text_parts = []
                        x0, y0, x1, y1 = s["bbox"]
                        for span in line["spans"]:
                            text_parts.append(span["text"])
                            sx0, sy0, sx1, sy1 = span["bbox"]
                            x0 = min(x0, sx0)
                            y0 = min(y0, sy0)
                            x1 = max(x1, sx1)
                            y1 = max(y1, sy1)
                        pill_bbox = fitz.Rect(x0, y0, x1, y1)
                        original_line_text = "".join(text_parts).strip()
                        return pill_bbox, original_line_text
    return None, ""


def apply_single_edit(
    input_pdf_path: Path,
    output_pdf_path: Path,
    fields: dict,
) -> dict:
    """
    Apply text overlay edits to a single Porter invoice PDF.

    Args:
        input_pdf_path: Path to the source PDF.
        output_pdf_path: Path to write the edited PDF.
        fields: Dict with keys: crn, date, vehicle_type, vehicle, num_stops,
                pickup_loc, pickup_date, pickup_time,
                drop_loc, drop_date, drop_time

    Returns:
        dict with 'status' ('success'|'error') and optional 'error' message.
    """
    crn = fields.get('crn', '').strip()
    date = fields.get('date', '').strip()
    vehicle_type = fields.get('vehicle_type', '').strip()
    vehicle = fields.get('vehicle', '').strip()
    num_stops = fields.get('num_stops', '').strip()
    pickup_loc = fields.get('pickup_loc', '').strip()
    pickup_date = fields.get('pickup_date', '').strip()
    pickup_time = fields.get('pickup_time', '').strip()
    drop_loc = fields.get('drop_loc', '').strip()
    drop_date = fields.get('drop_date', '').strip()
    drop_time = fields.get('drop_time', '').strip()

    try:
        doc = fitz.open(str(input_pdf_path))
        page = doc[0]
    except Exception as e:
        return {'status': 'error', 'error': f'Invalid or corrupted PDF: {e}'}

    try:
        # Redaction coordinates calibrated for Porter invoice template
        value_color = (130 / 255, 130 / 255, 130 / 255)
        text_color = (51 / 255, 51 / 255, 51 / 255)

        # ── Pass 1: Add redaction annotations ──────────────────────
        if crn:
            page.add_redact_annot(fitz.Rect(1055, 100, 1185, 130), fill=(1, 1, 1))
        if date:
            page.add_redact_annot(fitz.Rect(1090, 130, 1185, 160), fill=(1, 1, 1))

        # Pickup location
        if pickup_loc:
            page.add_redact_annot(fitz.Rect(650, 985, 950, 1070), fill=(1, 1, 1))

        # Pickup date/time
        if pickup_date and not pickup_time:
            page.add_redact_annot(fitz.Rect(728, 956, 900, 980), fill=(1, 1, 1))
        elif pickup_time and not pickup_date:
            page.add_redact_annot(fitz.Rect(650, 956, 725, 980), fill=(1, 1, 1))
        elif pickup_time and pickup_date:
            page.add_redact_annot(fitz.Rect(650, 956, 900, 980), fill=(1, 1, 1))

        # Drop location
        if drop_loc:
            page.add_redact_annot(fitz.Rect(650, 1185, 950, 1280), fill=(1, 1, 1))

        # Drop date/time
        if drop_date and not drop_time:
            page.add_redact_annot(fitz.Rect(728, 1156, 900, 1180), fill=(1, 1, 1))
        elif drop_time and not drop_date:
            page.add_redact_annot(fitz.Rect(650, 1156, 725, 1180), fill=(1, 1, 1))
        elif drop_time and drop_date:
            page.add_redact_annot(fitz.Rect(650, 1156, 900, 1180), fill=(1, 1, 1))

        # Vehicle pill detection
        pill_bbox, pill_original_text = _find_vehicle_pill(page)

        final_vehicle_text = ""
        if vehicle or vehicle_type:
            old_type = ""
            old_num = ""
            if not vehicle_type or not vehicle:
                if pill_bbox:
                    vehicle_raw = _get_ocr_text(page, pill_bbox, config="--oem 3 --psm 7")
                    if "|" in vehicle_raw:
                        parts = vehicle_raw.split("|", 1)
                        old_type = parts[0].strip()
                        old_num = parts[1].strip()
                    else:
                        old_num = vehicle_raw
            new_type = vehicle_type if vehicle_type else old_type
            new_num = vehicle if vehicle else old_num
            if new_type and new_num:
                final_vehicle_text = f"{new_type} | {new_num}"
            elif new_type:
                final_vehicle_text = new_type
            else:
                final_vehicle_text = new_num

        pill_bg = (240 / 255, 243 / 255, 255 / 255)
        if final_vehicle_text and pill_bbox:
            redact_rect = fitz.Rect(
                pill_bbox.x0 - 5, pill_bbox.y0 - 5,
                pill_bbox.x1 + 5, pill_bbox.y1 + 5
            )
            page.add_redact_annot(redact_rect, fill=pill_bg)
        elif final_vehicle_text:
            page.add_redact_annot(fitz.Rect(635, 765, 875, 810), fill=pill_bg)

        if num_stops:
            page.add_redact_annot(fitz.Rect(670, 1058, 735, 1086), fill=pill_bg)

        # ── Pass 2: Apply redactions (clears font state) ──────────
        page.apply_redactions()

        # ── Pass 3: Register fonts ────────────────────────────────
        font_regular = _get_font_bytes("regular")
        font_medium = _get_font_bytes("medium")
        font_bold = _get_font_bytes("bold")
        font_semibold = _get_font_bytes("semibold")

        page.insert_font(fontname="ssp-reg", fontbuffer=font_regular)
        page.insert_font(fontname="ssp-med", fontbuffer=font_medium)
        page.insert_font(fontname="ssp-bold", fontbuffer=font_bold)
        page.insert_font(fontname="ssp-semi", fontbuffer=font_semibold)

        # ── Pass 4: Insert text overlays ──────────────────────────
        if crn:
            page.insert_text(fitz.Point(1058, 122.5), crn,
                             fontname="ssp-reg", fontsize=18, color=value_color)
        if date:
            page.insert_text(fitz.Point(1093, 151), date,
                             fontname="ssp-reg", fontsize=18, color=value_color)

        if final_vehicle_text and pill_bbox:
            page.insert_text(
                fitz.Point(pill_bbox.x0, pill_bbox.y1 - 5),
                final_vehicle_text,
                fontname="ssp-med", fontsize=18.0,
                color=(41 / 255, 98 / 255, 255 / 255)
            )
        elif final_vehicle_text:
            page.insert_text(fitz.Point(640, 795), final_vehicle_text,
                             fontname="ssp-med", fontsize=15,
                             color=(41 / 255, 98 / 255, 255 / 255))

        if num_stops:
            page.insert_text(
                fitz.Point(676, 1078), f"{num_stops} stops",
                fontname="ssp-bold", fontsize=18,
                color=(56 / 255, 118 / 255, 253 / 255)
            )

        if pickup_loc:
            page.insert_textbox(fitz.Rect(656, 985, 950, 1075), pickup_loc.upper(),
                                fontname="ssp-reg", fontsize=16, color=text_color,
                                align=fitz.TEXT_ALIGN_LEFT)
        if pickup_time:
            page.insert_text(fitz.Point(656, 974.5), pickup_time + ",",
                             fontname="ssp-bold", fontsize=16, color=text_color)
        if pickup_date:
            page.insert_text(fitz.Point(727, 974), pickup_date,
                             fontname="ssp-bold", fontsize=17, color=text_color)

        if drop_loc:
            page.insert_textbox(fitz.Rect(656, 1185, 950, 1290), drop_loc.upper(),
                                fontname="ssp-reg", fontsize=16, color=text_color,
                                align=fitz.TEXT_ALIGN_LEFT)
        if drop_time:
            page.insert_text(fitz.Point(656, 1174), drop_time + ",",
                             fontname="ssp-bold", fontsize=16, color=text_color)
        if drop_date:
            page.insert_text(fitz.Point(727, 1174), drop_date,
                             fontname="ssp-bold", fontsize=17, color=text_color)

        # Save
        output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_pdf_path), garbage=4, deflate=True)
        doc.close()

        return {'status': 'success'}

    except Exception as e:
        logger.error("Single edit failed: %s", e, exc_info=True)
        try:
            doc.close()
        except Exception:
            pass
        return {'status': 'error', 'error': str(e)}
