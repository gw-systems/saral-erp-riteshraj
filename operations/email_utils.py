"""
Email utility functions for renewal and escalation tracking
Note: This is a placeholder for actual email integration
In production, integrate with your email service (SendGrid, AWS SES, etc.)
"""
import logging

from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_renewal_email(tracker, email_type):
    """
    Send renewal reminder email
    
    Args:
        tracker: AgreementRenewalTracker object
        email_type: 'initial', 'reminder_1', 'reminder_2', 'reminder_3', 'final'
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    
    # Email subject based on type
    subject_map = {
        'initial': f'Agreement Renewal - {tracker.project_card.project.project_code}',
        'reminder_1': f'Reminder: Agreement Renewal - {tracker.project_card.project.project_code}',
        'reminder_2': f'2nd Reminder: Agreement Renewal - {tracker.project_card.project.project_code}',
        'reminder_3': f'3rd Reminder: Agreement Renewal - {tracker.project_card.project.project_code}',
        'final': f'Final Notice: Agreement Expiry - {tracker.project_card.project.project_code}',
    }
    
    subject = subject_map.get(email_type, 'Agreement Renewal Notification')
    
    # Email body
    message = f"""
Dear Client,

This is regarding the agreement renewal for project: {tracker.project_card.project.project_code}

Agreement End Date: {tracker.project_card.agreement_end_date.strftime('%d %B %Y')}

Please respond at your earliest convenience.

Best regards,
{tracker.created_by.get_full_name()}
    """
    
    # In development, log to console
    logger.info(f"EMAIL SIMULATION - {email_type.upper()} | To: [Client Email] | Subject: {subject}")
    
    # Actual email sending (uncomment in production)
    # try:
    #     send_mail(
    #         subject=subject,
    #         message=message,
    #         from_email=settings.DEFAULT_FROM_EMAIL,
    #         recipient_list=['client@example.com'],  # Replace with actual client email
    #         fail_silently=False,
    #     )
    #     return True
    # except Exception as e:
    #     print(f"Email sending failed: {str(e)}")
    #     return False
    
    # For development, return True (simulated success)
    return True


def send_escalation_email(tracker, email_type):
    """
    Send escalation notification email
    
    Args:
        tracker: EscalationTracker object
        email_type: 'initial', 'reminder_1', 'reminder_2', 'final'
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    
    subject_map = {
        'initial': f'Escalation Notice - {tracker.project_card.project.project_code}',
        'reminder_1': f'Reminder: Escalation - {tracker.project_card.project.project_code}',
        'reminder_2': f'2nd Reminder: Escalation - {tracker.project_card.project.project_code}',
        'final': f'Final Notice: Escalation Application - {tracker.project_card.project.project_code}',
    }
    
    subject = subject_map.get(email_type, 'Escalation Notification')
    
    escalation_text = f"{tracker.escalation_percentage}%" if tracker.escalation_percentage else "as mutually agreed"
    
    message = f"""
Dear Client,

This is to inform you about the yearly escalation for project: {tracker.project_card.project.project_code}

Escalation Year: {tracker.escalation_year}
Escalation Date: {tracker.project_card.yearly_escalation_date.strftime('%d %B %Y')}
Escalation Rate: {escalation_text}

Please acknowledge receipt of this notice.

Best regards,
{tracker.created_by.get_full_name()}
    """
    
    # In development, log to console
    logger.info(f"EMAIL SIMULATION - ESCALATION {email_type.upper()} | To: [Client Email] | Subject: {subject}")
    
    # For development, return True (simulated success)
    return True


def notify_sales_manager(tracker, instance, notes):
    """
    Notify sales manager about renewal status
    
    Args:
        tracker: AgreementRenewalTracker object
        instance: '1' or '2' (first or second notification)
        notes: Communication notes
    
    Returns:
        bool: True if notification sent successfully
    """
    
    subject = f"Action Required: Agreement Renewal - {tracker.project_card.project.project_code}"
    
    message = f"""
Dear {tracker.project_card.project.sales_manager},

This is notification #{instance} regarding the agreement renewal for:

Project: {tracker.project_card.project.project_code}
Client: {tracker.project_card.project.client_name}
Agreement End Date: {tracker.project_card.agreement_end_date.strftime('%d %B %Y')}

Notes: {notes}

Please follow up with the client at your earliest convenience.

Best regards,
Operations Team
    """
    
    logger.info(f"SALES MANAGER NOTIFICATION #{instance} | To: {tracker.project_card.project.sales_manager} | Subject: {subject}")
    
    return True


def notify_finance_team(tracker, notes):
    """
    Notify finance team about escalation
    
    Args:
        tracker: EscalationTracker object
        notes: Notification notes
    
    Returns:
        bool: True if notification sent successfully
    """
    
    subject = f"Escalation to be Applied - {tracker.project_card.project.project_code}"
    
    escalation_text = f"{tracker.escalation_percentage}%" if tracker.escalation_percentage else "as mutually agreed"
    
    message = f"""
Dear Finance Team,

Please note that escalation is to be applied for:

Project: {tracker.project_card.project.project_code}
Client: {tracker.project_card.project.client_name}
Escalation Year: {tracker.escalation_year}
Escalation Rate: {escalation_text}
Escalation Date: {tracker.project_card.yearly_escalation_date.strftime('%d %B %Y')}

Notes: {notes}

Please process the escalation and update the rate card accordingly.

Best regards,
Operations Team
    """
    
    logger.info(f"FINANCE TEAM NOTIFICATION | To: Finance Team | Subject: {subject}")
    
    return True