# Generated manually on 2026-02-04
# Replace 'closed' status with 'dispute' status in DisputeStatus

from django.db import migrations


def replace_closed_with_dispute(apps, schema_editor):
    """
    Replace 'closed' status with 'dispute' status.
    This updates both the master dropdown and any existing dispute records.
    """
    DisputeStatus = apps.get_model('dropdown_master_data', 'DisputeStatus')
    DisputeLog = apps.get_model('operations', 'DisputeLog')

    print("\n  " + "="*60)
    print("  REPLACING 'closed' WITH 'dispute' STATUS")
    print("  " + "="*60 + "\n")

    # Step 1: Check if 'dispute' status already exists
    dispute_exists = DisputeStatus.objects.filter(code='dispute').exists()

    if not dispute_exists:
        # Step 2: Create 'dispute' status
        DisputeStatus.objects.create(
            code='dispute',
            label='Dispute',
            is_active=True,
            display_order=35,  # Between 'in_progress' (20) and 'resolved' (30)
            created_at=None,
            updated_at=None,
            updated_by=None,
        )
        print("  ✓ Created 'dispute' status")
    else:
        print("  ℹ 'dispute' status already exists")

    # Step 3: Update any DisputeLog records that have 'closed' status to 'dispute'
    closed_status = DisputeStatus.objects.filter(code='closed').first()
    dispute_status = DisputeStatus.objects.get(code='dispute')

    if closed_status:
        updated_count = DisputeLog.objects.filter(status=closed_status).update(status=dispute_status)
        if updated_count > 0:
            print(f"  ✓ Updated {updated_count} dispute record(s) from 'closed' to 'dispute'")
        else:
            print("  ℹ No dispute records with 'closed' status found")

        # Step 4: Soft delete the 'closed' status
        closed_status.is_active = False
        closed_status.save()
        print("  ✓ Deactivated 'closed' status")
    else:
        print("  ℹ 'closed' status not found")

    print("\n  " + "="*60)
    print("  MIGRATION COMPLETE")
    print("  " + "="*60 + "\n")


def reverse_replace(apps, schema_editor):
    """
    Reverse: Replace 'dispute' back to 'closed'
    """
    DisputeStatus = apps.get_model('dropdown_master_data', 'DisputeStatus')
    DisputeLog = apps.get_model('operations', 'DisputeLog')

    print("\n  REVERSING: Restoring 'closed' status")

    # Reactivate 'closed' status if it exists
    closed_status = DisputeStatus.objects.filter(code='closed').first()
    if closed_status:
        closed_status.is_active = True
        closed_status.save()
        print("  ✓ Reactivated 'closed' status")
    else:
        # Recreate 'closed' status
        DisputeStatus.objects.create(
            code='closed',
            label='Closed',
            is_active=True,
            display_order=40,
            created_at=None,
            updated_at=None,
            updated_by=None,
        )
        print("  ✓ Recreated 'closed' status")

    # Update any records back from 'dispute' to 'closed'
    dispute_status = DisputeStatus.objects.filter(code='dispute').first()
    if dispute_status:
        closed_status = DisputeStatus.objects.get(code='closed')
        updated_count = DisputeLog.objects.filter(status=dispute_status).update(status=closed_status)
        if updated_count > 0:
            print(f"  ✓ Updated {updated_count} dispute record(s) back to 'closed'")

        # Deactivate 'dispute' status
        dispute_status.is_active = False
        dispute_status.save()
        print("  ✓ Deactivated 'dispute' status")

    print("  Reverse migration complete\n")


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0011_add_missing_storage_units'),
        ('operations', '0049_alter_disputelog_comment_and_more'),  # Ensure DisputeLog exists
    ]

    operations = [
        migrations.RunPython(
            replace_closed_with_dispute,
            reverse_code=reverse_replace
        ),
    ]
