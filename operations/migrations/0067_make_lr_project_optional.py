from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0066_repair_monthly_billing_schema_drift'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lorryreceipt',
            name='project',
            field=models.ForeignKey(
                blank=True,
                db_column='project_id',
                help_text='For record-keeping only; NOT printed on LR',
                null=True,
                on_delete=models.PROTECT,
                related_name='lorry_receipts',
                to='projects.projectcode',
                to_field='project_id',
            ),
        ),
    ]
