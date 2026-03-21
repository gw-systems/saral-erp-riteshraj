from django.db import migrations


def populate_handling_unit(apps, schema_editor):
    """
    Populate HandlingUnit dropdown with common warehouse handling units.
    Used by MonthlyBilling for inbound/outbound handling quantity tracking.
    """
    HandlingUnit = apps.get_model('dropdown_master_data', 'HandlingUnit')

    units = [
        ('boxes', 'Boxes', 10),
        ('cartons', 'Cartons', 15),
        ('pieces', 'Pieces', 20),
        ('units', 'Units', 25),
        ('pallets', 'Pallets', 30),
        ('kgs', 'Kilograms (KG)', 40),
        ('tonnes', 'Tonnes', 50),
        ('mt', 'Metric Tonnes (MT)', 55),
        ('cbm', 'Cubic Meters (CBM)', 60),
        ('orders', 'Orders', 70),
        ('shipments', 'Shipments', 75),
        ('other', 'Other', 100),
    ]

    for code, label, display_order in units:
        HandlingUnit.objects.get_or_create(
            code=code,
            defaults={
                'label': label,
                'is_active': True,
                'display_order': display_order,
            },
        )

    print(f"Populated {len(units)} HandlingUnit values")


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0009_populate_vehicle_type'),
    ]

    operations = [
        migrations.RunPython(
            populate_handling_unit,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
