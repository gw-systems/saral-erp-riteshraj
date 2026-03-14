from django import template
from accounts.models import User

register = template.Library()

@register.simple_tag
def get_active_coordinators():
    """Get all active users with coordinator role"""
    return User.objects.filter(
        role='operation_coordinator',
        is_active=True
    ).order_by('first_name', 'last_name')
