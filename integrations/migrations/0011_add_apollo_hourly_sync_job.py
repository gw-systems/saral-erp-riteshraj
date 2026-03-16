from django.db import migrations


def seed_apollo_hourly_job(apps, schema_editor):
    ScheduledJob = apps.get_model('integrations', 'ScheduledJob')
    ScheduledJob.objects.update_or_create(
        endpoint='/integrations/apollo/workers/sync/',
        defaults={
            'name': 'Apollo Historical Sync',
            'integration': 'apollo',
            'payload': {
                'sync_type': 'full',
                'reset_checkpoint': False,
            },
            'cron_schedule': '0 * * * *',
            'is_enabled': True,
            'updated_by': 'migration',
        },
    )


def remove_apollo_hourly_job(apps, schema_editor):
    ScheduledJob = apps.get_model('integrations', 'ScheduledJob')
    ScheduledJob.objects.filter(endpoint='/integrations/apollo/workers/sync/').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0010_bigin_weekly_full_sync'),
    ]

    operations = [
        migrations.RunPython(seed_apollo_hourly_job, remove_apollo_hourly_job),
    ]
