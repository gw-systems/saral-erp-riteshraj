"""
Persistent sync status tracking for Gmail Leads
Tracks active syncs across page refreshes and navigation
"""

from django.core.cache import cache
from django.utils import timezone
from django.db import models
import logging

logger = logging.getLogger(__name__)


class SyncStatus(models.Model):
    """
    Database-backed sync status for persistence across server restarts
    """
    token = models.ForeignKey('GmailLeadsToken', on_delete=models.CASCADE, related_name='sync_statuses')
    sync_type = models.CharField(max_length=20, choices=[('incremental', 'Incremental'), ('full', 'Full')])
    status = models.CharField(max_length=20, choices=[
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed')
    ])
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    progress_percentage = models.IntegerField(default=0)
    current_status = models.TextField(default='Initializing...')
    stats = models.JSONField(default=dict)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        app_label = 'gmail_leads'

    def get_cache_key(self):
        """Get cache key for this sync"""
        return f'gmail_leads_sync_progress_{self.token_id}'

    def to_dict(self):
        """Convert to dict for JSON response"""
        return {
            'id': self.id,
            'status': self.status,
            'sync_type': self.sync_type,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'progress_percentage': self.progress_percentage,
            'current_status': self.current_status,
            'stats': self.stats,
            'error_message': self.error_message,
            'elapsed_seconds': int((timezone.now() - self.started_at).total_seconds()) if self.status == 'running' else int((self.completed_at - self.started_at).total_seconds()) if self.completed_at else 0
        }

    @classmethod
    def get_active_sync(cls, token_id):
        """Get currently active sync for a token"""
        # Check cache first (faster)
        cache_key = f'gmail_leads_sync_progress_{token_id}'
        cached_progress = cache.get(cache_key)
        if cached_progress:
            return cached_progress

        # Fallback to database
        sync = cls.objects.filter(token_id=token_id, status='running').first()
        if sync:
            return sync.to_dict()

        # Check for recently completed syncs (within last 5 minutes)
        recent_sync = cls.objects.filter(
            token_id=token_id,
            status__in=['completed', 'failed'],
            completed_at__gte=timezone.now() - timezone.timedelta(minutes=5)
        ).first()

        if recent_sync:
            return recent_sync.to_dict()

        return None

    @classmethod
    def get_all_active_syncs(cls):
        """Get all currently active syncs (for global status indicator)"""
        # Get from cache for all tokens
        from .models import GmailLeadsToken
        active_syncs = []

        for token in GmailLeadsToken.objects.filter(is_active=True):
            sync = cls.get_active_sync(token.id)
            if sync and sync.get('status') == 'running':
                sync['email_account'] = token.email_account
                active_syncs.append(sync)

        return active_syncs
