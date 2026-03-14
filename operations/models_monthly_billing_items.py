"""
Monthly Billing Line Items
Separate models for storing multiple entries per section (Storage, Handling, Transport, VAS, etc.)

ARCHITECTURE: Follows the same proven pattern as AdhocBillingLineItem
- Each row is a separate database record
- NO auto-summing on save (parent model handles totals explicitly)
- Preserves exact user input with 4 decimal places
"""

from django.db import models
from decimal import Decimal


class MonthlyBillingStorageItem(models.Model):
    """
    Individual storage entry within a monthly billing.
    Allows multiple storage line items per billing.

    CRITICAL: Client and vendor can have DIFFERENT quantities, unit types, and rates
    Example: Client 1200 sq ft @ ₹8/sq ft, Vendor 1000 pallets @ ₹5/pallet
    """
    monthly_billing = models.ForeignKey(
        'operations.MonthlyBilling',
        on_delete=models.CASCADE,
        related_name='storage_items'
    )

    # Client side quantities
    client_min_space = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    client_additional_space = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    client_storage_unit_type = models.ForeignKey(
        'dropdown_master_data.StorageUnit',
        on_delete=models.PROTECT,
        db_column='client_storage_unit_type',
        to_field='code',
        related_name='monthly_billing_storage_items_client',
        null=True,
        blank=True
    )
    client_storage_days = models.IntegerField(default=0)
    client_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    client_billing = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    # Vendor side quantities
    vendor_min_space = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    vendor_additional_space = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    vendor_storage_unit_type = models.ForeignKey(
        'dropdown_master_data.StorageUnit',
        on_delete=models.PROTECT,
        db_column='vendor_storage_unit_type',
        to_field='code',
        related_name='monthly_billing_storage_items_vendor',
        null=True,
        blank=True
    )
    vendor_storage_days = models.IntegerField(default=0)
    vendor_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    vendor_cost = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    # Common fields
    remarks = models.TextField(blank=True, default='')
    row_order = models.IntegerField(default=0)

    # Pricing model (flat rate, slab-based, or lumpsum)
    PRICING_TYPE_CHOICES = [
        ('flat', 'Flat Rate'),
        ('slab', 'Tiered/Slab Based'),
        ('lumpsum', 'Lumpsum'),
    ]
    pricing_type = models.CharField(
        max_length=10,
        choices=PRICING_TYPE_CHOICES,
        default='flat',
        help_text="Pricing model: flat rate, slab-based, or lumpsum"
    )

    # Lumpsum amounts (used when pricing_type='lumpsum')
    client_lumpsum_amount = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Fixed monthly amount for client (lumpsum pricing)"
    )
    vendor_lumpsum_amount = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Fixed monthly cost for vendor (lumpsum pricing)"
    )

    class Meta:
        db_table = 'monthly_billing_storage_items'
        ordering = ['row_order']
        verbose_name = 'Monthly Billing Storage Item'
        verbose_name_plural = 'Monthly Billing Storage Items'

    def __str__(self):
        return f"{self.monthly_billing} - Storage Item {self.row_order}"


class MonthlyBillingHandlingItem(models.Model):
    """
    Individual handling entry (IN or OUT) within a monthly billing.

    CRITICAL: Client and vendor can have DIFFERENT quantities and unit types
    Example: Client 500 kg @ ₹3/kg, Vendor 0.5 tons @ ₹2000/ton
    """
    DIRECTION_CHOICES = [
        ('in', 'Inbound'),
        ('out', 'Outbound'),
    ]

    monthly_billing = models.ForeignKey(
        'operations.MonthlyBilling',
        on_delete=models.CASCADE,
        related_name='handling_items'
    )

    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)

    # Client side quantities
    client_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    client_unit_type = models.ForeignKey(
        'dropdown_master_data.HandlingUnit',
        on_delete=models.PROTECT,
        db_column='client_unit_type',
        to_field='code',
        related_name='monthly_billing_handling_items_client',
        null=True,
        blank=True
    )
    client_channel = models.ForeignKey(
        'dropdown_master_data.SalesChannel',
        on_delete=models.PROTECT,
        db_column='client_channel',
        to_field='code',
        related_name='monthly_billing_handling_items_client',
        null=True,
        blank=True
    )
    client_base_type = models.ForeignKey(
        'dropdown_master_data.HandlingBaseType',
        on_delete=models.PROTECT,
        db_column='client_base_type',
        to_field='code',
        related_name='monthly_billing_handling_items_client',
        null=True,
        blank=True
    )
    client_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    client_billing = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    # Vendor side quantities
    vendor_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    vendor_unit_type = models.ForeignKey(
        'dropdown_master_data.HandlingUnit',
        on_delete=models.PROTECT,
        db_column='vendor_unit_type',
        to_field='code',
        related_name='monthly_billing_handling_items_vendor',
        null=True,
        blank=True
    )
    vendor_channel = models.ForeignKey(
        'dropdown_master_data.SalesChannel',
        on_delete=models.PROTECT,
        db_column='vendor_channel',
        to_field='code',
        related_name='monthly_billing_handling_items_vendor',
        null=True,
        blank=True
    )
    vendor_base_type = models.ForeignKey(
        'dropdown_master_data.HandlingBaseType',
        on_delete=models.PROTECT,
        db_column='vendor_base_type',
        to_field='code',
        related_name='monthly_billing_handling_items_vendor',
        null=True,
        blank=True
    )
    vendor_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    vendor_cost = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    # Common fields
    remarks = models.TextField(blank=True, default='')
    row_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'monthly_billing_handling_items'
        ordering = ['direction', 'row_order']
        verbose_name = 'Monthly Billing Handling Item'
        verbose_name_plural = 'Monthly Billing Handling Items'

    def __str__(self):
        direction_label = 'IN' if self.direction == 'in' else 'OUT'
        return f"{self.monthly_billing} - Handling {direction_label} Item {self.row_order}"


class MonthlyBillingTransportItem(models.Model):
    """
    Individual transport entry within a monthly billing.
    """
    SIDE_CHOICES = [
        ('vendor', 'Vendor'),
        ('client', 'Client'),
    ]

    monthly_billing = models.ForeignKey(
        'operations.MonthlyBilling',
        on_delete=models.CASCADE,
        related_name='transport_items'
    )

    side = models.CharField(max_length=10, choices=SIDE_CHOICES)

    vehicle_type = models.ForeignKey(
        'dropdown_master_data.VehicleType',
        on_delete=models.PROTECT,
        db_column='vehicle_type',
        to_field='code',
        null=True,
        blank=True
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    amount = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    remarks = models.TextField(blank=True, default='')

    # Row order
    row_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'monthly_billing_transport_items'
        ordering = ['side', 'row_order']
        verbose_name = 'Monthly Billing Transport Item'
        verbose_name_plural = 'Monthly Billing Transport Items'

    def __str__(self):
        return f"{self.monthly_billing} - {self.side.title()} Transport Item {self.row_order}"


class MonthlyBillingVASItem(models.Model):
    """
    Individual VAS (Value Added Service) entry within a monthly billing.

    CRITICAL: Client and vendor can have DIFFERENT service types, quantities, and units
    Example: Client labeling 1000 pieces, Vendor packaging 100 boxes
    """
    monthly_billing = models.ForeignKey(
        'operations.MonthlyBilling',
        on_delete=models.CASCADE,
        related_name='vas_items'
    )

    # Client side service details
    client_service_type = models.ForeignKey(
        'dropdown_master_data.VASServiceType',
        on_delete=models.PROTECT,
        db_column='client_service_type',
        to_field='code',
        related_name='monthly_billing_vas_items_client',
        null=True,
        blank=True
    )
    client_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    client_unit = models.ForeignKey(
        'dropdown_master_data.VASUnit',
        on_delete=models.PROTECT,
        db_column='client_unit',
        to_field='code',
        related_name='monthly_billing_vas_items_client',
        null=True,
        blank=True
    )
    client_hours = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
        help_text="Number of hours (used when unit is Per Hour)"
    )
    client_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    client_billing = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    # Vendor side service details
    vendor_service_type = models.ForeignKey(
        'dropdown_master_data.VASServiceType',
        on_delete=models.PROTECT,
        db_column='vendor_service_type',
        to_field='code',
        related_name='monthly_billing_vas_items_vendor',
        null=True,
        blank=True
    )
    vendor_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    vendor_unit = models.ForeignKey(
        'dropdown_master_data.VASUnit',
        on_delete=models.PROTECT,
        db_column='vendor_unit',
        to_field='code',
        related_name='monthly_billing_vas_items_vendor',
        null=True,
        blank=True
    )
    vendor_hours = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
        help_text="Number of hours (used when unit is Per Hour)"
    )
    vendor_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    vendor_cost = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    # Common fields
    remarks = models.TextField(blank=True, default='')
    row_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'monthly_billing_vas_items'
        ordering = ['row_order']
        verbose_name = 'Monthly Billing VAS Item'
        verbose_name_plural = 'Monthly Billing VAS Items'

    def __str__(self):
        return f"{self.monthly_billing} - VAS Item {self.row_order}"


class MonthlyBillingInfrastructureItem(models.Model):
    """
    Individual Infrastructure cost entry within a monthly billing.

    Examples: Equipment rental, facility charges, utilities, manpower costs
    CRITICAL: Client and vendor can have DIFFERENT amounts (markup/passthrough)
    """
    monthly_billing = models.ForeignKey(
        'operations.MonthlyBilling',
        on_delete=models.CASCADE,
        related_name='infrastructure_items'
    )

    # Cost type and description
    cost_type = models.ForeignKey(
        'dropdown_master_data.OperationalCostType',
        on_delete=models.PROTECT,
        db_column='cost_type',
        to_field='code',
        related_name='monthly_billing_infrastructure_items',
        null=True,
        blank=True,
        help_text='Type of infrastructure cost (Equipment, Facility, Utilities, etc.)'
    )
    description = models.TextField(
        blank=True,
        default='',
        help_text='Detailed description of this infrastructure cost'
    )

    # Client side (what we charge the client)
    client_billing = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        default=0,
        help_text='Amount charged to client for this infrastructure item'
    )

    # Vendor side (what vendor charges us)
    vendor_cost = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        default=0,
        help_text='Amount vendor charges us for this infrastructure item'
    )

    # Common fields
    row_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'monthly_billing_infrastructure_items'
        ordering = ['row_order']
        verbose_name = 'Monthly Billing Infrastructure Item'
        verbose_name_plural = 'Monthly Billing Infrastructure Items'

    def __str__(self):
        cost_type_name = self.cost_type.name if self.cost_type else 'Infrastructure'
        return f"{self.monthly_billing} - {cost_type_name} Item {self.row_order}"


class MonthlyBillingStorageSlab(models.Model):
    """
    Tiered/graduated storage pricing slabs for Monthly Billing.
    Similar to StorageRateSlab in Project Cards, but for actual monthly billing.

    Example:
    - Slab 1: 0-1000 sqft @ ₹10/sqft
    - Slab 2: 1001-5000 sqft @ ₹8/sqft
    - Slab 3: 5001+ sqft @ ₹6/sqft

    When slabs exist for a storage item, they take precedence over flat rates.
    Each slab is stored separately in the database for flexibility.
    """

    SIDE_CHOICES = [
        ('client', 'Client'),
        ('vendor', 'Vendor'),
    ]

    storage_item = models.ForeignKey(
        'MonthlyBillingStorageItem',
        on_delete=models.CASCADE,
        related_name='slabs',
        help_text="Storage item this slab belongs to"
    )

    side = models.CharField(
        max_length=10,
        choices=SIDE_CHOICES,
        help_text="Whether this slab applies to client or vendor"
    )

    min_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        help_text="Minimum quantity for this slab (inclusive). Use 0 for first slab."
    )

    max_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Maximum quantity for this slab (inclusive). Leave NULL for 'above' (last slab)."
    )

    rate_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Rate per unit in this slab"
    )

    remarks = models.TextField(
        blank=True,
        default='',
        help_text="Optional notes about this slab"
    )

    row_order = models.IntegerField(
        default=0,
        help_text="Order of slabs (for display)"
    )

    class Meta:
        db_table = 'monthly_billing_storage_slabs'
        ordering = ['storage_item', 'side', 'row_order']
        verbose_name = 'Monthly Billing Storage Slab'
        verbose_name_plural = 'Monthly Billing Storage Slabs'
        indexes = [
            models.Index(fields=['storage_item', 'side']),
        ]

    def __str__(self):
        max_qty_str = f"{self.max_quantity}" if self.max_quantity else "∞"
        return f"{self.storage_item} - {self.side} Slab: {self.min_quantity}-{max_qty_str} @ ₹{self.rate_per_unit}"
