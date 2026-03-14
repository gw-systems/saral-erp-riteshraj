"""
Google Ads OAuth2 Authentication Utilities
Handles OAuth2 flow for Google Ads API access
"""

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from datetime import datetime, timedelta


class GoogleAdsAuth:
    """
    Handles OAuth2 authentication for Google Ads API
    """

    # OAuth2 scopes required for Google Ads API
    SCOPES = ['https://www.googleapis.com/auth/adwords']

    @staticmethod
    def get_client_config():
        """
        Get OAuth2 client configuration.
        DB settings take priority over environment variables.

        Returns:
            dict: Client configuration
        """
        from integrations.google_ads.utils.settings_helper import get_google_ads_config
        config = get_google_ads_config()
        return {
            "web": {
                "client_id": config['client_id'],
                "client_secret": config['client_secret'],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [config['redirect_uri']]
            }
        }

    @staticmethod
    def create_flow(redirect_uri):
        """
        Create OAuth2 flow

        Args:
            redirect_uri: Redirect URI for OAuth callback

        Returns:
            Flow: OAuth2 flow object
        """
        client_config = GoogleAdsAuth.get_client_config()

        flow = Flow.from_client_config(
            client_config,
            scopes=GoogleAdsAuth.SCOPES,
            redirect_uri=redirect_uri,
            # Disable PKCE (autogenerate_code_verifier defaults to True in
            # google-auth-oauthlib >= 1.2.0, which causes "client_secret is
            # missing" errors for web app OAuth clients)
            autogenerate_code_verifier=False,
        )

        return flow

    @staticmethod
    def get_authorization_url(redirect_uri):
        """
        Get authorization URL for OAuth2 flow

        Args:
            redirect_uri: Redirect URI for OAuth callback

        Returns:
            tuple: (authorization_url, state)
        """
        flow = GoogleAdsAuth.create_flow(redirect_uri)

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )

        return authorization_url, state

    @staticmethod
    def exchange_code_for_token(code, redirect_uri):
        """
        Exchange authorization code for access token

        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Redirect URI used in authorization

        Returns:
            dict: Token data containing access_token, refresh_token, etc.
        """
        flow = GoogleAdsAuth.create_flow(redirect_uri)
        flow.fetch_token(code=code)

        credentials = flow.credentials

        # Convert credentials to dict
        token_data = {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes,
            'expiry': credentials.expiry.isoformat() if credentials.expiry else None
        }

        return token_data

    @staticmethod
    def refresh_token(token_data):
        """
        Refresh access token using refresh token

        Args:
            token_data: Token data dict containing refresh_token

        Returns:
            dict: Updated token data with new access_token
        """
        # Parse expiry if it's a string
        expiry = token_data.get('expiry')
        if isinstance(expiry, str):
            expiry = datetime.fromisoformat(expiry)

        # client_id/client_secret: use token_data first, then fall back to DB/env settings
        client_id = token_data.get('client_id')
        client_secret = token_data.get('client_secret')
        if not client_id or not client_secret:
            config = GoogleAdsAuth.get_client_config()
            web = config.get('web', {})
            client_id = client_id or web.get('client_id', '')
            client_secret = client_secret or web.get('client_secret', '')

        credentials = Credentials(
            token=token_data.get('access_token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri') or 'https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=token_data.get('scopes'),
            expiry=expiry
        )

        # Refresh the token
        credentials.refresh(Request())

        # Update token data
        token_data.update({
            'access_token': credentials.token,
            'expiry': credentials.expiry.isoformat() if credentials.expiry else None
        })

        return token_data

    @staticmethod
    def is_token_expired(token_data):
        """
        Check if access token is expired

        Args:
            token_data: Token data dict

        Returns:
            bool: True if expired, False otherwise
        """
        expiry = token_data.get('expiry')
        if not expiry:
            return True

        if isinstance(expiry, str):
            expiry = datetime.fromisoformat(expiry)

        # Consider token expired 5 minutes before actual expiry
        return expiry <= datetime.utcnow() + timedelta(minutes=5)

    @staticmethod
    def get_valid_token(token_data):
        """
        Get valid access token, refreshing if necessary

        Args:
            token_data: Token data dict

        Returns:
            dict: Updated token data with valid access_token
        """
        if GoogleAdsAuth.is_token_expired(token_data):
            token_data = GoogleAdsAuth.refresh_token(token_data)

        return token_data
