from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import datetime

User = get_user_model()


class ExpenseLogSettings(models.Model):
    """Singleton model for Google Sheets OAuth configuration"""
    id = models.AutoField(primary_key=True)
    client_id = models.CharField(max_length=500, blank=True)
    encrypted_client_secret = models.TextField(blank=True)
    redirect_uri = models.CharField(max_length=500, blank=True)
    api_version = models.CharField(max_length=10, default='v4')
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='expense_log_settings_updates'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Expense Log Settings'
        verbose_name_plural = 'Expense Log Settings'

    def __str__(self):
        return f"Expense Log Settings (Updated: {self.updated_at})"

    @classmethod
    def load(cls):
        """Load singleton settings object"""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        """Enforce singleton pattern"""
        self.pk = 1
        super().save(*args, **kwargs)

    def get_decrypted_client_secret(self):
        """Decrypt client secret"""
        if not self.encrypted_client_secret:
            return ''
        from .utils.encryption import ExpenseLogEncryption
        return ExpenseLogEncryption.decrypt(self.encrypted_client_secret)


class GoogleSheetsToken(models.Model):
    """OAuth2 token for connecting to Google Sheets"""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='expense_sheet_tokens'
    )
    email_account = models.CharField(max_length=255)
    encrypted_token = models.TextField()
    sheet_id = models.CharField(max_length=255, help_text="Google Sheet ID to sync from")
    sheet_name = models.CharField(max_length=255, default='Sheet1', help_text="Tab name in the sheet")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Google Sheets Token'
        verbose_name_plural = 'Google Sheets Tokens'
        unique_together = ('email_account', 'sheet_id')
        indexes = [
            models.Index(fields=['is_active', '-created_at']),
        ]

    def __str__(self):
        return f"{self.email_account} - {self.sheet_id}"

    def get_decrypted_token(self):
        """Decrypt OAuth token"""
        from .utils.encryption import ExpenseLogEncryption
        return ExpenseLogEncryption.decrypt(self.encrypted_token)


class UserNameMapping(models.Model):
    """Maps ERP users to names in Google Sheets 'Submitted By' column"""
    erp_user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='expense_name_mapping'
    )
    sheet_name = models.JSONField(
        default=list,
        help_text="List of names as they appear in 'Submitted By' column"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_expense_mappings'
    )

    class Meta:
        verbose_name = 'User Name Mapping'
        verbose_name_plural = 'User Name Mappings'

    def __str__(self):
        names = ', '.join(self.sheet_name) if isinstance(self.sheet_name, list) else self.sheet_name
        return f"{self.erp_user.username} → {names}"


class ExpenseRecord(models.Model):
    """Expense record synced from Google Sheets"""
    token = models.ForeignKey(
        GoogleSheetsToken,
        on_delete=models.CASCADE,
        related_name='expenses'
    )
    unique_expense_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique Expense Number from sheet (e.g., UEN00001)"
    )

    # Metadata
    timestamp = models.DateTimeField(help_text="From 'Timestamp' column")
    submitted_by = models.CharField(max_length=255, db_index=True)
    email_address = models.CharField(max_length=255, blank=True)

    # Client info
    client_name = models.CharField(max_length=500, blank=True)
    client = models.CharField(max_length=500, blank=True, help_text="Client entity name")
    service_month = models.CharField(max_length=50, blank=True)

    # Expense details
    nature_of_expense = models.CharField(
        max_length=100,
        blank=True,
        help_text="Transport/Operation/Stationary/Other"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payment_method = models.CharField(max_length=100, blank=True)
    expenses_borne_by = models.CharField(max_length=255, blank=True)
    remark = models.TextField(blank=True)

    # === TRANSPORT FIELDS ===
    transport = models.TextField(blank=True, help_text="Transport field from sheet")
    transport_type = models.CharField(max_length=100, blank=True, help_text="Select your Transport Type")
    transporter_name = models.CharField(max_length=255, blank=True)
    from_address = models.TextField(blank=True)
    to_address = models.TextField(blank=True)
    vehicle_no = models.CharField(max_length=100, blank=True, db_index=True)
    invoice_no = models.CharField(max_length=100, blank=True)
    charges_at_gw = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Charges@GW")
    charges_at_client = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Charges@Client")
    unloading_box_expense = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    box_count = models.IntegerField(null=True, blank=True)
    warai_charges = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    labour_charges = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    pod_hard_copy = models.CharField(max_length=100, blank=True, help_text="POD Hard Copy")
    expense_paid_by_transport = models.CharField(max_length=255, blank=True, help_text="Expense Paid By (Transport)")
    mention_other_transport = models.TextField(blank=True, help_text="Mention Other OR Remarks (Transport)")
    payment_summary_invoice = models.TextField(blank=True, help_text="Payment Summary (Invoice)")
    transport_bill = models.TextField(blank=True, help_text="Transport Bill URL/file")
    upload_invoice_transport_2 = models.TextField(blank=True, help_text="Upload Invoice 2 (Transport)")

    # === OPERATION FIELDS ===
    operation = models.TextField(blank=True, help_text="Operation field from sheet")
    operation_expense_type = models.CharField(max_length=100, blank=True, help_text="Select your Operational Expense Type")
    operation_expense_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expense_paid_by_operation = models.CharField(max_length=255, blank=True, help_text="Expense Paid By (Operation)")
    mention_other_operation = models.TextField(blank=True, help_text="Mention Other OR Remarks (Operation)")
    upload_invoice_operation_1 = models.TextField(blank=True, help_text="Upload Invoice 1 (Operation)")
    upload_invoice_operation_2 = models.TextField(blank=True, help_text="Upload Invoice 2 (Operation)")

    # === STATIONARY FIELDS ===
    stationary = models.TextField(blank=True, help_text="Stationary field from sheet")
    stationary_expense_type = models.CharField(max_length=100, blank=True, help_text="Select your Stationary Expense Type")
    stationary_expense_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expense_paid_by_stationary = models.CharField(max_length=255, blank=True, help_text="Expense Paid By (Stationary)")
    mention_other_stationary = models.TextField(blank=True, help_text="Mention Other OR Remarks (Stationary)")
    upload_invoice_stationary_1 = models.TextField(blank=True, help_text="Upload Invoice 1 (Stationary)")
    upload_invoice_stationary_2 = models.TextField(blank=True, help_text="Upload Invoice 2 (Stationary)")

    # === OTHER EXPENSE FIELDS ===
    other = models.TextField(blank=True, help_text="Other field from sheet")
    other_expense_type = models.CharField(max_length=100, blank=True, help_text="Select your Other Expense Type")
    other_expense_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expense_paid_by_other = models.CharField(max_length=255, blank=True, help_text="Expense Paid By (Other)")
    mention_other_remarks = models.TextField(blank=True, help_text="Mention Other OR Remarks (Other)")
    upload_invoice_other_1 = models.TextField(blank=True, help_text="Upload Invoice 1 (Other)")
    upload_invoice_other_2 = models.TextField(blank=True, help_text="Upload Invoice 2 (Other)")

    # === ADDITIONAL FIELDS ===
    entered_in_tally = models.BooleanField(default=False, help_text="Entered in Tally status")

    # Approval
    approval_status = models.CharField(
        max_length=50,
        default='Pending',
        db_index=True,
        help_text="Approved/Pending/Rejected"
    )

    # Raw data (full sheet row as JSON for flexibility)
    raw_data = models.JSONField(default=dict, help_text="Full row from Google Sheets")

    # Sync tracking
    synced_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Expense Record'
        verbose_name_plural = 'Expense Records'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['submitted_by', '-timestamp']),
            models.Index(fields=['approval_status', '-timestamp']),
            models.Index(fields=['token', '-timestamp']),
            models.Index(fields=['service_month']),
            models.Index(fields=['nature_of_expense', '-timestamp']),
            models.Index(fields=['client_name', '-timestamp']),  # For project-wise grouping
            models.Index(fields=['vehicle_no']),  # For transport search
            models.Index(fields=['transporter_name']),  # For transport search
        ]

    def __str__(self):
        return f"{self.unique_expense_number} - {self.submitted_by} - ₹{self.amount}"

    @classmethod
    def get_expenses_for_user(cls, user):
        """Filter expenses based on user role and name mapping"""
        # Admins, directors, operation controllers, and accounts executives see all expenses
        if user.role in ['admin', 'director', 'operation_controller', 'accounts_executive']:
            return cls.objects.all()

        # Regular users see only their mapped expenses
        try:
            mapping = UserNameMapping.objects.get(erp_user=user)
            # Support both old CharField (string) and new JSONField (list)
            if isinstance(mapping.sheet_name, list):
                # Empty list means no expenses visible
                if not mapping.sheet_name:
                    return cls.objects.none()
                # Check if "ALL_NAMES" special value is present
                if "ALL_NAMES" in mapping.sheet_name:
                    return cls.objects.all()
                return cls.objects.filter(submitted_by__in=mapping.sheet_name)
            else:
                # Empty string means no expenses visible
                if not mapping.sheet_name:
                    return cls.objects.none()
                return cls.objects.filter(submitted_by=mapping.sheet_name)
        except UserNameMapping.DoesNotExist:
            return cls.objects.none()  # No mapping = no expenses visible
