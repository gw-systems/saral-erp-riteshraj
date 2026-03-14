# Generated manually on 2026-01-26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0047_alter_infrastructurecost_cost_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='monthlybilling',
            name='mis_document',
            field=models.FileField(blank=True, help_text='MIS report document (PDF, Excel, etc.)', null=True, upload_to='monthly_billing/mis_documents/%Y/%m/'),
        ),
        migrations.AddField(
            model_name='monthlybilling',
            name='transport_document',
            field=models.FileField(blank=True, help_text='Transport related documents (POD, LR, etc.)', null=True, upload_to='monthly_billing/transport_documents/%Y/%m/'),
        ),
        migrations.AddField(
            model_name='monthlybilling',
            name='other_document',
            field=models.FileField(blank=True, help_text='Any other supporting documents', null=True, upload_to='monthly_billing/other_documents/%Y/%m/'),
        ),
    ]
