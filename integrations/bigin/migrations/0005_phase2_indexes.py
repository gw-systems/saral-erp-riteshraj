# Generated migration for Phase 2 optimizations
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bigin', '0004_alter_biginrecord_area_requirement_and_more'),
    ]

    operations = [
        # Phase 2: Composite index for incremental sync
        migrations.AddIndex(
            model_name='biginrecord',
            index=models.Index(
                fields=['module', '-modified_time', '-created_time'],
                name='idx_incremental_sync'
            ),
        ),
        # Phase 2: Covering index for upsert checks
        migrations.AddIndex(
            model_name='biginrecord',
            index=models.Index(
                fields=['bigin_id', 'module', 'modified_time'],
                name='idx_upsert_check'
            ),
        ),
    ]
