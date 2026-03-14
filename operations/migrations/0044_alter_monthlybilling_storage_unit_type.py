# Generated manually on 2026-01-26
# Make storage_unit_type nullable to allow blank values

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0010_populate_handling_unit'),
        ('operations', '0043_add_service_month_to_monthlybilling'),
    ]

    operations = [
        migrations.AlterField(
            model_name='monthlybilling',
            name='storage_unit_type',
            field=models.ForeignKey(
                blank=True,
                db_column='storage_unit_type',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='dropdown_master_data.storageunit',
                to_field='code'
            ),
        ),
    ]