"""
Custom template tags for operations app
"""
from django import template
from django.db.models import Q, Count
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

register = template.Library()


@register.simple_tag
def get_coordinator_billing_stats(user):
    """
    Get billing stats for coordinator dashboard
    Returns: dict with pending, submitted, approved, rejected counts
    """
    from operations.models import MonthlyBilling
    from projects.models import ProjectCode
    
    # Get last month (default billing month)
    last_month = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    
    # Get coordinator's projects
    user_name = user.get_full_name()
    projects = ProjectCode.objects.filter(
        Q(operation_coordinator=user_name) | Q(backup_coordinator=user_name),
        project_status__in=['Active', 'Notice Period']
    )
    
    # Get billing entries for last month
    billings = MonthlyBilling.objects.filter(
        project__in=projects,
        billing_month=last_month
    )
    
    stats = {
        'pending': billings.filter(status__code='draft').count(),
        'submitted': billings.filter(status__code__in=['submitted', 'controller_review', 'finance_review']).count(),
        'approved': billings.filter(status__code='approved').count(),
        'rejected': billings.filter(status__code__in=['controller_rejected', 'finance_rejected']).count(),
        'total_projects': projects.count(),
        'month': last_month,
    }
    
    return stats


@register.simple_tag
def get_pending_billing_reviews():
    """
    Get billing entries pending controller review
    Returns: QuerySet of MonthlyBilling objects
    """
    from operations.models import MonthlyBilling
    
    return MonthlyBilling.objects.filter(
        status__code='submitted'
    ).select_related('project', 'created_by').order_by('-submitted_at')


@register.simple_tag
def get_pending_finance_reviews():
    """
    Get billing entries pending finance review
    Returns: QuerySet of MonthlyBilling objects
    """
    from operations.models import MonthlyBilling
    
    return MonthlyBilling.objects.filter(
        status__code='finance_review'
    ).select_related('project', 'controller_reviewed_by').order_by('-controller_reviewed_at')


@register.simple_tag
def get_controller_billing_stats():
    """
    Get billing stats for controller dashboard
    """
    from operations.models import MonthlyBilling
    
    # Last month
    last_month = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    
    stats = {
        'pending_review': MonthlyBilling.objects.filter(status__code='submitted').count(),
        'approved_this_month': MonthlyBilling.objects.filter(
            status__code='finance_review',
            controller_reviewed_at__month=date.today().month
        ).count(),
        'rejected_this_month': MonthlyBilling.objects.filter(
            status__code='controller_rejected',
            controller_reviewed_at__month=date.today().month
        ).count(),
        'month': last_month,
    }
    
    return stats


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary using variable key"""
    return dictionary.get(key)


@register.filter
def replace(value, arg):
    """
    Replace substring in string
    Usage: {{ value|replace:"old,new" }}
    """
    if not arg or ',' not in arg:
        return value
    old, new = arg.split(',', 1)
    return str(value).replace(old, new)


@register.filter
def format_integration_name(value):
    """
    Format integration key to display name
    gmail_leads -> Gmail Leads
    google_ads -> Google Ads
    """
    return str(value).replace('_', ' ').title()


@register.filter
def format_sync_type(value):
    """
    Format sync type to display name
    gmail_leads_full -> Gmail Leads Full
    """
    return str(value).replace('_', ' ').title()


@register.filter
def split(value, arg):
    """
    Split string by delimiter
    Usage: {{ value|split:"," }}
    """
    if not value:
        return []
    return str(value).split(arg)