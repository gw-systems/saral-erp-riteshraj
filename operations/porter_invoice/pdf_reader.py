"""
pdf_reader.py — Hybrid extraction: Y-band field location via PyMuPDF spans +
OCR-based value reading via Tesseract/PyMuPDF render for actual numeric content.

WHY HYBRID:
  The invoices use a custom glyph encoding (CMap) that scrambles all text in the
  text layer — both labels and values. Field POSITIONS are still accurate and
  usable for bbox detection. But the numeric VALUES must be read from the rendered
  image (OCR), which shows the correct glyphs visually.
"""

from __future__ import annotations

import re
import fitz  # PyMuPDF
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image
import pytesseract

from .config import FIELD_SPECS, Y_TOLERANCE, VALUE_X_MIN

# ──────────────────────────────────────────────
# Tesseract path (cross-platform detection)
# ──────────────────────────────────────────────
import shutil
import platform

if platform.system() == 'Windows':
    TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
else:
    TESSERACT_PATH = shutil.which('tesseract') or '/usr/bin/tesseract'
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# Render scale: higher = better OCR but slower. 3x (≈216 DPI) is a sweet spot.
RENDER_SCALE = 3

# Tesseract config for numeric fields (digits, comma, dot, minus, space)
TESS_CONFIG = r"--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.,- "


# ──────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────

@dataclass
class SpanInfo:
    """All metadata about a single text span (used for field location + redact)."""
    text:      str
    bbox:      tuple[float, float, float, float]   # x0, y0, x1, y1  (PDF points)
    font:      str
    size:      float
    color:     int
    page_num:  int

    @property
    def y_center(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2

    @property
    def x0(self) -> float:
        return self.bbox[0]

    @property
    def origin(self) -> tuple[float, float]:
        """Bottom-left point for insert_text (PyMuPDF uses baseline)."""
        return (self.bbox[0], self.bbox[3])

    def matches_field(self, spec: dict) -> bool:
        """True if Y-centre is within tolerance AND size + color match."""
        y_ok    = abs(self.y_center - spec["y"]) <= Y_TOLERANCE
        size_ok = abs(self.size     - spec["size"]) <= 1.5
        color_ok = self.color == spec["color"]
        return y_ok and size_ok and color_ok


# ──────────────────────────────────────────────
# Span extraction (for location + bbox metadata)
# ──────────────────────────────────────────────

def extract_spans(pdf_path: Path, page_num: int = 0) -> list[SpanInfo]:
    """Extract every text span on the given page with full coordinates + font info."""
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    raw = page.get_text("dict")["blocks"]
    doc.close()

    spans: list[SpanInfo] = []
    for block in raw:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                txt = span["text"].strip()
                if not txt:
                    continue
                spans.append(SpanInfo(
                    text=txt,
                    bbox=tuple(span["bbox"]),
                    font=span["font"],
                    size=round(span["size"], 1),
                    color=span["color"],
                    page_num=page_num,
                ))
    spans.sort(key=lambda s: (s.bbox[1], s.bbox[0]))
    return spans


# Tight tolerance (PDF points) used for the second pass — snapping to the
# actual row Y found in pass 1.  5 pts ≈ 2 mm, well within one text line.
_VALUE_Y_TIGHT: float = 5.0


def _find_row_y(spans: list[SpanInfo], spec: dict) -> Optional[float]:
    """
    Pass 1 — Find the *actual* Y-center of the row for a field spec.

    Strategy: among ALL spans (left-column labels AND right-column values),
    find the one whose font size + color match the spec AND whose Y-center
    is closest to the expected spec["y"] within Y_TOLERANCE.

    Returns the y_center of that best-match span, or None if nothing found.

    WHY: Porter's invoices shift row positions between order templates.
    Using the spec Y only as a *loose seed* and then snapping to the real
    row Y makes the locator robust across layout variants.
    """
    best: Optional[SpanInfo] = None
    best_dy: float = float("inf")
    for s in spans:
        size_ok  = abs(s.size  - spec["size"])  <= 1.5
        color_ok = s.color == spec["color"]
        dy       = abs(s.y_center - spec["y"])
        if size_ok and color_ok and dy <= Y_TOLERANCE and dy < best_dy:
            best    = s
            best_dy = dy
    return best.y_center if best is not None else None


def find_field_span(spans: list[SpanInfo], field_name: str) -> Optional[SpanInfo]:
    """
    Find the VALUE span for a named field using a two-pass label-anchor strategy.

    Pass 1 (_find_row_y): Locate the actual Y of the row in *this* invoice by
    finding any span (label or value) whose font size + color match the spec,
    within a loose Y_TOLERANCE window around the spec's expected Y.

    Pass 2: Among spans in the value column (x0 >= VALUE_X_MIN), pick the one
    whose Y is within _VALUE_Y_TIGHT pts of the real row Y found in pass 1.
    Returns the rightmost such span (largest x0).

    This eliminates breakage when Porter shifts row positions between invoice
    variants — only a large structural redesign (>Y_TOLERANCE pts) would cause
    a miss, which will return None and log a warning upstream.
    """
    spec     = FIELD_SPECS[field_name]
    row_y    = _find_row_y(spans, spec)

    if row_y is None:
        return None

    # Pass 2: value spans on the same row, right column
    candidates = [
        s for s in spans
        if abs(s.y_center - row_y) <= _VALUE_Y_TIGHT
        and s.x0 >= VALUE_X_MIN
    ]
    digit_candidates = [s for s in candidates if any(ch.isdigit() for ch in s.text)]
    pool = digit_candidates if digit_candidates else candidates
    if not pool:
        return None
    return max(pool, key=lambda s: s.x0)


# ──────────────────────────────────────────────
# OCR-based value reading
# ──────────────────────────────────────────────

# Padding around the span bbox when cropping for OCR (PDF points)
OCR_PAD = 6.0

# Regex: matches a number token like  1,714  or  1,563.91  or  -0.00
_NUMBER_TOKEN_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _extract_number_from_ocr(raw: str) -> str:
    """
    Extract the canonical numeric value from a raw OCR string.

    Strategy (robust against rupee-symbol misread as '2', 'z', 'Z'):
      1. If raw string starts with '-', mark as negative.
      2. Find all number-like tokens (digit sequences with comma/dot).
      3. Return the LONGEST token — the real amount value.
         A single-char prefix artefact like '2' (from rupee misread)
         will always be shorter than the actual number '1,563.91'.
    """
    raw = raw.strip()
    negative = raw.startswith("-")
    tokens = _NUMBER_TOKEN_RE.findall(raw)
    if not tokens:
        return "0"
    best = max(tokens, key=len)
    if negative and not best.startswith("-"):
        best = f"-{best}"
    return best


def _render_span_image(pdf_path: Path, span: "SpanInfo") -> "Image.Image":
    """Render the zone around a span bbox to a PIL Image at RENDER_SCALE."""
    doc = fitz.open(str(pdf_path))
    page = doc[span.page_num]
    x0, y0, x1, y1 = span.bbox
    clip = fitz.Rect(
        max(0, x0 - OCR_PAD * 3),   # generous left margin to include prefix symbol
        max(0, y0 - OCR_PAD),
        min(page.rect.width, x1 + OCR_PAD),
        min(page.rect.height, y1 + OCR_PAD),
    )
    mat = fitz.Matrix(RENDER_SCALE, RENDER_SCALE)
    pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csRGB)
    doc.close()
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def ocr_field_value(pdf_path: Path, span: "SpanInfo") -> str:
    """
    Render the region around a span to an image and OCR it.

    Returns a cleaned numeric string like '1714', '1563.91', '0.09'.
    """
    img = _render_span_image(pdf_path, span)
    # Full charset OCR — gives Tesseract the best chance to read ₹ as a
    # separate symbol rather than fusing it with the digits
    raw_text = pytesseract.image_to_string(img, config="--oem 3 --psm 7").strip()
    result = _extract_number_from_ocr(raw_text)

    # Fallback: digit-whitelist if full OCR returned nothing useful
    if result == "0" and raw_text:
        raw2 = pytesseract.image_to_string(
            img, config=r"--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.,- "
        ).strip()
        result = _extract_number_from_ocr(raw2)

    return result


# ──────────────────────────────────────────────
# Color constants for Porter invoice rows
# ──────────────────────────────────────────────

# The discount/negative row always uses a distinct teal color — this is the
# sole unambiguous layout anchor regardless of how many rows the invoice has.
_DISCOUNT_COLOR: int = 2600544   # teal/grey used exclusively for discount

# Standard dark color used by all other breakdown rows
_STD_COLOR: int = 3355443


# ──────────────────────────────────────────────
# High-level scraper
# ──────────────────────────────────────────────

@dataclass
class FieldResult:
    """Holds both the span (for redact/overlay position) and the OCR-read value."""
    span:  Optional[SpanInfo]
    value: str   # cleaned numeric string; "0" if not found


def _collect_value_spans(spans: list[SpanInfo]) -> list[SpanInfo]:
    """
    Return all right-column spans (x0 >= VALUE_X_MIN) with a breakdown row
    font size (14–34 pt), sorted top-to-bottom by Y-center.
    Includes both the standard color and the discount teal color.
    """
    return sorted(
        [
            s for s in spans
            if s.x0 >= VALUE_X_MIN
            and 14 <= s.size <= 34
            and s.color in (_STD_COLOR, _DISCOUNT_COLOR)
        ],
        key=lambda s: s.y_center,
    )


def _locate_spans_by_position(
    all_spans: list[SpanInfo],
) -> dict[str, Optional[SpanInfo]]:
    """
    Assign value spans to field names using positional ordering.

    Layout logic (always holds regardless of toll_tax presence):
      • total_amount  — unique size=32, always first/topmost large number
      • discount      — unique color (_DISCOUNT_COLOR), unambiguous anchor
      • trip_fare     — last std-color row ABOVE discount (immediately before it)
      • toll_tax      — second-to-last std-color row ABOVE discount (None if absent)
      • sub_total     — 1st std-color row BELOW discount
      • rounding      — 2nd std-color row BELOW discount
      • net_fare      — 3rd std-color row BELOW discount

    This is completely Y-coordinate-free after bootstrap, making it robust
    to Porter's variable invoice templates (with or without toll/tax rows).
    """
    value_spans = _collect_value_spans(all_spans)

    result: dict[str, Optional[SpanInfo]] = {k: None for k in (
        "total_amount", "trip_fare", "toll_tax",
        "discount", "sub_total", "rounding", "net_fare",
    )}

    # ── total_amount: largest font size (32pt), topmost ──────────────────────
    large = [s for s in value_spans if s.size >= 28]
    if large:
        result["total_amount"] = min(large, key=lambda s: s.y_center)

    # ── discount anchor by color ──────────────────────────────────────────────
    disc_spans = [s for s in value_spans if s.color == _DISCOUNT_COLOR]
    if not disc_spans:
        # Fallback: no teal row found — treat everything as below-anchor
        disc_y = float("inf")
    else:
        disc_span = min(disc_spans, key=lambda s: s.y_center)
        result["discount"] = disc_span
        disc_y = disc_span.y_center

    # Derive the Y floor: only breakdown rows that sit BELOW the total_amount
    # header are valid. Spans above total_amount (order number, date, logo text)
    # share the same color/size and were being misclassified as toll_tax rows.
    total_y = result["total_amount"].y_center if result["total_amount"] else 0.0

    # ── rows above discount (std color, excluding total_amount + header) ───────
    above = sorted(
        [
            s for s in value_spans
            if s.color == _STD_COLOR
            and s.y_center > total_y    # must be BELOW the total_amount header
            and s.y_center < disc_y
            and s.size < 28             # exclude total_amount itself
        ],
        key=lambda s: s.y_center,
    )
    # The first row below the header is always trip_fare
    if above:
        result["trip_fare"] = above[0]
    # If there's a second row before the discount, it's toll_tax
    if len(above) >= 2:
        result["toll_tax"] = above[1]

    # ── rows below discount (std color, size=16) ─────────────────────────────
    below = sorted(
        [
            s for s in value_spans
            if s.color == _STD_COLOR
            and s.y_center > disc_y
        ],
        key=lambda s: s.y_center,
    )
    field_order = ["sub_total", "rounding", "net_fare"]
    for i, field in enumerate(field_order):
        result[field] = below[i] if i < len(below) else None

    return result


def scrape_invoice_fields(pdf_path: Path) -> dict[str, FieldResult]:
    """
    Extract all field spans (for position) and OCR-read their values.

    Uses positional/color ordering (layout-aware) rather than hardcoded
    Y-coordinates so it works correctly on any Porter invoice template,
    with or without a toll/tax row.

    Returns a dict mapping field_name → FieldResult.
    """
    spans = extract_spans(pdf_path)
    span_map = _locate_spans_by_position(spans)

    results: dict[str, FieldResult] = {}
    for field_name, span in span_map.items():
        if span is None:
            results[field_name] = FieldResult(span=None, value="0")
        else:
            value_str = ocr_field_value(pdf_path, span)
            results[field_name] = FieldResult(span=span, value=value_str)

    return results
