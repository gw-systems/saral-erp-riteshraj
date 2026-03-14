from django.db import models
from django.contrib.auth import get_user_model
from projects.models import ProjectCode
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from .models_projectcard import TransportRate

User = get_user_model()


# ============================================================================
# EXISTING MODELS (Keep these - they point to existing DB tables)
# ============================================================================

class OperationsDailyUpdate(models.Model):
    """Daily operational metrics for each project - EXISTING TABLE"""
    project_id = models.CharField(max_length=20)
    operation_date = models.DateField()
    space_utilization = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, help_text="Percentage (0-100)")
    inventory_value = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    outstanding_amount = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, db_column='created_by', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        managed = False
        db_table = 'operations_daily_update'
        unique_together = (('project_id', 'operation_date'),)
        ordering = ['-operation_date']
    
    def __str__(self):
        return f"{self.project_id} - {self.operation_date}"


class BillingStatement(models.Model):
    """Month-end billing with vendor costs and client revenue - EXISTING TABLE"""
    STORAGE_TYPE_CHOICES = [('Sq Ft', 'Square Feet'), ('Lumpsum', 'Lumpsum')]
    UNIT_CHOICES = [('Boxes', 'Boxes'), ('Tons', 'Tons'), ('Pieces', 'Pieces')]
    STATUS_CHOICES = [('draft', 'Draft'), ('pending_approval', 'Pending Approval'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    
    project_id = models.CharField(max_length=20)
    billing_month = models.DateField()
    
    # Vendor costs
    v_fixed_storage_sqft = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    v_additional_storage_sqft = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    v_storage_type = models.CharField(max_length=20, choices=STORAGE_TYPE_CHOICES, blank=True, null=True)
    v_storage_days = models.IntegerField(blank=True, null=True)
    v_storage_rate = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    v_storage_total = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    v_storage_remarks = models.TextField(blank=True, null=True)
    v_handling_in_qty = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    v_handling_in_unit = models.CharField(max_length=20, choices=UNIT_CHOICES, blank=True, null=True)
    v_handling_in_rate = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    v_handling_in_total = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    v_handling_in_remarks = models.TextField(blank=True, null=True)
    v_handling_out_qty = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    v_handling_out_unit = models.CharField(max_length=20, choices=UNIT_CHOICES, blank=True, null=True)
    v_handling_out_rate = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    v_handling_out_total = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    v_handling_out_remarks = models.TextField(blank=True, null=True)
    v_transport_charges = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    v_transport_remarks = models.TextField(blank=True, null=True)
    v_misc_charges = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    v_misc_remarks = models.TextField(blank=True, null=True)
    v_total_amount = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    
    # Client revenue
    c_fixed_storage_sqft = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    c_additional_storage_sqft = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    c_storage_type = models.CharField(max_length=20, choices=STORAGE_TYPE_CHOICES, blank=True, null=True)
    c_storage_days = models.IntegerField(blank=True, null=True)
    c_storage_rate = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    c_storage_total = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    c_storage_remarks = models.TextField(blank=True, null=True)
    c_handling_in_qty = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    c_handling_in_unit = models.CharField(max_length=20, choices=UNIT_CHOICES, blank=True, null=True)
    c_handling_in_rate = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    c_handling_in_total = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    c_handling_in_remarks = models.TextField(blank=True, null=True)
    c_handling_out_qty = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    c_handling_out_unit = models.CharField(max_length=20, choices=UNIT_CHOICES, blank=True, null=True)
    c_handling_out_rate = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    c_handling_out_total = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    c_handling_out_remarks = models.TextField(blank=True, null=True)
    c_transport_charges = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    c_transport_remarks = models.TextField(blank=True, null=True)
    c_misc_charges = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    c_misc_remarks = models.TextField(blank=True, null=True)
    c_total_amount = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    
    # Margin
    margin_amount = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    margin_percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    
    # Email & Links
    email_subject = models.CharField(max_length=255, blank=True, null=True)
    mis_link = models.TextField(blank=True, null=True)
    
    # Approval workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, db_column='submitted_by', related_name='billing_submitted', blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, db_column='approved_by', related_name='billing_approved', blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        managed = False
        db_table = 'billing_statements'
        unique_together = (('project_id', 'billing_month'),)
        ordering = ['-billing_month']
    
    def __str__(self):
        return f"{self.project_id} - {self.billing_month.strftime('%B %Y')}"


# ============================================================================
# NEW MODELS (For Operations Module - Updated for templates)
# ============================================================================

class DailySpaceUtilization(models.Model):
    """NEW: Daily space and inventory tracking by coordinators"""
    project = models.ForeignKey(ProjectCode, on_delete=models.CASCADE, related_name='daily_entries')
    entry_date = models.DateField()
    space_utilized = models.DecimalField(max_digits=10, decimal_places=2, help_text="Space used based on project's billing unit")
    inventory_value = models.DecimalField(max_digits=15, decimal_places=2, help_text="Total inventory value in ₹")
    gw_inventory = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        editable=False,
        null=True,
        blank=True,
        help_text="Auto-calculated: inventory_value * 1.30 (GW markup)"
    )
    remarks = models.TextField(blank=True)
    
    entered_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='daily_entries_created')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_modified_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='daily_entries_modified', null=True, blank=True)

    unit = models.ForeignKey(
    'dropdown_master_data.StorageUnit',
    on_delete=models.PROTECT,
    db_column='unit',
    to_field='code',
    default='sqft'
    )   
    
    class Meta:
        ordering = ['-entry_date', 'project']
        unique_together = ['project', 'entry_date']
        indexes = [
            models.Index(fields=['project', 'entry_date']),
            models.Index(fields=['entry_date']),
        ]
        verbose_name = 'Daily Space Utilization'
        verbose_name_plural = 'Daily Space Utilizations'
    
    def save(self, *args, **kwargs):
        """Auto-calculate GW inventory (30% OF the inventory value) before saving"""
        if self.inventory_value:
            # Convert to Decimal if it's a string
            if isinstance(self.inventory_value, str):
                self.inventory_value = Decimal(self.inventory_value)
            
            # CORRECTED LOGIC: 30% OF the value (e.g., 100 -> 30)
            self.gw_inventory = self.inventory_value * Decimal('0.30') 
        else:
            self.gw_inventory = None
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"{self.project.code} - {self.entry_date}"
    
    def get_display_unit(self):
        """Return display name for billing unit"""
        if self.project.billing_unit == 'sqft':
            return 'Sq Ft'
        elif self.project.billing_unit == 'pallet':
            return 'Pallets'
        else:
            return 'Unit'


class DailyEntryAuditLog(models.Model):
    """NEW: Audit trail for daily entry changes"""
    ACTION_CHOICES = [('CREATED', 'Created'), ('UPDATED', 'Updated')]
    
    daily_entry = models.ForeignKey(DailySpaceUtilization, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    changed_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField()
    change_reason = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Daily Entry Audit Log'
        verbose_name_plural = 'Daily Entry Audit Logs'
    
    def __str__(self):
        return f"{self.action} - {self.daily_entry} by {self.changed_by}"


class WarehouseHoliday(models.Model):
    """NEW: Holiday calendar - UPDATED for templates"""
    HOLIDAY_TYPE_CHOICES = [
        ('national', 'National Holiday'),
        ('regional', 'Regional Holiday'),
        ('warehouse_closure', 'Warehouse Closure'),
        ('project_specific', 'Project Specific'),
    ]
    
    project = models.ForeignKey(ProjectCode, on_delete=models.CASCADE, null=True, blank=True, related_name='holidays', help_text="Leave blank for warehouse-wide holidays")
    holiday_date = models.DateField()
    holiday_name = models.CharField(max_length=200, help_text="e.g., Diwali, Christmas, Maintenance Day")
    holiday_type = models.CharField(max_length=20, choices=HOLIDAY_TYPE_CHOICES, default='national')
    description = models.TextField(blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='holidays_created')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Deprecated fields (keep for backward compatibility)
    warehouse_name = models.CharField(max_length=200, blank=True, help_text="DEPRECATED: Use project instead")
    is_national = models.BooleanField(default=False, help_text="DEPRECATED: Use holiday_type instead")
    added_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='holidays_added_legacy')
    
    class Meta:
        ordering = ['-holiday_date']
        verbose_name = 'Warehouse Holiday'
        verbose_name_plural = 'Warehouse Holidays'
        indexes = [
            models.Index(fields=['holiday_date']),
            models.Index(fields=['project', 'holiday_date']),
        ]
    
    def __str__(self):
        if self.project:
            return f"{self.project.code} - {self.holiday_name} ({self.holiday_date})"
        return f"All Projects - {self.holiday_name} ({self.holiday_date})"
    
    def is_past(self):
        """Check if holiday is in the past"""
        return self.holiday_date < timezone.now().date()


class DailyMISLog(models.Model):
    """NEW: Track MIS sent status"""
    project = models.ForeignKey(ProjectCode, on_delete=models.CASCADE, related_name='mis_logs')
    log_date = models.DateField()
    mis_sent = models.BooleanField(default=False)
    sent_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='mis_logs_sent')
    sent_at = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['project', 'log_date']
        ordering = ['-log_date', 'project']
        verbose_name = 'Daily MIS Log'
        verbose_name_plural = 'Daily MIS Logs'
        indexes = [
            models.Index(fields=['project', '-log_date']),
        ]
    
    def __str__(self):
        status = "✓ Sent" if self.mis_sent else "✗ Not Sent"
        return f"{self.project.code} - {self.log_date} - {status}"
    
    def mark_sent(self, user):
        """Mark MIS as sent"""
        self.mis_sent = True
        self.sent_by = user
        self.sent_at = timezone.now()
        self.save()


class DisputeLog(models.Model):
    """NEW: Disputes tracking - UPDATED for new templates"""
    
    project = models.ForeignKey(ProjectCode, on_delete=models.CASCADE, related_name='disputes')
    category = models.ForeignKey(
    'dropdown_master_data.DisputeCategory',
    on_delete=models.PROTECT,
    db_column='category',
    to_field='code',
    default='operations',
    help_text="Type of dispute"
    )
    title = models.CharField(max_length=200, help_text="Brief summary of dispute", blank=True, default='')
    description = models.TextField(help_text="Detailed description", blank=True, default='')
    priority = models.ForeignKey(
    'dropdown_master_data.Priority',
    on_delete=models.PROTECT,
    db_column='priority',
    to_field='code'
    )
    status = models.ForeignKey(
    'dropdown_master_data.DisputeStatus',
    on_delete=models.PROTECT,
    db_column='status',
    to_field='code',
    default='open'
    )
    
    disputed_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Amount in dispute (if applicable)")
    dispute_date = models.DateField(null=True, blank=True, help_text="When the issue occurred")
    
    raised_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='disputes_raised', null=True, blank=True)
    raised_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    opened_at = models.DateTimeField(null=True, blank=True, help_text="When dispute status first became 'open'")
    
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='disputes_assigned')
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='disputes_resolved')
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Deprecated fields (keep for backward compatibility)
    dispute_id = models.AutoField(primary_key=True)
    operation_person = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='disputes_handled_legacy')
    issue_date = models.DateField(null=True, blank=True)
    dispute_type = models.CharField(max_length=30, blank=True, default='')
    severity = models.ForeignKey(
    'dropdown_master_data.Severity',
    on_delete=models.PROTECT,
    db_column='severity',
    to_field='code',
    null=True,
    blank=True
    )
    comment = models.TextField(blank=True, default='')
    resolution_date = models.DateField(null=True, blank=True)
    handled_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='disputes_resolved_legacy', null=True, blank=True)
    remark = models.TextField(blank=True, default='')
    tat_days = models.IntegerField(null=True, blank=True)


    @property
    def calculated_tat_days(self):
        if self.opened_at is None:
            return None
        
        if self.resolved_at:
            delta = self.resolved_at - self.opened_at
        else:
            delta = timezone.now() - self.opened_at
        
        return delta.days
    
    def get_tat_days(self):
        """Calculate Turnaround Time in days"""
        if self.opened_at is None:
            return None
        
        end_date = self.resolved_at if self.resolved_at else timezone.now()
        delta = end_date - self.opened_at
        
        return delta.days
    
    def is_overdue(self):
        # Handle case where opened_at is None
        if self.opened_at is None:
            return False
        
        # Only check overdue for open/in_progress disputes
        if self.status not in ['open', 'in_progress']:
            return False
        
        delta = timezone.now() - self.opened_at
        return delta.days > 7  # Overdue if more than 7 days
    
    def is_within_tat(self):
        """Check if resolved dispute was within 7-day TAT"""
        tat = self.get_tat_days()
        if tat is not None:
            return tat <= 7
        return None
    
    def get_first_response_time(self):
        """Get time to first comment in hours"""
        if hasattr(self, 'comments') and self.comments.exists():
            first_comment = self.comments.order_by('created_at').first()
            if first_comment:
                delta = first_comment.created_at - self.opened_at
                return delta.total_seconds() / 3600  # Return hours
        return None

    
    class Meta:
        ordering = ['-raised_at']
        verbose_name = 'Dispute Log'
        verbose_name_plural = 'Dispute Logs'
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['status', '-raised_at']),
            models.Index(fields=['assigned_to', 'status']),
        ]
    
    def __str__(self):
        return f"Dispute #{self.dispute_id} - {self.project.code}"

    
class InAppAlert(models.Model):
    """
    In-app notification system for coordinators and managers.
    Alerts are shown in navbar and alert dashboard.
    """
    ALERT_TYPE_CHOICES = [
        ('coordinator_reminder', 'Coordinator Reminder'),
        ('manager_notification', 'Manager Notification'),
        ('system_alert', 'System Alert'),
    ]
    
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='alerts',
        help_text="User who receives this alert"
    )
    alert_type = models.CharField(
        max_length=30, 
        choices=ALERT_TYPE_CHOICES,
        db_index=True
    )
    title = models.CharField(
        max_length=200,
        help_text="Brief alert title"
    )
    message = models.TextField(
        help_text="Detailed alert message"
    )
    severity = models.CharField(
        max_length=10, 
        choices=SEVERITY_CHOICES, 
        default='info'
    )
    is_read = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether user has read this alert"
    )
    related_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="Optional link to relevant page"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    read_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When user marked alert as read"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'In-App Alert'
        verbose_name_plural = 'In-App Alerts'
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        status = "✓ Read" if self.is_read else "● Unread"
        return f"{status} - {self.user.get_full_name()}: {self.title}"
    
    def mark_as_read(self):
        """Mark this alert as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])


class ProjectCardAlert(models.Model):
    """
    Alerts for project card issues that need attention
    """
    ALERT_TYPES = (
        ('missing_storage_rates', 'Missing Storage Rates'),
        ('missing_handling_rates', 'Missing Handling Rates'),
        ('missing_vas', 'Missing Value Added Services'),
        ('incomplete_project_card', 'Incomplete Project Card'),
        ('outdated_rates', 'Outdated Rates'),
        ('missing_infrastructure', 'Missing Infrastructure Costs'),
    )
    
    SEVERITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    )
    
    project = models.ForeignKey(
        'projects.ProjectCode',
        on_delete=models.CASCADE,
        related_name='project_card_alerts'
    )
    project_card = models.ForeignKey(
        'operations.ProjectCard',
        on_delete=models.CASCADE,
        related_name='alerts',
        null=True,
        blank=True
    )
    alert_type = models.CharField(
        max_length=50,
        choices=ALERT_TYPES
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default='medium'
    )
    message = models.TextField(
        help_text="Detailed description of the alert"
    )
    is_resolved = models.BooleanField(
        default=False
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True
    )
    resolved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_alerts'
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'is_resolved']),
            models.Index(fields=['alert_type', 'severity']),
        ]
    
    def __str__(self):
        return f"{self.project.project_code} - {self.get_alert_type_display()} ({self.severity})"
    
    def resolve(self, user):
        """Mark alert as resolved"""
        from django.utils import timezone
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.save()


class DisputeComment(models.Model):
    """Comments on disputes for discussion thread"""
    
    dispute = models.ForeignKey(
        DisputeLog,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='dispute_comments'
    )
    comment = models.TextField()
    
    # Attachments (optional)
    attachment = models.FileField(
        upload_to='dispute_attachments/%Y/%m/%d/',
        null=True,
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'dispute_comments'
        ordering = ['created_at']
    
    def __str__(self):
        return f"Comment by {self.user.get_full_name()} on {self.dispute.title}"
    
    @property
    def time_ago(self):
        """Human readable time ago"""
        from django.utils.timesince import timesince
        return timesince(self.created_at).split(',')[0]
    

    
class DisputeActivity(models.Model):
    """Track all activities/changes on disputes"""
    
    ACTIVITY_TYPES = [
        ('created', 'Created'),
        ('status_changed', 'Status Changed'),
        ('assigned', 'Assigned'),
        ('priority_changed', 'Priority Changed'),
        ('commented', 'Commented'),
        ('attachment_added', 'Attachment Added'),
        ('resolved', 'Resolved'),
    ]
    
    dispute = models.ForeignKey(
        DisputeLog,
        on_delete=models.CASCADE,
        related_name='activities'
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='dispute_activities'
    )
    activity_type = models.ForeignKey(
    'dropdown_master_data.ActivityType',
    on_delete=models.PROTECT,
    db_column='activity_type',
    to_field='code'
    )
    description = models.TextField()
    
    # Store old and new values for changes
    old_value = models.CharField(max_length=255, blank=True, null=True)
    new_value = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    class Meta:
        db_table = 'dispute_activities'
        ordering = ['-created_at']
        verbose_name_plural = 'Dispute Activities'
    
    def __str__(self):
        return f"{self.get_activity_type_display()} by {self.user.get_full_name()}"
    
    @property
    def time_ago(self):
        """Human readable time ago"""
        from django.utils.timesince import timesince
        return timesince(self.created_at).split(',')[0]
    



# ============================================================================
# ADHOC BILLING MODELS
# ============================================================================

from .models_adhoc import (
    AdhocBillingEntry,
    AdhocBillingAttachment,
)




from .models_projectcard import (
    ProjectCard,
    StorageRate,
    StorageRateSlab,
    HandlingRate,
    ValueAddedService,
    InfrastructureCost,
)

from .models_agreements import (
    AgreementRenewalTracker,
    AgreementRenewalLog,
    EscalationTracker,
    EscalationLog,
)

from .models_monthly_billing_items import (
    MonthlyBillingStorageItem,
    MonthlyBillingHandlingItem,
    MonthlyBillingTransportItem,
    MonthlyBillingVASItem,
)




class MonthlyBilling(models.Model):
    """
    Monthly billing for warehouse operations.
    Maps to existing monthly_billings table.
    """
    
    # ==================== IDENTIFIERS ====================
    project = models.ForeignKey(
    'projects.ProjectCode',
    on_delete=models.PROTECT,
    db_column='project_id',
    to_field='project_id',
    related_name='monthly_billings'
    )
    service_month = models.DateField(
        help_text='Month when services were actually provided (first day of month)',
        null=True,
        blank=True
    )
    billing_month = models.DateField(
        help_text='Month when invoice is sent to client (first day of month)',
        null=True,
        blank=True
    )
    
    # ==================== PROJECT CARD REFERENCE ====================
    project_card_missing = models.BooleanField(default=False)
    project_card_used = models.ForeignKey(
        'operations.ProjectCard',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='project_card_used_id'
    )
    
    # ==================== STORAGE ====================
    storage_min_space = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    storage_additional_space = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    storage_unit_type = models.ForeignKey(
        'dropdown_master_data.StorageUnit',
        on_delete=models.PROTECT,
        db_column='storage_unit_type',
        to_field='code',
        null=True,  # Add this
        blank=True  # Add this
    )

    storage_days = models.IntegerField(default=0)
    storage_remarks = models.TextField(blank=True, default='')
    
    # Vendor Storage
    vendor_storage_rate = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    vendor_storage_cost = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )

    # Client Storage
    client_storage_rate = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    client_storage_billing = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )


    # ==================== HANDLING IN ====================
    handling_in_quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    handling_in_unit_type = models.ForeignKey(
        'dropdown_master_data.HandlingUnit',
        on_delete=models.PROTECT,
        db_column='handling_in_unit_type',
        to_field='code',
        related_name='monthly_billings_handling_in',
        blank=True, 
        null=True    
    )
    handling_in_remarks = models.TextField(blank=True, default='')

    handling_in_channel = models.ForeignKey(
        'dropdown_master_data.SalesChannel',
        on_delete=models.PROTECT,
        db_column='handling_in_channel',
        to_field='code',
        related_name='monthly_billings_handling_in_channel',
        blank=True,
        null=True
    )
    handling_in_base_type = models.ForeignKey(
        'dropdown_master_data.HandlingBaseType',
        on_delete=models.PROTECT,
        db_column='handling_in_base_type',
        to_field='code',
        related_name='monthly_billings_handling_in_base',
        blank=True,
        null=True
    )
    
    vendor_handling_in_rate = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    vendor_handling_in_cost = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )

    client_handling_in_rate = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    client_handling_in_billing = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )

    
    # ==================== HANDLING OUT ====================
    handling_out_quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    handling_out_unit_type = models.ForeignKey(
        'dropdown_master_data.HandlingUnit',
        on_delete=models.PROTECT,
        db_column='handling_out_unit_type',
        to_field='code',
        related_name='monthly_billings_handling_out',
        blank=True, 
        null=True 
    )
    handling_out_remarks = models.TextField(blank=True, default='')

    handling_out_channel = models.ForeignKey(
        'dropdown_master_data.SalesChannel',
        on_delete=models.PROTECT,
        db_column='handling_out_channel',
        to_field='code',
        related_name='monthly_billings_handling_out_channel',
        blank=True,
        null=True
    )
    handling_out_base_type = models.ForeignKey(
        'dropdown_master_data.HandlingBaseType',
        on_delete=models.PROTECT,
        db_column='handling_out_base_type',
        to_field='code',
        related_name='monthly_billings_handling_out_base',
        blank=True,
        null=True
    )
    
    vendor_handling_out_rate = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    vendor_handling_out_cost = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )

    client_handling_out_rate = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    client_handling_out_billing = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
        
    # ==================== TRANSPORT ====================
    # Vendor Transport
    vendor_transport_vehicle_type = models.ForeignKey(
        'dropdown_master_data.VehicleType',
        on_delete=models.PROTECT,
        db_column='vendor_transport_vehicle_type',
        to_field='code',
        related_name='monthly_billings_vendor_transport',
        blank=True,
        null=True
    )
    vendor_transport_quantity = models.DecimalField(
        max_digits=12, decimal_places=4, default=0
    )
    vendor_transport_amount = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    vendor_transport_remarks = models.TextField(blank=True, default='')

    # Client Transport
    client_transport_vehicle_type = models.ForeignKey(
        'dropdown_master_data.VehicleType',
        on_delete=models.PROTECT,
        db_column='client_transport_vehicle_type',
        to_field='code',
        related_name='monthly_billings_client_transport',
        blank=True,
        null=True
    )
    client_transport_quantity = models.DecimalField(
        max_digits=12, decimal_places=4, default=0
    )
    client_transport_amount = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    client_transport_remarks = models.TextField(blank=True, default='')
    
    # ==================== MISCELLANEOUS ====================
    vendor_misc_amount = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    vendor_misc_description = models.TextField(blank=True, default='')

    client_misc_amount = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    client_misc_description = models.TextField(blank=True, default='')

    # VAS/Services
    vas_service_type = models.ForeignKey(
        'dropdown_master_data.VASServiceType',
        on_delete=models.PROTECT,
        db_column='vas_service_type',
        to_field='code',
        related_name='monthly_billings_vas',
        blank=True,
        null=True
    )
    vendor_vas_service_type = models.ForeignKey(  # ADD THIS FIELD
        'dropdown_master_data.VASServiceType',
        on_delete=models.PROTECT,
        db_column='vendor_vas_service_type',
        to_field='code',
        related_name='monthly_billings_vendor_vas',
        blank=True,
        null=True
    )
    vas_quantity = models.DecimalField(
        max_digits=12, decimal_places=4, default=0
    )
    vas_unit = models.ForeignKey(
        'dropdown_master_data.VASUnit',
        on_delete=models.PROTECT,
        db_column='vas_unit',
        to_field='code',
        related_name='monthly_billings_vas_unit',
        blank=True,
        null=True
    )
    vendor_vas_rate = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    vendor_vas_cost = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    client_vas_rate = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    client_vas_billing = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    vas_remarks = models.TextField(blank=True, default='')


    # ==================== INFRASTRUCTURE ====================
    client_infrastructure_amount = models.DecimalField(
        max_digits=15, decimal_places=4, default=0,
        help_text="Total infrastructure costs billed to client"
    )
    vendor_infrastructure_cost = models.DecimalField(
        max_digits=15, decimal_places=4, default=0,
        help_text="Total infrastructure costs from vendor"
    )
    infrastructure_remarks = models.TextField(
        blank=True, default='',
        help_text="Infrastructure cost details and breakdown"
    )


    # ==================== OVERRIDE TRACKING ====================
    # Storage Override
    storage_override_reason = models.TextField(blank=True, default='')
    storage_client_variance = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text='Difference from project card: actual - expected'
    )
    storage_vendor_variance = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text='Difference from project card: actual - expected'
    )
    
    # Handling IN Override
    handling_in_override_reason = models.TextField(blank=True, default='')
    handling_in_client_variance = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text='Difference from project card: actual - expected'
    )
    handling_in_vendor_variance = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text='Difference from project card: actual - expected'
    )
    
    # Handling OUT Override
    handling_out_override_reason = models.TextField(blank=True, default='')
    handling_out_client_variance = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text='Difference from project card: actual - expected'
    )
    handling_out_vendor_variance = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text='Difference from project card: actual - expected'
    )
    
    # ==================== TOTALS & MARGINS ====================
    vendor_total = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    client_total = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    margin_amount = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    margin_percentage = models.DecimalField(
        max_digits=6, decimal_places=4, default=0
    )
    
    # ==================== MIS FIELDS ====================
    mis_email_subject = models.CharField(max_length=500, blank=True, default='')
    mis_link = models.CharField(max_length=1000, blank=True, default='')

    # MIS Document Uploads
    mis_document = models.FileField(
        upload_to='monthly_billing/mis_documents/%Y/%m/',
        blank=True,
        null=True,
        help_text='MIS report document (PDF, Excel, etc.)'
    )
    transport_document = models.FileField(
        upload_to='monthly_billing/transport_documents/%Y/%m/',
        blank=True,
        null=True,
        help_text='Transport related documents (POD, LR, etc.)'
    )
    other_document = models.FileField(
        upload_to='monthly_billing/other_documents/%Y/%m/',
        blank=True,
        null=True,
        help_text='Any other supporting documents'
    )


    # Adhoc billing inclusion tracking
    included_adhoc_ids = models.JSONField(
        blank=True,
        default=list,
        help_text='JSON array of included adhoc billing IDs'
    )
    
    # ==================== WORKFLOW ====================
    status = models.ForeignKey(
        'dropdown_master_data.MonthlyBillingStatus',
        on_delete=models.PROTECT,
        db_column='status',
        to_field='code',
        default='draft'
    )
    
    # Submission
    submitted_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='monthly_billings_submitted'
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    
    # Controller Review
    controller_reviewed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='monthly_billings_controller_reviewed'
    )
    controller_reviewed_at = models.DateTimeField(null=True, blank=True)
    controller_remarks = models.TextField(blank=True, default='')
    controller_action = models.ForeignKey(
        'dropdown_master_data.ApprovalAction',
        on_delete=models.PROTECT,
        db_column='controller_action',
        to_field='code',
        related_name='monthly_billings_controller_actions',
        default='pending'
    )
    
    # Finance Review
    finance_reviewed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='monthly_billings_finance_reviewed'
    )
    finance_reviewed_at = models.DateTimeField(null=True, blank=True)
    finance_remarks = models.TextField(blank=True, default='')
    finance_action = models.ForeignKey(
        'dropdown_master_data.ApprovalAction',
        on_delete=models.PROTECT,
        db_column='finance_action',
        to_field='code',
        related_name='monthly_billings_finance_actions',
        default='pending'
    )
    
    # Rejection Deadline
    rejection_deadline = models.DateTimeField(null=True, blank=True)
    
    # Lock
    edit_locked_at = models.DateTimeField(null=True, blank=True)
    
    # ==================== METADATA ====================
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='monthly_billings_created'
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


    # ==================== PERMISSION METHODS ====================
    
    def is_locked(self):
        """Check if billing is locked (approved by finance)."""
        return self.edit_locked_at is not None
    
    def can_edit(self, user):
        """
        Check if user can edit this billing.
        Rules:
        - Cannot edit if locked (finance approved)
        - Creator can edit in draft or rejected states
        - Controller can edit submitted billings (pending_controller, pending_finance)
        """
        if self.is_locked():
            return False

        # Controllers can edit submitted billings
        if user.role == 'operation_controller':
            editable_statuses = ['pending_controller', 'pending_finance', 'draft', 'controller_rejected', 'finance_rejected']
            return self.status_id in editable_statuses

        # Creator can edit in draft or rejected states
        if self.created_by != user:
            return False

        # Can edit in draft or rejected states
        editable_statuses = ['draft', 'controller_rejected', 'finance_rejected']
        return self.status_id in editable_statuses
    
    def can_submit(self, user):
        """
        Check if user can submit for controller review.
        """
        if self.is_locked():
            return False
        
        # Only creator can submit
        if self.created_by != user:
            return False
        
        # Can submit from draft or rejected states
        submittable_statuses = ['draft', 'controller_rejected', 'finance_rejected']
        return self.status_id in submittable_statuses
    
    def can_controller_review(self, user):
        """
        Check if user can perform controller review.
        """
        if self.is_locked():
            return False
        
        # Only operation_controller or operation_manager
        allowed_roles = ['operation_controller', 'operation_manager', 'admin', 'super_user']
        if user.role not in allowed_roles:
            return False
        
        # Must be in pending_controller status
        return self.status_id == 'pending_controller'
    
    def can_finance_review(self, user):
        """
        Check if user can perform finance review.
        """
        if self.is_locked():
            return False
        
        # Only finance_manager
        allowed_roles = ['finance_manager', 'admin', 'super_user']
        if user.role not in allowed_roles:
            return False
        
        # Must be in pending_finance status
        return self.status_id == 'pending_finance'
    
    # ==================== WORKFLOW METHODS ====================
    
    def submit_for_review(self, user):
        """
        Submit billing for controller review.
        """
        from django.utils import timezone
        
        if not self.can_submit(user):
            raise ValueError("You cannot submit this billing")
        
        self.status_id = 'pending_controller'
        self.submitted_by = user
        self.submitted_at = timezone.now()
        self.save()
    
    def controller_approve(self, user, remarks=''):
        """
        Controller approves and sends to finance.
        """
        from django.utils import timezone
        
        if not self.can_controller_review(user):
            raise ValueError("You cannot review this billing")
        
        self.controller_reviewed_by = user
        self.controller_reviewed_at = timezone.now()
        self.controller_remarks = remarks
        self.controller_action_id = 'approved'
        self.status_id = 'pending_finance'
        self.save()
    
    def controller_reject(self, user, remarks):
        """
        Controller rejects and sends back to coordinator.
        Coordinator can edit the SAME record.
        """
        from django.utils import timezone
        from datetime import timedelta
        
        if not self.can_controller_review(user):
            raise ValueError("You cannot review this billing")
        
        if not remarks:
            raise ValueError("Rejection remarks are mandatory")
        
        self.controller_reviewed_by = user
        self.controller_reviewed_at = timezone.now()
        self.controller_remarks = remarks
        self.controller_action_id = 'rejected'
        self.status_id = 'controller_rejected'
        
        # Set rejection deadline (e.g., 48 hours)
        self.rejection_deadline = timezone.now() + timedelta(hours=48)
        
        self.save()
    
    def finance_approve(self, user, remarks=''):
        """
        Finance approves and LOCKS the billing.
        After this, no edits allowed - only Credit/Debit notes.
        """
        from django.utils import timezone
        
        if not self.can_finance_review(user):
            raise ValueError("You cannot review this billing")
        
        self.finance_reviewed_by = user
        self.finance_reviewed_at = timezone.now()
        self.finance_remarks = remarks
        self.finance_action_id = 'approved'
        self.status_id = 'approved'
        
        # LOCK THE BILLING
        self.edit_locked_at = timezone.now()
        
        self.save()
    
    def finance_reject(self, user, remarks):
        """
        Finance rejects and sends back to coordinator.
        Coordinator can edit the SAME record.
        """
        from django.utils import timezone
        from datetime import timedelta
        
        if not self.can_finance_review(user):
            raise ValueError("You cannot review this billing")
        
        if not remarks:
            raise ValueError("Rejection remarks are mandatory")
        
        self.finance_reviewed_by = user
        self.finance_reviewed_at = timezone.now()
        self.finance_remarks = remarks
        self.finance_action_id = 'rejected'
        self.status_id = 'finance_rejected'
        
        # Set rejection deadline (e.g., 48 hours)
        self.rejection_deadline = timezone.now() + timedelta(hours=48)
        
        self.save()
    
    # ==================== CALCULATION METHODS ====================

    def recalculate_totals(self):
        """
        Recalculate all totals from line items.
        Follows the SAME pattern as AdhocBillingEntry.recalculate_totals()

        This method should be called EXPLICITLY when line items change,
        NOT automatically on every save.
        """
        from django.db.models import Sum
        from decimal import Decimal

        # Storage items totals
        storage_totals = self.storage_items.aggregate(
            vendor_total=Sum('vendor_cost'),
            client_total=Sum('client_billing')
        )
        storage_vendor = storage_totals['vendor_total'] or Decimal('0')
        storage_client = storage_totals['client_total'] or Decimal('0')

        # Handling items totals
        handling_in_totals = self.handling_items.filter(direction='in').aggregate(
            vendor_total=Sum('vendor_cost'),
            client_total=Sum('client_billing')
        )
        handling_in_vendor = handling_in_totals['vendor_total'] or Decimal('0')
        handling_in_client = handling_in_totals['client_total'] or Decimal('0')

        handling_out_totals = self.handling_items.filter(direction='out').aggregate(
            vendor_total=Sum('vendor_cost'),
            client_total=Sum('client_billing')
        )
        handling_out_vendor = handling_out_totals['vendor_total'] or Decimal('0')
        handling_out_client = handling_out_totals['client_total'] or Decimal('0')

        # Transport items totals
        transport_vendor = self.transport_items.filter(side='vendor').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')

        transport_client = self.transport_items.filter(side='client').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')

        # VAS items totals
        vas_totals = self.vas_items.aggregate(
            vendor_total=Sum('vendor_cost'),
            client_total=Sum('client_billing')
        )
        vas_vendor = vas_totals['vendor_total'] or Decimal('0')
        vas_client = vas_totals['client_total'] or Decimal('0')

        # Update main billing totals
        self.vendor_storage_cost = storage_vendor
        self.client_storage_billing = storage_client

        self.vendor_handling_in_cost = handling_in_vendor
        self.client_handling_in_billing = handling_in_client

        self.vendor_handling_out_cost = handling_out_vendor
        self.client_handling_out_billing = handling_out_client

        self.vendor_transport_amount = transport_vendor
        self.client_transport_amount = transport_client

        self.vendor_vas_cost = vas_vendor
        self.client_vas_billing = vas_client

        # Calculate grand totals
        self.vendor_total = (
            storage_vendor +
            handling_in_vendor +
            handling_out_vendor +
            transport_vendor +
            self.vendor_misc_amount +
            vas_vendor +
            self.vendor_infrastructure_cost
        )

        self.client_total = (
            storage_client +
            handling_in_client +
            handling_out_client +
            transport_client +
            self.client_misc_amount +
            vas_client +
            self.client_infrastructure_amount
        )

        # Margin
        self.margin_amount = self.client_total - self.vendor_total

        # Margin Percentage
        if self.vendor_total > 0:
            self.margin_percentage = (self.margin_amount / self.vendor_total) * 100
        else:
            self.margin_percentage = 0

        # Save the updated totals
        self.save()

    def calculate_totals_from_line_items(self):
        """
        Calculate totals by SUMMING all line items from related tables.
        This method should be called EXPLICITLY when you want to recalculate,
        NOT automatically on save.
        """
        from django.db.models import Sum
        from decimal import Decimal

        # Storage items totals
        storage_totals = self.storage_items.aggregate(
            vendor_total=Sum('vendor_cost'),
            client_total=Sum('client_billing')
        )
        storage_vendor = storage_totals['vendor_total'] or Decimal('0')
        storage_client = storage_totals['client_total'] or Decimal('0')

        # Handling items totals
        handling_in_totals = self.handling_items.filter(direction='in').aggregate(
            vendor_total=Sum('vendor_cost'),
            client_total=Sum('client_billing')
        )
        handling_in_vendor = handling_in_totals['vendor_total'] or Decimal('0')
        handling_in_client = handling_in_totals['client_total'] or Decimal('0')

        handling_out_totals = self.handling_items.filter(direction='out').aggregate(
            vendor_total=Sum('vendor_cost'),
            client_total=Sum('client_billing')
        )
        handling_out_vendor = handling_out_totals['vendor_total'] or Decimal('0')
        handling_out_client = handling_out_totals['client_total'] or Decimal('0')

        # Transport items totals
        transport_vendor = self.transport_items.filter(side='vendor').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')

        transport_client = self.transport_items.filter(side='client').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')

        # VAS items totals
        vas_totals = self.vas_items.aggregate(
            vendor_total=Sum('vendor_cost'),
            client_total=Sum('client_billing')
        )
        vas_vendor = vas_totals['vendor_total'] or Decimal('0')
        vas_client = vas_totals['client_total'] or Decimal('0')

        # Update main billing totals (keeping old single-value fields for backward compatibility)
        self.vendor_storage_cost = storage_vendor
        self.client_storage_billing = storage_client

        self.vendor_handling_in_cost = handling_in_vendor
        self.client_handling_in_billing = handling_in_client

        self.vendor_handling_out_cost = handling_out_vendor
        self.client_handling_out_billing = handling_out_client

        self.vendor_transport_amount = transport_vendor
        self.client_transport_amount = transport_client

        self.vendor_vas_cost = vas_vendor
        self.client_vas_billing = vas_client

        # Calculate grand totals
        self.vendor_total = (
            storage_vendor +
            handling_in_vendor +
            handling_out_vendor +
            transport_vendor +
            self.vendor_misc_amount +
            vas_vendor +
            self.vendor_infrastructure_cost
        )

        self.client_total = (
            storage_client +
            handling_in_client +
            handling_out_client +
            transport_client +
            self.client_misc_amount +
            vas_client +
            self.client_infrastructure_amount
        )

        # Margin
        self.margin_amount = self.client_total - self.vendor_total

        # Margin Percentage
        if self.vendor_total > 0:
            self.margin_percentage = (self.margin_amount / self.vendor_total) * 100
        else:
            self.margin_percentage = 0

    def calculate_totals(self):
        """
        DEPRECATED: Old method that calculated from single fields.
        Use calculate_totals_from_line_items() instead for multi-row billing.

        This is kept for backward compatibility with old billing records
        that don't have line items.
        """
        # Client totals
        self.client_total = (
            self.client_storage_billing +
            self.client_handling_in_billing +
            self.client_handling_out_billing +
            self.client_transport_amount +
            self.client_misc_amount +
            self.client_vas_billing +
            self.client_infrastructure_amount
        )

        # Vendor totals
        self.vendor_total = (
            self.vendor_storage_cost +
            self.vendor_handling_in_cost +
            self.vendor_handling_out_cost +
            self.vendor_transport_amount +
            self.vendor_misc_amount +
            self.vendor_vas_cost +
            self.vendor_infrastructure_cost
        )


        # Margin
        self.margin_amount = self.client_total - self.vendor_total

        # Margin Percentage
        if self.vendor_total > 0:
            self.margin_percentage = (self.margin_amount / self.vendor_total) * 100
        else:
            self.margin_percentage = 0
    
    def save(self, *args, **kwargs):
        """
        Override save - DO NOT auto-calculate totals.
        Totals must be explicitly set by the view/form logic.
        """
        # REMOVED: Auto-calculation that was overwriting user input
        # self.calculate_totals()
        super().save(*args, **kwargs)

    
    class Meta:
        managed = False
        db_table = 'monthly_billings'
        ordering = ['-billing_month', '-created_at']
        unique_together = [['project', 'service_month']]
        verbose_name = 'Monthly Billing'
        verbose_name_plural = 'Monthly Billings'
    
    def __str__(self):
        billing = self.billing_month.strftime('%b %Y') if self.billing_month else 'Not Yet Billed'
        return f"{self.project.project_id} - {billing}"


# LR / Consignment Note models
from .models_lr import LorryReceipt, LRLineItem, LRAuditLog  # noqa: E402, F401

# Porter Invoice Editor models
from .models_porter_invoice import PorterInvoiceSession, PorterInvoiceFile  # noqa: E402, F401