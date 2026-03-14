from django.db import migrations


def seed_regions_and_states(apps, schema_editor):
    """Seed Region and StateCode with Indian states"""
    Region = apps.get_model('dropdown_master_data', 'Region')
    StateCode = apps.get_model('dropdown_master_data', 'StateCode')

    # Seed Regions
    regions = [
        {'code': 'north', 'label': 'North', 'display_order': 1, 'is_active': True},
        {'code': 'south', 'label': 'South', 'display_order': 2, 'is_active': True},
        {'code': 'east', 'label': 'East', 'display_order': 3, 'is_active': True},
        {'code': 'west', 'label': 'West', 'display_order': 4, 'is_active': True},
        {'code': 'central', 'label': 'Central', 'display_order': 5, 'is_active': True},
    ]
    for r in regions:
        Region.objects.get_or_create(code=r['code'], defaults=r)

    # Seed Indian StateCode
    states = [
        ('AP', 'Andhra Pradesh', 1),
        ('AR', 'Arunachal Pradesh', 2),
        ('AS', 'Assam', 3),
        ('BR', 'Bihar', 4),
        ('CG', 'Chhattisgarh', 5),
        ('GA', 'Goa', 6),
        ('GJ', 'Gujarat', 7),
        ('HR', 'Haryana', 8),
        ('HP', 'Himachal Pradesh', 9),
        ('JH', 'Jharkhand', 10),
        ('KA', 'Karnataka', 11),
        ('KL', 'Kerala', 12),
        ('MP', 'Madhya Pradesh', 13),
        ('MH', 'Maharashtra', 14),
        ('MN', 'Manipur', 15),
        ('ML', 'Meghalaya', 16),
        ('MZ', 'Mizoram', 17),
        ('NL', 'Nagaland', 18),
        ('OD', 'Odisha', 19),
        ('PB', 'Punjab', 20),
        ('RJ', 'Rajasthan', 21),
        ('SK', 'Sikkim', 22),
        ('TN', 'Tamil Nadu', 23),
        ('TS', 'Telangana', 24),
        ('TR', 'Tripura', 25),
        ('UP', 'Uttar Pradesh', 26),
        ('UK', 'Uttarakhand', 27),
        ('WB', 'West Bengal', 28),
        # Union Territories
        ('AN', 'Andaman and Nicobar Islands', 29),
        ('CH', 'Chandigarh', 30),
        ('DN', 'Dadra and Nagar Haveli and Daman and Diu', 31),
        ('DL', 'Delhi', 32),
        ('JK', 'Jammu and Kashmir', 33),
        ('LA', 'Ladakh', 34),
        ('LD', 'Lakshadweep', 35),
        ('PY', 'Puducherry', 36),
    ]
    for code, name, order in states:
        StateCode.objects.get_or_create(
            state_code=code,
            defaults={'state_name': name, 'display_order': order, 'is_active': True}
        )


def reverse_seed(apps, schema_editor):
    Region = apps.get_model('dropdown_master_data', 'Region')
    StateCode = apps.get_model('dropdown_master_data', 'StateCode')
    Region.objects.filter(code__in=['north', 'south', 'east', 'west', 'central']).delete()
    StateCode.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dropdown_master_data', '0015_seed_warehouse_dropdowns'),
    ]

    operations = [
        migrations.RunPython(seed_regions_and_states, reverse_seed),
    ]
