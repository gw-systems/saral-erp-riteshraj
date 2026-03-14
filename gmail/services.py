"""
Gmail Email Service
Core business logic for sending and managing emails
Enhanced with permission system for Saral ERP
"""

from django.contrib.auth import get_user_model
from gmail.models import GmailToken, Message
from gmail.utils.gmail_api import create_message, send_gmail_api, fetch_emails
from gmail.utils.gmail_auth import get_gmail_service
from gmail.utils.encryption import EncryptionUtils
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class EmailService:
    """Service class for Gmail email operations"""

    @staticmethod
    def get_available_sender_accounts(user):
        """
        Get Gmail accounts that user can send from

        Args:
            user: Django User object

        Returns:
            QuerySet of GmailToken objects user can send from
        """
        # Admin & Director can send from ANY account
        if user.role in ['admin', 'director']:
            return GmailToken.objects.filter(is_active=True)

        # Regular users can only send from their own accounts
        return GmailToken.objects.filter(user=user, is_active=True)

    @staticmethod
    def can_send_from_account(user, sender_email):
        """
        Check if user has permission to send from this email account

        Args:
            user: Django User object
            sender_email: Email address to send from

        Returns:
            Boolean
        """
        # Admin & Director can send from any active account
        if user.role in ['admin', 'director']:
            return GmailToken.objects.filter(
                email_account=sender_email,
                is_active=True
            ).exists()

        # Regular users can only send from their own accounts
        return GmailToken.objects.filter(
            user=user,
            email_account=sender_email,
            is_active=True
        ).exists()

    @staticmethod
    def send_email(
        user,
        sender_email,
        to_email,
        subject,
        message_text='',
        cc='',
        bcc='',
        attachments=None,
        html_body=None,
        reply_to=None
    ):
        """
        Send an email using Gmail API

        Args:
            user: Django User object (requesting user)
            sender_email: Email address to send from
            to_email: Recipient email address
            subject: Email subject
            message_text: Plain text version
            cc: CC recipients (comma-separated)
            bcc: BCC recipients (comma-separated)
            attachments: List of attachment dicts
            html_body: HTML version of email (for RFQ emails)
            reply_to: Reply-to address (for POC support)

        Returns:
            Boolean indicating success
        """
        try:
            # Permission check
            if not EmailService.can_send_from_account(user, sender_email):
                logger.error(
                    f"User {user.username} does not have permission to send from {sender_email}"
                )
                return False

            # Get Gmail token
            if user.role in ['admin', 'director']:
                # Admin/Director: Get any account's token
                gmail_token = GmailToken.objects.filter(
                    email_account=sender_email,
                    is_active=True
                ).first()
            else:
                # Regular user: Get their own token
                gmail_token = GmailToken.objects.filter(
                    user=user,
                    email_account=sender_email,
                    is_active=True
                ).first()

            if not gmail_token:
                logger.error(f"No active Gmail token found for {sender_email}")
                return False

            # Decrypt token
            token_data = EncryptionUtils.decrypt(gmail_token.encrypted_token_data)
            if not token_data:
                logger.error(f"Failed to decrypt token for {sender_email}")
                return False

            # Get Gmail service
            service = get_gmail_service(token_data)
            if not service:
                logger.error(f"Failed to create Gmail service for {sender_email}")
                return False

            # Create message with HTML support
            msg = create_message(
                sender=sender_email,
                to=to_email,
                subject=subject,
                message_text=message_text,
                cc=cc,
                bcc=bcc,
                attachments=attachments,
                html_body=html_body,
                reply_to=reply_to
            )

            # Send message
            sent_message = send_gmail_api(service, 'me', msg)

            if sent_message:
                logger.info(
                    f"Email sent successfully from {sender_email} to {to_email}. "
                    f"Message ID: {sent_message['id']}"
                )

                # Sync sent folder to capture this email
                try:
                    fetch_emails(service, sender_email, 'SENT', 1)
                except Exception as e:
                    logger.warning(f"Failed to sync sent folder: {e}")

                return True
            else:
                return False

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    @staticmethod
    def sync_emails(gmail_token, label='INBOX', max_results=50):
        """
        DEPRECATED: Use gmail_sync.sync_gmail_account() instead
        Kept for backward compatibility

        Sync emails from Gmail to database

        Args:
            gmail_token: GmailToken object
            label: Gmail label to sync (INBOX, SENT, etc.)
            max_results: Maximum emails to fetch

        Returns:
            Number of emails synced
        """
        try:
            # Use new sync function
            from .gmail_sync import sync_gmail_account
            stats = sync_gmail_account(gmail_token, force_full=False)
            return stats.get('synced', 0)

        except Exception as e:
            logger.error(f"Failed to sync emails for {gmail_token.email_account}: {e}")
            return 0

    @staticmethod
    def get_recent_emails(user, limit=50):
        """
        Get recent emails for user

        Args:
            user: Django User object
            limit: Maximum number of emails to return

        Returns:
            QuerySet of Email objects
        """
        return Message.objects.filter(account_link__user=user).order_by('-date')[:limit]

    @staticmethod
    def get_emails_by_account(user, email_account, limit=50):
        """
        Get emails for specific account

        Args:
            user: Django User object
            email_account: Email account string
            limit: Maximum number of emails

        Returns:
            QuerySet of Email objects
        """
        emails = Message.objects.filter(
            account_link__user=user,
            account_link__email_account=email_account
        ).order_by('-date')[:limit]

        return emails
