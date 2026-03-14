"""
Migration: Add SyncLog cleanup scheduled job.
Runs weekly to delete logs older than 90 days.
"""
from django.db import migrations


def seed_cleanup_job(apps, schema_editor):
    ScheduledJob = apps.get_model('integrations', 'ScheduledJob')
    ScheduledJob.objects.update_or_create(
        endpoint='/integrations/workers/cleanup-synclogs/',
        defaults={
            'name': 'SyncLog Cleanup',
            'integration': 'bigin',  # Use bigin as generic; closest to "system"
            'payload': {'days': 90},
            'cron_schedule': '0 4 * * 0',  # Weekly: Sunday 4 AM
            'is_enabled': True,
            'updated_by': 'migration',
        }
    )


def remove_cleanup_job(apps, schema_editor):
    ScheduledJob = apps.get_model('integrations', 'ScheduledJob')
    ScheduledJob.objects.filter(endpoint='/integrations/workers/cleanup-synclogs/').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0007_add_scheduled_job'),
    ]

    operations = [
        migrations.RunPython(seed_cleanup_job, remove_cleanup_job),
    ]
