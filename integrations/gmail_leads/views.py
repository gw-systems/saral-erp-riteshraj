"""
Gmail Leads Views
Dashboard and management views for lead emails
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from django.db.models import Q, Count
from datetime import datetime, timedelta
from django.utils import timezone
import logging
import os

from .models import GmailLeadsToken, LeadEmail
from integrations.models import SyncLog
from .utils.gmail_auth import create_oauth_flow, get_authorization_url, exchange_code_for_token
from .utils.encryption import EncryptionUtils
from .sync_progress import get_sync_progress
from integration_workers import create_task
import json

# Allow HTTP for local development (REMOVE IN PRODUCTION)
if os.getenv('DJANGO_SETTINGS_MODULE') != 'minierp.settings_production':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    """
    Gmail Leads dashboard with Bigin-style table and column visibility
    """
    # Get accessible tokens (admin/director/digital_marketing sees all, users see their own)
    if request.user.role in ['admin', 'director', 'digital_marketing']:
        tokens = GmailLeadsToken.objects.filter(is_active=True)
    else:
        tokens = GmailLeadsToken.objects.filter(user=request.user, is_active=True)

    # Get leads queryset
    leads = LeadEmail.get_leads_for_user(request.user).order_by('-datetime_received')

    # Get filter parameters with default to current month
    now = timezone.now()
    default_start_date = now.replace(day=1).strftime('%Y-%m-%d')
    default_end_date = now.strftime('%Y-%m-%d')

    start_date = request.GET.get('start_date', default_start_date)
    end_date = request.GET.get('end_date', default_end_date)
    lead_type = request.GET.get('lead_type', '')
    search = request.GET.get('search', '')

    # Multi-select filters
    def parse_filter_list(param_name):
        values = request.GET.getlist(param_name)
        if values:
            result = []
            for val in values:
                if ',' in val:
                    result.extend([v.strip() for v in val.split(',') if v.strip()])
                else:
                    result.append(val)
            return result
        single_val = request.GET.get(param_name, '')
        if single_val:
            return [v.strip() for v in single_val.split(',') if v.strip()]
        return []

    utm_campaign_list = parse_filter_list('utm_campaign')
    utm_medium_list = parse_filter_list('utm_medium')
    utm_content_list = parse_filter_list('utm_content')
    form_email_list = parse_filter_list('form_email')

    # Apply date filters
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            leads = leads.filter(date_received__gte=start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            leads = leads.filter(date_received__lte=end_dt)
        except ValueError:
            pass

    # Apply lead type filter
    if lead_type:
        leads = leads.filter(lead_type=lead_type)

    # Apply search
    if search:
        leads = leads.filter(
            Q(form_name__icontains=search) |
            Q(form_email__icontains=search) |
            Q(form_phone__icontains=search) |
            Q(form_company_name__icontains=search) |
            Q(message_preview__icontains=search) |
            Q(utm_campaign__icontains=search)
        )

    # Apply multi-select filters
    if utm_campaign_list:
        campaign_query = Q()
        for campaign in utm_campaign_list:
            campaign_query |= Q(utm_campaign__iexact=campaign)
        leads = leads.filter(campaign_query)

    if utm_medium_list:
        medium_query = Q()
        for medium in utm_medium_list:
            medium_query |= Q(utm_medium__iexact=medium)
        leads = leads.filter(medium_query)

    if utm_content_list:
        content_query = Q()
        for content in utm_content_list:
            content_query |= Q(utm_content__iexact=content)
        leads = leads.filter(content_query)

    if form_email_list:
        email_query = Q()
        for email in form_email_list:
            email_query |= Q(form_email__iexact=email)
        leads = leads.filter(email_query)

    # Get distinct filter options
    all_leads = LeadEmail.get_leads_for_user(request.user)
    utm_campaigns = all_leads.values_list('utm_campaign', flat=True).distinct().order_by('utm_campaign')
    utm_campaigns = [c for c in utm_campaigns if c]  # Remove empty values

    utm_mediums = all_leads.values_list('utm_medium', flat=True).distinct().order_by('utm_medium')
    utm_mediums = [m for m in utm_mediums if m]

    utm_contents = all_leads.values_list('utm_content', flat=True).distinct().order_by('utm_content')
    utm_contents = [c for c in utm_contents if c]

    # Limit results
    leads_displayed = leads[:500]

    # Get statistics based on filtered date range
    filtered_leads = LeadEmail.get_leads_for_user(request.user)

    # Apply date filters to stats
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            filtered_leads = filtered_leads.filter(date_received__gte=start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            filtered_leads = filtered_leads.filter(date_received__lte=end_dt)
        except ValueError:
            pass

    # Calculate stats for the selected date range
    today_date = timezone.now().date()

    stats = {
        # Total leads for selected date range (Contact Us + SAAS Inventory)
        'total': filtered_leads.count(),

        # Contact Us leads for selected date range
        'contact_us': filtered_leads.filter(lead_type='CONTACT_US').count(),

        # Today's Contact Us leads
        'today_contact_us': filtered_leads.filter(
            lead_type='CONTACT_US',
            date_received=today_date
        ).count(),

        # SAAS Inventory leads for selected date range
        'saas_inventory': filtered_leads.filter(lead_type='SAAS_INVENTORY').count(),

        # Today's SAAS Inventory leads
        'today_saas_inventory': filtered_leads.filter(
            lead_type='SAAS_INVENTORY',
            date_received=today_date
        ).count(),
    }

    context = {
        'tokens': tokens,
        'leads': leads_displayed,
        'stats': stats,
        'utm_campaigns': utm_campaigns,
        'utm_mediums': utm_mediums,
        'utm_contents': utm_contents,
        'start_date': start_date,
        'end_date': end_date,
        'selected_lead_type': lead_type,
        'search': search,
        'selected_utm_campaigns': utm_campaign_list,
        'selected_utm_mediums': utm_medium_list,
        'selected_utm_contents': utm_content_list,
        'page_title': 'Gmail Lead Fetcher'
    }

    return render(request, 'gmail_leads/dashboard.html', context)


@login_required
def connect(request):
    """
    Step 1: Initiate OAuth2 flow to connect Gmail Leads account
    """
    try:
        # Use configured redirect URI (must match Google Cloud Console exactly)
        from integrations.gmail_leads.utils.settings_helper import get_gmail_leads_config
        gmail_config = get_gmail_leads_config()
        redirect_uri = gmail_config['redirect_uri']

        # Create OAuth flow
        flow = create_oauth_flow(redirect_uri)

        # Get authorization URL
        authorization_url, state = get_authorization_url(flow)

        # Store state in session for security
        request.session['gmail_leads_oauth_state'] = state

        # Redirect to Google OAuth consent screen
        return redirect(authorization_url)

    except Exception as e:
        logger.error(f"Failed to initiate OAuth flow: {e}")
        messages.error(request, f"Failed to connect Gmail: {str(e)}")
        return redirect('gmail_leads:dashboard')


@login_required
def oauth_callback(request):
    """
    Step 2: Handle OAuth2 callback from Google
    Exchange authorization code for access token
    """
    try:
        # Verify state parameter
        state = request.session.get('gmail_leads_oauth_state')
        if not state:
            raise ValueError("Invalid OAuth state")

        # Use configured redirect URI (must match Google Cloud Console exactly)
        from integrations.gmail_leads.utils.settings_helper import get_gmail_leads_config
        from django.conf import settings
        gmail_config = get_gmail_leads_config()
        redirect_uri = gmail_config['redirect_uri']

        # Create OAuth flow with state
        flow = create_oauth_flow(redirect_uri)
        flow.state = state

        # Get full authorization response URL (ensure https for production)
        authorization_response = request.build_absolute_uri()
        if authorization_response.startswith('http://') and not settings.DEBUG:
            authorization_response = authorization_response.replace('http://', 'https://', 1)

        # Exchange code for token
        token_data = exchange_code_for_token(flow, authorization_response)

        # Get user email from token (provided by Google)
        email_account = token_data.get('email', request.user.email)

        # Encrypt and store token
        encrypted_token = EncryptionUtils.encrypt(token_data)

        # Create or update GmailLeadsToken
        gmail_token, created = GmailLeadsToken.objects.update_or_create(
            email_account=email_account,
            defaults={
                'user': request.user,
                'encrypted_token_data': encrypted_token,
                'is_active': True
            }
        )

        action = "connected" if created else "reconnected"
        messages.success(request, f"Gmail Leads account {email_account} {action} successfully!")

        # Clear session state
        if 'gmail_leads_oauth_state' in request.session:
            del request.session['gmail_leads_oauth_state']

        return redirect('gmail_leads:dashboard')

    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        messages.error(request, f"Failed to connect Gmail: {str(e)}")
        return redirect('gmail_leads:dashboard')


@login_required
def disconnect(request, token_id):
    """
    Disconnect a Gmail Leads account
    """
    if request.method == 'POST':
        try:
            token = GmailLeadsToken.objects.get(id=token_id)

            # Permission check
            if not token.can_be_accessed_by(request.user):
                messages.error(request, "You don't have permission to disconnect this account.")
                return redirect('gmail_leads:dashboard')

            email_account = token.email_account
            token.delete()

            messages.success(request, f"Gmail Leads account {email_account} disconnected.")
        except GmailLeadsToken.DoesNotExist:
            messages.error(request, "Gmail account not found.")

    return redirect('gmail_leads:dashboard')


@login_required
def sync_account(request, token_id):
    """
    AJAX endpoint: Manually trigger sync for a Gmail Leads account
    Supports force_full parameter for full historical sync
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        from django.conf import settings

        # Get token and check permission
        token = GmailLeadsToken.objects.get(id=token_id)

        if not token.can_be_accessed_by(request.user):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Get force_full parameter from request body
        force_full = False
        try:
            body = json.loads(request.body.decode('utf-8'))
            force_full = body.get('force_full', False)
        except:
            pass

        # Create batch log before dispatching sync
        from integrations.models import SyncLog
        sync_type = 'gmail_leads_full' if force_full else 'gmail_leads_incremental'
        batch_log = SyncLog.objects.create(
            integration='gmail_leads',
            sync_type=sync_type,
            log_kind='batch',
            status='running',
            triggered_by_user=token.email_account,
        )

        task_name = create_task(
            endpoint='/integrations/gmail-leads/workers/sync-account/',
            payload={
                'token_id': token_id,
                'force_full': force_full,
                'triggered_by_user': request.user.username,
                'batch_log_id': batch_log.id,
            },
            task_name=f'gmail-leads-sync-{token_id}-{int(timezone.now().timestamp())}'
        )

        return JsonResponse({
            'status': 'started',
            'message': f'{"Full" if force_full else "Incremental"} sync started for {token.email_account}',
            'task_name': task_name,
            'sync_id': batch_log.id
        })

    except GmailLeadsToken.DoesNotExist:
        return JsonResponse({'error': 'Gmail account not found'}, status=404)
    except Exception as e:
        logger.error(f"Sync failed for token {token_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def sync_all_accounts(request):
    """
    AJAX endpoint: Sync all Gmail Leads accounts
    Admin only
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    # Permission check
    if request.user.role not in ['admin', 'director', 'digital_marketing']:
        return JsonResponse({'error': 'Admin access required'}, status=403)

    try:
        # Trigger Cloud Tasks worker
        task_name = create_task(
            endpoint='/integrations/gmail-leads/workers/sync-all-accounts/',
            payload={
                'force_full': False
            },
            task_name=f'gmail-leads-sync-all-{int(timezone.now().timestamp())}'
        )

        return JsonResponse({
            'status': 'started',
            'message': 'Sync started for all accounts',
            'task_name': task_name
        })

    except Exception as e:
        logger.error(f"Sync all accounts failed: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def sync_date_range_view(request, token_id):
    """
    AJAX endpoint: Sync emails for a specific date range
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        # Get token and check permission
        token = GmailLeadsToken.objects.get(id=token_id)

        if not token.can_be_accessed_by(request.user):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Parse dates
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')

        if not start_date_str or not end_date_str:
            return JsonResponse({'error': 'start_date and end_date required'}, status=400)

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

            # Make timezone-aware
            start_date = timezone.make_aware(start_date)
            end_date = timezone.make_aware(end_date.replace(hour=23, minute=59, second=59))

            # Validate date range
            if start_date > end_date:
                return JsonResponse({'error': 'start_date must be before end_date'}, status=400)

            if (end_date - start_date).days > 90:
                return JsonResponse({'error': 'Date range cannot exceed 90 days'}, status=400)

        except ValueError as e:
            return JsonResponse({'error': f'Invalid date format: {str(e)}'}, status=400)

        # Run date range sync synchronously (for now)
        from .gmail_leads_sync import sync_date_range

        logger.info(f"Starting date range sync for {token.email_account}: {start_date_str} to {end_date_str}")

        result = sync_date_range(token, start_date, end_date)

        if result['status'] == 'success':
            return JsonResponse({
                'status': 'completed',
                'message': f"Synced {result['total_created']} leads from {start_date_str} to {end_date_str}",
                'stats': result
            })
        elif result['status'] == 'partial_failure':
            return JsonResponse({
                'status': 'partial',
                'message': f"Partially synced {result['total_created']} leads (some lead types failed)",
                'stats': result
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result.get('error', 'Unknown error'),
                'stats': result
            }, status=500)

    except GmailLeadsToken.DoesNotExist:
        return JsonResponse({'error': 'Gmail account not found'}, status=404)
    except Exception as e:
        logger.error(f"Date range sync failed for token {token_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def update_exclusions(request, token_id):
    """
    AJAX endpoint: Update excluded emails for a Gmail Leads account
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        # Get token and check permission
        token = GmailLeadsToken.objects.get(id=token_id)

        if not token.can_be_accessed_by(request.user):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Get excluded emails from POST data
        excluded_emails = request.POST.get('excluded_emails', '').strip()

        # Update token
        token.excluded_emails = excluded_emails
        token.save(update_fields=['excluded_emails'])

        logger.info(f"Updated excluded emails for {token.email_account}: {excluded_emails}")

        return JsonResponse({
            'status': 'success',
            'message': 'Excluded emails updated successfully'
        })

    except GmailLeadsToken.DoesNotExist:
        return JsonResponse({'error': 'Gmail account not found'}, status=404)
    except Exception as e:
        logger.error(f"Failed to update exclusions for token {token_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def sync_logs(request):
    """
    View sync logs
    """
    # Batch logs (one per sync run) and operation logs
    batch_logs = SyncLog.objects.filter(integration='gmail_leads', log_kind='batch').order_by('-started_at')[:50]
    op_logs = SyncLog.objects.filter(integration='gmail_leads', log_kind='operation').order_by('-started_at')

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
        'page_title': 'Gmail Leads Sync Logs'
    }

    return render(request, 'gmail_leads/sync_logs.html', context)


@login_required
def sync_progress(request, token_id):
    """
    AJAX endpoint: Get real-time sync progress for a token
    Used by frontend to poll for progress updates
    """
    try:
        # Get token and check permission
        token = GmailLeadsToken.objects.get(id=token_id)

        if not token.can_be_accessed_by(request.user):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Get progress from cache
        progress = get_sync_progress(token_id)

        if not progress:
            return JsonResponse({
                'status': 'no_sync',
                'message': 'No active sync found'
            })

        return JsonResponse(progress)

    except GmailLeadsToken.DoesNotExist:
        return JsonResponse({'error': 'Gmail account not found'}, status=404)
    except Exception as e:
        logger.error(f"Failed to get sync progress for token {token_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def settings(request):
    """
    Gmail Leads settings page - Admin only
    Manage Gmail account connections
    """
    # Restrict to admin/director/digital_marketing only
    if request.user.role not in ['admin', 'director', 'digital_marketing']:
        messages.error(request, "You don't have permission to access settings.")
        return redirect('gmail_leads:dashboard')

    # Get all tokens (admin sees all)
    tokens = GmailLeadsToken.objects.all().order_by('-created_at')

    context = {
        'tokens': tokens,
        'page_title': 'Gmail Leads Settings'
    }

    return render(request, 'gmail_leads/settings.html', context)


# ─── Stop / Force-Stop Sync ───────────────────────────────────────────────────

@login_required
def stop_sync(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if request.user.role not in ['admin', 'director']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    sync_id = request.POST.get('sync_id')
    if not sync_id:
        return JsonResponse({'error': 'sync_id is required'}, status=400)
    try:
        sync_log = SyncLog.objects.get(id=sync_id, integration='gmail_leads', log_kind='batch')
    except SyncLog.DoesNotExist:
        return JsonResponse({'error': f'Sync {sync_id} not found'}, status=404)
    if sync_log.status != 'running':
        return JsonResponse({'error': f'Sync is not running (status: {sync_log.status})'}, status=400)
    sync_log.stop_requested = True
    sync_log.save(update_fields=['stop_requested'])
    logger.info(f"[Gmail Leads] Stop requested for sync {sync_id} by {request.user}")
    return JsonResponse({'status': 'success', 'message': 'Stop requested. Sync will finish current operation then stop.'})


@login_required
def force_stop_sync(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if request.user.role not in ['admin', 'director']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    sync_id = request.POST.get('sync_id')
    try:
        if sync_id:
            sync_log = SyncLog.objects.get(id=sync_id, integration='gmail_leads', log_kind='batch')
        else:
            # No sync_id — force-stop the most recent batch log regardless of status
            sync_log = SyncLog.objects.filter(
                integration='gmail_leads', log_kind='batch'
            ).order_by('-started_at').first()
            if not sync_log:
                return JsonResponse({'error': 'No sync log found'}, status=404)
    except SyncLog.DoesNotExist:
        return JsonResponse({'error': f'Sync {sync_id} not found'}, status=404)
    elapsed = int((timezone.now() - sync_log.started_at).total_seconds())
    sync_log.status = 'stopped'
    sync_log.stop_requested = True
    sync_log.completed_at = timezone.now()
    sync_log.duration_seconds = elapsed
    sync_log.error_message = f'Force-stopped by {request.user} after {elapsed}s'
    sync_log.save()
    logger.warning(f"[Gmail Leads] Force-stopped sync {sync_log.id} by {request.user} after {elapsed}s")
    return JsonResponse({'status': 'success', 'message': f'Sync force-stopped after {elapsed}s.'})


@login_required
def api_sync_logs(request, batch_id):
    """
    API endpoint to fetch detailed operation logs for a specific sync batch.

    Args:
        batch_id: SyncLog batch ID

    Returns:
        JSON with operation-level logs
    """
    try:
        # Get the batch log
        batch_log = SyncLog.objects.get(pk=batch_id, integration='gmail_leads', log_kind='batch')

        # Get all operation logs for this batch
        operation_logs = SyncLog.objects.filter(
            batch=batch_log,
            log_kind='operation'
        ).order_by('started_at')

        # Format logs for frontend
        logs = []
        for op_log in operation_logs:
            logs.append({
                'id': op_log.id,
                'timestamp': timezone.localtime(op_log.started_at).strftime('%H:%M:%S'),
                'level': op_log.level,
                'operation': op_log.operation,
                'message': op_log.message or '',
                'duration_ms': op_log.duration_ms
            })

        return JsonResponse({
            'logs': logs,
            'batch_status': batch_log.status,
            'batch_started': batch_log.started_at.isoformat(),
            'batch_completed': batch_log.completed_at.isoformat() if batch_log.completed_at else None
        })

    except SyncLog.DoesNotExist:
        return JsonResponse({'error': 'Sync log not found'}, status=404)
    except Exception as e:
        logger.error(f"Failed to fetch sync logs: {e}")
        return JsonResponse({'error': str(e)}, status=500)
