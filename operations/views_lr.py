"""
Lorry Receipt (LR / Consignment Note) Views
Full CRUD with audit trail, DOCX/PDF/Image download.
"""
import json
import logging
import os
import tempfile

from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.core.paginator import Paginator

from projects.models import ProjectCode
from .models_lr import LorryReceipt, LRLineItem, LRAuditLog

logger = logging.getLogger(__name__)

# Roles allowed for LR CRUD (except delete)
LR_ALLOWED_ROLES = [
    'operation_coordinator', 'operation_manager', 'operation_controller',
    'admin', 'super_user', 'sales_manager',
]

# Roles allowed to delete
LR_DELETE_ROLES = ['admin', 'super_user', 'operation_controller']


# ============================================================================
# HELPERS
# ============================================================================

def _get_projects_for_user(user):
    """Return projects queryset based on user role."""
    if user.role in ['admin', 'super_user', 'operation_controller']:
        return ProjectCode.objects.filter(
            project_status__in=['Active', 'Operation Not Started']
        ).order_by('client_name')

    if user.role == 'operation_manager':
        return ProjectCode.objects.filter(
            project_status__in=['Active', 'Operation Not Started'],
        ).order_by('client_name')

    if user.role == 'operation_coordinator':
        return ProjectCode.objects.filter(
            project_status__in=['Active', 'Operation Not Started'],
        ).filter(
            Q(operation_coordinator=user.get_full_name()) |
            Q(backup_coordinator=user.get_full_name())
        ).order_by('client_name')

    if user.role == 'sales_manager':
        return ProjectCode.objects.filter(
            project_status__in=['Active', 'Operation Not Started'],
            sales_manager=user.get_full_name(),
        ).order_by('client_name')

    return ProjectCode.objects.none()


def _lr_to_dict(lr):
    """Snapshot LR fields into a dict for audit logging."""
    data = {
        'lr_number': lr.lr_number,
        'lr_date': str(lr.lr_date),
        'project': str(lr.project.project_id),
        'from_location': lr.from_location,
        'to_location': lr.to_location,
        'vehicle_no': lr.vehicle_no,
        'vehicle_type': lr.vehicle_type,
        'delivery_office_address': lr.delivery_office_address,
        'consignor_name': lr.consignor_name,
        'consignor_address': lr.consignor_address,
        'consignee_name': lr.consignee_name,
        'consignee_address': lr.consignee_address,
        'consignor_gst_no': lr.consignor_gst_no,
        'consignee_gst_no': lr.consignee_gst_no,
        'invoice_no': lr.invoice_no,
        'gst_paid_by': lr.gst_paid_by,
        'mode_of_packing': lr.mode_of_packing,
        'value': lr.value,
        'remarks': lr.remarks,
        'insurance_company': lr.insurance_company,
        'insurance_policy_no': lr.insurance_policy_no,
        'insurance_date': lr.insurance_date,
        'insurance_amount': lr.insurance_amount,
        'insurance_risk': lr.insurance_risk,
    }
    items = []
    for item in lr.line_items.all().order_by('order'):
        items.append({
            'packages': item.packages,
            'description': item.description,
            'actual_weight': item.actual_weight,
            'charged_weight': item.charged_weight,
            'amount': item.amount,
        })
    data['line_items'] = items
    return data


def _create_audit_log(lr, action, user, old_values=None, new_values=None, reason=''):
    """Create an audit log entry."""
    LRAuditLog.objects.create(
        lr=lr,
        action=action,
        changed_by=user,
        old_values=old_values,
        new_values=new_values or {},
        change_reason=reason,
    )


def _extract_line_items(post_data):
    """Extract line items from POST data arrays."""
    packages_list = post_data.getlist('item_packages[]')
    descriptions_list = post_data.getlist('item_description[]')
    actual_weights_list = post_data.getlist('item_actual_weight[]')
    charged_weights_list = post_data.getlist('item_charged_weight[]')
    amounts_list = post_data.getlist('item_amount[]')

    items = []
    for i in range(len(packages_list)):
        # Skip completely empty rows
        if not any([
            packages_list[i].strip(),
            descriptions_list[i].strip() if i < len(descriptions_list) else '',
            actual_weights_list[i].strip() if i < len(actual_weights_list) else '',
            charged_weights_list[i].strip() if i < len(charged_weights_list) else '',
            amounts_list[i].strip() if i < len(amounts_list) else '',
        ]):
            continue

        items.append({
            'packages': packages_list[i].strip(),
            'description': descriptions_list[i].strip() if i < len(descriptions_list) else '',
            'actual_weight': actual_weights_list[i].strip() if i < len(actual_weights_list) else '',
            'charged_weight': charged_weights_list[i].strip() if i < len(charged_weights_list) else '',
            'amount': amounts_list[i].strip() if i < len(amounts_list) else '',
            'order': i,
        })
    return items


# ============================================================================
# LIST VIEW
# ============================================================================

@login_required
def lr_list(request):
    """List LRs with search, project filter, date range, pagination."""
    if request.user.role not in LR_ALLOWED_ROLES:
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')

    # Base queryset
    qs = LorryReceipt.objects.filter(is_deleted=False).select_related(
        'project', 'created_by'
    )

    # Role-based filtering
    if request.user.role == 'operation_coordinator':
        qs = qs.filter(
            Q(project__operation_coordinator=request.user.get_full_name()) |
            Q(project__backup_coordinator=request.user.get_full_name())
        )
    elif request.user.role == 'sales_manager':
        qs = qs.filter(project__sales_manager=request.user.get_full_name())

    # Filters
    search = request.GET.get('search', '').strip()
    project_filter = request.GET.get('project', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if search:
        qs = qs.filter(
            Q(lr_number__icontains=search) |
            Q(from_location__icontains=search) |
            Q(to_location__icontains=search) |
            Q(vehicle_no__icontains=search) |
            Q(consignor_name__icontains=search) |
            Q(consignor_address__icontains=search) |
            Q(consignee_name__icontains=search) |
            Q(consignee_address__icontains=search)
        )
    if project_filter:
        qs = qs.filter(project__project_id=project_filter)
    if date_from:
        try:
            qs = qs.filter(lr_date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(lr_date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass

    qs = qs.order_by('-lr_date', '-created_at')

    # Summary stats
    total_count = qs.count()
    from django.utils import timezone
    now = timezone.now()
    this_month_count = qs.filter(
        lr_date__year=now.year, lr_date__month=now.month
    ).count()

    # Pagination
    paginator = Paginator(qs, 25)
    page = request.GET.get('page')
    lrs = paginator.get_page(page)

    # Projects for filter dropdown
    projects = _get_projects_for_user(request.user)

    context = {
        'lrs': lrs,
        'projects': projects,
        'total_count': total_count,
        'this_month_count': this_month_count,
        'search': search,
        'project_filter': project_filter,
        'date_from': date_from,
        'date_to': date_to,
        'can_delete': request.user.role in LR_DELETE_ROLES,
    }
    return render(request, 'operations/lr_list.html', context)


# ============================================================================
# CREATE VIEW
# ============================================================================

@login_required
def lr_create(request):
    """Create a new LR."""
    if request.user.role not in LR_ALLOWED_ROLES:
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                project_id = request.POST.get('project')
                lr_date_str = request.POST.get('lr_date')
                if not project_id or not lr_date_str:
                    raise ValueError("Project and LR Date are required.")

                project = ProjectCode.objects.get(project_id=project_id)
                lr_date = datetime.strptime(lr_date_str, '%Y-%m-%d').date()

                lr = LorryReceipt(
                    lr_date=lr_date,
                    project=project,
                    from_location=request.POST.get('from_location', '').strip(),
                    to_location=request.POST.get('to_location', '').strip(),
                    vehicle_no=request.POST.get('vehicle_no', '').strip(),
                    vehicle_type=request.POST.get('vehicle_type', '').strip(),
                    delivery_office_address=request.POST.get('delivery_office_address', '').strip(),
                    consignor_name=request.POST.get('consignor_name', '').strip(),
                    consignor_address=request.POST.get('consignor_address', '').strip(),
                    consignee_name=request.POST.get('consignee_name', '').strip(),
                    consignee_address=request.POST.get('consignee_address', '').strip(),
                    consignor_gst_no=request.POST.get('consignor_gst_no', '').strip(),
                    consignee_gst_no=request.POST.get('consignee_gst_no', '').strip(),
                    invoice_no=request.POST.get('invoice_no', '').strip(),
                    gst_paid_by=request.POST.get('gst_paid_by', 'consignee'),
                    mode_of_packing=request.POST.get('mode_of_packing', '').strip(),
                    value=request.POST.get('value', '').strip(),
                    remarks=request.POST.get('remarks', '').strip(),
                    insurance_company=request.POST.get('insurance_company', '').strip(),
                    insurance_policy_no=request.POST.get('insurance_policy_no', '').strip(),
                    insurance_date=request.POST.get('insurance_date', '').strip(),
                    insurance_amount=request.POST.get('insurance_amount', '').strip(),
                    insurance_risk=request.POST.get('insurance_risk', '').strip(),
                    created_by=request.user,
                )
                lr.save()

                # Line items
                items = _extract_line_items(request.POST)
                for item_data in items:
                    LRLineItem.objects.create(lr=lr, **item_data)

                # Audit log
                _create_audit_log(
                    lr, 'CREATED', request.user,
                    new_values=_lr_to_dict(lr),
                )

                messages.success(request, f"LR {lr.lr_number} created successfully.")
                return redirect('operations:lr_detail', lr_id=lr.id)

        except ValueError as e:
            messages.error(request, f"Validation Error: {e}")
        except ProjectCode.DoesNotExist:
            messages.error(request, "Project not found.")
        except Exception as e:
            logger.exception("Error creating LR")
            messages.error(request, f"Error: {e}")

    projects = _get_projects_for_user(request.user)
    context = {
        'projects': projects,
        'is_edit': False,
        'gst_paid_by_choices': LorryReceipt.GST_PAID_BY_CHOICES,
    }
    return render(request, 'operations/lr_form.html', context)


# ============================================================================
# DETAIL VIEW
# ============================================================================

@login_required
def lr_detail(request, lr_id):
    """Show LR details with line items and audit log."""
    if request.user.role not in LR_ALLOWED_ROLES:
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')

    lr = get_object_or_404(
        LorryReceipt.objects.select_related('project', 'created_by', 'last_modified_by'),
        id=lr_id, is_deleted=False,
    )
    line_items = lr.line_items.all().order_by('order')
    audit_logs = lr.audit_logs.all().select_related('changed_by').order_by('-changed_at')

    context = {
        'lr': lr,
        'line_items': line_items,
        'audit_logs': audit_logs,
        'can_delete': request.user.role in LR_DELETE_ROLES,
    }
    return render(request, 'operations/lr_detail.html', context)


# ============================================================================
# EDIT VIEW
# ============================================================================

@login_required
def lr_edit(request, lr_id):
    """Edit an existing LR."""
    if request.user.role not in LR_ALLOWED_ROLES:
        messages.error(request, "Access denied.")
        return redirect('accounts:dashboard')

    lr = get_object_or_404(LorryReceipt, id=lr_id, is_deleted=False)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Snapshot old values
                old_values = _lr_to_dict(lr)

                project_id = request.POST.get('project')
                lr_date_str = request.POST.get('lr_date')
                if not project_id or not lr_date_str:
                    raise ValueError("Project and LR Date are required.")

                project = ProjectCode.objects.get(project_id=project_id)
                lr_date = datetime.strptime(lr_date_str, '%Y-%m-%d').date()

                lr.lr_date = lr_date
                lr.project = project
                lr.from_location = request.POST.get('from_location', '').strip()
                lr.to_location = request.POST.get('to_location', '').strip()
                lr.vehicle_no = request.POST.get('vehicle_no', '').strip()
                lr.vehicle_type = request.POST.get('vehicle_type', '').strip()
                lr.delivery_office_address = request.POST.get('delivery_office_address', '').strip()
                lr.consignor_name = request.POST.get('consignor_name', '').strip()
                lr.consignor_address = request.POST.get('consignor_address', '').strip()
                lr.consignee_name = request.POST.get('consignee_name', '').strip()
                lr.consignee_address = request.POST.get('consignee_address', '').strip()
                lr.consignor_gst_no = request.POST.get('consignor_gst_no', '').strip()
                lr.consignee_gst_no = request.POST.get('consignee_gst_no', '').strip()
                lr.invoice_no = request.POST.get('invoice_no', '').strip()
                lr.gst_paid_by = request.POST.get('gst_paid_by', 'consignee')
                lr.mode_of_packing = request.POST.get('mode_of_packing', '').strip()
                lr.value = request.POST.get('value', '').strip()
                lr.remarks = request.POST.get('remarks', '').strip()
                lr.insurance_company = request.POST.get('insurance_company', '').strip()
                lr.insurance_policy_no = request.POST.get('insurance_policy_no', '').strip()
                lr.insurance_date = request.POST.get('insurance_date', '').strip()
                lr.insurance_amount = request.POST.get('insurance_amount', '').strip()
                lr.insurance_risk = request.POST.get('insurance_risk', '').strip()
                lr.last_modified_by = request.user
                lr.save()

                # Replace line items
                lr.line_items.all().delete()
                items = _extract_line_items(request.POST)
                for item_data in items:
                    LRLineItem.objects.create(lr=lr, **item_data)

                # Audit log
                new_values = _lr_to_dict(lr)
                _create_audit_log(
                    lr, 'UPDATED', request.user,
                    old_values=old_values,
                    new_values=new_values,
                )

                messages.success(request, f"LR {lr.lr_number} updated successfully.")
                return redirect('operations:lr_detail', lr_id=lr.id)

        except ValueError as e:
            messages.error(request, f"Validation Error: {e}")
        except ProjectCode.DoesNotExist:
            messages.error(request, "Project not found.")
        except Exception as e:
            logger.exception("Error editing LR")
            messages.error(request, f"Error: {e}")

    projects = _get_projects_for_user(request.user)
    line_items = lr.line_items.all().order_by('order')

    context = {
        'lr': lr,
        'projects': projects,
        'line_items': line_items,
        'is_edit': True,
        'gst_paid_by_choices': LorryReceipt.GST_PAID_BY_CHOICES,
    }
    return render(request, 'operations/lr_form.html', context)


# ============================================================================
# DELETE VIEW
# ============================================================================

@login_required
def lr_delete(request, lr_id):
    """Soft-delete an LR (restricted roles)."""
    if request.user.role not in LR_DELETE_ROLES:
        messages.error(request, "Access denied. Only Admin, Super User, or Operation Controller can delete LRs.")
        return redirect('operations:lr_list')

    lr = get_object_or_404(LorryReceipt, id=lr_id, is_deleted=False)

    if request.method == 'POST':
        with transaction.atomic():
            old_values = _lr_to_dict(lr)
            lr.is_deleted = True
            lr.last_modified_by = request.user
            lr.save()

            _create_audit_log(
                lr, 'DELETED', request.user,
                old_values=old_values,
                new_values={'is_deleted': True},
                reason=request.POST.get('delete_reason', ''),
            )

        messages.success(request, f"LR {lr.lr_number} deleted successfully.")
        return redirect('operations:lr_list')

    context = {'lr': lr}
    return render(request, 'operations/lr_delete.html', context)


# ============================================================================
# DOWNLOAD DOCX
# ============================================================================

@login_required
def lr_download_docx(request, lr_id):
    """Generate and download LR as DOCX."""
    if request.user.role not in LR_ALLOWED_ROLES:
        raise Http404

    lr = get_object_or_404(LorryReceipt, id=lr_id, is_deleted=False)
    line_items = list(lr.line_items.all().order_by('order'))

    from operations.services.lr_docx_generator import generate_lr_docx
    docx_path = generate_lr_docx(lr, line_items)

    response = FileResponse(
        open(docx_path, 'rb'),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    response['Content-Disposition'] = f'attachment; filename="LR_{lr.lr_number}.docx"'

    # Clean up temp file after response is sent
    response._resource_closers.append(lambda: _safe_unlink(docx_path))
    return response


# ============================================================================
# DOWNLOAD PDF
# ============================================================================

@login_required
def lr_download_pdf(request, lr_id):
    """Generate and download LR as PDF via docx2pdf."""
    if request.user.role not in LR_ALLOWED_ROLES:
        raise Http404

    lr = get_object_or_404(LorryReceipt, id=lr_id, is_deleted=False)
    line_items = list(lr.line_items.all().order_by('order'))

    from operations.services.lr_docx_generator import generate_lr_pdf
    try:
        pdf_path = generate_lr_pdf(lr, line_items)
    except RuntimeError as e:
        messages.error(request, str(e))
        return redirect('operations:lr_detail', lr_id=lr.id)

    response = FileResponse(
        open(pdf_path, 'rb'),
        content_type='application/pdf',
    )
    response['Content-Disposition'] = f'attachment; filename="LR_{lr.lr_number}.pdf"'
    response._resource_closers.append(lambda: _safe_unlink(pdf_path))
    return response


# ============================================================================
# DOWNLOAD IMAGE (JPEG/PNG)
# ============================================================================

@login_required
def lr_download_image(request, lr_id):
    """Generate and download LR as a PNG image."""
    if request.user.role not in LR_ALLOWED_ROLES:
        raise Http404

    lr = get_object_or_404(LorryReceipt, id=lr_id, is_deleted=False)
    line_items = list(lr.line_items.all().order_by('order'))

    from operations.services.lr_docx_generator import generate_lr_image
    try:
        image_path = generate_lr_image(lr, line_items)
    except RuntimeError as e:
        messages.error(request, str(e))
        return redirect('operations:lr_detail', lr_id=lr.id)

    response = FileResponse(
        open(image_path, 'rb'),
        content_type='image/png',
    )
    response['Content-Disposition'] = f'attachment; filename="LR_{lr.lr_number}.png"'
    response._resource_closers.append(lambda: _safe_unlink(image_path))
    return response


# ============================================================================
# UTILITIES
# ============================================================================

def _safe_unlink(path):
    """Safely remove a file, ignoring errors."""
    try:
        os.unlink(path)
    except OSError:
        pass
