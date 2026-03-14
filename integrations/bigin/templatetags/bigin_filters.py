from django import template

register = template.Library()

@register.filter
def clean_locations(value):
    """Clean location string and return list"""
    if not value:
        return []
    # Remove brackets and quotes
    cleaned = str(value).replace('[', '').replace(']', '').replace("'", "").replace('"', '')
    # Split by comma and clean
    return [loc.strip() for loc in cleaned.split(',') if loc.strip()]

@register.filter
def split_status(value):
    """Split comma-separated status values"""
    if not value:
        return []
    return [s.strip() for s in str(value).split(',') if s.strip()]

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    if not dictionary or not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)

@register.filter
def indian_number_format(value):
    """Format number with Indian comma standard (1,11,11,111)"""
    try:
        num = int(float(value))
    except (ValueError, TypeError):
        return value

    if num == 0:
        return '0'

    num_str = str(abs(num))

    # Handle numbers with less than 4 digits
    if len(num_str) <= 3:
        return ('-' if num < 0 else '') + num_str

    # Split into last 3 digits and rest
    last_three = num_str[-3:]
    remaining = num_str[:-3]

    # Add commas every 2 digits for remaining part
    result = last_three
    while remaining:
        if len(remaining) <= 2:
            result = remaining + ',' + result
            remaining = ''
        else:
            result = remaining[-2:] + ',' + result
            remaining = remaining[:-2]

    return ('-' if num < 0 else '') + result
