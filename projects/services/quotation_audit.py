"""
Quotation Audit Service
Comprehensive audit logging for quotations
"""

from projects.models_quotation import QuotationAudit
import logging

logger = logging.getLogger(__name__)


class QuotationAuditService:
    """Service for logging quotation actions."""

    @staticmethod
    def log_action(quotation, user, action, changes=None, ip_address=None, metadata=None):
        """
        Log an action on a quotation.

        Args:
            quotation: Quotation instance
            user: User who performed the action
            action: Action type (created, modified, etc.)
            changes: Dict of changes made
            ip_address: IP address of user
            metadata: Additional metadata dict

        Returns:
            QuotationAudit instance or None if failed
        """
        try:
            return QuotationAudit.objects.create(
                quotation=quotation,
                user=user,
                action=action,
                changes=changes or {},
                ip_address=ip_address,
                additional_metadata=metadata or {}
            )
        except Exception as e:
            logger.error(f"Failed to log audit action: {e}")
            return None

    @staticmethod
    def get_client_ip(request):
        """Extract client IP from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
