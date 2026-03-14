# Generated manually on 2026-01-19
# Data migration to add required adhoc billing statuses

from django.db import migrations


def add_required_adhoc_billing_statuses(apps, schema_editor):
    """
    Add adhoc billing status values that are referenced in operations data.
    
    This must run before operations migrations that enforce foreign key constraints.
    """
    AdhocBillingStatus = apps.get_model('dropdown_master_data', 'AdhocBillingStatus')
    
    # Define all statuses found in operations_adhocbillingentry table
    # Order: (code, label, display_order)
    required_statuses = [
        ('pending', 'Pending', 10),
        ('billed', 'Billed', 20),
        ('cancelled', 'Cancelled', 30),
    ]
    
    created_count = 0
    existing_count = 0
    
    for code, label, display_order in required_statuses:
        obj, created = AdhocBillingStatus.objects.get_or_create(
            code=code,
            defaults={
                'label': label,
                'is_active': True,
                'display_order': display_order,
                'created_at': None,
                'updated_at': None,
                'updated_by': None,
            }
        )
        if created:
            created_count += 1
            print(f"  ✓ Created adhoc billing status: '{code}' ({label})")
        else:
            existing_count += 1
            print(f"  → Adhoc billing status already exists: '{code}'")
    
    print(f"  Summary: {created_count} created, {existing_count} already existed")


def reverse_migration(apps, schema_editor):
    """
    Reverse migration - we cannot safely delete these statuses as 
    operations_adhocbillingentry data depends on them.
    """
    print("  Note: Cannot reverse - data depends on these status values")
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0002_delete_citycode'),
    ]

    operations = [
        migrations.RunPython(
            add_required_adhoc_billing_statuses,
            reverse_code=reverse_migration
        ),
    ]