from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def smart_num(value):
    """
    Format a number removing unnecessary trailing zeros.
    6.87000  → 6.87
    56.0000  → 56
    46.9876  → 46.9876
    35.0909  → 35.0909
    0.0000   → 0
    """
    if value is None:
        return ''
    try:
        d = Decimal(str(value))
        # Normalize removes trailing zeros: 6.8700 → 6.87, 56.0000 → 56
        normalized = d.normalize()
        # If result is in scientific notation (e.g. 5E+2), convert to plain string
        result = format(normalized, 'f')
        return result
    except (InvalidOperation, ValueError):
        return value


@register.filter
def format_dispute_title(value):
    """
    Convert dispute title codes to readable labels.
    storage_space → Storage Space
    manpower_ot → Manpower/OT
    """
    if not value:
        return value

    # Mapping of old code values to proper labels
    title_map = {
        'storage_space': 'Storage Space',
        'handling': 'Handling',
        'manpower_ot': 'Manpower/OT',
        'operations': 'Operations',
        'mis_stock': 'MIS / Stock Issue',
        'billing_issue': 'Billing Issue',
    }

    # Return mapped value if exists, otherwise return as-is (for new properly formatted titles)
    return title_map.get(value.lower(), value)