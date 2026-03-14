"""
Gmail Integration Views
OAuth2 connection flow, settings management, and email viewing
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from django.db.models import Q, Prefetch
from django.core.paginator import Paginator

from gmail.models import (
    GmailSettings, GmailToken, Thread, Message, Contact, Draft, SyncStatus
)
from gmail.utils.gmail_auth import create_oauth_flow, get_authorization_url, exchange_code_for_token
from gmail.permissions import get_accessible_accounts
from gmail.search import SearchService
from gmail.sync_engine import SyncEngine
from integration_workers import create_task
from django.utils import timezone
import logging
import os
import json

# Allow HTTP for local development (REMOVE IN PRODUCTION)
if os.getenv('DJANGO_SETTINGS_MODULE') != 'minierp.settings_production':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

logger = logging.getLogger(__name__)


# =============================================================================
# SETTINGS
# =============================================================================

@login_required
def gmail_settings(request):
    """
    Gmail settings — OAuth configuration.
    GET: redirect to integrations hub (gmail_app tab).
    POST: save OAuth credentials, then redirect back to integrations hub.
    """
    is_admin = request.user.role in ['admin', 'director']

    if request.method == 'POST':
        if not is_admin:
            messages.error(request, "Admin access required to update OAuth settings")
            return redirect('accounts:admin_dashboard_integrations')

        settings = GmailSettings.load()
        client_id = request.POST.get('client_id', '').strip()
        client_secret = request.POST.get('client_secret', '').strip()
        redirect_uri = request.POST.get('redirect_uri', '').strip()

        settings.client_id = client_id
        settings.redirect_uri = redirect_uri
        if client_secret:
            settings.set_client_secret(client_secret)
        settings.updated_by = request.user
        settings.save()

        messages.success(request, "Gmail OAuth credentials updated successfully")
        return redirect('accounts:admin_dashboard_integrations')

    # GET — redirect to integrations hub
    return redirect('accounts:admin_dashboard_integrations')


# =============================================================================
# OAUTH CONNECTION
# =============================================================================

@login_required
def gmail_connect(request):
    """Step 1: Initiate OAuth2 flow to connect Gmail account"""
    try:
        # Check if settings configured
        settings = GmailSettings.load()
        if not settings.client_id or not settings.get_decrypted_client_secret():
            messages.error(
                request,
                "Gmail OAuth not configured. Please ask your administrator to configure OAuth settings."
            )
            return redirect('gmail:inbox')

        # Build redirect URI
        redirect_uri = request.build_absolute_uri(reverse('gmail:oauth_callback'))

        # Create OAuth flow
        flow = create_oauth_flow(redirect_uri)

        # Get authorization URL
        authorization_url, state = get_authorization_url(flow)

        # Store state in session for security
        request.session['gmail_oauth_state'] = state

        # Redirect to Google OAuth consent screen
        return redirect(authorization_url)

    except Exception as e:
        logger.error(f"Failed to initiate OAuth flow: {e}")
        messages.error(request, f"Failed to connect Gmail: {str(e)}")
        return redirect('gmail:inbox')


@login_required
def gmail_oauth_callback(request):
    """Step 2: Handle OAuth2 callback from Google"""
    try:
        # Verify state parameter
        state = request.session.get('gmail_oauth_state')
        if not state:
            raise ValueError("Invalid OAuth state")

        # Build redirect URI
        redirect_uri = request.build_absolute_uri(reverse('gmail:oauth_callback'))

        # Create OAuth flow with state
        flow = create_oauth_flow(redirect_uri)
        flow.state = state

        # Get full authorization response URL
        authorization_response = request.build_absolute_uri()

        # Exchange code for token
        token_data = exchange_code_for_token(flow, authorization_response)

        # Get user email from token — must not be null
        email_account = token_data.get('email') or request.user.email
        if not email_account:
            raise ValueError("Could not determine Gmail email address. Please ensure the Gmail API has userinfo scope.")

        # Create or update GmailToken
        gmail_token, created = GmailToken.objects.update_or_create(
            user=request.user,
            email_account=email_account,
            defaults={'is_active': True}
        )

        # Store encrypted token
        gmail_token.set_token(token_data)
        gmail_token.save()

        action = "connected" if created else "reconnected"
        messages.success(request, f"Gmail account {email_account} {action} successfully!")

        # Clear session state
        if 'gmail_oauth_state' in request.session:
            del request.session['gmail_oauth_state']

        # Trigger initial sync
        try:
            create_task(
                endpoint='/gmail/workers/sync-account/',
                payload={
                    'gmail_token_id': gmail_token.id,
                    'full_sync': True
                },
                task_name=f'gmail-sync-{gmail_token.id}-{int(timezone.now().timestamp())}'
            )
            messages.info(request, "Initial sync started in background")
        except Exception as e:
            logger.error(f"Failed to start initial sync: {e}")

        return redirect('gmail:inbox')

    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        messages.error(request, f"Failed to connect Gmail: {str(e)}")
        return redirect('gmail:inbox')


@login_required
def gmail_disconnect(request, token_id):
    """Disconnect a Gmail account"""
    if request.method == 'POST':
        try:
            token = GmailToken.objects.get(id=token_id)

            # Permission check
            if not token.can_be_accessed_by(request.user):
                messages.error(request, "You don't have permission to disconnect this account.")
                return redirect('gmail:inbox')

            email_account = token.email_account
            token.delete()

            messages.success(request, f"Gmail account {email_account} disconnected.")
        except GmailToken.DoesNotExist:
            messages.error(request, "Gmail account not found.")

    return redirect('gmail:gmail_settings')


# =============================================================================
# INBOX - WhatsApp-style UI
# =============================================================================

@login_required
def inbox(request):
    """
    Main inbox view with WhatsApp-style thread list
    """
    # Get accessible accounts
    accounts = get_accessible_accounts(request.user)

    # Check if OAuth is configured
    settings = GmailSettings.load()
    oauth_configured = bool(settings.client_id and settings.get_decrypted_client_secret())

    if not accounts.exists():
        # No accounts connected - show friendly message
        context = {
            'oauth_configured': oauth_configured,
            'is_admin': request.user.role in ['admin', 'director'],
            'page_title': 'Gmail Inbox'
        }
        return render(request, 'gmail/no_accounts.html', context)

    # Get filter parameters
    search_query = request.GET.get('search', '').strip()
    account_filter = request.GET.get('account', '')
    view_filter = request.GET.get('view', 'all')  # all, unread, starred, archived

    # Base queryset
    threads = Thread.get_threads_for_user(request.user)

    # Apply search
    if search_query:
        threads = SearchService.execute_search(request.user, search_query)
    else:
        # Apply view filters
        if view_filter == 'unread':
            threads = threads.filter(has_unread=True)
        elif view_filter == 'starred':
            threads = threads.filter(is_starred=True)
        elif view_filter == 'archived':
            threads = threads.filter(is_archived=True)
        else:  # all - exclude archived by default
            threads = threads.filter(is_archived=False)

        # Apply account filter
        if account_filter:
            threads = threads.filter(account_link__email_account=account_filter)

    # Optimize query with prefetch
    threads = threads.select_related('account_link').prefetch_related(
        'participants'
    ).order_by('-last_message_date')

    # Pagination
    paginator = Paginator(threads, 50)
    page_number = request.GET.get('page', 1)
    threads_page = paginator.get_page(page_number)

    context = {
        'accounts': accounts,
        'threads': threads_page,
        'search_query': search_query,
        'selected_account': account_filter,
        'selected_view': view_filter,
        'page_title': 'Gmail Inbox'
    }

    return render(request, 'gmail/inbox.html', context)


@login_required
def thread_detail_api(request, thread_id):
    """
    API endpoint: Get full thread conversation for display in right panel
    Returns JSON with all messages in thread
    """
    try:
        thread = Thread.objects.get(thread_id=thread_id)

        # Permission check
        if not thread.account_link.can_be_accessed_by(request.user):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Get all messages in thread
        messages_qs = thread.messages.select_related(
            'from_contact'
        ).prefetch_related(
            'to_contacts', 'cc_contacts', 'stored_attachments'
        ).order_by('date')

        # Build response
        messages_data = []
        for message in messages_qs:
            messages_data.append({
                'message_id': message.message_id,
                'subject': message.subject,
                'from': {
                    'name': message.from_contact.name if message.from_contact else 'Unknown',
                    'email': message.from_contact.email if message.from_contact else '',
                    'initial': message.from_contact.get_initial() if message.from_contact else '?'
                },
                'to': [
                    {'name': c.name, 'email': c.email}
                    for c in message.to_contacts.all()
                ],
                'cc': [
                    {'name': c.name, 'email': c.email}
                    for c in message.cc_contacts.all()
                ],
                'date': message.date.isoformat(),
                'date_display': timezone.localtime(message.date).strftime('%b %d, %Y %I:%M %p'),
                'body_html': message.body_html,
                'body_text': message.body_text,
                'is_read': message.is_read,
                'is_starred': message.is_starred,
                'has_attachments': message.has_attachments,
                'attachments': [
                    {
                        'id': att.id,
                        'filename': att.filename,
                        'size': att.size,
                        'mime_type': att.mime_type,
                        'is_downloaded': att.is_downloaded
                    }
                    for att in message.stored_attachments.all()
                ] if message.has_attachments else []
            })

        thread_data = {
            'thread_id': thread.thread_id,
            'subject': thread.subject,
            'is_starred': thread.is_starred,
            'is_archived': thread.is_archived,
            'has_unread': thread.has_unread,
            'message_count': thread.message_count,
            'account_email': thread.account_link.email_account,
            'participants': [
                {'name': p.name, 'email': p.email, 'initial': p.get_initial()}
                for p in thread.participants.all()
            ],
            'messages': messages_data
        }

        return JsonResponse({'success': True, 'thread': thread_data})

    except Thread.DoesNotExist:
        return JsonResponse({'error': 'Thread not found'}, status=404)
    except Exception as e:
        logger.error(f"Thread detail API failed: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# SYNC
# =============================================================================

@login_required
def sync_account(request, token_id):
    """AJAX endpoint: Manually trigger sync for a Gmail account"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        from django.conf import settings as django_settings

        # Get token and check permission
        token = GmailToken.objects.get(id=token_id)

        if not token.can_be_accessed_by(request.user):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Parse optional full_sync flag from request body
        full_sync = False
        try:
            body = json.loads(request.body)
            full_sync = body.get('full_sync', False)
        except Exception:
            pass

        sync_label = 'Full' if full_sync else 'Incremental'

        task_name = create_task(
            endpoint='/gmail/workers/sync-account/',
            payload={
                'gmail_token_id': token_id,
                'full_sync': full_sync
            },
            task_name=f'gmail-sync-{token_id}-{"full" if full_sync else "inc"}-{int(timezone.now().timestamp())}'
        )

        return JsonResponse({
            'status': 'started',
            'message': f'{sync_label} sync started for {token.email_account}',
            'task_name': task_name
        })

    except GmailToken.DoesNotExist:
        return JsonResponse({'error': 'Gmail account not found'}, status=404)
    except Exception as e:
        logger.error(f"Sync failed for token {token_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def sync_all_accounts(request):
    """AJAX endpoint: Sync all Gmail accounts (Admin only)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    # Permission check
    if request.user.role not in ['admin', 'director']:
        return JsonResponse({'error': 'Admin access required'}, status=403)

    try:
        from django.conf import settings as django_settings

        # Parse optional full_sync flag from request body
        full_sync = False
        try:
            body = json.loads(request.body)
            full_sync = body.get('full_sync', False)
        except Exception:
            pass

        sync_label = 'Full' if full_sync else 'Incremental'

        task_name = create_task(
            endpoint='/gmail/workers/sync-all-accounts/',
            payload={'full_sync': full_sync},
            task_name=f'gmail-sync-all-{"full" if full_sync else "inc"}-{int(timezone.now().timestamp())}'
        )

        return JsonResponse({
            'status': 'started',
            'message': f'{sync_label} sync started for all accounts',
            'task_name': task_name
        })

    except Exception as e:
        logger.error(f"Sync all accounts failed: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# SYNC PROGRESS / STOP
# =============================================================================

@login_required
def sync_progress(request, token_id):
    """AJAX endpoint: Real-time sync progress for a Gmail token (polling)."""
    from gmail.sync_progress import get_sync_progress
    try:
        token = GmailToken.objects.get(id=token_id)
        if not token.can_be_accessed_by(request.user):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        return JsonResponse(get_sync_progress(token_id))
    except GmailToken.DoesNotExist:
        return JsonResponse({'error': 'Gmail account not found'}, status=404)
    except Exception as e:
        logger.error(f"Failed to get sync progress for token {token_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def stop_sync(request, token_id):
    """AJAX endpoint: Request graceful stop of a running Gmail sync."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if request.user.role not in ['admin', 'director']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    try:
        from integrations.models import SyncLog as _SyncLog
        sync_log = _SyncLog.objects.filter(
            integration='gmail', log_kind='batch', status='running'
        ).order_by('-started_at').first()
        if not sync_log:
            return JsonResponse({'error': 'No running sync found'}, status=400)
        sync_log.stop_requested = True
        sync_log.save(update_fields=['stop_requested'])
        logger.info(f"[Gmail] Stop requested for sync {sync_log.id} by {request.user}")
        return JsonResponse({'status': 'success', 'message': 'Stop requested. Sync will finish the current label then stop.'})
    except Exception as e:
        logger.error(f"Stop sync failed: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def force_stop_sync(request, token_id):
    """AJAX endpoint: Immediately force-stop a running Gmail sync."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if request.user.role not in ['admin', 'director']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    try:
        from integrations.models import SyncLog as _SyncLog
        sync_log = _SyncLog.objects.filter(
            integration='gmail', log_kind='batch'
        ).order_by('-started_at').first()
        if not sync_log:
            return JsonResponse({'error': 'No sync log found'}, status=400)
        elapsed = int((timezone.now() - sync_log.started_at).total_seconds())
        sync_log.status = 'stopped'
        sync_log.stop_requested = True
        sync_log.completed_at = timezone.now()
        sync_log.duration_seconds = elapsed
        sync_log.error_message = f'Force-stopped by {request.user} after {elapsed}s'
        sync_log.save()
        logger.warning(f"[Gmail] Force-stopped sync {sync_log.id} by {request.user} after {elapsed}s")
        return JsonResponse({'status': 'success', 'message': f'Sync force-stopped after {elapsed}s.'})
    except Exception as e:
        logger.error(f"Force stop sync failed: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# UTILITY
# =============================================================================

@login_required
def get_sender_accounts(request):
    """
    AJAX endpoint: Get available sender accounts for current user
    Used in compose dialog and account filter
    """
    sender_accounts = get_accessible_accounts(request.user)

    data = [
        {
            'id': account.id,
            'email': account.email_account,
            'user': account.user.get_full_name()
        }
        for account in sender_accounts
    ]

    return JsonResponse({'accounts': data})


@login_required
def get_signature_api(request):
    """
    API endpoint: Get Gmail signature for a specific account token
    Fetches from Gmail API users.settings.sendAs
    """
    token_id = request.GET.get('token_id')
    if not token_id:
        return JsonResponse({'signature': ''})

    try:
        token = GmailToken.objects.get(id=token_id)

        if not token.can_be_accessed_by(request.user):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        from gmail.utils.gmail_auth import get_gmail_service
        token_data = token.get_decrypted_token()
        service = get_gmail_service(token_data)

        if not service:
            return JsonResponse({'signature': ''})

        # Get sendAs settings (includes signature for each send-as address)
        result = service.users().settings().sendAs().list(userId='me').execute()
        send_as_list = result.get('sendAs', [])

        # Find the primary (default) signature
        signature = ''
        for send_as in send_as_list:
            if send_as.get('isPrimary') or send_as.get('sendAsEmail') == token.email_account:
                signature = send_as.get('signature', '')
                break

        # Fallback to first available
        if not signature and send_as_list:
            signature = send_as_list[0].get('signature', '')

        return JsonResponse({'signature': signature, 'email': token.email_account})

    except GmailToken.DoesNotExist:
        return JsonResponse({'signature': ''})
    except Exception as e:
        logger.warning(f"Failed to fetch Gmail signature for token {token_id}: {e}")
        return JsonResponse({'signature': ''})


@login_required
def sync_status_api(request):
    """
    API endpoint: Get sync status for all accessible Gmail accounts
    Returns last sync time, counts, and status for each account
    """
    accounts = get_accessible_accounts(request.user)

    status_data = []
    for token in accounts:
        sync_status = SyncStatus.objects.filter(gmail_token=token).order_by('-updated_at').first()

        thread_count = Thread.objects.filter(account_link=token).count()
        unread_count = Thread.objects.filter(account_link=token, has_unread=True).count()

        status_data.append({
            'token_id': token.id,
            'email': token.email_account,
            'user': token.user.get_full_name(),
            'is_active': token.is_active,
            'last_sync_at': token.last_sync_at.isoformat() if token.last_sync_at else None,
            'last_sync_display': token.last_sync_at.strftime('%b %d, %I:%M %p') if token.last_sync_at else 'Never',
            'sync_status': sync_status.status if sync_status else 'unknown',
            'emails_synced': sync_status.emails_synced if sync_status else 0,
            'threads_synced': sync_status.threads_synced if sync_status else 0,
            'error_message': sync_status.error_message if sync_status else '',
            'thread_count': thread_count,
            'unread_count': unread_count,
        })

    return JsonResponse({'accounts': status_data})


@login_required
def api_sync_logs(request, batch_id):
    """
    API endpoint: Fetch detailed operation logs for a specific sync batch.
    Used by the integrations hub modal to show per-step logs.
    """
    if request.user.role not in ['admin', 'director', 'operation_controller']:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    from integrations.models import SyncLog as _SyncLog

    try:
        batch_log = _SyncLog.objects.get(pk=batch_id, integration='gmail', log_kind='batch')
        operation_logs = _SyncLog.objects.filter(
            batch=batch_log, log_kind='operation'
        ).order_by('started_at')

        logs = [
            {
                'id': op.id,
                'timestamp': timezone.localtime(op.started_at).strftime('%H:%M:%S'),
                'level': op.level,
                'operation': op.operation,
                'message': op.message or '',
                'duration_ms': op.duration_ms,
            }
            for op in operation_logs
        ]

        return JsonResponse({
            'logs': logs,
            'batch_status': batch_log.status,
            'batch_started': batch_log.started_at.isoformat(),
            'batch_completed': batch_log.completed_at.isoformat() if batch_log.completed_at else None,
        })

    except _SyncLog.DoesNotExist:
        return JsonResponse({'error': 'Sync log not found'}, status=404)
    except Exception as e:
        logger.error(f"Failed to fetch gmail sync logs: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def sync_logs(request):
    """
    View Gmail sync logs (admin/director only)
    """
    if request.user.role not in ['admin', 'director', 'operation_controller']:
        messages.error(request, "Access denied.")
        return redirect('gmail:inbox')

    from integrations.models import SyncLog
    from datetime import datetime

    batch_logs = SyncLog.objects.filter(integration='gmail', log_kind='batch').order_by('-started_at')[:50]
    op_logs = SyncLog.objects.filter(integration='gmail', log_kind='operation').order_by('-started_at')

    level_filter = request.GET.get('level', '')
    date_filter = request.GET.get('date', '')

    if level_filter:
        op_logs = op_logs.filter(level=level_filter)

    if date_filter:
        try:
            date_obj = datetime.strptime(date_filter, '%Y-%m-%d').date()
            op_logs = op_logs.filter(started_at__date=date_obj)
        except ValueError:
            pass

    op_logs = op_logs[:1000]

    context = {
        'batch_logs': batch_logs,
        'logs': op_logs,
        'level_filter': level_filter,
        'date_filter': date_filter,
        'page_title': 'Gmail Sync Logs',
    }
    return render(request, 'gmail/sync_logs.html', context)


@login_required
def threads_api(request):
    """
    API endpoint: List threads with filters (used by JavaScript to load thread list)
    Returns JSON list of threads for the frontend.
    """
    search_query = request.GET.get('search', '').strip()
    account_filter = request.GET.get('account', '')
    view_filter = request.GET.get('view', 'all')
    page = int(request.GET.get('page', 1))
    page_size = 50

    # Base queryset
    threads = Thread.get_threads_for_user(request.user)

    if search_query:
        threads = SearchService.execute_search(request.user, search_query)
    else:
        if view_filter == 'inbox':
            threads = threads.filter(is_archived=False, messages__labels__contains=['INBOX']).distinct()
        elif view_filter == 'sent':
            threads = threads.filter(messages__labels__contains=['SENT']).distinct()
        elif view_filter == 'starred':
            threads = threads.filter(is_starred=True)
        elif view_filter == 'drafts':
            threads = threads.filter(messages__labels__contains=['DRAFT']).distinct()
        elif view_filter == 'unread':
            threads = threads.filter(has_unread=True, is_archived=False)
        elif view_filter == 'archived':
            threads = threads.filter(is_archived=True)
        else:
            threads = threads.filter(is_archived=False)

        if account_filter:
            threads = threads.filter(account_link__email_account=account_filter)

    threads = threads.select_related('account_link').prefetch_related(
        'participants'
    ).order_by('-last_message_date')

    total = threads.count()
    total_pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size
    threads_page = threads[offset:offset + page_size]

    threads_data = []
    for thread in threads_page:
        # Get first participant initial for avatar
        first_participant = thread.participants.first()
        sender_name = thread.last_sender_name or 'Unknown'
        sender_initial = sender_name[0].upper() if sender_name else '?'
        sender_email = first_participant.email if first_participant else ''

        threads_data.append({
            'thread_id': thread.thread_id,
            'subject': thread.subject,
            'snippet': thread.snippet,
            'last_sender_name': thread.last_sender_name,
            'last_message_date': thread.last_message_date.isoformat(),
            'message_count': thread.message_count,
            'has_unread': thread.has_unread,
            'is_starred': thread.is_starred,
            'is_archived': thread.is_archived,
            'sender_initial': sender_initial,
            'sender_email': sender_email,
        })

    return JsonResponse({
        'threads': threads_data,
        'total': total,
        'total_pages': total_pages,
        'current_page': page,
    })
