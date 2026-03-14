from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class User(AbstractUser):
    """
    Extended User model with roles and additional fields
    """
    
    ROLE_CHOICES = [
        # Tier 1: Admin Access
        ('admin', 'Admin'),
        ('super_user', 'Super User'),

        # Tier 2: Executive View
        ('director', 'Director'),

        # Tier 3: Management
        ('finance_manager', 'Finance Manager'),
        ('operation_controller', 'Operation Controller'),
        ('operation_manager', 'Operation Manager'),
        ('sales_manager', 'Sales Manager'),
        ('supply_manager', 'Supply Manager'),

        # Tier 4: Execution
        ('operation_coordinator', 'Operation Coordinator'),
        ('warehouse_manager', 'Warehouse Manager'),
        ('backoffice', 'Backoffice'),
        ('crm_executive', 'CRM Executive'),
        ('digital_marketing', 'Digital Marketing'),

        # Tier 5: External
        ('client', 'Client'),
        ('vendor', 'Vendor'),
    ]
    
    # Basic Fields
    role = models.CharField(
        max_length=50,
        choices=ROLE_CHOICES,
        default='operation_coordinator'
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
        ordering = ['first_name', 'last_name']
    
    def __str__(self):
        if self.last_name:
            return f"{self.first_name} {self.last_name} ({self.get_role_display()})"
        return f"{self.first_name} ({self.get_role_display()})"
    
    def get_full_name(self):
        """Return full name"""
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name
    
    @property
    def is_admin_or_superuser(self):
        """Check if user is admin or super_user"""
        return self.role in ['admin', 'super_user']
    
    @property
    def is_management(self):
        """Check if user is in management tier"""
        return self.role in [
            'finance_manager',
            'operation_controller',
            'operation_manager',
            'sales_manager',
            'supply_manager'
        ]
    
    @property
    def is_operations_team(self):
        """Check if user is part of operations team"""
        return self.role in [
            'operation_controller',
            'operation_manager',
            'operation_coordinator',
            'warehouse_manager'
        ]
    
    @property
    def can_delete(self):
        """Only admin can delete records"""
        return self.role == 'admin'
    
    @property
    def can_see_margins(self):
        """Roles that can see profit margins"""
        return self.role in [
            'admin',
            'super_user',
            'director',
            'finance_manager',
            'operation_controller',
            'sales_manager'  # Only for assigned projects
        ]
    
    @property
    def can_approve_billing(self):
        """Roles that can approve billings"""
        return self.role in [
            'admin',
            'finance_manager',
            'operat'
            'ion_controller'
        ]
    
class Notification(models.Model):
    """Enterprise-grade in-app notification system"""

    # Notification Types
    NOTIFICATION_TYPES = [
        # Operations
        ('dispute_raised', 'Dispute Raised'),
        ('dispute_assigned', 'Dispute Assigned'),
        ('dispute_resolved', 'Dispute Resolved'),
        ('query_raised', 'Billing Query Raised'),
        ('query_assigned', 'Query Assigned'),
        ('query_resolved', 'Query Resolved'),
        ('billing_corrected', 'Monthly Billing Corrected'),
        ('data_entry_missing', 'Data Entry Missing'),
        # Reminders
        ('coordinator_reminder', 'Coordinator Reminder'),
        ('manager_notification', 'Manager Notification'),
        # General
        ('daily_summary', 'Daily Summary'),
        ('assignment', 'New Assignment'),
        ('mention', 'Mentioned in Comment'),
        ('system_alert', 'System Alert'),
        ('system', 'System Notification'),
    ]

    # Priority Levels
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    # Severity Levels
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]

    # Categories for grouping
    CATEGORY_CHOICES = [
        ('operations', 'Operations'),
        ('billing', 'Billing'),
        ('finance', 'Finance'),
        ('projects', 'Projects'),
        ('system', 'System'),
        ('reminder', 'Reminder'),
        ('alert', 'Alert'),
    ]

    # Core fields
    recipient = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='notifications',
        db_index=True
    )
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES,
        db_index=True
    )
    title = models.CharField(max_length=255)
    message = models.TextField()

    # Classification
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='normal',
        db_index=True
    )
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default='info'
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='system',
        db_index=True
    )

    # Related objects (optional)
    dispute = models.ForeignKey(
        'operations.DisputeLog',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    project = models.ForeignKey(
        'projects.ProjectCode',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    monthly_billing = models.ForeignKey(
        'operations.MonthlyBilling',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )

    # Action and metadata
    action_url = models.CharField(max_length=500, blank=True, null=True)
    action_label = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Label for action button (e.g., 'View Billing', 'Resolve Dispute')"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata for notification (JSON)"
    )

    # Status tracking
    is_read = models.BooleanField(default=False, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    is_pinned = models.BooleanField(default=False, db_index=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    # Grouping (for related notifications)
    group_key = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Key to group related notifications together"
    )

    class Meta:
        db_table = 'notifications'
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
            models.Index(fields=['recipient', 'is_deleted', 'is_archived']),
            models.Index(fields=['recipient', 'category', '-created_at']),
            models.Index(fields=['recipient', 'priority', '-created_at']),
            models.Index(fields=['group_key', '-created_at']),
        ]
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        status = "📌 Pinned" if self.is_pinned else ("✓ Read" if self.is_read else "● Unread")
        return f"{status} - {self.recipient.get_full_name()}: {self.title}"

    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def mark_as_unread(self):
        """Mark notification as unread"""
        if self.is_read:
            self.is_read = False
            self.read_at = None
            self.save(update_fields=['is_read', 'read_at'])

    def soft_delete(self):
        """Soft delete notification"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def archive(self):
        """Archive notification"""
        self.is_archived = True
        self.archived_at = timezone.now()
        self.save(update_fields=['is_archived', 'archived_at'])

    def pin(self):
        """Pin notification to top"""
        self.is_pinned = True
        self.save(update_fields=['is_pinned'])

    def unpin(self):
        """Unpin notification"""
        self.is_pinned = False
        self.save(update_fields=['is_pinned'])

    @property
    def icon(self):
        """Get icon based on severity and type"""
        severity_icons = {
            'critical': '🚨',
            'error': '❌',
            'warning': '⚠️',
            'success': '✅',
            'info': 'ℹ️',
        }
        return severity_icons.get(self.severity, 'ℹ️')

    @property
    def color_class(self):
        """Get Tailwind color class based on severity"""
        severity_colors = {
            'critical': 'red',
            'error': 'red',
            'warning': 'yellow',
            'success': 'green',
            'info': 'blue',
        }
        return severity_colors.get(self.severity, 'gray')

    @classmethod
    def create_notification(cls, recipient, title, message, notification_type='system',
                           priority='normal', severity='info', category='system',
                           action_url=None, action_label=None, metadata=None,
                           dispute=None, project=None, monthly_billing=None, group_key=None):
        """Unified method to create notifications"""
        return cls.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            severity=severity,
            category=category,
            action_url=action_url,
            action_label=action_label,
            metadata=metadata or {},
            dispute=dispute,
            project=project,
            monthly_billing=monthly_billing,
            group_key=group_key
        )

class PasswordHistory(models.Model):
    """Track password changes for audit purposes"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_history')
    password_hash = models.CharField(max_length=255)  # Store the hashed password
    changed_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='password_changes_made')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True, null=True)  # "Self change", "Admin reset", etc.
    
    class Meta:
        db_table = 'password_history'
        ordering = ['-changed_at']
        verbose_name = 'Password History'
        verbose_name_plural = 'Password Histories'
    
    def __str__(self):
        return f"{self.user.username} - {self.changed_at.strftime('%Y-%m-%d %H:%M')}"


class ErrorLog(models.Model):
    """Store application errors for admin review"""

    SEVERITY_ERROR = 'error'
    SEVERITY_WARNING = 'warning'
    SEVERITY_INFO = 'info'
    SEVERITY_CHOICES = [
        ('error', 'Error'),
        ('warning', 'Warning'),
        ('info', 'Info'),
    ]

    SOURCE_UNHANDLED = 'unhandled'   # middleware-caught 500
    SOURCE_CAUGHT = 'caught'         # manually logged via log_caught_exception
    SOURCE_CHOICES = [
        ('unhandled', 'Unhandled (500)'),
        ('caught', 'Caught (view-handled)'),
    ]

    error_id = models.CharField(max_length=50, unique=True, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # Exception details
    exception_type = models.CharField(max_length=255)
    exception_message = models.TextField()
    traceback = models.TextField()

    # Severity & source
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='error', db_index=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='unhandled', db_index=True)

    # Request context
    request_path = models.CharField(max_length=500)
    request_method = models.CharField(max_length=10)
    request_user = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='errors'
    )

    # Environment context
    environment = models.CharField(max_length=20)  # staging/production
    revision = models.CharField(max_length=50, blank=True)

    # Additional data
    request_data = models.JSONField(default=dict, blank=True)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_errors'
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'error_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['resolved', '-timestamp']),
            models.Index(fields=['severity', '-timestamp']),
            models.Index(fields=['source', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.exception_type} at {self.request_path} ({self.timestamp})"

    def save(self, *args, **kwargs):
        if not self.error_id:
            import uuid
            self.error_id = str(uuid.uuid4())[:8]
        super().save(*args, **kwargs)


class ImpersonationLog(models.Model):
    """Track when admins impersonate users for audit purposes"""
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='impersonations_made')
    impersonated_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='impersonations_received')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    reason = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = 'impersonation_logs'
        ordering = ['-started_at']
        verbose_name = 'Impersonation Log'
        verbose_name_plural = 'Impersonation Logs'

    def __str__(self):
        return f"{self.admin.username} → {self.impersonated_user.username} at {self.started_at}"