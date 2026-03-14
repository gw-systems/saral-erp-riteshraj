from django.core.management.base import BaseCommand
from activity_logs.models import ActivityLog


class Command(BaseCommand):
    help = 'Anonymize activity logs for a deleted user (GDPR compliance)'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, required=True)

    def handle(self, *args, **options):
        user_id = options['user_id']
        updated = ActivityLog.objects.filter(user_id=user_id).update(
            user=None,
            user_display_name='Deleted User',
            anonymized=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Anonymized {updated} activity log entries for user_id={user_id}'
        ))
