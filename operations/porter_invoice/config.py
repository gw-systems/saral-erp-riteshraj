"""
config.py — Field definitions, Y-band specs, regex constants.

Field identification uses Y-coordinate proximity + font size + color fingerprint,
since the PDF text layer may be scrambled/encoded. All Y values are in PDF points
and were calibrated from invoice_CRN1091124414.pdf using _scan_pdf.py.

To recalibrate for a different invoice template, run:
    python main.py --calibrate path/to/invoice.pdf
and update FIELD_SPECS accordingly.
"""

# ──────────────────────────────────────────────
# Matching tolerances
# ──────────────────────────────────────────────

# How many PDF points above/below a field's Y-centre we still accept a span.
# Used as the loose first-pass search radius in the label-proximity locator.
# 80 pts ≈ 28 mm — wide enough for Porter's layout variants, narrow enough
# to avoid accidentally matching a completely different row.
Y_TOLERANCE: float = 80.0

# How far (pts) to the right of the label column we expect the value span.
# Value spans sit in the right portion of the page. Lowered from 900 → 700
# because on some Porter invoice variants (e.g. CRN1523859283) the net_fare
# value span is at x0≈742 — still well clear of the label column (~660).
VALUE_X_MIN: float = 700.0

# ──────────────────────────────────────────────
# Field specifications
# Calibrated from the sample PDF scan output.
# Each key maps to a dict with:
#   y      – vertical centre of the span (points from page top)
#   size   – font size
#   color  – PyMuPDF integer colour (R<<16 | G<<8 | B)
# ──────────────────────────────────────────────

FIELD_SPECS: dict[str, dict] = {
    # Large bold "Total Amount" header block  (calibrated Y=251.2 from sample PDF)
    "total_amount": {"y": 251.2, "size": 32.0, "color": 3355443},

    # Breakdown rows — calibrated from invoice_CRN1091124414.pdf
    # NOTE: toll_tax and discount have DIFFERENT colors (teal vs grey).
    # Colors confirmed from _spans_dump.json on CRN1523859283:
    #   toll_tax  row value at y≈364 has color=2600544  (teal/grey)
    #   discount  row value at y≈426 has color=3355443  (standard dark)
    "trip_fare":    {"y": 322.2, "size": 16.0, "color": 3355443},
    "toll_tax":     {"y": 364.8, "size": 16.0, "color": 2600544},   # teal/grey
    "discount":     {"y": 407.5, "size": 16.0, "color": 3355443},
    "sub_total":    {"y": 469.4, "size": 16.0, "color": 3355443},
    "rounding":     {"y": 531.3, "size": 16.0, "color": 3355443},
    "net_fare":     {"y": 625.0, "size": 16.0, "color": 3355443},
}

# Row background colors for whiteout
# Use #F9F9F9 (approx (0.976, 0.976, 0.976)) for shaded rows
# Use #FFFFFF (1.0, 1.0, 1.0) for white rows
ROW_BACKGROUNDS: dict[str, tuple[float, float, float]] = {
    "total_amount": (0.976, 0.976, 0.976), # Header is Shaded (F9F9F9)
    "trip_fare":    (0.976, 0.976, 0.976), # Shaded
    "toll_tax":     (0.976, 0.976, 0.976), # Shaded (was 1.0 wrongly)
    "discount":     (0.976, 0.976, 0.976), # Shaded (was White)
    "sub_total":    (0.976, 0.976, 0.976), # Shaded
    "rounding":     (0.976, 0.976, 0.976), # Shaded (was White)
    "net_fare":     (0.976, 0.976, 0.976), # Shaded
}

# ──────────────────────────────────────────────
# Currency extraction — matches  ₹1,530  or  ₹ 1530  or embedded forms
# ──────────────────────────────────────────────
import re

CURRENCY_RE: re.Pattern = re.compile(
    r"[\u20b9\u20a8Rs\.]+\s*"          # ₹ or ₨ or Rs.
    r"([\d,]+(?:\.\d+)?)"               # capture digits (with optional decimal)
)

# ──────────────────────────────────────────────
# Formula constants
# ──────────────────────────────────────────────

# Default escalation multiplier (20 %)
DEFAULT_MULTIPLIER: float = 1.20

# Output currency prefix
CURRENCY_PREFIX: str = "₹"

# Global vertical shift for all edited values (negative = up)
GLOBAL_Y_NUDGE: float = -1.5

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
LOG_FILE: str = "batch_run.log"
