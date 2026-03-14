"""
Quotation Forms
Forms for quotation CRUD operations
"""

from django import forms
from django.forms import inlineformset_factory
from projects.models_quotation import Quotation, QuotationLocation, QuotationItem, QuotationProduct
from projects.models_quotation_settings import QuotationSettings
from decimal import Decimal, InvalidOperation

INPUT_CLASSES = 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'
SELECT_CLASSES = 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'
TEXTAREA_CLASSES = 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none'


class QuotationForm(forms.ModelForm):
    """
    Main quotation form with MANUAL CLIENT ENTRY fields.
    No ClientCard dropdown - users enter client details manually.
    Includes scope of service, T&C, and all new fields from Godamwale template.
    """

    # Checkbox field for "same as billing address"
    same_as_billing = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
        })
    )

    class Meta:
        model = Quotation
        fields = [
            # Manual client entry fields
            'client_name',
            'client_company',
            'client_email',
            'client_phone',
            'billing_address',
            'shipping_address',
            'client_gst_number',
            # Quotation details
            'validity_period',
            'gst_rate',
            # Commercial table settings
            'commercial_type',
            'default_markup_pct',
            # Operational Scope
            'operational_total_boxes',
            'operational_variance_pct',
            'operational_pallet_l',
            'operational_pallet_w',
            'operational_pallet_h',
            # Terms & Conditions
            'payment_terms',
            'sla_terms',
            'contract_terms',
            'liability_terms',
            # Branding
            'company_tagline',
            'for_godamwale_signatory',
        ]
        widgets = {
            'client_name': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'Contact person name',
                'required': True
            }),
            'client_company': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'Company/organization name',
                'required': True
            }),
            'client_email': forms.EmailInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'client@example.com',
                'required': True
            }),
            'client_phone': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': '+91 XXXXX XXXXX'
            }),
            'billing_address': forms.Textarea(attrs={
                'class': TEXTAREA_CLASSES,
                'placeholder': 'Billing address',
                'rows': '3',
                'required': True
            }),
            'shipping_address': forms.Textarea(attrs={
                'class': TEXTAREA_CLASSES,
                'placeholder': 'Shipping address (leave blank if same as billing)',
                'rows': '3'
            }),
            'client_gst_number': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': '22AAAAA0000A1Z5 (optional)'
            }),
            'validity_period': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'min': '1',
                'max': '365',
            }),
            'gst_rate': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.01',
                'min': '0',
                'max': '100',
            }),
            'commercial_type': forms.Select(attrs={
                'class': SELECT_CLASSES,
                'id': 'id_commercial_type',
            }),
            'default_markup_pct': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.01',
                'min': '0',
                'max': '1000',
                'id': 'id_default_markup_pct',
            }),
            'payment_terms': forms.Textarea(attrs={
                'class': TEXTAREA_CLASSES,
                'rows': '5',
                'placeholder': 'Leave blank to use default from settings'
            }),
            'sla_terms': forms.Textarea(attrs={
                'class': TEXTAREA_CLASSES,
                'rows': '5',
                'placeholder': 'Leave blank to use default from settings'
            }),
            'contract_terms': forms.Textarea(attrs={
                'class': TEXTAREA_CLASSES,
                'rows': '4',
                'placeholder': 'Leave blank to use default from settings'
            }),
            'liability_terms': forms.Textarea(attrs={
                'class': TEXTAREA_CLASSES,
                'rows': '5',
                'placeholder': 'Leave blank to use default from settings'
            }),
            'company_tagline': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
            }),
            'for_godamwale_signatory': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
            }),
            'operational_total_boxes': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '1', 'min': '1',
                'placeholder': 'Total boxes to be stored'
            }),
            'operational_variance_pct': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.01', 'min': '0', 'max': '100',
            }),
            'operational_pallet_l': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.001', 'min': '0.001',
            }),
            'operational_pallet_w': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.001', 'min': '0.001',
            }),
            'operational_pallet_h': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.001', 'min': '0.001',
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        settings = QuotationSettings.get_settings()

        # Set defaults from QuotationSettings for new quotations
        if not self.instance.pk:  # New quotation
            self.fields['validity_period'].initial = settings.default_validity_days
            self.fields['gst_rate'].initial = settings.default_gst_rate
            self.fields['payment_terms'].initial = settings.default_payment_terms
            self.fields['sla_terms'].initial = settings.default_sla_terms
            self.fields['contract_terms'].initial = settings.default_contract_terms
            self.fields['liability_terms'].initial = settings.default_liability_terms

            # Pre-fill signatory from the creating user's ERP profile
            if user:
                full_name = user.get_full_name() or user.username
                phone = getattr(user, 'phone', '') or ''
                self.fields['for_godamwale_signatory'].initial = (
                    f"{full_name} [{phone}]" if phone else full_name
                )

        # Fields not rendered in template — use model defaults if blank
        self.fields['company_tagline'].required = False
        self.fields['for_godamwale_signatory'].required = False

        # NOTE: scope_of_service checkboxes removed; replaced by
        # QuotationProduct rows in the Operational Scope section.


class QuotationLocationForm(forms.ModelForm):
    """Form for quotation locations."""

    class Meta:
        model = QuotationLocation
        fields = ['location_name', 'order']
        widgets = {
            'location_name': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'e.g., Mumbai Warehouse, Delhi DC',
                'required': True
            }),
            'order': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'min': '0',
                'value': '0'
            }),
        }


class QuotationItemForm(forms.ModelForm):
    """Form for quotation line items (client + vendor commercials)."""

    class Meta:
        model = QuotationItem
        fields = [
            'item_description',
            'custom_description',
            'unit_cost',
            'quantity',
            'vendor_unit_cost',
            'vendor_quantity',
            'storage_unit_type',
            'order',
        ]
        widgets = {
            'item_description': forms.Select(attrs={
                'class': SELECT_CLASSES
            }),
            'custom_description': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'Optional custom description...'
            }),
            'unit_cost': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'Enter rate or "at actual"'
            }),
            'quantity': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'Enter quantity or "as applicable"'
            }),
            'vendor_unit_cost': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'Vendor rate or "at actual"'
            }),
            'vendor_quantity': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'Vendor qty or "as applicable"'
            }),
            'storage_unit_type': forms.Select(attrs={
                'class': SELECT_CLASSES
            }),
            'order': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'min': '0',
                'value': '0'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit_cost'].required = False
        self.fields['quantity'].required = False
        self.fields['vendor_unit_cost'].required = False
        self.fields['vendor_quantity'].required = False

    # ------------------------------------------------------------------ #
    # Client cost cleaning                                                 #
    # ------------------------------------------------------------------ #

    def clean_unit_cost(self):
        cost = self.cleaned_data.get('unit_cost', '').strip()
        if not cost or cost in ('0', '0.00'):
            return 'at actual'
        if cost.lower() in ('at actual', 'as applicable'):
            return 'at actual'
        try:
            cost_decimal = Decimal(str(cost))
            if cost_decimal < 0:
                raise forms.ValidationError('Unit cost must be positive')
            return str(cost_decimal)
        except (ValueError, InvalidOperation):
            raise forms.ValidationError('Enter a valid number or "at actual"')

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity', '').strip()
        if not qty or qty in ('0', '0.00'):
            return 'at actual'
        if qty.lower() in ('at actual', 'as applicable'):
            return 'at actual'
        try:
            qty_decimal = Decimal(str(qty))
            if qty_decimal <= 0:
                return 'at actual'
            return str(qty_decimal)
        except (ValueError, InvalidOperation):
            raise forms.ValidationError('Enter a valid number or "at actual"')

    # ------------------------------------------------------------------ #
    # Vendor cost cleaning (same logic)                                    #
    # ------------------------------------------------------------------ #

    def clean_vendor_unit_cost(self):
        cost = self.cleaned_data.get('vendor_unit_cost', '').strip()
        if not cost or cost in ('0', '0.00'):
            return 'at actual'
        if cost.lower() in ('at actual', 'as applicable'):
            return 'at actual'
        try:
            cost_decimal = Decimal(str(cost))
            if cost_decimal < 0:
                raise forms.ValidationError('Vendor unit cost must be positive')
            return str(cost_decimal)
        except (ValueError, InvalidOperation):
            raise forms.ValidationError('Enter a valid number or "at actual"')

    def clean_vendor_quantity(self):
        qty = self.cleaned_data.get('vendor_quantity', '').strip()
        if not qty or qty in ('0', '0.00'):
            return 'at actual'
        if qty.lower() in ('at actual', 'as applicable'):
            return 'at actual'
        try:
            qty_decimal = Decimal(str(qty))
            if qty_decimal <= 0:
                return 'at actual'
            return str(qty_decimal)
        except (ValueError, InvalidOperation):
            raise forms.ValidationError('Enter a valid number or "at actual"')


class QuotationSettingsForm(forms.ModelForm):
    """
    Form for configuring quotation system settings via frontend UI.
    Includes Google Docs template URL and OAuth 2.0 credentials.
    """

    # Add plaintext field for client_secret input (will be encrypted on save)
    client_secret_plaintext = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASSES,
            'placeholder': 'Enter Client Secret (will be encrypted)'
        }),
        help_text='Leave blank to keep existing secret'
    )

    class Meta:
        model = QuotationSettings
        fields = [
            'google_docs_template_url',
            'client_id',
            'redirect_uri',
            'default_gst_rate',
            'default_validity_days',
            'email_subject_template',
            'email_body_template',
        ]
        widgets = {
            'google_docs_template_url': forms.URLInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'https://docs.google.com/document/d/DOCUMENT_ID/edit'
            }),
            'client_id': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'Google OAuth 2.0 Client ID'
            }),
            'redirect_uri': forms.URLInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'https://yourdomain.com/projects/quotations/oauth-callback/'
            }),
            'default_gst_rate': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'default_validity_days': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'min': '1',
                'max': '365'
            }),
            'email_subject_template': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'Use {quotation_number}, {client_company}, {date}'
            }),
            'email_body_template': forms.Textarea(attrs={
                'class': TEXTAREA_CLASSES,
                'rows': '10',
                'placeholder': 'Use {client_name}, {quotation_number}, {validity_date}, {created_by_name}'
            }),
        }
        help_texts = {
            'google_docs_template_url': 'Paste the full URL of your Google Docs quotation template',
            'client_id': 'Google OAuth 2.0 Client ID from Google Cloud Console',
            'redirect_uri': 'OAuth 2.0 redirect URI (must match Google Cloud Console)',
            'email_subject_template': 'Available placeholders: {quotation_number}, {client_company}, {date}',
            'email_body_template': 'Available placeholders: {client_name}, {quotation_number}, {validity_date}, {created_by_name}',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show masked client secret if exists
        if self.instance and self.instance.client_secret:
            self.fields['client_secret_plaintext'].widget.attrs['placeholder'] = '••••••••••••••••'

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Handle client_secret encryption
        client_secret_plaintext = self.cleaned_data.get('client_secret_plaintext')
        if client_secret_plaintext:
            instance.set_client_secret(client_secret_plaintext)

        if commit:
            instance.save()
        return instance


class EmailQuotationForm(forms.Form):
    """
    Form for sending quotation emails via Gmail API.
    Uses existing gmail app's EmailService.
    """

    sender_email = forms.ChoiceField(
        label='Send From',
        widget=forms.Select(attrs={
            'class': SELECT_CLASSES,
            'required': True
        }),
        help_text='Select your connected Gmail account'
    )

    recipient_email = forms.EmailField(
        label='Recipient Email',
        widget=forms.EmailInput(attrs={
            'class': INPUT_CLASSES,
            'required': True
        })
    )

    cc_emails = forms.CharField(
        label='CC Emails (comma-separated)',
        required=False,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASSES,
            'placeholder': 'email1@example.com, email2@example.com'
        })
    )

    custom_message = forms.CharField(
        label='Custom Message (optional)',
        required=False,
        widget=forms.Textarea(attrs={
            'class': TEXTAREA_CLASSES,
            'rows': '6',
            'placeholder': 'Leave blank to use default template from settings'
        })
    )

    def __init__(self, user, quotation, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Get available sender accounts from gmail app
        from gmail.services import EmailService
        available_accounts = EmailService.get_available_sender_accounts(user)

        self.fields['sender_email'].choices = [
            (account.email_account, f"{account.email_account} ({account.user.get_full_name()})")
            for account in available_accounts
        ]

        # Pre-populate recipient email from quotation
        self.fields['recipient_email'].initial = quotation.client_email

        if not available_accounts.exists():
            self.fields['sender_email'].help_text = 'No Gmail accounts connected. Please connect a Gmail account first.'

    def clean_cc_emails(self):
        """Validate CC emails."""
        cc_emails_str = self.cleaned_data.get('cc_emails', '')
        if not cc_emails_str.strip():
            return []

        emails = [email.strip() for email in cc_emails_str.split(',')]

        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as DjangoValidationError

        validated_emails = []
        for email in emails:
            if email:
                try:
                    validate_email(email)
                    validated_emails.append(email)
                except DjangoValidationError:
                    raise forms.ValidationError(f"Invalid email address: {email}")

        return validated_emails


# Inline formsets for nested location/item creation
QuotationLocationFormSet = inlineformset_factory(
    Quotation,
    QuotationLocation,
    form=QuotationLocationForm,
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True,
    max_num=50,
    validate_max=True,
)

QuotationItemFormSet = inlineformset_factory(
    QuotationLocation,
    QuotationItem,
    form=QuotationItemForm,
    extra=0,
    can_delete=True,
    max_num=50,
    validate_max=True,
)


class QuotationProductForm(forms.ModelForm):
    """Form for each product/SKU in the Operational Scope section."""

    class Meta:
        model = QuotationProduct
        fields = [
            'product_name', 'type_of_business', 'type_of_operation',
            'packaging_type', 'avg_weight_kg',
            'dim_l', 'dim_w', 'dim_h', 'dim_unit',
            'share_pct', 'order',
        ]
        widgets = {
            'product_name': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'e.g. Baby Diapers, Electronics',
                'required': True
            }),
            'type_of_business': forms.Select(attrs={'class': SELECT_CLASSES}),
            'type_of_operation': forms.Select(attrs={'class': SELECT_CLASSES}),
            'packaging_type': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'e.g. Carton, Polybag, Drum'
            }),
            'avg_weight_kg': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.01', 'min': '0', 'placeholder': 'kg'
            }),
            'dim_l': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.0001', 'min': '0.0001', 'placeholder': 'Length'
            }),
            'dim_w': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.0001', 'min': '0.0001', 'placeholder': 'Width'
            }),
            'dim_h': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.0001', 'min': '0.0001', 'placeholder': 'Height'
            }),
            'dim_unit': forms.Select(attrs={'class': SELECT_CLASSES}),
            'share_pct': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.01', 'min': '0', 'max': '100', 'placeholder': '100'
            }),
            'order': forms.NumberInput(attrs={
                'class': INPUT_CLASSES + ' w-16', 'min': '0', 'value': '0'
            }),
        }

    def clean_share_pct(self):
        val = self.cleaned_data.get('share_pct')
        if val is not None and (val < 0 or val > 100):
            raise forms.ValidationError('Share % must be between 0 and 100.')
        return val

    def clean(self):
        cleaned = super().clean()
        for field in ('dim_l', 'dim_w', 'dim_h'):
            val = cleaned.get(field)
            if val is not None and val <= 0:
                self.add_error(field, 'Dimension must be greater than zero.')
        return cleaned


QuotationProductFormSet = inlineformset_factory(
    Quotation,
    QuotationProduct,
    form=QuotationProductForm,
    extra=0,
    can_delete=True,
    min_num=0,
    max_num=20,
)
