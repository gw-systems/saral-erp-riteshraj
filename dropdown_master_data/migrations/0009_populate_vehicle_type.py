from django.db import migrations


def populate_vehicle_type(apps, schema_editor):
    """
    Populate VehicleType dropdown with common logistics vehicles.
    Used by MonthlyBilling transport fields for client and vendor billing.
    """
    VehicleType = apps.get_model('dropdown_master_data', 'VehicleType')

    vehicles = [
        ('bike', 'Bike', 10),
        ('3_wheeler', '3 Wheeler', 15),
        ('pick_up', 'Pick Up', 20),
        ('tata_ace', 'Tata Ace', 25),
        ('porter', 'Porter', 30),
        ('max_2mp', 'Max 2MP', 35),
        ('tata_407', 'Tata 407', 40),
        ('14_ft', '14 FT Truck', 50),
        ('17_ft', '17 FT Truck', 55),
        ('20_ft', '20 FT Truck', 60),
        ('32_ft', '32 FT Truck', 65),
        ('tata_709', 'Tata 709', 70),
        ('tata_909', 'Tata 909', 75),
        ('ftl_1109', 'FTL 1109', 80),
        ('local_transport', 'Local Transport', 90),
        ('other', 'Other', 100),
    ]

    for code, label, display_order in vehicles:
        VehicleType.objects.get_or_create(
            code=code,
            defaults={
                'label': label,
                'is_active': True,
                'display_order': display_order,
            },
        )

    print(f"Populated {len(vehicles)} VehicleType values")


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0008_populate_approval_action'),
    ]

    operations = [
        migrations.RunPython(
            populate_vehicle_type,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
