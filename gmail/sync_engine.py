"""
Gmail Sync Engine - Thread-Aware
Enterprise-grade email syncing with thread grouping and incremental updates
"""

import logging
import time
from datetime import datetime
from typing import List, Dict, Optional
from django.utils import timezone
from django.db import transaction
from django.db.models import F
import email.utils
import base64

from gmail.models import (
    GmailToken, Thread, Message, Contact, Label, SyncStatus
)
from gmail.utils.gmail_auth import get_gmail_service
from gmail.sync_progress import SyncProgressTracker
from integrations.models import SyncLog
from integrations.sync_logger import SyncLogHandler

logger = logging.getLogger("gmail.sync")

# Module-level batch log holder (set at sync start, used by all helpers)
_current_batch_log = None
_current_sync_type = 'gmail_incremental'


def _gmail_log(level, operation, message='', sub_type='', duration_ms=None):
    """Helper: log a gmail operation to unified SyncLog."""
    if _current_batch_log is None:
        logger.warning(f"[Gmail Sync] _gmail_log called but _current_batch_log is None! Operation: {operation}")
        return

    SyncLog.log(
        integration='gmail',
        sync_type=_current_sync_type,
        level=level,
        operation=operation,
        message=message,
        sub_type=sub_type,
        duration_ms=duration_ms,
        batch=_current_batch_log,
    )


class SyncEngine:
    """Thread-aware sync engine for Gmail"""

    # Configuration
    SYNC_LABELS = ["INBOX", "SENT", "IMPORTANT"]
    MAX_RESULTS = 500
    BATCH_SIZE = 50

    @staticmethod
    def sync_account(gmail_token_id: int, full_sync: bool = False, scheduled_job_id=None):
        """
        Main sync entry point for a Gmail account

        Args:
            gmail_token_id: ID of GmailToken to sync
            full_sync: If True, do full sync instead of incremental
        """
        global _current_batch_log, _current_sync_type

        sync_type_str = "FULL" if full_sync else "INCREMENTAL"
        sync_type_key = 'gmail_full' if full_sync else 'gmail_incremental'
        _current_sync_type = sync_type_key

        logger.info(f"[Gmail Sync] ▶ Starting {sync_type_str} sync for token ID {gmail_token_id}")

        # Progress tracker for live UI updates
        tracker = SyncProgressTracker(token_id=gmail_token_id, sync_type=sync_type_key)
        tracker.start()

        # Create batch SyncLog entry
        batch_log = SyncLog.objects.create(
            integration='gmail',
            sync_type=sync_type_key,
            log_kind='batch',
            status='running',
            triggered_by_user=f'token_id:{gmail_token_id}',
            scheduled_job_id=scheduled_job_id,
        )
        _current_batch_log = batch_log

        sync_start = time.time()

        _sync_log_handler = SyncLogHandler(batch_log, integration='gmail', sync_type=sync_type_key,
                                           loggers=['gmail'])
        _sync_log_handler._attach()
        try:
            gmail_token = GmailToken.objects.get(id=gmail_token_id)
            logger.info(f"[Gmail Sync] Account: {gmail_token.email_account} (user: {gmail_token.user})")

            # Update batch log with account info
            batch_log.triggered_by_user = gmail_token.email_account
            batch_log.save(update_fields=['triggered_by_user'])

            tracker.update(message=f"Starting {sync_type_str} sync for {gmail_token.email_account}", progress_percentage=5)
            _gmail_log('INFO', 'Sync Start',
                       f"Starting {sync_type_str} sync for {gmail_token.email_account}")

            # Get sync status
            sync_status, created = SyncStatus.objects.get_or_create(
                gmail_token=gmail_token,
                defaults={'status': 'in_progress'}
            )
            sync_status.status = 'in_progress'
            sync_status.error_message = ''
            sync_status.save()
            logger.info(f"[Gmail Sync] Status set to in_progress (record {'created' if created else 'updated'})")

            # Get Gmail service (no outer transaction.atomic — logs must commit immediately for live polling)
            token_data = gmail_token.get_decrypted_token()
            if not token_data:
                raise ValueError("No valid token data — account may need to be reconnected")

            service = get_gmail_service(token_data)
            if not service:
                raise ValueError("Failed to create Gmail API service — check OAuth credentials")

            logger.info(f"[Gmail Sync] Gmail API service created successfully")
            tracker.update(message="Gmail API connected", progress_percentage=10)
            _gmail_log('INFO', 'API Service', "Gmail API service created successfully")

            # Sync labels first
            label_start = time.time()
            tracker.update(message="Syncing labels...", progress_percentage=15)
            SyncEngine._sync_labels(service, gmail_token)
            _gmail_log('INFO', 'Labels Synced',
                       f"Labels synced for {gmail_token.email_account}",
                       duration_ms=int((time.time() - label_start) * 1000))

            # Sync messages by label
            total_synced = 0
            threads_synced_set = set()
            label_count = len(SyncEngine.SYNC_LABELS)

            for i, label in enumerate(SyncEngine.SYNC_LABELS):
                # Check for stop request
                batch_log.refresh_from_db(fields=['stop_requested', 'status'])
                if batch_log.stop_requested:
                    logger.info(f"[Gmail Sync] Stop requested — halting after {label}")
                    tracker.update(message=f"Stop requested — halting sync", progress_percentage=int(20 + (i / label_count) * 75))
                    _gmail_log('WARNING', 'Stop Requested', f"Sync stopped by user request after processing {i}/{label_count} labels")
                    batch_log.status = 'stopped'
                    batch_log.completed_at = timezone.now()
                    batch_log.duration_seconds = int(time.time() - sync_start)
                    batch_log.records_created = total_synced
                    batch_log.error_message = 'Stopped by user request'
                    batch_log.save()
                    tracker.complete(success=False, message=f"Sync stopped: {total_synced} messages in {len(threads_synced_set)} threads saved")
                    return

                logger.info(f"[Gmail Sync] Processing label: {label}")
                label_start = time.time()
                pct = int(20 + (i / label_count) * 75)
                tracker.update(message=f"Syncing {label}...", progress_percentage=pct)
                _gmail_log('INFO', f'Label: {label}', f"Starting sync for label {label}...")

                synced, threads = SyncEngine._sync_label(
                    service, gmail_token, label, full_sync
                )
                label_ms = int((time.time() - label_start) * 1000)
                total_synced += synced
                threads_synced_set.update(threads)

                logger.info(f"[Gmail Sync] Label {label}: {synced} new messages in {len(threads)} threads")
                tracker.update(
                    message=f"{label}: {synced} new messages in {len(threads)} threads",
                    progress_percentage=int(20 + ((i + 1) / label_count) * 75),
                    messages_synced=total_synced,
                    threads_synced=len(threads_synced_set),
                )
                _gmail_log('INFO', f'Label: {label}',
                           f"{synced} new messages across {len(threads)} threads",
                           sub_type=label,
                           duration_ms=label_ms)

            # Update sync status
            sync_status.status = 'success'
            sync_status.last_sync_at = timezone.now()
            sync_status.emails_synced = total_synced
            sync_status.threads_synced = len(threads_synced_set)
            sync_status.error_message = ''
            sync_status.save()

            # Update gmail_token
            gmail_token.last_sync_at = timezone.now()
            gmail_token.save()

            total_duration = int((time.time() - sync_start) * 1000)
            completion_msg = (
                f"Completed {sync_type_str} sync for {gmail_token.email_account}: "
                f"{total_synced} new messages in {len(threads_synced_set)} threads"
            )
            logger.info(f"[Gmail Sync] ✅ {completion_msg}")
            _gmail_log('SUCCESS', 'Sync Complete', completion_msg, duration_ms=total_duration)

            # Finalize batch log
            batch_log.status = 'completed'
            batch_log.completed_at = timezone.now()
            batch_log.duration_seconds = int(time.time() - sync_start)
            batch_log.records_created = total_synced
            batch_log.total_records_synced = total_synced
            batch_log.module_results = {
                'threads_synced': len(threads_synced_set),
                'messages_synced': total_synced,
                'account': gmail_token.email_account,
            }
            batch_log.api_calls_count = batch_log.operations.count()
            batch_log.save()

            tracker.complete(
                success=True,
                message=f"✅ Sync complete: {total_synced} messages, {len(threads_synced_set)} threads",
                stats={'messages_synced': total_synced, 'threads_synced': len(threads_synced_set)},
            )

        except Exception as e:
            total_duration = int((time.time() - sync_start) * 1000)
            logger.error(f"[Gmail Sync] ❌ Sync failed for token {gmail_token_id}: {e}", exc_info=True)

            _gmail_log('ERROR', 'Sync Failed',
                       f"Sync failed: {str(e)}",
                       duration_ms=total_duration)

            # Finalize batch log as failed
            batch_log.status = 'failed'
            batch_log.completed_at = timezone.now()
            batch_log.duration_seconds = int(time.time() - sync_start)
            batch_log.error_message = str(e)
            batch_log.save()

            tracker.complete(success=False, message=f"❌ Sync failed: {str(e)}")

            try:
                sync_status = SyncStatus.objects.get(gmail_token_id=gmail_token_id)
                sync_status.status = 'error'
                sync_status.error_message = str(e)
                sync_status.save()
            except Exception:
                pass
            raise

        finally:
            _sync_log_handler._detach()
            _current_batch_log = None

    @staticmethod
    def _sync_labels(service, gmail_token):
        """Sync Gmail labels"""
        try:
            results = service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])

            for label_data in labels:
                label_type = label_data.get('type', 'user').lower()

                Label.objects.update_or_create(
                    account_link=gmail_token,
                    label_id=label_data['id'],
                    defaults={
                        'name': label_data['name'],
                        'type': label_type,
                    }
                )

            logger.info(f"[Gmail Sync] Labels: synced {len(labels)} labels for {gmail_token.email_account}")

        except Exception as e:
            logger.error(f"[Gmail Sync] Failed to sync labels: {e}")
            _gmail_log('ERROR', 'Labels Failed', f"Failed to sync labels: {str(e)}")

    @staticmethod
    def _sync_label(service, gmail_token, label_name, full_sync=False):
        """
        Sync messages for a specific label with thread grouping

        Returns:
            Tuple of (messages_synced_count, thread_ids_set)
        """
        try:
            # Build query
            query = f"label:{label_name}"

            # Fetch message list
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=SyncEngine.MAX_RESULTS
            ).execute()

            messages = results.get('messages', [])

            if not messages:
                logger.info(f"[Gmail Sync] No messages found for label {label_name}")
                return 0, set()

            # Group by thread_id
            threads_map = {}
            for msg in messages:
                thread_id = msg['threadId']
                if thread_id not in threads_map:
                    threads_map[thread_id] = []
                threads_map[thread_id].append(msg['id'])

            logger.info(
                f"[Gmail Sync] Label {label_name}: {len(messages)} messages in {len(threads_map)} threads"
            )

            # Process each thread
            synced_count = 0
            thread_ids = set()
            total_threads = len(threads_map)
            LOG_EVERY = 25  # Log progress every N threads

            for idx, (thread_id, message_ids) in enumerate(threads_map.items(), start=1):
                count = SyncEngine._process_thread(
                    service, gmail_token, thread_id, message_ids
                )
                synced_count += count
                thread_ids.add(thread_id)

                # Emit a progress log every LOG_EVERY threads so UI updates live
                if idx % LOG_EVERY == 0 or idx == total_threads:
                    _gmail_log(
                        'INFO', f'Label: {label_name}',
                        f"{idx}/{total_threads} threads processed, {synced_count} new messages so far",
                        sub_type=label_name,
                    )

            logger.info(
                f"[Gmail Sync] Label {label_name}: synced {synced_count} new messages "
                f"across {len(thread_ids)} threads (total {total_threads} threads found)"
            )

            return synced_count, thread_ids

        except Exception as e:
            logger.error(f"[Gmail Sync] Failed to sync label {label_name}: {e}", exc_info=True)
            _gmail_log('ERROR', f'Label Failed: {label_name}', f"Failed to sync label {label_name}: {str(e)}")
            return 0, set()

    @staticmethod
    def _process_thread(service, gmail_token, thread_id, message_ids):
        """
        Process a complete thread

        Args:
            service: Gmail API service
            gmail_token: GmailToken instance
            thread_id: Gmail thread ID
            message_ids: List of message IDs in this thread

        Returns:
            Number of messages processed
        """
        try:
            # Get or create Thread
            thread, created = Thread.objects.get_or_create(
                thread_id=thread_id,
                account_link=gmail_token,
                defaults={
                    'first_message_date': timezone.now(),
                    'last_message_date': timezone.now(),
                    'subject': '(No Subject)',
                }
            )

            if created:
                logger.debug(f"[Gmail Sync] New thread created: {thread_id}")

            # Fetch and save messages
            synced_count = 0
            skipped_count = 0
            for message_id in message_ids:
                # Check if message already exists
                if Message.objects.filter(message_id=message_id).exists():
                    skipped_count += 1
                    continue

                # Fetch full message
                msg_data = service.users().messages().get(
                    userId='me',
                    id=message_id,
                    format='full'
                ).execute()

                # Save message
                if SyncEngine._save_message(gmail_token, thread, msg_data):
                    synced_count += 1
                else:
                    logger.warning(f"[Gmail Sync] Failed to save message {message_id} in thread {thread_id}")

            if synced_count > 0 or skipped_count > 0:
                logger.debug(
                    f"[Gmail Sync] Thread {thread_id}: {synced_count} new, {skipped_count} already exist"
                )

            # Update thread metadata
            SyncEngine._update_thread_metadata(thread)

            return synced_count

        except Exception as e:
            logger.error(f"[Gmail Sync] Failed to process thread {thread_id}: {e}", exc_info=True)
            return 0

    @staticmethod
    def _save_message(gmail_token, thread, msg_data):
        """
        Save a message to database

        Returns:
            True if message was created, False otherwise
        """
        try:
            message_id = msg_data['id']

            # Check if already exists
            if Message.objects.filter(message_id=message_id).exists():
                return False

            # Parse headers
            headers = {
                h['name'].lower(): h['value']
                for h in msg_data['payload'].get('headers', [])
            }

            # Parse contacts
            contacts = SyncEngine._parse_contacts(headers)

            # Get or create from_contact
            from_contact = None
            if contacts['from']:
                from_data = contacts['from'][0]
                from_contact = SyncEngine._get_or_create_contact(
                    from_data['name'], from_data['email']
                )

            # Parse date
            date_str = headers.get('date', '')
            try:
                from email.utils import parsedate_to_datetime
                date = parsedate_to_datetime(date_str) if date_str else timezone.now()
            except:
                date = timezone.now()

            # Parse body
            body_text, body_html = SyncEngine._parse_body(msg_data['payload'])

            # Parse attachments
            has_attachments, attachments_meta = SyncEngine._parse_attachments(
                msg_data['payload']
            )

            # Get labels
            labels = msg_data.get('labelIds', [])
            is_read = 'UNREAD' not in labels
            is_starred = 'STARRED' in labels
            is_draft = 'DRAFT' in labels

            # Create message
            message = Message.objects.create(
                message_id=message_id,
                thread=thread,
                account_link=gmail_token,
                subject=headers.get('subject', '(No Subject)'),
                from_contact=from_contact,
                body_text=body_text,
                body_html=body_html,
                snippet=msg_data.get('snippet', ''),
                date=date,
                labels=labels,
                is_read=is_read,
                is_starred=is_starred,
                is_draft=is_draft,
                has_attachments=has_attachments,
                attachments_meta=attachments_meta,
                history_id=msg_data.get('historyId', ''),
                internal_date=msg_data.get('internalDate'),
            )

            # Add to_contacts
            for to_data in contacts['to']:
                contact = SyncEngine._get_or_create_contact(
                    to_data['name'], to_data['email']
                )
                message.to_contacts.add(contact)

            # Add cc_contacts
            for cc_data in contacts['cc']:
                contact = SyncEngine._get_or_create_contact(
                    cc_data['name'], cc_data['email']
                )
                message.cc_contacts.add(contact)

            # Add bcc_contacts
            for bcc_data in contacts['bcc']:
                contact = SyncEngine._get_or_create_contact(
                    bcc_data['name'], bcc_data['email']
                )
                message.bcc_contacts.add(contact)

            # Add participants to thread
            all_contacts = [from_contact] if from_contact else []
            all_contacts.extend([
                SyncEngine._get_or_create_contact(c['name'], c['email'])
                for c in contacts['to'] + contacts['cc'] + contacts['bcc']
            ])

            for contact in all_contacts:
                if contact:
                    thread.participants.add(contact)

            return True

        except Exception as e:
            logger.error(f"[Gmail Sync] Failed to save message {msg_data.get('id')}: {e}", exc_info=True)
            return False

    @staticmethod
    def _parse_contacts(headers):
        """
        Parse email headers to extract contacts

        Returns:
            dict with 'from', 'to', 'cc', 'bcc' contact lists
        """
        def extract_emails(header_value):
            if not header_value:
                return []
            addresses = email.utils.getaddresses([header_value])
            return [
                {'name': name.strip(), 'email': addr.lower().strip()}
                for name, addr in addresses if addr
            ]

        return {
            'from': extract_emails(headers.get('from', '')),
            'to': extract_emails(headers.get('to', '')),
            'cc': extract_emails(headers.get('cc', '')),
            'bcc': extract_emails(headers.get('bcc', ''))
        }

    @staticmethod
    def _get_or_create_contact(name, email):
        """
        Get or create contact with analytics update

        Returns:
            Contact instance
        """
        if not email:
            return None

        contact, created = Contact.objects.get_or_create(
            email=email.lower().strip(),
            defaults={'name': name.strip() if name else ''}
        )

        if not created and name and not contact.name:
            contact.name = name.strip()
            contact.save()

        # Update analytics
        Contact.objects.filter(id=contact.id).update(
            email_count=F('email_count') + 1,
            last_email_date=timezone.now()
        )

        return contact

    @staticmethod
    def _parse_body(payload):
        """
        Parse email body from payload

        Returns:
            Tuple of (body_text, body_html)
        """
        body_text = ''
        body_html = ''

        def decode_body(data):
            """Decode base64 body data"""
            if not data:
                return ''
            try:
                # Gmail uses URL-safe base64
                decoded = base64.urlsafe_b64decode(data)
                return decoded.decode('utf-8', errors='ignore')
            except:
                return ''

        def extract_body_recursive(part):
            """Recursively extract body from parts"""
            nonlocal body_text, body_html

            mime_type = part.get('mimeType', '')
            body = part.get('body', {})
            data = body.get('data', '')

            if mime_type == 'text/plain':
                body_text = decode_body(data)
            elif mime_type == 'text/html':
                body_html = decode_body(data)

            # Recursively process parts
            for subpart in part.get('parts', []):
                extract_body_recursive(subpart)

        extract_body_recursive(payload)

        return body_text, body_html

    @staticmethod
    def _parse_attachments(payload):
        """
        Parse attachments metadata from payload

        Returns:
            Tuple of (has_attachments, attachments_meta_list)
        """
        attachments = []

        def extract_attachments_recursive(part):
            """Recursively extract attachment metadata"""
            filename = part.get('filename', '')
            body = part.get('body', {})
            attachment_id = body.get('attachmentId', '')

            if filename and attachment_id:
                attachments.append({
                    'filename': filename,
                    'attachment_id': attachment_id,
                    'mime_type': part.get('mimeType', ''),
                    'size': body.get('size', 0)
                })

            # Recursively process parts
            for subpart in part.get('parts', []):
                extract_attachments_recursive(subpart)

        extract_attachments_recursive(payload)

        return len(attachments) > 0, attachments

    @staticmethod
    def _update_thread_metadata(thread):
        """Update thread cached metadata"""
        try:
            # Get all messages in thread
            messages = thread.messages.order_by('date')

            if not messages.exists():
                return

            # Update message count
            thread.message_count = messages.count()

            # Update has_unread
            thread.has_unread = messages.filter(is_read=False).exists()

            # Get first and last message
            first_msg = messages.first()
            last_msg = messages.last()

            thread.first_message_date = first_msg.date
            thread.last_message_date = last_msg.date

            # Update subject from first message
            thread.subject = first_msg.subject

            # Update last sender
            if last_msg.from_contact:
                thread.last_sender_name = last_msg.from_contact.name or last_msg.from_contact.email
            else:
                thread.last_sender_name = 'Unknown'

            # Update snippet from last message
            thread.snippet = last_msg.snippet[:500]

            # Check if thread is starred
            thread.is_starred = messages.filter(is_starred=True).exists()

            thread.save()

        except Exception as e:
            logger.error(f"Failed to update thread metadata: {e}")
