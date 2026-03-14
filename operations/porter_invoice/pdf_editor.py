"""
pdf_editor.py — "Invisible Edit" engine: white-out original value, overlay new value.

Two-step process per field:
  1. WHITEOUT  — draw a solid white filled rectangle over the old value area.
                 (NOT redaction annotations — those leave a visible border.)
  2. OVERLAY   — insert the new text using the original span's font variant,
                 loaded from the Source Sans Pro OTF files so ₹ renders correctly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from .pdf_reader import SpanInfo
from .config import ROW_BACKGROUNDS, GLOBAL_Y_NUDGE

# Standard row background color (used as fallback)
BG_COLOR_GREY = (0.976, 0.976, 0.976)  # #F9F9F9


# ──────────────────────────────────────────────
# Font resolution
# ──────────────────────────────────────────────

# Path to our local Source Sans Pro OTF files
from django.conf import settings as _django_settings
FONTS_DIR = Path(_django_settings.BASE_DIR) / "static" / "fonts" / "source-sans-pro"

# Map (bold, semibold-ish) flags to the correct OTF file
_FONT_FILES: dict[str, str] = {
    "bold":     "SourceSansPro-Bold.otf",
    "semibold": "SourceSansPro-Semibold.otf",
    "medium":   "SourceSansPro-Medium.otf",
    "regular":  "SourceSansPro-Regular.otf",
    "light":    "SourceSansPro-Light.otf",
    "black":    "SourceSansPro-Black.otf",
}

# Global cache for font bytes to strictly prevent GC/buffer issues
_FONT_CACHE: dict[str, bytes] = {}

def _get_font_bytes(font_name: str, less_bold: bool = False) -> bytes:
    """
    Return the bytes for the best-matching Source Sans Pro OTF.
    If less_bold=True, shift the weight down by one level.
    """
    f = font_name.lower()
    if "black" in f:
        key = "bold" if less_bold else "black"
    elif "bold" in f:
        key = "semibold" if less_bold else "bold"
    elif "semibold" in f or "demi" in f:
        key = "medium" if less_bold else "semibold"
    elif "medium" in f:
        key = "regular" if less_bold else "medium"
    elif "light" in f or "extralight" in f:
        key = "light" # Minimum weight
    else:
        # Regular
        key = "light" if less_bold else "regular"

    # Return cached if available
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
        
    path = FONTS_DIR / _FONT_FILES[key]
    if not path.exists():
        path = FONTS_DIR / _FONT_FILES["regular"]
        key = "regular"
        if key in _FONT_CACHE: 
            return _FONT_CACHE[key]

    # Load and cache
    try:
        data = path.read_bytes()
        _FONT_CACHE[key] = data
        return data
    except Exception as e:
        print(f"CRITICAL: Failed to read font {path}: {e}")
        return b""


# ──────────────────────────────────────────────
# Colour utilities
# ──────────────────────────────────────────────

def _int_to_rgb(color_int: int) -> tuple[float, float, float]:
    """Convert PyMuPDF integer colour → (r, g, b) floats in [0, 1]."""
    r = ((color_int >> 16) & 0xFF) / 255.0
    g = ((color_int >> 8)  & 0xFF) / 255.0
    b = (color_int         & 0xFF) / 255.0
    return (r, g, b)


# ──────────────────────────────────────────────
# Per-field replacement
# ──────────────────────────────────────────────

# How far left of the span x0 we extend the whiteout rect.
# This covers the ₹ prefix glyph that lives to the left of the digit span.
LEFT_EXTEND = 80.0   # must cover `- ₹` prefix (discount row is widest)
PADDING     = 3.0


def replace_span(
    page:      fitz.Page,
    span:      SpanInfo,
    new_text:  str,
    font_ref:  str,          # xref name like "F0" registered via insert_font
    left_extend: float = LEFT_EXTEND,
    fill_color: tuple[float, float, float] = BG_COLOR_GREY,
    extra_whiteout_rects: list[fitz.Rect] = [],
    y_nudge: float = 0.0,
    less_bold: bool = False,
) -> None:
    """
    Insert text for a single span. 
    NOTE: Redaction must be applied via page.apply_redactions() BEFORE calling this,
    as apply_redactions clears all registered fonts.
    """
    x0, y0, x1, y1 = span.bbox
    rgb = _int_to_rgb(span.color)

    # Measure text width so we can right-align it to x1
    try:
        font_data = _get_font_bytes(span.font, less_bold=less_bold)
        font_obj = fitz.Font(fontbuffer=font_data)
        text_w = font_obj.text_length(new_text, fontsize=span.size)
    except Exception:
        text_w = 0.0

    # Start x = x1 - text_width (right-aligned to original value column edge)
    insert_x = max(x0 - LEFT_EXTEND, x1 - text_w)
    # Baseline offset: y1 includes descenders; visual baseline is ~15% of font size above y1
    insert_y = y1 - span.size * 0.15 + y_nudge + GLOBAL_Y_NUDGE

    page.insert_text(
        point=fitz.Point(insert_x, insert_y),
        text=new_text,
        fontname=font_ref,
        fontsize=span.size,
        color=rgb,
    )


# ──────────────────────────────────────────────
# Full invoice edit
# ──────────────────────────────────────────────

def apply_edits(
    pdf_path:    Path,
    output_path: Path,
    field_spans: dict[str, Optional[SpanInfo]],
    new_values:  dict[str, str],
    override_left_extend: dict[str, float] = {},
    extra_rects_map: dict[str, list[fitz.Rect]] = {},
    y_nudge_map: dict[str, float] = {},
) -> list[str]:
    """
    Apply all field replacements to a PDF and save to output_path.

    Process:
      1. Batch all redaction annotations (whiteout).
      2. Apply redactions (this clears internal font state).
      3. Register fonts and insert new text overlays.
    """
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    warnings: list[str] = []

    # ── Pass 1: Redaction Annotations ────────────────────────────────────
    for field_name in new_values:
        span = field_spans.get(field_name)
        if not span:
            continue

        left_ext = override_left_extend.get(field_name, LEFT_EXTEND)
        bg = ROW_BACKGROUNDS.get(field_name, BG_COLOR_GREY)
        extras = extra_rects_map.get(field_name, [])

        x0, y0, x1, y1 = span.bbox
        whiteout_rect = fitz.Rect(
            x0 - left_ext - PADDING,
            y0 - PADDING,
            x1 + PADDING,
            y1 + PADDING,
        )
        page.add_redact_annot(whiteout_rect, fill=bg)
        for r in extras:
            page.add_redact_annot(r, fill=bg)

    # ── Pass 2: Commit Redactions ────────────────────────────────────────
    # CRITICAL: This MUST happen before Pass 3 because it resets font state.
    page.apply_redactions()

    # ── Pass 3: Text Overlay ─────────────────────────────────────────────
    # Register all required Source Sans Pro variants as embedded fonts (Pass 3)
    _registered: dict[str, str] = {}

    def _get_font_ref(font_name: str, less_bold: bool = False) -> str:
        cache_key = f"{font_name}|less={less_bold}"
        if cache_key not in _registered:
            idx = len(_registered)
            ref_name = f"SourceSP{idx}"
            font_data = _get_font_bytes(font_name, less_bold=less_bold)
            page.insert_font(fontname=ref_name, fontbuffer=font_data)
            _registered[cache_key] = ref_name
        return _registered[cache_key]

    for field_name, new_text in new_values.items():
        span = field_spans.get(field_name)
        if span is None:
            warnings.append(f"Field '{field_name}' not found — skipped.")
            continue
        try:
            # Do not shift weight down for any field. Maintain original PDF weights.
            should_less_bold = False
            
            font_ref = _get_font_ref(span.font, less_bold=should_less_bold)
            left_ext = override_left_extend.get(field_name, LEFT_EXTEND)
            bg = ROW_BACKGROUNDS.get(field_name, BG_COLOR_GREY)
            extras = extra_rects_map.get(field_name, [])

            replace_span(
                page, span, new_text, font_ref, 
                left_extend=left_ext, 
                fill_color=bg,
                extra_whiteout_rects=extras,
                y_nudge=y_nudge_map.get(field_name, 0.0),
                less_bold=should_less_bold,
            )
        except Exception as exc:
            warnings.append(f"Field '{field_name}' edit failed: {exc}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()
    return warnings


