# Manual migration to add missing service_month column
# Created on 2026-01-25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0042_monthlybilling_handling_in_client_variance_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='monthlybilling',
            name='service_month',
            field=models.DateField(
                blank=True,
                help_text='Month when services were actually provided (first day of month)',
                null=True
            ),
        ),
    ]