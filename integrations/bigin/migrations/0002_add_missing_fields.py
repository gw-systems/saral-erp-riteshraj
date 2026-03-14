# Generated manually on 2026-01-27
# Originally added ALL fields for production (where 0001 was faked).
# Fixed: removed duplicates of 0001, converted max_length changes to AlterField,
# kept only truly new AddField ops. Safe for both fresh and existing databases.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bigin', '0001_initial'),
    ]

    operations = [
        # --- Truly new fields (not in 0001_initial) ---
        migrations.AddField(
            model_name='biginrecord',
            name='first_name',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='biginrecord',
            name='last_name',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='biginrecord',
            name='title',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='biginrecord',
            name='business_model',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='biginrecord',
            name='last_activity_time',
            field=models.DateTimeField(blank=True, null=True),
        ),

        # --- AlterField: fields in 0001 with smaller max_length, widened here ---
        migrations.AlterField(
            model_name='biginrecord',
            name='owner',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='biginrecord',
            name='contact_type',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='biginrecord',
            name='lead_source',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='biginrecord',
            name='lead_stage',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='biginrecord',
            name='industry_type',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='biginrecord',
            name='business_type',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),

        # Fix BiginAuthToken created_at field
        migrations.AlterField(
            model_name='biginauthtoken',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, blank=True, null=True),
        ),
    ]
