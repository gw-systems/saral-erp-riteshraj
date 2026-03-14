"""
Gmail Action Views
Email operations: mark read/unread, archive, star, delete, send, draft management
"""

from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import transaction
import json
import logging

from gmail.models import GmailToken, Thread, Message, Draft, Attachment
from gmail.utils.gmail_auth import get_gmail_service
from django.core.files.base import ContentFile
import base64

logger = logging.getLogger("gmail.actions")


@login_required
@require_POST
def mark_as_read(request):
    """Mark message(s) as read"""
    try:
        data = json.loads(request.body)
        message_ids = data.get('message_ids', [])

        if not message_ids:
            return JsonResponse({'success': False, 'error': 'No message IDs provided'})

        messages = Message.objects.filter(message_id__in=message_ids)

        # Check permissions
        for message in messages:
            if not message.account_link.can_be_accessed_by(request.user):
                return JsonResponse({
                    'success': False,
                    'error': 'Permission denied'
                }, status=403)

        # Update in database
        messages.update(is_read=True)

        # Update in Gmail via API
        for message in messages:
            try:
                token_data = message.account_link.get_decrypted_token()
                service = get_gmail_service(token_data)

                if service:
                    service.users().messages().modify(
                        userId='me',
                        id=message.message_id,
                        body={'removeLabelIds': ['UNREAD']}
                    ).execute()
            except Exception as e:
                logger.error(f"Failed to mark message {message.message_id} as read in Gmail: {e}")

        # Update thread unread status
        thread_ids = messages.values_list('thread_id', flat=True).distinct()
        for thread_id in thread_ids:
            thread = Thread.objects.get(id=thread_id)
            thread.has_unread = thread.messages.filter(is_read=False).exists()
            thread.save()

        return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"Mark as read failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def mark_as_unread(request):
    """Mark message(s) as unread"""
    try:
        data = json.loads(request.body)
        message_ids = data.get('message_ids', [])

        if not message_ids:
            return JsonResponse({'success': False, 'error': 'No message IDs provided'})

        messages = Message.objects.filter(message_id__in=message_ids)

        # Check permissions
        for message in messages:
            if not message.account_link.can_be_accessed_by(request.user):
                return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        # Update in database
        messages.update(is_read=False)

        # Update in Gmail via API
        for message in messages:
            try:
                token_data = message.account_link.get_decrypted_token()
                service = get_gmail_service(token_data)

                if service:
                    service.users().messages().modify(
                        userId='me',
                        id=message.message_id,
                        body={'addLabelIds': ['UNREAD']}
                    ).execute()
            except Exception as e:
                logger.error(f"Failed to mark message {message.message_id} as unread in Gmail: {e}")

        # Update thread unread status
        thread_ids = messages.values_list('thread_id', flat=True).distinct()
        for thread_id in thread_ids:
            thread = Thread.objects.get(id=thread_id)
            thread.has_unread = True
            thread.save()

        return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"Mark as unread failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def archive_thread(request):
    """Archive entire thread"""
    try:
        data = json.loads(request.body)
        thread_id = data.get('thread_id')

        if not thread_id:
            return JsonResponse({'success': False, 'error': 'No thread ID provided'})

        thread = Thread.objects.get(thread_id=thread_id)

        # Permission check
        if not thread.account_link.can_be_accessed_by(request.user):
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        # Update in database
        thread.is_archived = True
        thread.save()

        # Remove INBOX label from all messages in Gmail
        token_data = thread.account_link.get_decrypted_token()
        service = get_gmail_service(token_data)

        if service:
            for message in thread.messages.all():
                try:
                    service.users().messages().modify(
                        userId='me',
                        id=message.message_id,
                        body={'removeLabelIds': ['INBOX']}
                    ).execute()
                except Exception as e:
                    logger.error(f"Failed to archive message {message.message_id}: {e}")

        return JsonResponse({'success': True})

    except Thread.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Thread not found'}, status=404)
    except Exception as e:
        logger.error(f"Archive thread failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def unarchive_thread(request):
    """Unarchive a thread"""
    try:
        data = json.loads(request.body)
        thread_id = data.get('thread_id')

        thread = Thread.objects.get(thread_id=thread_id)

        if not thread.account_link.can_be_accessed_by(request.user):
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        thread.is_archived = False
        thread.save()

        # Add INBOX label back
        token_data = thread.account_link.get_decrypted_token()
        service = get_gmail_service(token_data)

        if service:
            for message in thread.messages.all():
                try:
                    service.users().messages().modify(
                        userId='me',
                        id=message.message_id,
                        body={'addLabelIds': ['INBOX']}
                    ).execute()
                except Exception as e:
                    logger.error(f"Failed to unarchive message {message.message_id}: {e}")

        return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"Unarchive thread failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def toggle_star(request):
    """Toggle star on thread"""
    try:
        data = json.loads(request.body)
        thread_id = data.get('thread_id')

        thread = Thread.objects.get(thread_id=thread_id)

        if not thread.account_link.can_be_accessed_by(request.user):
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        # Toggle star
        thread.is_starred = not thread.is_starred
        thread.save()

        # Update in Gmail
        token_data = thread.account_link.get_decrypted_token()
        service = get_gmail_service(token_data)

        if service:
            label_action = 'addLabelIds' if thread.is_starred else 'removeLabelIds'

            for message in thread.messages.all():
                try:
                    service.users().messages().modify(
                        userId='me',
                        id=message.message_id,
                        body={label_action: ['STARRED']}
                    ).execute()
                except Exception as e:
                    logger.error(f"Failed to toggle star for message {message.message_id}: {e}")

        return JsonResponse({'success': True, 'is_starred': thread.is_starred})

    except Exception as e:
        logger.error(f"Toggle star failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def delete_thread(request):
    """Delete thread (move to trash in Gmail)"""
    try:
        data = json.loads(request.body)
        thread_id = data.get('thread_id')

        thread = Thread.objects.get(thread_id=thread_id)

        if not thread.account_link.can_be_accessed_by(request.user):
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        # Move to trash in Gmail
        token_data = thread.account_link.get_decrypted_token()
        service = get_gmail_service(token_data)

        if service:
            try:
                service.users().threads().trash(
                    userId='me',
                    id=thread.thread_id
                ).execute()
            except Exception as e:
                logger.error(f"Failed to trash thread in Gmail: {e}")

        # Delete from database
        thread.delete()

        return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"Delete thread failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def send_email(request):
    """Send a new email or reply"""
    try:
        data = json.loads(request.body)

        account_id = data.get('account_id')
        to_emails = data.get('to_emails', '')
        cc_emails = data.get('cc_emails', '')
        bcc_emails = data.get('bcc_emails', '')
        subject = data.get('subject', '')
        body_html = data.get('body_html', '')
        thread_id = data.get('thread_id')  # For replies
        in_reply_to = data.get('in_reply_to')  # Message-ID header for threading

        gmail_token = GmailToken.objects.get(id=account_id)

        if not gmail_token.can_be_accessed_by(request.user):
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        # Create email message
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        message = MIMEMultipart('alternative')
        message['To'] = to_emails
        if cc_emails:
            message['Cc'] = cc_emails
        if bcc_emails:
            message['Bcc'] = bcc_emails
        message['Subject'] = subject
        message['From'] = gmail_token.email_account

        # Add threading headers if replying
        if in_reply_to:
            message['In-Reply-To'] = in_reply_to
            message['References'] = in_reply_to

        # Add body
        html_part = MIMEText(body_html, 'html')
        message.attach(html_part)

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        # Send via Gmail API
        token_data = gmail_token.get_decrypted_token()
        service = get_gmail_service(token_data)

        if not service:
            return JsonResponse({'success': False, 'error': 'Failed to create Gmail service'})

        send_body = {'raw': raw_message}
        if thread_id:
            send_body['threadId'] = thread_id

        result = service.users().messages().send(
            userId='me',
            body=send_body
        ).execute()

        return JsonResponse({
            'success': True,
            'message_id': result['id'],
            'thread_id': result.get('threadId')
        })

    except Exception as e:
        logger.error(f"Send email failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def save_draft(request):
    """Save draft with auto-save support"""
    try:
        data = json.loads(request.body)

        draft_id = data.get('draft_id')
        account_id = data.get('account_id')
        thread_id = data.get('thread_id')
        to_emails = data.get('to_emails', '')
        cc_emails = data.get('cc_emails', '')
        bcc_emails = data.get('bcc_emails', '')
        subject = data.get('subject', '')
        body_html = data.get('body_html', '')

        gmail_token = GmailToken.objects.get(id=account_id)

        if not gmail_token.can_be_accessed_by(request.user):
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        # Get thread if specified
        thread = None
        if thread_id:
            try:
                thread = Thread.objects.get(thread_id=thread_id)
            except Thread.DoesNotExist:
                pass

        # Create or update draft
        if draft_id:
            draft = Draft.objects.get(id=draft_id)
        else:
            draft = Draft(account_link=gmail_token, thread=thread)

        draft.to_emails = to_emails
        draft.cc_emails = cc_emails
        draft.bcc_emails = bcc_emails
        draft.subject = subject
        draft.body_html = body_html
        draft.save()

        return JsonResponse({
            'success': True,
            'draft_id': draft.id
        })

    except Exception as e:
        logger.error(f"Save draft failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def get_draft(request):
    """Get draft for a thread"""
    try:
        thread_id = request.GET.get('thread_id')

        if not thread_id:
            return JsonResponse({'success': False, 'error': 'No thread ID'})

        try:
            draft = Draft.objects.filter(thread__thread_id=thread_id).latest('last_saved_at')

            return JsonResponse({
                'success': True,
                'draft': {
                    'id': draft.id,
                    'to_emails': draft.to_emails,
                    'cc_emails': draft.cc_emails,
                    'bcc_emails': draft.bcc_emails,
                    'subject': draft.subject,
                    'body_html': draft.body_html,
                }
            })

        except Draft.DoesNotExist:
            return JsonResponse({'success': True, 'draft': None})

    except Exception as e:
        logger.error(f"Get draft failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def download_attachment(request, attachment_id):
    """Download attachment from Gmail and serve to user"""
    try:
        attachment = Attachment.objects.get(id=attachment_id)

        # Permission check
        if not attachment.message.account_link.can_be_accessed_by(request.user):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # If already downloaded, serve from storage
        if attachment.is_downloaded and attachment.file:
            from django.http import FileResponse
            return FileResponse(
                attachment.file.open('rb'),
                as_attachment=True,
                filename=attachment.filename
            )

        # Download from Gmail
        token_data = attachment.message.account_link.get_decrypted_token()
        service = get_gmail_service(token_data)

        if not service:
            return JsonResponse({'error': 'Failed to create Gmail service'}, status=500)

        # Get attachment data
        att_data = service.users().messages().attachments().get(
            userId='me',
            messageId=attachment.message.message_id,
            id=attachment.attachment_id
        ).execute()

        # Decode data
        file_data = base64.urlsafe_b64decode(att_data['data'])

        # Save to storage
        attachment.file.save(
            attachment.filename,
            ContentFile(file_data),
            save=True
        )
        attachment.is_downloaded = True
        attachment.save()

        # Serve file
        from django.http import FileResponse
        return FileResponse(
            attachment.file.open('rb'),
            as_attachment=True,
            filename=attachment.filename
        )

    except Attachment.DoesNotExist:
        return JsonResponse({'error': 'Attachment not found'}, status=404)
    except Exception as e:
        logger.error(f"Download attachment failed: {e}")
        return JsonResponse({'error': str(e)}, status=500)
