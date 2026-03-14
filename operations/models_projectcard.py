from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from dropdown_master_data.models import (
    StorageUnit,
    SalesChannel,  # Not Channel
    HandlingBaseType,
    #Condition,
    VASServiceType,  # Not VASType
    OperationalCostType,
)


class ProjectCard(models.Model):
    """
    Project Card: Comprehensive rate card for a project with versioning support.
    Each project can have multiple versions over time.
    """
    
    # Version Control
    project = models.ForeignKey(
        'projects.ProjectCode',
        on_delete=models.CASCADE,
        related_name='project_cards',
        help_text="The project this card belongs to"
    )
    
    version = models.PositiveIntegerField(
        default=1,
        help_text="Version number (1, 2, 3, ...)"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Only one version can be active at a time"
    )
    
    superseded_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supersedes',
        help_text="The newer version that replaced this one"
    )
    
    # Validity Period
    valid_from = models.DateField(
        help_text="Date from which this card becomes effective"
    )
    
    valid_to = models.DateField(
        null=True,
        blank=True,
        help_text="Date until which this card is valid (NULL = ongoing)"
    )
    
    # Agreement Details
    agreement_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Agreement start date"
    )
    
    agreement_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Agreement end date"
    )
    
    yearly_escalation_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when yearly escalation should be applied"
    )
    
    # Operational Dates
    billing_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when billing should start"
    )
    
    operation_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when operations started"
    )
    
    # Escalation Terms
    ESCALATION_CHOICES = [
        ('no_escalation', 'No Escalation'),
        ('mutually_agreed', 'Mutually Agreed'),
        ('fixed_percentage', 'Fixed Percentage'),
    ]
    
    escalation_terms = models.CharField(
        max_length=20,
        choices=ESCALATION_CHOICES,
        default='no_escalation',
        help_text="Type of escalation applicable"
    )
    
    has_fixed_escalation = models.BooleanField(
        default=False,
        help_text="Whether this card has a fixed escalation percentage"
    )
    
    annual_escalation_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Annual escalation percentage (e.g., 5.00 for 5%)"
    )
    
    # Payment Terms
    storage_payment_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Payment terms for storage (in days)"
    )
    
    handling_payment_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Payment terms for handling (in days)"
    )
    
    # Financial
    security_deposit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Security deposit amount"
    )
    
    # Master Data Links
    client_card = models.ForeignKey(
        'projects.ClientCard',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='project_cards',
        help_text="Link to client master data",
        db_column='client_card_code', 
        to_field='client_code',
    )
    
    vendor_warehouse = models.ForeignKey(
        'supply.VendorWarehouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='project_cards',
        help_text="Link to vendor warehouse master data",
        db_column='vendor_warehouse_code', 
        to_field='warehouse_code',
    )
    
    # Notes
    notes = models.TextField(
        blank=True,
        default='',
        help_text="Additional notes or comments"
    )
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_project_cards',
        help_text="User who created this card"
    )
    last_modified_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modified_project_cards',
        help_text="User who last modified this card"
    )
    
    class Meta:
        db_table = 'operations_projectcard'
        ordering = ['-version']
        verbose_name = 'Project Card'
        verbose_name_plural = 'Project Cards'
        unique_together = [
            ('project', 'version')
        ]
        indexes = [
            models.Index(fields=['project', 'is_active']),
            models.Index(fields=['valid_from', 'valid_to']),
        ]
    
    def __str__(self):
        status = "ACTIVE" if self.is_active else "ARCHIVED"
        return f"{self.project.project_code} - v{self.version} ({status})"
    
    @property
    def escalation_display(self):
        """Human-readable escalation info"""
        if self.escalation_terms == 'no_escalation':
            return "No Escalation"
        elif self.escalation_terms == 'mutually_agreed':
            return "Mutually Agreed"
        elif self.escalation_terms == 'fixed_percentage' and self.annual_escalation_percent:
            return f"{self.annual_escalation_percent}% Annual"
        return "—"
    
    @property
    def agreement_duration_months(self):
        """Calculate agreement duration in months"""
        if self.agreement_start_date and self.agreement_end_date:
            delta = self.agreement_end_date - self.agreement_start_date
            return round(delta.days / 30)
        return None


class StorageRate(models.Model):
    """
    Simple/flat storage rates for a project card.
    
    This model supports two pricing modes:
    1. **Flat Rate per Unit**: minimum_billable_area + flat_rate_per_unit
    2. **Fixed Monthly Amount**: monthly_billable_amount (lumpsum)
    
    For tiered/slab-based pricing, use StorageRateSlab instead.
    When slabs exist for a rate_for, they take precedence over flat_rate_per_unit.
    """
    
    RATE_FOR_CHOICES = [
        ('client', 'Client'),
        ('vendor', 'Vendor'),
    ]
    
    project_card = models.ForeignKey(
        ProjectCard,
        on_delete=models.CASCADE,
        related_name='storage_rates',
        null=True,
        blank=True,
        help_text="Project card this rate belongs to"
    )
    
    rate_for = models.CharField(
        max_length=20,
        choices=RATE_FOR_CHOICES,
        null=True,
        blank=True,
        help_text="Whether this rate applies to client or vendor"
    )
    
    space_type = models.ForeignKey(
        StorageUnit,
        on_delete=models.PROTECT,
        db_column='space_type',
        to_field='code',
        null=True,
        blank=True,
        help_text="Type of space measurement (sqft, pallet, etc.)"
    )
    
    minimum_billable_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum billable area/quantity. Client pays for at least this much."
    )
    
    flat_rate_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Rate per unit (sqft, pallet, etc.). Used when NOT using slabs."
    )
    
    monthly_billable_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed monthly lumpsum amount. Alternative to flat_rate_per_unit."
    )
    
    saas_monthly_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Monthly SaaS/platform charge (added on top of storage cost)"
    )

    remarks = models.TextField(
        blank=True, 
        default='',
        help_text="Optional notes about this rate"
    )
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_storage_rates',
        help_text="User who created this rate"
    )
    
    class Meta:
        db_table = 'operations_storagerate'
        ordering = ['rate_for']
        verbose_name = 'Storage Rate'
        verbose_name_plural = 'Storage Rates'
    
    def has_slabs(self):
        """Check if this rate has associated slabs (slabs override flat rate)"""
        if not self.project_card or not self.rate_for or not self.space_type:
            return False
        return StorageRateSlab.objects.filter(
            project_card=self.project_card,
            rate_for=self.rate_for,
            space_type=self.space_type
        ).exists()
    
    def __str__(self):
        if not self.project_card:
            return "Unassigned Rate"
        return f"{self.project_card.project.project_code} - {self.rate_for} - {self.space_type}"


class StorageRateSlab(models.Model):
    """
    Tiered/graduated storage pricing for volume-based discounts.
    
    Example:
    - Slab 1: 0-1000 sqft @ ₹10/sqft
    - Slab 2: 1001-5000 sqft @ ₹8/sqft  
    - Slab 3: 5001+ sqft @ ₹6/sqft
    
    When slabs exist for a rate_for, they take precedence over StorageRate.flat_rate_per_unit.
    """
    
    RATE_FOR_CHOICES = [
        ('client', 'Client'),
        ('vendor', 'Vendor'),
    ]

    project_card = models.ForeignKey(
        ProjectCard,
        on_delete=models.CASCADE,
        related_name='storage_slabs',
        null=True,
        blank=True,
        help_text="Project card this slab belongs to"
    )
    
    rate_for = models.CharField(
        max_length=20,
        choices=RATE_FOR_CHOICES,
        null=True,
        blank=True,
        help_text="Whether this slab applies to client or vendor"
    )
    
    space_type = models.ForeignKey(
        StorageUnit,
        on_delete=models.PROTECT,
        db_column='space_type',
        to_field='code',
        null=True,
        blank=True,
        help_text="Type of space measurement (sqft, pallet, etc.)"
    )
    
    min_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum quantity for this slab (inclusive). Use 0 for first slab."
    )
    
    max_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum quantity for this slab (inclusive). Leave NULL for 'above' (last slab)."
    )
    
    rate_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Rate per unit in this slab"
    )
    
    remarks = models.TextField(
        blank=True, 
        default='',
        help_text="Optional notes about this slab"
    )
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_storage_slabs',
        help_text="User who created this slab"
    )
    
    class Meta:
        db_table = 'operations_storagerateslab'
        ordering = ['rate_for', 'min_quantity']
        verbose_name = 'Storage Rate Slab'
        verbose_name_plural = 'Storage Rate Slabs'
    
    def __str__(self):
        if not self.project_card:
            return "Unassigned Slab"
        max_qty = f"{self.max_quantity}" if self.max_quantity else "above"
        return f"{self.project_card.project.project_code} - {self.rate_for}: {self.min_quantity}-{max_qty} @ ₹{self.rate_per_unit}"


class HandlingRate(models.Model):
    """Handling rates for inbound/outbound operations"""
    
    RATE_FOR_CHOICES = [
        ('client', 'Client'),
        ('vendor', 'Vendor'),
    ]
    
    DIRECTION_CHOICES = [
        ('in', 'Inbound'),
        ('out', 'Outbound'),
    ]
    
    project_card = models.ForeignKey(
        ProjectCard,
        on_delete=models.CASCADE,
        related_name='handling_rates',
        help_text="Project card this rate belongs to"
    )
    
    rate_for = models.CharField(
        max_length=20,
        choices=RATE_FOR_CHOICES,
        help_text="Client or Vendor rate"
    )
    
    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        help_text="Inbound or Outbound"
    )
    
    channel = models.ForeignKey(
        SalesChannel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column='channel',
        to_field='code',
        help_text="Sales channel (B2B, B2C, etc.)"
    )
    
    base_type = models.ForeignKey(
        HandlingBaseType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column='base_type',
        to_field='code',
        help_text="Base type for rate calculation"
    )
    
    min_weight_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum weight in kg for this rate"
    )
    
    max_weight_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum weight in kg for this rate"
    )
    
    rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Rate amount"
    )
    
    # condition = models.ForeignKey(
    #     Condition,
    #     on_delete=models.PROTECT,
    #     null=True,
    #     blank=True,
    #     db_column='condition',
    #     to_field='code',
    #     help_text="Condition for rate application"
    # )
    
    # condition_value = models.DecimalField(
    #     max_digits=10,
    #     decimal_places=2,
    #     null=True,
    #     blank=True,
    #     help_text="Value for the condition"
    # )
    
    remarks = models.TextField(blank=True, default='')
    
    class Meta:
        db_table = 'operations_handlingrate'
        ordering = ['rate_for', 'direction']
        verbose_name = 'Handling Rate'
        verbose_name_plural = 'Handling Rates'
    
    def __str__(self):
        return f"{self.project_card.project.project_code} - {self.rate_for} - {self.direction}"


class ValueAddedService(models.Model):
    """Value Added Services rates"""
    
    RATE_FOR_CHOICES = [
        ('client', 'Client'),
        ('vendor', 'Vendor'),
    ]
    
    project_card = models.ForeignKey(
        ProjectCard,
        on_delete=models.CASCADE,
        related_name='vas_services',
        help_text="Project card this service belongs to"
    )
    
    rate_for = models.CharField(
        max_length=20,
        choices=RATE_FOR_CHOICES,
        help_text="Client or Vendor rate"
    )
    
    service_type = models.ForeignKey(
        VASServiceType,
        on_delete=models.PROTECT,
        db_column='service_type',
        to_field='code',
        help_text="Type of value-added service"
    )
    
    service_description = models.TextField(
        blank=True,
        default='',
        help_text="Description of the service"
    )
    
    rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Rate for this service"
    )
    
    unit = models.CharField(
        max_length=50,
        default='per unit',
        help_text="Unit of measurement"
    )
    
    remarks = models.TextField(blank=True, default='')
    
    class Meta:
        db_table = 'operations_valueaddedservice'
        ordering = ['rate_for', 'service_type']
        verbose_name = 'Value Added Service'
        verbose_name_plural = 'Value Added Services'
    
    def __str__(self):
        return f"{self.project_card.project.project_code} - {self.rate_for} - {self.service_type}"


class InfrastructureCost(models.Model):
    """Infrastructure and other fixed costs"""
    
    RATE_FOR_CHOICES = [
        ('client', 'Client'),
        ('vendor', 'Vendor'),
    ]
    
    project_card = models.ForeignKey(
        ProjectCard,
        on_delete=models.CASCADE,
        related_name='infrastructure_costs',
        help_text="Project card this cost belongs to"
    )
    
    rate_for = models.CharField(
        max_length=20,
        choices=RATE_FOR_CHOICES,
        help_text="Client or Vendor cost"
    )
    
    cost_type = models.ForeignKey(
        OperationalCostType,
        on_delete=models.PROTECT,
        db_column='cost_type',
        to_field='code',
        null=True,
        blank=True,
        help_text="Type of infrastructure cost (optional)"
    )

    
    description = models.TextField(
        blank=True,
        default='',
        help_text="Description of the cost"
    )
    
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Cost amount"
    )
    
    is_at_actual = models.BooleanField(
        default=False,
        help_text="Whether this cost is billed at actual"
    )
    
    remarks = models.TextField(blank=True, default='')
    
    class Meta:
        db_table = 'operations_infrastructurecost'
        ordering = ['rate_for', 'cost_type']
        verbose_name = 'Infrastructure Cost'
        verbose_name_plural = 'Infrastructure Costs'
    
    def __str__(self):
        return f"{self.project_card.project.project_code} - {self.rate_for} - {self.cost_type}"


class TransportRate(models.Model):
    """Transport rates for the project"""
    
    RATE_FOR_CHOICES = [
        ('client', 'Client'),
        ('vendor', 'Vendor'),
    ]
    
    project_card = models.ForeignKey(
        ProjectCard,
        on_delete=models.CASCADE,
        related_name='transport_rates',
        help_text="Project card this rate belongs to"
    )
    
    rate_for = models.CharField(
        max_length=20,
        choices=RATE_FOR_CHOICES,
        help_text="Client or Vendor rate"
    )
    
    vehicle_type = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Type of vehicle (e.g., Truck, Van, etc.)"
    )
    
    rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Transport rate"
    )
    
    description = models.TextField(
        blank=True,
        default='',
        help_text="Description of transport service"
    )
    
    remarks = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'operations_transportrate'
        ordering = ['rate_for', 'vehicle_type']
        verbose_name = 'Transport Rate'
        verbose_name_plural = 'Transport Rates'
    
    def __str__(self):
        return f"{self.project_card.project.project_code} - {self.rate_for} - {self.vehicle_type}"