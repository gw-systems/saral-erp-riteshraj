"""
Encryption utilities for Callyzer API keys
Uses Fernet encryption for secure API key storage
"""
import logging

from cryptography.fernet import Fernet
from django.conf import settings
import base64

logger = logging.getLogger(__name__)


class CallyzerEncryption:
    """
    Encryption utility for Callyzer API keys
    Handles plain string encryption/decryption
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
    def encrypt(api_key: str) -> str:
        """
        Encrypt Callyzer API key

        Args:
            api_key: Plain text API key

        Returns:
            Encrypted API key string
        """
        if not api_key:
            return ""

        f = Fernet(CallyzerEncryption.get_encryption_key())
        encrypted = f.encrypt(api_key.encode())
        return encrypted.decode()

    @staticmethod
    def decrypt(encrypted_api_key: str) -> str:
        """
        Decrypt Callyzer API key

        Args:
            encrypted_api_key: Encrypted API key

        Returns:
            Decrypted plain text API key
        """
        if not encrypted_api_key:
            return ""

        try:
            f = Fernet(CallyzerEncryption.get_encryption_key())
            decrypted = f.decrypt(encrypted_api_key.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return ""
