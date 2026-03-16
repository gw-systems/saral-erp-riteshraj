from django.db import models


class ApolloSyncState(models.Model):
    sync_key = models.CharField(max_length=50, unique=True, default='historical')
    start_year = models.PositiveIntegerField(null=True, blank=True)
    start_month = models.PositiveSmallIntegerField(null=True, blank=True)
    end_year = models.PositiveIntegerField(null=True, blank=True)
    end_month = models.PositiveSmallIntegerField(null=True, blank=True)
    c_year = models.PositiveIntegerField(null=True, blank=True)
    c_month = models.PositiveSmallIntegerField(null=True, blank=True)
    c_camp_idx = models.PositiveIntegerField(default=0)
    c_page = models.PositiveIntegerField(default=1)
    is_complete = models.BooleanField(default=False)
    last_checkpoint_at = models.DateTimeField(null=True, blank=True)
    last_run_started_at = models.DateTimeField(null=True, blank=True)
    last_run_completed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    last_api_calls = models.PositiveIntegerField(default=0)
    total_messages_synced = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Apollo Sync State'
        verbose_name_plural = 'Apollo Sync State'

    def __str__(self):
        return (
            f"{self.sync_key}: {self.c_year}-{(self.c_month or 0) + 1:02d} "
            f"campaign={self.c_camp_idx} page={self.c_page} complete={self.is_complete}"
        )

    @classmethod
    def load(cls, sync_key='historical'):
        state, _ = cls.objects.get_or_create(sync_key=sync_key)
        return state


class ApolloCampaign(models.Model):
    apollo_id = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    created_at_remote = models.DateTimeField(null=True, blank=True, db_index=True)
    updated_at_remote = models.DateTimeField(null=True, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at_remote', '-id']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['-created_at_remote']),
        ]

    def __str__(self):
        return self.name or f"Apollo Campaign {self.apollo_id}"


class ApolloMessage(models.Model):
    apollo_id = models.CharField(max_length=64, unique=True, db_index=True)
    campaign = models.ForeignKey(
        ApolloCampaign,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='messages',
    )
    recipient_email = models.EmailField(blank=True)
    first_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)
    linkedin_url = models.URLField(blank=True, max_length=500)
    title = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=255, blank=True)
    subject = models.TextField(blank=True)
    num_opens = models.PositiveIntegerField(default=0)
    num_clicks = models.PositiveIntegerField(default=0)
    replied = models.BooleanField(default=False, db_index=True)
    status = models.CharField(max_length=100, blank=True, db_index=True)
    email_status = models.CharField(max_length=100, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_opened_at = models.DateTimeField(null=True, blank=True)
    lead_category = models.CharField(max_length=50, blank=True, db_index=True)
    raw_message = models.JSONField(default=dict, blank=True)
    raw_activity = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-sent_at', '-id']
        indexes = [
            models.Index(fields=['campaign', '-sent_at']),
            models.Index(fields=['lead_category', '-sent_at']),
            models.Index(fields=['status', '-sent_at']),
        ]

    def __str__(self):
        return self.subject or self.recipient_email or f"Apollo Message {self.apollo_id}"
