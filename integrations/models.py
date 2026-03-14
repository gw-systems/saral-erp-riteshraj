from django.db import models
from django.utils import timezone
from datetime import timedelta, datetime


class SyncLog(models.Model):
    """
    Unified audit log for ALL integration syncs and operations.

    Two log kinds:
      - 'batch'     : One row per sync run. Tracks status, progress %, module results, record counts.
      - 'operation' : One row per individual API call/operation. Linked to parent batch via batch FK.

    Replaces: gmail_leads.SyncLog, GoogleAdsSyncLog, CallyzerSyncLog, tallysync.SyncLog
    """

    INTEGRATION_CHOICES = [
        ('bigin', 'Bigin CRM'),
        ('gmail', 'Gmail Inbox'),
        ('gmail_leads', 'Gmail Leads'),
        ('google_ads', 'Google Ads'),
        ('callyzer', 'Callyzer'),
        ('tallysync', 'TallySync'),
        ('expense_log', 'Expense Log'),
    ]

    SYNC_TYPE_CHOICES = [
        ('bigin_full', 'Bigin Full Sync'),
        ('bigin_incremental', 'Bigin Incremental Sync'),
        ('bigin_module', 'Bigin Module Sync'),
        ('gmail_full', 'Gmail Full Sync'),
        ('gmail_incremental', 'Gmail Incremental Sync'),
        ('gmail_leads_full', 'Gmail Leads Full Sync'),
        ('gmail_leads_incremental', 'Gmail Leads Incremental Sync'),
        ('google_ads', 'Google Ads Sync'),
        ('google_ads_historical', 'Google Ads Historical Sync'),
        ('callyzer', 'Callyzer Sync'),
        ('tally_full', 'Tally Full Sync'),
        ('tally_incremental', 'Tally Incremental Sync'),
        ('tally_companies', 'Tally Companies Sync'),
        ('tally_ledgers', 'Tally Ledgers Sync'),
        ('tally_vouchers', 'Tally Vouchers Sync'),
        ('expense_log_full', 'Expense Log Full Sync'),
        ('expense_log_incremental', 'Expense Log Incremental Sync'),
    ]

    LOG_KIND_CHOICES = [
        ('batch', 'Batch Run'),
        ('operation', 'Operation'),
    ]

    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Completed'),
        ('stopping', 'Stopping'),
        ('stopped', 'Stopped'),
    ]

    LEVEL_CHOICES = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('SUCCESS', 'Success'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]

    # --- Core identity ---
    integration = models.CharField(max_length=50, choices=INTEGRATION_CHOICES, db_index=True, blank=True, null=True)
    sync_type = models.CharField(max_length=50, choices=SYNC_TYPE_CHOICES, db_index=True)
    log_kind = models.CharField(max_length=20, choices=LOG_KIND_CHOICES, default='batch', db_index=True)

    # Parent batch link (for operation-level rows)
    batch = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE,
        related_name='operations', db_index=True
    )

    # --- Timing ---
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)  # operation-level granularity
    last_updated = models.DateTimeField(auto_now=True)

    # --- Batch-level progress ---
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running', db_index=True)
    current_module = models.CharField(max_length=100, blank=True, null=True)
    current_module_progress = models.IntegerField(default=0)
    current_module_total = models.IntegerField(default=0)
    overall_progress_percent = models.IntegerField(default=0)
    stop_requested = models.BooleanField(default=False)
    modules = models.JSONField(default=list, blank=True)

    # --- Record counts (batch-level) ---
    total_records_synced = models.IntegerField(default=0)
    records_created = models.IntegerField(default=0)
    records_updated = models.IntegerField(default=0)
    records_failed = models.IntegerField(default=0)
    errors_count = models.IntegerField(default=0)
    module_results = models.JSONField(default=dict, blank=True)
    # Example: {"Contacts": {"synced": 2000, "created": 50, "updated": 1950, "errors": 0}}

    # --- Operation-level fields ---
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, blank=True, null=True, db_index=True)
    operation = models.CharField(max_length=200, blank=True, null=True)
    message = models.TextField(blank=True, null=True)
    details = models.JSONField(default=dict, blank=True)

    # Sub-categorization (replaces gmail lead_type, callyzer report_type, tally company name)
    sub_type = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # --- Error info ---
    error_message = models.TextField(blank=True, null=True)
    error_details = models.JSONField(default=dict, blank=True)

    # --- Trigger info ---
    triggered_by = models.CharField(max_length=100, blank=True, null=True)
    triggered_by_user = models.CharField(max_length=100, blank=True, null=True)

    # --- Job monitoring ---
    scheduled_job = models.ForeignKey(
        'ScheduledJob', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='sync_logs', db_index=True,
    )
    api_calls_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['integration', '-started_at']),
            models.Index(fields=['integration', 'log_kind', '-started_at']),
            models.Index(fields=['sync_type', '-started_at']),
            models.Index(fields=['status', '-started_at']),
            models.Index(fields=['level', '-started_at']),
            models.Index(fields=['scheduled_job', '-started_at']),
        ]
        verbose_name = "Sync Log"
        verbose_name_plural = "Sync Logs"

    def __str__(self):
        if self.log_kind == 'operation':
            return f"[{self.integration}] {self.level} {self.operation} ({self.started_at:%H:%M:%S})"
        return f"[{self.integration}] {self.get_sync_type_display()} - {self.status} ({self.started_at:%Y-%m-%d %H:%M})"

    @classmethod
    def log(cls, integration, sync_type, level, operation, message='', details=None,
            sub_type='', duration_ms=None, batch=None):
        """Create an operation-level log entry. Replaces all per-app .log() helper methods."""
        return cls.objects.create(
            integration=integration,
            sync_type=sync_type,
            log_kind='operation',
            batch=batch,
            level=level,
            operation=operation,
            message=message,
            details=details or {},
            sub_type=sub_type or '',
            duration_ms=duration_ms,
        )

    @property
    def duration_display(self):
        """Human-readable duration"""
        if self.duration_ms is not None:
            if self.duration_ms < 1000:
                return f"{self.duration_ms}ms"
            return f"{self.duration_ms / 1000:.1f}s"
        if not self.duration_seconds:
            return "N/A"
        minutes, seconds = divmod(self.duration_seconds, 60)
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    @property
    def success_rate(self):
        """Calculate success rate"""
        if self.total_records_synced == 0:
            return 100.0 if self.status == 'completed' else 0.0
        if self.errors_count == 0:
            return 100.0
        return round((self.total_records_synced - self.errors_count) / self.total_records_synced * 100, 2)


class LeadAttributionManager(models.Manager):
    """Custom manager for lead attribution matching"""

    def match_and_create(self, gmail_lead, time_window_hours=24):
        """
        Find matching Bigin contact and create attribution

        Args:
            gmail_lead: LeadEmail instance
            time_window_hours: Hours to look before/after for temporal matching

        Returns:
            LeadAttribution instance or None
        """
        from integrations.bigin.models import BiginContact
        from datetime import timedelta

        # Primary match: exact email + time proximity (both required)
        if gmail_lead.form_email and gmail_lead.datetime_received:
            time_start = gmail_lead.datetime_received - timedelta(hours=time_window_hours)
            time_end = gmail_lead.datetime_received + timedelta(hours=6)

            exact_match = BiginContact.objects.filter(
                email__iexact=gmail_lead.form_email,
                created_time__gte=time_start,
                created_time__lte=time_end
            ).order_by('created_time').first()

            if exact_match:
                return self.create_attribution(
                    gmail_lead, exact_match,
                    match_confidence='exact_email',
                    match_score=100.0
                )

        # Fallback: fuzzy email + time proximity
        if gmail_lead.form_email and gmail_lead.datetime_received:
            time_start = gmail_lead.datetime_received - timedelta(hours=time_window_hours)
            time_end = gmail_lead.datetime_received + timedelta(hours=6)

            proximity_matches = BiginContact.objects.filter(
                created_time__gte=time_start,
                created_time__lte=time_end
            )

            email_local = gmail_lead.form_email.split('@')[0]
            for contact in proximity_matches:
                if contact.email and email_local.lower() in contact.email.lower():
                    return self.create_attribution(
                        gmail_lead, contact,
                        match_confidence='fuzzy_email',
                        match_score=75.0
                    )

        return None

    def create_attribution(self, gmail_lead, bigin_contact, match_confidence, match_score):
        """
        Create attribution record with denormalized UTM data

        Args:
            gmail_lead: LeadEmail instance
            bigin_contact: BiginContact instance
            match_confidence: One of 'exact_email', 'fuzzy_email', 'temporal'
            match_score: Confidence score 0-100

        Returns:
            LeadAttribution instance
        """
        time_diff = (bigin_contact.created_time - gmail_lead.datetime_received).total_seconds() / 3600

        return self.create(
            gmail_lead=gmail_lead,
            bigin_contact=bigin_contact,
            match_confidence=match_confidence,
            match_score=match_score,
            utm_campaign=gmail_lead.utm_campaign or '',
            utm_medium=gmail_lead.utm_medium or '',
            utm_term=gmail_lead.utm_term or '',
            utm_content=gmail_lead.utm_content or '',
            gclid=gmail_lead.gclid or '',
            gmail_received_at=gmail_lead.datetime_received,
            bigin_created_at=bigin_contact.created_time,
            time_to_contact_hours=time_diff
        )

    def refresh_attributions(self, start_date=None):
        """
        Refresh attribution records for all unmatched leads.

        Args:
            start_date: Unused, kept for backwards compatibility

        Returns:
            int: Number of new matches created
        """
        from integrations.gmail_leads.models import LeadEmail

        # Fetch all already-matched lead IDs in one query
        already_matched_ids = set(self.values_list('gmail_lead_id', flat=True))

        # Process all leads not yet matched
        leads = LeadEmail.objects.exclude(id__in=already_matched_ids)

        matched_count = 0
        for lead in leads:
            attribution = self.match_and_create(lead)
            if attribution:
                matched_count += 1

        return matched_count


class LeadAttribution(models.Model):
    """
    Cross-integration model: Maps Gmail Leads → Bigin Contacts
    Denormalizes UTM data for performance in marketing analytics

    This model enables tracking the complete funnel:
    Google Ads → Gmail Leads → Bigin CRM → Conversions
    """
    # Relationships
    gmail_lead = models.ForeignKey(
        'gmail_leads.LeadEmail',
        on_delete=models.CASCADE,
        related_name='attributions'
    )
    bigin_contact = models.ForeignKey(
        'bigin.BiginContact',
        on_delete=models.CASCADE,
        related_name='attributions'
    )

    # Matching metadata
    MATCH_CONFIDENCE_CHOICES = [
        ('exact_email', 'Exact Email Match'),
        ('fuzzy_email', 'Fuzzy Email Match'),
        ('temporal', 'Temporal Proximity Match'),
    ]
    match_confidence = models.CharField(max_length=20, choices=MATCH_CONFIDENCE_CHOICES)
    match_score = models.FloatField(help_text="0-100 confidence score")
    matched_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Denormalized UTM data (for performance - avoid JOIN to gmail_leads)
    utm_campaign = models.CharField(max_length=255, blank=True, db_index=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_term = models.CharField(max_length=255, blank=True)
    utm_content = models.CharField(max_length=255, blank=True)
    gclid = models.CharField(max_length=255, blank=True, help_text="Google Click Identifier")

    # Timing analysis
    gmail_received_at = models.DateTimeField(db_index=True, help_text="When lead was received")
    bigin_created_at = models.DateTimeField(help_text="When contact was created in Bigin")
    time_to_contact_hours = models.FloatField(help_text="Hours between lead and contact creation")

    objects = LeadAttributionManager()

    class Meta:
        db_table = 'integrations_lead_attribution'
        unique_together = [['gmail_lead', 'bigin_contact']]
        indexes = [
            models.Index(fields=['bigin_contact', '-matched_at']),
            models.Index(fields=['utm_campaign', '-matched_at']),
            models.Index(fields=['match_confidence']),
            models.Index(fields=['-gmail_received_at']),
        ]
        verbose_name = "Lead Attribution"
        verbose_name_plural = "Lead Attributions"
        ordering = ['-matched_at']

    def __str__(self):
        return f"{self.gmail_lead.form_email} → {self.bigin_contact.email} ({self.match_confidence})"

    @property
    def conversion_rate_display(self):
        """Display conversion percentage"""
        if self.time_to_contact_hours < 0:
            return "Pre-existing contact"
        return f"{self.time_to_contact_hours:.1f}h"


class ScheduledJob(models.Model):
    """
    DB-driven cron job registry.
    One master Cloud Scheduler job fires every minute → /integrations/scheduled-jobs/tick/
    That endpoint reads this table and fires due jobs via Cloud Tasks.
    Admins manage schedules here instead of in GCP console.
    """

    INTEGRATION_CHOICES = [
        ('bigin', 'Bigin CRM'),
        ('gmail_leads', 'Gmail Leads'),
        ('google_ads', 'Google Ads'),
        ('callyzer', 'Callyzer'),
        ('tallysync', 'TallySync'),
        ('gmail', 'Gmail'),
        ('expense_log', 'Expense Log'),
    ]

    LAST_FIRED_RESULT_CHOICES = [
        ('ok', 'OK'),
        ('skipped', 'Skipped'),
        ('error', 'Error'),
    ]

    name = models.CharField(max_length=100)
    integration = models.CharField(max_length=50, choices=INTEGRATION_CHOICES, db_index=True)
    endpoint = models.CharField(max_length=200, help_text="Relative URL path, e.g. /integrations/bigin/workers/sync-all-modules/")
    payload = models.JSONField(default=dict, help_text="JSON payload sent to the worker endpoint")
    cron_schedule = models.CharField(max_length=100, help_text="5-field cron expression, e.g. */5 * * * *")
    is_enabled = models.BooleanField(default=True, db_index=True)
    last_fired_at = models.DateTimeField(null=True, blank=True)
    last_fired_result = models.CharField(max_length=20, choices=LAST_FIRED_RESULT_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=100, blank=True, help_text="Username of last editor")

    class Meta:
        ordering = ['integration', 'name']
        verbose_name = "Scheduled Job"
        verbose_name_plural = "Scheduled Jobs"

    def __str__(self):
        status = "enabled" if self.is_enabled else "disabled"
        return f"[{self.get_integration_display()}] {self.name} ({self.cron_schedule}) — {status}"
