"""
Change Bigin Full Sync from daily 3am to weekly Sunday 3am.

Incremental COQL sync runs every 5 minutes and now covers all modules + inline notes,
so weekly full sync is sufficient for catching edge cases (deletes, missed records).
"""
from django.db import migrations


def change_to_weekly(apps, schema_editor):
    ScheduledJob = apps.get_model('integrations', 'ScheduledJob')
    ScheduledJob.objects.filter(name='Bigin Full Sync').update(cron_schedule='0 3 * * 0')


def revert_to_daily(apps, schema_editor):
    ScheduledJob = apps.get_model('integrations', 'ScheduledJob')
    ScheduledJob.objects.filter(name='Bigin Full Sync').update(cron_schedule='0 3 * * *')


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0009_synclog_job_monitoring'),
    ]

    operations = [
        migrations.RunPython(change_to_weekly, revert_to_daily),
    ]
