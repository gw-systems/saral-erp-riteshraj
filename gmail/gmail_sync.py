"""
Gmail Sync Utilities
Similar to Bigin sync pattern - periodic background syncing of emails
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from .models import GmailToken, Email, Contact, SyncStatus
from .utils.gmail_auth import get_gmail_service
from .utils.gmail_api import decode_base64
from .utils.encryption import EncryptionUtils

User = get_user_model()
logger = logging.getLogger("gmail.sync")


# -------------------------
# Configuration
# -------------------------
CONFIG = {
    "SYNC_LABELS": ["INBOX", "SENT"],  # Labels to sync
    "MAX_EMAILS_PER_SYNC": 50,  # Max emails per account per sync
    "BATCH_SIZE": 20,  # Batch size for database operations
    "HISTORY_SYNC_DAYS": 7,  # How many days back to sync initially
}


# -------------------------
# Token Management
# -------------------------
def get_valid_token_data(gmail_token: GmailToken) -> Optional[dict]:
    """
    Get valid token data from GmailToken, handling decryption

    Args:
        gmail_token: GmailToken model instance

    Returns:
        Dict with token data or None if failed
    """
    try:
        token_data = EncryptionUtils.decrypt(gmail_token.encrypted_token_data)
        if not token_data:
            logger.error(f"Failed to decrypt token for {gmail_token.email_account}")
            return None
        return token_data
    except Exception as e:
        logger.error(f"Error getting token data for {gmail_token.email_account}: {e}")
        return None


# -------------------------
# Email Parsing
# -------------------------
def parse_email_message(message: dict, account_link: GmailToken, account_email: str) -> Optional[Dict]:
    """
    Parse Gmail API message into Email model format

    Args:
        message: Raw Gmail API message dict
        account_link: GmailToken foreign key
        account_email: Email account string

    Returns:
        Dict with email data ready for Email.objects.create()
    """
    try:
        msg_id = message['id']
        thread_id = message['threadId']

        # Parse headers
        headers = {h['name'].lower(): h['value'] for h in message['payload'].get('headers', [])}

        subject = headers.get('subject', '(No Subject)')
        date_str = headers.get('date', '')
        sender = headers.get('from', '')
        to_recipients = headers.get('to', '')

        # Parse date
        try:
            # Gmail returns RFC 2822 format
            from email.utils import parsedate_to_datetime
            date = parsedate_to_datetime(date_str) if date_str else timezone.now()
        except:
            date = timezone.now()

        # Get snippet
        snippet = message.get('snippet', '')

        # Get labels
        labels = message.get('labelIds', [])

        # Check if read
        is_read = 'UNREAD' not in labels

        # Check for attachments
        has_attachments = any(
            part.get('filename')
            for part in message['payload'].get('parts', [])
        )

        # Extract body (text and HTML)
        body_text, body_html = _extract_body(message['payload'])

        return {
            'account_link': account_link,
            'account_email': account_email,
            'message_id': msg_id,
            'thread_id': thread_id,
            'subject': subject,
            'body_text': body_text,
            'body_html': body_html,
            'snippet': snippet,
            'labels': labels,
            'date': date,
            'is_read': is_read,
            'has_attachments': has_attachments,
            'sender_email': _extract_email(sender),
            'sender_name': _extract_name(sender),
            'recipients_str': to_recipients,
        }

    except Exception as e:
        logger.error(f"Failed to parse email message {message.get('id')}: {e}")
        return None


def _extract_body(payload: dict) -> tuple:
    """
    Extract text and HTML body from Gmail message payload

    Returns:
        (body_text, body_html) tuple
    """
    body_text = ''
    body_html = ''

    # Single part message
    if 'body' in payload and payload['body'].get('data'):
        mime_type = payload.get('mimeType', '')
        data = decode_base64(payload['body']['data'])

        if 'text/plain' in mime_type:
            body_text = data
        elif 'text/html' in mime_type:
            body_html = data

    # Multipart message
    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')

            if mime_type == 'text/plain' and part.get('body', {}).get('data'):
                body_text = decode_base64(part['body']['data'])
            elif mime_type == 'text/html' and part.get('body', {}).get('data'):
                body_html = decode_base64(part['body']['data'])

            # Recursive for nested parts
            elif 'parts' in part:
                text, html = _extract_body(part)
                if text:
                    body_text = text
                if html:
                    body_html = html

    return body_text, body_html


def _extract_email(email_str: str) -> str:
    """Extract email address from 'Name <email>' format"""
    import re
    match = re.search(r'<(.+?)>', email_str)
    if match:
        return match.group(1)
    return email_str


def _extract_name(email_str: str) -> str:
    """Extract name from 'Name <email>' format"""
    import re
    match = re.match(r'(.+?)\s*<', email_str)
    if match:
        return match.group(1).strip('"')
    return ''


# -------------------------
# Contact Management
# -------------------------
def get_or_create_contact(email: str, name: str = '') -> Optional[Contact]:
    """
    Get or create a Contact record

    Args:
        email: Contact email address
        name: Contact name (optional)

    Returns:
        Contact object or None
    """
    if not email:
        return None

    try:
        contact, created = Contact.objects.get_or_create(
            email=email,
            defaults={'name': name}
        )

        # Update name if provided and different
        if name and not contact.name:
            contact.name = name
            contact.save(update_fields=['name'])

        return contact
    except Exception as e:
        logger.error(f"Failed to create contact {email}: {e}")
        return None


# -------------------------
# Core Sync Function
# -------------------------
@transaction.atomic
def sync_gmail_account(gmail_token: GmailToken, force_full: bool = False) -> Dict:
    """
    Sync emails for a single Gmail account
    Similar to Bigin's sync_module pattern

    ATOMIC: Wrapped in transaction for database consistency.

    Args:
        gmail_token: GmailToken object to sync
        force_full: If True, fetch more history

    Returns:
        Dict with sync statistics
    """
    stats = {
        'synced': 0,
        'created': 0,
        'updated': 0,
        'errors': 0,
        'account': gmail_token.email_account
    }

    try:
        # Get or create sync status
        sync_status, _ = SyncStatus.objects.get_or_create(
            account_email=gmail_token.email_account,
            defaults={'status': 'in_progress'}
        )

        sync_status.status = 'in_progress'
        sync_status.save(update_fields=['status'])

        # Get token data
        token_data = get_valid_token_data(gmail_token)
        if not token_data:
            raise ValueError("Invalid token data")

        # Get Gmail service
        service = get_gmail_service(token_data)
        if not service:
            raise ValueError("Failed to create Gmail service")

        # Sync each label
        for label in CONFIG["SYNC_LABELS"]:
            logger.info(f"Syncing {label} for {gmail_token.email_account}")

            try:
                label_stats = _sync_label(
                    service=service,
                    gmail_token=gmail_token,
                    label=label,
                    max_results=CONFIG["MAX_EMAILS_PER_SYNC"]
                )

                stats['synced'] += label_stats['synced']
                stats['created'] += label_stats['created']
                stats['updated'] += label_stats['updated']
                stats['errors'] += label_stats['errors']

            except Exception as e:
                logger.error(f"Failed to sync {label} for {gmail_token.email_account}: {e}")
                stats['errors'] += 1

        # Update sync status
        sync_status.status = 'success' if stats['errors'] == 0 else 'error'
        sync_status.last_sync_at = timezone.now()
        sync_status.emails_synced = stats['synced']
        sync_status.error_message = ''
        sync_status.save()

        # Update token last_sync_at
        gmail_token.last_sync_at = timezone.now()
        gmail_token.save(update_fields=['last_sync_at'])

        logger.info(
            f"✅ Synced {stats['synced']} emails for {gmail_token.email_account} "
            f"(created: {stats['created']}, updated: {stats['updated']}, errors: {stats['errors']})"
        )

    except Exception as e:
        logger.error(f"Failed to sync {gmail_token.email_account}: {e}")
        stats['errors'] += 1

        # Update sync status
        try:
            sync_status.status = 'error'
            sync_status.error_message = str(e)
            sync_status.save()
        except:
            pass

    return stats


def _sync_label(service, gmail_token: GmailToken, label: str, max_results: int) -> Dict:
    """
    Sync emails for a specific label

    Returns:
        Dict with sync statistics
    """
    stats = {'synced': 0, 'created': 0, 'updated': 0, 'errors': 0}

    try:
        # Fetch messages from Gmail API
        results = service.users().messages().list(
            userId='me',
            labelIds=[label],
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])

        if not messages:
            logger.info(f"No messages found in {label}")
            return stats

        # Get existing message IDs to avoid duplicates
        existing_ids = set(
            Email.objects.filter(
                account_email=gmail_token.email_account
            ).values_list('message_id', flat=True)
        )

        logger.info(f"Found {len(messages)} messages in {label}, {len(existing_ids)} already synced")

        # Process messages in batches
        to_create = []

        for msg in messages:
            try:
                msg_id = msg['id']

                # Skip if already synced
                if msg_id in existing_ids:
                    stats['synced'] += 1
                    continue

                # Fetch full message details
                full_message = service.users().messages().get(
                    userId='me',
                    id=msg_id,
                    format='full'
                ).execute()

                # Parse message
                email_data = parse_email_message(
                    message=full_message,
                    account_link=gmail_token,
                    account_email=gmail_token.email_account
                )

                if not email_data:
                    stats['errors'] += 1
                    continue

                # Extract contact info for later processing
                sender_email = email_data.pop('sender_email', None)
                sender_name = email_data.pop('sender_name', '')
                recipients_str = email_data.pop('recipients_str', '')

                # Create email object (don't save yet)
                email_obj = Email(**email_data)

                # Store contact info for batch processing
                email_obj._sender_email = sender_email
                email_obj._sender_name = sender_name
                email_obj._recipients_str = recipients_str

                to_create.append(email_obj)
                stats['created'] += 1

                # Batch save when batch size reached
                if len(to_create) >= CONFIG["BATCH_SIZE"]:
                    _batch_save_emails(to_create)
                    to_create = []

            except Exception as e:
                logger.error(f"Failed to process message {msg.get('id')}: {e}")
                stats['errors'] += 1

        # Save remaining emails
        if to_create:
            _batch_save_emails(to_create)

        stats['synced'] = stats['created']

    except Exception as e:
        logger.error(f"Failed to sync label {label}: {e}")
        stats['errors'] += 1

    return stats


@transaction.atomic
def _batch_save_emails(emails: List[Email]):
    """
    Batch save emails with contact relationships

    Args:
        emails: List of Email objects to save
    """
    try:
        # Bulk create emails
        Email.objects.bulk_create(emails, ignore_conflicts=True, batch_size=100)

        # Process contacts
        for email in emails:
            try:
                # Create sender contact
                if hasattr(email, '_sender_email') and email._sender_email:
                    sender_contact = get_or_create_contact(
                        email=email._sender_email,
                        name=getattr(email, '_sender_name', '')
                    )
                    if sender_contact:
                        # Refresh email from DB to get ID
                        saved_email = Email.objects.get(message_id=email.message_id)
                        saved_email.sender_contact = sender_contact
                        saved_email.save(update_fields=['sender_contact'])

                # TODO: Parse and create recipient contacts
                # This would require parsing the recipients_str

            except Exception as e:
                logger.error(f"Failed to create contacts for email {email.message_id}: {e}")

        logger.info(f"✅ Batch saved {len(emails)} emails")

    except Exception as e:
        logger.error(f"Failed to batch save emails: {e}")
        raise


# -------------------------
# Sync All Accounts
# -------------------------
def sync_all_gmail_accounts(force_full: bool = False) -> Dict:
    """
    Sync all active Gmail accounts
    Similar to Bigin's download_bigin_contacts

    Args:
        force_full: If True, do full sync for all accounts

    Returns:
        Dict with overall sync statistics
    """
    overall_stats = {
        'total_accounts': 0,
        'successful': 0,
        'failed': 0,
        'total_emails': 0,
        'created': 0,
        'errors': 0,
        'accounts': []
    }

    try:
        # Get all active Gmail tokens
        gmail_tokens = GmailToken.objects.filter(is_active=True)
        overall_stats['total_accounts'] = gmail_tokens.count()

        logger.info(f"Starting sync for {overall_stats['total_accounts']} Gmail accounts")

        for gmail_token in gmail_tokens:
            try:
                logger.info(f"Syncing {gmail_token.email_account}...")

                stats = sync_gmail_account(gmail_token, force_full=force_full)

                overall_stats['successful'] += 1
                overall_stats['total_emails'] += stats['synced']
                overall_stats['created'] += stats['created']
                overall_stats['errors'] += stats['errors']
                overall_stats['accounts'].append(stats)

            except Exception as e:
                logger.error(f"Failed to sync {gmail_token.email_account}: {e}")
                overall_stats['failed'] += 1
                overall_stats['errors'] += 1

        logger.info(
            f"✅ Gmail sync complete: {overall_stats['successful']}/{overall_stats['total_accounts']} "
            f"accounts synced, {overall_stats['total_emails']} emails processed"
        )

    except Exception as e:
        logger.error(f"Failed to sync Gmail accounts: {e}")

    return overall_stats
