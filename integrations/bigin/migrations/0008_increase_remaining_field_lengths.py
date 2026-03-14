# Generated manually on 2026-02-02
# Increase remaining field lengths that were missed in 0007

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bigin', '0007_increase_field_lengths'),
    ]

    operations = [
        # Increase business_type from 100 to 255
        migrations.AlterField(
            model_name='biginrecord',
            name='business_type',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        # Increase contact_type from 100 to 255
        migrations.AlterField(
            model_name='biginrecord',
            name='contact_type',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        # Increase industry_type from 100 to 255
        migrations.AlterField(
            model_name='biginrecord',
            name='industry_type',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        # Increase lead_source from 100 to 255
        migrations.AlterField(
            model_name='biginrecord',
            name='lead_source',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        # Increase owner from 100 to 255
        migrations.AlterField(
            model_name='biginrecord',
            name='owner',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
    ]
