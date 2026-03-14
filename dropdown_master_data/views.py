from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from accounts.permissions import require_role
from .models import (
    Region, StateCode, StorageUnit, HandlingBaseType,
    VASServiceType, VASUnit, SalesChannel, OperationalCostType,
    DisputeCategory, DisputeStatus, Priority, Severity,
    ActivityType, RenewalActionType, RenewalStatus,
    EscalationActionType, EscalationStatus,
    AdhocBillingStatus, AdhocChargeType, TransactionSide,
    EscalationTerms
)

DROPDOWN_MODELS = {
    'region': Region,
    'storage_unit': StorageUnit,
    'handling_base_type': HandlingBaseType,
    'vas_service_type': VASServiceType,
    'vas_unit': VASUnit,
    'sales_channel': SalesChannel,
    'operational_cost_type': OperationalCostType,
    'dispute_category': DisputeCategory,
    'dispute_status': DisputeStatus,
    'priority': Priority,
    'severity': Severity,
    'activity_type': ActivityType,
    'renewal_action_type': RenewalActionType,
    'renewal_status': RenewalStatus,
    'escalation_action_type': EscalationActionType,
    'escalation_status': EscalationStatus,
    'adhoc_billing_status': AdhocBillingStatus,
    'adhoc_charge_type': AdhocChargeType,
    'transaction_side': TransactionSide,
    'escalation_terms': EscalationTerms,
}

@login_required
@require_role('admin', 'super_user')
def dropdown_master_list(request):
    """Master dropdown management dashboard"""
    
    dropdown_data = []  # Use list instead of dict
    for key, model in DROPDOWN_MODELS.items():
        dropdown_data.append({
            'name': model._meta.verbose_name_plural.title(),
            'model_name': key,  # This is the model_name for URL
            'count': model.objects.filter(is_active=True).count(),
            'total': model.objects.count()
        })
    
    context = {
        'dropdown_data': dropdown_data,
        'page_title': 'Master Dropdown Management'
    }
    
    return render(request, 'dropdown_master_data/master_list.html', context)


@login_required
@require_role('admin', 'super_user')
def dropdown_detail(request, model_name):
    """View and manage specific dropdown entries"""
    
    if model_name not in DROPDOWN_MODELS:
        messages.error(request, 'Invalid dropdown type')
        return redirect('dropdown_master_data:master_list')
    
    model = DROPDOWN_MODELS[model_name]
    # Handle StateCode special case
    if model_name == 'state':
        entries = model.objects.all().order_by('display_order', 'state_name')
    else:
        entries = model.objects.all().order_by('display_order', 'code')
    
    context = {
        'model_name': model_name,
        'model_verbose_name': model._meta.verbose_name_plural.title(),
        'entries': entries,
        'page_title': f'Manage {model._meta.verbose_name_plural.title()}'
    }
    
    return render(request, 'dropdown_master_data/dropdown_detail.html', context)


@login_required
@require_role('admin', 'super_user')
def dropdown_create(request, model_name):
    """Create new dropdown entry"""
    
    if model_name not in DROPDOWN_MODELS:
        messages.error(request, 'Invalid dropdown type')
        return redirect('dropdown_master_data:master_list')
    
    model = DROPDOWN_MODELS[model_name]
    
    if request.method == 'POST':
        code = request.POST.get('code')
        label = request.POST.get('label')
        display_order = request.POST.get('display_order', 100)
        
        try:
            model.objects.create(
                code=code,
                label=label,
                display_order=display_order,
                is_active=True
            )
            messages.success(request, f'{model._meta.verbose_name} created successfully!')
            return redirect('dropdown_master_data:dropdown_detail', model_name=model_name)
        except Exception as e:
            messages.error(request, f'Error creating entry: {str(e)}')
    
    context = {
        'model_name': model_name,
        'model_verbose_name': model._meta.verbose_name.title(),
        'action': 'Create'
    }
    
    return render(request, 'dropdown_master_data/dropdown_form.html', context)


@login_required
@require_role('admin', 'super_user')
def dropdown_edit(request, model_name, entry_code):
    """Edit dropdown entry"""
    
    if model_name not in DROPDOWN_MODELS:
        messages.error(request, 'Invalid dropdown type')
        return redirect('dropdown_master_data:master_list')
    
    model = DROPDOWN_MODELS[model_name]
    entry = get_object_or_404(model, code=entry_code)
    
    if request.method == 'POST':
        entry.code = request.POST.get('code')
        entry.label = request.POST.get('label')
        entry.display_order = request.POST.get('display_order', 100)
        entry.is_active = request.POST.get('is_active') == 'on'
        
        try:
            entry.save()
            messages.success(request, f'{model._meta.verbose_name} updated successfully!')
            return redirect('dropdown_master_data:dropdown_detail', model_name=model_name)
        except Exception as e:
            messages.error(request, f'Error updating entry: {str(e)}')
    
    context = {
        'model_name': model_name,
        'model_verbose_name': model._meta.verbose_name.title(),
        'entry': entry,
        'action': 'Edit'
    }
    
    return render(request, 'dropdown_master_data/dropdown_form.html', context)


@login_required
@require_role('admin', 'super_user')
def dropdown_toggle_active(request, model_name, entry_code):
    """Toggle active status"""
    
    if model_name not in DROPDOWN_MODELS:
        messages.error(request, 'Invalid dropdown type')
        return redirect('dropdown_master_data:master_list')
    
    model = DROPDOWN_MODELS[model_name]
    entry = get_object_or_404(model, code=entry_code)
    
    entry.is_active = not entry.is_active
    entry.save()
    
    status = 'activated' if entry.is_active else 'deactivated'
    messages.success(request, f'{entry.label} {status}!')
    
    return redirect('dropdown_master_data:dropdown_detail', model_name=model_name)