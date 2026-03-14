"""
Lorry Receipt (LR) / Consignment Note Models
"""

from django.db import models
from django.contrib.auth import get_user_model
from projects.models import ProjectCode

User = get_user_model()


class LorryReceipt(models.Model):
    """Lorry Receipt / Consignment Note"""

    GST_PAID_BY_CHOICES = [
        ('consignee', 'Consignee'),
        ('consignor', 'Consignor'),
        ('transporter', 'Transporter'),
    ]

    # ==================== HEADER ====================
    lr_number = models.CharField(
        max_length=10,
        unique=True,
        editable=False,
        help_text="Auto-generated GW-NNNN"
    )
    lr_date = models.DateField(help_text="Date shown on the LR")
    project = models.ForeignKey(
        ProjectCode,
        on_delete=models.PROTECT,
        db_column='project_id',
        to_field='project_id',
        related_name='lorry_receipts',
        help_text="For record-keeping only; NOT printed on LR"
    )
    from_location = models.CharField(max_length=200)
    to_location = models.CharField(max_length=200)
    vehicle_no = models.CharField(max_length=50, blank=True, default='')
    vehicle_type = models.CharField(max_length=100, blank=True, default='')
    delivery_office_address = models.TextField(
        blank=True,
        default='',
        help_text="Address of Delivery Office"
    )

    # ==================== CONSIGNMENT PARTIES ====================
    consignor_name = models.CharField(max_length=200, blank=True, default='')
    consignor_address = models.TextField(blank=True, default='')
    consignee_name = models.CharField(max_length=200, blank=True, default='')
    consignee_address = models.TextField(blank=True, default='')
    consignor_gst_no = models.CharField(max_length=50, blank=True, default='')
    consignee_gst_no = models.CharField(max_length=50, blank=True, default='')

    # ==================== SHIPMENT DETAILS ====================
    invoice_no = models.CharField(max_length=100, blank=True, default='')
    gst_paid_by = models.CharField(
        max_length=15,
        choices=GST_PAID_BY_CHOICES,
        default='consignee'
    )
    mode_of_packing = models.CharField(max_length=200, blank=True, default='')
    value = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Declared value of goods"
    )
    remarks = models.TextField(blank=True, default='')

    # ==================== INSURANCE ====================
    insurance_company = models.CharField(max_length=200, blank=True, default='')
    insurance_policy_no = models.CharField(max_length=100, blank=True, default='')
    insurance_date = models.CharField(max_length=50, blank=True, default='')
    insurance_amount = models.CharField(max_length=50, blank=True, default='')
    insurance_risk = models.CharField(max_length=200, blank=True, default='')

    # ==================== AUDIT FIELDS ====================
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='lr_created'
    )
    last_modified_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='lr_modified',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-lr_date', '-created_at']
        verbose_name = 'Lorry Receipt'
        verbose_name_plural = 'Lorry Receipts'
        indexes = [
            models.Index(fields=['project', '-lr_date']),
            models.Index(fields=['-lr_date']),
            models.Index(fields=['lr_number']),
        ]

    def __str__(self):
        return f"{self.lr_number} - {self.from_location} to {self.to_location}"

    def save(self, *args, **kwargs):
        if not self.lr_number:
            self.lr_number = LorryReceipt.get_next_lr_number()
        super().save(*args, **kwargs)

    @staticmethod
    def get_next_lr_number():
        """Generate next GW-NNNN number."""
        last = (
            LorryReceipt.objects
            .filter(lr_number__startswith='GW-')
            .order_by('-lr_number')
            .values_list('lr_number', flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                seq = 1
        else:
            seq = 1
        return f"GW-{seq:04d}"


class LRLineItem(models.Model):
    """Items table rows on the LR"""
    lr = models.ForeignKey(
        LorryReceipt,
        on_delete=models.CASCADE,
        related_name='line_items'
    )
    packages = models.CharField(max_length=100, blank=True, default='')
    description = models.CharField(max_length=500, blank=True, default='')
    actual_weight = models.CharField(max_length=50, blank=True, default='')
    charged_weight = models.CharField(max_length=50, blank=True, default='')
    amount = models.CharField(max_length=50, blank=True, default='')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        verbose_name = 'LR Line Item'
        verbose_name_plural = 'LR Line Items'

    def __str__(self):
        return f"{self.lr.lr_number} item {self.order}: {self.description[:50]}"


class LRAuditLog(models.Model):
    """Audit trail for LR changes"""
    ACTION_CHOICES = [
        ('CREATED', 'Created'),
        ('UPDATED', 'Updated'),
        ('DELETED', 'Deleted'),
    ]

    lr = models.ForeignKey(
        LorryReceipt,
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    changed_at = models.DateTimeField(auto_now_add=True)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField()
    change_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'LR Audit Log'
        verbose_name_plural = 'LR Audit Logs'

    def __str__(self):
        return f"{self.action} {self.lr.lr_number} by {self.changed_by}"
