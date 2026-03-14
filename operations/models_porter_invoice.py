"""
Porter Invoice Editor Models
Audit trail for batch and single invoice edit sessions.
"""

from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class PorterInvoiceSession(models.Model):
    """Tracks each batch or single-edit session."""

    SESSION_TYPE_CHOICES = [
        ('batch', 'Batch Processing'),
        ('single', 'Single Edit'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    session_type = models.CharField(max_length=10, choices=SESSION_TYPE_CHOICES)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')

    # Batch parameters
    multiplier = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True,
        help_text="Escalation multiplier (e.g. 1.20 = +20%)"
    )
    excel_mapping_file = models.FileField(
        upload_to='porter_invoices/excel_mappings/%Y/%m/',
        null=True, blank=True,
        help_text="Optional Excel file with CRN-to-target-total mapping"
    )

    # Results summary
    total_files = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)

    # ZIP download (for batch)
    result_zip = models.FileField(
        upload_to='porter_invoices/results/%Y/%m/',
        null=True, blank=True
    )

    # Audit fields
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='porter_invoice_sessions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Porter Invoice Session'
        verbose_name_plural = 'Porter Invoice Sessions'
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['session_type', 'status']),
        ]

    def __str__(self):
        return f"{self.get_session_type_display()} - {self.created_at:%d %b %Y %H:%M}"


class PorterInvoiceFile(models.Model):
    """Individual file within a session."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('skipped', 'Skipped'),
        ('error', 'Error'),
    ]

    session = models.ForeignKey(
        PorterInvoiceSession, on_delete=models.CASCADE, related_name='files'
    )
    original_filename = models.CharField(max_length=255)
    crn = models.CharField(max_length=50, blank=True, default='',
                           help_text="Extracted CRN/Order number")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, default='')

    # Financial data (batch mode)
    old_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    new_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Single-edit fields (JSON for flexibility)
    edit_fields = models.JSONField(
        null=True, blank=True,
        help_text="Fields edited in single-edit mode"
    )

    # File storage
    original_pdf = models.FileField(upload_to='porter_invoices/originals/%Y/%m/')
    edited_pdf = models.FileField(
        upload_to='porter_invoices/edited/%Y/%m/',
        null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['original_filename']
        verbose_name = 'Porter Invoice File'
        verbose_name_plural = 'Porter Invoice Files'
        indexes = [
            models.Index(fields=['session', 'status']),
            models.Index(fields=['crn']),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.get_status_display()})"
