from django.db import models
from django.contrib.auth import get_user_model
from dropdown_master_data.models import (
    WarehouseGrade as MasterWarehouseGrade,
    PropertyType as MasterPropertyType,
    BusinessType as MasterBusinessType,
    StorageUnit as MasterStorageUnit,
    SLAStatus as MasterSLAStatus
)
import hashlib
import re

User = get_user_model()


# ============================================================================
# MASTER DATA / LOOKUP TABLES
# ============================================================================

class Location(models.Model):
    """Master location data"""
    id = models.AutoField(primary_key=True)
    
    region = models.CharField(max_length=20, default='central')
    state_code = models.CharField(max_length=2, blank=True, null=True)
    city_code = models.CharField(max_length=3, blank=True, null=True)
    
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50)
    location = models.CharField(max_length=100, default='Unknown')
    pincode = models.CharField(max_length=6, blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'locations'
        ordering = ['state', 'city', 'location']
        unique_together = [['state', 'city', 'location']]
        indexes = [
            models.Index(fields=['state_code']),
            models.Index(fields=['city_code']),
            models.Index(fields=['is_active', 'state', 'city'], name='idx_loc_active_state_city'),
        ]

    def __str__(self):
        return f"{self.location}, {self.city}, {self.state}"
    
    @property
    def full_location(self):
        return f"{self.location}, {self.city}, {self.state}"
    
    @property
    def city_name(self):
        return self.city
    
    @property
    def state_name(self):
        return self.state
    
    @property
    def region_name(self):
        return self.region


class CityCode(models.Model):
    city_name = models.CharField(max_length=100)
    city_code = models.CharField(max_length=3, unique=True)
    state_code = models.CharField(max_length=2)  # NOT a FK, just a CharField
    is_active = models.BooleanField(default=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    
    class Meta:
        db_table = 'city_codes'
        unique_together = [('city_name', 'state_code')]
        indexes = [
            models.Index(fields=['city_code'], name='idx_city_codes_code'),
        ]
    
    def __str__(self):
        return f"{self.city_name} ({self.city_code})"



# ============================================================================
# VENDOR CARDS
# ============================================================================

class VendorCard(models.Model):
    """Vendor master data"""
    vendor_code = models.CharField(max_length=50, primary_key=True)
    def save(self, *args, **kwargs):
        if not self.vendor_code:
            self.vendor_code = self.generate_vendor_code(self.vendor_legal_name)
        if not self.vendor_short_name:
            words = self.vendor_legal_name.split()
            self.vendor_short_name = ' '.join(words[:2]) if len(words) >= 2 else self.vendor_legal_name
        super().save(*args, **kwargs)

    @staticmethod
    def sanitize_name(name):
        noise = [
            'pvt ltd', 'private limited', 'pvt. ltd.', 'ltd',
            'limited', 'llp', 'llc', 'inc', 'incorporated'
        ]
        clean_name = name.lower()
        for n in noise:
            clean_name = clean_name.replace(n, '')
        clean_name = re.sub(r'[^a-z0-9\s]', '', clean_name)
        clean_name = ' '.join(clean_name.split())
        return clean_name.strip()

    @staticmethod
    def generate_vendor_code(vendor_legal_name):
        clean_name = VendorCard.sanitize_name(vendor_legal_name)
        alphanumeric = re.sub(r'[^a-zA-Z]', '', vendor_legal_name)
        prefix = alphanumeric[:3].upper()
        if len(prefix) < 3:
            prefix = prefix.ljust(3, 'X')
        hash_object = hashlib.sha256(clean_name.encode())
        hash_hex = hash_object.hexdigest()
        suffix = hash_hex[-4:].upper()
        return f"{prefix}-{suffix}"
    vendor_short_name = models.CharField(max_length=100, blank=True)
    vendor_legal_name = models.CharField(max_length=200)
    vendor_trade_name = models.CharField(max_length=200, blank=True)
    
    vendor_pan = models.CharField(
        max_length=10,
        blank=True,
        db_column='vendor_pan_number'
    )
    vendor_gstin = models.CharField(
        max_length=15,
        blank=True,
        db_column='vendor_gst_number'
    )
    vendor_cin_number = models.CharField(max_length=21, blank=True)
    
    vendor_registered_address = models.TextField(blank=True)
    vendor_corporate_address = models.TextField(blank=True)
    vendor_is_active = models.BooleanField(default=True)
    vendor_created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    vendor_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendor_cards'
        ordering = ['-vendor_created_at']
        indexes = [
            models.Index(fields=['vendor_is_active'], name='idx_vc_is_active'),
            models.Index(fields=['vendor_is_active', 'vendor_short_name'], name='idx_vc_active_name'),
        ]

    def __str__(self):
        return f"{self.vendor_code} - {self.vendor_short_name}"


class VendorContact(models.Model):
    """Vendor contact persons"""
    id = models.AutoField(primary_key=True)
    vendor_code = models.ForeignKey(
        VendorCard,
        on_delete=models.CASCADE,
        db_column='vendor_code_id',
        to_field='vendor_code',
        related_name='contacts'
    )
    vendor_contact_person = models.CharField(max_length=100)
    vendor_contact_designation = models.CharField(max_length=100)
    vendor_contact_department = models.CharField(max_length=100)
    vendor_contact_phone = models.CharField(max_length=15)
    vendor_contact_email = models.EmailField()
    vendor_contact_is_primary = models.BooleanField(default=False)
    vendor_contact_is_active = models.BooleanField(default=True)
    vendor_contact_created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    # RFQ-specific fields (from Vivek Data sheet)
    is_rfq_contact = models.BooleanField(default=False)
    rfq_cc_emails = models.JSONField(
        default=list,
        blank=True,
        help_text="CC email addresses for RFQ emails (JSON array)"
    )
    rfq_cities = models.CharField(
        max_length=500,
        blank=True,
        help_text="Comma-separated cities this vendor serves (e.g., 'Mumbai, Pune, Bangalore')"
    )
    rfq_contact_number = models.CharField(max_length=15, blank=True)


    class Meta:
        db_table = 'vendor_contacts'

    def __str__(self):
        return f"{self.vendor_contact_person} ({self.vendor_code.vendor_short_name})"


# ============================================================================
# WAREHOUSES
# ============================================================================

class VendorWarehouse(models.Model):
    """Vendor warehouse master data"""
    id = models.AutoField(primary_key=True)
    warehouse_code = models.CharField(max_length=100, unique=True)
    def save(self, *args, **kwargs):
        if not self.warehouse_code and self.warehouse_location_id:
            try:
                city_code_obj = CityCode.objects.get(
                    city_name=self.warehouse_location_id.city,
                    is_active=True
                )
                state_code = city_code_obj.state_code
                city_code = city_code_obj.city_code
            except CityCode.DoesNotExist:
                state_code = self.warehouse_location_id.state[:2].upper()
                city_code = self.warehouse_location_id.city[:3].upper()
            
            location_name = self.warehouse_location_id.location

            # Generate unique sequence number by checking all warehouses with same code pattern
            code_prefix = f"{state_code}-{city_code}-{location_name}-"
            existing_codes = VendorWarehouse.objects.filter(
                warehouse_code__startswith=code_prefix
            ).values_list('warehouse_code', flat=True)

            # Find the next available sequence number
            sequence_number = 1
            while f"{code_prefix}{str(sequence_number).zfill(3)}" in existing_codes:
                sequence_number += 1

            self.warehouse_code = f"{code_prefix}{str(sequence_number).zfill(3)}"
        
        super().save(*args, **kwargs)
    vendor_code = models.ForeignKey(
        VendorCard,
        on_delete=models.CASCADE,
        db_column='vendor_code',
        to_field='vendor_code',
        related_name='warehouses'
    )
    warehouse_name = models.CharField(max_length=200, blank=True, null=True)
    warehouse_digipin = models.CharField(max_length=20, blank=True, null=True)
    warehouse_address = models.TextField(blank=True, null=True)
    warehouse_pincode = models.CharField(max_length=6, blank=True, null=True)
    warehouse_location_id = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        db_column='warehouse_location_id',
        null=True,
        blank=True
    )
    warehouse_owner_name = models.CharField(max_length=150, blank=True, null=True)
    warehouse_owner_contact = models.CharField(max_length=15, blank=True, null=True)
    google_map_location = models.CharField(max_length=500, blank=True, null=True)
    warehouse_is_active = models.BooleanField(default=True)
    warehouse_created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    warehouse_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendor_warehouses'
        ordering = ['-warehouse_created_at']
        indexes = [
            models.Index(fields=['warehouse_is_active'], name='idx_vw_is_active'),
            models.Index(fields=['warehouse_location_id', 'warehouse_is_active'], name='idx_vw_loc_active'),
            models.Index(fields=['vendor_code', 'warehouse_is_active'], name='idx_vw_vendor_active'),
        ]

    def __str__(self):
        return f"{self.warehouse_code} - {self.warehouse_name or 'Unnamed'}"


class WarehouseProfile(models.Model):
    """Warehouse profile details"""
    warehouse = models.OneToOneField(
        VendorWarehouse,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column='warehouse_id',
        related_name='profile'
    )
    warehouse_grade = models.ForeignKey(
        MasterWarehouseGrade,
        on_delete=models.PROTECT,
        db_column='warehouse_grade_id',
        to_field='code',
        null=True,
        blank=True
    )
    property_type = models.ForeignKey(
        MasterPropertyType,
        on_delete=models.PROTECT,
        db_column='property_type_id',
        to_field='code',
        null=True,
        blank=True
    )
    business_type = models.ForeignKey(
        MasterBusinessType,
        on_delete=models.PROTECT,
        db_column='business_type_id',
        to_field='code',
        null=True,
        blank=True
    )
    fire_safety_compliant = models.BooleanField(default=False)
    security_features = models.TextField(blank=True)
    certifications = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'warehouse_profiles'

    def __str__(self):
        return f"Profile: {self.warehouse.warehouse_code}"


class WarehouseCapacity(models.Model):
    """Warehouse capacity details"""
    warehouse = models.OneToOneField(
        VendorWarehouse,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column='warehouse_id',
        related_name='capacity'
    )
    capacity_unit_type = models.ForeignKey(
        MasterStorageUnit,
        on_delete=models.PROTECT,
        db_column='capacity_unit_type_id',
        to_field='code',
        null=True,
        blank=True
    )
    total_area_sqft = models.IntegerField(null=True, blank=True)
    total_capacity = models.IntegerField(null=True, blank=True)
    available_capacity = models.IntegerField(null=True, blank=True)
    pallets_available = models.IntegerField(null=True, blank=True)
    racking_available = models.BooleanField(default=False)
    racking_details = models.TextField(blank=True)
    forklifts_count = models.IntegerField(null=True, blank=True)
    loading_bays_count = models.IntegerField(null=True, blank=True)
    operating_hours = models.CharField(max_length=100, blank=True)
    is_24x7 = models.BooleanField(default=False)
    temperature_controlled = models.BooleanField(default=False)
    hazmat_supported = models.BooleanField(default=False)
    last_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'warehouse_capacities'

    def __str__(self):
        return f"Capacity: {self.warehouse.warehouse_code}"


class WarehouseCommercial(models.Model):
    """Warehouse commercial details"""
    warehouse = models.OneToOneField(
        VendorWarehouse,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column='warehouse_id',
        related_name='commercial'
    )
    rate_unit_type = models.ForeignKey(
        MasterStorageUnit,
        on_delete=models.PROTECT,
        db_column='rate_unit_type_id',
        to_field='code',
        null=True,
        blank=True,
        related_name='commercials_by_rate_unit'
    )
    sla_status = models.ForeignKey(
        MasterSLAStatus,
        on_delete=models.PROTECT,
        db_column='sla_status_id',
        to_field='code',
        null=True,
        blank=True
    )
    indicative_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    minimum_commitment_months = models.IntegerField(null=True, blank=True)
    payment_terms = models.TextField(blank=True)
    security_deposit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    contract_start_date = models.DateField(null=True, blank=True)
    contract_end_date = models.DateField(null=True, blank=True)
    notice_period_days = models.IntegerField(null=True, blank=True)
    escalation_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    escalation_terms = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'warehouse_commercials'

    def __str__(self):
        return f"Commercial: {self.warehouse.warehouse_code}"


class WarehouseContact(models.Model):
    """Warehouse contact persons"""
    id = models.AutoField(primary_key=True)
    warehouse_code = models.ForeignKey(
        VendorWarehouse,
        on_delete=models.CASCADE,
        db_column='warehouse_code_id',
        to_field='warehouse_code',
        related_name='contacts'
    )
    warehouse_contact_person = models.CharField(max_length=100)
    warehouse_contact_designation = models.CharField(max_length=100)
    warehouse_contact_department = models.CharField(max_length=20)
    warehouse_contact_phone = models.CharField(max_length=15)
    warehouse_contact_email = models.EmailField()
    warehouse_contact_is_primary = models.BooleanField(default=False)
    warehouse_contact_is_active = models.BooleanField(default=True)
    warehouse_contact_created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)


    class Meta:
        db_table = 'warehouse_contacts'

    def __str__(self):
        return f"{self.warehouse_contact_person} ({self.warehouse_code.warehouse_name})"


class VendorWarehouseDocument(models.Model):
    """Warehouse documents"""
    id = models.AutoField(primary_key=True)
    warehouse_code = models.OneToOneField(
        VendorWarehouse,
        on_delete=models.CASCADE,
        db_column='warehouse_code_id',
        to_field='warehouse_code',
        related_name='documents'
    )
    vendor_code = models.ForeignKey(
        VendorCard,
        on_delete=models.CASCADE,
        db_column='vendor_code_id',
        to_field='vendor_code'
    )
    warehouse_electricity_bill = models.FileField(upload_to='warehouse_docs/electricity/', blank=True, null=True)
    warehouse_property_tax_receipt = models.FileField(upload_to='warehouse_docs/tax/', blank=True, null=True)

    # Legal & Compliance Documents (Multiple files stored as JSON)
    warehouse_owner_agreements = models.JSONField(default=dict, blank=True, help_text="Rent agreements between Owner & Vendor (multiple files)")
    warehouse_sla_documents = models.JSONField(default=dict, blank=True, help_text="SLA documents between Vendor & Godamwale (multiple files)")
    warehouse_other_legal_docs = models.JSONField(default=dict, blank=True, help_text="Other legal & compliance documents (multiple files)")

    warehouse_poc_aadhar = models.FileField(upload_to='warehouse_docs/poc_aadhar/', blank=True, null=True)
    warehouse_poc_pan = models.FileField(upload_to='warehouse_docs/poc_pan/', blank=True, null=True)
    warehouse_noc_owner = models.FileField(upload_to='warehouse_docs/noc_owner/', blank=True, null=True)
    warehouse_owner_pan = models.FileField(upload_to='warehouse_docs/owner_pan/', blank=True, null=True)
    warehouse_owner_aadhar = models.FileField(upload_to='warehouse_docs/owner_aadhar/', blank=True, null=True)
    warehouse_noc_vendor = models.FileField(upload_to='warehouse_docs/noc_vendor/', blank=True, null=True)
    warehouse_doc_uploaded_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    warehouse_doc_last_updated = models.DateTimeField(auto_now=True)
    warehouse_doc_uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='warehouse_doc_uploaded_by_id'
    )

    class Meta:
        db_table = 'vendor_warehouse_documents'

    def __str__(self):
        return f"Documents: {self.warehouse_code.warehouse_code}"
    


class WarehousePhoto(models.Model):
    """Warehouse photos/videos"""
    id = models.AutoField(primary_key=True)
    warehouse_code = models.ForeignKey(
        VendorWarehouse,
        on_delete=models.CASCADE,
        db_column='warehouse_code',
        to_field='warehouse_code',
        related_name='photos'
    )
    file = models.FileField(upload_to='warehouse_photos/')
    file_type = models.CharField(max_length=10, choices=[('photo', 'Photo'), ('video', 'Video')])
    caption = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='uploaded_by_id'
    )

    class Meta:
        db_table = 'warehouse_photos'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Photo: {self.warehouse_code.warehouse_code}"

# ============================================================================
# RFQ (REQUEST FOR QUOTATION) MODELS
# ============================================================================

class RFQ(models.Model):
    """
    Request for Quotation
    Auto-generates RFQ IDs like RFQ-042576, RFQ-042577, etc.
    """
    rfq_id = models.CharField(max_length=20, unique=True, primary_key=True)

    # Basic Information
    status = models.CharField(
        max_length=20,
        choices=[
            ('open', 'Open'),
            ('closed', 'Closed'),
            ('postponed', 'Postponed'),
        ],
        default='open',
        db_index=True
    )
    city = models.CharField(max_length=200, db_index=True)
    area_required_sqft = models.IntegerField()
    product = models.CharField(max_length=200)
    tenure = models.CharField(
        max_length=20,
        choices=[
            ('short', 'Short Term'),
            ('medium', 'Medium Term'),
            ('high', 'Long Term'),
        ],
        blank=True
    )
    remarks = models.TextField(blank=True)

    # Optional Rates (from Google Sheet columns)
    storage_rate_sqft = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Storage Rate (Rs/Sq Ft)"
    )
    storage_rate_pallet = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Storage Rate (Rs/Pallet)"
    )
    storage_rate_mt = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Storage Rate (Rs/MT)"
    )
    handling_rate_pallet = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Handling Rate (Rs/Pallet)"
    )

    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='rfqs_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rfqs'
        ordering = ['-rfq_id']
        verbose_name = 'RFQ'
        verbose_name_plural = 'RFQs'

    def __str__(self):
        return f"{self.rfq_id} - {self.area_required_sqft} sqft in {self.city}"

    def save(self, *args, **kwargs):
        """Auto-generate RFQ ID if not set"""
        if not self.rfq_id:
            # Get the last RFQ
            last_rfq = RFQ.objects.order_by('-rfq_id').first()

            if last_rfq:
                # Extract numeric part: "RFQ-042575" → 42575
                try:
                    last_number = int(last_rfq.rfq_id.split('-')[1])
                    next_number = last_number + 1
                except (IndexError, ValueError):
                    # Fallback if format is unexpected
                    next_number = 42576
            else:
                # First RFQ ever - start from 42576 (after user's last RFQ-042575)
                next_number = 42576

            # Format: RFQ-042576 (6 digits with leading zeros)
            self.rfq_id = f"RFQ-{next_number:06d}"

        super().save(*args, **kwargs)

    @property
    def vendors_sent_count(self):
        """Count of vendors this RFQ was sent to"""
        return self.vendor_mappings.count()

    @property
    def response_rate(self):
        """Percentage of vendors who responded"""
        total = self.vendor_mappings.count()
        if total == 0:
            return 0
        responded = self.vendor_mappings.filter(response_received=True).count()
        return round((responded / total) * 100, 1)


class RFQVendorMapping(models.Model):
    """
    Tracks which vendors received which RFQs
    Links to Gmail Email model for email history
    """
    id = models.AutoField(primary_key=True)

    # RFQ and Vendor
    rfq = models.ForeignKey(
        RFQ,
        on_delete=models.CASCADE,
        related_name='vendor_mappings'
    )
    vendor_contact = models.ForeignKey(
        VendorContact,
        on_delete=models.PROTECT,
        related_name='rfq_mappings'
    )

    # Email Details
    sent_from_account = models.EmailField()  # Which Gmail account sent it
    sent_to_email = models.EmailField()  # Primary TO
    sent_cc_emails = models.JSONField(default=list, blank=True)  # CC emails used
    deadline_date = models.DateField()

    # Point of Contact (POC)
    point_of_contact = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rfq_poc_mappings'
    )

    # Link to Gmail Message (optional)
    gmail_email = models.ForeignKey(
        'gmail.Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rfq_mappings'
    )

    # Tracking
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='rfq_emails_sent'
    )

    # Response Tracking
    response_received = models.BooleanField(default=False)
    response_date = models.DateTimeField(null=True, blank=True)
    quoted_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    vendor_notes = models.TextField(blank=True)
    follow_up_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending Response'),
            ('responded', 'Responded'),
            ('quoted', 'Quote Received'),
            ('declined', 'Declined'),
            ('no_response', 'No Response'),
        ],
        default='pending'
    )

    class Meta:
        db_table = 'rfq_vendor_mappings'
        unique_together = [('rfq', 'vendor_contact')]  # Can't send same RFQ to same vendor twice
        ordering = ['-sent_at']
        verbose_name = 'RFQ Vendor Mapping'
        verbose_name_plural = 'RFQ Vendor Mappings'

    def __str__(self):
        return f"{self.rfq.rfq_id} → {self.vendor_contact.vendor_code.vendor_short_name}"

    @property
    def days_since_sent(self):
        """Number of days since RFQ was sent"""
        from django.utils import timezone
        delta = timezone.now() - self.sent_at
        return delta.days

    @property
    def is_overdue(self):
        """Check if deadline has passed"""
        from django.utils import timezone
        return timezone.now().date() > self.deadline_date
