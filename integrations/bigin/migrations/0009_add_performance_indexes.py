# Generated manually on 2026-02-04
# Add composite indexes for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bigin', '0008_increase_remaining_field_lengths'),
    ]

    operations = [
        # Composite index for dashboard filters
        migrations.AddIndex(
            model_name='biginrecord',
            index=models.Index(fields=['module', 'owner', 'status'], name='bigin_mod_own_stat_idx'),
        ),
        # Composite index for type filtering
        migrations.AddIndex(
            model_name='biginrecord',
            index=models.Index(fields=['module', 'contact_type'], name='bigin_mod_type_idx'),
        ),
        # Composite index for stage filtering
        migrations.AddIndex(
            model_name='biginrecord',
            index=models.Index(fields=['module', 'lead_stage'], name='bigin_mod_stage_idx'),
        ),
        # Index for full name search
        migrations.AddIndex(
            model_name='biginrecord',
            index=models.Index(fields=['full_name'], name='bigin_fullname_idx'),
        ),
        # Index for email search
        migrations.AddIndex(
            model_name='biginrecord',
            index=models.Index(fields=['email'], name='bigin_email_idx'),
        ),
    ]
