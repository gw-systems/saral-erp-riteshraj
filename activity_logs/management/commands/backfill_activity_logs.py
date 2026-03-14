from django.core.management.base import BaseCommand
from django.utils import timezone
from activity_logs.models import ActivityLog

BATCH_SIZE = 500


SOURCES = [
    'DailyEntryAuditLog', 'LRAuditLog', 'QuotationAudit', 'ProjectCodeChangeLog',
    'DisputeLog', 'DailyMISLog', 'EscalationLog', 'AgreementRenewalLog',
    'PorterInvoiceSession', 'ImpersonationLog', 'PasswordHistory',
]


class Command(BaseCommand):
    help = 'Backfill ActivityLog from existing audit models'

    def add_arguments(self, parser):
        parser.add_argument('--source', default='all',
            choices=['all'] + SOURCES,
            help='Which source to backfill from')
        parser.add_argument('--dry-run', action='store_true',
            help='Show counts without inserting')

    def handle(self, *args, **options):
        source = options['source']
        dry_run = options['dry_run']

        if source in ('all', 'DailyEntryAuditLog'):
            self._backfill_daily_entry(dry_run)
        if source in ('all', 'LRAuditLog'):
            self._backfill_lr(dry_run)
        if source in ('all', 'QuotationAudit'):
            self._backfill_quotation(dry_run)
        if source in ('all', 'ProjectCodeChangeLog'):
            self._backfill_project_changes(dry_run)
        if source in ('all', 'DisputeLog'):
            self._backfill_disputes(dry_run)
        if source in ('all', 'DailyMISLog'):
            self._backfill_mis(dry_run)
        if source in ('all', 'EscalationLog'):
            self._backfill_escalation(dry_run)
        if source in ('all', 'AgreementRenewalLog'):
            self._backfill_agreement_renewal(dry_run)
        if source in ('all', 'PorterInvoiceSession'):
            self._backfill_porter_invoice(dry_run)
        if source in ('all', 'ImpersonationLog'):
            self._backfill_impersonation(dry_run)
        if source in ('all', 'PasswordHistory'):
            self._backfill_password_history(dry_run)

        self.stdout.write(self.style.SUCCESS('Backfill complete.'))

    def _bulk_insert(self, records, dry_run, source_name):
        if dry_run:
            self.stdout.write(f'[DRY RUN] Would insert {len(records)} from {source_name}')
            return
        ActivityLog.objects.bulk_create(records, ignore_conflicts=True, batch_size=BATCH_SIZE)
        self.stdout.write(self.style.SUCCESS(f'Inserted {len(records)} from {source_name}'))

    def _backfill_daily_entry(self, dry_run):
        try:
            from operations.models import DailyEntryAuditLog
        except ImportError:
            self.stdout.write('DailyEntryAuditLog not found — skipping')
            return

        records = []
        for log in DailyEntryAuditLog.objects.select_related('changed_by', 'daily_entry').iterator():
            ts = log.changed_at or timezone.now()
            user = log.changed_by
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='signal',
                action_category='create' if log.action == 'CREATED' else 'update',
                action_type='daily_entry_' + log.action.lower(),
                module='operations',
                object_type='DailySpaceUtilization',
                object_id=log.daily_entry_id,
                object_repr=f'Daily Entry #{log.daily_entry_id}',
                description=f'{log.action} daily entry',
                extra_data={
                    'old_values': log.old_values or {},
                    'new_values': log.new_values or {},
                    'change_reason': log.change_reason or '',
                },
                is_backfilled=True,
                backfill_source='DailyEntryAuditLog',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'DailyEntryAuditLog')

    def _backfill_lr(self, dry_run):
        try:
            from operations.models_lr import LRAuditLog
        except ImportError:
            self.stdout.write('LRAuditLog not found — skipping')
            return

        records = []
        for log in LRAuditLog.objects.select_related('changed_by').iterator():
            ts = log.changed_at or timezone.now()
            user = log.changed_by
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='signal',
                action_category={
                    'CREATED': 'create', 'UPDATED': 'update', 'DELETED': 'delete'
                }.get(log.action, 'update'),
                action_type='lr_' + log.action.lower(),
                module='operations',
                object_type='LorryReceipt',
                object_id=log.lr_id,
                object_repr=f'LR #{log.lr_id}',
                description=f'{log.action} lorry receipt #{log.lr_id}',
                extra_data={
                    'old_values': log.old_values or {},
                    'new_values': log.new_values or {},
                },
                is_backfilled=True,
                backfill_source='LRAuditLog',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'LRAuditLog')

    def _backfill_quotation(self, dry_run):
        try:
            from projects.models_quotation import QuotationAudit
        except ImportError:
            self.stdout.write('QuotationAudit not found — skipping')
            return

        records = []
        for log in QuotationAudit.objects.select_related('user').iterator():
            ts = log.timestamp or timezone.now()
            user = log.user
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='web',
                action_category='create' if 'created' in log.action else (
                    'export' if log.action in ('pdf_generated', 'docx_generated', 'downloaded') else
                    'email' if log.action == 'email_sent' else
                    'approve' if log.action == 'client_accepted' else
                    'update'
                ),
                action_type='quotation_' + log.action,
                module='projects',
                object_type='Quotation',
                object_id=log.quotation_id,
                object_repr=f'Quotation #{log.quotation_id}',
                description=f'Quotation {log.action.replace("_", " ")}',
                ip_address=log.ip_address if hasattr(log, 'ip_address') else None,
                extra_data=log.changes or {},
                is_backfilled=True,
                backfill_source='QuotationAudit',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'QuotationAudit')

    def _backfill_project_changes(self, dry_run):
        try:
            from projects.models import ProjectCodeChangeLog
        except ImportError:
            self.stdout.write('ProjectCodeChangeLog not found — skipping')
            return

        records = []
        for log in ProjectCodeChangeLog.objects.select_related('changed_by').iterator():
            ts = log.changed_at or timezone.now()
            user = log.changed_by
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='web',
                action_category='update',
                action_type='project_field_changed',
                module='projects',
                object_type='ProjectCode',
                object_id=log.project_id,
                object_repr=f'Project #{log.project_id}',
                description=f'Changed {log.field_name} on project',
                ip_address=getattr(log, 'ip_address', None),
                extra_data={
                    'field_name': log.field_name,
                    'old': {log.field_name: log.old_value},
                    'new': {log.field_name: log.new_value},
                },
                is_backfilled=True,
                backfill_source='ProjectCodeChangeLog',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'ProjectCodeChangeLog')

    def _backfill_disputes(self, dry_run):
        try:
            from operations.models import DisputeLog
        except ImportError:
            self.stdout.write('DisputeLog not found — skipping')
            return

        records = []
        for log in DisputeLog.objects.select_related('raised_by', 'project').iterator():
            ts = log.opened_at or log.created_at or timezone.now()
            user = log.raised_by
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='web',
                action_category='create',
                action_type='dispute_raised',
                module='operations',
                object_type='DisputeLog',
                object_id=log.pk,
                object_repr=f'Dispute — {log.title or log.pk}',
                related_object_type='ProjectCode',
                related_object_id=log.project_id,
                description=f'Raised dispute: {log.title or log.pk}',
                extra_data={
                    'project_code': log.project.project_code if log.project_id else '',
                    'status': str(log.status) if log.status_id else '',
                },
                is_backfilled=True,
                backfill_source='DisputeLog',
                timestamp=ts,
                date=ts.date(),
            ))
            # Also log resolution if resolved
            if log.resolved_at and log.resolved_by:
                rt = log.resolved_at
                records.append(ActivityLog(
                    user=log.resolved_by,
                    user_display_name=log.resolved_by.get_full_name(),
                    role_snapshot=getattr(log.resolved_by, 'role', 'unknown'),
                    source='web',
                    action_category='update',
                    action_type='dispute_resolved',
                    module='operations',
                    object_type='DisputeLog',
                    object_id=log.pk,
                    object_repr=f'Dispute — {log.title or log.pk}',
                    related_object_type='ProjectCode',
                    related_object_id=log.project_id,
                    description=f'Resolved dispute: {log.title or log.pk}',
                    extra_data={'resolution': log.resolution or ''},
                    is_backfilled=True,
                    backfill_source='DisputeLog',
                    timestamp=rt,
                    date=rt.date(),
                ))
        self._bulk_insert(records, dry_run, 'DisputeLog')

    def _backfill_mis(self, dry_run):
        try:
            from operations.models import DailyMISLog
        except ImportError:
            self.stdout.write('DailyMISLog not found — skipping')
            return

        records = []
        for log in DailyMISLog.objects.select_related('sent_by', 'project').filter(mis_sent=True).iterator():
            ts = log.sent_at or log.created_at or timezone.now()
            user = log.sent_by
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='web',
                action_category='update',
                action_type='mis_sent',
                module='operations',
                object_type='DailyMISLog',
                object_id=log.pk,
                object_repr=f'MIS — {log.project.project_code if log.project_id else log.pk} ({log.log_date})',
                related_object_type='ProjectCode',
                related_object_id=log.project_id,
                description=f'MIS sent for {log.log_date}',
                extra_data={
                    'log_date': str(log.log_date),
                    'remarks': log.remarks or '',
                },
                is_backfilled=True,
                backfill_source='DailyMISLog',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'DailyMISLog')

    def _backfill_escalation(self, dry_run):
        try:
            from operations.models_agreements import EscalationLog
        except ImportError:
            self.stdout.write('EscalationLog not found — skipping')
            return

        records = []
        for log in EscalationLog.objects.select_related('performed_by', 'tracker').iterator():
            ts = timezone.make_aware(
                timezone.datetime.combine(log.action_date, timezone.datetime.min.time())
            ) if log.action_date else timezone.now()
            user = log.performed_by
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='web',
                action_category='update',
                action_type='escalation_action_logged',
                module='operations',
                object_type='EscalationLog',
                object_id=log.pk,
                object_repr=str(log),
                description=f'Escalation action on {log.action_date}',
                extra_data={
                    'action_date': str(log.action_date),
                    'email_sent_to': log.email_sent_to or '',
                    'notes': log.notes or '',
                },
                is_backfilled=True,
                backfill_source='EscalationLog',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'EscalationLog')

    def _backfill_agreement_renewal(self, dry_run):
        try:
            from operations.models_agreements import AgreementRenewalLog
        except ImportError:
            self.stdout.write('AgreementRenewalLog not found — skipping')
            return

        records = []
        for log in AgreementRenewalLog.objects.select_related('performed_by', 'tracker').iterator():
            ts = timezone.make_aware(
                timezone.datetime.combine(log.action_date, timezone.datetime.min.time())
            ) if log.action_date else timezone.now()
            user = log.performed_by
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='web',
                action_category='update',
                action_type='agreement_renewal_action_logged',
                module='operations',
                object_type='AgreementRenewalLog',
                object_id=log.pk,
                object_repr=str(log),
                description=f'Agreement renewal action on {log.action_date}',
                extra_data={
                    'action_date': str(log.action_date),
                    'email_sent_to': log.email_sent_to or '',
                    'notes': log.notes or '',
                },
                is_backfilled=True,
                backfill_source='AgreementRenewalLog',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'AgreementRenewalLog')

    def _backfill_porter_invoice(self, dry_run):
        try:
            from operations.models_porter_invoice import PorterInvoiceSession
        except ImportError:
            self.stdout.write('PorterInvoiceSession not found — skipping')
            return

        records = []
        for session in PorterInvoiceSession.objects.select_related('created_by').iterator():
            ts = session.created_at or timezone.now()
            user = session.created_by
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='web',
                action_category='create',
                action_type='porter_invoice_session_created',
                module='operations',
                object_type='PorterInvoiceSession',
                object_id=session.pk,
                object_repr=f'Porter Invoice Session #{session.pk} ({session.session_type})',
                description=f'Porter invoice session #{session.pk} — {session.session_type}, status: {session.status}',
                extra_data={
                    'session_type': session.session_type,
                    'status': session.status,
                    'total_files': session.total_files,
                    'success_count': session.success_count,
                    'error_count': session.error_count,
                },
                is_backfilled=True,
                backfill_source='PorterInvoiceSession',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'PorterInvoiceSession')

    def _backfill_impersonation(self, dry_run):
        try:
            from accounts.models import ImpersonationLog
        except ImportError:
            self.stdout.write('ImpersonationLog not found — skipping')
            return

        records = []
        for log in ImpersonationLog.objects.select_related('admin', 'impersonated_user').iterator():
            ts = log.started_at or timezone.now()
            records.append(ActivityLog(
                user=log.admin,
                user_display_name=log.admin.get_full_name() if log.admin else 'Unknown',
                role_snapshot=getattr(log.admin, 'role', 'unknown') if log.admin else 'unknown',
                source='web',
                action_category='permission_denied',
                action_type='impersonation_started',
                module='accounts',
                object_type='User',
                object_id=log.impersonated_user_id,
                object_repr=f'User — {log.impersonated_user.get_full_name() if log.impersonated_user else log.impersonated_user_id}',
                description=f'{log.admin.get_full_name() if log.admin else "?"} impersonated {log.impersonated_user.get_full_name() if log.impersonated_user else "?"}',
                extra_data={'impersonation_log_id': log.pk},
                is_backfilled=True,
                backfill_source='ImpersonationLog',
                timestamp=ts,
                date=ts.date(),
            ))
            if log.ended_at:
                et = log.ended_at
                records.append(ActivityLog(
                    user=log.admin,
                    user_display_name=log.admin.get_full_name() if log.admin else 'Unknown',
                    role_snapshot=getattr(log.admin, 'role', 'unknown') if log.admin else 'unknown',
                    source='web',
                    action_category='auth',
                    action_type='impersonation_ended',
                    module='accounts',
                    object_type='User',
                    object_id=log.impersonated_user_id,
                    object_repr=f'User — {log.impersonated_user.get_full_name() if log.impersonated_user else log.impersonated_user_id}',
                    description=f'{log.admin.get_full_name() if log.admin else "?"} ended impersonation of {log.impersonated_user.get_full_name() if log.impersonated_user else "?"}',
                    extra_data={'impersonation_log_id': log.pk},
                    is_backfilled=True,
                    backfill_source='ImpersonationLog',
                    timestamp=et,
                    date=et.date(),
                ))
        self._bulk_insert(records, dry_run, 'ImpersonationLog')

    def _backfill_password_history(self, dry_run):
        try:
            from accounts.models import PasswordHistory
        except ImportError:
            self.stdout.write('PasswordHistory not found — skipping')
            return

        records = []
        for ph in PasswordHistory.objects.select_related('user', 'changed_by').iterator():
            ts = ph.changed_at or timezone.now()
            user = ph.changed_by or ph.user
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='web',
                action_category='update',
                action_type='password_changed',
                module='accounts',
                object_type='User',
                object_id=ph.user_id,
                object_repr=f'User — {ph.user.get_full_name() if ph.user else ph.user_id}',
                description=f'Password changed for {ph.user.get_full_name() if ph.user else ph.user_id} — {ph.reason or ""}',
                extra_data={
                    'reason': ph.reason or '',
                    'changed_by_id': ph.changed_by_id,
                    'ip_address': str(ph.ip_address) if ph.ip_address else '',
                },
                is_backfilled=True,
                backfill_source='PasswordHistory',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'PasswordHistory')
