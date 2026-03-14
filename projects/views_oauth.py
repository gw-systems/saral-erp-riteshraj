"""
OAuth Views for Quotation Google Docs/Drive Integration
"""

from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
import json
import logging

logger = logging.getLogger(__name__)


@login_required
def quotation_oauth_authorize(request):
    """
    Initiate OAuth flow for Google Docs/Drive API access.
    """
    from projects.utils.google_auth import create_oauth_flow, get_authorization_url
    from projects.models_quotation_settings import QuotationSettings

    settings = QuotationSettings.get_settings()

    # Check if OAuth credentials are configured
    if not settings.client_id or not settings.client_secret:
        messages.error(
            request,
            "OAuth credentials not configured. Please configure Client ID and Client Secret in Quotation Settings first."
        )
        return redirect('projects:quotation_settings')

    try:
        # Build redirect URI
        redirect_uri = request.build_absolute_uri(reverse('projects:quotation_oauth_callback'))

        # Create OAuth flow
        flow = create_oauth_flow(redirect_uri)

        # Get authorization URL
        authorization_url, state = get_authorization_url(flow)

        # Store state in session for verification
        request.session['quotation_oauth_state'] = state

        # Redirect to Google authorization page
        return redirect(authorization_url)

    except Exception as e:
        logger.error(f"OAuth authorization error: {e}")
        messages.error(request, f"Failed to initiate OAuth: {str(e)}")
        return redirect('projects:quotation_settings')


@login_required
def quotation_oauth_callback(request):
    """
    Handle OAuth callback from Google.
    """
    from projects.utils.google_auth import create_oauth_flow, exchange_code_for_token
    from projects.models_quotation_settings import QuotationToken
    from cryptography.fernet import Fernet
    from django.conf import settings as django_settings
    import base64

    # Check for errors
    error = request.GET.get('error')
    if error:
        messages.error(request, f"OAuth authorization failed: {error}")
        return redirect('projects:quotation_settings')

    # Verify state to prevent CSRF
    state = request.GET.get('state')
    session_state = request.session.get('quotation_oauth_state')

    if not state or state != session_state:
        messages.error(request, "Invalid OAuth state. Possible CSRF attack detected.")
        return redirect('projects:quotation_settings')

    try:
        # Build redirect URI
        redirect_uri = request.build_absolute_uri(reverse('projects:quotation_oauth_callback'))

        # Create OAuth flow
        flow = create_oauth_flow(redirect_uri)
        flow.state = state  # Restore state

        # Exchange authorization code for token
        authorization_response = request.build_absolute_uri()
        token_data = exchange_code_for_token(flow, authorization_response)

        # Encrypt token data
        if hasattr(django_settings, 'QUOTATION_ENCRYPTION_KEY'):
            key = django_settings.QUOTATION_ENCRYPTION_KEY.encode()
        else:
            key = base64.urlsafe_b64encode(
                django_settings.SECRET_KEY[:32].encode().ljust(32)[:32]
            )

        fernet = Fernet(key)
        encrypted_token_data = fernet.encrypt(json.dumps(token_data).encode()).decode()

        # Get email from token data
        email = token_data.get('email')
        if not email:
            messages.error(request, "Failed to retrieve email from OAuth token")
            return redirect('projects:quotation_settings')

        # Save or update token
        token, created = QuotationToken.objects.update_or_create(
            user=request.user,
            email_account=email,
            defaults={
                'encrypted_token_data': encrypted_token_data,
                'is_active': True
            }
        )

        if created:
            messages.success(
                request,
                f"Successfully connected Google account: {email}"
            )
        else:
            messages.success(
                request,
                f"Successfully updated Google account: {email}"
            )

        # Clear session state
        if 'quotation_oauth_state' in request.session:
            del request.session['quotation_oauth_state']

        return redirect('projects:quotation_settings')

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        messages.error(request, f"Failed to complete OAuth: {str(e)}")
        return redirect('projects:quotation_settings')


@login_required
def quotation_oauth_disconnect(request, token_id):
    """
    Disconnect a Google OAuth token.
    """
    from projects.models_quotation_settings import QuotationToken

    try:
        token = QuotationToken.objects.get(id=token_id)

        # Check permission
        if not token.can_be_accessed_by(request.user):
            messages.error(request, "You don't have permission to disconnect this account")
            return redirect('projects:quotation_settings')

        email = token.email_account
        token.delete()

        messages.success(request, f"Successfully disconnected Google account: {email}")

    except QuotationToken.DoesNotExist:
        messages.error(request, "Token not found")

    return redirect('projects:quotation_settings')
