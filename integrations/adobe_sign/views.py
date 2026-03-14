"""
Adobe Sign Views
Enhanced workflow views with template-based signature placement

NOTE: This is a complete backend implementation. Views are ready for frontend integration.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, FileResponse
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

import io
import logging


def _flatten_pdf_acroforms(file_obj):
    """
    Return a BytesIO with all native PDF AcroForm fields and widget annotations removed.

    PDFs with native acroform fields cause Adobe Sign PUT /formFields to fail:
    Adobe imports those fields and then refuses any PUT with INVALID_FORM_FIELD_PROPERTY.
    We must remove both the /AcroForm dict from the root AND the /Widget annotations
    from each page's /Annots array — PdfWriter.add_page() copies annotations along with
    page content, so just deleting /AcroForm from root is not sufficient.
    """
    try:
        from PyPDF2 import PdfReader, PdfWriter, generic
        reader = PdfReader(file_obj)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        # Strip /AcroForm from root (PdfWriter may or may not carry it over)
        if '/AcroForm' in writer._root_object:
            del writer._root_object['/AcroForm']

        # Strip Widget annotations from every page — these are the visible acrofield boxes.
        # Adobe Sign picks these up even when /AcroForm is absent from the root.
        for page in writer.pages:
            if '/Annots' not in page:
                continue
            annots = page['/Annots']
            if hasattr(annots, 'get_object'):
                annots = annots.get_object()
            keep = []
            for annot_ref in annots:
                annot = annot_ref.get_object() if hasattr(annot_ref, 'get_object') else annot_ref
                subtype = annot.get('/Subtype')
                # Drop /Widget (acroform fields) and /Link (hyperlinks) — both get imported
                # by Adobe Sign as form fields and break PUT /formFields with 400 errors.
                if subtype not in ('/Widget', '/Link'):
                    keep.append(annot_ref)
            if keep:
                page[generic.NameObject('/Annots')] = generic.ArrayObject(keep)
            else:
                del page['/Annots']

        out = io.BytesIO()
        writer.write(out)
        out.seek(0)
        return out
    except Exception as e:
        logging.getLogger(__name__).warning(f"Could not flatten PDF acroforms: {e}. Uploading original.")
        file_obj.seek(0)
        return file_obj


from .models import (
    DocumentTemplate,
    Document,
    AdobeAgreement,
    Signer,
    AgreementEvent,
    AdobeSignSettings
)
from .forms import (
    DocumentTemplateForm,
    DocumentUploadForm,
    AgreementCreateForm,
    AgreementEditForm,
    AgreementRejectForm,
    DocumentReplaceForm,
)
from .services import AdobeAuthService, AdobeDocumentService, AdobeAgreementService
from .exceptions import AdobeSignException
from .utils.signature_field_validator import validate_signature_field_coordinates

logger = logging.getLogger(__name__)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def check_admin_or_backoffice(user):
    """Check if user is admin, director, or backoffice"""
    return user.role in ['admin', 'director', 'super_user', 'backoffice']


def check_director_or_admin(user):
    """Check if user is director or admin (for approval actions)"""
    return user.role in ['admin', 'director', 'super_user']


# ============================================================================
# DASHBOARD
# ============================================================================

@login_required
def dashboard(request):
    """
    Adobe Sign Dashboard
    Shows different views based on user role
    """
    if not check_admin_or_backoffice(request.user):
        messages.error(request, 'Access denied')
        return redirect('accounts:dashboard')

    # Get counts for different statuses
    draft_count = AdobeAgreement.objects.filter(approval_status='DRAFT').count()
    pending_count = AdobeAgreement.objects.filter(approval_status='PENDING_APPROVAL').count()
    rejected_count = AdobeAgreement.objects.filter(approval_status='REJECTED').count()
    approved_count = AdobeAgreement.objects.filter(approval_status='APPROVED_SENT').count()
    completed_count = AdobeAgreement.objects.filter(approval_status='COMPLETED').count()

    # Get recent agreements
    recent_agreements = AdobeAgreement.objects.all()[:10]

    # Get templates count
    templates_count = DocumentTemplate.objects.filter(is_active=True).count()

    # Check configuration
    is_configured, config_error = AdobeAuthService.validate_configuration()

    context = {
        'draft_count': draft_count,
        'pending_count': pending_count,
        'rejected_count': rejected_count,
        'approved_count': approved_count,
        'completed_count': completed_count,
        'recent_agreements': recent_agreements,
        'templates_count': templates_count,
        'is_configured': is_configured,
        'config_error': config_error,
        'is_director_or_admin': check_director_or_admin(request.user),
    }

    return render(request, 'adobe_sign/dashboard.html', context)


# ============================================================================
# DOCUMENT TEMPLATES (Admin Only)
# ============================================================================

@login_required
def template_list(request):
    """List all document templates"""
    if not check_director_or_admin(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    templates = DocumentTemplate.objects.all()

    context = {
        'templates': templates,
    }

    return render(request, 'adobe_sign/template_list.html', context)


@login_required
def template_create(request):
    """Create new document template"""
    if not check_director_or_admin(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    if request.method == 'POST':
        form = DocumentTemplateForm(request.POST, request.FILES)
        if form.is_valid():
            template = form.save(commit=False)
            template.created_by = request.user
            template.save()
            messages.success(request, f'Template "{template.name}" created successfully')
            return redirect('adobe_sign:template_list')
    else:
        form = DocumentTemplateForm()

    return render(request, 'adobe_sign/template_form.html', {'form': form, 'is_create': True})


@login_required
def template_edit(request, template_id):
    """Edit document template"""
    if not check_director_or_admin(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    template = get_object_or_404(DocumentTemplate, id=template_id)

    if request.method == 'POST':
        form = DocumentTemplateForm(request.POST, request.FILES, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, f'Template "{template.name}" updated successfully')
            return redirect('adobe_sign:template_list')
    else:
        form = DocumentTemplateForm(instance=template)

    return render(request, 'adobe_sign/template_form.html', {'form': form, 'template': template, 'is_create': False})


@login_required
@require_POST
def template_delete(request, template_id):
    """Delete (deactivate) document template"""
    if not check_director_or_admin(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)

    template = get_object_or_404(DocumentTemplate, id=template_id)
    template.is_active = False
    template.save()

    messages.success(request, f'Template "{template.name}" deactivated')
    return JsonResponse({'success': True})


# ============================================================================
# AGREEMENT WORKFLOW - BACKOFFICE
# ============================================================================

@login_required
def agreement_add(request):
    """
    Create new agreement — single-step: upload PDF, place e-sign blocks, create in Adobe Sign AUTHORING.

    This creates the agreement locally AND in Adobe Sign (AUTHORING state).
    Signature field data is saved locally but NOT pushed to Adobe yet — that happens
    when the director approves (PUT /formFields + PUT /state at approval time).
    """
    if not check_admin_or_backoffice(request.user):
        messages.error(request, 'Access denied')
        return redirect('accounts:dashboard')

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = AgreementCreateForm(request.POST, request.FILES)

        if form.is_valid():
            from django.db import transaction
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError
            import json

            try:
                with transaction.atomic():
                    # Create document from uploaded file
                    uploaded_file = form.cleaned_data.get('file')
                    if not uploaded_file:
                        error_msg = 'Please upload a PDF document'
                        if is_ajax:
                            return JsonResponse({'success': False, 'message': error_msg}, status=400)
                        messages.error(request, error_msg)
                        return render(request, 'adobe_sign/agreement_add.html', {'form': form})

                    document = Document.objects.create(
                        file=uploaded_file,
                        original_filename=uploaded_file.name,
                        file_size=uploaded_file.size,
                        uploaded_by=request.user
                    )

                    # Create agreement
                    agreement = form.save(commit=False)
                    agreement.document = document
                    agreement.prepared_by = request.user
                    agreement.created_by = request.user

                    # Get project and vendor
                    project = form.cleaned_data.get('project')
                    vendor = form.cleaned_data.get('vendor')

                    # Store references
                    agreement.project = project
                    agreement.vendor = vendor

                    # Auto-populate vendor_name
                    if vendor:
                        agreement.vendor_name = vendor.vendor_legal_name

                    # Auto-populate client_name and agreement_name
                    project_card_error = None
                    if project:
                        # Client name from project
                        if project.client_card:
                            agreement.client_name = project.client_card.client_legal_name
                        elif project.client_name:
                            agreement.client_name = project.client_name
                        else:
                            agreement.client_name = 'Client'

                        # Agreement name from project
                        if project.code:
                            agreement.agreement_name = f"{project.code} - {agreement.client_name}"
                        else:
                            agreement.agreement_name = f"{project.project_id} - {agreement.client_name}"

                        # Auto-populate tracking fields from ProjectCard
                        try:
                            from operations.models_projectcard import ProjectCard, StorageRate

                            project_card = ProjectCard.objects.filter(
                                project=project,
                                is_active=True
                            ).first()

                            if project_card:
                                storage_rate = StorageRate.objects.filter(
                                    project_card=project_card,
                                    rate_for='client'
                                ).first()

                                if storage_rate:
                                    agreement.minimum_billable_area = storage_rate.minimum_billable_area
                                    agreement.monthly_billable_amount = storage_rate.monthly_billable_amount
                                else:
                                    project_card_error = "No storage rate found for this project"
                            else:
                                project_card_error = "No active project card found for this project"
                        except Exception as e:
                            logger.warning(f"Could not fetch project card data: {e}")
                            project_card_error = "Could not fetch project billing data"

                        # Location & sales person
                        if project.location:
                            agreement.location = project.location
                        if project.sales_manager:
                            agreement.sales_person = project.sales_manager

                    elif vendor:
                        # Vendor-only agreement
                        agreement.client_name = vendor.vendor_legal_name
                        agreement.agreement_name = f"{vendor.vendor_legal_name} - Agreement"

                    # Mirror email fields for tracking
                    agreement.to_email = agreement.client_email
                    agreement.cc_email_list = agreement.cc_emails

                    # Store signature fields data (saved in DB, NOT sent to Adobe yet)
                    signature_fields_json = form.cleaned_data.get('signature_fields', '')
                    agreement.signature_field_data = signature_fields_json

                    # Validate signature fields exist
                    if not signature_fields_json:
                        error_msg = 'Please place at least one signature block on the document'
                        if is_ajax:
                            return JsonResponse({'success': False, 'message': error_msg}, status=400)
                        messages.error(request, error_msg)
                        return render(request, 'adobe_sign/agreement_add.html', {'form': form})

                    # Validate director email
                    director_email = AdobeAuthService.get_director_email()
                    if not director_email:
                        error_msg = 'Director email not configured. Please contact administrator.'
                        if is_ajax:
                            return JsonResponse({'success': False, 'message': error_msg}, status=400)
                        messages.error(request, error_msg)
                        return render(request, 'adobe_sign/agreement_add.html', {'form': form})

                    # Build signers list for Adobe Sign
                    signers_data = []
                    director_name = 'Director'
                    try:
                        db_settings = AdobeSignSettings.get_settings()
                        if db_settings and db_settings.director_name:
                            director_name = db_settings.director_name
                    except Exception:
                        pass

                    if agreement.flow_type == 'director_then_client':
                        # Director signs first (order 1): Company Seal field uses SIGNATURE,
                        # Director Seal field uses INITIALS — both in same participant set
                        # so director signs once in a single session.
                        signers_data.append({
                            'name': director_name,
                            'email': director_email,
                            'role': 'SIGNER',
                            'order': 1
                        })
                        # Client signs after director (order 2)
                        signers_data.append({
                            'name': agreement.client_name,
                            'email': agreement.client_email,
                            'role': 'SIGNER',
                            'order': 2
                        })
                    elif agreement.flow_type == 'client_only':
                        signers_data.append({
                            'name': agreement.client_name,
                            'email': agreement.client_email,
                            'role': 'SIGNER',
                            'order': 1
                        })

                    # --- Adobe Sign API: Upload + Create AUTHORING ---
                    # Upload transient document (flatten acroforms first to avoid
                    # Adobe Sign rejecting PUT /formFields on agreements with imported fields)
                    with document.file.open('rb') as f:
                        flat_pdf = _flatten_pdf_acroforms(f)
                        transient_id = AdobeDocumentService.upload_transient_document(
                            flat_pdf,
                            document.file_name
                        )

                    # Create agreement in AUTHORING state (no emails sent, no formFields yet)
                    detail_path = f'/integrations/adobe-sign/agreements/{agreement.id}/'
                    redirect_url_abs = request.build_absolute_uri(detail_path)

                    adobe_agreement_id = AdobeAgreementService.create_agreement_for_authoring(
                        transient_document_id=transient_id,
                        agreement_name=agreement.agreement_name,
                        signers_data=signers_data,
                        ccs=agreement.get_cc_list() if agreement.cc_emails else None,
                        message=agreement.agreement_message,
                        days_until_signing_deadline=agreement.days_until_signing_deadline,
                        reminder_frequency=agreement.reminder_frequency,
                        post_sign_redirect_url=redirect_url_abs
                    )

                    # Update agreement with Adobe ID and status
                    agreement.adobe_agreement_id = adobe_agreement_id
                    agreement.adobe_status = 'AUTHORING'
                    agreement.approval_status = 'PENDING_APPROVAL'
                    agreement.task_undertaken_by = request.user
                    agreement.sent_date_director = timezone.now()
                    agreement.submitted_at = timezone.now()
                    agreement.rejection_reason = ''
                    agreement.rejection_notes = ''
                    agreement.save()

                    # Create signer records (keyed on order so two director rows are distinct)
                    for s in signers_data:
                        Signer.objects.get_or_create(
                            agreement=agreement,
                            order=s['order'],
                            defaults={
                                'name': s['name'],
                                'email': s['email'],
                                'role': s['role'],
                                'status': 'NOT_YET_VISIBLE'
                            }
                        )

                    logger.info(
                        f"Agreement {agreement.id} created and uploaded to Adobe Sign AUTHORING "
                        f"(Adobe ID: {adobe_agreement_id}). Awaiting director approval."
                    )

                    # Build response
                    redirect_url = f'/integrations/adobe-sign/agreements/{agreement.id}/'
                    success_msg = 'Agreement created and sent for director approval.'

                    if project_card_error:
                        success_msg += f' Note: {project_card_error}.'

                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'redirect_url': redirect_url,
                            'message': success_msg,
                        })

                    messages.success(request, success_msg)
                    return redirect('adobe_sign:agreement_detail', agreement_id=agreement.id)

            except AdobeSignException as e:
                logger.error(f"Adobe Sign error creating agreement: {e}")
                error_msg = 'Failed to create agreement in Adobe Sign. Please try again.'
                if is_ajax:
                    return JsonResponse({'success': False, 'message': error_msg}, status=500)
                messages.error(request, error_msg)

            except Exception as e:
                logger.error(f"Error creating agreement: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({'success': False, 'message': 'Error creating agreement. Please try again.'}, status=500)
                messages.error(request, 'Error creating agreement. Please try again.')
        else:
            # Form validation failed
            if is_ajax:
                errors = {}
                for field, error_list in form.errors.items():
                    errors[field] = [str(e) for e in error_list]
                return JsonResponse({
                    'success': False,
                    'errors': errors,
                    'message': 'Please correct the errors below.'
                }, status=400)
    else:
        form = AgreementCreateForm()

    # Get projects data for JavaScript
    from projects.models import ProjectCode
    from operations.models_projectcard import ProjectCard, StorageRate
    from supply.models import VendorCard
    import json

    projects_data = []
    for project in ProjectCode.objects.filter(
        project_status__in=['Active', 'Operation Not Started'],
        series_type='WAAS'
    ).select_related('client_card').order_by('client_name', 'project_id'):
        client_name = ''
        if project.client_card:
            client_name = project.client_card.client_legal_name
        elif project.client_name:
            client_name = project.client_name

        minimum_billable_area = None
        monthly_billable_amount = None
        try:
            project_card = ProjectCard.objects.filter(
                project=project, is_active=True
            ).first()
            if project_card:
                storage_rate = StorageRate.objects.filter(
                    project_card=project_card, rate_for='client'
                ).first()
                if storage_rate:
                    minimum_billable_area = float(storage_rate.minimum_billable_area) if storage_rate.minimum_billable_area else None
                    monthly_billable_amount = float(storage_rate.monthly_billable_amount) if storage_rate.monthly_billable_amount else None
        except Exception as e:
            logger.warning(f"Could not fetch project card data for {project.project_id}: {e}")

        projects_data.append({
            'project_id': project.project_id,
            'code': project.code or '',
            'client_name': client_name,
            'minimum_billable_area': minimum_billable_area,
            'monthly_billable_amount': monthly_billable_amount,
            'location': project.location or '',
            'sales_person': project.sales_manager or ''
        })

    # Get vendors data for JavaScript
    vendors_data = []
    for v in VendorCard.objects.filter(vendor_is_active=True).order_by('vendor_legal_name'):
        vendors_data.append({
            'vendor_code': v.vendor_code,
            'vendor_legal_name': v.vendor_legal_name,
            'vendor_short_name': v.vendor_short_name or '',
        })

    # Get director email for frontend flow validation
    director_email = ''
    try:
        director_email = AdobeAuthService.get_director_email() or ''
    except Exception:
        pass

    context = {
        'form': form,
        'templates': DocumentTemplate.objects.filter(is_active=True),
        'projects_data': json.dumps(projects_data),
        'vendors_data': json.dumps(vendors_data),
        'director_email': director_email,
    }

    return render(request, 'adobe_sign/agreement_add.html', context)


@login_required
def agreement_edit(request, agreement_id):
    """
    Edit agreement (Draft or Rejected only)
    """
    import json
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_admin_or_backoffice(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    if not agreement.can_edit():
        messages.error(request, 'This agreement cannot be edited')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    if request.method == 'POST':
        form = AgreementEditForm(request.POST, instance=agreement)
        if form.is_valid():
            # Save updated signature fields if provided
            signature_fields_raw = request.POST.get('signature_fields', '')
            if signature_fields_raw:
                agreement_obj = form.save(commit=False)
                agreement_obj.signature_field_data = signature_fields_raw
                agreement_obj.save()
            else:
                form.save()
            messages.success(request, 'Agreement updated successfully')
            return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)
    else:
        form = AgreementEditForm(instance=agreement)

    # Pass existing signature fields as JSON for pre-loading in the PDF viewer
    existing_fields = agreement.signature_field_data or '[]'
    if isinstance(existing_fields, list):
        existing_fields_json = json.dumps(existing_fields)
    else:
        try:
            parsed = json.loads(existing_fields)
            existing_fields_json = json.dumps(parsed if isinstance(parsed, list) else [])
        except (json.JSONDecodeError, TypeError):
            existing_fields_json = '[]'

    context = {
        'agreement': agreement,
        'form': form,
        'existing_signature_fields_json': existing_fields_json,
    }

    return render(request, 'adobe_sign/agreement_edit.html', context)


@login_required
def agreement_submit(request, agreement_id):
    """DEPRECATED: Agreement creation and Adobe upload now happens in agreement_add."""
    return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)


@login_required
def replace_document(request, agreement_id):
    """
    Replace document for rejected agreement
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_admin_or_backoffice(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    if agreement.approval_status != 'REJECTED':
        messages.error(request, 'Can only replace document for rejected agreements')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    if request.method == 'POST':
        form = DocumentReplaceForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                new_file = form.cleaned_data['new_document']

                # Create new document
                new_doc = Document(
                    file=new_file,
                    uploaded_by=request.user
                )
                new_doc.save()

                # Update agreement
                agreement.document = new_doc
                agreement.adobe_agreement_id = None  # Clear old Adobe ID
                agreement.adobe_status = 'DRAFT'
                agreement.save()

                messages.success(request, 'Document replaced successfully')
                return redirect('adobe_sign:agreement_edit', agreement_id=agreement_id)

            except Exception as e:
                logger.error(f"Error replacing document: {e}")
                messages.error(request, f'Error: {str(e)}')
    else:
        form = DocumentReplaceForm()

    context = {
        'agreement': agreement,
        'form': form,
    }

    return render(request, 'adobe_sign/replace_document.html', context)


@login_required
@require_POST
def agreement_recall(request, agreement_id):
    """
    Backoffice recalls (withdraws) an agreement from director review.
    Cancels the AUTHORING agreement in Adobe Sign and returns to DRAFT.
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_admin_or_backoffice(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    if not agreement.can_recall():
        messages.error(request, 'This agreement cannot be recalled')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    # Cancel the AUTHORING agreement in Adobe Sign
    if agreement.adobe_agreement_id and agreement.adobe_agreement_id != 'PROCESSING':
        try:
            AdobeAgreementService.cancel_agreement(
                agreement.adobe_agreement_id,
                reason='Recalled by backoffice for editing',
                notify_signers=False
            )
            logger.info(f"Agreement {agreement.id} cancelled in Adobe Sign on recall")
        except AdobeSignException as e:
            logger.warning(f"Could not cancel Adobe agreement on recall: {e}")

    # Reset agreement to DRAFT
    agreement.recall()

    logger.info(f"Agreement {agreement.id} recalled by {request.user.email}")
    messages.success(request, 'Agreement recalled successfully. You can now edit and resubmit it.')
    return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)


@login_required
@require_POST
def agreement_recall_from_signing(request, agreement_id):
    """
    Admin/backoffice recalls an agreement that is currently OUT_FOR_SIGNATURE.
    Cancels the active Adobe Sign agreement and resets to DRAFT so it can be
    re-edited and resubmitted.
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_admin_or_backoffice(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    if not agreement.can_recall_from_signing():
        messages.error(request, 'This agreement cannot be recalled from signing (wrong status)')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    # Cancel the active agreement in Adobe Sign
    if agreement.adobe_agreement_id:
        try:
            AdobeAgreementService.cancel_agreement(
                agreement.adobe_agreement_id,
                reason='Recalled by admin — agreement will be re-edited and resubmitted',
                notify_signers=True,
            )
            logger.info(f"Agreement {agreement.id} cancelled in Adobe Sign (recalled from signing)")
        except AdobeSignException as e:
            logger.warning(f"Could not cancel Adobe agreement on recall-from-signing: {e}")
            messages.warning(request, f'Adobe Sign cancellation failed ({e}), but agreement has been reset locally.')

    # Reset to DRAFT
    agreement.recall_from_signing()

    logger.info(f"Agreement {agreement.id} recalled from signing by {request.user.email}")
    messages.success(request, 'Agreement recalled from signing. It is now in Draft — you can edit and resubmit.')
    return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)


@login_required
@require_POST
def agreement_resubmit(request, agreement_id):
    """
    Backoffice resubmits a DRAFT agreement (after recall or rejection) to director.
    Re-uploads document to Adobe Sign, creates new AUTHORING agreement,
    and sets approval_status back to PENDING_APPROVAL.
    """
    import json

    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_admin_or_backoffice(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    if not agreement.can_submit_for_approval():
        messages.error(request, 'This agreement cannot be submitted in its current state')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    if not agreement.document:
        messages.error(request, 'No document attached to this agreement')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    try:
        # Get director email
        director_email = AdobeAuthService.get_director_email()
        if agreement.flow_type == 'director_then_client' and not director_email:
            messages.error(request, 'Director email not configured. Please contact admin.')
            return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

        # Build signers list
        signers_data = []
        director_name = 'Director'
        try:
            db_settings = AdobeSignSettings.get_settings()
            if db_settings and db_settings.director_name:
                director_name = db_settings.director_name
        except Exception:
            pass

        if agreement.flow_type == 'director_then_client':
            signers_data.append({
                'name': director_name,
                'email': director_email,
                'role': 'SIGNER',
                'order': 1
            })
            # Client signs after director (order 2)
            signers_data.append({
                'name': agreement.client_name,
                'email': agreement.client_email,
                'role': 'SIGNER',
                'order': 2
            })
        elif agreement.flow_type == 'client_only':
            signers_data.append({
                'name': agreement.client_name,
                'email': agreement.client_email,
                'role': 'SIGNER',
                'order': 1
            })

        # Upload transient document to Adobe Sign (flatten acroforms first)
        with agreement.document.file.open('rb') as f:
            flat_pdf = _flatten_pdf_acroforms(f)
            transient_id = AdobeDocumentService.upload_transient_document(
                flat_pdf,
                agreement.document.file_name
            )

        # Create new AUTHORING agreement in Adobe Sign
        adobe_agreement_id = AdobeAgreementService.create_agreement_for_authoring(
            transient_document_id=transient_id,
            agreement_name=agreement.agreement_name,
            signers_data=signers_data,
            ccs=agreement.get_cc_list() if agreement.cc_emails else None,
            message=agreement.agreement_message,
            days_until_signing_deadline=agreement.days_until_signing_deadline,
            reminder_frequency=agreement.reminder_frequency
        )

        # Update agreement with new Adobe ID and status
        agreement.adobe_agreement_id = adobe_agreement_id
        agreement.adobe_status = 'AUTHORING'
        agreement.approval_status = 'PENDING_APPROVAL'
        agreement.task_undertaken_by = request.user
        agreement.sent_date_director = timezone.now()
        agreement.submitted_at = timezone.now()
        agreement.rejection_reason = ''
        agreement.rejection_notes = ''
        agreement.save()

        # Ensure signer records exist
        for s in signers_data:
            Signer.objects.get_or_create(
                agreement=agreement,
                email=s['email'],
                defaults={
                    'name': s['name'],
                    'role': s['role'],
                    'order': s['order'],
                    'status': 'NOT_YET_VISIBLE'
                }
            )

        logger.info(f"Agreement {agreement.id} resubmitted to Adobe Sign AUTHORING by {request.user.email}")
        messages.success(request, 'Agreement resubmitted for director approval.')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    except AdobeSignException as e:
        logger.error(f"Adobe Sign error on resubmit: {e}")
        messages.error(request, f'Adobe Sign error: {str(e)}')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)
    except Exception as e:
        logger.error(f"Error resubmitting agreement: {e}")
        messages.error(request, f'Error: {str(e)}')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)


# ============================================================================
# AGREEMENT WORKFLOW - DIRECTOR/ADMIN
# ============================================================================

@login_required
def pending_agreements(request):
    """
    List agreements pending director approval
    """
    if not check_director_or_admin(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    pending = AdobeAgreement.objects.filter(approval_status='PENDING_APPROVAL').order_by('-submitted_at')

    context = {
        'pending_agreements': pending,
    }

    return render(request, 'adobe_sign/pending_agreements.html', context)


@login_required
def agreement_review(request, agreement_id):
    """
    Director reviews agreement before approval.
    Shows interactive PDF editor where director can adjust e-sign block positions.
    Signature fields are loaded from DB for editing. No Adobe API calls at this stage.
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_director_or_admin(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    # Get director email for field config
    director_email = ''
    try:
        director_email = AdobeAuthService.get_director_email() or ''
    except Exception:
        pass

    context = {
        'agreement': agreement,
        'signers': agreement.signers.all(),
        'flow_type': agreement.flow_type,
        'director_email': director_email,
    }

    return render(request, 'adobe_sign/agreement_review.html', context)


@login_required
@require_POST
def agreement_approve(request, agreement_id):
    """
    Director approves agreement: PUT /formFields → PUT /state → GET /signingUrls.

    Flow:
    1. Accept updated signature fields from director (they can adjust positions)
    2. Save updated fields to DB
    3. PUT /formFields on AUTHORING agreement (places fields in Adobe)
    4. PUT /state → IN_PROCESS (sends to signers)
    5. For director_then_client: GET /signingUrls for director to sign in-app
    6. For client_only: agreement goes directly to client (no director signing)
    """
    import json
    import re

    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_director_or_admin(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)

    if not agreement.can_approve():
        return JsonResponse({'success': False, 'error': 'Agreement cannot be approved'}, status=400)

    if not agreement.adobe_agreement_id or agreement.adobe_agreement_id == 'PROCESSING':
        return JsonResponse({'success': False, 'error': 'Agreement not created in Adobe Sign'}, status=400)

    if agreement.adobe_status not in ('AUTHORING', 'DRAFT'):
        logger.warning(
            f"Agreement {agreement_id} approve attempted but adobe_status={agreement.adobe_status}. "
            f"May have already been sent. Adobe ID: {agreement.adobe_agreement_id}"
        )
        return JsonResponse({
            'success': False,
            'error': f'Agreement is already in {agreement.adobe_status} state in Adobe Sign. '
                     f'It may have been previously sent. Please check the agreement detail page.'
        }, status=400)

    try:
        from django.db import transaction

        # Parse updated signature fields from request body
        try:
            body = json.loads(request.body)
            updated_fields = body.get('signature_fields', [])
        except (json.JSONDecodeError, AttributeError):
            updated_fields = []

        # Use updated fields if provided, otherwise use stored fields
        if updated_fields:
            signature_fields = updated_fields
        elif agreement.signature_field_data:
            if isinstance(agreement.signature_field_data, str):
                signature_fields = json.loads(agreement.signature_field_data)
            else:
                signature_fields = agreement.signature_field_data
        else:
            return JsonResponse({
                'success': False,
                'error': 'No signature fields found. Please place at least one signature block.'
            }, status=400)

        if not isinstance(signature_fields, list) or len(signature_fields) == 0:
            return JsonResponse({
                'success': False,
                'error': 'At least one signature field is required.'
            }, status=400)

        # Log raw incoming fields from JS for debugging
        logger.warning(f"[Approve] Raw signature_fields from JS ({len(signature_fields)}): {json.dumps(signature_fields)}")

        # Fetch participant sets from Adobe to get the actual participant set IDs.
        # Adobe Sign v6 PUT /formFields uses `assignee` (participant set ID string),
        # not `recipientIndex` (which was a v5 concept).
        details = AdobeAgreementService.get_agreement_details(agreement.adobe_agreement_id)
        psets = details.get('participantSetsInfo', [])
        logger.warning(f"[Approve] Adobe participantSetsInfo: {json.dumps(psets)}")

        # Build order → participant_set_id map (order is 1-indexed, matching set creation order)
        order_to_pset_id = {pset['order']: pset['id'] for pset in psets if 'order' in pset and 'id' in pset}
        logger.warning(f"[Approve] order_to_pset_id: {order_to_pset_id}")

        # Build Adobe formFields payload from signature data
        form_fields = []
        for field in signature_fields:
            recipient_index = field.get('recipientIndex', 0)

            # Map JS signer value → participant set order → participant set ID
            # director_then_client: signer 0,1 → order 1 (Director), signer 2 → order 2 (Client)
            # client_only: signer 0 → order 1 (Client)
            if agreement.flow_type == 'client_only':
                pset_order = 1
            elif agreement.flow_type == 'director_then_client':
                pset_order = 1 if recipient_index in (0, 1) else 2
            else:
                pset_order = recipient_index + 1

            assignee_id = order_to_pset_id.get(pset_order)
            if not assignee_id:
                logger.error(f"[Approve] No participant set found for order={pset_order}. Available: {order_to_pset_id}")
                return JsonResponse({'success': False, 'error': f'Participant set not found for signer order {pset_order}'}, status=400)

            locations = field.get('locations', [])
            if not locations:
                continue

            location = locations[0]

            raw_name = field.get('name', f"sig_p{location.get('pageNumber', 1)}_o{pset_order}")
            # Adobe Sign field names: only alphanumeric and underscores allowed
            safe_name = re.sub(r'[^A-Za-z0-9_]', '_', raw_name)

            coord_version = field.get('coord_version', 1)
            raw_top = float(location.get('top', 0))
            raw_left = float(location.get('left', 0))
            raw_width = float(location.get('width', 150))
            raw_height = float(location.get('height', 50))

            # Adobe Sign REST API v6 does not support INITIALS as a contentType for
            # programmatically placed fields — it silently converts them to DATA (text box).
            # All director fields must use SIGNATURE type.
            input_type = "SIGNATURE"
            content_type = "SIGNATURE"

            adobe_field = {
                "name": safe_name,
                "inputType": input_type,
                "contentType": content_type,
                "assignee": assignee_id,
                "required": field.get('required', True),
                "visible": True,
                "_coord_version": coord_version,  # kept for inversion step below
                "locations": [{
                    "pageNumber": int(location.get('pageNumber', 1)),
                    "top": raw_top,
                    "left": raw_left,
                    "width": raw_width,
                    "height": raw_height
                }]
            }
            form_fields.append(adobe_field)

        if not form_fields:
            return JsonResponse({
                'success': False,
                'error': 'No valid signature fields found.'
            }, status=400)

        # Read PDF page dimensions once — used for both coordinate inversion and clamping.
        _page_dims = {}
        try:
            from PyPDF2 import PdfReader
            pdf_path = agreement.document.file.path
            with open(pdf_path, 'rb') as _pdf_f:
                _pdf = PdfReader(_pdf_f)
                _page_dims = {}
                for i in range(len(_pdf.pages)):
                    page = _pdf.pages[i]
                    mb = page.mediabox
                    # CropBox defines the visible area PDF renderers use.
                    # If present, PDF.js renders only the CropBox region,
                    # so coordinates must be relative to CropBox, not MediaBox.
                    cb = page.cropbox if '/CropBox' in page else mb
                    _page_dims[i + 1] = {
                        'width': float(cb.width),
                        'height': float(cb.height),
                        'left': float(cb.left),
                        'bottom': float(cb.bottom),
                    }
                # Log page 1 boxes to detect crop offset
                if _page_dims:
                    p1 = _page_dims[1]
                    page0 = _pdf.pages[0]
                    mb0 = page0.mediabox
                    cb0 = page0.cropbox if '/CropBox' in page0 else mb0
                    logger.warning(
                        f"[Approve] Page 1 MediaBox: left={float(mb0.left):.2f} bottom={float(mb0.bottom):.2f} "
                        f"width={float(mb0.width):.2f} height={float(mb0.height):.2f} | "
                        f"CropBox: left={float(cb0.left):.2f} bottom={float(cb0.bottom):.2f} "
                        f"width={float(cb0.width):.2f} height={float(cb0.height):.2f}"
                    )
        except Exception as _dim_err:
            logger.warning(f"Could not read PDF page dimensions: {_dim_err}")

        # Adobe Sign `top` = Y from page BOTTOM (PDF user space, bottom-left origin).
        # PDF.js canvas `top` = Y from page TOP (top-left origin).
        # Invert: adobe_top = page_height - canvas_top
        for _field in form_fields:
            _field.pop('_coord_version', None)
            _locs = _field.get('locations', [])
            if not _locs:
                continue
            _loc = _locs[0]
            _pg = int(_loc.get('pageNumber', 1))
            _dim = _page_dims.get(_pg)
            if _dim:
                _canvas_top = float(_loc.get('top', 0))
                _adobe_top = _dim['height'] - _canvas_top
                logger.info(
                    f"[Approve] Field '{_field.get('name')}' pg={_pg}: "
                    f"canvas_top={_canvas_top:.1f} → adobe_top={_adobe_top:.1f} (pageH={_dim['height']:.2f})"
                )
                _loc['top'] = max(0.0, _adobe_top)

        # Log what we are about to send to Adobe for debugging
        logger.info(f"[Approve] Sending {len(form_fields)} form fields to Adobe for agreement {agreement.adobe_agreement_id}:")
        for _ff in form_fields:
            _loc = _ff.get('locations', [{}])[0]
            logger.info(
                f"  Field '{_ff.get('name')}' assignee={_ff.get('assignee')} "
                f"page={_loc.get('pageNumber')} top={_loc.get('top'):.1f} left={_loc.get('left'):.1f} "
                f"w={_loc.get('width'):.1f} h={_loc.get('height'):.1f}"
            )

        # --- Adobe Sign API calls (correct order) ---
        # Step 1: PUT /formFields on AUTHORING agreement
        AdobeAgreementService.put_form_fields(
            agreement_id=agreement.adobe_agreement_id,
            form_fields=form_fields
        )

        # Step 2: PUT /state → IN_PROCESS (sends to signers)
        AdobeAgreementService.send_agreement(agreement.adobe_agreement_id)

        # CRITICAL: Update adobe_status immediately after send succeeds.
        # This is irreversible in Adobe — if anything fails after this point,
        # the local DB must still reflect the Adobe reality.
        agreement.adobe_status = 'OUT_FOR_SIGNATURE'
        agreement.save(update_fields=['adobe_status'])

        # Step 3: For director_then_client, get signing URL for director
        signing_url = None
        if agreement.flow_type == 'director_then_client':
            director_email = AdobeAuthService.get_director_email()
            logger.info(f"Director email for signing URL: {director_email}")
            if director_email:
                signing_url = AdobeAgreementService.get_signing_url(
                    agreement.adobe_agreement_id,
                    signer_email=director_email
                )
            if not signing_url:
                logger.warning(f"Could not get signing URL for director on agreement {agreement.id}")

        # Save updated signature fields and approval status to DB
        agreement.signature_field_data = json.dumps(signature_fields)
        agreement.approve(user=request.user)
        agreement.sent_at = timezone.now()

        if not agreement.sent_date_client_vendor:
            agreement.sent_date_client_vendor = timezone.now()

        agreement.to_email = agreement.client_email
        agreement.cc_email_list = agreement.cc_emails

        agreement.save()

        logger.info(f"Agreement {agreement.id} approved and sent by {request.user.email}")

        if agreement.flow_type == 'client_only':
            messages.success(request, 'Agreement approved and sent to client for signing.')
        else:
            messages.success(request, 'Agreement activated. Click "Sign Document" to open the signing page.')

        response_data = {
            'success': True,
            'redirect_url': f'/integrations/adobe-sign/agreements/{agreement.id}/',
            'flow_type': agreement.flow_type,
        }
        if signing_url:
            response_data['signing_url'] = signing_url

        return JsonResponse(response_data)

    except AdobeSignException as e:
        logger.error(f"Adobe Sign error approving agreement {agreement_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to send agreement via Adobe Sign: {str(e)}'
        }, status=500)

    except Exception as e:
        logger.error(f"Error approving agreement {agreement_id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Failed to approve agreement'}, status=500)


@login_required
def agreement_reject(request, agreement_id):
    """
    Director rejects agreement and sends back to backoffice
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_director_or_admin(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    if not agreement.can_reject():
        messages.error(request, 'Agreement cannot be rejected')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    if request.method == 'POST':
        form = AgreementRejectForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['rejection_reason']
            notes = form.cleaned_data['rejection_notes']

            # Cancel the agreement in Adobe Sign if it was already submitted
            if agreement.adobe_agreement_id and agreement.adobe_agreement_id != 'PROCESSING':
                try:
                    AdobeAgreementService.cancel_agreement(
                        agreement.adobe_agreement_id,
                        reason=f'Rejected by director: {reason}',
                        notify_signers=False
                    )
                    agreement.adobe_status = 'CANCELLED'
                    agreement.adobe_agreement_id = None
                    logger.info(f"Agreement {agreement.id} cancelled in Adobe Sign on rejection")
                except AdobeSignException as e:
                    logger.warning(f"Could not cancel Adobe agreement on rejection: {e}")

            agreement.reject(reason=reason, notes=notes, user=request.user)

            messages.success(request, 'Agreement sent back to backoffice for corrections')
            return redirect('adobe_sign:pending_agreements')
    else:
        form = AgreementRejectForm()

    context = {
        'agreement': agreement,
        'form': form,
    }

    return render(request, 'adobe_sign/agreement_reject.html', context)


@login_required
def send_to_client(request, agreement_id):
    """DEPRECATED: Sending now happens via agreement_approve (PUT formFields + PUT state)."""
    return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)


# ============================================================================
# AGREEMENT DETAILS & ACTIONS
# ============================================================================

@login_required
def agreement_detail(request, agreement_id):
    """
    View agreement details with full audit trail.
    Backoffice users do NOT get Adobe view URLs (no direct Adobe access).
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_admin_or_backoffice(request.user):
        messages.error(request, 'Access denied')
        return redirect('accounts:dashboard')

    # Get latest events
    events = agreement.events.all()[:20]

    is_director = check_director_or_admin(request.user)

    # Only directors/admins get Adobe document view URL
    document_view_url = None
    if is_director and agreement.adobe_agreement_id:
        try:
            document_view_url = AdobeAgreementService.get_document_view_url(
                agreement.adobe_agreement_id
            )
        except Exception as e:
            logger.warning(f"Could not get document view URL for agreement {agreement_id}: {e}")

    context = {
        'agreement': agreement,
        'signers': agreement.signers.all(),
        'events': events,
        'document_view_url': document_view_url,
        'is_director_or_admin': is_director,
    }

    return render(request, 'adobe_sign/agreement_detail.html', context)


@login_required
def agreement_events(request, agreement_id):
    """
    View full event history for agreement
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_admin_or_backoffice(request.user):
        messages.error(request, 'Access denied')
        return redirect('accounts:dashboard')

    events = agreement.events.all()

    context = {
        'agreement': agreement,
        'events': events,
    }

    return render(request, 'adobe_sign/agreement_events.html', context)


@login_required
def download_signed_document(request, agreement_id):
    """
    Download signed PDF document
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_admin_or_backoffice(request.user):
        messages.error(request, 'Access denied')
        return redirect('accounts:dashboard')

    if not agreement.adobe_agreement_id:
        messages.error(request, 'Agreement not yet uploaded to Adobe')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    try:
        # Check if we already have a locally saved copy
        if agreement.signed_document_file:
            try:
                response = FileResponse(
                    agreement.signed_document_file.open('rb'),
                    content_type='application/pdf'
                )
                response['Content-Disposition'] = f'attachment; filename="{agreement.agreement_name}_signed.pdf"'
                return response
            except Exception:
                logger.warning(f"Local signed document missing for {agreement.id}, re-downloading from Adobe")

        # Download from Adobe
        pdf_content = AdobeAgreementService.get_signed_document(agreement.adobe_agreement_id)

        # Save locally for durability
        try:
            from django.core.files.base import ContentFile
            filename = f"{agreement.agreement_name}_signed.pdf"
            agreement.signed_document_file.save(filename, ContentFile(pdf_content), save=True)
            logger.info(f"Signed document saved locally for agreement {agreement.id}")
        except Exception as save_err:
            logger.warning(f"Could not save signed document locally: {save_err}")

        # Create response
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{agreement.agreement_name}_signed.pdf"'

        return response

    except Exception as e:
        logger.error(f"Error downloading signed document: {e}")
        messages.error(request, f'Error downloading document: {str(e)}')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)


# ============================================================================
# AJAX ENDPOINTS
# ============================================================================

@login_required
@require_POST
def sync_agreement_status(request, agreement_id):
    """
    Sync agreement status from Adobe Sign API
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_admin_or_backoffice(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)

    if not agreement.adobe_agreement_id:
        return JsonResponse({'success': False, 'error': 'Agreement not uploaded to Adobe'}, status=400)

    try:
        # Get status from Adobe
        adobe_status = AdobeAgreementService.get_agreement_status(agreement.adobe_agreement_id)

        agreement.adobe_status = adobe_status
        agreement.last_synced_at = timezone.now()

        # Check if completed
        if adobe_status in ['SIGNED', 'APPROVED', 'COMPLETED']:
            agreement.mark_completed()

        agreement.save()

        return JsonResponse({
            'success': True,
            'adobe_status': adobe_status,
            'approval_status': agreement.approval_status,
            'last_synced': agreement.last_synced_at.isoformat()
        })

    except Exception as e:
        logger.error(f"Error syncing status: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def get_authoring_url(request, agreement_id):
    """
    Fetch a fresh Adobe Sign authoring URL and redirect the user there.
    This is a server-side redirect, so it bypasses popup blockers entirely.
    Only available for agreements in AUTHORING / PENDING_APPROVAL state.
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_admin_or_backoffice(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    if not agreement.adobe_agreement_id:
        messages.error(request, 'Agreement has not been uploaded to Adobe Sign yet.')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    if agreement.adobe_status not in ('AUTHORING',) and agreement.approval_status != 'PENDING_APPROVAL':
        messages.error(request, 'Agreement is no longer in authoring state.')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)

    try:
        authoring_url = AdobeAgreementService.get_authoring_url(agreement.adobe_agreement_id)
        return redirect(authoring_url)
    except AdobeSignException as e:
        logger.error(f"Failed to get authoring URL for agreement {agreement_id}: {e}")
        messages.error(request, 'Could not retrieve Adobe Sign authoring link. Please try again.')
        return redirect('adobe_sign:agreement_detail', agreement_id=agreement_id)


@login_required
def get_director_signing_url(request, agreement_id):
    """
    AJAX: Fetch a fresh director signing URL for embedding in an iframe.
    Only available while agreement is APPROVED_SENT (out for director signing).
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_director_or_admin(request.user):
        return JsonResponse({'error': 'Access denied'}, status=403)

    if not agreement.adobe_agreement_id:
        return JsonResponse({'error': 'No Adobe agreement ID'}, status=400)

    if agreement.approval_status != 'APPROVED_SENT':
        return JsonResponse({'error': 'Agreement is not currently out for signing'}, status=400)

    try:
        signing_url = AdobeAgreementService.get_signing_url(agreement.adobe_agreement_id)
        if signing_url:
            return JsonResponse({'signing_url': signing_url})
        return JsonResponse({'error': 'Signing URL not yet available. Please try again in a moment.'}, status=404)
    except Exception as e:
        logger.error(f"Could not get director signing URL for agreement {agreement_id}: {e}")
        return JsonResponse({'error': 'Failed to fetch signing URL'}, status=500)


@login_required
@require_POST
def send_reminder(request, agreement_id):
    """
    Send reminder to pending signers
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_director_or_admin(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)

    if not agreement.adobe_agreement_id:
        return JsonResponse({'success': False, 'error': 'Agreement not uploaded to Adobe'}, status=400)

    try:
        AdobeAgreementService.remind_signers(agreement.adobe_agreement_id)
        messages.success(request, 'Reminder sent to pending signers')
        return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"Error sending reminder: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def cancel_agreement(request, agreement_id):
    """
    Cancel agreement
    """
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    if not check_director_or_admin(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)

    if not agreement.adobe_agreement_id:
        return JsonResponse({'success': False, 'error': 'Agreement not uploaded to Adobe'}, status=400)

    try:
        reason = request.POST.get('reason', 'Cancelled by admin')

        AdobeAgreementService.cancel_agreement(
            agreement.adobe_agreement_id,
            reason=reason,
            notify_signers=True
        )

        agreement.approval_status = 'CANCELLED'
        agreement.adobe_status = 'CANCELLED'
        agreement.save()

        messages.success(request, 'Agreement cancelled')
        return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"Error cancelling agreement: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ============================================================================
# SETTINGS
# ============================================================================

@login_required
def settings_view(request):
    """
    Adobe Sign settings — Integration Key, director info, defaults.
    """
    if not check_director_or_admin(request.user):
        messages.error(request, 'Access denied')
        return redirect('adobe_sign:dashboard')

    settings_obj = AdobeSignSettings.get_settings()

    if request.method == 'POST':
        # Integration key — encrypt via model method (don't use form.save for this)
        integration_key_raw = request.POST.get('integration_key', '').strip()
        if integration_key_raw:
            settings_obj.set_integration_key(integration_key_raw)

        # Director info
        settings_obj.director_name = request.POST.get('director_name', '').strip() or settings_obj.director_name
        settings_obj.director_email = request.POST.get('director_email', '').strip() or settings_obj.director_email
        settings_obj.director_title = request.POST.get('director_title', '').strip() or settings_obj.director_title

        # API base URL
        api_base_url = request.POST.get('api_base_url', '').strip()
        if api_base_url:
            settings_obj.api_base_url = api_base_url

        # Defaults
        try:
            settings_obj.default_expiration_days = int(request.POST.get('default_expiration_days', 30))
        except (ValueError, TypeError):
            pass
        settings_obj.default_reminder_frequency = request.POST.get('default_reminder_frequency', '') or settings_obj.default_reminder_frequency

        settings_obj.save()
        messages.success(request, 'Adobe Sign settings saved successfully.')
        return redirect('adobe_sign:settings')

    # Check configuration (uses DB-first resolution)
    is_configured, config_error = AdobeAuthService.validate_configuration()

    # Build webhook URL for display
    try:
        webhook_url = request.build_absolute_uri('/integrations/adobe-sign/webhook/')
    except Exception:
        webhook_url = 'https://yourdomain.com/integrations/adobe-sign/webhook/'

    context = {
        'settings': settings_obj,
        'is_configured': is_configured,
        'config_error': config_error,
        'integration_key_configured': bool(AdobeAuthService.get_integration_key()),
        'director_email_configured': bool(AdobeAuthService.get_director_email()),
        'webhook_url': webhook_url,
    }

    return render(request, 'adobe_sign/settings.html', context)


@login_required
@require_POST
def test_connection(request):
    """
    AJAX: Test Adobe Sign API connection using the saved integration key.
    Calls GET /baseUris to verify the key works, then GET /users/me for account info.
    """
    import requests as http_requests

    if not check_director_or_admin(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)

    try:
        integration_key = AdobeAuthService.get_integration_key()
        if not integration_key:
            return JsonResponse({'success': False, 'error': 'No Integration Key configured. Save your key first.'})

        settings_obj = AdobeSignSettings.get_settings()
        base_url = settings_obj.api_base_url.rstrip('/')

        headers = {
            'Authorization': f'Bearer {integration_key}',
            'Content-Type': 'application/json',
        }

        # Test 1: GET /baseUris (validates the key)
        resp = http_requests.get(f'{base_url}/baseUris', headers=headers, timeout=15)
        if resp.status_code == 401:
            return JsonResponse({'success': False, 'error': 'Invalid Integration Key (401 Unauthorized). Check key and try again.'})
        if resp.status_code != 200:
            return JsonResponse({'success': False, 'error': f'API returned HTTP {resp.status_code}: {resp.text[:200]}'})

        # Test 2: GET /users/me (get account email)
        api_url = resp.json().get('apiAccessPoint', base_url.rsplit('/api/', 1)[0] + '/')
        api_url = api_url.rstrip('/') + '/api/rest/v6'
        resp2 = http_requests.get(f'{api_url}/users/me', headers=headers, timeout=15)
        email = ''
        if resp2.status_code == 200:
            email = resp2.json().get('email', '')

        return JsonResponse({'success': True, 'email': email})

    except http_requests.exceptions.Timeout:
        return JsonResponse({'success': False, 'error': 'Connection timed out. Check your API Base URL.'})
    except http_requests.exceptions.ConnectionError:
        return JsonResponse({'success': False, 'error': 'Cannot reach Adobe Sign servers. Check your internet connection and API Base URL.'})
    except Exception as e:
        logger.error(f'Test connection error: {e}', exc_info=True)
        return JsonResponse({'success': False, 'error': f'Unexpected error: {str(e)}'})


# ============================================================================
# WEBHOOK HANDLER
# ============================================================================

from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

@csrf_exempt
@require_POST
def adobe_webhook(request):
    """
    Webhook endpoint for Adobe Sign events with full security

    Fixes:
    - C2: Webhook signature verification
    - C3: Out-of-order event processing
    - C4: Idempotency protection
    - H3: Transaction handling
    """
    import hmac
    import hashlib
    import json
    from django.db import transaction
    from django.conf import settings

    # C2 FIX: Verify webhook signature
    webhook_secret = getattr(settings, 'ADOBE_SIGN_WEBHOOK_SECRET', None)

    if not webhook_secret:
        logger.error('ADOBE_SIGN_WEBHOOK_SECRET not configured')
        return HttpResponse(status=500)

    # Get signature from header
    signature_header = request.META.get('HTTP_X_ADOBESIGN_SIGNATURE', '')

    if not signature_header:
        logger.warning('Webhook missing X-ADOBESIGN-SIGNATURE header')
        return HttpResponse(status=401)

    # Calculate expected signature
    body = request.body.decode('utf-8')
    expected_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        body.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Timing-safe comparison
    if not hmac.compare_digest(signature_header, expected_signature):
        logger.warning(f'Invalid webhook signature from IP: {request.META.get("REMOTE_ADDR")}')
        return HttpResponse(status=401)

    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error(f'Webhook JSON decode error: {e}')
        return HttpResponse(status=400)

    # Extract event details
    event_type = payload.get('event')
    agreement_id = payload.get('agreement', {}).get('id')
    webhook_id = payload.get('webhookId')
    participant_email = payload.get('participantInfo', {}).get('email', '')

    if not agreement_id:
        logger.warning('Webhook received without agreement ID')
        return HttpResponse(status=200)

    if not webhook_id:
        logger.warning('Webhook received without webhookId')
        return HttpResponse(status=400)

    # C4 FIX: Check idempotency - prevent duplicate processing
    event_exists = AgreementEvent.objects.filter(
        adobe_event_id=webhook_id
    ).exists()

    if event_exists:
        logger.info(f'Webhook {webhook_id} already processed (retry), returning 200')
        return HttpResponse(status=200)

    # Find agreement
    try:
        agreement = AdobeAgreement.objects.get(adobe_agreement_id=agreement_id)
    except AdobeAgreement.DoesNotExist:
        logger.warning(f'Webhook received for unknown agreement: {agreement_id}')
        return HttpResponse(status=200)

    # H3 FIX: Wrap everything in transaction
    try:
        with transaction.atomic():
            # Lock agreement row to prevent concurrent webhook processing
            agreement = AdobeAgreement.objects.select_for_update().get(
                adobe_agreement_id=agreement_id
            )

            # Store event FIRST with webhook_id for idempotency
            event = AgreementEvent.objects.create(
                agreement=agreement,
                event_type=event_type,
                adobe_event_id=webhook_id,
                event_date=timezone.now(),
                participant_email=participant_email,
                raw_payload=payload,
                description=f'Event {event_type} from Adobe Sign'
            )

            # Process event based on type
            if event_type == 'ESIGNED':
                # Participant signed
                logger.info(f'Agreement {agreement.id}: {participant_email} signed')

                # Update signer status
                Signer.objects.filter(
                    agreement=agreement,
                    email=participant_email
                ).update(
                    status='SIGNED',
                    signed_at=timezone.now()
                )

                # Update event description
                event.description = f'{participant_email} signed the agreement'
                event.save()

            elif event_type == 'AGREEMENT_ALL_SIGNED':
                # All signers signed
                logger.info(f'Agreement {agreement.id}: All parties signed')

                # Update all signers to SIGNED
                Signer.objects.filter(agreement=agreement).update(
                    status='SIGNED',
                    signed_at=timezone.now()
                )

                event.description = 'All parties have signed'
                event.save()

            elif event_type == 'AGREEMENT_WORKFLOW_COMPLETED':
                # C3 FIX: Validate all signers actually signed before marking complete
                pending_signers = Signer.objects.filter(
                    agreement=agreement,
                    status__in=['WAITING_FOR_MY_SIGNATURE', 'NOT_YET_VISIBLE', 'OUT_FOR_SIGNATURE']
                ).count()

                if pending_signers > 0:
                    # Not all signers signed yet - ESIGNED events haven't arrived
                    logger.warning(
                        f'WORKFLOW_COMPLETED received but {pending_signers} signers still pending. '
                        f'Out-of-order event detected. Delaying completion.'
                    )
                    event.description = f'Workflow completed notification (delayed - {pending_signers} signers pending)'
                    event.save()
                else:
                    # All signers signed, safe to mark complete
                    logger.info(f'Agreement {agreement.id}: Workflow completed')
                    agreement.mark_completed()
                    event.description = 'Agreement workflow completed - all signatures collected'
                    event.save()

            elif event_type == 'AGREEMENT_REJECTED':
                # Agreement rejected by signer
                logger.info(f'Agreement {agreement.id}: Rejected by {participant_email}')

                event.description = f'Agreement rejected by {participant_email}'
                event.save()

            elif event_type == 'AGREEMENT_EXPIRED':
                # Agreement expired
                logger.info(f'Agreement {agreement.id}: Expired')

                agreement.adobe_status = 'EXPIRED'
                agreement.save()

                event.description = 'Agreement expired before all signatures collected'
                event.save()

            elif event_type == 'AGREEMENT_RECALLED':
                # Agreement recalled/cancelled
                logger.info(f'Agreement {agreement.id}: Recalled')

                agreement.adobe_status = 'RECALLED'
                agreement.save()

                event.description = 'Agreement recalled/cancelled'
                event.save()

            # Update last synced timestamp
            agreement.last_synced_at = timezone.now()
            agreement.save()

            logger.info(f'Webhook processed successfully: {agreement.id} - {event_type}')
            return HttpResponse(status=200)

    except Exception as e:
        logger.error(f'Webhook processing error: {e}', exc_info=True)
        return HttpResponse(status=500)
