from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0067_make_lr_project_optional'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lorryreceipt',
            name='project',
            field=models.ForeignKey(
                db_column='project_id',
                help_text='For record-keeping only; NOT printed on LR',
                on_delete=models.PROTECT,
                related_name='lorry_receipts',
                to='projects.projectcode',
                to_field='project_id',
            ),
        ),
    ]
