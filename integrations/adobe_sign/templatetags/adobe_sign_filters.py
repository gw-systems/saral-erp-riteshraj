from django import template

register = template.Library()


@register.filter
def replace(value, arg):
    """
    Replace all occurrences of arg (a 'old:new' string) in value.
    Usage: {{ value|replace:"_: " }}
    Falls back to removing the character if no ':' separator given.
    """
    if ':' in arg:
        old, new = arg.split(':', 1)
    else:
        old, new = arg, ''
    return str(value).replace(old, new)
