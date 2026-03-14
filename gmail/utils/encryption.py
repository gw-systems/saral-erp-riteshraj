"""
Token encryption utilities
Securely encrypts/decrypts OAuth2 tokens
"""
import logging

from cryptography.fernet import Fernet
from django.conf import settings
import base64
import json

logger = logging.getLogger(__name__)


class EncryptionUtils:
    """Utility class for encrypting and decrypting sensitive data"""

    @staticmethod
    def get_encryption_key():
        """Get or generate encryption key from settings"""
        if hasattr(settings, 'GMAIL_ENCRYPTION_KEY'):
            return settings.GMAIL_ENCRYPTION_KEY.encode()
        # Fallback: generate from SECRET_KEY (not ideal for production)
        key = base64.urlsafe_b64encode(settings.SECRET_KEY[:32].encode().ljust(32)[:32])
        return key

    @staticmethod
    def encrypt(data):
        """Encrypt data (dict or string)"""
        if isinstance(data, dict):
            data = json.dumps(data)

        f = Fernet(EncryptionUtils.get_encryption_key())
        encrypted = f.encrypt(data.encode())
        return encrypted.decode()

    @staticmethod
    def decrypt(encrypted_data):
        """Decrypt data and return as dict"""
        if not encrypted_data:
            return None

        try:
            f = Fernet(EncryptionUtils.get_encryption_key())
            decrypted = f.decrypt(encrypted_data.encode())
            return json.loads(decrypted.decode())
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return None
