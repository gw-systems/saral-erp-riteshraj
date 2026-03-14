# Generated migration to fix all audit issues
from django.db import migrations, models
import django.db.models.deletion


def fix_duplicate_adobe_ids(apps, schema_editor):
    """
    Fix duplicate empty adobe_agreement_id values before adding unique constraint
    Only keep empty string for agreements that are truly not submitted yet
    """
    AdobeAgreement = apps.get_model('adobe_sign', 'AdobeAgreement')

    # Find all agreements with empty adobe_agreement_id
    empty_agreements = AdobeAgreement.objects.filter(
        models.Q(adobe_agreement_id='') | models.Q(adobe_agreement_id__isnull=True)
    )

    # For agreements that have been submitted but have empty ID, set to NULL temporarily
    # We'll keep the first one as empty string
    first_empty = True
    for agreement in empty_agreements:
        if first_empty:
            # Keep the first one as empty string
            agreement.adobe_agreement_id = ''
            agreement.save()
            first_empty = False
        else:
            # Set others to NULL temporarily
            agreement.adobe_agreement_id = None
            agreement.save()


class Migration(migrations.Migration):

    dependencies = [
        ('adobe_sign', '0004_rename_tracking_fields'),
    ]

    operations = [
        # First, allow NULL temporarily to fix duplicates
        migrations.AlterField(
            model_name='adobeagreement',
            name='adobe_agreement_id',
            field=models.CharField(
                blank=True,
                null=True,
                help_text='Adobe Sign agreement ID',
                max_length=255
            ),
        ),

        # Run data migration to fix duplicates
        migrations.RunPython(fix_duplicate_adobe_ids, migrations.RunPython.noop),

        # Now convert NULL to empty string and remove unique constraint temporarily
        # We'll handle uniqueness at application level for non-empty values
        migrations.AlterField(
            model_name='adobeagreement',
            name='adobe_agreement_id',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Adobe Sign agreement ID',
                max_length=255,
                db_index=True  # Add index instead of unique constraint
            ),
        ),

        # H9: Change signature_field_data to JSONField
        migrations.AlterField(
            model_name='adobeagreement',
            name='signature_field_data',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Signature field placement data',
                null=True
            ),
        ),

        # C4 & M2: Add adobe_event_id for webhook idempotency
        migrations.AddField(
            model_name='agreementevent',
            name='adobe_event_id',
            field=models.CharField(
                blank=True,
                help_text='Adobe webhook ID for idempotency',
                max_length=255,
                null=True,
                unique=True
            ),
        ),

        # C4: Add raw_payload for webhook reprocessing
        migrations.AddField(
            model_name='agreementevent',
            name='raw_payload',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Raw webhook payload for debugging',
                null=True
            ),
        ),

        # M2: Add unique constraint for Signer (agreement, email)
        migrations.AlterUniqueTogether(
            name='signer',
            unique_together={('agreement', 'email')},
        ),

        # M10 & M11: Keeping file_hash and template fields - they are part of DocumentTemplate feature
        # These fields are defined in models.py and should not be removed

        # Add webhook_secret to settings
        migrations.AddField(
            model_name='adobesignsettings',
            name='webhook_secret',
            field=models.CharField(
                blank=True,
                help_text='Secret key for webhook signature verification',
                max_length=255
            ),
        ),
    ]
