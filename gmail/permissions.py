"""
Permission system for Gmail app
Controls who can view/send emails from which accounts
"""

from .models import GmailToken


def can_view_email(user, email):
    """
    Check if user can view this email

    Args:
        user: Django User object
        email: Email object

    Returns:
        Boolean
    """
    # Admin, Director, Operation Controller can view ALL emails
    if user.role in ['admin', 'director', 'operation_controller']:
        return True

    # Regular users can only view emails from their own accounts
    return email.account_link.user == user


def can_access_account(user, email_account):
    """
    Check if user can access this Gmail account

    Args:
        user: Django User object
        email_account: Email address (string)

    Returns:
        Boolean
    """
    # Admin, Director, Operation Controller can access ALL accounts
    if user.role in ['admin', 'director', 'operation_controller']:
        return GmailToken.objects.filter(
            email_account=email_account,
            is_active=True
        ).exists()

    # Regular users can only access their own accounts
    return GmailToken.objects.filter(
        user=user,
        email_account=email_account,
        is_active=True
    ).exists()


def get_accessible_accounts(user):
    """
    Get all Gmail accounts accessible by this user

    Args:
        user: Django User object

    Returns:
        QuerySet of GmailToken objects
    """
    # Admin, Director, Operation Controller can access ALL accounts
    if user.role in ['admin', 'director', 'operation_controller']:
        return GmailToken.objects.filter(is_active=True)

    # Regular users see only their own accounts
    return GmailToken.objects.filter(user=user, is_active=True)
