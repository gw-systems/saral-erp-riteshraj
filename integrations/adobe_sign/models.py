"""
Adobe Sign E-Signature Models
Enhanced models with improved workflow and template support
"""

import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

User = get_user_model()


def document_upload_path(instance, filename):
    """Generate upload path for documents"""
    return f'adobe_sign/documents/{instance.id}/{filename}'


class DocumentTemplate(models.Model):
    """
    Pre-configured document templates with signature field definitions
    Eliminates manual field placement - backoffice just selects template
    """
    TEMPLATE_TYPE_CHOICES = [
        ('nda', 'Non-Disclosure Agreement'),
        ('service_agreement', 'Service Agreement'),
        ('lease_agreement', 'Lease Agreement'),
        ('amendment', 'Amendment'),
        ('renewal', 'Renewal Agreement'),
        ('termination', 'Termination Notice'),
        ('custom', 'Custom Document'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text='Template name (e.g., "Standard NDA")')
    template_type = models.CharField(max_length=50, choices=TEMPLATE_TYPE_CHOICES, default='custom')
    description = models.TextField(blank=True, help_text='What this template is used for')

    # Template file with pre-placed signature fields using Adobe Text Tags
    template_file = models.FileField(
        upload_to='adobe_sign/templates/',
        help_text='PDF with Adobe Text Tags for signature fields'
    )

    # Field definitions (JSON) - stores which text tags are in the template
    field_definitions = models.JSONField(
        default=dict,
        help_text='JSON mapping of field names to text tag patterns'
    )

    # Default signer configuration
    default_signer_order = models.JSONField(
        default=list,
        help_text='Default signer order: [{"role": "Director", "order": 1}, {"role": "Client", "order": 2}]'
    )

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_templates')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['template_type', 'name']
        verbose_name = 'Document Template'
        verbose_name_plural = 'Document Templates'

    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"


class Document(models.Model):
    """
    Uploaded documents for e-signature
    Enhanced with template linking and validation
    """
    FILE_TYPE_CHOICES = [
        ('pdf', 'PDF'),
        ('docx', 'DOCX'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to=document_upload_path)
    file_name = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    file_size = models.PositiveIntegerField(default=0, help_text='File size in bytes')
    file_hash = models.CharField(max_length=64, blank=True, help_text='SHA-256 hash for deduplication')

    # Optional: Link to template if document was generated from template
    template = models.ForeignKey(
        DocumentTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents'
    )

    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_documents')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'

    def save(self, *args, **kwargs):
        if self.file:
            self.file_name = self.file.name
            self.file_size = self.file.size

            # Detect file type
            if self.file.name.lower().endswith('.pdf'):
                self.file_type = 'pdf'
            elif self.file.name.lower().endswith('.docx'):
                self.file_type = 'docx'

        super().save(*args, **kwargs)

    def __str__(self):
        return self.file_name


class AdobeAgreement(models.Model):
    """
    Adobe Sign agreement with enhanced approval workflow

    Workflow States:
    1. DRAFT - Being prepared by backoffice
    2. PENDING_APPROVAL - Submitted to admin for review
    3. REJECTED - Admin sent back for corrections
    4. APPROVED_SENT - Admin approved and sent to client
    5. COMPLETED - All parties signed
    6. CANCELLED - Agreement cancelled
    """

    # Adobe Agreement Status (synced from Adobe API)
    AGREEMENT_STATUS_CHOICES = [
        ('AUTHORING', 'Authoring'),  # Being prepared in Adobe
        ('DRAFT', 'Draft'),
        ('OUT_FOR_SIGNATURE', 'Out for Signature'),
        ('WAITING_FOR_MY_SIGNATURE', 'Waiting for My Signature'),
        ('SIGNED', 'Signed'),
        ('APPROVED', 'Approved'),
        ('DELIVERED', 'Delivered'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('EXPIRED', 'Expired'),
        ('RECALLED', 'Recalled'),
        ('ARCHIVED', 'Archived'),
        ('PREFILL', 'Prefill'),
        ('WIDGET', 'Widget'),
        ('DOCUMENTS_NOT_YET_PROCESSED', 'Documents Not Yet Processed'),
        ('WAITING_FOR_FAXIN', 'Waiting for Fax In'),
        ('WAITING_FOR_VERIFICATION', 'Waiting for Verification'),
        ('OTHER', 'Other'),
    ]

    # Internal Approval Workflow Status
    APPROVAL_STATUS_CHOICES = [
        ('DRAFT', 'Draft'),  # Being prepared by backoffice
        ('PENDING_APPROVAL', 'Pending Admin Approval'),  # Waiting for Vivek Sir
        ('REJECTED', 'Sent Back for Correction'),  # Vivek Sir rejected
        ('APPROVED_SENT', 'Approved and Sent'),  # Sent to client
        ('COMPLETED', 'Completed'),  # All signatures collected
        ('CANCELLED', 'Cancelled'),  # Agreement cancelled
    ]

    # Signing Flow Type
    FLOW_TYPE_CHOICES = [
        ('director_then_client', 'Director Signs First, Then Client'),
        ('client_only', 'Client Only (Director Already Signed Physically)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Document reference
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='agreements',
        help_text='Document to be signed'
    )

    # Adobe agreement ID (from Adobe API)
    adobe_agreement_id = models.CharField(
        max_length=255,
        unique=True,
        blank=True,
        null=True,
        help_text='Adobe Sign agreement ID'
    )

    # Agreement details
    agreement_name = models.CharField(max_length=255, help_text='Agreement name visible to signers')
    agreement_message = models.TextField(
        blank=True,
        help_text='Custom message shown to signers'
    )

    # Status tracking
    adobe_status = models.CharField(
        max_length=50,
        choices=AGREEMENT_STATUS_CHOICES,
        default='DRAFT',
        help_text='Current status in Adobe Sign'
    )
    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default='DRAFT',
        help_text='Internal approval workflow status'
    )

    # Signing configuration
    flow_type = models.CharField(
        max_length=30,
        choices=FLOW_TYPE_CHOICES,
        default='director_then_client',
        help_text='Signing flow/order'
    )

    # Recipient configuration
    client_name = models.CharField(max_length=200, blank=True, help_text='Client name')
    client_email = models.EmailField(help_text='Client email address')
    cc_emails = models.TextField(
        blank=True,
        help_text='Comma-separated CC email addresses'
    )

    # Expiration
    days_until_signing_deadline = models.PositiveIntegerField(
        default=30,
        help_text='Number of days before agreement expires'
    )
    expiration_date = models.DateTimeField(null=True, blank=True)

    # Reminders
    reminder_frequency = models.CharField(
        max_length=20,
        choices=[
            ('DAILY_UNTIL_SIGNED', 'Daily Until Signed'),
            ('EVERY_OTHER_DAY', 'Every Other Day'),
            ('EVERY_THIRD_DAY', 'Every Third Day'),
            ('EVERY_FIFTH_DAY', 'Every Fifth Day'),
            ('WEEKLY_UNTIL_SIGNED', 'Weekly Until Signed'),
        ],
        default='EVERY_OTHER_DAY',
        help_text='How often to remind signers'
    )

    # Workflow tracking
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_agreements',
        help_text='User who created this agreement'
    )
    prepared_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prepared_agreements',
        help_text='User who prepared this agreement'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_agreements',
        help_text='Admin who approved this agreement'
    )
    rejection_reason = models.TextField(blank=True)
    rejection_notes = models.TextField(blank=True, help_text='Specific corrections needed')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)  # When submitted for approval
    approved_at = models.DateTimeField(null=True, blank=True)  # When admin approved
    sent_at = models.DateTimeField(null=True, blank=True)  # When sent to client
    completed_at = models.DateTimeField(null=True, blank=True)  # When all signatures collected

    # Signature field data (JSON format)
    signature_field_data = models.TextField(
        blank=True,
        null=True,
        help_text='JSON data for signature field placements'
    )

    # Adobe Sign authoring URL (one-time, stored at agreement creation)
    adobe_authoring_url = models.TextField(blank=True, null=True)

    # Signed document
    signed_document_url = models.URLField(blank=True, null=True)
    signed_document_file = models.FileField(
        upload_to='adobe_sign/signed/',
        blank=True,
        null=True,
        help_text='Downloaded signed document'
    )

    # Audit trail
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last time status was synced from Adobe'
    )
    sync_error = models.TextField(blank=True, help_text='Last sync error if any')

    # ==================== TRACKING FIELDS (Google Sheet Replication) ====================

    # Project Reference (for auto-fill)
    project = models.ForeignKey(
        'projects.ProjectCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adobe_agreements',
        help_text='Link to project for auto-filling agreement details'
    )

    # Vendor Reference
    vendor = models.ForeignKey(
        'supply.VendorCard',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adobe_agreements',
        help_text='Link to vendor (select either project or vendor)'
    )
    vendor_name = models.CharField(
        max_length=200,
        blank=True,
        help_text='Vendor legal name (auto-filled from VendorCard)'
    )

    # Agreement Type and Category (from dropdown master data)
    agreement_type = models.ForeignKey(
        'dropdown_master_data.AgreementType',
        on_delete=models.PROTECT,
        db_column='agreement_type',
        to_field='code',
        null=True,
        blank=True,
        help_text='Type of agreement: Client Agreement, SLA Agreement, Addendum-Client, Addendum-3PL'
    )

    agreement_category = models.ForeignKey(
        'dropdown_master_data.AgreementCategory',
        on_delete=models.PROTECT,
        db_column='agreement_category',
        to_field='code',
        null=True,
        blank=True,
        help_text='Agreement category: New or Renewal'
    )

    # Auto-filled from Project (read-only display fields)
    minimum_billable_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Minimum billable area from ProjectCard (auto-filled)'
    )

    monthly_billable_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Monthly billable amount from ProjectCard (auto-filled)'
    )

    location = models.CharField(
        max_length=100,
        blank=True,
        help_text='Project location from ProjectCode (auto-filled)'
    )

    sales_person = models.CharField(
        max_length=100,
        blank=True,
        help_text='Sales manager from ProjectCode (auto-filled)'
    )

    # Manual tracking fields
    task_undertaken_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='undertaken_agreements',
        help_text='Backoffice user who submitted this agreement (auto-filled on submit)'
    )

    sent_date_director = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Date when backoffice sent to director (auto-filled on submit)'
    )

    sent_date_client_vendor = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Date when director sent to client/vendor (auto-filled when sent)'
    )

    # Manual email fields (already exist as client_email and cc_emails, these are for display)
    to_email = models.EmailField(
        blank=True,
        help_text='Primary recipient email (mirrors client_email)'
    )

    cc_email_list = models.TextField(
        blank=True,
        help_text='CC emails (mirrors cc_emails)'
    )

    # GST Status tracking (from dropdown master data)
    gst_status = models.ForeignKey(
        'dropdown_master_data.GSTStatus',
        on_delete=models.PROTECT,
        db_column='gst_status',
        to_field='code',
        null=True,
        blank=True,
        help_text='GST registration status: Not Registered, Registration Pending, Registered, N/A'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Adobe Agreement'
        verbose_name_plural = 'Adobe Agreements'
        indexes = [
            models.Index(fields=['approval_status', '-created_at']),
            models.Index(fields=['adobe_status']),
            models.Index(fields=['client_email']),
        ]

    def __str__(self):
        return f"{self.agreement_name} - {self.get_approval_status_display()}"

    def get_cc_list(self):
        """Return CC emails as a list"""
        if not self.cc_emails:
            return []
        return [email.strip() for email in self.cc_emails.split(',') if email.strip()]

    def can_edit(self):
        """Check if agreement can be edited"""
        return self.approval_status in ['DRAFT', 'REJECTED']

    def can_submit_for_approval(self):
        """Check if agreement can be submitted for approval"""
        return self.approval_status in ['DRAFT', 'REJECTED']

    def can_approve(self):
        """Check if agreement can be approved"""
        return self.approval_status == 'PENDING_APPROVAL'

    def can_reject(self):
        """Check if agreement can be rejected"""
        return self.approval_status == 'PENDING_APPROVAL'

    def can_recall(self):
        """Check if agreement can be recalled (withdrawn) by backoffice"""
        return (
            self.approval_status == 'PENDING_APPROVAL'
            and self.adobe_status in ['AUTHORING', 'DRAFT']
        )

    def can_recall_from_signing(self):
        """Check if agreement can be recalled after being sent out for signing"""
        return (
            self.approval_status == 'APPROVED_SENT'
            and self.adobe_status in ['OUT_FOR_SIGNATURE', 'IN_PROCESS', 'OUT_FOR_APPROVAL']
        )

    def recall_from_signing(self):
        """Recall agreement from active signing session, return to DRAFT for re-editing."""
        if not self.can_recall_from_signing():
            raise ValidationError('Agreement cannot be recalled from signing in its current state')

        self.approval_status = 'DRAFT'
        self.adobe_status = 'CANCELLED'
        self.adobe_agreement_id = None
        self.adobe_authoring_url = None
        self.submitted_at = None
        self.sent_date_director = None
        self.approved_at = None
        self.approved_by = None
        self.save()

    def recall(self):
        """Recall agreement - withdraw from director review, return to DRAFT."""
        if not self.can_recall():
            raise ValidationError('Agreement cannot be recalled in its current state')

        self.approval_status = 'DRAFT'
        self.adobe_status = 'DRAFT'
        self.adobe_agreement_id = None
        self.adobe_authoring_url = None
        self.submitted_at = None
        self.sent_date_director = None
        self.rejection_reason = ''
        self.rejection_notes = ''
        self.save()

    def submit_for_approval(self, user=None):
        """Submit agreement for admin approval"""
        if not self.can_submit_for_approval():
            raise ValidationError('Agreement cannot be submitted in its current state')

        self.approval_status = 'PENDING_APPROVAL'
        self.submitted_at = timezone.now()
        self.rejection_reason = ''
        self.rejection_notes = ''
        if user:
            self.prepared_by = user
        self.save()

    def approve(self, user=None):
        """Approve agreement"""
        if not self.can_approve():
            raise ValidationError('Agreement cannot be approved in its current state')

        self.approval_status = 'APPROVED_SENT'
        self.approved_at = timezone.now()
        if user:
            self.approved_by = user
        self.save()

    def reject(self, reason, notes='', user=None):
        """Reject agreement and send back for corrections"""
        if not self.can_reject():
            raise ValidationError('Agreement cannot be rejected in its current state')

        self.approval_status = 'REJECTED'
        self.rejection_reason = reason
        self.rejection_notes = notes
        self.save()

    def mark_completed(self):
        """Mark agreement as completed"""
        self.approval_status = 'COMPLETED'
        self.adobe_status = 'COMPLETED'
        self.completed_at = timezone.now()
        self.save()


class Signer(models.Model):
    """
    Signer configuration for an agreement
    Enhanced with role labels and order management
    """
    SIGNER_ROLE_CHOICES = [
        ('SIGNER', 'Signer'),
        ('APPROVER', 'Approver'),
        ('ACCEPTOR', 'Acceptor'),
        ('CERTIFIED_RECIPIENT', 'Certified Recipient'),
        ('FORM_FILLER', 'Form Filler'),
        ('DELEGATE_TO_SIGNER', 'Delegate to Signer'),
        ('DELEGATE_TO_APPROVER', 'Delegate to Approver'),
    ]

    SIGNER_STATUS_CHOICES = [
        ('WAITING_FOR_MY_SIGNATURE', 'Waiting for Signature'),
        ('WAITING_FOR_MY_APPROVAL', 'Waiting for Approval'),
        ('WAITING_FOR_MY_ACCEPTANCE', 'Waiting for Acceptance'),
        ('WAITING_FOR_MY_ACKNOWLEDGEMENT', 'Waiting for Acknowledgement'),
        ('WAITING_FOR_MY_FORM_FILLING', 'Waiting for Form Filling'),
        ('WAITING_FOR_MY_DELEGATION', 'Waiting for Delegation'),
        ('OUT_FOR_SIGNATURE', 'Out for Signature'),
        ('SIGNED', 'Signed'),
        ('APPROVED', 'Approved'),
        ('RECALLED', 'Recalled'),
        ('HIDDEN', 'Hidden'),
        ('NOT_YET_VISIBLE', 'Not Yet Visible'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agreement = models.ForeignKey(AdobeAgreement, on_delete=models.CASCADE, related_name='signers')

    # Signer details
    name = models.CharField(max_length=200, help_text='Signer name')
    email = models.EmailField(help_text='Signer email address')
    role = models.CharField(max_length=50, choices=SIGNER_ROLE_CHOICES, default='SIGNER')
    role_label = models.CharField(
        max_length=100,
        blank=True,
        help_text='Custom label (e.g., "Director", "Client", "Witness")'
    )

    # Signing order
    order = models.PositiveIntegerField(default=1, help_text='Signing order (1 = first)')

    # Status
    status = models.CharField(
        max_length=50,
        choices=SIGNER_STATUS_CHOICES,
        default='NOT_YET_VISIBLE'
    )

    # Signing details
    signed_at = models.DateTimeField(null=True, blank=True)
    signing_url = models.URLField(blank=True, max_length=500)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['agreement', 'order']
        verbose_name = 'Signer'
        verbose_name_plural = 'Signers'

    def __str__(self):
        label = self.role_label or self.get_role_display()
        return f"{self.name} ({label}) - Order {self.order}"


class AgreementEvent(models.Model):
    """
    Audit trail events for agreements
    Synced from Adobe Sign API
    """
    EVENT_TYPE_CHOICES = [
        ('CREATED', 'Agreement Created'),
        ('UPLOADED_BY_SENDER', 'Uploaded by Sender'),
        ('FAXED_BY_SENDER', 'Faxed by Sender'),
        ('PRESIGNED', 'Pre-signed'),
        ('SIGNED', 'Signed'),
        ('ESIGNED', 'E-signed'),
        ('DIGSIGNED', 'Digitally Signed'),
        ('APPROVED', 'Approved'),
        ('OFFLINE_SYNC', 'Offline Sync'),
        ('FAXIN_RECEIVED', 'Fax Received'),
        ('SIGNATURE_REQUESTED', 'Signature Requested'),
        ('APPROVAL_REQUESTED', 'Approval Requested'),
        ('RECALLED', 'Recalled'),
        ('REJECTED', 'Rejected'),
        ('EXPIRED', 'Expired'),
        ('AUTO_CANCELLED_CONVERSION_PROBLEM', 'Auto-Cancelled (Conversion Problem)'),
        ('DOCUMENTS_DELETED', 'Documents Deleted'),
        ('ACTION_DELEGATED', 'Action Delegated'),
        ('ACTION_REPLACED_SIGNER', 'Signer Replaced'),
        ('ACTION_SHARED', 'Action Shared'),
        ('ACTION_COMPLETED', 'Action Completed'),
        ('OTHER', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agreement = models.ForeignKey(AdobeAgreement, on_delete=models.CASCADE, related_name='events')

    # Event details
    event_type = models.CharField(max_length=100, choices=EVENT_TYPE_CHOICES)
    event_date = models.DateTimeField()
    participant_email = models.EmailField(blank=True)
    participant_role = models.CharField(max_length=100, blank=True)
    acting_user_email = models.EmailField(blank=True)
    acting_user_ip = models.GenericIPAddressField(null=True, blank=True)
    description = models.TextField(blank=True)
    comment = models.TextField(blank=True)

    # Webhook idempotency
    adobe_event_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        help_text='Adobe webhook event ID for idempotency'
    )
    raw_payload = models.JSONField(
        blank=True,
        null=True,
        help_text='Raw webhook payload for debugging'
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-event_date']
        verbose_name = 'Agreement Event'
        verbose_name_plural = 'Agreement Events'

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.event_date.strftime('%Y-%m-%d %H:%M')}"


class AdobeSignSettings(models.Model):
    """
    Adobe Sign integration settings.
    Singleton model - only one record should exist.
    Credentials saved here override environment variables.
    """
    id = models.AutoField(primary_key=True)

    # Director details
    director_name = models.CharField(max_length=200, default='Vivek Tiwari')
    director_email = models.EmailField(
        blank=True,
        help_text='Adobe Sign account email used for director signing'
    )
    director_title = models.CharField(max_length=100, default='Director', blank=True)

    # API Credentials (DB takes priority over env vars when set)
    integration_key = models.TextField(
        blank=True,
        default='',
        help_text='Adobe Sign Integration Key — stored encrypted'
    )

    # API Configuration
    api_base_url = models.CharField(
        max_length=500,
        default='https://api.in1.adobesign.com/api/rest/v6',
        help_text='Adobe Sign API base URL (India: api.in1.adobesign.com)'
    )

    # Default settings
    default_expiration_days = models.PositiveIntegerField(
        default=30,
        help_text='Default days until agreement expires'
    )
    default_reminder_frequency = models.CharField(
        max_length=20,
        default='EVERY_OTHER_DAY',
        help_text='Default reminder frequency'
    )

    # Notification settings
    notify_on_signature = models.BooleanField(
        default=True,
        help_text='Send notification when document is signed'
    )
    notify_on_completion = models.BooleanField(
        default=True,
        help_text='Send notification when all signatures collected'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Adobe Sign Settings'
        verbose_name_plural = 'Adobe Sign Settings'

    def __str__(self):
        return f"Adobe Sign Settings - {self.director_email}"

    def save(self, *args, **kwargs):
        # Ensure only one settings record exists
        if not self.pk and AdobeSignSettings.objects.exists():
            raise ValidationError('Adobe Sign Settings already exists. Edit the existing record.')
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        """Get or create settings instance"""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings

    def _get_fernet(self):
        from cryptography.fernet import Fernet
        from django.conf import settings as django_settings
        import base64
        # Use dedicated Adobe Sign encryption key, then fall back to general key, then SECRET_KEY
        if hasattr(django_settings, 'ADOBE_SIGN_ENCRYPTION_KEY') and django_settings.ADOBE_SIGN_ENCRYPTION_KEY:
            key = django_settings.ADOBE_SIGN_ENCRYPTION_KEY.encode()
        elif hasattr(django_settings, 'GMAIL_ENCRYPTION_KEY') and django_settings.GMAIL_ENCRYPTION_KEY:
            key = django_settings.GMAIL_ENCRYPTION_KEY.encode()
        else:
            key = base64.urlsafe_b64encode(
                django_settings.SECRET_KEY[:32].encode().ljust(32)[:32]
            )
        return Fernet(key)

    def get_decrypted_integration_key(self):
        """Return decrypted integration key"""
        if not self.integration_key:
            return ''
        try:
            return self._get_fernet().decrypt(self.integration_key.encode()).decode()
        except Exception:
            return self.integration_key  # Fallback: return as-is (pre-encryption values)

    def set_integration_key(self, value):
        """Encrypt and store integration key"""
        if not value:
            return
        try:
            self.integration_key = self._get_fernet().encrypt(value.encode()).decode()
        except Exception:
            self.integration_key = value
