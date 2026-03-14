from django import template

register = template.Library()

@register.filter
def split(value, arg):
    """Split string by delimiter"""
    if not value:
        return []
    return str(value).split(arg)

@register.filter
def trim(value):
    """Trim whitespace"""
    if not value:
        return value
    return str(value).strip()
