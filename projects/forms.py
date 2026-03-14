from django import forms
from django.core.exceptions import ValidationError
from supply.models import Location, VendorCard
from .models import ProjectCode
from .models_client import ClientCard
from supply.models import VendorWarehouse
from accounts.models import User
from .utils import validate_gst_state

# ============================================================================
# PROJECT CREATE FORM (Existing)
# ============================================================================

class ProjectCreateForm(forms.Form):
    SERIES_CHOICES = [
        ('WAAS', 'Warehouse as a Service'),
        ('SAAS', 'SaaS Only Client'),
        ('GW', 'Internal Use (GW)'),
    ]
    
    # Excluded vendor names (Keep existing logic)
    EXCLUDED_VENDORS = [
        'Marketing/Sales',
        'IT Expenses',
        'Office Expenses',
        'Grandhi',
        'Sesaram',
        'Gowardhan',
        'Hussian Zulfiqar',
        'Santosh Devi',
        'Nileshkumar Patel',
    ]
    
    # State names to exclude from location dropdown (Keep existing logic)
    STATE_NAMES = [
        'Rajasthan', 'Gujarat', 'Karnataka', 'Kerala', 'Delhi', 
        'Haryana', 'Uttar Pradesh', 'Maharashtra', 'Tamil Nadu',
        'Telangana', 'West Bengal', 'Punjab', 'Odisha', 'Bihar',
        'Jharkhand', 'Chhattisgarh', 'Madhya Pradesh', 'Assam',
        'Andhra Pradesh', 'Goa', 'Uttarakhand', 'Himachal Pradesh'
    ]
    
    # Series Type - WITH DEFAULT VALUE
    series_type = forms.ChoiceField(
        choices=SERIES_CHOICES,
        initial='WAAS',  # ← WAAS AS DEFAULT
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-3 px-4 text-base'
        })
    )
    
    # Client Name
    client_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-3 px-4 text-base',
            'placeholder': 'Enter client company name'
        })
    )
    
    # Vendor Name - Optimized dropdown
    vendor_name = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-3 px-4 text-base optimized-dropdown',
            'size': '1'
        })
    )
    
    # Location - Optimized dropdown
    location = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-3 px-4 text-base optimized-dropdown',
            'size': '1'
        })
    )
    
    # Sales Manager - REQUIRED
    sales_manager = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-3 px-4 text-base optimized-dropdown',
            'size': '1'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate vendor choices from VendorCard short names
        vendors = VendorCard.objects.filter(
            vendor_is_active=True
        ).exclude(
            vendor_short_name__isnull=True
        ).exclude(
            vendor_short_name=''
        ).values_list('vendor_short_name', flat=True).distinct().order_by('vendor_short_name')

        self.fields['vendor_name'].choices = [('', 'Select Vendor')] + [(v, v) for v in vendors]
        
        # Populate location choices from locations table (excluding state names)
        locations = Location.objects.filter(
            is_active=True
        ).exclude(
            city__in=self.STATE_NAMES
        ).values_list('city', flat=True).distinct().order_by('city')
        
        self.fields['location'].choices = [('', 'Select Location')] + [(loc, loc) for loc in locations]
        
        # Populate sales manager choices
        users = User.objects.filter(
            is_active=True,
            role__in=['sales_manager', 'crm_executive', 'director', 'admin']
        ).order_by('first_name', 'username')
        
        sales_choices = [('', 'Select Sales Manager')]
        for user in users:
            if user.first_name:
                name = f"{user.first_name} {user.last_name}".strip() if user.last_name else user.first_name
            else:
                name = user.username
            
            # Add role indicator in parentheses
            role_label = ''
            if user.role == 'director':
                role_label = ' (Director)'
            elif user.role == 'crm_executive':
                role_label = ' (CRM Executive)'
            elif user.role == 'sales_manager':
                role_label = ' (Sales Manager)'
            elif user.role == 'admin':
                role_label = ' (Admin)'
            
            sales_choices.append((user.id, f"{name}{role_label}"))
        
        self.fields['sales_manager'].choices = sales_choices
    
    def clean(self):
        cleaned_data = super().clean()
        series_type = cleaned_data.get('series_type')
        location_city = cleaned_data.get('location')
        
#        # Get state from location for GST validation
#        if location_city:
#            try:
#                location_obj = Location.objects.filter(city=location_city, is_active=True).first()
#                if location_obj:
#                    state_code = location_obj.state
#                    # Use fallback state if provided
#                    if 'fallback_state_code' in cleaned_data:
#                        state_code = cleaned_data['fallback_state_code']
#                    
#                    # Validate GST for WAAS series
#                    if series_type == 'WAAS':
#                        is_valid, warning_msg, fallback_state = validate_gst_state(state_code, series_type)
#                        # Store fallback state silently - no error shown to user
#                        cleaned_data['fallback_state_code'] = fallback_state
#            except Location.DoesNotExist:
#                raise forms.ValidationError('Selected location not found.')
        
        return cleaned_data


# ============================================================================
# PROJECT CODE FORM (For Editing Existing Projects - WITH FK FIELDS)
# ============================================================================

class ProjectCodeForm(forms.ModelForm):
    # Add custom dropdown fields
    vendor_name_dropdown = forms.ChoiceField(
        required=False,
        label="Select Vendor (Recommended)",
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
        })
    )

    location_dropdown = forms.ChoiceField(
        required=False,
        label="Select Location (Recommended)",
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
        })
    )

    # Add fields from ProjectCard (related model)
    billing_start_date = forms.DateField(
        required=False,
        label="Billing Start Date",
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'
        })
    )

    operation_start_date = forms.DateField(
        required=False,
        label="Operation Start Date",
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'
        })
    )

    class Meta:
        model = ProjectCode
        fields = [
            'series_type',
            'client_card',
            'client_name',
            'vendor_warehouse',
            'vendor_name',
            'warehouse_code',
            'location',
            'state',
            'project_status',
            'sales_manager',
            'operation_coordinator',
            'backup_coordinator',
            # 'billing_start_date' removed - now in ProjectCard only
            'operation_mode',
            'mis_status',
            # 'billing_unit' removed - not needed in project edit
            'minimum_billable_sqft',
            'minimum_billable_pallets',
        ]
        widgets = {
            'series_type': forms.Select(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'}),
            'client_card': forms.Select(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent'}),
            'vendor_warehouse': forms.Select(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent'}),
            'client_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent', 'placeholder': 'Or enter manually'}),
            'vendor_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent', 'placeholder': 'Or enter manually'}),
            'warehouse_code': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent', 'placeholder': 'Or enter manually'}),
            'location': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent', 'placeholder': 'Or enter manually'}),
            'state': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'}),
            'project_status': forms.Select(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'}),
            'sales_manager': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'}),
            'operation_coordinator': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'}),
            'backup_coordinator': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'}),
            # 'billing_start_date' widget removed - now custom field from ProjectCard
            'operation_mode': forms.Select(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'}),
            'mis_status': forms.Select(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'}),
            # 'billing_unit' widget removed - not needed in project edit
            'minimum_billable_sqft': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent', 'step': '0.01'}),
            'minimum_billable_pallets': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate client card dropdown
        self.fields['client_card'].queryset = ClientCard.objects.filter(
            client_is_active=True
        ).order_by('client_legal_name')
        self.fields['client_card'].empty_label = "-- Select Client Card --"
        self.fields['client_card'].required = False
        
        # Populate warehouse dropdown
        self.fields['vendor_warehouse'].queryset = VendorWarehouse.objects.filter(
            warehouse_is_active=True
        ).select_related('vendor_code', 'warehouse_location_id').order_by('warehouse_code')
        self.fields['vendor_warehouse'].empty_label = "-- Select Warehouse --"
        self.fields['vendor_warehouse'].required = False
        
        # Populate vendor dropdown (from existing projects)
        EXCLUDED_VENDORS = [
            'Marketing/Sales', 'IT Expenses', 'Office Expenses',
            'Grandhi', 'Sesaram', 'Gowardhan', 'Hussian Zulfiqar',
            'Santosh Devi', 'Nileshkumar Patel',
        ]
        # Populate vendor choices from VendorCard short names
        vendors = VendorCard.objects.filter(
            vendor_is_active=True
        ).exclude(
            vendor_short_name__isnull=True
        ).exclude(
            vendor_short_name=''
        ).values_list('vendor_short_name', flat=True).distinct().order_by('vendor_short_name')

        self.fields['vendor_name_dropdown'].choices = [('', '-- Select Vendor --')] + [(v, v) for v in vendors]
        
        # Populate location dropdown
        STATE_NAMES = [
            'Rajasthan', 'Gujarat', 'Karnataka', 'Kerala', 'Delhi',
            'Haryana', 'Uttar Pradesh', 'Maharashtra', 'Tamil Nadu',
            'Telangana', 'West Bengal', 'Punjab', 'Odisha', 'Bihar',
            'Jharkhand', 'Chhattisgarh', 'Madhya Pradesh', 'Assam',
            'Andhra Pradesh', 'Goa', 'Uttarakhand', 'Himachal Pradesh'
        ]
        locations = Location.objects.filter(
            is_active=True
        ).exclude(
            city__in=STATE_NAMES
        ).values_list('city', flat=True).distinct().order_by('city')
        
        self.fields['location_dropdown'].choices = [('', '-- Select Location --')] + [(loc, loc) for loc in locations]
        
        # Pre-select current values
        if self.instance and self.instance.pk:
            if self.instance.vendor_name:
                self.fields['vendor_name_dropdown'].initial = self.instance.vendor_name
            if self.instance.location:
                self.fields['location_dropdown'].initial = self.instance.location
        
        # Make all fields optional
        self.fields['client_name'].required = False
        self.fields['vendor_name'].required = False
        self.fields['warehouse_code'].required = False
        self.fields['location'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Use dropdown value if selected, otherwise use manual input
        vendor_dropdown = cleaned_data.get('vendor_name_dropdown')
        if vendor_dropdown:
            cleaned_data['vendor_name'] = vendor_dropdown
        
        location_dropdown = cleaned_data.get('location_dropdown')
        if location_dropdown:
            cleaned_data['location'] = location_dropdown
        
        # Existing validations
        client_card = cleaned_data.get('client_card')
        client_name = cleaned_data.get('client_name')
        vendor_warehouse = cleaned_data.get('vendor_warehouse')
        vendor_name = cleaned_data.get('vendor_name')
        
        if not client_card and not client_name:
            raise forms.ValidationError("Please select a Client Card OR enter a Client Name manually.")
        
        if not vendor_warehouse and not (vendor_name or cleaned_data.get('warehouse_code')):
            raise forms.ValidationError("Please select a Warehouse OR enter Vendor/Warehouse details manually.")
        
        return cleaned_data


# ============================================================================
# MASTER DATA FORMS (New - With Duplicate Checks)
# ============================================================================

class LocationForm(forms.ModelForm):
    # Hardcoded states list for India
    INDIAN_STATES = [
        ('MH', 'Maharashtra'), ('DL', 'Delhi'), ('KA', 'Karnataka'),
        ('TN', 'Tamil Nadu'), ('GJ', 'Gujarat'), ('UP', 'Uttar Pradesh'),
        ('TG', 'Telangana'), ('WB', 'West Bengal'), ('RJ', 'Rajasthan'),
        ('HR', 'Haryana'), ('MP', 'Madhya Pradesh'), ('AP', 'Andhra Pradesh'),
        ('BR', 'Bihar'), ('PB', 'Punjab'), ('JH', 'Jharkhand'),
        ('OR', 'Odisha'), ('CT', 'Chhattisgarh'), ('AS', 'Assam'),
        ('KL', 'Kerala'), ('UK', 'Uttarakhand'), ('HP', 'Himachal Pradesh'),
        ('GA', 'Goa'), ('JK', 'Jammu and Kashmir'), ('TR', 'Tripura'),
        ('ML', 'Meghalaya'), ('MN', 'Manipur'), ('NL', 'Nagaland'),
        ('AR', 'Arunachal Pradesh'), ('MZ', 'Mizoram'), ('SK', 'Sikkim'),
        ('CH', 'Chandigarh'), ('PY', 'Puducherry'),
    ]

    state_code = forms.ChoiceField(
        choices=INDIAN_STATES, 
        label="State",
        widget=forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500'})
    )
    city = forms.CharField(
        max_length=100, 
        label="City Name",
        widget=forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500', 'placeholder': 'e.g. Mumbai'})
    )

    class Meta:
        model = Location
        fields = ['city', 'state_code']

    def clean(self):
        cleaned_data = super().clean()
        city = cleaned_data.get('city')
        state_code = cleaned_data.get('state_code')
        
        # 1. Logic to populate state name automatically
        state_dict = dict(self.INDIAN_STATES)
        if state_code:
            self.instance.state = state_dict.get(state_code)

        # 2. DUPLICATE CHECK LOGIC
        if city and state_code:
            # Check using 'iexact' for case-insensitive match (e.g., "Pune" == "pune")
            exists = Location.objects.filter(
                city__iexact=city.strip(), 
                state_code=state_code
            ).exists()
            
            if exists:
                raise ValidationError(f"⚠️ Location '{city}' already exists in {state_dict.get(state_code)}.")
        
        return cleaned_data