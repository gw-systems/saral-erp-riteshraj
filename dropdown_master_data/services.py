"""
Central Dropdown Service
Provides cached, efficient access to dropdown master data.
"""

from django.core.cache import cache
from django.apps import apps


# Cache timeout: 4 hours (dropdowns rarely change; clear_dropdown_cache() is called on edits)
CACHE_TIMEOUT = 14400


def get_dropdown_model(model_name):
    """
    Get dropdown model class by name.
    
    Args:
        model_name: String name of model (e.g., 'StorageUnit', 'Priority')
    
    Returns:
        Model class or None
    """
    try:
        return apps.get_model('dropdown_master_data', model_name)
    except LookupError:
        return None


def get_dropdown_choices(model_name, include_blank=False, blank_label='---'):
    """
    Get choices for Django form fields.
    
    Args:
        model_name: String name of model (e.g., 'StorageUnit')
        include_blank: Whether to include blank option
        blank_label: Label for blank option
    
    Returns:
        List of tuples: [(code, label), ...]
    
    Example:
        >>> get_dropdown_choices('StorageUnit')
        [('sqft', 'Square Feet'), ('pallet', 'Pallet'), ...]
    """
    cache_key = f'dropdown_choices_{model_name}_{include_blank}'
    choices = cache.get(cache_key)
    
    if choices is None:
        model = get_dropdown_model(model_name)
        if not model:
            return []
        
        queryset = model.objects.filter(is_active=True).order_by('display_order', 'code')
        choices = [(item.code, item.label) for item in queryset]
        
        if include_blank:
            choices = [('', blank_label)] + choices
        
        cache.set(cache_key, choices, CACHE_TIMEOUT)
    
    return choices


def get_dropdown_codes(model_name, codes_only=True):
    """
    Get list of active dropdown codes.
    
    Args:
        model_name: String name of model
        codes_only: If True, return list of codes; if False, return queryset
    
    Returns:
        List of code strings or QuerySet
    
    Example:
        >>> get_dropdown_codes('Priority')
        ['low', 'medium', 'high', 'critical']
    """
    cache_key = f'dropdown_codes_{model_name}'
    codes = cache.get(cache_key)
    
    if codes is None:
        model = get_dropdown_model(model_name)
        if not model:
            return []
        
        queryset = model.objects.filter(is_active=True).order_by('display_order', 'code')
        
        if codes_only:
            codes = list(queryset.values_list('code', flat=True))
        else:
            codes = queryset
        
        cache.set(cache_key, codes, CACHE_TIMEOUT)
    
    return codes


def get_dropdown_map(model_name):
    """
    Get code-to-label mapping dictionary.
    
    Args:
        model_name: String name of model
    
    Returns:
        Dict: {code: label, ...}
    
    Example:
        >>> get_dropdown_map('StorageUnit')
        {'sqft': 'Square Feet', 'pallet': 'Pallet', ...}
    """
    cache_key = f'dropdown_map_{model_name}'
    mapping = cache.get(cache_key)
    
    if mapping is None:
        model = get_dropdown_model(model_name)
        if not model:
            return {}
        
        queryset = model.objects.filter(is_active=True)
        mapping = {item.code: item.label for item in queryset}
        
        cache.set(cache_key, mapping, CACHE_TIMEOUT)
    
    return mapping


def get_dropdown_value(model_name, code):
    """
    Get single dropdown instance by code.
    
    Args:
        model_name: String name of model
        code: Code value to lookup
    
    Returns:
        Model instance or None
    
    Example:
        >>> unit = get_dropdown_value('StorageUnit', 'sqft')
        >>> unit.label
        'Square Feet'
    """
    model = get_dropdown_model(model_name)
    if not model:
        return None
    
    try:
        return model.objects.get(code=code, is_active=True)
    except model.DoesNotExist:
        return None


ALL_DROPDOWN_MODELS = [
    'StorageUnit', 'BillingUnit', 'HandlingUnit', 'VehicleType', 'VASUnit',
    'Priority', 'ApprovalStatus', 'BillingStatus', 'EscalationStatus',
    'TicketStatus', 'MonthlyBillingStatus', 'ApprovalAction', 'DisputeStatus',
    'QueryCategory', 'HolidayType', 'AdhocChargeType', 'EscalationActionType',
    'AlertType', 'Severity', 'ActivityType', 'SeriesType', 'ProjectStatus',
    'SalesChannel', 'HandlingBaseType', 'VASServiceType', 'OperationalCostType',
    'EscalationTerms', 'NoticePeriodDuration', 'OperationMode', 'MISStatus',
    'RateApplicability', 'HandlingDirection', 'TransactionSide', 'TicketType',
    'UserRole', 'NotificationType', 'WarehouseGrade', 'BusinessType',
    'PropertyType', 'SLAStatus', 'WarehouseContactDepartment', 'FileType',
]

ALL_DROPDOWNS_CACHE_KEY = 'all_dropdowns'


def clear_dropdown_cache(model_name=None):
    """
    Clear dropdown cache.

    Args:
        model_name: If provided, clear only this model's cache.
                   If None, clear all dropdown caches.

    Example:
        >>> clear_dropdown_cache('StorageUnit')  # Clear one
        >>> clear_dropdown_cache()  # Clear all
    """
    if model_name:
        cache.delete(f'dropdown_choices_{model_name}_False')
        cache.delete(f'dropdown_choices_{model_name}_True')
        cache.delete(f'dropdown_codes_{model_name}')
        cache.delete(f'dropdown_map_{model_name}')
        cache.delete(ALL_DROPDOWNS_CACHE_KEY)
    else:
        # Clear all dropdown caches explicitly (works with ALL cache backends)
        keys_to_delete = [ALL_DROPDOWNS_CACHE_KEY]
        for model in ALL_DROPDOWN_MODELS:
            keys_to_delete.extend([
                f'dropdown_choices_{model}_False',
                f'dropdown_choices_{model}_True',
                f'dropdown_codes_{model}',
                f'dropdown_map_{model}',
            ])
        cache.delete_many(keys_to_delete)


def validate_dropdown_value(model_name, code):
    """
    Check if a dropdown code is valid and active.
    
    Args:
        model_name: String name of model
        code: Code value to validate
    
    Returns:
        Boolean: True if valid and active
    
    Example:
        >>> validate_dropdown_value('StorageUnit', 'sqft')
        True
        >>> validate_dropdown_value('StorageUnit', 'invalid')
        False
    """
    valid_codes = get_dropdown_codes(model_name)
    return code in valid_codes