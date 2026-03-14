"""
Google Docs Template Service
Fetch quotation templates from Google Docs using Drive API with OAuth 2.0
"""

from googleapiclient.http import MediaIoBaseDownload
import io
import tempfile
import logging
import json

logger = logging.getLogger(__name__)


class GoogleDocsTemplateService:
    """
    Service for fetching quotation templates from Google Docs.
    Uses Google Drive API v3 with OAuth 2.0 authentication.
    """

    def __init__(self, user=None):
        """
        Initialize with user for OAuth token access.

        Args:
            user: Django User model instance (optional, for token lookup)
        """
        from projects.models_quotation_settings import QuotationSettings
        self.settings = QuotationSettings.get_settings()
        self.user = user

    def get_token_data(self):
        """
        Get OAuth token data for the user.

        Returns:
            dict: Token data

        Raises:
            FileNotFoundError: If no token found for user
            ValueError: If token data invalid
        """
        if not self.user:
            raise ValueError("User required for OAuth authentication")

        from projects.models_quotation_settings import QuotationToken

        # Get active token for user
        token = QuotationToken.objects.filter(
            user=self.user,
            is_active=True
        ).first()

        if not token:
            raise FileNotFoundError(
                "No Google OAuth token found. Please authorize access first."
            )

        # Decrypt token data
        try:
            from cryptography.fernet import Fernet
            from django.conf import settings as django_settings
            import base64

            if hasattr(django_settings, 'QUOTATION_ENCRYPTION_KEY'):
                key = django_settings.QUOTATION_ENCRYPTION_KEY.encode()
            else:
                key = base64.urlsafe_b64encode(
                    django_settings.SECRET_KEY[:32].encode().ljust(32)[:32]
                )

            fernet = Fernet(key)
            decrypted = fernet.decrypt(token.encrypted_token_data.encode()).decode()
            token_data = json.loads(decrypted)

            return token_data

        except Exception as e:
            logger.error(f"Failed to decrypt token data: {e}")
            raise ValueError(f"Invalid token data: {e}")

    def fetch_template(self):
        """
        Fetch quotation template from Google Docs as DOCX.

        Returns:
            str: Path to downloaded DOCX file

        Raises:
            ValueError: If template URL not configured
            RuntimeError: If download fails
        """
        if not self.settings.google_docs_template_id:
            raise ValueError(
                "Google Docs template not configured. "
                "Please set template URL in Quotation Settings."
            )

        try:
            # Get OAuth token
            token_data = self.get_token_data()

            # Build Drive API service
            from projects.utils.google_auth import get_drive_service
            service = get_drive_service(token_data)

            if not service:
                raise RuntimeError("Failed to create Google Drive service")

            # Export Google Doc as DOCX
            request = service.files().export_media(
                fileId=self.settings.google_docs_template_id,
                mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )

            # Download to memory
            file_handle = io.BytesIO()
            downloader = MediaIoBaseDownload(file_handle, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.info(f"Download progress: {int(status.progress() * 100)}%")

            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.docx', delete=False)
            template_path = temp_file.name

            with open(template_path, 'wb') as f:
                f.write(file_handle.getvalue())

            logger.info(f"Template downloaded successfully: {template_path}")
            return template_path

        except Exception as e:
            logger.error(f"Failed to fetch Google Docs template: {e}")
            raise RuntimeError(f"Template download failed: {e}")
