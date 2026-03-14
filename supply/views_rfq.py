"""
RFQ (Request for Quotation) Views
Handles RFQ management and sending to vendors via Gmail
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.utils import timezone
from django.http import JsonResponse
from accounts.permissions import require_role
from gmail.services import EmailService
from gmail.models import GmailToken
from .models import RFQ, RFQVendorMapping, VendorContact, VendorCard
from accounts.models import User


@login_required
@require_role('admin', 'director', 'supply_manager', 'sales_manager', 'crm_executive')
def rfq_list(request):
    """
    List all RFQs with filters
    """
    rfqs = RFQ.objects.annotate(
        vendors_count=Count('vendor_mappings')
    ).select_related('created_by')

    # Search
    search = request.GET.get('search', '').strip()
    if search:
        rfqs = rfqs.filter(
            Q(rfq_id__icontains=search) |
            Q(city__icontains=search) |
            Q(product__icontains=search)
        )

    # Status filter
    status = request.GET.get('status', '')
    if status:
        rfqs = rfqs.filter(status=status)

    # City filter
    city = request.GET.get('city', '')
    if city:
        rfqs = rfqs.filter(city__icontains=city)

    # Pagination
    paginator = Paginator(rfqs, 20)
    page = request.GET.get('page', 1)
    rfqs_page = paginator.get_page(page)

    # Get unique cities for filter dropdown
    cities = RFQ.objects.values_list('city', flat=True).distinct().order_by('city')

    context = {
        'rfqs': rfqs_page,
        'search': search,
        'status': status,
        'city': city,
        'cities': cities,
        'total_count': rfqs.count(),
        'page_title': 'RFQ Management'
    }

    return render(request, 'supply/rfq_list.html', context)


@login_required
@require_role('admin', 'director', 'supply_manager', 'sales_manager')
def rfq_create(request):
    """
    Create new RFQ
    """
    if request.method == 'POST':
        try:
            rfq = RFQ.objects.create(
                city=request.POST.get('city', ''),
                area_required_sqft=int(request.POST.get('area_required_sqft') or 0),
                product=request.POST.get('product', ''),
                tenure=request.POST.get('tenure', ''),
                remarks=request.POST.get('remarks', ''),
                storage_rate_sqft=request.POST.get('storage_rate_sqft') or None,
                storage_rate_pallet=request.POST.get('storage_rate_pallet') or None,
                storage_rate_mt=request.POST.get('storage_rate_mt') or None,
                handling_rate_pallet=request.POST.get('handling_rate_pallet') or None,
                status='open',
                created_by=request.user
            )

            messages.success(request, f'RFQ {rfq.rfq_id} created successfully!')
            return redirect('supply:rfq_detail', rfq_id=rfq.rfq_id)

        except Exception as e:
            messages.error(request, f'Failed to create RFQ: {str(e)}')

    context = {
        'action': 'Create',
        'page_title': 'Create New RFQ'
    }

    return render(request, 'supply/rfq_form.html', context)


@login_required
@require_role('admin', 'director', 'supply_manager', 'sales_manager')
def rfq_edit(request, rfq_id):
    """
    Edit existing RFQ
    """
    rfq = get_object_or_404(RFQ, rfq_id=rfq_id)

    if request.method == 'POST':
        try:
            rfq.city = request.POST.get('city')
            rfq.area_required_sqft = request.POST.get('area_required_sqft')
            rfq.product = request.POST.get('product')
            rfq.tenure = request.POST.get('tenure', '')
            rfq.remarks = request.POST.get('remarks', '')
            rfq.storage_rate_sqft = request.POST.get('storage_rate_sqft') or None
            rfq.storage_rate_pallet = request.POST.get('storage_rate_pallet') or None
            rfq.storage_rate_mt = request.POST.get('storage_rate_mt') or None
            rfq.handling_rate_pallet = request.POST.get('handling_rate_pallet') or None
            rfq.save()

            messages.success(request, f'RFQ {rfq.rfq_id} updated successfully!')
            return redirect('supply:rfq_detail', rfq_id=rfq.rfq_id)

        except Exception as e:
            messages.error(request, f'Failed to update RFQ: {str(e)}')

    context = {
        'rfq': rfq,
        'action': 'Update',
        'page_title': f'Edit RFQ - {rfq.rfq_id}'
    }

    return render(request, 'supply/rfq_form.html', context)


@login_required
@require_role('admin', 'director', 'supply_manager', 'sales_manager', 'crm_executive')
def rfq_detail(request, rfq_id):
    """
    View RFQ details and vendor mappings
    """
    rfq = get_object_or_404(RFQ, rfq_id=rfq_id)

    # Get vendor mappings
    mappings = RFQVendorMapping.objects.filter(rfq=rfq).select_related(
        'vendor_contact',
        'vendor_contact__vendor_code',
        'point_of_contact',
        'sent_by'
    ).order_by('-sent_at')

    # Stats
    total_sent = mappings.count()
    responded = mappings.filter(response_received=True).count()
    pending = mappings.filter(follow_up_status='pending').count()

    context = {
        'rfq': rfq,
        'mappings': mappings,
        'total_sent': total_sent,
        'responded': responded,
        'pending': pending,
        'response_rate': rfq.response_rate,
        'page_title': f'RFQ Detail - {rfq.rfq_id}'
    }

    return render(request, 'supply/rfq_detail.html', context)


@login_required
@require_role('admin', 'director', 'supply_manager', 'sales_manager')
def rfq_send_to_vendors(request, rfq_id):
    """
    Send RFQ to selected vendors via Gmail
    Main feature - integrates with Gmail EmailService
    """
    rfq = get_object_or_404(RFQ, rfq_id=rfq_id)

    if request.method == 'POST':
        try:
            # Get form data
            vendor_contact_ids = request.POST.getlist('vendor_contacts')
            deadline_date = request.POST.get('deadline_date')
            poc_id = request.POST.get('point_of_contact')
            sender_email = request.POST.get('sender_email')

            if not vendor_contact_ids:
                messages.error(request, 'Please select at least one vendor.')
                return redirect('supply:rfq_send', rfq_id=rfq_id)

            if not sender_email:
                messages.error(request, 'Please select a Gmail account to send from.')
                return redirect('supply:rfq_send', rfq_id=rfq_id)

            # Permission check
            if not EmailService.can_send_from_account(request.user, sender_email):
                messages.error(request, "You don't have permission to send from this Gmail account.")
                return redirect('supply:rfq_send', rfq_id=rfq_id)

            # Get POC
            poc = User.objects.get(id=poc_id) if poc_id else None
            reply_to_email = poc.email if poc else "saral@godamwale.com"

            # Get vendor contacts
            vendor_contacts = VendorContact.objects.filter(
                id__in=vendor_contact_ids,
                vendor_contact_is_active=True
            ).select_related('vendor_code')

            success_count = 0
            failed_vendors = []

            for contact in vendor_contacts:
                # Prepare email content
                subject = f"{rfq.rfq_id} - {rfq.area_required_sqft} Sq Ft in {rfq.city}"

                # Render HTML email
                html_body = render_to_string('supply/rfq_email.html', {
                    'rfq': rfq,
                    'deadline': deadline_date,
                    'poc': poc,
                    'sender': request.user,
                    'vendor': contact
                })

                # Plain text version
                plain_text = f"""
Dear Sir/Ma'am,

We are pleased to share an RFQ for your quote.

RFQ ID: {rfq.rfq_id}
City: {rfq.city}
Area Required: {rfq.area_required_sqft} Sq Ft
Product: {rfq.product}
Tenure: {rfq.get_tenure_display() if rfq.tenure else 'N/A'}

{rfq.remarks}

Please help us with your rates by {deadline_date} EOD.

Regards,
{request.user.get_full_name()}
                """.strip()

                # CC emails from JSONField
                cc_emails = ', '.join(contact.rfq_cc_emails) if contact.rfq_cc_emails else ''

                # Send email
                success = EmailService.send_email(
                    user=request.user,
                    sender_email=sender_email,
                    to_email=contact.vendor_contact_email,
                    subject=subject,
                    message_text=plain_text,
                    html_body=html_body,
                    cc=cc_emails,
                    reply_to=reply_to_email
                )

                if success:
                    # Create tracking record
                    RFQVendorMapping.objects.create(
                        rfq=rfq,
                        vendor_contact=contact,
                        sent_from_account=sender_email,
                        sent_to_email=contact.vendor_contact_email,
                        sent_cc_emails=contact.rfq_cc_emails if contact.rfq_cc_emails else [],
                        deadline_date=deadline_date,
                        point_of_contact=poc,
                        sent_by=request.user,
                        follow_up_status='pending'
                    )
                    success_count += 1
                else:
                    failed_vendors.append(contact.vendor_code.vendor_short_name)

            # Success message
            if success_count > 0:
                messages.success(
                    request,
                    f'RFQ {rfq.rfq_id} sent successfully to {success_count} vendor(s)!'
                )

            if failed_vendors:
                messages.warning(
                    request,
                    f'Failed to send to: {", ".join(failed_vendors)}'
                )

            return redirect('supply:rfq_detail', rfq_id=rfq.rfq_id)

        except Exception as e:
            messages.error(request, f'Error sending RFQ: {str(e)}')
            return redirect('supply:rfq_send', rfq_id=rfq_id)

    # GET request - show send dialog
    # Get available sender accounts based on user role
    sender_accounts = EmailService.get_available_sender_accounts(request.user)

    # Get RFQ vendor contacts (marked as is_rfq_contact=True)
    vendor_contacts = VendorContact.objects.filter(
        is_rfq_contact=True,
        vendor_contact_is_active=True
    ).select_related('vendor_code').order_by('vendor_code__vendor_short_name')

    # Get POC users (sales_manager, supply_manager, admin)
    pocs = User.objects.filter(
        is_active=True,
        role__in=['sales_manager', 'supply_manager', 'crm_executive', 'admin', 'director']
    ).order_by('first_name')

    # Get already sent vendors
    already_sent = RFQVendorMapping.objects.filter(rfq=rfq).values_list('vendor_contact_id', flat=True)

    context = {
        'rfq': rfq,
        'sender_accounts': sender_accounts,
        'vendor_contacts': vendor_contacts,
        'pocs': pocs,
        'already_sent': list(already_sent),
        'page_title': f'Send RFQ - {rfq.rfq_id}'
    }

    return render(request, 'supply/rfq_send.html', context)


@login_required
@require_role('admin', 'director', 'supply_manager')
def rfq_toggle_status(request, rfq_id):
    """
    Change RFQ status (Open/Closed/Postponed)
    """
    if request.method == 'POST':
        rfq = get_object_or_404(RFQ, rfq_id=rfq_id)
        new_status = request.POST.get('status')

        if new_status in ['open', 'closed', 'postponed']:
            rfq.status = new_status
            rfq.save()
            messages.success(request, f'RFQ {rfq.rfq_id} status changed to {rfq.get_status_display()}')
        else:
            messages.error(request, 'Invalid status')

    return redirect('supply:rfq_detail', rfq_id=rfq_id)


@login_required
def get_rfq_vendor_contacts(request):
    """
    AJAX endpoint: Get RFQ vendor contacts with search
    """
    search = request.GET.get('search', '').strip()

    contacts = VendorContact.objects.filter(
        is_rfq_contact=True,
        vendor_contact_is_active=True
    ).select_related('vendor_code')

    if search:
        contacts = contacts.filter(
            Q(vendor_code__vendor_short_name__icontains=search) |
            Q(rfq_cities__icontains=search) |
            Q(vendor_contact_email__icontains=search)
        )

    data = [
        {
            'id': contact.id,
            'vendor_name': contact.vendor_code.vendor_short_name,
            'email': contact.vendor_contact_email,
            'cities': contact.rfq_cities,
            'cc_count': len(contact.rfq_cc_emails) if contact.rfq_cc_emails else 0
        }
        for contact in contacts[:50]  # Limit to 50 results
    ]

    return JsonResponse({'contacts': data})
