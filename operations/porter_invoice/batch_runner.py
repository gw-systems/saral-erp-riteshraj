"""
batch_runner.py — Orchestrate bulk processing of all PDFs in a folder.

For each PDF:
  1. Extract Order Number from filename (e.g. invoice_CRN1091124414.pdf → CRN1091124414).
  2. Scrape field spans from the PDF.
  3. Run the math chain.
  4. Apply edits and save to output folder.
  5. Log results.

Future: Excel lookup for per-order New Total will be plugged in here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .config import DEFAULT_MULTIPLIER, LOG_FILE
from .math_engine import calculate_chain, parse_currency, InvoiceValues
from .pdf_reader import scrape_invoice_fields, FieldResult
from .pdf_editor import apply_edits
import fitz  # needed for fitz.Rect in discount masking logic


# ──────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────

def _setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("invoice_editor")
    logger.setLevel(logging.DEBUG)

    # File handler
    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))

    # Console handler (INFO and above only)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)-8s  %(message)s"))

    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger


# ──────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────

@dataclass
class ProcessResult:
    filename:     str
    order_number: str
    status:       str           # "success" | "skipped" | "error"
    old_total:    Optional[Decimal] = None
    new_total:    Optional[Decimal] = None
    warnings:     list[str] = None
    error:        Optional[str] = None


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

_ORDER_RE = re.compile(r"invoice[_\-]?([A-Za-z0-9]+)", re.IGNORECASE)

def extract_order_number(filename: str) -> str:
    """
    Pull the order/CRN number from a filename like 'invoice_CRN1091124414.pdf'.
    Falls back to the full stem if the pattern is not found.
    """
    stem = Path(filename).stem
    m = _ORDER_RE.search(stem)
    return m.group(1) if m else stem


# ──────────────────────────────────────────────
# Single-PDF processor
# ──────────────────────────────────────────────

def process_single(
    pdf_path:    Path,
    output_dir:  Path,
    multiplier:  float = DEFAULT_MULTIPLIER,
    target_total: Optional[Decimal] = None,
    dry_run:     bool  = False,
    logger:      Optional[logging.Logger] = None,
) -> ProcessResult:
    """
    Process one PDF invoice.

    Args:
        pdf_path:   Path to the source PDF.
        output_dir: Folder to write the edited PDF.
        multiplier: Escalation factor (default 1.20).
        target_total: Optional desired final total (overrides multiplier).
        dry_run:    If True, compute values but do NOT write output.
        logger:     Logger instance (creates one if None).

    Returns:
        ProcessResult with status and computed values.
    """
    log = logger or logging.getLogger("invoice_editor")
    filename = pdf_path.name
    order_number = extract_order_number(filename)
    log.debug(f"Processing: {filename}  (order={order_number}) target={target_total or multiplier}")

    try:
        # 1. Scrape field positions (spans) + OCR-read values
        try:
            field_results: dict[str, FieldResult] = scrape_invoice_fields(pdf_path)
        except Exception as e:
            log.warning(f"{filename}: Failed to open or parse PDF — SKIPPED. ({e})")
            return ProcessResult(
                filename=filename,
                order_number=order_number,
                status="error",
                error=f"Invalid or corrupted PDF: {e}",
            )

        # 2. Parse OCR'd values from FieldResult.value strings
        def _get_value(name: str) -> Decimal:
            fr = field_results.get(name)
            if fr is None or fr.value in ("", "0"):
                return Decimal("0")
            return parse_currency(fr.value)

        original_total = _get_value("total_amount")
        toll_tax        = _get_value("toll_tax")
        discount        = _get_value("discount")
        original_trip_fare = _get_value("trip_fare")

        if original_total == 0:
            log.warning(f"{filename}: Total Amount could not be read — SKIPPED.")
            return ProcessResult(
                filename=filename,
                order_number=order_number,
                status="skipped",
                error="Total Amount span not found or parsed as 0",
            )

        # 3. Run math chain
        values: InvoiceValues = calculate_chain(
            original_total=original_total,
            toll_tax=toll_tax,
            discount=discount,
            original_trip_fare=original_trip_fare,
            multiplier=multiplier,
            target_total=target_total,
        )

        display = values.as_display_dict()
        log.info(
            f"{filename}: {original_total} → {values.new_total}  "
            f"[trip={values.trip_fare}, toll={values.toll_tax}, "
            f"disc={values.discount}, sub={values.sub_total}, round={values.rounding}]"
        )

        if dry_run:
            log.info(f"  DRY-RUN — no output written for {filename}")
            return ProcessResult(
                filename=filename,
                order_number=order_number,
                status="success",
                old_total=original_total,
                new_total=values.new_total,
                warnings=[],
            )

        # 4. Apply edits and save — pass only the span object for positioning
        field_spans = {k: fr.span for k, fr in field_results.items()}
        output_path = output_dir / f"{pdf_path.name}"
        
        # Discount field has a separate "- ₹" prefix span far to the left (x~660 vs x~1090)
        # Old method: extend left by 500pts -> This covered the "Discount" label at x<200.
        # New method: target the prefix specifically with an extra whiteout rect.
        # Prefix is approx 430pts to the left of the number span.
        # We'll whiteout [x0-460, y0, x0-380, y1] for discount.
        extra_rects = {}
        if "discount" in field_spans and field_spans["discount"]:
            d_span = field_spans["discount"]
            x0, y0, x1, y1 = d_span.bbox
            # TODO: coordinate (x0-460) was covering the label. Need to debug exact position.
            # prefix_rect = fitz.Rect(x0 - 460, y0, x0 - 380, y1)
            # extra_rects["discount"] = [prefix_rect]
            pass

        # Do not overwrite these fields in the PDF (keep original text)
        for field in ["toll_tax", "discount", "rounding"]:
            display.pop(field, None)

        warnings = apply_edits(
            pdf_path,
            output_path,
            field_spans,
            display,
            override_left_extend={"discount": 50.0},
            extra_rects_map=extra_rects,
            y_nudge_map={"total_amount": -3.0},
        )
        for w in warnings:
            log.warning(f"  {filename}: {w}")

        return ProcessResult(
            filename=filename,
            order_number=order_number,
            status="success",
            old_total=original_total,
            new_total=values.new_total,
            warnings=warnings,
        )

    except Exception as exc:
        log.error(f"{filename}: Unexpected error — {exc}", exc_info=True)
        return ProcessResult(
            filename=filename,
            order_number=order_number,
            status="error",
            error=str(exc),
        )


# ──────────────────────────────────────────────
# Batch runner
# ──────────────────────────────────────────────

def run_batch(
    input_dir:  Path,
    output_dir: Path,
    multiplier: float = DEFAULT_MULTIPLIER,
    dry_run:    bool  = False,
    log_path:   Optional[Path] = None,
) -> list[ProcessResult]:
    """
    Process all *.pdf files in input_dir.

    Args:
        input_dir:  Folder containing source PDFs.
        output_dir: Folder where edited PDFs will be written.
        multiplier: Escalation factor.
        dry_run:    If True, no files are written.
        log_path:   Path to log file (defaults to batch_run.log in cwd).

    Returns:
        List of ProcessResult objects (one per PDF).
    """
    log_file = log_path or Path(LOG_FILE)
    logger = _setup_logger(log_file)

    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        logger.warning(f"No PDF files found in {input_dir}")
        return []

    logger.info(f"{'DRY-RUN — ' if dry_run else ''}Starting batch: {len(pdf_files)} PDFs")
    logger.info(f"  Input:  {input_dir}")
    logger.info(f"  Output: {output_dir}")
    logger.info(f"  Multiplier: {multiplier}  (×{multiplier:.0%} escalation)")

    results: list[ProcessResult] = []
    for i, pdf_path in enumerate(pdf_files, 1):
        logger.info(f"[{i}/{len(pdf_files)}] {pdf_path.name}")
        result = process_single(pdf_path, output_dir, multiplier, target_total=None, dry_run=dry_run, logger=logger)
        results.append(result)

    # Summary
    success = sum(1 for r in results if r.status == "success")
    skipped = sum(1 for r in results if r.status == "skipped")
    errors  = sum(1 for r in results if r.status == "error")
    logger.info(
        f"\n{'--'*25}\n"
        f"Batch complete: {success} success / {skipped} skipped / {errors} errors\n"
        f"Log saved to: {log_file.resolve()}\n"
        f"{'--'*25}"
    )
    return results
