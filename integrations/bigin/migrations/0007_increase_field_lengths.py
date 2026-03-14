# Generated manually on 2026-02-02
# Increase field lengths to prevent data truncation errors

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bigin', '0006_remove_biginrecord_idx_incremental_sync_and_more'),
    ]

    operations = [
        # Increase first_name from 100 to 255
        migrations.AlterField(
            model_name='biginrecord',
            name='first_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        # Increase last_name from 100 to 255
        migrations.AlterField(
            model_name='biginrecord',
            name='last_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        # Increase mobile from 50 to 255
        migrations.AlterField(
            model_name='biginrecord',
            name='mobile',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        # Increase area_requirement from 50 to 255
        migrations.AlterField(
            model_name='biginrecord',
            name='area_requirement',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        # Increase status from 50 to 500 (matching current model)
        migrations.AlterField(
            model_name='biginrecord',
            name='status',
            field=models.CharField(blank=True, db_index=True, max_length=500, null=True),
        ),
        # Increase lead_stage from 255 to 500 (matching current model)
        migrations.AlterField(
            model_name='biginrecord',
            name='lead_stage',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
    ]
