"""
Migration: Add ScheduledJob model and seed all existing Cloud Scheduler jobs.

After this migration, the DB contains all 9 scheduled jobs that were
previously hardcoded in GCP Cloud Scheduler console. A single master
Cloud Scheduler job (every minute → /integrations/scheduled-jobs/tick/)
now drives all scheduling.
"""
from django.db import migrations, models


SEED_JOBS = [
    {
        'name': 'Bigin Incremental Sync',
        'integration': 'bigin',
        'endpoint': '/integrations/bigin/workers/sync-all-modules/',
        'payload': {'run_full': False},
        'cron_schedule': '*/5 * * * *',
        'is_enabled': True,
    },
    {
        'name': 'Bigin Full Sync',
        'integration': 'bigin',
        'endpoint': '/integrations/bigin/workers/sync-all-modules/',
        'payload': {'run_full': True},
        'cron_schedule': '0 3 * * *',
        'is_enabled': True,
    },
    {
        'name': 'Bigin Token Refresh',
        'integration': 'bigin',
        'endpoint': '/integrations/bigin/workers/refresh-token/',
        'payload': {},
        'cron_schedule': '0 * * * *',
        'is_enabled': True,
    },
    {
        'name': 'Bigin Stale Lead Check',
        'integration': 'bigin',
        'endpoint': '/integrations/bigin/workers/stale-lead-check/',
        'payload': {},
        'cron_schedule': '*/15 * * * *',
        'is_enabled': True,
    },
    {
        'name': 'Gmail Leads Sync',
        'integration': 'gmail_leads',
        'endpoint': '/integrations/gmail-leads/workers/sync-all-accounts/',
        'payload': {'force_full': False},
        'cron_schedule': '*/15 * * * *',
        'is_enabled': True,
    },
    {
        'name': 'Google Ads Daily Sync',
        'integration': 'google_ads',
        'endpoint': '/integrations/google-ads/workers/sync-all-accounts/',
        'payload': {'sync_yesterday': True, 'sync_current_month_search_terms': True},
        'cron_schedule': '0 2 * * *',
        'is_enabled': True,
    },
    {
        'name': 'TallySync',
        'integration': 'tallysync',
        'endpoint': '/integrations/tallysync/workers/sync-tally-data/',
        'payload': {'days': 7},
        'cron_schedule': '*/30 * * * *',
        'is_enabled': True,
    },
    {
        'name': 'Callyzer Daily Sync',
        'integration': 'callyzer',
        'endpoint': '/integrations/callyzer/workers/sync-all-accounts/',
        'payload': {'days_back': 150},
        'cron_schedule': '0 2 * * *',
        'is_enabled': True,
    },
    {
        'name': 'Gmail Inbox Sync',
        'integration': 'gmail',
        'endpoint': '/gmail/workers/sync-all-accounts/',
        'payload': {'force_full': False},
        'cron_schedule': '*/15 * * * *',
        'is_enabled': True,
    },
]


def seed_scheduled_jobs(apps, schema_editor):
    ScheduledJob = apps.get_model('integrations', 'ScheduledJob')
    for job_data in SEED_JOBS:
        ScheduledJob.objects.get_or_create(
            name=job_data['name'],
            integration=job_data['integration'],
            defaults={
                'endpoint': job_data['endpoint'],
                'payload': job_data['payload'],
                'cron_schedule': job_data['cron_schedule'],
                'is_enabled': job_data['is_enabled'],
                'updated_by': 'migration',
            }
        )


def unseed_scheduled_jobs(apps, schema_editor):
    ScheduledJob = apps.get_model('integrations', 'ScheduledJob')
    names = [j['name'] for j in SEED_JOBS]
    ScheduledJob.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0006_add_gmail_to_synclog'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScheduledJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('integration', models.CharField(
                    choices=[
                        ('bigin', 'Bigin CRM'),
                        ('gmail_leads', 'Gmail Leads'),
                        ('google_ads', 'Google Ads'),
                        ('callyzer', 'Callyzer'),
                        ('tallysync', 'TallySync'),
                        ('gmail', 'Gmail'),
                        ('expense_log', 'Expense Log'),
                    ],
                    db_index=True,
                    max_length=50,
                )),
                ('endpoint', models.CharField(
                    help_text='Relative URL path, e.g. /integrations/bigin/workers/sync-all-modules/',
                    max_length=200,
                )),
                ('payload', models.JSONField(
                    default=dict,
                    help_text='JSON payload sent to the worker endpoint',
                )),
                ('cron_schedule', models.CharField(
                    help_text='5-field cron expression, e.g. */5 * * * *',
                    max_length=100,
                )),
                ('is_enabled', models.BooleanField(default=True, db_index=True)),
                ('last_fired_at', models.DateTimeField(blank=True, null=True)),
                ('last_fired_result', models.CharField(
                    blank=True,
                    choices=[('ok', 'OK'), ('skipped', 'Skipped'), ('error', 'Error')],
                    max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.CharField(
                    blank=True,
                    help_text='Username of last editor',
                    max_length=100,
                )),
            ],
            options={
                'verbose_name': 'Scheduled Job',
                'verbose_name_plural': 'Scheduled Jobs',
                'ordering': ['integration', 'name'],
            },
        ),
        migrations.RunPython(seed_scheduled_jobs, reverse_code=unseed_scheduled_jobs),
    ]
