from django.db import migrations


def add_missing_cities(apps, schema_editor):
    """Add cities missing from the master CityCode table."""
    CityCode = apps.get_model('supply', 'CityCode')

    cities = [
        # (city_code, city_name, state_code)
        ('NHS', 'Nhava Sheva', 'MH'),   # Port area near Navi Mumbai, Maharashtra
        ('DWK', 'Dwarka', 'DL'),         # Dwarka, Delhi
        ('ALR', 'Alipur', 'DL'),         # Alipur, Delhi
    ]

    for city_code, city_name, state_code in cities:
        CityCode.objects.get_or_create(
            city_code=city_code,
            defaults={
                'city_name': city_name,
                'state_code': state_code,
                'is_active': True,
            }
        )


def remove_missing_cities(apps, schema_editor):
    CityCode = apps.get_model('supply', 'CityCode')
    CityCode.objects.filter(city_code__in=['NHS', 'DWK', 'ALR']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('supply', '0007_seed_city_codes'),
    ]

    operations = [
        migrations.RunPython(add_missing_cities, remove_missing_cities),
    ]
