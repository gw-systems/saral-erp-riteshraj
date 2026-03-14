"""
Callyzer Integration Models
Stores call tracking data synced from Callyzer API
"""

from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


class CallyzerToken(models.Model):
    """
    Stores Callyzer API tokens for authentication
    Supports multiple accounts for different teams/departments
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='callyzer_tokens',
        help_text="User who connected this Callyzer account"
    )
    account_name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Descriptive name for this Callyzer account"
    )
    encrypted_api_key = models.TextField(
        help_text="Encrypted Callyzer API key"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this token is active and should be synced"
    )
    last_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful sync timestamp"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'callyzer_tokens'
        verbose_name = 'Callyzer Token'
        verbose_name_plural = 'Callyzer Tokens'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.account_name} ({'Active' if self.is_active else 'Inactive'})"

    def can_be_accessed_by(self, user):
        """Check if user has permission to access this token"""
        if user.role in ['admin', 'director']:
            return True
        return self.user == user


class CallSummary(models.Model):
    """Overall Summary Report - Aggregated call statistics"""

    token = models.ForeignKey(
        CallyzerToken,
        on_delete=models.CASCADE,
        related_name='call_summaries'
    )

    # Raw API response for audit trail
    raw_data = models.JSONField(
        default=dict,
        help_text="Complete API response"
    )

    # Extracted metrics
    total_calls = models.IntegerField(default=0)
    answered_calls = models.IntegerField(default=0)
    missed_calls = models.IntegerField(default=0)
    total_duration_seconds = models.IntegerField(default=0)
    avg_duration_seconds = models.FloatField(default=0.0)

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'callyzer_call_summaries'
        verbose_name = 'Call Summary'
        verbose_name_plural = 'Call Summaries'
        ordering = ['-synced_at']

    def __str__(self):
        return f"Summary for {self.token.account_name} - {self.total_calls} calls"


class EmployeeSummary(models.Model):
    """Employee Summary Report - Per-employee call metrics"""

    token = models.ForeignKey(
        CallyzerToken,
        on_delete=models.CASCADE,
        related_name='employee_summaries'
    )

    # Employee info
    emp_name = models.CharField(max_length=255, db_index=True)
    emp_id = models.CharField(max_length=100, blank=True)

    # Call metrics
    total_calls = models.IntegerField(default=0)
    answered_calls = models.IntegerField(default=0)
    missed_calls = models.IntegerField(default=0)
    outbound_calls = models.IntegerField(default=0)
    inbound_calls = models.IntegerField(default=0)
    total_duration_seconds = models.IntegerField(default=0)
    avg_duration_seconds = models.FloatField(default=0.0)

    # Raw data
    raw_data = models.JSONField(default=dict)

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'callyzer_employee_summaries'
        verbose_name = 'Employee Summary'
        verbose_name_plural = 'Employee Summaries'
        ordering = ['emp_name']
        indexes = [
            models.Index(fields=['token', 'emp_name']),
            models.Index(fields=['token', '-synced_at']),
        ]

    def __str__(self):
        return f"{self.emp_name} - {self.total_calls} calls"


class CallAnalysis(models.Model):
    """Analysis Report - Detailed call type breakdown"""

    token = models.ForeignKey(
        CallyzerToken,
        on_delete=models.CASCADE,
        related_name='call_analyses'
    )

    # Call type breakdown
    answered_calls = models.IntegerField(default=0)
    missed_calls = models.IntegerField(default=0)
    rejected_calls = models.IntegerField(default=0)
    busy_calls = models.IntegerField(default=0)
    never_attended = models.IntegerField(default=0)
    not_picked_up_by_client = models.IntegerField(default=0)

    # Duration metrics
    total_talk_time_seconds = models.IntegerField(default=0)
    avg_talk_time_seconds = models.FloatField(default=0.0)

    # Raw data
    raw_data = models.JSONField(default=dict)

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'callyzer_call_analyses'
        verbose_name = 'Call Analysis'
        verbose_name_plural = 'Call Analyses'
        ordering = ['-synced_at']

    def __str__(self):
        return f"Analysis for {self.token.account_name}"


class NeverAttendedCall(models.Model):
    """Never Attended Calls Report - Calls that were never answered"""

    token = models.ForeignKey(
        CallyzerToken,
        on_delete=models.CASCADE,
        related_name='never_attended_calls'
    )

    # Employee info
    emp_name = models.CharField(max_length=255, db_index=True)
    emp_id = models.CharField(max_length=100, blank=True)

    # Client info
    client_name = models.CharField(max_length=255, blank=True)
    client_number = models.CharField(max_length=50, db_index=True)

    # Call info (from parsed call_logs)
    call_type = models.CharField(max_length=50, blank=True)
    call_direction = models.CharField(max_length=50, blank=True)
    call_status = models.CharField(max_length=50, blank=True)
    call_date = models.DateField(db_index=True)
    call_time = models.TimeField()
    call_duration_seconds = models.IntegerField(default=0)

    # Raw data
    raw_data = models.JSONField(default=dict)

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'callyzer_never_attended_calls'
        verbose_name = 'Never Attended Call'
        verbose_name_plural = 'Never Attended Calls'
        ordering = ['-call_date', '-call_time']
        indexes = [
            models.Index(fields=['token', '-call_date']),
            models.Index(fields=['emp_name', '-call_date']),
            models.Index(fields=['client_number', '-call_date']),
        ]

    def __str__(self):
        return f"{self.emp_name} - {self.client_number} on {self.call_date}"


class NotPickedUpCall(models.Model):
    """Not Picked Up By Client Report - Calls where client didn't answer"""

    token = models.ForeignKey(
        CallyzerToken,
        on_delete=models.CASCADE,
        related_name='not_picked_up_calls'
    )

    # Employee info
    emp_name = models.CharField(max_length=255, db_index=True)
    emp_id = models.CharField(max_length=100, blank=True)

    # Client info
    client_name = models.CharField(max_length=255, blank=True)
    client_number = models.CharField(max_length=50, db_index=True)

    # Call info (from parsed call_logs)
    call_type = models.CharField(max_length=50, blank=True)
    call_direction = models.CharField(max_length=50, blank=True)
    call_status = models.CharField(max_length=50, blank=True)
    call_date = models.DateField(db_index=True)
    call_time = models.TimeField()
    call_duration_seconds = models.IntegerField(default=0)

    # Raw data
    raw_data = models.JSONField(default=dict)

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'callyzer_not_picked_up_calls'
        verbose_name = 'Not Picked Up Call'
        verbose_name_plural = 'Not Picked Up Calls'
        ordering = ['-call_date', '-call_time']
        indexes = [
            models.Index(fields=['token', '-call_date']),
            models.Index(fields=['emp_name', '-call_date']),
            models.Index(fields=['client_number', '-call_date']),
        ]

    def __str__(self):
        return f"{self.emp_name} - {self.client_number} on {self.call_date}"


class UniqueClient(models.Model):
    """Unique Clients Report - List of unique client contacts"""

    token = models.ForeignKey(
        CallyzerToken,
        on_delete=models.CASCADE,
        related_name='unique_clients'
    )

    client_name = models.CharField(max_length=255, blank=True)
    client_number = models.CharField(max_length=50, db_index=True)

    # Aggregated metrics
    total_calls = models.IntegerField(default=0)
    answered_calls = models.IntegerField(default=0)
    missed_calls = models.IntegerField(default=0)
    outbound_calls = models.IntegerField(default=0)
    inbound_calls = models.IntegerField(default=0)
    first_call_date = models.DateField(null=True, blank=True)
    last_call_date = models.DateField(null=True, blank=True)

    # Raw data
    raw_data = models.JSONField(default=dict)

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'callyzer_unique_clients'
        verbose_name = 'Unique Client'
        verbose_name_plural = 'Unique Clients'
        ordering = ['-total_calls']
        unique_together = [['token', 'client_number']]
        indexes = [
            models.Index(fields=['token', 'client_number']),
            models.Index(fields=['token', '-total_calls']),
        ]

    def __str__(self):
        return f"{self.client_name or self.client_number} - {self.total_calls} calls"


class HourlyAnalytic(models.Model):
    """Hourly Analytics Report - Hour-by-hour call patterns"""

    token = models.ForeignKey(
        CallyzerToken,
        on_delete=models.CASCADE,
        related_name='hourly_analytics'
    )

    hour = models.IntegerField(db_index=True, help_text="Hour of day (0-23)")

    # Call metrics
    total_calls = models.IntegerField(default=0)
    answered_calls = models.IntegerField(default=0)
    missed_calls = models.IntegerField(default=0)
    total_duration_seconds = models.IntegerField(default=0)
    avg_duration_seconds = models.FloatField(default=0.0)

    # Raw data
    raw_data = models.JSONField(default=dict)

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'callyzer_hourly_analytics'
        verbose_name = 'Hourly Analytic'
        verbose_name_plural = 'Hourly Analytics'
        ordering = ['hour']
        unique_together = [['token', 'hour']]

    def __str__(self):
        return f"Hour {self.hour}:00 - {self.total_calls} calls"


class DailyAnalytic(models.Model):
    """Daily Analytics Report - Day-wise call analytics"""

    token = models.ForeignKey(
        CallyzerToken,
        on_delete=models.CASCADE,
        related_name='daily_analytics'
    )

    date = models.DateField(db_index=True)

    # Call metrics
    total_calls = models.IntegerField(default=0)
    answered_calls = models.IntegerField(default=0)
    missed_calls = models.IntegerField(default=0)
    total_duration_seconds = models.IntegerField(default=0)
    avg_duration_seconds = models.FloatField(default=0.0)

    # Raw data
    raw_data = models.JSONField(default=dict)

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'callyzer_daily_analytics'
        verbose_name = 'Daily Analytic'
        verbose_name_plural = 'Daily Analytics'
        ordering = ['-date']
        unique_together = [['token', 'date']]
        indexes = [
            models.Index(fields=['token', '-date']),
        ]

    def __str__(self):
        return f"{self.date} - {self.total_calls} calls"


class CallHistory(models.Model):
    """Call History Report - Complete call log"""

    CALL_TYPE_CHOICES = [
        ('incoming', 'Incoming'),
        ('outgoing', 'Outgoing'),
        ('missed', 'Missed'),
    ]

    CALL_DIRECTION_CHOICES = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ]

    token = models.ForeignKey(
        CallyzerToken,
        on_delete=models.CASCADE,
        related_name='call_histories'
    )

    # Employee info
    emp_name = models.CharField(max_length=255, db_index=True)
    emp_id = models.CharField(max_length=100, blank=True)
    emp_number = models.CharField(max_length=50, blank=True)

    # Client info
    client_name = models.CharField(max_length=255, blank=True)
    client_number = models.CharField(max_length=50, db_index=True)

    # Call info
    call_type = models.CharField(max_length=50, choices=CALL_TYPE_CHOICES, blank=True, db_index=True)
    call_direction = models.CharField(max_length=50, choices=CALL_DIRECTION_CHOICES, blank=True, db_index=True)
    call_date = models.DateField(db_index=True)
    call_time = models.TimeField()
    duration_seconds = models.IntegerField(default=0)

    # Additional metadata
    call_status = models.CharField(max_length=50, blank=True)
    recording_url = models.URLField(blank=True, null=True)

    # Raw data
    raw_data = models.JSONField(default=dict)

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'callyzer_call_histories'
        verbose_name = 'Call History'
        verbose_name_plural = 'Call Histories'
        ordering = ['-call_date', '-call_time']
        indexes = [
            models.Index(fields=['token', '-call_date']),
            models.Index(fields=['emp_name', '-call_date']),
            models.Index(fields=['client_number', '-call_date']),
            models.Index(fields=['call_type', '-call_date']),
        ]

    def __str__(self):
        return f"{self.emp_name} - {self.client_number} on {self.call_date} {self.call_time}"


