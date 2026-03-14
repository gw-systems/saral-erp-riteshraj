"""
Adobe Sign Forms
Enhanced forms for improved signature placement workflow
"""

from django import forms
from .models import DocumentTemplate, Document, AdobeAgreement, Signer, AdobeSignSettings
from projects.models import ProjectCode
from supply.models import VendorCard


class DocumentTemplateForm(forms.ModelForm):
    """Form for creating/editing document templates"""

    class Meta:
        model = DocumentTemplate
        fields = [
            'name',
            'template_type',
            'description',
            'template_file',
            'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Standard NDA Template'
            }),
            'template_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe when to use this template...'
            }),
            'template_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf'
            }),
        }

    def clean_template_file(self):
        """Validate template file"""
        file = self.cleaned_data.get('template_file')
        if file:
            if not file.name.lower().endswith('.pdf'):
                raise forms.ValidationError('Only PDF files are allowed for templates')
            if file.size > 10 * 1024 * 1024:  # 10 MB limit
                raise forms.ValidationError('Template file size must be under 10 MB')
        return file


class DocumentUploadForm(forms.ModelForm):
    """Form for uploading documents"""

    template = forms.ModelChoiceField(
        queryset=DocumentTemplate.objects.filter(is_active=True),
        required=False,
        empty_label='-- No Template (Upload Custom Document) --',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Select a template to auto-place signature fields'
    )

    class Meta:
        model = Document
        fields = ['file', 'template']
        widgets = {
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.docx'
            }),
        }

    def clean_file(self):
        """Validate uploaded file"""
        file = self.cleaned_data.get('file')
        if file:
            ext = file.name.lower().split('.')[-1]
            if ext not in ['pdf', 'docx']:
                raise forms.ValidationError('Only PDF and DOCX files are allowed')
            if file.size > 10 * 1024 * 1024:  # 10 MB limit
                raise forms.ValidationError('File size must be under 10 MB')
        return file


class AgreementCreateForm(forms.ModelForm):
    """
    Enhanced form for creating agreements
    Project and Vendor are optional but at least one must be selected.
    Agreement Type and Category are mandatory.
    """

    # Project selection dropdown (searchable) - OPTIONAL (only WAAS projects)
    project = forms.ModelChoiceField(
        queryset=ProjectCode.objects.filter(
            project_status__in=['Active', 'Operation Not Started'],
            series_type='WAAS'
        ).select_related('client_card').order_by('client_name', 'project_id'),
        required=False,
        empty_label='-- Select Project (Optional) --',
        widget=forms.Select(attrs={
            'class': 'w-full searchable-select border border-gray-300 rounded-lg',
            'id': 'project-select'
        }),
        label='Project',
        help_text='Select associated project'
    )

    # Vendor selection dropdown (searchable) - OPTIONAL
    vendor = forms.ModelChoiceField(
        queryset=VendorCard.objects.filter(
            vendor_is_active=True
        ).order_by('vendor_legal_name'),
        required=False,
        empty_label='-- Select Vendor (Optional) --',
        widget=forms.Select(attrs={
            'class': 'w-full searchable-select border border-gray-300 rounded-lg',
            'id': 'vendor-select'
        }),
        label='Vendor Name',
        help_text='Select vendor if this is a vendor agreement'
    )

    # File upload
    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'w-full form-control border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'accept': '.pdf',
            'id': 'file-upload'
        }),
        label='Upload PDF Document',
        help_text='PDF format only (max 10MB)'
    )

    # Signature fields data (hidden field)
    signature_fields = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )

    # Simplified flow type - only 2 options
    SIMPLIFIED_FLOW_CHOICES = [
        ('director_then_client', 'Director signs first, then Client'),
        ('client_only', 'Client Only'),
    ]

    flow_type = forms.ChoiceField(
        choices=SIMPLIFIED_FLOW_CHOICES,
        initial='director_then_client',
        widget=forms.Select(attrs={'class': 'w-full form-select border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white'}),
        label='Signing Flow',
        help_text='Who needs to sign this agreement?'
    )

    class Meta:
        model = AdobeAgreement
        fields = [
            'agreement_type',
            'agreement_category',
            'client_email',
            'cc_emails',
            'flow_type',
            'agreement_message',
            'days_until_signing_deadline',
        ]
        widgets = {
            'agreement_type': forms.Select(attrs={
                'class': 'w-full form-select border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white',
                'id': 'agreement-type'
            }),
            'agreement_category': forms.Select(attrs={
                'class': 'w-full form-select border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white',
                'id': 'agreement-category'
            }),
            'client_email': forms.EmailInput(attrs={
                'class': 'w-full form-control border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'client@example.com',
                'id': 'client-email'
            }),
            'agreement_message': forms.Textarea(attrs={
                'class': 'w-full form-control border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'rows': 3,
                'placeholder': 'Optional message shown to signers...'
            }),
            'cc_emails': forms.Textarea(attrs={
                'class': 'w-full form-control border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'rows': 2,
                'placeholder': 'email1@example.com, email2@example.com'
            }),
            'days_until_signing_deadline': forms.NumberInput(attrs={
                'class': 'w-full form-control border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'min': 1,
                'max': 180,
                'value': 30
            }),
        }
        labels = {
            'agreement_type': 'Agreement Type',
            'agreement_category': 'New or Renewal',
            'client_email': 'Client/Vendor Email (TO)',
            'cc_emails': 'CC Emails (Optional)',
            'agreement_message': 'Message to Signers (Optional)',
            'days_until_signing_deadline': 'Expires in (Days)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Customize project field display
        self.fields['project'].label_from_instance = lambda obj: obj.project_code
        # Customize vendor field display
        self.fields['vendor'].label_from_instance = lambda obj: obj.vendor_legal_name
        # Make agreement_type and agreement_category required
        self.fields['agreement_type'].required = True
        self.fields['agreement_category'].required = True

    def clean_file(self):
        """Validate uploaded file"""
        file = self.cleaned_data.get('file')
        if file:
            if not file.name.lower().endswith('.pdf'):
                raise forms.ValidationError('Only PDF files are allowed')
            if file.size > 10 * 1024 * 1024:  # 10 MB limit
                raise forms.ValidationError('File size must be under 10 MB')
        return file

    def clean_signature_fields(self):
        """Validate signature fields are placed"""
        signature_fields_json = self.cleaned_data.get('signature_fields', '')
        if signature_fields_json:
            import json
            try:
                fields = json.loads(signature_fields_json)
                if not isinstance(fields, list) or len(fields) == 0:
                    raise forms.ValidationError('At least one signature field must be placed on the document')
                return signature_fields_json
            except json.JSONDecodeError:
                raise forms.ValidationError('Invalid signature field data')
        else:
            raise forms.ValidationError('At least one signature field must be placed on the document before submitting')

    def clean_cc_emails(self):
        """Validate CC emails"""
        cc_emails = self.cleaned_data.get('cc_emails', '')
        if cc_emails:
            emails = [e.strip() for e in cc_emails.split(',') if e.strip()]
            for email in emails:
                if '@' not in email or '.' not in email.split('@')[1]:
                    raise forms.ValidationError(f'Invalid email format: {email}')
            # Check for duplicates
            if len(emails) != len(set(emails)):
                raise forms.ValidationError('Duplicate email addresses found in CC list')
        return cc_emails

    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()

        # At least one of project or vendor must be selected
        project = cleaned_data.get('project')
        vendor = cleaned_data.get('vendor')
        if not project and not vendor:
            raise forms.ValidationError(
                'Please select at least one: a Project or a Vendor.'
            )

        # CC emails must not duplicate client email
        client_email = cleaned_data.get('client_email', '').strip().lower()
        cc_emails = cleaned_data.get('cc_emails', '')

        if cc_emails and client_email:
            cc_list = [e.strip().lower() for e in cc_emails.split(',') if e.strip()]
            if client_email in cc_list:
                raise forms.ValidationError({
                    'cc_emails': 'Client email cannot be in CC list (already in TO field)'
                })

        return cleaned_data


class AgreementEditForm(forms.ModelForm):
    """Form for editing draft/rejected agreements"""

    class Meta:
        model = AdobeAgreement
        fields = [
            'agreement_name',
            'agreement_message',
            'client_name',
            'client_email',
            'cc_emails',
            'days_until_signing_deadline',
            'reminder_frequency'
        ]
        widgets = {
            'agreement_name': forms.TextInput(attrs={'class': 'form-control'}),
            'agreement_message': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'client_name': forms.TextInput(attrs={'class': 'form-control'}),
            'client_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'cc_emails': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'days_until_signing_deadline': forms.NumberInput(attrs={'class': 'form-control'}),
            'reminder_frequency': forms.Select(attrs={'class': 'form-select'}),
        }


class AgreementRejectForm(forms.Form):
    """Form for rejecting agreements"""

    rejection_reason = forms.ChoiceField(
        choices=[
            ('incorrect_info', 'Incorrect Information'),
            ('wrong_document', 'Wrong Document'),
            ('missing_details', 'Missing Details'),
            ('formatting_issues', 'Formatting Issues'),
            ('signature_fields_wrong', 'Signature Fields Incorrectly Placed'),
            ('other', 'Other (specify in notes)'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='Rejection Reason'
    )

    rejection_notes = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Optional: Provide specific details about what needs to be corrected...'
        }),
        label='Additional Notes',
        help_text='Optional: Add specific instructions for backoffice',
        required=False
    )


class DocumentReplaceForm(forms.Form):
    """Form for replacing document in rejected agreements"""

    new_document = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.docx'
        }),
        label='Corrected Document',
        help_text='Upload the corrected document (PDF or DOCX)'
    )

    def clean_new_document(self):
        """Validate replacement document"""
        file = self.cleaned_data.get('new_document')
        if file:
            ext = file.name.lower().split('.')[-1]
            if ext not in ['pdf', 'docx']:
                raise forms.ValidationError('Only PDF and DOCX files are allowed')
            if file.size > 10 * 1024 * 1024:  # 10 MB
                raise forms.ValidationError('File size must be under 10 MB')
        return file


class SignerForm(forms.ModelForm):
    """Form for adding/editing signers"""

    class Meta:
        model = Signer
        fields = ['name', 'email', 'role', 'role_label', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'role_label': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Director, Client, Witness'
            }),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }
        help_texts = {
            'role_label': 'Custom label shown to other signers',
            'order': 'Signing order (1 = signs first)',
        }


class AdobeSignSettingsForm(forms.ModelForm):
    """Form for Adobe Sign settings (director information + integration key)"""

    class Meta:
        model = AdobeSignSettings
        fields = ['integration_key', 'director_name', 'director_email', 'director_title']
        widgets = {
            'integration_key': forms.PasswordInput(attrs={
                'class': 'form-control border border-gray-300 rounded-md font-mono text-sm',
                'placeholder': 'Paste your Adobe Sign Integration Key here',
                'autocomplete': 'off',
            }),
            'director_name': forms.TextInput(attrs={
                'class': 'w-full form-control border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'e.g., Vivek Tiwari'
            }),
            'director_email': forms.EmailInput(attrs={
                'class': 'w-full form-control border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'director@company.com'
            }),
            'director_title': forms.TextInput(attrs={
                'class': 'w-full form-control border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'e.g., Managing Director'
            }),
        }
