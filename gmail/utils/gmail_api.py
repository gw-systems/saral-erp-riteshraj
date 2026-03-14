"""
Gmail API utilities for email operations
Enhanced with HTML email support for Saral ERP
"""

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import base64
import logging

logger = logging.getLogger(__name__)


def create_message(sender, to, subject, message_text='', cc='', bcc='', attachments=None, html_body=None, reply_to=None):
    """
    Create an email message with support for both plain text and HTML

    Args:
        sender: Sender email address
        to: Recipient email address
        subject: Email subject
        message_text: Plain text version of email
        cc: CC recipients (comma-separated)
        bcc: BCC recipients (comma-separated)
        attachments: List of file attachments
        html_body: HTML version of email (NEW - for RFQ emails)
        reply_to: Reply-to email address (for POC support)

    Returns:
        Dict with 'raw' key containing base64url-encoded message
    """
    if html_body:
        # Create multipart/alternative message (plain text + HTML)
        msg = MIMEMultipart('alternative')
    else:
        # Create multipart message for attachments
        msg = MIMEMultipart()

    msg['to'] = to
    msg['from'] = sender
    msg['subject'] = subject

    if cc:
        msg['cc'] = cc
    if bcc:
        msg['bcc'] = bcc
    if reply_to:
        msg['reply-to'] = reply_to

    # Attach plain text version
    if message_text:
        text_part = MIMEText(message_text, 'plain', 'utf-8')
        msg.attach(text_part)

    # Attach HTML version (if provided)
    if html_body:
        html_part = MIMEText(html_body, 'html', 'utf-8')
        msg.attach(html_part)

    # Handle attachments
    if attachments:
        for attachment in attachments:
            try:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment['data'])
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {attachment["filename"]}'
                )
                msg.attach(part)
            except Exception as e:
                logger.error(f"Failed to attach file {attachment.get('filename', 'unknown')}: {e}")

    # Encode message as base64url
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {'raw': raw}


def send_gmail_api(service, user_id, message):
    """
    Send an email message using Gmail API

    Args:
        service: Authenticated Gmail API service object
        user_id: User's email address or 'me'
        message: Message dict with 'raw' key

    Returns:
        Sent message dict or None if failed
    """
    try:
        sent_message = service.users().messages().send(
            userId=user_id,
            body=message
        ).execute()

        logger.info(f"Email sent successfully. Message ID: {sent_message['id']}")
        return sent_message

    except Exception as e:
        error_str = str(e)

        # Check for insufficient scope error
        if '403' in error_str and 'gmail.send' in error_str.lower():
            logger.error(
                "Insufficient OAuth scope. The 'https://www.googleapis.com/auth/gmail.send' "
                "scope is required. Please re-authenticate the Gmail account."
            )
        else:
            logger.error(f"Failed to send email: {e}")

        return None


def fetch_emails(service, account_email, label_name='INBOX', max_results=10):
    """
    Fetch emails from Gmail

    Args:
        service: Authenticated Gmail API service object
        account_email: Email account being synced
        label_name: Gmail label to fetch (INBOX, SENT, etc.)
        max_results: Maximum number of emails to fetch

    Returns:
        List of email message dicts
    """
    try:
        # Get list of messages
        results = service.users().messages().list(
            userId='me',
            labelIds=[label_name],
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])

        email_list = []
        for msg in messages:
            # Get full message details
            message = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='full'
            ).execute()
            email_list.append(message)

        return email_list

    except Exception as e:
        logger.error(f"Failed to fetch emails for {account_email}: {e}")
        return []


def decode_base64(data):
    """Decode base64url-encoded data"""
    if not data:
        return ''

    try:
        # Add padding if needed
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)

        decoded = base64.urlsafe_b64decode(data)
        return decoded.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.error(f"Failed to decode base64: {e}")
        return ''
