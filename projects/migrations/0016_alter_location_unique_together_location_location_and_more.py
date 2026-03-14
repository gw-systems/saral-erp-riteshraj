# Generated migration - reorder operations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0015_alter_location_options'),
    ]

    operations = [
        # FIRST: Add the new fields
        migrations.AddField(
            model_name='location',
            name='location',
            field=models.CharField(default='Unknown', max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='location',
            name='pincode',
            field=models.CharField(blank=True, max_length=6, null=True),
        ),
        migrations.AddField(
            model_name='location',
            name='region',
            field=models.CharField(choices=[('north', 'North'), ('south', 'South'), ('east', 'East'), ('west', 'West'), ('central', 'Central')], default='central', max_length=20),
            preserve_default=False,
        ),
        # THEN: Remove old field
        migrations.RemoveField(
            model_name='location',
            name='state_code',
        ),
        # FINALLY: Set unique_together (now that 'location' field exists)
        migrations.AlterUniqueTogether(
            name='location',
            unique_together={('state', 'city', 'location')},
        ),
    ]