"""
Google Sheets OAuth2 authentication flow.
Handles authorization URL generation and token exchange.
"""
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import json
import logging

from .settings_helper import ExpenseLogSettingsHelper
from .encryption import ExpenseLogEncryption

logger = logging.getLogger(__name__)

# Google Sheets API scopes
SCOPES = [
    'openid',  # Required for userinfo
    'https://www.googleapis.com/auth/userinfo.email',         # Get user email
    'https://www.googleapis.com/auth/spreadsheets.readonly',  # Read sheets
]


class SheetsOAuthManager:
    """Manages Google Sheets OAuth2 flow"""

    def __init__(self):
        self.config = ExpenseLogSettingsHelper.get_oauth_config()

    def get_authorization_url(self, state=None):
        """
        Generate OAuth2 authorization URL.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            tuple: (authorization_url: str, state: str)
        """
        is_valid, missing = ExpenseLogSettingsHelper.validate_oauth_config(self.config)
        if not is_valid:
            raise ValueError(f"OAuth config incomplete. Missing: {', '.join(missing)}")

        client_config = {
            "web": {
                "client_id": self.config['client_id'],
                "client_secret": self.config['client_secret'],
                "redirect_uris": [self.config['redirect_uri']],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        flow = Flow.from_client_config(
            client_config=client_config,
            scopes=SCOPES,
            redirect_uri=self.config['redirect_uri']
        )

        if state:
            flow.state = state

        authorization_url, state = flow.authorization_url(
            access_type='offline',  # Request refresh token
            include_granted_scopes='true',
            prompt='consent'  # Force consent screen to get refresh token
        )

        return authorization_url, state

    def exchange_code_for_token(self, authorization_response, state=None):
        """
        Exchange authorization code for access/refresh tokens.

        Args:
            authorization_response: Full callback URL with code
            state: State parameter for verification

        Returns:
            dict: {
                'token': str (JSON with access_token, refresh_token, etc.),
                'email': str (user's Google email)
            }
        """
        is_valid, missing = ExpenseLogSettingsHelper.validate_oauth_config(self.config)
        if not is_valid:
            raise ValueError(f"OAuth config incomplete. Missing: {', '.join(missing)}")

        client_config = {
            "web": {
                "client_id": self.config['client_id'],
                "client_secret": self.config['client_secret'],
                "redirect_uris": [self.config['redirect_uri']],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        flow = Flow.from_client_config(
            client_config=client_config,
            scopes=SCOPES,
            redirect_uri=self.config['redirect_uri']
        )

        if state:
            flow.state = state

        # Exchange code for token
        flow.fetch_token(authorization_response=authorization_response)

        credentials = flow.credentials

        # Get user email from credentials
        email = self._get_user_email(credentials)

        # Prepare token data as JSON
        token_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes,
        }

        return {
            'token': json.dumps(token_data),
            'email': email
        }

    def _get_user_email(self, credentials):
        """
        Fetch user email from Google using OAuth token.

        Args:
            credentials: google.oauth2.credentials.Credentials object

        Returns:
            str: User's email address
        """
        try:
            from googleapiclient.discovery import build
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            return user_info.get('email', '')
        except Exception as e:
            logger.error(f"Failed to get user email: {e}")
            return ''

    @staticmethod
    def refresh_token_if_needed(token_json):
        """
        Refresh access token if expired.

        Args:
            token_json: JSON string with token data

        Returns:
            str: Updated token JSON (may be unchanged if not expired)
        """
        try:
            token_data = json.loads(token_json)
            credentials = Credentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri=token_data.get('token_uri'),
                client_id=token_data.get('client_id'),
                client_secret=token_data.get('client_secret'),
                scopes=token_data.get('scopes')
            )

            # Refresh if expired
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())

                # Update token data
                token_data['token'] = credentials.token
                return json.dumps(token_data)

            return token_json

        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise

    @staticmethod
    def get_credentials_from_token(token_json):
        """
        Convert stored token JSON to google.oauth2.credentials.Credentials.

        Args:
            token_json: JSON string with token data

        Returns:
            google.oauth2.credentials.Credentials
        """
        token_data = json.loads(token_json)
        return Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes')
        )
