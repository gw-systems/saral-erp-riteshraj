"""
Gmail OAuth2 Authentication for Lead Fetcher
Separate OAuth credentials from main gmail app
"""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow
import logging

logger = logging.getLogger(__name__)

# Gmail API scopes needed for reading emails
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
]


def create_oauth_flow(redirect_uri):
    """
    Create OAuth2 flow for Gmail Leads using settings credentials

    Args:
        redirect_uri: Callback URL for OAuth

    Returns:
        Flow object
    """
    # Create client config — DB settings take priority over environment variables
    from integrations.gmail_leads.utils.settings_helper import get_gmail_leads_config
    gmail_config = get_gmail_leads_config()
    client_config = {
        "web": {
            "client_id": gmail_config['client_id'],
            "client_secret": gmail_config['client_secret'],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri]
        }
    }

    # autogenerate_code_verifier defaults to True in google-auth-oauthlib >= 1.2.0,
    # causing "client_secret is missing" for web app OAuth clients. Disable PKCE.
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
        autogenerate_code_verifier=False,
    )
    return flow


def get_authorization_url(flow):
    """
    Get OAuth2 authorization URL

    Args:
        flow: OAuth flow object

    Returns:
        tuple: (authorization_url, state)
    """
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='false',  # Don't include previously granted scopes
        prompt='consent'  # Force consent screen to get refresh token
    )
    return authorization_url, state


def exchange_code_for_token(flow, authorization_response):
    """
    Exchange authorization code for access token

    Args:
        flow: OAuth flow object
        authorization_response: Full callback URL with code

    Returns:
        dict: Token data including access_token, refresh_token, etc.
    """
    flow.fetch_token(authorization_response=authorization_response)

    credentials = flow.credentials

    token_data = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes,
        'expiry': credentials.expiry.isoformat() if credentials.expiry else None
    }

    # Try to get email from token info
    try:
        service = build('gmail', 'v1', credentials=credentials)
        profile = service.users().getProfile(userId='me').execute()
        token_data['email'] = profile.get('emailAddress')
    except Exception as e:
        logger.warning(f"Could not fetch user email: {e}")

    return token_data


def get_gmail_service(token_data):
    """
    Create Gmail API service from token data

    Args:
        token_data: Dictionary containing OAuth2 token information

    Returns:
        Gmail API service object
    """
    try:
        credentials = Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes')
        )

        service = build('gmail', 'v1', credentials=credentials)
        return service

    except Exception as e:
        logger.error(f"Failed to create Gmail service: {e}")
        return None


def refresh_token(token_data):
    """
    Refresh an expired access token

    Args:
        token_data: Dictionary containing OAuth2 token information

    Returns:
        dict: Updated token data with new access_token
    """
    try:
        credentials = Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes')
        )

        from google.auth.transport.requests import Request
        credentials.refresh(Request())

        # Update token data
        token_data['token'] = credentials.token
        if credentials.expiry:
            token_data['expiry'] = credentials.expiry.isoformat()

        logger.info("Token refreshed successfully")
        return token_data

    except Exception as e:
        logger.error(f"Failed to refresh token: {e}")
        raise
