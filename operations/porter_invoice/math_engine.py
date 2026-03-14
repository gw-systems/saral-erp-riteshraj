"""
math_engine.py ΓÇö Pure-Decimal calculation chain for invoice values.

Chain logic (must always hold: net_fare == new_total):
    new_total  = original_total ├ù multiplier
    trip_fare  = new_total  - toll_tax + discount
    sub_total  = trip_fare  + toll_tax - discount   (== new_total always)
    rounding   = new_total  - sub_total             (should be 0.00 or tiny epsilon)
    net_fare   = new_total
"""

from typing import Optional
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Result dataclass
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

@dataclass
class InvoiceValues:
    original_total: Decimal
    new_total:      Decimal
    trip_fare:      Decimal
    toll_tax:       Decimal
    discount:       Decimal
    sub_total:      Decimal
    rounding:       Decimal
    net_fare:       Decimal

    def as_display_dict(self) -> dict[str, str]:
        """Return ₹-prefixed display strings for each field.
        The Source Sans Pro OTF font supports the ₹ glyph natively."""
        def fmt(v: Decimal, decimals: int = 2) -> str:
            if decimals == 0:
                s = f"{abs(v):,.0f}"
            else:
                s = f"{abs(v):,.2f}"
            return f"₹ {s}"

        def fmt_discount(v: Decimal) -> str:
            return f"– {fmt(v, decimals=2)}"

        def fmt_rounding(v: Decimal) -> str:
            # Rounding is negative when sub_total rounds DOWN to net_fare
            # e.g. 223.20 → 223 gives rounding = -0.20  → display "– ₹ 0.20"
            if v < 0:
                return f"– {fmt(v, decimals=2)}"
            return fmt(v, decimals=2)

        return {
            "total_amount": fmt(self.new_total, decimals=0),
            "trip_fare":    fmt(self.trip_fare, decimals=2),
            "toll_tax":     fmt(self.toll_tax, decimals=2),
            "discount":     fmt_discount(self.discount),
            "sub_total":    fmt(self.sub_total, decimals=2),
            "rounding":     fmt_rounding(self.rounding),
            "net_fare":     fmt(self.net_fare, decimals=2),
        }


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Core calculation
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def calculate_chain(
    original_total: Decimal,
    toll_tax:       Decimal,
    discount:       Decimal,
    original_trip_fare: Optional[Decimal] = None,
    multiplier:     float = 1.20,
    target_total:   Optional[Decimal] = None,
) -> InvoiceValues:
    """
    Apply the mathematical chain and return all derived values.

    Args:
        original_total: Scraped "Total Amount" from the PDF (₹, no symbol).
        toll_tax:       Scraped "Toll / Tax" value.
        discount:       Scraped "Discount" value.
        multiplier:     Escalation factor (default 1.20 = +20%).
        target_total:   Optional desired final total. If provided, multiplier is ignored.

    Returns:
        InvoiceValues with all fields computed.
    """
    if target_total is not None:
        new_total_val = target_total.quantize(Decimal("1."), rounding=ROUND_HALF_UP)
    else:
        m = Decimal(str(multiplier))
        new_total_val = (original_total * m).quantize(Decimal("1."), rounding=ROUND_HALF_UP)

    if original_trip_fare is not None:
        # Extract purely the decimal part (e.g., .80 from 1099.80)
        original_decimal = original_trip_fare % 1
    else:
        original_decimal = Decimal("0.00")

    # We need New Sub Total to round to New Total.
    # Sub Total = Trip Fare + Toll - Discount
    # Let C = Toll - Discount
    c = toll_tax - discount
    
    # We want to find an integer X such that: round(X + original_decimal + C) == new_total_val
    # X + round(original_decimal + C) == new_total_val
    # X = new_total_val - round(original_decimal + C)
    rounded_offset = (original_decimal + c).quantize(Decimal("1."), rounding=ROUND_HALF_UP)
    integer_part = new_total_val - rounded_offset
    
    # New Trip Fare = X + original_decimal
    trip_fare = (integer_part + original_decimal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Sub Total (should round cleanly to new_total_val)
    sub_total = (trip_fare + toll_tax - discount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Final Rounded Total (Net Fare)
    net_fare = sub_total.quantize(Decimal("1."), rounding=ROUND_HALF_UP)

    # 5. Rounding Adjustment
    rounding_val = (net_fare - sub_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 6. Header Total (same as Net Fare)
    new_total = net_fare

    return InvoiceValues(
        original_total=original_total,
        new_total=new_total,
        trip_fare=trip_fare,
        toll_tax=toll_tax,
        discount=discount,
        sub_total=sub_total,
        rounding=rounding_val,
        net_fare=net_fare,
    )


def parse_currency(text: str) -> Decimal:
    """
    Extract a Decimal value from a currency string like '₹1,530' or '1 g₹ng7'.
    Strips all non-numeric characters except the decimal point.

    Returns Decimal('0') if nothing numeric is found.
    """
    import re
    # Remove commas, currency symbols, and letters — keep digits and dot
    cleaned = re.sub(r"[^\d.]", "", text)
    if not cleaned or cleaned == ".":
        return Decimal("0")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0")
