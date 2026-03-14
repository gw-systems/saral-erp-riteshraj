# Generated manually on 2026-01-26
# Make all optional/remarks/override fields nullable

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0010_populate_handling_unit'),
        ('operations', '0044_alter_monthlybilling_storage_unit_type'),
    ]

    operations = [
        # Make all remarks fields nullable (optional text fields)
        migrations.AlterField(
            model_name='monthlybilling',
            name='handling_in_remarks',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='monthlybilling',
            name='handling_out_remarks',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='monthlybilling',
            name='storage_remarks',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='monthlybilling',
            name='controller_remarks',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='monthlybilling',
            name='finance_remarks',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='monthlybilling',
            name='client_transport_remarks',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='monthlybilling',
            name='vendor_transport_remarks',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='monthlybilling',
            name='client_misc_description',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='monthlybilling',
            name='vendor_misc_description',
            field=models.TextField(blank=True, default=''),
        ),
        
        # Make all override_reason fields nullable
        migrations.AlterField(
            model_name='monthlybilling',
            name='handling_in_override_reason',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='monthlybilling',
            name='handling_out_override_reason',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='monthlybilling',
            name='storage_override_reason',
            field=models.TextField(blank=True, default=''),
        ),
        
        # Make MIS fields nullable (optional)
        migrations.AlterField(
            model_name='monthlybilling',
            name='mis_email_subject',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AlterField(
            model_name='monthlybilling',
            name='mis_link',
            field=models.CharField(blank=True, default='', max_length=1000),
        ),
        
        # Make included_adhoc_ids nullable (optional CSV list)
        migrations.AlterField(
            model_name='monthlybilling',
            name='included_adhoc_ids',
            field=models.TextField(blank=True, default='', help_text='Comma-separated IDs of included adhoc billings'),
        ),
    ]