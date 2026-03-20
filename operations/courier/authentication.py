"""
Custom authentication for admin endpoints using X-Admin-Token header.
Supports signed admin session tokens issued by /api/admin/auth/login.
"""
from rest_framework import authentication
from rest_framework import exceptions
from django.conf import settings
from django.core import signing
import secrets
import logging

logger = logging.getLogger('courier')


_SESSION_TOKEN_PREFIX = "admin-session"
DEFAULT_ADMIN_SESSION_MAX_AGE = 60 * 60 * 12  # 12 hours


def get_admin_session_max_age():
    return getattr(settings, "ADMIN_SESSION_MAX_AGE_SECONDS", DEFAULT_ADMIN_SESSION_MAX_AGE)


def create_admin_session_token():
    """
    Issue a signed, time-bound admin session token.
    Token is stateless and verified via Django signing.
    """
    signer = signing.TimestampSigner(salt="courier.admin.session")
    payload = f"{_SESSION_TOKEN_PREFIX}:{secrets.token_urlsafe(24)}"
    return signer.sign(payload)


def is_valid_admin_token(token):
    """
    Validate signed admin session token.
    """
    if not token:
        return False

    signer = signing.TimestampSigner(salt="courier.admin.session")
    try:
        raw = signer.unsign(token, max_age=get_admin_session_max_age())
        if isinstance(raw, str) and raw.startswith(f"{_SESSION_TOKEN_PREFIX}:"):
            return True
    except (signing.BadSignature, signing.SignatureExpired):
        return False
    return False


class AdminTokenAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication class that validates X-Admin-Token header.
    Used for admin-only endpoints requiring password protection.
    """

    def authenticate(self, request):
        """
        Authenticate admin users via X-Admin-Token header.
        Returns None to allow DRF to fall through to permission classes.
        """
        # Check if this is an admin endpoint
        path = request.path
        if '/admin/' in path and '/admin/auth/' not in path:
            token = request.META.get('HTTP_X_ADMIN_TOKEN')

            if not token:
                logger.warning(
                    f"UNAUTHORIZED_ACCESS_ATTEMPT: Missing admin token from {request.META.get('REMOTE_ADDR')} "
                    f"to {path}"
                )
                return None

            # Verify signed session token
            if not is_valid_admin_token(token):
                logger.warning(
                    f"UNAUTHORIZED_ACCESS_ATTEMPT: Invalid admin token from {request.META.get('REMOTE_ADDR')} "
                    f"to {path}"
                )
                return None

            # Token is valid - create a pseudo-user for admin
            from django.contrib.auth.models import AnonymousUser
            class AdminUser(AnonymousUser):
                @property
                def is_authenticated(self):
                    return True

                @property
                def is_admin(self):
                    return True

            return (AdminUser(), token)

        # Non-admin endpoints don't require authentication here
        return None

    def authenticate_header(self, request):
        return 'X-Admin-Token'


def verify_admin_token(request):
    """
    Helper function to verify admin token from request headers.
    Raises PermissionDenied if token is invalid or missing.

    DEPRECATED: Use AdminTokenAuthentication class instead.
    Kept for backward compatibility.
    """
    token = request.META.get('HTTP_X_ADMIN_TOKEN')

    if not token:
        logger.warning(
            f"UNAUTHORIZED_ACCESS_ATTEMPT: Missing admin token from {request.META.get('REMOTE_ADDR')}"
        )
        raise exceptions.PermissionDenied("Missing Admin Token")

    if not is_valid_admin_token(token):
        logger.warning(
            f"UNAUTHORIZED_ACCESS_ATTEMPT: Invalid admin token from {request.META.get('REMOTE_ADDR')}"
        )
        raise exceptions.PermissionDenied("Invalid Admin Token")

    return True
