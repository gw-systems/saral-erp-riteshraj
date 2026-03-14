# Generated migration to increase warehouse_code field length

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supply', '0002_citycode_created_at_citycode_is_active_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vendorwarehouse',
            name='warehouse_code',
            field=models.CharField(max_length=100, unique=True),
        ),
    ]
