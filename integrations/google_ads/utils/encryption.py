"""
Encryption utilities for Google Ads OAuth tokens
Uses Fernet encryption for secure token storage
"""
import logging

from cryptography.fernet import Fernet
from django.conf import settings
import base64
import json

logger = logging.getLogger(__name__)


class GoogleAdsEncryption:
    """
    Encryption utility for Google Ads OAuth tokens
    Handles JSON token encryption/decryption
    """

    @staticmethod
    def get_encryption_key():
        """Get or generate encryption key from settings"""
        if hasattr(settings, 'GMAIL_ENCRYPTION_KEY'):
            return settings.GMAIL_ENCRYPTION_KEY.encode()
        # Fallback: generate from SECRET_KEY
        key = base64.urlsafe_b64encode(settings.SECRET_KEY[:32].encode().ljust(32)[:32])
        return key

    @staticmethod
    def encrypt(token_data: dict) -> str:
        """
        Encrypt Google Ads OAuth token

        Args:
            token_data: Dictionary containing OAuth token data
                       (access_token, refresh_token, expiry, etc.)

        Returns:
            Encrypted token string
        """
        if not token_data:
            return ""

        # Convert dict to JSON string
        token_json = json.dumps(token_data)

        f = Fernet(GoogleAdsEncryption.get_encryption_key())
        encrypted = f.encrypt(token_json.encode())
        return encrypted.decode()

    @staticmethod
    def decrypt(encrypted_token: str) -> dict:
        """
        Decrypt Google Ads OAuth token

        Args:
            encrypted_token: Encrypted token string

        Returns:
            Dictionary containing OAuth token data
        """
        if not encrypted_token:
            return {}

        try:
            f = Fernet(GoogleAdsEncryption.get_encryption_key())
            decrypted = f.decrypt(encrypted_token.encode())
            return json.loads(decrypted.decode())
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return {}
