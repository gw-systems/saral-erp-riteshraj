# Generated manually to add missing transport quantity fields
# These fields exist in the model but migration was never created

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0049_alter_disputelog_comment_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='monthlybilling',
            name='vendor_transport_quantity',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12
            ),
        ),
        migrations.AddField(
            model_name='monthlybilling',
            name='client_transport_quantity',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12
            ),
        ),
    ]
