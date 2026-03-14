from django.db.models.signals import post_save, post_delete
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.utils import timezone

from .utils import log_activity_direct
from .middleware import get_current_request


# ── Auth signals ─────────────────────────────────────────────────────────────

@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    log_activity_direct(
        user=user, source='web',
        action_category='auth', action_type='login',
        module='accounts', description=f'{user.get_full_name() or user.username} logged in',
        request=request,
    )


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user:
        log_activity_direct(
            user=user, source='web',
            action_category='auth', action_type='logout',
            module='accounts', description=f'{user.get_full_name() or user.username} logged out',
            request=request,
        )


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request, **kwargs):
    from .models import ActivityLog
    from .middleware import get_client_ip

    username_tried = credentials.get('username', '')
    now = timezone.now()
    try:
        ActivityLog.objects.create(
            user=None,
            user_display_name=f'Failed login: {username_tried}',
            role_snapshot='anonymous',
            source='web',
            action_category='auth',
            action_type='login_failed',
            module='accounts',
            description=f'Failed login attempt for username: {username_tried}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            url_path=request.path,
            request_method=request.method,
            extra_data={'username_tried': username_tried},
            is_suspicious=True,
            timestamp=now,
            date=now.date(),
        )
    except Exception:
        pass


# ── Generic model log helper ──────────────────────────────────────────────────

def _log_model(*, instance, created, action_type_create, action_type_update,
               module, object_type, object_repr_fn, description_fn,
               user_field='entered_by', extra_data_fn=None,
               related_type='', related_id_fn=None):
    """Generic helper to log a model post_save."""
    request = get_current_request()
    user = getattr(instance, user_field, None)
    if user is None:
        user = getattr(instance, 'created_by', None)
    if user is None:
        user = getattr(instance, 'raised_by', None)

    action_type = action_type_create if created else action_type_update
    category = 'create' if created else 'update'

    extra = extra_data_fn(instance) if extra_data_fn else {}
    related_id = related_id_fn(instance) if related_id_fn else None

    log_activity_direct(
        user=user,
        source='web' if request else 'signal',
        action_category=category,
        action_type=action_type,
        module=module,
        object_type=object_type,
        object_id=instance.pk,
        object_repr=object_repr_fn(instance),
        related_object_type=related_type,
        related_object_id=related_id,
        description=description_fn(instance, created),
        request=request,
        extra_data=extra,
    )


# ── Operations signals ────────────────────────────────────────────────────────

try:
    from operations.models import DailySpaceUtilization

    @receiver(post_save, sender=DailySpaceUtilization)
    def log_daily_entry(sender, instance, created, **kwargs):
        _log_model(
            instance=instance, created=created,
            action_type_create='daily_entry_created',
            action_type_update='daily_entry_updated',
            module='operations',
            object_type='DailySpaceUtilization',
            object_repr_fn=lambda i: f'Daily Entry — {i.project.project_code} ({i.entry_date})',
            description_fn=lambda i, c: (
                f'{"Created" if c else "Updated"} daily entry for {i.project.project_code} on {i.entry_date}'
            ),
            user_field='entered_by',
            related_type='ProjectCode',
            related_id_fn=lambda i: i.project_id,
            extra_data_fn=lambda i: {
                'project_code': i.project.project_code,
                'entry_date': str(i.entry_date),
                'space_utilized': str(i.space_utilized),
                'inventory_value': str(i.inventory_value),
            },
        )
except ImportError:
    pass


try:
    from operations.models import DisputeLog

    @receiver(post_save, sender=DisputeLog)
    def log_dispute(sender, instance, created, **kwargs):
        _log_model(
            instance=instance, created=created,
            action_type_create='dispute_raised',
            action_type_update='dispute_updated',
            module='operations',
            object_type='DisputeLog',
            object_repr_fn=lambda i: f'Dispute — {i.title or i.pk}',
            description_fn=lambda i, c: (
                f'{"Raised" if c else "Updated"} dispute: {i.title or i.pk}'
            ),
            user_field='raised_by',
            related_type='ProjectCode',
            related_id_fn=lambda i: i.project_id,
            extra_data_fn=lambda i: {
                'project_code': i.project.project_code if i.project_id else '',
                'status': str(i.status) if i.status_id else '',
                'priority': str(i.priority) if i.priority_id else '',
            },
        )
except ImportError:
    pass


try:
    from operations.models_adhoc import AdhocBillingEntry

    @receiver(post_save, sender=AdhocBillingEntry)
    def log_adhoc_billing(sender, instance, created, **kwargs):
        _log_model(
            instance=instance, created=created,
            action_type_create='adhoc_billing_created',
            action_type_update='adhoc_billing_updated',
            module='operations',
            object_type='AdhocBillingEntry',
            object_repr_fn=lambda i: f'Adhoc Billing — {i.project.project_code} ({i.event_date})',
            description_fn=lambda i, c: (
                f'{"Created" if c else "Updated"} adhoc billing for {i.project.project_code}'
            ),
            user_field='created_by',
            related_type='ProjectCode',
            related_id_fn=lambda i: i.project_id,
            extra_data_fn=lambda i: {
                'project_code': i.project.project_code,
                'event_date': str(i.event_date),
                'total_client_amount': str(i.total_client_amount or 0),
            },
        )
except ImportError:
    pass


# ── Operations — Porter Invoice signals ──────────────────────────────────────

try:
    from operations.models_porter_invoice import PorterInvoiceSession

    @receiver(post_save, sender=PorterInvoiceSession)
    def log_porter_invoice_session(sender, instance, created, **kwargs):
        request = get_current_request()
        log_activity_direct(
            user=instance.created_by,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='porter_invoice_session_created' if created else 'porter_invoice_session_updated',
            module='operations',
            object_type='PorterInvoiceSession',
            object_id=instance.pk,
            object_repr=f'Porter Invoice Session #{instance.pk} ({instance.session_type})',
            description=f'{"Created" if created else "Updated"} porter invoice session #{instance.pk} — status: {instance.status}',
            request=request,
            extra_data={
                'session_type': instance.session_type,
                'status': instance.status,
                'total_files': instance.total_files,
                'success_count': instance.success_count,
                'error_count': instance.error_count,
            },
        )
except ImportError:
    pass


# ── Operations — MIS signals ──────────────────────────────────────────────────

try:
    from operations.models import DailyMISLog

    @receiver(post_save, sender=DailyMISLog)
    def log_mis(sender, instance, created, **kwargs):
        request = get_current_request()
        user = instance.sent_by
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='update',
            action_type='mis_sent' if instance.mis_sent else 'mis_unmarked',
            module='operations',
            object_type='DailyMISLog',
            object_id=instance.pk,
            object_repr=f'MIS — {instance.project.project_code if instance.project_id else instance.pk} ({instance.log_date})',
            description=f'MIS {"sent" if instance.mis_sent else "unmarked"} for {instance.log_date}',
            request=request,
            extra_data={
                'log_date': str(instance.log_date),
                'mis_sent': instance.mis_sent,
                'remarks': instance.remarks or '',
            },
        )
except ImportError:
    pass


# ── Operations — Escalation signals ──────────────────────────────────────────

try:
    from operations.models_agreements import EscalationLog

    @receiver(post_save, sender=EscalationLog)
    def log_escalation(sender, instance, created, **kwargs):
        if not created:
            return
        request = get_current_request()
        log_activity_direct(
            user=instance.performed_by,
            source='web' if request else 'signal',
            action_category='update',
            action_type='escalation_action_logged',
            module='operations',
            object_type='EscalationLog',
            object_id=instance.pk,
            object_repr=f'Escalation — {str(instance)}',
            description=f'Escalation action logged: {str(instance)}',
            request=request,
            extra_data={
                'action_date': str(instance.action_date),
                'email_sent_to': instance.email_sent_to or '',
            },
        )
except ImportError:
    pass


# ── Operations — Agreement Renewal signals ────────────────────────────────────

try:
    from operations.models_agreements import AgreementRenewalLog

    @receiver(post_save, sender=AgreementRenewalLog)
    def log_agreement_renewal(sender, instance, created, **kwargs):
        if not created:
            return
        request = get_current_request()
        log_activity_direct(
            user=instance.performed_by,
            source='web' if request else 'signal',
            action_category='update',
            action_type='agreement_renewal_action_logged',
            module='operations',
            object_type='AgreementRenewalLog',
            object_id=instance.pk,
            object_repr=f'Agreement Renewal — {str(instance)}',
            description=f'Agreement renewal action logged: {str(instance)}',
            request=request,
            extra_data={
                'action_date': str(instance.action_date),
                'email_sent_to': instance.email_sent_to or '',
            },
        )
except ImportError:
    pass


# ── Supply signals ────────────────────────────────────────────────────────────

try:
    from supply.models import VendorCard

    @receiver(post_save, sender=VendorCard)
    def log_vendor(sender, instance, created, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='vendor_created' if created else 'vendor_updated',
            module='supply',
            object_type='VendorCard',
            object_id=instance.pk,
            object_repr=f'Vendor — {instance.vendor_name if hasattr(instance, "vendor_name") else instance.pk}',
            description=f'{"Created" if created else "Updated"} vendor: {instance.vendor_name if hasattr(instance, "vendor_name") else instance.pk}',
            request=request,
        )

    @receiver(post_delete, sender=VendorCard)
    def log_vendor_delete(sender, instance, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='delete',
            action_type='vendor_deleted',
            module='supply',
            object_type='VendorCard',
            object_id=instance.pk,
            object_repr=f'Vendor — {instance.vendor_name if hasattr(instance, "vendor_name") else instance.pk}',
            description=f'Deleted vendor: {instance.vendor_name if hasattr(instance, "vendor_name") else instance.pk}',
            request=request,
        )
except ImportError:
    pass


try:
    from supply.models import WarehouseProfile

    @receiver(post_save, sender=WarehouseProfile)
    def log_warehouse(sender, instance, created, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='warehouse_created' if created else 'warehouse_updated',
            module='supply',
            object_type='WarehouseProfile',
            object_id=instance.pk,
            object_repr=f'Warehouse — {instance.warehouse_name if hasattr(instance, "warehouse_name") else instance.pk}',
            description=f'{"Created" if created else "Updated"} warehouse: {instance.warehouse_name if hasattr(instance, "warehouse_name") else instance.pk}',
            request=request,
        )

    @receiver(post_delete, sender=WarehouseProfile)
    def log_warehouse_delete(sender, instance, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='delete',
            action_type='warehouse_deleted',
            module='supply',
            object_type='WarehouseProfile',
            object_id=instance.pk,
            object_repr=f'Warehouse — {instance.warehouse_name if hasattr(instance, "warehouse_name") else instance.pk}',
            description=f'Deleted warehouse: {instance.warehouse_name if hasattr(instance, "warehouse_name") else instance.pk}',
            request=request,
        )
except ImportError:
    pass


try:
    from supply.models import Location

    @receiver(post_save, sender=Location)
    def log_location(sender, instance, created, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='location_created' if created else 'location_updated',
            module='supply',
            object_type='Location',
            object_id=instance.pk,
            object_repr=f'Location — {str(instance)}',
            description=f'{"Created" if created else "Updated"} location: {str(instance)}',
            request=request,
        )

    @receiver(post_delete, sender=Location)
    def log_location_delete(sender, instance, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='delete',
            action_type='location_deleted',
            module='supply',
            object_type='Location',
            object_id=instance.pk,
            object_repr=f'Location — {str(instance)}',
            description=f'Deleted location: {str(instance)}',
            request=request,
        )
except ImportError:
    pass


# ── Accounts — Impersonation signals ─────────────────────────────────────────

try:
    from accounts.models import ImpersonationLog

    @receiver(post_save, sender=ImpersonationLog)
    def log_impersonation(sender, instance, created, **kwargs):
        if created:
            log_activity_direct(
                user=instance.admin,
                source='web',
                action_category='permission_denied',
                action_type='impersonation_started',
                module='accounts',
                object_type='User',
                object_id=instance.impersonated_user_id,
                object_repr=f'User — {instance.impersonated_user.get_full_name() or instance.impersonated_user.username}',
                description=f'{instance.admin.get_full_name()} started impersonating {instance.impersonated_user.get_full_name()}',
                extra_data={'impersonation_log_id': instance.pk},
            )
        elif instance.ended_at:
            log_activity_direct(
                user=instance.admin,
                source='web',
                action_category='auth',
                action_type='impersonation_ended',
                module='accounts',
                object_type='User',
                object_id=instance.impersonated_user_id,
                object_repr=f'User — {instance.impersonated_user.get_full_name() or instance.impersonated_user.username}',
                description=f'{instance.admin.get_full_name()} ended impersonation of {instance.impersonated_user.get_full_name()}',
                extra_data={'impersonation_log_id': instance.pk},
            )
except ImportError:
    pass


# ── Projects signals ──────────────────────────────────────────────────────────

try:
    from projects.models import ProjectCode

    @receiver(post_save, sender=ProjectCode)
    def log_project(sender, instance, created, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='project_created' if created else 'project_updated',
            module='projects',
            object_type='ProjectCode',
            object_id=instance.pk,
            object_repr=f'Project — {instance.project_code}',
            description=f'{"Created" if created else "Updated"} project {instance.project_code}',
            request=request,
            extra_data={
                'project_code': instance.project_code,
                'status': instance.status if hasattr(instance, 'status') else '',
            },
        )
except ImportError:
    pass


# ── Quotation signals ─────────────────────────────────────────────────────────

try:
    from projects.models_quotation import Quotation

    @receiver(post_save, sender=Quotation)
    def log_quotation(sender, instance, created, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='quotation_created' if created else 'quotation_updated',
            module='projects',
            object_type='Quotation',
            object_id=instance.pk,
            object_repr=f'Quotation — {instance.quotation_number if hasattr(instance, "quotation_number") else instance.pk}',
            description=f'{"Created" if created else "Updated"} quotation {instance.pk}',
            request=request,
        )
except ImportError:
    pass


# ── Operations — LorryReceipt signals ────────────────────────────────────────

try:
    from operations.models_lr import LorryReceipt

    @receiver(post_save, sender=LorryReceipt)
    def log_lr(sender, instance, created, **kwargs):
        user = instance.created_by if created else getattr(instance, 'last_modified_by', instance.created_by)
        request = get_current_request()
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='lr_created' if created else 'lr_updated',
            module='operations',
            object_type='LorryReceipt',
            object_id=instance.pk,
            object_repr=f'LR #{instance.pk}',
            description=f'{"Created" if created else "Updated"} lorry receipt #{instance.pk}',
            request=request,
        )

    @receiver(post_delete, sender=LorryReceipt)
    def log_lr_delete(sender, instance, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else instance.created_by
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='delete',
            action_type='lr_deleted',
            module='operations',
            object_type='LorryReceipt',
            object_id=instance.pk,
            object_repr=f'LR #{instance.pk}',
            description=f'Deleted lorry receipt #{instance.pk}',
            request=request,
        )
except ImportError:
    pass


# ── Operations — MonthlyBilling signals ──────────────────────────────────────

try:
    from operations.models import MonthlyBilling

    @receiver(post_save, sender=MonthlyBilling)
    def log_monthly_billing(sender, instance, created, **kwargs):
        user = instance.created_by if created else getattr(instance, 'submitted_by', instance.created_by)
        request = get_current_request()
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='monthly_billing_created' if created else 'monthly_billing_updated',
            module='operations',
            object_type='MonthlyBilling',
            object_id=instance.pk,
            object_repr=f'Monthly Billing — {instance.project.project_code if instance.project_id else instance.pk}',
            description=f'{"Created" if created else "Updated"} monthly billing for {instance.project.project_code if instance.project_id else instance.pk}',
            request=request,
            related_object_type='ProjectCode',
            related_object_id=instance.project_id,
        )
except ImportError:
    pass


# ── Operations — DisputeComment signals ──────────────────────────────────────

try:
    from operations.models import DisputeComment

    @receiver(post_save, sender=DisputeComment)
    def log_dispute_comment(sender, instance, created, **kwargs):
        if not created:
            return
        request = get_current_request()
        log_activity_direct(
            user=instance.user,
            source='web' if request else 'signal',
            action_category='update',
            action_type='dispute_commented',
            module='operations',
            object_type='DisputeComment',
            object_id=instance.pk,
            object_repr=f'Comment on Dispute — {instance.dispute.title if instance.dispute_id else instance.pk}',
            related_object_type='DisputeLog',
            related_object_id=instance.dispute_id,
            description=f'{instance.user.get_full_name()} commented on dispute: {instance.dispute.title if instance.dispute_id else instance.pk}',
            request=request,
        )
except ImportError:
    pass


# ── Operations — ProjectCard signals ─────────────────────────────────────────

try:
    from operations.models_projectcard import ProjectCard

    @receiver(post_save, sender=ProjectCard)
    def log_project_card(sender, instance, created, **kwargs):
        request = get_current_request()
        user = instance.created_by if created else (request.user if request and request.user.is_authenticated else instance.created_by)
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='project_card_created' if created else 'project_card_updated',
            module='operations',
            object_type='ProjectCard',
            object_id=instance.pk,
            object_repr=str(instance),
            description=f'{"Created" if created else "Updated"} project card: {instance}',
            request=request,
            related_object_type='ProjectCode',
            related_object_id=instance.project_id,
        )
except ImportError:
    pass


# ── Supply — RFQ signals ──────────────────────────────────────────────────────

try:
    from supply.models import RFQ

    @receiver(post_save, sender=RFQ)
    def log_rfq(sender, instance, created, **kwargs):
        request = get_current_request()
        log_activity_direct(
            user=instance.created_by,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='rfq_created' if created else 'rfq_updated',
            module='supply',
            object_type='RFQ',
            object_id=instance.pk,
            object_repr=f'RFQ #{instance.pk}',
            description=f'{"Created" if created else "Updated"} RFQ #{instance.pk}',
            request=request,
        )
except ImportError:
    pass


try:
    from supply.models import RFQVendorMapping

    @receiver(post_save, sender=RFQVendorMapping)
    def log_rfq_vendor(sender, instance, created, **kwargs):
        if not created:
            return
        request = get_current_request()
        log_activity_direct(
            user=instance.sent_by,
            source='web' if request else 'signal',
            action_category='update',
            action_type='rfq_sent_to_vendor',
            module='supply',
            object_type='RFQVendorMapping',
            object_id=instance.pk,
            object_repr=f'RFQ sent to vendor',
            related_object_type='RFQ',
            related_object_id=instance.rfq_id,
            description=f'RFQ sent to vendor',
            request=request,
        )
except ImportError:
    pass


# ── Projects — ClientCard signals ─────────────────────────────────────────────

try:
    from projects.models_client import ClientCard

    @receiver(post_save, sender=ClientCard)
    def log_client_card(sender, instance, created, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='client_created' if created else 'client_updated',
            module='projects',
            object_type='ClientCard',
            object_id=instance.pk,
            object_repr=f'Client — {str(instance)}',
            description=f'{"Created" if created else "Updated"} client: {instance}',
            request=request,
        )

    @receiver(post_delete, sender=ClientCard)
    def log_client_delete(sender, instance, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='delete',
            action_type='client_deleted',
            module='projects',
            object_type='ClientCard',
            object_id=instance.pk,
            object_repr=f'Client — {str(instance)}',
            description=f'Deleted client: {instance}',
            request=request,
        )
except ImportError:
    pass


# ── Projects — QuotationRevision signals ─────────────────────────────────────

try:
    from projects.models_quotation import QuotationRevision

    @receiver(post_save, sender=QuotationRevision)
    def log_quotation_revision(sender, instance, created, **kwargs):
        if not created:
            return
        request = get_current_request()
        log_activity_direct(
            user=instance.created_by,
            source='web' if request else 'signal',
            action_category='update',
            action_type='quotation_revision_created',
            module='projects',
            object_type='QuotationRevision',
            object_id=instance.pk,
            object_repr=f'Quotation Revision v{instance.revision_number}',
            related_object_type='Quotation',
            related_object_id=instance.quotation_id,
            description=f'Created revision v{instance.revision_number} for quotation #{instance.quotation_id}: {instance.reason or ""}',
            request=request,
        )
except ImportError:
    pass
