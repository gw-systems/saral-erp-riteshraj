"""
Gmail OAuth2 authentication utilities
Uses database settings instead of credentials.json
"""

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from gmail.utils.settings_helper import get_gmail_config
import logging

logger = logging.getLogger(__name__)


def get_gmail_service(token_data):
    """
    Get authenticated Gmail API service from token data

    Args:
        token_data: Dict containing OAuth2 token information

    Returns:
        Authenticated Gmail API service object
    """
    try:
        config = get_gmail_config()

        credentials = Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=config['token_uri'],
            client_id=token_data.get('client_id') or config['client_id'],
            client_secret=token_data.get('client_secret') or config['client_secret'],
            scopes=token_data.get('scopes', config['scopes'])
        )

        service = build('gmail', 'v1', credentials=credentials)
        return service

    except Exception as e:
        logger.error(f"Failed to create Gmail service: {e}")
        return None


def create_oauth_flow(redirect_uri):
    """
    Create OAuth2 flow for Gmail authentication using database settings

    Args:
        redirect_uri: Redirect URI after OAuth consent

    Returns:
        Flow object for OAuth2 authentication
    """
    try:
        config = get_gmail_config()

        # Validate configuration
        if not config['client_id'] or not config['client_secret']:
            raise ValueError(
                "Gmail OAuth not configured. "
                "Please configure Client ID and Client Secret in Gmail Settings."
            )

        # Create flow from client config (instead of credentials.json)
        client_config = {
            "web": {
                "client_id": config['client_id'],
                "client_secret": config['client_secret'],
                "auth_uri": config['auth_uri'],
                "token_uri": config['token_uri'],
                "redirect_uris": [redirect_uri]
            }
        }

        # Disable PKCE for web app OAuth clients
        flow = Flow.from_client_config(
            client_config,
            scopes=config['scopes'],
            redirect_uri=redirect_uri,
            autogenerate_code_verifier=False,
        )

        return flow

    except Exception as e:
        logger.error(f"Failed to create OAuth flow: {e}")
        raise


def get_authorization_url(flow, state=None):
    """
    Get OAuth2 authorization URL

    Args:
        flow: OAuth2 Flow object
        state: Optional state parameter for security

    Returns:
        Tuple of (authorization_url, state)
    """
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # Force consent screen to get refresh token
    )

    return authorization_url, state


def exchange_code_for_token(flow, authorization_response):
    """
    Exchange authorization code for access token

    Args:
        flow: OAuth2 Flow object
        authorization_response: Full callback URL with code

    Returns:
        Dict containing token data
    """
    try:
        flow.fetch_token(authorization_response=authorization_response)

        credentials = flow.credentials

        # Get user email — try id_token first, then fall back to Gmail API profile
        email = None

        # Method 1: extract from id_token
        if credentials.id_token:
            try:
                import google.oauth2.id_token
                import google.auth.transport.requests
                request = google.auth.transport.requests.Request()
                id_info = google.oauth2.id_token.verify_oauth2_token(
                    credentials.id_token,
                    request,
                    credentials.client_id
                )
                email = id_info.get('email')
            except Exception as e:
                logger.warning(f"id_token email extraction failed: {e}")

        # Method 2: fallback — call Gmail userinfo API directly
        if not email:
            try:
                service = build('gmail', 'v1', credentials=credentials)
                profile = service.users().getProfile(userId='me').execute()
                email = profile.get('emailAddress')
            except Exception as e:
                logger.warning(f"Gmail profile fetch failed: {e}")

        token_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes,
            'email': email  # User's email address
        }

        return token_data

    except Exception as e:
        logger.error(f"Failed to exchange code for token: {e}")
        raise
