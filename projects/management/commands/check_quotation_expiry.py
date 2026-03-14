"""
Management command: check_quotation_expiry
Marks 'sent' quotations as 'expired' when their validity date has passed.
Run daily via crontab or Django-Q scheduler.
"""

import logging
from datetime import date

from django.core.management.base import BaseCommand

from projects.models_quotation import Quotation
from projects.services.quotation_audit import QuotationAuditService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Mark sent quotations as expired when their validity date has passed.'

    def handle(self, *args, **options):
        today = date.today()
        expired_qs = Quotation.objects.filter(
            status='sent',
            expiry_notified=False,
        )

        count = 0
        for quotation in expired_qs:
            if quotation.validity_date < today:
                old_status = quotation.status
                quotation.status = 'expired'
                quotation.expiry_notified = True
                quotation.save(update_fields=['status', 'expiry_notified'])

                QuotationAuditService.log_action(
                    quotation=quotation,
                    user=None,
                    action='status_changed',
                    changes={'from': old_status, 'to': 'expired', 'reason': 'validity_period_passed'},
                )
                count += 1

        self.stdout.write(self.style.SUCCESS(f'Marked {count} quotation(s) as expired.'))
        logger.info(f'check_quotation_expiry: {count} quotation(s) marked expired.')
