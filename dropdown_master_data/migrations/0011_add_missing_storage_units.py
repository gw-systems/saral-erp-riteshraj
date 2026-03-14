# Generated migration to add missing StorageUnit values

from django.db import migrations


def populate_missing_storage_units(apps, schema_editor):
    """
    Add missing StorageUnit values that are used in daily space utilization:
    - unit: For counting individual units
    - order: For tracking by order
    - lumpsum: For flat-rate billing (already exists from migration 0006, but ensure it's there)
    """
    StorageUnit = apps.get_model('dropdown_master_data', 'StorageUnit')

    # Add missing units
    units = [
        ('unit', 'Unit', 60),
        ('order', 'Order', 70),
    ]

    for code, label, display_order in units:
        StorageUnit.objects.get_or_create(
            code=code,
            defaults={
                'label': label,
                'is_active': True,
                'display_order': display_order
            }
        )

    print(f"✅ Added missing StorageUnit values: unit, order")


def reverse_missing_storage_units(apps, schema_editor):
    """Remove the added storage units"""
    StorageUnit = apps.get_model('dropdown_master_data', 'StorageUnit')

    StorageUnit.objects.filter(code__in=['unit', 'order']).delete()
    print("✅ Removed StorageUnit values: unit, order")


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0010_populate_handling_unit'),
    ]

    operations = [
        migrations.RunPython(
            populate_missing_storage_units,
            reverse_missing_storage_units
        ),
    ]
