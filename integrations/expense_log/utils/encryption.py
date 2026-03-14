"""
Encryption utilities for Google Sheets OAuth tokens and credentials.
Uses Fernet symmetric encryption with Django SECRET_KEY.
"""
from cryptography.fernet import Fernet
from django.conf import settings
import hashlib
import base64
import logging

logger = logging.getLogger(__name__)


class ExpenseLogEncryption:
    """Handles encryption/decryption of sensitive OAuth data"""

    @staticmethod
    def _get_cipher():
        """Generate Fernet cipher from Django SECRET_KEY"""
        # Hash SECRET_KEY to get 32-byte key
        key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        # Encode as base64 for Fernet
        key = base64.urlsafe_b64encode(key)
        return Fernet(key)

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        """
        Encrypt plaintext string.

        Args:
            plaintext: String to encrypt (e.g., OAuth token JSON, client secret)

        Returns:
            Base64-encoded encrypted string
        """
        if not plaintext:
            return ''

        try:
            cipher = cls._get_cipher()
            encrypted_bytes = cipher.encrypt(plaintext.encode('utf-8'))
            return encrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    @classmethod
    def decrypt(cls, encrypted_text: str) -> str:
        """
        Decrypt encrypted string.

        Args:
            encrypted_text: Base64-encoded encrypted string

        Returns:
            Decrypted plaintext string
        """
        if not encrypted_text:
            return ''

        try:
            cipher = cls._get_cipher()
            decrypted_bytes = cipher.decrypt(encrypted_text.encode('utf-8'))
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise
