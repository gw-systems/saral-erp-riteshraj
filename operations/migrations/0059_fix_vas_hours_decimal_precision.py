from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Fix VAS hours fields to allow 4 decimal places (was 2).
    Consistent with all other quantity/rate fields in monthly billing.
    """

    dependencies = [
        ('operations', '0058_fix_infrastructure_item_decimal_precision'),
    ]

    operations = [
        migrations.AlterField(
            model_name='monthlybillingvasitem',
            name='client_hours',
            field=models.DecimalField(decimal_places=4, max_digits=10, null=True, blank=True,
                                      help_text='Number of hours (used when unit is Per Hour)'),
        ),
        migrations.AlterField(
            model_name='monthlybillingvasitem',
            name='vendor_hours',
            field=models.DecimalField(decimal_places=4, max_digits=10, null=True, blank=True,
                                      help_text='Number of hours (used when unit is Per Hour)'),
        ),
    ]
