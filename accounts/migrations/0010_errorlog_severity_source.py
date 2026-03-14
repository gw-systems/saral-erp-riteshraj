from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_alter_user_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='errorlog',
            name='severity',
            field=models.CharField(
                choices=[('error', 'Error'), ('warning', 'Warning'), ('info', 'Info')],
                default='error',
                db_index=True,
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='errorlog',
            name='source',
            field=models.CharField(
                choices=[('unhandled', 'Unhandled (500)'), ('caught', 'Caught (view-handled)')],
                default='unhandled',
                db_index=True,
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name='errorlog',
            index=models.Index(fields=['severity', '-timestamp'], name='errorlog_severity_ts_idx'),
        ),
        migrations.AddIndex(
            model_name='errorlog',
            index=models.Index(fields=['source', '-timestamp'], name='errorlog_source_ts_idx'),
        ),
    ]
