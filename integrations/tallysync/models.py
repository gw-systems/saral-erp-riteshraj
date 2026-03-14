from django.db import models
from django.utils import timezone
from django.db.models import ForeignKey
from projects.models import ProjectCode
from django.contrib.auth import get_user_model

User = get_user_model()


class TallySyncSettings(models.Model):
    """
    Singleton model for TallySync configuration
    Stores Tally server connection details (no OAuth, just XML API over HTTP)
    """
    server_ip = models.CharField(
        max_length=255,
        blank=True,
        help_text="Tally server IP address (e.g., 192.168.1.100)"
    )
    server_port = models.CharField(
        max_length=10,
        default='2245',
        blank=True,
        help_text="Tally XML API port"
    )
    company_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Default Tally company name to sync"
    )
    tunnel_url = models.URLField(
        max_length=500,
        blank=True,
        default='',
        help_text="ngrok/tunnel URL (e.g., https://xxx.ngrok-free.dev). When set, overrides server_ip:port for production."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Enable/disable TallySync integration"
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tallysync_settings_updates'
    )

    class Meta:
        db_table = 'tallysync_settings'
        verbose_name = 'TallySync Settings'
        verbose_name_plural = 'TallySync Settings'

    def __str__(self):
        return f"TallySync Settings ({self.server_ip}:{self.server_port})"

    def save(self, *args, **kwargs):
        # Enforce singleton pattern
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Get or create the singleton settings instance"""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def delete(self, *args, **kwargs):
        """Prevent deletion of singleton"""
        pass


class TallyCompany(models.Model):
    """Stores Tally company information"""
    name = models.CharField(max_length=255, unique=True)
    guid = models.CharField(max_length=255, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tallysync_company'
        verbose_name = 'Tally Company'
        verbose_name_plural = 'Tally Companies'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class TallyGroup(models.Model):
    """Stores Tally groups (ledger categories)"""
    company = models.ForeignKey(TallyCompany, on_delete=models.CASCADE, related_name='groups')
    name = models.CharField(max_length=255)
    parent = models.CharField(max_length=255, blank=True)
    is_revenue = models.BooleanField(default=False)
    is_expense = models.BooleanField(default=False)
    is_asset = models.BooleanField(default=False)
    is_liability = models.BooleanField(default=False)
    
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tallysync_group'
        verbose_name = 'Tally Group'
        verbose_name_plural = 'Tally Groups'
        unique_together = ['company', 'name']
        ordering = ['name']
        indexes = [
            models.Index(fields=['parent']),
            models.Index(fields=['company', 'parent']),
        ]
    
    def __str__(self):
        return self.name


class TallyLedger(models.Model):
    """Stores Tally ledger (account) information"""
    company = models.ForeignKey(TallyCompany, on_delete=models.CASCADE, related_name='ledgers')
    name = models.CharField(max_length=500)
    parent = models.CharField(max_length=255, blank=True)
    group = models.ForeignKey(TallyGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='ledgers')
    guid = models.CharField(max_length=255, blank=True)
    
    # Party details (for customer/vendor ledgers)
    gstin = models.CharField(max_length=15, blank=True)
    state_name = models.CharField(max_length=100, blank=True)
    
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tallysync_ledger'
        verbose_name = 'Tally Ledger'
        verbose_name_plural = 'Tally Ledgers'
        unique_together = ['company', 'name']
        ordering = ['name']
        indexes = [
            models.Index(fields=['parent']),
            models.Index(fields=['gstin']),
        ]
    
    def __str__(self):
        return self.name


class TallyCostCentre(models.Model):
    """Stores Tally cost centres (project codes)"""
    company = models.ForeignKey(TallyCompany, on_delete=models.CASCADE, related_name='cost_centres')
    name = models.CharField(max_length=500)  # Full name like "DL007 - (Bizcrum Infotech - ...)"
    code = models.CharField(max_length=50)  # Extracted code like "DL007"
    
    # Parsed fields
    client_name = models.CharField(max_length=255, blank=True)
    vendor_name = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    
    # Matching to ERP
    erp_project = models.ForeignKey('projects.ProjectCode', on_delete=models.SET_NULL, null=True, blank=True, related_name='tally_cost_centres')
    match_confidence = models.IntegerField(default=0)  # 0-100
    match_method = models.CharField(max_length=50, blank=True)  # 'auto', 'manual', 'fuzzy'
    is_matched = models.BooleanField(default=False)
    
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tallysync_cost_centre'
        verbose_name = 'Tally Cost Centre'
        verbose_name_plural = 'Tally Cost Centres'
        unique_together = ['company', 'code']
        ordering = ['code']
        indexes = [
            models.Index(fields=['is_matched']),
            models.Index(fields=['code']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.client_name}"


class TallyVoucher(models.Model):
    """Stores Tally voucher (transaction) information"""
    VOUCHER_TYPES = [
        ('Sales', 'Sales'),
        ('Purchase', 'Purchase'),
        ('Receipt', 'Receipt'),
        ('Payment', 'Payment'),
        ('Journal', 'Journal'),
        ('Contra', 'Contra'),
        ('Debit Note', 'Debit Note'),
        ('Credit Note', 'Credit Note'),
        ('Proforma invoice', 'Proforma Invoice'),
    ]
    
    company = models.ForeignKey(TallyCompany, on_delete=models.CASCADE, related_name='vouchers')
    
    date = models.DateField()
    voucher_type = models.CharField(max_length=50, choices=VOUCHER_TYPES)
    voucher_number = models.CharField(max_length=100, blank=True, default='')
    guid = models.CharField(max_length=255, unique=True)
    master_id = models.BigIntegerField(null=True, blank=True)
    
    # Party information
    party_ledger_name = models.CharField(max_length=500, blank=True)
    party_name = models.CharField(max_length=500, blank=True)
    party_gstin = models.CharField(max_length=15, blank=True)
    party_state = models.CharField(max_length=100, blank=True)
    
    # Invoice details
    reference = models.CharField(max_length=255, blank=True)
    narration = models.TextField(blank=True)
    is_invoice = models.BooleanField(default=False)
    is_cancelled = models.BooleanField(default=False)
    
    # Amounts
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # E-way bill
    eway_bill_number = models.CharField(max_length=50, blank=True)
    
    # Bank/Payment details
    payment_mode = models.CharField(max_length=50, blank=True)
    cheque_number = models.CharField(max_length=50, blank=True)
    cheque_date = models.DateField(null=True, blank=True)
    
    # Buyer/Consignee details (for B2B invoices)
    buyer_name = models.CharField(max_length=500, blank=True)
    buyer_gstin = models.CharField(max_length=15, blank=True)
    buyer_state = models.CharField(max_length=100, blank=True)
    consignee_name = models.CharField(max_length=500, blank=True)
    consignee_gstin = models.CharField(max_length=15, blank=True)
    
    # Matching to ERP
    erp_monthly_billing = models.ForeignKey('operations.MonthlyBilling', on_delete=models.SET_NULL, null=True, blank=True, related_name='tally_vouchers')
    erp_adhoc_billing = models.ForeignKey('operations.AdhocBillingEntry', on_delete=models.SET_NULL, null=True, blank=True, related_name='tally_vouchers')
    is_matched = models.BooleanField(default=False)
    
    # Raw XML for reference
    raw_xml = models.TextField(blank=True)
    
    # Payment transaction details
    transaction_type = models.CharField(max_length=50, blank=True)   # Cheque / NEFT / IMPS etc
    utr_number = models.CharField(max_length=100, blank=True)         # UNIQUEREFERENCENUMBER
    credit_period = models.CharField(max_length=20, blank=True)       # 7 Days / 30 Days etc

    # Custom UDF fields
    billing_month = models.CharField(max_length=10, blank=True)       # Like "NOV25"
    billing_month_date = models.DateField(null=True, blank=True)      # First of billing month, derived from billing_month; falls back to date
    need_to_pay = models.CharField(max_length=255, blank=True)        # PAYMENTFAVOURING
    remark = models.TextField(blank=True)                              # NARRATION
    
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tallysync_voucher'
        verbose_name = 'Tally Voucher'
        verbose_name_plural = 'Tally Vouchers'
        unique_together = ['company', 'guid'] 
        ordering = ['-date', 'voucher_number']
        indexes = [
            models.Index(fields=['date', 'voucher_type']),
            models.Index(fields=['company', 'date']),
            models.Index(fields=['company', 'voucher_type', 'date']),
            models.Index(fields=['is_matched']),
            models.Index(fields=['party_ledger_name']),
            models.Index(fields=['guid']),
        ]
    
    def __str__(self):
        return f"{self.voucher_type} - {self.voucher_number} ({self.date})"


class TallyVoucherLedgerEntry(models.Model):
    """Stores individual ledger entries within a voucher (double-entry details)"""
    voucher = models.ForeignKey(TallyVoucher, on_delete=models.CASCADE, related_name='ledger_entries')
    ledger = models.ForeignKey(TallyLedger, on_delete=models.SET_NULL, null=True, blank=True)
    ledger_name = models.CharField(max_length=500)
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    is_debit = models.BooleanField()  # True = Debit, False = Credit
    
    # GST Details
    gst_class = models.CharField(max_length=100, blank=True)
    gst_hsn_code = models.CharField(max_length=20, blank=True)
    
    cgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    igst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cess_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    cgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    sgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    igst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cess_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # TDS Details
    tds_nature_of_payment = models.CharField(max_length=255, blank=True)
    tds_section = models.CharField(max_length=50, blank=True)
    tds_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tallysync_voucher_ledger_entry'
        verbose_name = 'Voucher Ledger Entry'
        verbose_name_plural = 'Voucher Ledger Entries'
        ordering = ['voucher', 'id']
        indexes = [
            models.Index(fields=['voucher']),
            models.Index(fields=['ledger_name']),
            models.Index(fields=['ledger']),
        ]
    
    def __str__(self):
        return f"{self.ledger_name} - ₹{self.amount}"


class TallyVoucherCostCentreAllocation(models.Model):
    """Stores cost centre allocations within voucher ledger entries"""
    ledger_entry = models.ForeignKey(TallyVoucherLedgerEntry, on_delete=models.CASCADE, related_name='cost_allocations')
    cost_centre = models.ForeignKey(TallyCostCentre, on_delete=models.SET_NULL, null=True, blank=True)
    cost_centre_name = models.CharField(max_length=500)
    category = models.CharField(max_length=255, blank=True)  # Like "Primary Cost Category"
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tallysync_cost_allocation'
        verbose_name = 'Cost Centre Allocation'
        verbose_name_plural = 'Cost Centre Allocations'
        indexes = [
            models.Index(fields=['cost_centre']),
            models.Index(fields=['ledger_entry']),
        ]
    
    def __str__(self):
        return f"{self.cost_centre_name} - ₹{self.amount}"


class TallyBillReference(models.Model):
    """Stores bill/invoice references from vouchers"""
    ledger_entry = models.ForeignKey(TallyVoucherLedgerEntry, on_delete=models.CASCADE, related_name='bills')
    
    bill_name = models.CharField(max_length=255)  # Like "GJ-296", "Invoice-001"
    bill_type = models.CharField(max_length=50)  # "New Ref", "Agst Ref", etc.
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    class Meta:
        db_table = 'tallysync_bill_reference'
        verbose_name = 'Bill Reference'
        verbose_name_plural = 'Bill References'
        ordering = ['ledger_entry', 'bill_name']
    
    def __str__(self):
        return f"{self.bill_name} - ₹{self.amount}"


class ProjectCostCentreMapping(models.Model):
    """Manual mapping table for ERP projects to Tally cost centres"""
    erp_project = models.ForeignKey('projects.ProjectCode', on_delete=models.CASCADE, related_name='tally_mappings')
    tally_cost_centre = models.ForeignKey(TallyCostCentre, on_delete=models.CASCADE, related_name='erp_mappings')
    
    mapped_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    mapping_note = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tallysync_project_mapping'
        verbose_name = 'Project-Cost Centre Mapping'
        verbose_name_plural = 'Project-Cost Centre Mappings'
        unique_together = ['erp_project', 'tally_cost_centre']
    
    def __str__(self):
        return f"{self.erp_project.project_code} → {self.tally_cost_centre.code}"


class VarianceAlert(models.Model):
    """Stores detected variances between ERP and Tally"""
    ALERT_TYPES = [
        ('amount_mismatch', 'Amount Mismatch'),
        ('missing_in_tally', 'Missing in Tally'),
        ('missing_in_erp', 'Missing in ERP'),
        ('unmatched_cost_centre', 'Unmatched Cost Centre'),
        ('date_mismatch', 'Date Mismatch'),
    ]
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('ignored', 'Ignored'),
    ]
    
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    severity = models.CharField(max_length=20, default='medium')  # 'low', 'medium', 'high'
    
    # References
    tally_voucher = models.ForeignKey(TallyVoucher, on_delete=models.CASCADE, null=True, blank=True, related_name='variance_alerts')
    erp_monthly_billing = models.ForeignKey('operations.MonthlyBilling', on_delete=models.CASCADE, null=True, blank=True)
    erp_adhoc_billing = models.ForeignKey('operations.AdhocBillingEntry', on_delete=models.CASCADE, null=True, blank=True)
    
    # Variance details
    erp_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    tally_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    variance_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    description = models.TextField()
    resolution_note = models.TextField(blank=True)
    
    assigned_to = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_variance_alerts')
    resolved_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_variance_alerts')
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tallysync_variance_alert'
        verbose_name = 'Variance Alert'
        verbose_name_plural = 'Variance Alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'alert_type']),
            models.Index(fields=['severity']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.alert_type} - ₹{self.variance_amount} ({self.status})"



