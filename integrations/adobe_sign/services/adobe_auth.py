"""
Adobe Sign Authentication Service
Handles Integration Key authentication.

Credential priority:
  1. AdobeSignSettings DB record (director configures via frontend)
  2. Environment variables (fallback)
"""

from django.conf import settings
from integrations.adobe_sign.exceptions import AdobeAuthError


def _get_db_settings():
    """
    Safely fetch the AdobeSignSettings singleton from DB.
    Returns None if table doesn't exist yet (e.g. pre-migration).
    """
    try:
        from integrations.adobe_sign.models import AdobeSignSettings
        return AdobeSignSettings.objects.filter(pk=1).first()
    except Exception:
        return None


class AdobeAuthService:
    """
    Service for Adobe Sign authentication headers.
    Reads credentials from DB first, falls back to env vars.
    """

    @staticmethod
    def get_integration_key():
        """
        Returns the integration key — DB takes priority over env.
        """
        db = _get_db_settings()
        if db and db.integration_key:
            return db.get_decrypted_integration_key()
        return getattr(settings, 'ADOBE_SIGN_INTEGRATION_KEY', None) or None

    @staticmethod
    def get_headers(obo_email=None):
        """
        Returns authorization headers for Adobe Sign API calls.

        Args:
            obo_email: Optional email for On-Behalf-Of header

        Returns:
            Dict of headers

        Raises:
            AdobeAuthError: If integration key is not configured
        """
        integration_key = AdobeAuthService.get_integration_key()
        if not integration_key:
            raise AdobeAuthError(
                "Adobe Sign Integration Key is not configured. "
                "Go to E-Signature Settings and enter your Integration Key."
            )

        headers = {
            "Authorization": f"Bearer {integration_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        if obo_email:
            headers["x-api-user"] = f"email:{obo_email}"

        return headers

    @staticmethod
    def get_upload_headers(obo_email=None):
        """
        Headers for multipart file upload.
        Content-Type omitted so requests sets the multipart boundary.
        """
        headers = AdobeAuthService.get_headers(obo_email=obo_email).copy()
        headers.pop("Content-Type", None)
        return headers

    @staticmethod
    def get_director_email():
        """
        Returns director email — DB takes priority over env.
        """
        db = _get_db_settings()
        if db and db.director_email:
            return db.director_email
        return getattr(settings, 'ADOBE_SIGN_DIRECTOR_EMAIL', None) or None

    @staticmethod
    def validate_configuration():
        """
        Validate that required credentials are configured.

        Returns:
            tuple: (is_valid, error_message or None)
        """
        errors = []

        if not AdobeAuthService.get_integration_key():
            errors.append(
                'Adobe Sign Integration Key is not set — '
                'configure it in E-Signature Settings'
            )

        if not AdobeAuthService.get_director_email():
            errors.append('Director email is not set')

        if errors:
            return False, '; '.join(errors)

        return True, None
