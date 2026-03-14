from django.db import models
from django.conf import settings


class ActivityLog(models.Model):
    # Choices
    SOURCE_CHOICES = [
        ('web', 'Web'),
        ('api', 'API'),
        ('cron', 'Cron'),
        ('management_command', 'Management Command'),
        ('signal', 'Signal'),
    ]
    CATEGORY_CHOICES = [
        ('auth', 'Auth'),
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('view', 'View'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('export', 'Export'),
        ('email', 'Email'),
        ('system', 'System'),
        ('permission_denied', 'Permission Denied'),
        ('file_upload', 'File Upload'),
        ('search', 'Search'),
        ('bulk_action', 'Bulk Action'),
    ]

    # Who
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='activity_logs'
    )
    user_display_name = models.CharField(max_length=150)
    role_snapshot = models.CharField(max_length=50)

    # Source
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='web')

    # What
    action_category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    action_type = models.CharField(max_length=100)
    module = models.CharField(max_length=50)

    # Target object
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=50, blank=True, default='')
    object_repr = models.CharField(max_length=255, blank=True)

    # Related object (e.g. project the object belongs to)
    related_object_type = models.CharField(max_length=100, blank=True)
    related_object_id = models.CharField(max_length=50, blank=True, default='')

    # Human description
    description = models.TextField()

    # Request context (nullable for cron/signal sources)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    session_key = models.CharField(max_length=40, blank=True)
    request_method = models.CharField(max_length=10, blank=True)
    url_path = models.CharField(max_length=500, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    response_time_ms = models.IntegerField(null=True, blank=True)

    # Flexible payload (old/new values, file names, etc.)
    extra_data = models.JSONField(default=dict, blank=True)

    # Flags
    is_suspicious = models.BooleanField(default=False)
    is_backfilled = models.BooleanField(default=False)
    backfill_source = models.CharField(max_length=100, blank=True)
    anonymized = models.BooleanField(default=False)

    # Time
    timestamp = models.DateTimeField(db_index=True)
    date = models.DateField(db_index=True)

    class Meta:
        db_table = 'activity_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'date'], name='al_user_date_idx'),
            models.Index(fields=['date', 'action_category'], name='al_date_cat_idx'),
            models.Index(fields=['user', 'timestamp'], name='al_user_ts_idx'),
            models.Index(fields=['module', 'date'], name='al_module_date_idx'),
            models.Index(fields=['is_suspicious', 'date'], name='al_suspicious_idx'),
        ]

    def __str__(self):
        return f'{self.user_display_name} — {self.action_type} @ {self.timestamp}'
