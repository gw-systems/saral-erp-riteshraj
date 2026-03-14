from django.db import models
from django.utils import timezone
from datetime import timedelta


class GstState(models.Model):
    """GST registration tracking by state"""
    state_code = models.CharField(max_length=2, unique=True)
    state_name = models.CharField(max_length=50)
    gst_number = models.CharField(max_length=15, blank=True, null=True)
    registration_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        managed = False
        db_table = 'gst_states'
    
    def __str__(self):
        return f"{self.state_name} ({self.state_code})"



class ProjectCode(models.Model):
    """Main project table - links clients, vendors, locations"""
    SERIES_CHOICES = [
        ('WAAS', 'Warehouse as a Service'),
        ('SAAS', 'SaaS Only Client'),
        ('GW', 'Internal Use'),
    ]
    STATUS_CHOICES = [
        ('Operation Not Started', 'Operation Not Started'),
        ('Active', 'Active'),
        ('Notice Period', 'Notice Period'),
        ('Inactive', 'Inactive'),
    ]
    
    # EXISTING FIELDS (keep these in order)
    project_id = models.CharField(max_length=20, primary_key=True)
    series_type = models.CharField(max_length=10, choices=SERIES_CHOICES)
    code = models.CharField(max_length=20, unique=True)
    project_code = models.CharField(max_length=255, unique=True, blank=True, null=True)
    client_name = models.CharField(max_length=100, blank=True, null=True)
    vendor_name = models.CharField(max_length=100, blank=True, null=True)
    warehouse_code = models.CharField(max_length=50, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=50, blank=True, null=True)
    project_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Operation Not Started')
    sales_manager = models.CharField(max_length=100, blank=True, null=True)
    operation_coordinator = models.CharField(max_length=100, blank=True, null=True)
    backup_coordinator = models.CharField(max_length=100, blank=True, null=True)
    # billing_start_date removed - now stored in ProjectCard model only
    notice_period_start_date = models.DateField(blank=True, null=True, help_text="Date when notice period started")
    notice_period_duration = models.IntegerField(blank=True, null=True, choices=[(15, '15 Days'), (30, '1 Month (30 Days)'), (60, '2 Months (60 Days)'), (90, '3 Months (90 Days)'),], help_text="Duration of notice period in days")
    notice_period_end_date = models.DateField(blank=True, null=True, help_text="Auto-calculated end date of notice period")
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # OPERATION & MIS FIELDS
    operation_mode = models.CharField(
        max_length=20,
        choices=[
            ('auto_mode', 'Auto Mode'),
            ('data_sharing', 'Data Sharing'),
            ('active_engagement', 'Active Engagement'),
        ],
        null=True,
        blank=True,
        verbose_name="Operation Mode"
    )
    
    mis_status = models.CharField(
        max_length=20,
        choices=[
            ('mis_daily', 'MIS Daily'),
            ('mis_weekly', 'MIS Weekly'),
            ('mis_monthly', 'MIS Monthly'),
            ('inciflo', 'Inciflo'),
            ('mis_automode', 'MIS Automode'),
            ('mis_not_required', 'MIS Not Required'),
        ],
        null=True,
        blank=True,
        verbose_name="MIS Status"
    )
    
    billing_unit = models.ForeignKey(
    'dropdown_master_data.BillingUnit',
    on_delete=models.PROTECT,
    db_column='billing_unit',
    to_field='code',
    default='sqft',
    db_index=True
    )
    
    minimum_billable_sqft = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum billable area in square feet (reference only)"
    )
    
    minimum_billable_pallets = models.IntegerField(
        null=True,
        blank=True,
        help_text="Minimum billable pallets (reference only)"
    )
    
    # ==================== NEW FOREIGN KEY FIELDS (USE STRING REFERENCES) ====================
    
    client_card = models.ForeignKey(
        'projects.ClientCard',  # ← STRING REFERENCE (app_label.ModelName)
        on_delete=models.PROTECT,
        related_name='projects',
        to_field='client_code',
        null=True,
        blank=True,
        help_text="Link to Client Card (master data) - auto-fills client_name",
        db_column='client_card_code',
        db_index=True
    )
    
    vendor_warehouse = models.ForeignKey(
        'supply.VendorWarehouse',  # ← CHANGED: supply app
        on_delete=models.PROTECT,
        related_name='projects',
        to_field='warehouse_code',
        null=True,
        blank=True,
        help_text="Link to Vendor Warehouse (master data) - auto-fills vendor_name, warehouse_code, location",
        db_column='vendor_warehouse_code',
        db_index=True
    )
    
    class Meta:
        managed = True
        db_table = 'project_codes'
        ordering = ['code']
        indexes = [
            models.Index(fields=['project_status']),
            models.Index(fields=['project_status', 'operation_coordinator']),
            models.Index(fields=['project_status', 'backup_coordinator']),
            models.Index(fields=['vendor_name'], name='idx_pc_vendor_name'),
            models.Index(fields=['vendor_name', 'project_status'], name='idx_pc_vendor_status'),
        ]
    
    def get_display_name(self):
        """
        Returns the exact value from project_code column in database.
        No formatting logic - uses stored value directly.
        """
        return self.project_code if self.project_code else self.code
    
    def __str__(self):
        """
        String representation used everywhere by default.
        Returns exact database project_code value.
        """
        return self.project_code if self.project_code else self.code
    
    def generate_project_code(self):
        """
        Generate project_code from code + client + vendor + location
        Uses existing business logic format
        """
        if not self.code or not self.client_name or not self.vendor_name or not self.location:
            return None
        
        return f"{self.code} - ({self.client_name} - {self.vendor_name} ({self.location}))"
    
    def save(self, *args, **kwargs):
        """
        Auto-generate project_code, validate uniqueness
        Auto-update project_status when operation_start_date is set
        Auto-fill client/vendor fields from FK relationships
        """
        is_new = self._state.adding
        
        # Auto-fill client_name from ClientCard FK
        if self.client_card and not self.client_name:
            self.client_name = self.client_card.client_legal_name
        
        # Auto-fill vendor/warehouse fields from VendorWarehouse FK
        if self.vendor_warehouse:
            if not self.vendor_name:
                self.vendor_name = self.vendor_warehouse.vendor_code.vendor_short_name
            if not self.warehouse_code:
                self.warehouse_code = self.vendor_warehouse.warehouse_code
            if not self.location:
                self.location = self.vendor_warehouse.warehouse_location_id.city
            if not self.state:
                self.state = self.vendor_warehouse.warehouse_state_name
        
        # Auto-generate project_code for new projects if missing
        if is_new and not self.project_code:
            generated = self.generate_project_code()
            if generated:
                self.project_code = generated
        
        # Validate uniqueness before DB save
        if self.project_code:
            existing = ProjectCode.objects.filter(
                project_code=self.project_code
            ).exclude(pk=self.pk).exists()
            
            if existing:
                raise ValueError(
                    f"Duplicate project_code '{self.project_code}' already exists. "
                    f"Cannot save project."
                )
        
        # Auto-update project_status when operation_start_date is set
        if hasattr(self, 'operation_start_date') and self.operation_start_date and self.project_status == 'Operation Not Started':
            self.project_status = 'Active'
        
        super().save(*args, **kwargs)


class UnusedProjectId(models.Model):
    """Track TEMP project IDs that were deleted/merged"""
    project_id = models.CharField(max_length=20, primary_key=True)
    was_intended_for = models.CharField(max_length=200)
    intended_series = models.CharField(max_length=10, help_text="WAAS/SAAS/GW")
    merged_into = models.CharField(max_length=20, null=True, blank=True)
    created_at = models.DateTimeField()
    deleted_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    deleted_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    reason = models.TextField(blank=True)
    
    class Meta:
        db_table = 'unused_project_ids'
        ordering = ['-deleted_at']
    
    def __str__(self):
        return f"{self.project_id} ({self.intended_series}) → {self.merged_into or 'Deleted'}"


class ProjectNameChangeLog(models.Model):
    """Track project name/client changes"""
    project = models.ForeignKey(ProjectCode, on_delete=models.CASCADE, related_name='name_changes')
    old_client_name = models.CharField(max_length=100)
    new_client_name = models.CharField(max_length=100)
    old_project_code = models.CharField(max_length=255)
    new_project_code = models.CharField(max_length=255)
    changed_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    changed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    reason = models.TextField(blank=True)
    
    class Meta:
        db_table = 'project_name_change_logs'
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.project.project_id}: {self.old_client_name} → {self.new_client_name}"
    

class ProjectCodeChangeLog(models.Model):
    """Track ALL changes to project_codes for audit trail"""
    project_id = models.CharField(max_length=20, db_index=True)  # Not FK because project_id can change
    field_name = models.CharField(max_length=50)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    changed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'project_code_change_logs'
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['project_id', '-changed_at']),
            models.Index(fields=['changed_by', '-changed_at']),
        ]
    
    def __str__(self):
        return f"{self.project_id} - {self.field_name} changed by {self.changed_by}"


# Import client models from local
from .models_client import ClientGroup, ClientCard, ClientContact, ClientGST, ClientDocument
from .models_system import SystemSettings
from .models_document import ProjectDocument
from .models_quotation import Quotation, QuotationLocation, QuotationItem, QuotationAudit
from .models_quotation_settings import QuotationSettings

__all__ = ['ProjectDocument', 'Quotation', 'QuotationLocation', 'QuotationItem', 'QuotationAudit', 'QuotationSettings']