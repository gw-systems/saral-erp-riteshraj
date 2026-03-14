from django.db import models
from django.contrib.auth import get_user_model
from projects.models import ProjectCode
from datetime import datetime, date
from dropdown_master_data.models import AdhocBillingStatus, TransactionSide, AdhocChargeType

User = get_user_model()


class AdhocBillingEntry(models.Model):
    """Header for adhoc billing with multiple line items"""
    
    project = models.ForeignKey(
        ProjectCode,
        to_field='project_id',
        on_delete=models.CASCADE,
        related_name='adhoc_billing_entries'
    )
    
    # Event Details
    event_date = models.DateField(help_text="Date when the chargeable event occurred")
    service_month = models.DateField(
        help_text="Auto-calculated from event_date (YYYY-MM-01 - for matching with monthly billing)",
        null=True,
        blank=True
    )
    
    # Totals (calculated from line items)
    total_client_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_vendor_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Status & Remarks
    status = models.ForeignKey(
    #'dropdown_master_data.AdhocBillingStatus',
    AdhocBillingStatus,
    on_delete=models.PROTECT,
    db_column='status',
    to_field='code',
    default='pending'
    )
    billing_remarks = models.TextField(blank=True)
    
    # Audit
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='adhoc_entries_created')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-event_date', '-created_at']
        verbose_name = 'Adhoc Billing Entry'
        verbose_name_plural = 'Adhoc Billing Entries'
        indexes = [
            models.Index(fields=['project', 'event_date']),
            models.Index(fields=['service_month', 'status']),
        ]
    
    def save(self, *args, **kwargs):
        # Auto-calculate service month from event date
        if self.event_date:
            if isinstance(self.event_date, str):
                try:
                    parsed_date = datetime.strptime(self.event_date, '%Y-%m-%d').date()
                    self.service_month = parsed_date.replace(day=1)
                except ValueError:
                    pass
            elif isinstance(self.event_date, date):
                self.service_month = self.event_date.replace(day=1)
        
        super().save(*args, **kwargs)
    
    def recalculate_totals(self):
        """Recalculate totals from line items"""
        # Get TransactionSide objects
        try:
            client_side = TransactionSide.objects.get(code='client')
            vendor_side = TransactionSide.objects.get(code='vendor')
        except TransactionSide.DoesNotExist:
            # Fallback to string comparison if TransactionSide not found
            client_total = self.line_items.filter(side__code='client').aggregate(
                total=models.Sum('amount')
            )['total'] or 0
            vendor_total = self.line_items.filter(side__code='vendor').aggregate(
                total=models.Sum('amount')
            )['total'] or 0
        else:
            client_total = self.line_items.filter(side=client_side).aggregate(
                total=models.Sum('amount')
            )['total'] or 0

            vendor_total = self.line_items.filter(side=vendor_side).aggregate(
                total=models.Sum('amount')
            )['total'] or 0

        self.total_client_amount = client_total
        self.total_vendor_amount = vendor_total
        self.save()
    
    def __str__(self):
        return f"{self.project.project_code} - {self.event_date}"
    
    @property
    def client_item_count(self):
        return self.line_items.filter(side__code='client').count()

    @property
    def vendor_item_count(self):
        return self.line_items.filter(side__code='vendor').count()

    def mark_as_billed(self):
        # Get or create billed status
        billed_status, _ = AdhocBillingStatus.objects.get_or_create(code='billed')
        self.status = billed_status
        self.save()


class AdhocBillingLineItem(models.Model):
    """Individual line items for adhoc billing"""
    
    entry = models.ForeignKey(
        AdhocBillingEntry,
        on_delete=models.CASCADE,
        related_name='line_items'
    )
    
    side = models.ForeignKey(
    #'dropdown_master_data.TransactionSide',
    TransactionSide,
    on_delete=models.PROTECT,
    db_column='side',
    to_field='code'
    )
    charge_type = models.ForeignKey(
        #'dropdown_master_data.AdhocChargeType',
        AdhocChargeType, 
        on_delete=models.PROTECT,
        db_column='charge_type',
        to_field='code'
    )
    description = models.TextField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    rate = models.DecimalField(max_digits=10, decimal_places=4)
    unit = models.CharField(max_length=50, help_text="e.g., per person, per sq.ft., per box")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    class Meta:
        ordering = ['id']
        verbose_name = 'Adhoc Billing Line Item'
        verbose_name_plural = 'Adhoc Billing Line Items'
    
    def save(self, *args, **kwargs):
        # Auto-calculate amount
        self.amount = float(self.quantity) * float(self.rate)
        super().save(*args, **kwargs)
        
        # Update parent entry totals
        self.entry.recalculate_totals()
    
    def delete(self, *args, **kwargs):
        entry = self.entry
        super().delete(*args, **kwargs)
        # Update parent totals after deletion
        entry.recalculate_totals()
    
    def __str__(self):
        return f"{self.get_side_display()} - {self.get_charge_type_display()} - ₹{self.amount}"


class AdhocBillingAttachment(models.Model):
    """Supporting documents split by type"""
    
    TYPE_CHOICES = [
        ('client_approval', 'Client Approval/Mail'),
        ('vendor_bill', 'Vendor Bill/Proof'),
        ('other', 'Other'),
    ]

    entry = models.ForeignKey(AdhocBillingEntry, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='adhoc_billing/%Y/%m/')
    filename = models.CharField(max_length=255)
    attachment_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='other')
    
    uploaded_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    
    class Meta:
        ordering = ['uploaded_at']
    
    def __str__(self):
        return f"{self.get_attachment_type_display()} - {self.filename}"