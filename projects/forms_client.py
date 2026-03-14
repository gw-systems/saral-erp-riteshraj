from django import forms
from .models_client import ClientCard, ClientContact, ClientGST, ClientDocument


class ClientCardForm(forms.ModelForm):
    class Meta:
        model = ClientCard
        fields = [
            'client_legal_name',
            'client_trade_name',
            'client_short_name',
            'client_gst_number',
            'client_cin_number',
            'client_pan_number',
            'client_registered_address',
            'client_corporate_address',
            'client_industry_type',
        ]
        widgets = {
            'client_legal_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Enter full legal name (e.g., Reliance Retail Limited)'
            }),
            'client_trade_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Enter trade name (e.g., Reliance Retail)'
            }),
            'client_short_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Leave blank to auto-generate (first 2 words of legal name)'
            }),
            'client_gst_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': '15-digit GST number (Primary)'
            }),
            'client_cin_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Corporate Identity Number'
            }),
            'client_pan_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': '10-character PAN'
            }),
            'client_registered_address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Legal/GST registered address',
                'rows': 3
            }),
            'client_corporate_address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Corporate/operational HQ address',
                'rows': 3
            }),
            'client_industry_type': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'e.g., FMCG, Pharma, Auto, E-commerce'
            }),
        }
        labels = {
            'client_legal_name': 'Legal Name *',
            'client_trade_name': 'Trade Name',
            'client_short_name': 'Short Name (Optional)',
            'client_gst_number': 'GST Number (Primary)',
            'client_cin_number': 'CIN Number',
            'client_pan_number': 'PAN Number',
            'client_registered_address': 'Registered Address',
            'client_corporate_address': 'Corporate Address',
            'client_industry_type': 'Industry Type',
        }


class ClientContactForm(forms.ModelForm):
    class Meta:
        model = ClientContact
        fields = [
            'client_contact_person',
            'client_contact_designation',
            'client_contact_department',
            'client_contact_phone',
            'client_contact_email',
            'client_contact_is_primary',
        ]
        widgets = {
            'client_contact_person': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'Contact person name'
            }),
            'client_contact_designation': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'Designation'
            }),
            'client_contact_department': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'Department'
            }),
            'client_contact_phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'Phone number'
            }),
            'client_contact_email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'Email address'
            }),
            'client_contact_is_primary': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-blue-600 rounded'
            }),
        }


class ClientGSTForm(forms.ModelForm):
    class Meta:
        model = ClientGST
        fields = [
            'client_gst_legal_entity_name',
            'client_gst_number',
            'client_gst_state_name',
            'client_gst_registered_address',
            'client_gst_is_primary',
        ]
        widgets = {
            'client_gst_legal_entity_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'Legal entity name for this GST'
            }),
            'client_gst_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': '15-digit GST number'
            }),
            'client_gst_state_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'State of registration'
            }),
            'client_gst_registered_address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'Registered address for this GST',
                'rows': 3
            }),
            'client_gst_is_primary': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-blue-600 rounded'
            }),
        }
        labels = {
            'client_gst_legal_entity_name': 'Legal Entity Name',
            'client_gst_number': 'GST Number *',
            'client_gst_state_name': 'State',
            'client_gst_registered_address': 'Registered Address',
            'client_gst_is_primary': 'Primary GST',
        }


class ClientDocumentForm(forms.ModelForm):
    class Meta:
        model = ClientDocument
        fields = [
            'client_doc_certificate_of_incorporation',
            'client_doc_board_resolution',
            'client_doc_authorized_signatory',
        ]
        widgets = {
            'client_doc_certificate_of_incorporation': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'client_doc_board_resolution': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'client_doc_authorized_signatory': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
        }
        labels = {
            'client_doc_certificate_of_incorporation': 'Certificate of Incorporation',
            'client_doc_board_resolution': 'Board Resolution',
            'client_doc_authorized_signatory': 'Authorized Signatory Details',
        }