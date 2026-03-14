"""
Supply Chain Management Forms
"""

from django import forms
from django.forms import inlineformset_factory

from .models import (
    VendorCard,
    VendorContact,
    VendorWarehouse,
    WarehouseProfile,
    WarehouseCapacity,
    WarehouseCommercial,
    WarehouseContact,
    VendorWarehouseDocument,
    WarehousePhoto,
    Location
)

from dropdown_master_data.models import Region, StateCode
from supply.models import CityCode

# ============================================================================
# VENDOR CARD FORMS
# ============================================================================

class VendorCardForm(forms.ModelForm):
    """Form for creating/editing vendor cards"""
    
    class Meta:
        model = VendorCard
        fields = [
            'vendor_short_name',
            'vendor_legal_name',
            'vendor_trade_name',
            'vendor_pan',
            'vendor_gstin',
            'vendor_cin_number',
            'vendor_registered_address',
            'vendor_corporate_address',
            'vendor_is_active',
        ]
        widgets = {
            'vendor_short_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'Short name',
                'required': True
            }),
            'vendor_legal_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'Full legal name',
                'required': True
            }),
            'vendor_trade_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'Trade name (optional)'
            }),
            'vendor_pan': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'e.g., ABCDE1234F',
                'maxlength': '10',
                'style': 'text-transform: uppercase;'
            }),
            'vendor_gstin': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'e.g., 27ABCDE1234F1Z5',
                'maxlength': '15',
                'style': 'text-transform: uppercase;'
            }),
            'vendor_cin_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'e.g., U12345MH2020PTC123456',
                'maxlength': '21',
                'style': 'text-transform: uppercase;'
            }),
            'vendor_registered_address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'Full registered address',
                'rows': 3,
                'required': True
            }),
            'vendor_corporate_address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'Corporate office address (leave blank if same as registered)',
                'rows': 3
            }),
            'vendor_is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500'
            }),
        }
        labels = {
            'vendor_short_name': 'Short Name',
            'vendor_legal_name': 'Legal Name',
            'vendor_trade_name': 'Trade Name',
            'vendor_pan': 'PAN Number',
            'vendor_gstin': 'GSTIN',
            'vendor_cin_number': 'CIN Number',
            'vendor_registered_address': 'Registered Address',
            'vendor_corporate_address': 'Corporate Address',
            'vendor_is_active': 'Active Status',
        }
        help_texts = {   
            'vendor_pan': '10-character PAN number',
            'vendor_gstin': '15-character GSTIN',
            'vendor_cin_number': 'Corporate Identification Number (21 characters)',
        }

    def clean_vendor_code(self):
        """Validate and format vendor code"""
        vendor_code = self.cleaned_data.get('vendor_code') # Get it from cleaned_data first
        if vendor_code:
            vendor_code = vendor_code.upper().strip()

    def clean_vendor_pan(self):
        """Validate PAN format"""
        pan = self.cleaned_data.get('vendor_pan')
        if pan:
            pan = pan.upper().strip()
            if len(pan) != 10:
                raise forms.ValidationError('PAN must be exactly 10 characters')
            # Basic PAN format validation: 5 letters + 4 digits + 1 letter
            if not (pan[:5].isalpha() and pan[5:9].isdigit() and pan[9].isalpha()):
                raise forms.ValidationError('Invalid PAN format (should be: ABCDE1234F)')
        return pan

    def clean_vendor_gstin(self):
        """Validate GSTIN format"""
        gstin = self.cleaned_data.get('vendor_gstin')
        if gstin:
            gstin = gstin.upper().strip()
            if len(gstin) != 15:
                raise forms.ValidationError('GSTIN must be exactly 15 characters')
        return gstin

    def clean_vendor_cin_number(self):
        """Validate CIN format"""
        cin = self.cleaned_data.get('vendor_cin_number')
        if cin:
            cin = cin.upper().strip()
            if len(cin) != 21:
                raise forms.ValidationError('CIN must be exactly 21 characters')
        return cin


class VendorContactForm(forms.ModelForm):
    """Form for vendor contact persons"""
    
    class Meta:
        model = VendorContact
        fields = [
            'vendor_contact_person',
            'vendor_contact_designation',
            'vendor_contact_department',
            'vendor_contact_phone',
            'vendor_contact_email',
            'vendor_contact_is_primary',
            'vendor_contact_is_active'
        ]
        widgets = {
            'vendor_contact_person': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Full name'
            }),
            'vendor_contact_designation': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Designation/Role'
            }),
            'vendor_contact_department': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Department'
            }),
            'vendor_contact_phone': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Phone number',
                'maxlength': '15'
            }),
            'vendor_contact_email': forms.EmailInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'email@example.com'
            }),
            'vendor_contact_is_primary': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500'
            }),
            'vendor_contact_is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500'
            })
        }
        labels = {
            'vendor_contact_person': 'Contact Person',
            'vendor_contact_designation': 'Designation',
            'vendor_contact_department': 'Department',
            'vendor_contact_phone': 'Phone Number',
            'vendor_contact_email': 'Email',
            'vendor_contact_is_primary': 'Primary Contact',
            'vendor_contact_is_active': 'Active',
        }

    def clean_vendor_contact_phone(self):
        """Validate phone number"""
        phone = self.cleaned_data.get('vendor_contact_phone')
        if phone:
            phone = ''.join(filter(str.isdigit, phone))
            if len(phone) < 10:
                raise forms.ValidationError('Phone number must be at least 10 digits')
        return phone
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False


# Create formset for vendor contacts
VendorContactFormSet = inlineformset_factory(
    VendorCard,
    VendorContact,
    form=VendorContactForm,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
    fk_name='vendor_code'
)


# ============================================================================
# WAREHOUSE FORMS
# ============================================================================

class VendorWarehouseForm(forms.ModelForm):
    """Form for creating/editing warehouses"""
    
    class Meta:
        model = VendorWarehouse
        fields = [
            'vendor_code',
            'warehouse_name',
            'warehouse_digipin',
            'warehouse_address',
            'warehouse_pincode',
            'warehouse_location_id',
            'warehouse_owner_name',
            'warehouse_owner_contact',
            'google_map_location',
            'warehouse_is_active'
        ]
        widgets = {
            'vendor_code': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'required': True
            }),
            'warehouse_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Warehouse name'
            }),
            'warehouse_digipin': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Digipin code'
            }),
            'warehouse_address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'rows': 3,
                'placeholder': 'Full warehouse address'
            }),
            'warehouse_pincode': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': '6-digit pincode',
                'maxlength': '6'
            }),
            'warehouse_location_id': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500'
            }),
            'warehouse_owner_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Owner name'
            }),
            'warehouse_owner_contact': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Owner contact number',
                'maxlength': '15'
            }),
            'google_map_location': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Google Maps URL'
            }),
            'warehouse_is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500'
            })
        }
        labels = {
            'vendor_code': 'Vendor',
            'warehouse_name': 'Warehouse Name',
            'warehouse_digipin': 'Digipin',
            'warehouse_address': 'Address',
            'warehouse_pincode': 'Pincode',
            'warehouse_location_id': 'Location',
            'warehouse_owner_name': 'Owner Name',
            'warehouse_owner_contact': 'Owner Contact',
            'google_map_location': 'Google Maps Link',
            'warehouse_is_active': 'Active',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vendor_code'].queryset = VendorCard.objects.filter(
            vendor_is_active=True
        ).order_by('vendor_short_name')
        
        self.fields['warehouse_location_id'].queryset = Location.objects.filter(
            is_active=True
        ).order_by('state', 'city')
        
        self.fields['vendor_code'].label_from_instance = lambda obj: f"{obj.vendor_code} - {obj.vendor_short_name}"
        self.fields['warehouse_location_id'].label_from_instance = lambda obj: f"{obj.location} - {obj.city}, {obj.state}"


class WarehouseProfileForm(forms.ModelForm):
    """Form for warehouse profile details"""

    class Meta:
        model = WarehouseProfile
        fields = [
            'warehouse_grade',
            'property_type',
            'business_type',
            'fire_safety_compliant',
            'security_features',
            'certifications',
            'remarks'
        ]
        widgets = {
            'warehouse_grade': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500'
            }),
            'property_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500'
            }),
            'business_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500'
            }),
            'fire_safety_compliant': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600'
            }),
            'security_features': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'rows': 3,
                'placeholder': 'Security features (CCTV, guards, etc.)'
            }),
            'certifications': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'rows': 3,
                'placeholder': 'Certifications (ISO, etc.)'
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'rows': 3,
                'placeholder': 'Additional remarks'
            })
        }
        labels = {
            'warehouse_grade': 'Warehouse Grade',
            'property_type': 'Property Type',
            'business_type': 'Business Type',
            'fire_safety_compliant': 'Fire Safety Compliant',
            'security_features': 'Security Features',
            'certifications': 'Certifications',
            'remarks': 'Remarks'
        }

    def clean(self):
        """Validate profile data"""
        cleaned_data = super().clean()
        fire_safety = cleaned_data.get('fire_safety_compliant')
        security_features = cleaned_data.get('security_features')

        # If fire safety compliant is checked, security features should be described
        if fire_safety and not security_features:
            self.add_error('security_features', 'Please describe security features if warehouse is fire safety compliant')

        return cleaned_data


class WarehouseCapacityForm(forms.ModelForm):
    """Form for warehouse capacity details"""

    class Meta:
        model = WarehouseCapacity
        fields = [
            'capacity_unit_type',
            'total_area_sqft',
            'total_capacity',
            'available_capacity',
            'pallets_available',
            'racking_available',
            'racking_details',
            'forklifts_count',
            'loading_bays_count',
            'operating_hours',
            'is_24x7',
            'temperature_controlled',
            'hazmat_supported'
        ]
        widgets = {
            'capacity_unit_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500'
            }),
            'total_area_sqft': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Total area in sqft'
            }),
            'total_capacity': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Total capacity'
            }),
            'available_capacity': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Available capacity'
            }),
            'pallets_available': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Number of pallets'
            }),
            'racking_available': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600'
            }),
            'racking_details': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'rows': 2,
                'placeholder': 'Racking details'
            }),
            'forklifts_count': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Number of forklifts'
            }),
            'loading_bays_count': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Number of loading bays'
            }),
            'operating_hours': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'e.g., 9 AM - 6 PM'
            }),
            'is_24x7': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600'
            }),
            'temperature_controlled': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600'
            }),
            'hazmat_supported': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600'
            })
        }
        labels = {
            'capacity_unit_type': 'Capacity Unit Type',
            'total_area_sqft': 'Total Area (sqft)',
            'total_capacity': 'Total Capacity',
            'available_capacity': 'Available Capacity',
            'pallets_available': 'Pallets Available',
            'racking_available': 'Racking Available',
            'racking_details': 'Racking Details',
            'forklifts_count': 'Forklifts Count',
            'loading_bays_count': 'Loading Bays Count',
            'operating_hours': 'Operating Hours',
            'is_24x7': '24x7 Operations',
            'temperature_controlled': 'Temperature Controlled',
            'hazmat_supported': 'Hazmat Supported'
        }

    def clean(self):
        """Validate capacity data"""
        cleaned_data = super().clean()
        total_capacity = cleaned_data.get('total_capacity')
        available_capacity = cleaned_data.get('available_capacity')
        total_area_sqft = cleaned_data.get('total_area_sqft')
        forklifts_count = cleaned_data.get('forklifts_count')
        loading_bays_count = cleaned_data.get('loading_bays_count')
        pallets_available = cleaned_data.get('pallets_available')

        # Validate positive values
        if total_capacity is not None and total_capacity < 0:
            raise forms.ValidationError({'total_capacity': 'Total capacity cannot be negative'})

        if available_capacity is not None and available_capacity < 0:
            raise forms.ValidationError({'available_capacity': 'Available capacity cannot be negative'})

        if total_area_sqft is not None and total_area_sqft < 0:
            raise forms.ValidationError({'total_area_sqft': 'Total area cannot be negative'})

        if forklifts_count is not None and forklifts_count < 0:
            raise forms.ValidationError({'forklifts_count': 'Forklifts count cannot be negative'})

        if loading_bays_count is not None and loading_bays_count < 0:
            raise forms.ValidationError({'loading_bays_count': 'Loading bays count cannot be negative'})

        if pallets_available is not None and pallets_available < 0:
            raise forms.ValidationError({'pallets_available': 'Pallets available cannot be negative'})

        # Validate available capacity does not exceed total capacity
        if total_capacity is not None and available_capacity is not None:
            if available_capacity > total_capacity:
                raise forms.ValidationError({
                    'available_capacity': 'Available capacity cannot exceed total capacity'
                })

        return cleaned_data


class WarehouseCommercialForm(forms.ModelForm):
    """Form for warehouse commercial details"""
    
    class Meta:
        model = WarehouseCommercial
        fields = [
            'rate_unit_type',
            'sla_status',
            'indicative_rate',
            'minimum_commitment_months',
            'payment_terms',
            'security_deposit',
            'contract_start_date',
            'contract_end_date',
            'notice_period_days',
            'escalation_percentage',
            'escalation_terms',
            'remarks'
        ]
        widgets = {
            'rate_unit_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500'
            }),
            'sla_status': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500'
            }),
            'indicative_rate': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Indicative rate',
                'step': '0.01'
            }),
            'minimum_commitment_months': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Minimum commitment in months'
            }),
            'payment_terms': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'rows': 2,
                'placeholder': 'Payment terms'
            }),
            'security_deposit': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Security deposit amount',
                'step': '0.01'
            }),
            'contract_start_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'type': 'date'
            }),
            'contract_end_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'type': 'date'
            }),
            'notice_period_days': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Notice period in days'
            }),
            'escalation_percentage': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Escalation percentage',
                'step': '0.01'
            }),
            'escalation_terms': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'rows': 2,
                'placeholder': 'Escalation terms'
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'rows': 3,
                'placeholder': 'Additional remarks'
            })
        }
        labels = {
            'rate_unit_type': 'Rate Unit Type',
            'sla_status': 'SLA Status',
            'indicative_rate': 'Indicative Rate',
            'minimum_commitment_months': 'Minimum Commitment (Months)',
            'payment_terms': 'Payment Terms',
            'security_deposit': 'Security Deposit',
            'contract_start_date': 'Contract Start Date',
            'contract_end_date': 'Contract End Date',
            'notice_period_days': 'Notice Period (Days)',
            'escalation_percentage': 'Escalation Percentage',
            'escalation_terms': 'Escalation Terms',
            'remarks': 'Remarks'
        }

    def clean(self):
        """Validate commercial data"""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('contract_start_date')
        end_date = cleaned_data.get('contract_end_date')
        indicative_rate = cleaned_data.get('indicative_rate')
        minimum_commitment = cleaned_data.get('minimum_commitment_months')
        escalation_pct = cleaned_data.get('escalation_percentage')
        notice_period = cleaned_data.get('notice_period_days')

        # Validate contract dates
        if start_date and end_date:
            if start_date > end_date:
                raise forms.ValidationError({
                    'contract_end_date': 'Contract end date must be after start date'
                })

        # Validate positive values
        if indicative_rate is not None and indicative_rate < 0:
            raise forms.ValidationError({'indicative_rate': 'Indicative rate cannot be negative'})

        if minimum_commitment is not None and minimum_commitment < 0:
            raise forms.ValidationError({'minimum_commitment_months': 'Minimum commitment cannot be negative'})

        if escalation_pct is not None and (escalation_pct < 0 or escalation_pct > 100):
            raise forms.ValidationError({'escalation_percentage': 'Escalation percentage must be between 0 and 100'})

        if notice_period is not None and notice_period < 0:
            raise forms.ValidationError({'notice_period_days': 'Notice period cannot be negative'})

        return cleaned_data


class WarehouseContactForm(forms.ModelForm):
    """Form for warehouse contact persons"""
    
    class Meta:
        model = WarehouseContact
        fields = [
            'warehouse_contact_person',
            'warehouse_contact_designation',
            'warehouse_contact_department',
            'warehouse_contact_phone',
            'warehouse_contact_email',
            'warehouse_contact_is_primary',
            'warehouse_contact_is_active'
        ]
        widgets = {
            'warehouse_contact_person': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Full name'
            }),
            'warehouse_contact_designation': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Designation/Role'
            }),
            'warehouse_contact_department': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Department'
            }),
            'warehouse_contact_phone': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Phone number',
                'maxlength': '15'
            }),
            'warehouse_contact_email': forms.EmailInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'email@example.com'
            }),
            'warehouse_contact_is_primary': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500'
            }),
            'warehouse_contact_is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500'
            })
        }
        labels = {
            'warehouse_contact_person': 'Contact Person',
            'warehouse_contact_designation': 'Designation',
            'warehouse_contact_department': 'Department',
            'warehouse_contact_phone': 'Phone Number',
            'warehouse_contact_email': 'Email',
            'warehouse_contact_is_primary': 'Primary Contact',
            'warehouse_contact_is_active': 'Active',
        }

    def clean_warehouse_contact_phone(self):
        """Validate phone number"""
        phone = self.cleaned_data.get('warehouse_contact_phone')
        if phone:
            # Remove spaces and special characters
            phone = ''.join(filter(str.isdigit, phone))
            if len(phone) < 10:
                raise forms.ValidationError('Phone number must be at least 10 digits')
        return phone


# Create formset for warehouse contacts
WarehouseContactFormSet = inlineformset_factory(
    VendorWarehouse,
    WarehouseContact,
    form=WarehouseContactForm,
    extra=0,
    can_delete=True,
    min_num=0,
    validate_min=False,
    fk_name='warehouse_code'
)


class VendorWarehouseDocumentForm(forms.ModelForm):
    """Form for uploading warehouse documents"""
    
    class Meta:
        model = VendorWarehouseDocument
        fields = [
            'warehouse_electricity_bill',
            'warehouse_property_tax_receipt',
            'warehouse_poc_aadhar',
            'warehouse_poc_pan',
            'warehouse_noc_owner',
            'warehouse_owner_pan',
            'warehouse_owner_aadhar',
            'warehouse_noc_vendor'
        ]
        widgets = {
            'warehouse_electricity_bill': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'warehouse_property_tax_receipt': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'warehouse_poc_aadhar': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'warehouse_poc_pan': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'warehouse_noc_owner': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'warehouse_owner_pan': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'warehouse_owner_aadhar': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'warehouse_noc_vendor': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            })
        }
        labels = {
            'warehouse_electricity_bill': 'Electricity Bill',
            'warehouse_property_tax_receipt': 'Property Tax Receipt',
            'warehouse_poc_aadhar': 'POC Aadhar Card',
            'warehouse_poc_pan': 'POC PAN Card',
            'warehouse_noc_owner': 'NOC from Owner',
            'warehouse_owner_pan': 'Owner PAN Card',
            'warehouse_owner_aadhar': 'Owner Aadhar Card',
            'warehouse_noc_vendor': 'NOC from Vendor',
        }
        help_texts = {
            'warehouse_electricity_bill': 'Upload electricity bill (PDF, JPG, PNG)',
            'warehouse_property_tax_receipt': 'Upload property tax receipt (PDF, JPG, PNG)',
            'warehouse_poc_aadhar': 'Upload POC Aadhar card (PDF, JPG, PNG)',
            'warehouse_poc_pan': 'Upload POC PAN card (PDF, JPG, PNG)',
            'warehouse_noc_owner': 'Upload NOC from owner (PDF, JPG, PNG)',
            'warehouse_owner_pan': 'Upload owner PAN card (PDF, JPG, PNG)',
            'warehouse_owner_aadhar': 'Upload owner Aadhar card (PDF, JPG, PNG)',
            'warehouse_noc_vendor': 'Upload NOC from vendor (PDF, JPG, PNG)',
        }


class WarehousePhotoForm(forms.ModelForm):
    """Form for uploading warehouse photos/videos"""
    
    class Meta:
        model = WarehousePhoto
        fields = [
            'file',
            'file_type',
            'caption'
        ]
        widgets = {
            'file': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'accept': 'image/*,video/*'
            }),
            'file_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500'
            }),
            'caption': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Brief caption for the photo/video'
            })
        }
        labels = {
            'file': 'Upload Photo/Video',
            'file_type': 'Type',
            'caption': 'Caption',
        }


# Note: Photo upload now uses multi-file input via warehouse_photos_upload view
# WarehousePhotoFormSet removed - no longer using formset approach


# ============================================================================
# LOCATION FORM
# ============================================================================

class LocationForm(forms.ModelForm):
    """Form for creating/editing locations"""
    
    # Override to make them ModelChoiceFields
    region = forms.ModelChoiceField(
        queryset=Region.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
            'required': True
        }),
        empty_label="Select Region"
    )
    
    state = forms.ChoiceField(
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
            'required': True,
            'id': 'id_state'
        }),
        choices=[]
    )
    
    city = forms.ChoiceField(
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
            'required': True,
            'id': 'id_city'
        }),
        choices=[]
    )
    
    class Meta:
        model = Location
        fields = [
            'region',
            'state', 
            'city',
            'location', 
            'pincode',
            'is_active'
        ]
        widgets = {
            'location': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'e.g., Andheri East, Mumbai',
                'required': True
            }),
            'pincode': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'e.g., 400001',
                'maxlength': '6'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500'
            })
        }
        labels = {
            'region': 'Region',
            'state': 'State',
            'city': 'City',
            'location': 'Location',
            'pincode': 'Pincode',
            'is_active': 'Active',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Pre-select region when editing (model stores code string, field expects PK)
        if self.instance and self.instance.pk and self.instance.region:
            self.initial['region'] = self.instance.region

        # Populate state choices
        states = StateCode.objects.filter(is_active=True).order_by('state_name')
        self.fields['state'].choices = [('', 'Select State')] + [
            (state.state_name, state.state_name) for state in states
        ]

        # Determine which state to load cities for:
        # 1. POST data (form submission) — must populate to pass validation
        # 2. Existing instance (editing)
        selected_state = None
        if self.data and self.data.get('state'):
            selected_state = self.data.get('state')
        elif self.instance and self.instance.pk and self.instance.state:
            selected_state = self.instance.state

        if selected_state:
            try:
                state_obj = StateCode.objects.get(state_name=selected_state)
                cities = CityCode.objects.filter(
                    state_code=state_obj.state_code,
                    is_active=True
                ).order_by('city_name')
                self.fields['city'].choices = [('', 'Select City')] + [
                    (city.city_name, city.city_name) for city in cities
                ]
            except StateCode.DoesNotExist:
                self.fields['city'].choices = [('', 'Select State First')]
        else:
            self.fields['city'].choices = [('', 'Select State First')]
    
    def clean_region(self):
        """Convert Region model instance to its code string for the CharField"""
        region = self.cleaned_data.get('region')
        if region:
            return region.code
        return 'central'

    def clean_pincode(self):
        """Validate pincode"""
        pincode = self.cleaned_data.get('pincode')
        if pincode:
            pincode = ''.join(filter(str.isdigit, pincode))
            if len(pincode) != 6:
                raise forms.ValidationError('Pincode must be exactly 6 digits')
        return pincode