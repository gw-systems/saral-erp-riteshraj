"""
Quotation Views
CRUD operations for quotations
"""

import json
import logging
import os
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from django.db.models import Count, Sum, Avg, Q as DQ
from projects.models_quotation import (
    Quotation, QuotationLocation, QuotationItem, QuotationAudit, QuotationProduct,
    QuotationRevision, QuotationAcceptanceToken
)
from projects.models_quotation_settings import QuotationSettings
from projects.forms_quotation import (
    QuotationForm, QuotationLocationFormSet, QuotationItemFormSet,
    QuotationProductFormSet, QuotationSettingsForm, EmailQuotationForm
)
from projects.services.quotation_audit import QuotationAuditService
from projects.services.quotation_pdf import QuotationPdfGenerator

logger = logging.getLogger(__name__)

# Markup thresholds (markup = (client - cost) / cost * 100).
# ≥26%: save freely. 15–25.99%: auto pending_approval. <15%: hard block.
MINIMUM_MARKUP_PCT = Decimal('26.00')
AUTO_REJECT_MARKUP_PCT = Decimal('15.00')


def _compute_margin_from_post(request):
    """
    Compute the overall gross markup from POST data.
    Returns (client_total, vendor_total, markup_pct) as Decimals.
    markup_pct is None when vendor_total == 0 (markup undefined).
    Formula: (client - cost) / cost * 100
    """
    client_total = Decimal('0')
    vendor_total = Decimal('0')

    location_count = min(
        int(request.POST.get('locations-TOTAL_FORMS', 0)),
        _MAX_LOCATION_FORMS
    )
    for i in range(location_count):
        prefix = f'locations-{i}-items'
        total_items = int(request.POST.get(f'{prefix}-TOTAL_FORMS', 0))
        for j in range(total_items):
            p = f'{prefix}-{j}'
            if request.POST.get(f'{p}-DELETE'):
                continue
            try:
                uc = Decimal(request.POST.get(f'{p}-unit_cost', '').strip())
                qty = Decimal(request.POST.get(f'{p}-quantity', '').strip())
                client_total += uc * qty
            except Exception:
                pass
            try:
                vuc = Decimal(request.POST.get(f'{p}-vendor_unit_cost', '').strip())
                vqty = Decimal(request.POST.get(f'{p}-vendor_quantity', '').strip())
                vendor_total += vuc * vqty
            except Exception:
                pass

    markup_pct = None
    if vendor_total > 0:
        markup_pct = ((client_total - vendor_total) / vendor_total) * Decimal('100')

    return client_total, vendor_total, markup_pct


@login_required
def quotation_list(request):
    """List all quotations with search and filters."""
    quotations = Quotation.objects.select_related('created_by').prefetch_related('locations__items')

    # Search
    search = request.GET.get('search', '').strip()
    if search:
        quotations = quotations.filter(
            Q(quotation_number__icontains=search) |
            Q(client_company__icontains=search) |
            Q(client_name__icontains=search) |
            Q(client_email__icontains=search)
        )

    # Status filter
    status = request.GET.get('status', '').strip()
    if status:
        quotations = quotations.filter(status=status)

    quotations = quotations.order_by('-date', '-quotation_id')

    # Pagination
    paginator = Paginator(quotations, 50)
    page = request.GET.get('page')
    quotations = paginator.get_page(page)

    context = {
        'quotations': quotations,
        'search_query': search,
        'status_filter': status,
    }

    return render(request, 'projects/quotations/quotation_list.html', context)


@login_required
def quotation_detail(request, quotation_id):
    """Display quotation details with audit history."""
    quotation = get_object_or_404(
        Quotation.objects.select_related('created_by').prefetch_related(
            'locations__items',
            'products',
            'audit_logs__user'
        ),
        quotation_id=quotation_id
    )

    is_director = (
        request.user.is_superuser
        or (hasattr(request.user, 'role') and request.user.role in ('director', 'admin'))
    )

    # Check if Gmail accounts are available for email sending
    from gmail.models import GmailToken
    has_gmail_accounts = GmailToken.objects.filter(user=request.user, is_active=True).exists()

    context = {
        'quotation': quotation,
        'audit_logs': quotation.audit_logs.all()[:20],
        'is_director': is_director,
        'has_gmail_accounts': has_gmail_accounts,
        'revisions': quotation.revisions.all(),
    }

    return render(request, 'projects/quotations/quotation_detail.html', context)


_MAX_LOCATION_FORMS = 50  # Must match QuotationLocationFormSet max_num


def _collect_item_formsets(request, location_formset):
    """Collect per-location item formsets from POST data."""
    item_formsets = []
    location_count = min(
        int(request.POST.get('locations-TOTAL_FORMS', 0)),
        _MAX_LOCATION_FORMS
    )
    for i in range(location_count):
        prefix = f'locations-{i}-items'
        # For existing locations, bind formset to instance so INITIAL_FORMS works
        loc_instance = None
        if i < len(location_formset.forms):
            loc = location_formset.forms[i].instance
            if loc and loc.pk:
                loc_instance = loc
        if loc_instance:
            item_formset = QuotationItemFormSet(request.POST, prefix=prefix, instance=loc_instance)
        else:
            item_formset = QuotationItemFormSet(request.POST, prefix=prefix)
        item_formsets.append((i, item_formset))
    return item_formsets


def _save_item_formsets(item_formsets, location_formset, quotation):
    """Save items for each location after locations are saved."""
    for i, item_formset in item_formsets:
        if i >= len(location_formset.forms):
            continue
        loc_form = location_formset.forms[i]
        if loc_form.cleaned_data.get('DELETE', False):
            continue
        location_instance = loc_form.instance
        item_formset.instance = location_instance
        items = item_formset.save(commit=False)
        for item in items:
            item.location = location_instance
            item.save()
        for item in item_formset.deleted_objects:
            item.delete()


def _build_existing_items_json(location_formset):
    """Build JSON of existing items keyed by location form index."""
    existing_items = {}
    for i, loc_form in enumerate(location_formset.forms):
        if loc_form.instance and loc_form.instance.pk:
            items = loc_form.instance.items.all().order_by('order')
            existing_items[str(i)] = [
                {
                    'id': item.pk,
                    'item_description': item.item_description,
                    'custom_description': item.custom_description or '',
                    'unit_cost': item.unit_cost,
                    'quantity': item.quantity,
                    'vendor_unit_cost': item.vendor_unit_cost or '',
                    'vendor_quantity': item.vendor_quantity or '',
                    'storage_unit_type': item.storage_unit_type or '',
                    'order': item.order,
                }
                for item in items
            ]
    return json.dumps(existing_items)


def _build_items_json_from_post(request):
    """Reconstruct items JSON from POST data (for re-rendering on validation failure)."""
    existing_items = {}
    location_count = int(request.POST.get('locations-TOTAL_FORMS', 0))
    for i in range(location_count):
        prefix = f'locations-{i}-items'
        total_items = int(request.POST.get(f'{prefix}-TOTAL_FORMS', 0))
        items = []
        for j in range(total_items):
            p = f'{prefix}-{j}'
            desc = request.POST.get(f'{p}-item_description', '')
            if not desc:
                continue
            items.append({
                'id': request.POST.get(f'{p}-item_id', ''),
                'item_description': desc,
                'custom_description': request.POST.get(f'{p}-custom_description', ''),
                'unit_cost': request.POST.get(f'{p}-unit_cost', ''),
                'quantity': request.POST.get(f'{p}-quantity', ''),
                'vendor_unit_cost': request.POST.get(f'{p}-vendor_unit_cost', ''),
                'vendor_quantity': request.POST.get(f'{p}-vendor_quantity', ''),
                'storage_unit_type': request.POST.get(f'{p}-storage_unit_type', ''),
                'order': request.POST.get(f'{p}-order', '0'),
            })
        if items:
            existing_items[str(i)] = items
    return json.dumps(existing_items)


def _collect_product_formset(request, quotation=None):
    """Collect product formset from POST data."""
    if quotation and quotation.pk:
        return QuotationProductFormSet(request.POST, prefix='products', instance=quotation)
    return QuotationProductFormSet(request.POST, prefix='products')


def _build_existing_products_json(quotation):
    """Build JSON list of existing products for template pre-population."""
    if not quotation or not quotation.pk:
        return '[]'
    products = quotation.products.all().order_by('order')
    return json.dumps([
        {
            'id': p.pk,
            'product_name': p.product_name,
            'type_of_business': p.type_of_business,
            'type_of_operation': p.type_of_operation,
            'packaging_type': p.packaging_type or '',
            'avg_weight_kg': str(p.avg_weight_kg) if p.avg_weight_kg else '',
            'dim_l': str(p.dim_l),
            'dim_w': str(p.dim_w),
            'dim_h': str(p.dim_h),
            'dim_unit': p.dim_unit,
            'share_pct': str(p.share_pct),
            'order': p.order,
        }
        for p in products
    ])


def _build_products_json_from_post(request):
    """Reconstruct products JSON from POST data (for re-render on validation failure)."""
    total = int(request.POST.get('products-TOTAL_FORMS', 0))
    products = []
    for i in range(total):
        p = f'products-{i}'
        name = request.POST.get(f'{p}-product_name', '')
        if not name:
            continue
        products.append({
            'id': request.POST.get(f'{p}-id', ''),
            'product_name': name,
            'type_of_business': request.POST.get(f'{p}-type_of_business', 'B2B'),
            'type_of_operation': request.POST.get(f'{p}-type_of_operation', ''),
            'packaging_type': request.POST.get(f'{p}-packaging_type', ''),
            'avg_weight_kg': request.POST.get(f'{p}-avg_weight_kg', ''),
            'dim_l': request.POST.get(f'{p}-dim_l', ''),
            'dim_w': request.POST.get(f'{p}-dim_w', ''),
            'dim_h': request.POST.get(f'{p}-dim_h', ''),
            'dim_unit': request.POST.get(f'{p}-dim_unit', 'CM'),
            'share_pct': request.POST.get(f'{p}-share_pct', '100'),
            'order': request.POST.get(f'{p}-order', str(i)),
        })
    return json.dumps(products)


def _product_context():
    """Return context dict entries for product dropdown choices."""
    return {
        'product_business_choices': QuotationProduct.BUSINESS_TYPE_CHOICES,
        'product_operation_choices': QuotationProduct.OPERATION_TYPE_CHOICES,
        'product_dim_unit_choices': QuotationProduct.DIM_UNIT_CHOICES,
    }


@login_required
@transaction.atomic
def quotation_create(request):
    """Create new quotation with manual client entry and nested formsets."""
    if request.method == 'POST':
        form = QuotationForm(request.POST, user=request.user)
        location_formset = QuotationLocationFormSet(request.POST, prefix='locations')
        product_formset = _collect_product_formset(request)

        # Collect item formsets per location
        item_formsets = _collect_item_formsets(request, location_formset)

        # Validate all
        all_valid = form.is_valid() and location_formset.is_valid() and product_formset.is_valid()
        for _, item_formset in item_formsets:
            if not item_formset.is_valid():
                all_valid = False
                logger.warning(f"Item formset errors: {item_formset.errors}")

        if all_valid:
            # Compute markup from submitted item data
            client_total, vendor_total, markup_pct = _compute_margin_from_post(request)
            requesting_approval = request.POST.get('_request_approval') == '1'

            # Hard block: <15% markup — directors not notified, cannot save
            if markup_pct is not None and markup_pct < AUTO_REJECT_MARKUP_PCT:
                messages.error(
                    request,
                    f"Markup is {markup_pct:.1f}%, below the minimum 15%. "
                    "Pricing is too low to proceed. Directors will not review sub-15% requests."
                )
                existing_items_json = _build_items_json_from_post(request)
                context = {
                    'form': form,
                    'location_formset': location_formset,
                    'product_formset': product_formset,
                    'item_choices': QuotationItem.ITEM_DESCRIPTION_CHOICES,
                    'storage_unit_choices': QuotationItem.STORAGE_UNIT_CHOICES,
                    'existing_items_json': existing_items_json,
                    'existing_products_json': _build_products_json_from_post(request),
                    'title': 'Create Quotation',
                    'markup_pct': float(markup_pct),
                    'min_markup_pct': float(MINIMUM_MARKUP_PCT),
                    **_product_context(),
                }
                return render(request, 'projects/quotations/quotation_create.html', context)

            # Soft block: 15–25.99% — requires approval unless user explicitly requesting it
            if (
                markup_pct is not None
                and markup_pct < MINIMUM_MARKUP_PCT
                and not requesting_approval
            ):
                messages.error(
                    request,
                    f"Markup is {markup_pct:.1f}%, below the required 26%. "
                    "Please adjust pricing or request director approval."
                )
                existing_items_json = _build_items_json_from_post(request)
                context = {
                    'form': form,
                    'location_formset': location_formset,
                    'product_formset': product_formset,
                    'item_choices': QuotationItem.ITEM_DESCRIPTION_CHOICES,
                    'storage_unit_choices': QuotationItem.STORAGE_UNIT_CHOICES,
                    'existing_items_json': existing_items_json,
                    'existing_products_json': _build_products_json_from_post(request),
                    'title': 'Create Quotation',
                    'markup_pct': float(markup_pct),
                    'min_markup_pct': float(MINIMUM_MARKUP_PCT),
                    **_product_context(),
                }
                return render(request, 'projects/quotations/quotation_create.html', context)

            quotation = form.save(commit=False)
            quotation.created_by = request.user
            quotation.point_of_contact = request.user.get_full_name()
            quotation.poc_phone = request.user.phone or ''
            # Signatory: always set from creating user (field not shown in template)
            phone = getattr(request.user, 'phone', '') or ''
            quotation.for_godamwale_signatory = (
                f"{request.user.get_full_name()} [{phone}]" if phone else request.user.get_full_name()
            )

            if requesting_approval and markup_pct is not None and markup_pct < MINIMUM_MARKUP_PCT:
                # Save as pending_approval — blocks send-to-client until a director approves
                quotation.status = 'pending_approval'
                quotation.margin_override_requested = True
            quotation.save()

            # Save locations
            location_formset.instance = quotation
            location_formset.save()

            # Save items per location
            _save_item_formsets(item_formsets, location_formset, quotation)

            # Save product SKU rows
            product_formset.instance = quotation
            product_formset.save()

            QuotationAuditService.log_action(
                quotation=quotation,
                user=request.user,
                action='created',
                ip_address=QuotationAuditService.get_client_ip(request),
                metadata={'markup_pct': str(markup_pct) if markup_pct is not None else None}
            )

            if requesting_approval:
                messages.warning(
                    request,
                    f"Quotation {quotation.quotation_number} saved as 'Pending Approval'. "
                    "A director must approve the low markup before this quotation can be sent."
                )
            else:
                messages.success(request, f"Quotation {quotation.quotation_number} created successfully.")
            return redirect('projects:quotation_detail', quotation_id=quotation.quotation_id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = QuotationForm(user=request.user)
        location_formset = QuotationLocationFormSet(prefix='locations')
        product_formset = QuotationProductFormSet(prefix='products')

    item_choices = QuotationItem.ITEM_DESCRIPTION_CHOICES
    storage_unit_choices = QuotationItem.STORAGE_UNIT_CHOICES

    # For validation failure, preserve submitted items/products
    existing_items_json = '{}'
    existing_products_json = '[]'
    if request.method == 'POST':
        existing_items_json = _build_items_json_from_post(request)
        existing_products_json = _build_products_json_from_post(request)

    context = {
        'form': form,
        'location_formset': location_formset,
        'product_formset': product_formset,
        'item_choices': item_choices,
        'storage_unit_choices': storage_unit_choices,
        'existing_items_json': existing_items_json,
        'existing_products_json': existing_products_json,
        'title': 'Create Quotation',
        'min_markup_pct': float(MINIMUM_MARKUP_PCT),
        **_product_context(),
    }

    return render(request, 'projects/quotations/quotation_create.html', context)


@login_required
@transaction.atomic
def quotation_edit(request, quotation_id):
    """Edit existing quotation with nested formsets."""
    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)

    if request.method == 'POST':
        form = QuotationForm(request.POST, instance=quotation)
        location_formset = QuotationLocationFormSet(request.POST, instance=quotation, prefix='locations')
        product_formset = _collect_product_formset(request, quotation=quotation)

        # Collect item formsets per location
        item_formsets = _collect_item_formsets(request, location_formset)

        # Validate all
        all_valid = form.is_valid() and location_formset.is_valid() and product_formset.is_valid()
        for _, item_formset in item_formsets:
            if not item_formset.is_valid():
                all_valid = False
                logger.warning(f"Item formset errors: {item_formset.errors}")

        if all_valid:
            # Compute markup from submitted item data
            client_total, vendor_total, markup_pct = _compute_margin_from_post(request)
            requesting_approval = request.POST.get('_request_approval') == '1'

            # Hard block: <15% markup
            if markup_pct is not None and markup_pct < AUTO_REJECT_MARKUP_PCT:
                messages.error(
                    request,
                    f"Markup is {markup_pct:.1f}%, below the minimum 15%. "
                    "Pricing is too low to proceed. Directors will not review sub-15% requests."
                )
                existing_items_json = _build_items_json_from_post(request)
                context = {
                    'form': form,
                    'location_formset': location_formset,
                    'product_formset': product_formset,
                    'quotation': quotation,
                    'item_choices': QuotationItem.ITEM_DESCRIPTION_CHOICES,
                    'storage_unit_choices': QuotationItem.STORAGE_UNIT_CHOICES,
                    'existing_items_json': existing_items_json,
                    'existing_products_json': _build_products_json_from_post(request),
                    'title': 'Edit Quotation',
                    'markup_pct': float(markup_pct),
                    'min_markup_pct': float(MINIMUM_MARKUP_PCT),
                    **_product_context(),
                }
                return render(request, 'projects/quotations/quotation_create.html', context)

            # Soft block: 15–25.99% — requires approval unless already approved or requesting
            if (
                markup_pct is not None
                and markup_pct < MINIMUM_MARKUP_PCT
                and not requesting_approval
                and not quotation.margin_override_approved
            ):
                messages.error(
                    request,
                    f"Markup is {markup_pct:.1f}%, below the required 26%. "
                    "Please adjust pricing or request director approval."
                )
                existing_items_json = _build_items_json_from_post(request)
                context = {
                    'form': form,
                    'location_formset': location_formset,
                    'product_formset': product_formset,
                    'quotation': quotation,
                    'item_choices': QuotationItem.ITEM_DESCRIPTION_CHOICES,
                    'storage_unit_choices': QuotationItem.STORAGE_UNIT_CHOICES,
                    'existing_items_json': existing_items_json,
                    'existing_products_json': _build_products_json_from_post(request),
                    'title': 'Edit Quotation',
                    'markup_pct': float(markup_pct),
                    'min_markup_pct': float(MINIMUM_MARKUP_PCT),
                    **_product_context(),
                }
                return render(request, 'projects/quotations/quotation_create.html', context)

            # Track changes
            changes = {}
            for field in form.changed_data:
                changes[field] = {
                    'old': str(form.initial.get(field, '')),
                    'new': str(form.cleaned_data[field])
                }

            # Snapshot before saving if editing a sent/accepted quotation
            if quotation.status in ('sent', 'accepted'):
                _create_revision(quotation, request.user)

            quotation = form.save(commit=False)

            if requesting_approval and markup_pct is not None and markup_pct < MINIMUM_MARKUP_PCT:
                quotation.status = 'pending_approval'
                quotation.margin_override_requested = True
            quotation.save()

            # Save locations
            location_formset.instance = quotation
            location_formset.save()

            # Save items per location
            _save_item_formsets(item_formsets, location_formset, quotation)

            # Save product SKU rows
            product_formset.instance = quotation
            product_formset.save()

            QuotationAuditService.log_action(
                quotation=quotation,
                user=request.user,
                action='modified',
                changes=changes,
                ip_address=QuotationAuditService.get_client_ip(request),
                metadata={'markup_pct': str(markup_pct) if markup_pct is not None else None}
            )

            if requesting_approval:
                messages.warning(
                    request,
                    f"Quotation {quotation.quotation_number} updated and saved as 'Pending Approval'."
                )
            else:
                messages.success(request, f"Quotation {quotation.quotation_number} updated successfully.")
            return redirect('projects:quotation_detail', quotation_id=quotation.quotation_id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = QuotationForm(instance=quotation)
        location_formset = QuotationLocationFormSet(instance=quotation, prefix='locations')
        product_formset = QuotationProductFormSet(instance=quotation, prefix='products')

    item_choices = QuotationItem.ITEM_DESCRIPTION_CHOICES
    storage_unit_choices = QuotationItem.STORAGE_UNIT_CHOICES

    # Build existing items/products JSON
    if request.method == 'POST':
        existing_items_json = _build_items_json_from_post(request)
        existing_products_json = _build_products_json_from_post(request)
    else:
        existing_items_json = _build_existing_items_json(location_formset)
        existing_products_json = _build_existing_products_json(quotation)

    context = {
        'form': form,
        'location_formset': location_formset,
        'product_formset': product_formset,
        'quotation': quotation,
        'item_choices': item_choices,
        'storage_unit_choices': storage_unit_choices,
        'existing_items_json': existing_items_json,
        'existing_products_json': existing_products_json,
        'title': 'Edit Quotation',
        'min_markup_pct': float(MINIMUM_MARKUP_PCT),
        **_product_context(),
    }

    return render(request, 'projects/quotations/quotation_create.html', context)


@login_required
def quotation_settings(request):
    """
    Frontend UI for configuring quotation system settings.
    Admin-only access.
    """
    # Permission check
    if not (request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role == 'admin')):
        messages.error(request, "You don't have permission to access settings.")
        return redirect('projects:quotation_list')

    settings = QuotationSettings.get_settings()

    if request.method == 'POST':
        form = QuotationSettingsForm(request.POST, request.FILES, instance=settings)

        if form.is_valid():
            settings = form.save(commit=False)
            settings.updated_by = request.user
            settings.save()

            messages.success(request, "Quotation settings updated successfully.")
            return redirect('projects:quotation_settings')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = QuotationSettingsForm(instance=settings)

    # Get connected OAuth tokens
    from projects.models_quotation_settings import QuotationToken
    quotation_tokens = QuotationToken.objects.filter(is_active=True).select_related('user')

    context = {
        'form': form,
        'settings': settings,
        'quotation_tokens': quotation_tokens,
    }

    return render(request, 'projects/quotations/quotation_settings.html', context)


@login_required
def download_docx(request, quotation_id):
    """Generate and download quotation as DOCX. Uses Google Docs API if configured, otherwise local generator."""
    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)

    try:
        settings = QuotationSettings.get_settings()

        if settings.google_docs_template_id:
            # Use Google Docs API
            generator = QuotationPdfGenerator(quotation, user=request.user)
            docx_path = generator.generate_docx()
        else:
            # Use local python-docx generator
            from projects.services.quotation_docx_local import LocalQuotationDocxGenerator
            generator = LocalQuotationDocxGenerator(quotation)
            docx_path = generator.generate_docx()

        QuotationAuditService.log_action(
            quotation=quotation,
            user=request.user,
            action='docx_generated',
            ip_address=QuotationAuditService.get_client_ip(request)
        )

        # Read into memory then delete temp file to prevent disk leaks
        try:
            with open(docx_path, 'rb') as f:
                file_data = f.read()
        finally:
            try:
                os.unlink(docx_path)
            except OSError:
                pass

        response = HttpResponse(
            file_data,
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{quotation.quotation_number}.docx"'
        return response

    except Exception as e:
        logger.error(f"DOCX generation error: {e}", exc_info=True)
        messages.error(request, f"Error generating document: {str(e)}")
        return redirect('projects:quotation_detail', quotation_id=quotation_id)


@login_required
def download_pdf(request, quotation_id):
    """Generate and download quotation as PDF. Uses Google Docs API if configured, otherwise local DOCX→PDF conversion."""
    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)

    try:
        settings = QuotationSettings.get_settings()

        if settings.google_docs_template_id:
            # Use Google Docs API for PDF (template-based)
            pdf_generator = QuotationPdfGenerator(quotation, user=request.user)
            pdf_path = pdf_generator.generate_pdf()
        else:
            # Local DOCX generation + Google Drive API for PDF conversion
            from projects.services.quotation_docx_local import LocalQuotationDocxGenerator
            generator = LocalQuotationDocxGenerator(quotation)
            pdf_path = generator.generate_pdf(user=request.user)

        QuotationAuditService.log_action(
            quotation=quotation,
            user=request.user,
            action='pdf_generated',
            ip_address=QuotationAuditService.get_client_ip(request)
        )

        # Read into memory then delete temp file to prevent disk leaks
        try:
            with open(pdf_path, 'rb') as f:
                file_data = f.read()
        finally:
            try:
                os.unlink(pdf_path)
            except OSError:
                pass

        response = HttpResponse(file_data, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{quotation.quotation_number}.pdf"'
        return response

    except Exception as e:
        logger.error(f"PDF generation error: {e}", exc_info=True)
        messages.error(request, f"Error generating PDF: {str(e)}")
        return redirect('projects:quotation_detail', quotation_id=quotation_id)


@login_required
def quotation_approve_margin(request, quotation_id):
    """
    Director-only view: approve a low-margin quotation.
    Sets margin_override_approved = True and moves status from
    pending_approval back to draft so the creator can send it.
    """
    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)

    # Only directors (and admins/superusers) may approve
    is_director = (
        request.user.is_superuser
        or (hasattr(request.user, 'role') and request.user.role in ('director', 'admin'))
    )
    if not is_director:
        messages.error(request, "Only directors can approve low-margin exceptions.")
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    if request.method == 'POST':
        action = request.POST.get('action', 'approve')

        if action == 'approve':
            quotation.margin_override_approved = True
            quotation.margin_override_approved_by = request.user
            quotation.margin_override_approved_at = timezone.now()
            if quotation.status == 'pending_approval':
                quotation.status = 'draft'
            quotation.save()

            QuotationAuditService.log_action(
                quotation=quotation,
                user=request.user,
                action='status_changed',
                changes={'from': 'pending_approval', 'to': 'draft', 'reason': 'director margin approval'},
                ip_address=QuotationAuditService.get_client_ip(request)
            )

            messages.success(
                request,
                f"Margin exception approved for {quotation.quotation_number}. "
                "Quotation is now in Draft and can be sent to the client."
            )

        elif action == 'reject':
            # Keep as pending_approval — creator must revise pricing
            QuotationAuditService.log_action(
                quotation=quotation,
                user=request.user,
                action='status_changed',
                changes={'action': 'margin_rejected', 'by': request.user.get_full_name()},
                ip_address=QuotationAuditService.get_client_ip(request)
            )
            messages.warning(
                request,
                f"Margin exception rejected for {quotation.quotation_number}. "
                "The creator must revise pricing to achieve ≥22% margin."
            )

    return redirect('projects:quotation_detail', quotation_id=quotation_id)


@login_required
def send_email(request, quotation_id):
    """
    Send quotation email with PDF attachment via Gmail API.
    Uses existing gmail app's EmailService.
    """
    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)

    # Block sending if margin approval is pending
    if quotation.status == 'pending_approval':
        messages.error(
            request,
            "This quotation is pending director approval for a low margin exception. "
            "It cannot be sent until a director approves it."
        )
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    if request.method == 'POST':
        form = EmailQuotationForm(user=request.user, quotation=quotation, data=request.POST)

        if form.is_valid():
            try:
                # Generate PDF — use Google Docs template if configured, otherwise fall back
                # to the local DOCX generator (which converts via Google Drive API).
                settings_obj = QuotationSettings.get_settings()
                if settings_obj.google_docs_template_id:
                    pdf_generator = QuotationPdfGenerator(quotation, user=request.user)
                    pdf_path = pdf_generator.generate_pdf()
                else:
                    from projects.services.quotation_docx_local import LocalQuotationDocxGenerator
                    generator = LocalQuotationDocxGenerator(quotation)
                    pdf_path = generator.generate_pdf(user=request.user)

                # Read PDF for attachment then clean up temp file
                try:
                    with open(pdf_path, 'rb') as f:
                        pdf_data = f.read()
                finally:
                    try:
                        os.unlink(pdf_path)
                    except OSError:
                        pass

                attachments = [{
                    'filename': f'{quotation.quotation_number}.pdf',
                    'data': pdf_data
                }]

                # Prepare email content
                custom_message = form.cleaned_data.get('custom_message', '').strip()

                if custom_message:
                    html_body = f"<html><body>{custom_message}</body></html>"
                    plain_text = custom_message
                else:
                    # Use template from settings
                    settings = QuotationSettings.get_settings()
                    plain_text = settings.email_body_template.format(
                        client_name=quotation.client_name,
                        quotation_number=quotation.quotation_number,
                        validity_date=quotation.validity_date.strftime('%d %B %Y'),
                        created_by_name=quotation.created_by.get_full_name()
                    )
                    html_body = f"<html><body><pre>{plain_text}</pre></body></html>"

                subject = QuotationSettings.get_settings().email_subject_template.format(
                    quotation_number=quotation.quotation_number,
                    client_company=quotation.client_company,
                    date=quotation.date.strftime('%d %B %Y')
                )

                cc_emails_list = form.cleaned_data.get('cc_emails', [])
                cc_string = ', '.join(cc_emails_list) if cc_emails_list else ''

                # Send via Gmail API
                from gmail.services import EmailService

                success = EmailService.send_email(
                    user=request.user,
                    sender_email=form.cleaned_data['sender_email'],
                    to_email=form.cleaned_data['recipient_email'],
                    subject=subject,
                    message_text=plain_text,
                    cc=cc_string,
                    html_body=html_body,
                    attachments=attachments
                )

                if not success:
                    raise Exception("Email sending failed via Gmail API")

                QuotationAuditService.log_action(
                    quotation=quotation,
                    user=request.user,
                    action='email_sent',
                    ip_address=QuotationAuditService.get_client_ip(request),
                    metadata={
                        'sender': form.cleaned_data['sender_email'],
                        'recipient': form.cleaned_data['recipient_email'],
                        'cc': cc_emails_list
                    }
                )

                if quotation.status == 'draft':
                    quotation.status = 'sent'
                    quotation.save()

                    QuotationAuditService.log_action(
                        quotation=quotation,
                        user=request.user,
                        action='status_changed',
                        changes={'from': 'draft', 'to': 'sent'},
                        ip_address=QuotationAuditService.get_client_ip(request)
                    )

                messages.success(request, f"Quotation sent successfully to {form.cleaned_data['recipient_email']}")
                return redirect('projects:quotation_detail', quotation_id=quotation_id)

            except Exception as e:
                messages.error(request, f"Error sending email: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = EmailQuotationForm(user=request.user, quotation=quotation)

    context = {
        'quotation': quotation,
        'form': form,
    }

    return render(request, 'projects/quotations/quotation_email.html', context)


# ─────────────────────────────────────────────────────────────
#  HELPERS FOR NEW FEATURES
# ─────────────────────────────────────────────────────────────

def _snapshot_quotation(quotation):
    """Return a JSON-serialisable dict of full quotation state."""
    locations = []
    for loc in quotation.locations.prefetch_related('items').all():
        items = []
        for item in loc.items.all():
            items.append({
                'item_id': item.item_id,
                'item_description': item.item_description,
                'custom_description': item.custom_description,
                'unit_cost': item.unit_cost,
                'quantity': item.quantity,
                'vendor_unit_cost': item.vendor_unit_cost,
                'vendor_quantity': item.vendor_quantity,
                'storage_unit_type': item.storage_unit_type,
                'order': item.order,
            })
        locations.append({
            'location_id': loc.location_id,
            'location_name': loc.location_name,
            'order': loc.order,
            'items': items,
        })
    return {
        'quotation_number': quotation.quotation_number,
        'status': quotation.status,
        'client_name': quotation.client_name,
        'client_company': quotation.client_company,
        'client_email': quotation.client_email,
        'validity_period': quotation.validity_period,
        'point_of_contact': quotation.point_of_contact,
        'commercial_type': quotation.commercial_type,
        'default_markup_pct': str(quotation.default_markup_pct),
        'locations': locations,
    }


def _create_revision(quotation, user):
    """Snapshot quotation before overwriting (called when editing sent/accepted)."""
    revision_number = quotation.revisions.count() + 1
    QuotationRevision.objects.create(
        quotation=quotation,
        revision_number=revision_number,
        snapshot=_snapshot_quotation(quotation),
        created_by=user,
    )
    QuotationAuditService.log_action(
        quotation=quotation,
        user=user,
        action='revision_created',
        metadata={'revision_number': revision_number},
    )


# ─────────────────────────────────────────────────────────────
#  FEATURE 2: STATUS TRANSITIONS
# ─────────────────────────────────────────────────────────────

@login_required
def quotation_transition(request, quotation_id):
    """Handle status transitions from the detail page."""
    if request.method != 'POST':
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)
    to_status = request.POST.get('to_status', '').strip()

    is_director = (
        request.user.is_superuser
        or (hasattr(request.user, 'role') and request.user.role in ('director', 'admin'))
    )

    ALLOWED_TRANSITIONS = {
        'sent': {
            'accepted': lambda u: True,
            'rejected': lambda u: True,
        },
        'accepted': {
            'draft': lambda u: is_director,
        },
        'rejected': {
            'draft': lambda u: is_director,
        },
        'draft': {
            'voided': lambda u: is_director,
        },
    }

    allowed = ALLOWED_TRANSITIONS.get(quotation.status, {})
    checker = allowed.get(to_status)

    if checker is None or not checker(request.user):
        messages.error(request, f"Transition from '{quotation.status}' to '{to_status}' is not allowed.")
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    old_status = quotation.status
    quotation.status = to_status
    quotation.save()

    QuotationAuditService.log_action(
        quotation=quotation,
        user=request.user,
        action='status_changed',
        changes={'from': old_status, 'to': to_status},
        ip_address=QuotationAuditService.get_client_ip(request),
    )

    messages.success(request, f"Quotation status updated to '{quotation.get_status_display()}'.")
    return redirect('projects:quotation_detail', quotation_id=quotation_id)


# ─────────────────────────────────────────────────────────────
#  FEATURE 3: VERSIONING / REVISIONS
# ─────────────────────────────────────────────────────────────

@login_required
def quotation_revision_view(request, quotation_id, revision_number):
    """Read-only view of a quotation revision snapshot."""
    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)
    revision = get_object_or_404(
        QuotationRevision,
        quotation=quotation,
        revision_number=revision_number
    )
    return render(request, 'projects/quotations/quotation_revision.html', {
        'quotation': quotation,
        'revision': revision,
        'snapshot': revision.snapshot,
    })


# ─────────────────────────────────────────────────────────────
#  FEATURE 5: DUPLICATE / CLONE
# ─────────────────────────────────────────────────────────────

@login_required
@transaction.atomic
def quotation_clone(request, quotation_id):
    """Clone an existing quotation — new number, all locations/items/products copied, status=draft."""
    if request.method != 'POST':
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    original = get_object_or_404(
        Quotation.objects.prefetch_related('locations__items', 'products'),
        quotation_id=quotation_id
    )

    # Create new quotation (pk=None forces INSERT)
    new_q = Quotation(
        client_name=original.client_name,
        client_company=original.client_company,
        client_email=original.client_email,
        client_phone=original.client_phone,
        client_address=original.client_address,
        billing_address=original.billing_address,
        shipping_address=original.shipping_address,
        client_gst_number=original.client_gst_number,
        validity_period=original.validity_period,
        point_of_contact=original.point_of_contact,
        poc_phone=original.poc_phone,
        gst_rate=original.gst_rate,
        commercial_type=original.commercial_type,
        default_markup_pct=original.default_markup_pct,
        payment_terms=original.payment_terms,
        sla_terms=original.sla_terms,
        contract_terms=original.contract_terms,
        liability_terms=original.liability_terms,
        company_tagline=original.company_tagline,
        for_godamwale_signatory=original.for_godamwale_signatory,
        operational_total_boxes=original.operational_total_boxes,
        operational_variance_pct=original.operational_variance_pct,
        operational_pallet_l=original.operational_pallet_l,
        operational_pallet_w=original.operational_pallet_w,
        operational_pallet_h=original.operational_pallet_h,
        status='draft',
        created_by=request.user,
    )
    new_q.save()

    # Clone locations and items
    for loc in original.locations.all():
        new_loc = QuotationLocation(
            quotation=new_q,
            location_name=loc.location_name,
            order=loc.order,
        )
        new_loc.save()
        for item in loc.items.all():
            QuotationItem(
                location=new_loc,
                item_description=item.item_description,
                custom_description=item.custom_description,
                unit_cost=item.unit_cost,
                quantity=item.quantity,
                vendor_unit_cost=item.vendor_unit_cost,
                vendor_quantity=item.vendor_quantity,
                storage_unit_type=item.storage_unit_type,
                order=item.order,
            ).save()

    # Clone products
    for prod in original.products.all():
        QuotationProduct(
            quotation=new_q,
            product_name=prod.product_name,
            type_of_business=prod.type_of_business,
            type_of_operation=prod.type_of_operation,
            packaging_type=prod.packaging_type,
            avg_weight_kg=prod.avg_weight_kg,
            dim_l=prod.dim_l,
            dim_w=prod.dim_w,
            dim_h=prod.dim_h,
            dim_unit=prod.dim_unit,
            share_pct=prod.share_pct,
            order=prod.order,
        ).save()

    QuotationAuditService.log_action(
        quotation=new_q,
        user=request.user,
        action='cloned',
        metadata={'cloned_from': original.quotation_number},
        ip_address=QuotationAuditService.get_client_ip(request),
    )

    messages.success(
        request,
        f"Quotation cloned as {new_q.quotation_number}. Review and update before sending."
    )
    return redirect('projects:quotation_edit', quotation_id=new_q.quotation_id)


# ─────────────────────────────────────────────────────────────
#  FEATURE 6: CLIENT ACCEPTANCE LINK
# ─────────────────────────────────────────────────────────────

@login_required
def quotation_generate_acceptance_link(request, quotation_id):
    """Generate (or regenerate) a client acceptance token and return the link."""
    if request.method != 'POST':
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)

    # Create or replace token
    from django.utils import timezone as tz
    import datetime
    expires_at = tz.make_aware(
        datetime.datetime.combine(quotation.validity_date, datetime.time.max)
    )

    try:
        token_obj = quotation.acceptance_token
        # Regenerate
        import uuid as _uuid
        token_obj.token = _uuid.uuid4()
        token_obj.expires_at = expires_at
        token_obj.used_at = None
        token_obj.accepted = None
        token_obj.client_remarks = ''
        token_obj.save()
    except QuotationAcceptanceToken.DoesNotExist:
        token_obj = QuotationAcceptanceToken.objects.create(
            quotation=quotation,
            expires_at=expires_at,
        )

    QuotationAuditService.log_action(
        quotation=quotation,
        user=request.user,
        action='acceptance_link_sent',
        ip_address=QuotationAuditService.get_client_ip(request),
        metadata={'token': str(token_obj.token)},
    )

    link = request.build_absolute_uri(
        f'/quotations/accept/{token_obj.token}/'
    )
    messages.success(request, f"Acceptance link generated: {link}")
    return redirect('projects:quotation_detail', quotation_id=quotation_id)


def quotation_accept_public(request, token):
    """Public view — no login required. Client accepts or rejects quotation."""
    token_obj = get_object_or_404(QuotationAcceptanceToken, token=token)
    quotation = token_obj.quotation

    if token_obj.is_expired:
        return render(request, 'projects/quotations/quotation_accept_public.html', {
            'expired': True,
            'quotation': quotation,
            'token': token_obj,
        })

    if token_obj.is_used:
        return render(request, 'projects/quotations/quotation_accept_public.html', {
            'already_used': True,
            'quotation': quotation,
            'token': token_obj,
        })

    if request.method == 'POST':
        decision = request.POST.get('decision', '')
        remarks = request.POST.get('client_remarks', '').strip()

        if decision not in ('accept', 'reject'):
            messages.error(request, "Invalid decision.")
            return redirect('projects:quotation_accept_public', token=token)

        token_obj.accepted = (decision == 'accept')
        token_obj.client_remarks = remarks
        token_obj.used_at = timezone.now()
        token_obj.save()

        new_status = 'accepted' if decision == 'accept' else 'rejected'
        old_status = quotation.status
        quotation.status = new_status
        quotation.save()

        QuotationAuditService.log_action(
            quotation=quotation,
            user=None,
            action='client_accepted' if decision == 'accept' else 'client_rejected',
            changes={'from': old_status, 'to': new_status},
            metadata={'via': 'client_link', 'remarks': remarks},
        )

        return render(request, 'projects/quotations/quotation_accept_public.html', {
            'thank_you': True,
            'accepted': token_obj.accepted,
            'quotation': quotation,
        })

    return render(request, 'projects/quotations/quotation_accept_public.html', {
        'quotation': quotation,
        'token': token_obj,
    })


# ─────────────────────────────────────────────────────────────
#  FEATURE 7: WIN/LOSS DASHBOARD
# ─────────────────────────────────────────────────────────────

@login_required
def quotation_dashboard(request):
    """Win/loss analytics dashboard — directors and admins only."""
    is_director = (
        request.user.is_superuser
        or (hasattr(request.user, 'role') and request.user.role in ('director', 'admin'))
    )
    if not is_director:
        messages.error(request, "You don't have permission to access the dashboard.")
        return redirect('projects:quotation_list')

    from datetime import date
    today = date.today()
    month_start = today.replace(day=1)

    qs = Quotation.objects.all()
    this_month = qs.filter(date__gte=month_start)

    total_sent = this_month.filter(status__in=['sent', 'accepted', 'rejected', 'expired']).count()
    total_won = this_month.filter(status='accepted').count()
    total_lost = this_month.filter(status='rejected').count()
    win_rate = round((total_won / total_sent * 100) if total_sent > 0 else 0, 1)

    # Pipeline value = sum of subtotals for sent quotations
    sent_qs = qs.filter(status='sent')
    pipeline_value = sum(q.subtotal for q in sent_qs[:100])  # cap to avoid slow queries

    # Approval queue
    pending_approval_count = qs.filter(status='pending_approval').count()

    # Expiring this week
    import datetime
    next_week = today + datetime.timedelta(days=7)
    expiring_soon = qs.filter(
        status='sent',
        date__lte=next_week
    ).count()

    # Top clients by won value
    won_qs = qs.filter(status='accepted').select_related().prefetch_related('locations__items')
    top_clients = {}
    for q in won_qs[:200]:
        key = q.client_company
        top_clients[key] = top_clients.get(key, Decimal('0')) + q.subtotal
    top_clients_list = sorted(top_clients.items(), key=lambda x: x[1], reverse=True)[:5]

    context = {
        'total_sent': total_sent,
        'total_won': total_won,
        'total_lost': total_lost,
        'win_rate': win_rate,
        'pipeline_value': pipeline_value,
        'pending_approval_count': pending_approval_count,
        'expiring_soon': expiring_soon,
        'top_clients': top_clients_list,
        'month_label': today.strftime('%B %Y'),
    }
    return render(request, 'projects/quotations/quotation_dashboard.html', context)


# ─────────────────────────────────────────────────────────────
#  AJAX: Auto-price endpoint
# ─────────────────────────────────────────────────────────────

@login_required
def quotation_auto_price(request):
    """AJAX endpoint: given cost + markup %, return client price."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        cost_unit = Decimal(str(data.get('cost_unit', '0')))
        cost_qty = Decimal(str(data.get('cost_qty', '0')))
        markup_pct = Decimal(str(data.get('markup_pct', '26')))

        multiplier = 1 + markup_pct / Decimal('100')
        client_unit = (cost_unit * multiplier).quantize(Decimal('0.01'))
        client_qty = cost_qty
        client_total = (client_unit * client_qty).quantize(Decimal('0.01'))
        actual_markup = (
            ((client_unit - cost_unit) / cost_unit * Decimal('100')).quantize(Decimal('0.01'))
            if cost_unit > 0 else Decimal('0')
        )

        return JsonResponse({
            'client_unit': str(client_unit),
            'client_qty': str(client_qty),
            'client_total': str(client_total),
            'markup_pct': str(actual_markup),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
