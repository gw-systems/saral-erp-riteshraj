import logging
import requests
from django.utils import timezone
from datetime import timedelta
from .models import BiginAuthToken

logger = logging.getLogger(__name__)


def get_valid_token():
    """
    Get a valid access token string.
    Refreshes if expired.
    Returns: str (access token)
    """
    token = BiginAuthToken.objects.first()
    if not token:
        raise Exception("❌ No token found in database. Run OAuth flow first.")

    if token.is_expired():
        logger.info("Bigin token expired — refreshing...")
        token = refresh_token()

    return token.get_decrypted_access_token()  # Use encrypted storage


def refresh_token():
    """
    Use refresh_token to get new access_token.
    DB settings take priority over environment variables.
    Returns: BiginAuthToken object (updated)
    """
    from integrations.bigin.utils.settings_helper import get_bigin_config
    token = BiginAuthToken.objects.first()
    if not token:
        raise Exception("No stored refresh token found")

    bigin_config = get_bigin_config()

    data = {
        "refresh_token": token.get_decrypted_refresh_token(),
        "client_id": bigin_config['client_id'],
        "client_secret": bigin_config['client_secret'],
        "redirect_uri": bigin_config['redirect_uri'],
        "grant_type": "refresh_token"
    }

    url = bigin_config['token_url']
    logger.info("Refreshing Bigin token...")

    res = requests.post(url, data=data)
    res.raise_for_status()
    response = res.json()

    if "access_token" not in response:
        raise Exception(f"Token refresh failed: {response}")

    # Store new access token encrypted
    token.set_tokens(
        access_token=response["access_token"],
        refresh_token=token.get_decrypted_refresh_token()  # Keep existing refresh token
    )
    token.expires_at = timezone.now() + timedelta(seconds=response.get("expires_in", 3600))
    token.save()

    logger.info(f"Bigin token refreshed! Expires at {token.expires_at}")
    return token