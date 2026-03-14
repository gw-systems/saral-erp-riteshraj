from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('adobe_sign', '0008_add_adobe_authoring_url'),
    ]

    operations = [
        # Change CharField(max_length=500) to TextField so encrypted tokens
        # (which are longer than 500 chars) can be stored without truncation.
        migrations.AlterField(
            model_name='adobesignsettings',
            name='integration_key',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Adobe Sign Integration Key — stored encrypted',
            ),
        ),
    ]
