"""
Quotation Management Models
Manual client entry approach - no FK to ClientCard
"""

import hashlib

from django.db import connection, models, transaction
from django.conf import settings
from decimal import Decimal, InvalidOperation
from datetime import timedelta


class Quotation(models.Model):
    """
    Main quotation model with MANUAL CLIENT ENTRY.
    No FK to ClientCard - allows fast quotation creation for new clients.
    """
    # Primary key
    quotation_id = models.AutoField(primary_key=True)

    # Auto-generated unique quotation number (format: GW-Q-20260213-0001)
    quotation_number = models.CharField(max_length=50, unique=True, editable=False)

    # MANUAL CLIENT ENTRY FIELDS (no FK to ClientCard)
    client_name = models.CharField(
        max_length=255,
        help_text="Contact person name"
    )
    client_company = models.CharField(
        max_length=255,
        help_text="Company/organization name"
    )
    client_email = models.EmailField(
        help_text="Primary email for quotation delivery"
    )
    client_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Contact phone number"
    )
    client_address = models.TextField(
        blank=True,
        help_text="Full address for quotation (deprecated - use billing_address)"
    )
    billing_address = models.TextField(
        blank=True,
        help_text="Billing address"
    )
    shipping_address = models.TextField(
        blank=True,
        help_text="Shipping address (leave blank if same as billing)"
    )
    client_gst_number = models.CharField(
        max_length=15,
        blank=True,
        help_text="GST number (optional)"
    )

    # Quotation details
    date = models.DateField(auto_now_add=True)
    validity_period = models.IntegerField(
        default=30,
        help_text="Validity in days (from QuotationSettings default)"
    )
    point_of_contact = models.CharField(
        max_length=255,
        blank=True,
        help_text="Point of contact name"
    )
    poc_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Point of contact phone number"
    )

    # Status workflow
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('voided', 'Voided'),
        ('expired', 'Expired'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Commercial table type
    COMMERCIAL_TYPE_CHOICES = [
        ('vendor', 'Vendor Commercial'),
        ('market_rate', 'Market Rate'),
    ]
    commercial_type = models.CharField(
        max_length=20,
        choices=COMMERCIAL_TYPE_CHOICES,
        default='vendor',
        help_text='Type of cost input used for this quotation'
    )
    default_markup_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('26.00'),
        help_text='Default markup % applied to cost to derive client price'
    )
    expiry_notified = models.BooleanField(
        default=False,
        help_text='True once expiry management command has processed this quotation'
    )

    # GST configuration
    gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('18.00'),
        help_text="GST rate in percentage (from QuotationSettings default)"
    )

    # Operational Scope of Service (replaces legacy scope_of_service checkboxes)
    operational_total_boxes = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text='Total boxes to be stored across all SKUs'
    )
    operational_variance_pct = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=Decimal('30.00'),
        help_text='Batch management buffer percentage (default 30%)'
    )
    operational_pallet_l = models.DecimalField(
        max_digits=6, decimal_places=3,
        default=Decimal('3.330'),
        help_text='Pallet length in ft (default 3.33)'
    )
    operational_pallet_w = models.DecimalField(
        max_digits=6, decimal_places=3,
        default=Decimal('3.330'),
        help_text='Pallet width in ft (default 3.33)'
    )
    operational_pallet_h = models.DecimalField(
        max_digits=6, decimal_places=3,
        default=Decimal('4.000'),
        help_text='Pallet height in ft (default 4.00)'
    )

    # Terms & Conditions
    payment_terms = models.TextField(
        blank=True,
        help_text="Payment terms (uses default from settings if empty)"
    )
    sla_terms = models.TextField(
        blank=True,
        help_text="SLA & service commitments (uses default from settings if empty)"
    )
    contract_terms = models.TextField(
        blank=True,
        help_text="Contract tenure terms (uses default from settings if empty)"
    )
    liability_terms = models.TextField(
        blank=True,
        help_text="Liability & compliance terms (uses default from settings if empty)"
    )

    # Branding & Signature
    company_tagline = models.CharField(
        max_length=255,
        default="Comprehensive Warehousing & Logistics Services",
        help_text="Company tagline for quotation header"
    )
    for_godamwale_signatory = models.CharField(
        max_length=255,
        default="Annand Aryamane [9820504595]",
        help_text="Godamwale authorized signatory"
    )

    # Margin override / director approval
    margin_override_requested = models.BooleanField(
        default=False,
        help_text='User requested director approval for sub-22% margin'
    )
    margin_override_approved = models.BooleanField(
        default=False,
        help_text='Director approved the low-margin exception'
    )
    margin_override_approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_margin_quotations'
    )
    margin_override_approved_at = models.DateTimeField(null=True, blank=True)

    # Relationships
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_quotations'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Calculated properties
    @property
    def validity_date(self):
        """Calculate validity end date."""
        return self.date + timedelta(days=self.validity_period)

    @property
    def subtotal(self):
        """Sum of all location subtotals (client commercials)."""
        return sum(loc.subtotal for loc in self.locations.all())

    @property
    def vendor_subtotal(self):
        """Sum of all location vendor subtotals."""
        return sum(loc.vendor_subtotal for loc in self.locations.all())

    @property
    def margin_pct(self):
        """Gross markup percentage: (client - cost) / cost * 100.
        Returns None if cost subtotal is zero (markup undefined)."""
        client = self.subtotal
        vendor = self.vendor_subtotal
        if vendor == 0:
            return None
        return ((client - vendor) / vendor) * Decimal('100')

    @property
    def pallet_area_sqft(self):
        """Pallet floor area in sq.ft."""
        return self.operational_pallet_l * self.operational_pallet_w

    @property
    def pallet_volume_ft3(self):
        """Pallet volume in cubic feet."""
        return self.operational_pallet_l * self.operational_pallet_w * self.operational_pallet_h

    @property
    def total_pallets_required(self):
        """Sum of num_pallets across all SKUs. Returns None if any SKU is incomplete."""
        products = list(self.products.all())
        if not products:
            return None
        pallets = [p.num_pallets for p in products]
        if any(p is None for p in pallets):
            return None
        return sum(pallets)

    @property
    def actual_pallets_required(self):
        """total_pallets * (1 + variance_pct / 100)."""
        total = self.total_pallets_required
        if total is None:
            return None
        return total * (1 + self.operational_variance_pct / Decimal('100'))

    @property
    def billable_storage_area_sqft(self):
        """actual_pallets * 25 sq.ft."""
        actual = self.actual_pallets_required
        if actual is None:
            return None
        return actual * Decimal('25')

    @property
    def gst_amount(self):
        """Calculate GST amount."""
        return (self.subtotal * self.gst_rate) / Decimal('100')

    @property
    def grand_total(self):
        """Calculate grand total with GST."""
        return self.subtotal + self.gst_amount

    class Meta:
        db_table = 'quotation'
        ordering = ['-date', '-quotation_id']
        indexes = [
            models.Index(fields=['client_company', 'status']),
            models.Index(fields=['created_by']),
            models.Index(fields=['-date']),
            models.Index(fields=['client_email']),
        ]

    def __str__(self):
        return f"{self.quotation_number} - {self.client_company}"

    def save(self, *args, **kwargs):
        """Auto-generate quotation number on creation."""
        if not self.quotation_number:
            from datetime import date
            today = date.today()
            date_str = today.strftime('%Y%m%d')

            with transaction.atomic():
                # Serialise number generation for this date using a PostgreSQL advisory lock.
                # pg_advisory_xact_lock is transaction-scoped and releases on commit/rollback.
                # This prevents duplicate numbers even under concurrent requests.
                lock_key = int(hashlib.md5(f'qnum_{date_str}'.encode()).hexdigest()[:15], 16) % (2 ** 63 - 1)
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_xact_lock(%s)', [lock_key])

                last_quotation = (
                    Quotation.objects
                    .filter(quotation_number__startswith=f'GW-Q-{date_str}')
                    .order_by('-quotation_number')
                    .first()
                )
                if last_quotation:
                    last_seq = int(last_quotation.quotation_number.split('-')[-1])
                    new_seq = last_seq + 1
                else:
                    new_seq = 1

                self.quotation_number = f'GW-Q-{date_str}-{new_seq:04d}'
                super().save(*args, **kwargs)
            return

        super().save(*args, **kwargs)


class QuotationLocation(models.Model):
    """Multi-location pricing support."""
    location_id = models.AutoField(primary_key=True)

    quotation = models.ForeignKey(
        'Quotation',
        on_delete=models.CASCADE,
        related_name='locations'
    )

    location_name = models.CharField(max_length=255)
    order = models.IntegerField(default=0, help_text="Display order")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def subtotal(self):
        """Sum of all client item totals for this location."""
        return sum(
            item.total for item in self.items.all()
            if item.is_calculated
        )

    @property
    def vendor_subtotal(self):
        """Sum of all vendor item totals for this location."""
        return sum(
            item.vendor_total for item in self.items.all()
            if item.vendor_is_calculated
        )

    @property
    def gst_amount(self):
        """Calculate GST for this location."""
        return (self.subtotal * self.quotation.gst_rate) / Decimal('100')

    @property
    def grand_total(self):
        """Calculate total with GST for this location."""
        return self.subtotal + self.gst_amount

    class Meta:
        db_table = 'quotation_location'
        ordering = ['quotation', 'order']
        unique_together = [['quotation', 'order']]

    def __str__(self):
        return f"{self.quotation.quotation_number} - {self.location_name}"


class QuotationItem(models.Model):
    """Line items with flexible pricing (numeric or text like 'at actual')."""
    item_id = models.AutoField(primary_key=True)

    location = models.ForeignKey(
        'QuotationLocation',
        on_delete=models.CASCADE,
        related_name='items'
    )

    ITEM_DESCRIPTION_CHOICES = [
        ('storage_per_pallet', 'Storage Charges (per pallet per month)'),
        ('inbound_handling', 'Inbound Handling (per unit)'),
        ('outbound_handling', 'Outbound Handling (per unit)'),
        ('pick_pack', 'Pick & Pack (per order)'),
        ('packaging_material', 'Packaging Material'),
        ('labelling', 'Labelling Services'),
        ('wms_access', 'WMS Platform Access (monthly per pallet)'),
        ('value_added', 'Value-Added Services'),
        ('transport', 'Transport Services'),
        ('other', 'Other'),
    ]
    item_description = models.CharField(max_length=50, choices=ITEM_DESCRIPTION_CHOICES)
    custom_description = models.CharField(max_length=255, blank=True, help_text="Optional custom description override")

    # Flexible pricing - can be numeric or text
    unit_cost = models.CharField(
        max_length=50,
        help_text="Enter number or 'at actual'"
    )
    quantity = models.CharField(
        max_length=50,
        default='1',
        help_text="Enter number or 'as applicable'"
    )

    # Vendor commercials
    vendor_unit_cost = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Vendor cost per unit or 'at actual'"
    )
    vendor_quantity = models.CharField(
        max_length=50,
        blank=True,
        default='1',
        help_text="Vendor quantity or 'as applicable'"
    )

    STORAGE_UNIT_CHOICES = [
        ('pallet', 'Per Pallet'),
        ('sqft', 'Per Sq. Ft.'),
        ('cbm', 'Per CBM'),
        ('mt', 'Per MT'),
        ('unit', 'Per Unit'),
    ]
    storage_unit_type = models.CharField(
        max_length=20,
        choices=STORAGE_UNIT_CHOICES,
        blank=True,
        null=True
    )

    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_calculated(self):
        """Check if client item has numeric values."""
        try:
            Decimal(self.unit_cost)
            Decimal(self.quantity)
            return True
        except (ValueError, InvalidOperation):
            return False

    @property
    def total(self):
        """Calculate client total if numeric."""
        if self.is_calculated:
            return Decimal(self.unit_cost) * Decimal(self.quantity)
        return Decimal('0.00')

    @property
    def vendor_is_calculated(self):
        """Check if vendor item has numeric values."""
        try:
            Decimal(self.vendor_unit_cost)
            Decimal(self.vendor_quantity)
            return True
        except (ValueError, InvalidOperation):
            return False

    @property
    def vendor_total(self):
        """Calculate vendor total if numeric."""
        if self.vendor_is_calculated:
            return Decimal(self.vendor_unit_cost) * Decimal(self.vendor_quantity)
        return Decimal('0.00')

    @property
    def item_margin_pct(self):
        """Markup % for this item: (client - cost) / cost * 100. Returns None if vendor total is zero."""
        client = self.total
        vendor = self.vendor_total
        if vendor == 0:
            return None
        return ((client - vendor) / vendor) * Decimal('100')

    @property
    def display_unit_cost(self):
        """Format for display."""
        if self.is_calculated:
            return f"₹{Decimal(self.unit_cost):,.2f}"
        return self.unit_cost.title()

    @property
    def display_quantity(self):
        """Format for display."""
        if self.is_calculated:
            return f"{Decimal(self.quantity):,.2f}"
        return self.quantity.title()

    @property
    def display_total(self):
        """Format for display."""
        if self.is_calculated:
            return f"₹{self.total:,.2f}"
        return "As Applicable"

    class Meta:
        db_table = 'quotation_item'
        ordering = ['location', 'order']

    def __str__(self):
        desc = self.custom_description if self.custom_description else self.get_item_description_display()
        return f"{self.location.location_name} - {desc}"


class QuotationProduct(models.Model):
    """Per-SKU product data for Operational Scope of Service section."""

    BUSINESS_TYPE_CHOICES = [
        ('B2B', 'B2B'),
        ('B2C', 'B2C'),
    ]
    OPERATION_TYPE_CHOICES = [
        ('box_in_box_out', 'Box In \u2013 Box Out'),
        ('box_in_piece_out', 'Box In \u2013 Piece Out'),
        ('box_in_pallet_out', 'Box In \u2013 Pallet Out'),
        ('pallet_in_box_out', 'Pallet In \u2013 Box Out'),
    ]
    DIM_UNIT_CHOICES = [
        ('MM', 'MM'),
        ('CM', 'CM'),
        ('INCH', 'INCH'),
        ('FT', 'FT'),
    ]
    _UNIT_TO_FT = {
        'MM': Decimal('304.8'),
        'CM': Decimal('30.48'),
        'INCH': Decimal('12'),
        'FT': Decimal('1'),
    }

    product_id = models.AutoField(primary_key=True)
    quotation = models.ForeignKey(
        'Quotation',
        on_delete=models.CASCADE,
        related_name='products'
    )
    product_name = models.CharField(max_length=255)
    type_of_business = models.CharField(
        max_length=10,
        choices=BUSINESS_TYPE_CHOICES,
        default='B2B'
    )
    type_of_operation = models.CharField(
        max_length=30,
        choices=OPERATION_TYPE_CHOICES
    )
    packaging_type = models.CharField(max_length=100, blank=True)
    avg_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        help_text='Average box/bag/pallet weight in kg'
    )
    dim_l = models.DecimalField(max_digits=10, decimal_places=4)
    dim_w = models.DecimalField(max_digits=10, decimal_places=4)
    dim_h = models.DecimalField(max_digits=10, decimal_places=4)
    dim_unit = models.CharField(max_length=10, choices=DIM_UNIT_CHOICES, default='CM')
    share_pct = models.DecimalField(
        max_digits=6, decimal_places=2,
        default=Decimal('100.00'),
        help_text='% of total boxes this SKU represents (0-100)'
    )
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'quotation_product'
        ordering = ['quotation', 'order']

    def __str__(self):
        return f"{self.quotation.quotation_number} \u2013 {self.product_name}"

    def _to_ft(self, val):
        """Convert dimension value to feet."""
        divisor = self._UNIT_TO_FT.get(self.dim_unit, Decimal('1'))
        return val / divisor

    @property
    def dim_l_ft(self):
        return self._to_ft(self.dim_l)

    @property
    def dim_w_ft(self):
        return self._to_ft(self.dim_w)

    @property
    def dim_h_ft(self):
        return self._to_ft(self.dim_h)

    @property
    def volume_per_box_ft3(self):
        """Product box volume in cubic feet."""
        return self.dim_l_ft * self.dim_w_ft * self.dim_h_ft

    @property
    def boxes_per_pallet(self):
        """How many boxes fit per pallet."""
        vol = self.volume_per_box_ft3
        if vol == 0:
            return None
        pallet_vol = self.quotation.pallet_volume_ft3
        if not pallet_vol:
            return None
        return pallet_vol / vol

    @property
    def total_boxes(self):
        """Boxes for this SKU = total_boxes * share_pct / 100."""
        if self.quotation.operational_total_boxes is None:
            return None
        return self.quotation.operational_total_boxes * (self.share_pct / Decimal('100'))

    @property
    def num_pallets(self):
        """Pallets required for this SKU."""
        bpp = self.boxes_per_pallet
        tb = self.total_boxes
        if bpp is None or tb is None or bpp == 0:
            return None
        return tb / bpp


class QuotationAudit(models.Model):
    """Comprehensive audit trail for quotations."""
    audit_id = models.AutoField(primary_key=True)

    quotation = models.ForeignKey(
        'Quotation',
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    ACTION_CHOICES = [
        ('created', 'Created'),
        ('modified', 'Modified'),
        ('docx_generated', 'DOCX Generated'),
        ('pdf_generated', 'PDF Generated'),
        ('email_sent', 'Email Sent'),
        ('status_changed', 'Status Changed'),
        ('downloaded', 'Downloaded'),
        ('revision_created', 'Revision Created'),
        ('cloned', 'Cloned'),
        ('acceptance_link_sent', 'Acceptance Link Sent'),
        ('client_accepted', 'Client Accepted'),
        ('client_rejected', 'Client Rejected'),
    ]
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)

    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    additional_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'quotation_audit'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['quotation', '-timestamp']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.quotation.quotation_number} - {self.action} at {self.timestamp}"


import uuid as _uuid


class QuotationRevision(models.Model):
    """Snapshot of quotation state before a significant edit (e.g. editing a sent/accepted quote)."""
    revision_id = models.AutoField(primary_key=True)
    quotation = models.ForeignKey(
        'Quotation',
        on_delete=models.CASCADE,
        related_name='revisions'
    )
    revision_number = models.IntegerField()
    snapshot = models.JSONField(
        help_text='Full snapshot: quotation fields + all locations/items at time of revision'
    )
    reason = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'quotation_revision'
        unique_together = [['quotation', 'revision_number']]
        ordering = ['-revision_number']

    def __str__(self):
        return f"{self.quotation.quotation_number} Rev {self.revision_number}"


class QuotationAcceptanceToken(models.Model):
    """Secure token for client to accept/reject a quotation without logging in."""
    token_id = models.AutoField(primary_key=True)
    quotation = models.OneToOneField(
        'Quotation',
        on_delete=models.CASCADE,
        related_name='acceptance_token'
    )
    token = models.UUIDField(default=_uuid.uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    accepted = models.BooleanField(null=True, blank=True)  # None=pending, True=accepted, False=rejected
    client_remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'quotation_acceptance_token'

    def __str__(self):
        return f"{self.quotation.quotation_number} — token {self.token}"

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    @property
    def is_used(self):
        return self.used_at is not None
