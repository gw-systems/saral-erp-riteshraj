from django.db import migrations


def normalize_display_names(apps, schema_editor):
    Courier = apps.get_model("courier", "Courier")

    Courier.objects.filter(display_name="Bluedart 500 gms").update(display_name="Blue Dart")
    Courier.objects.filter(display_name="ShadowFax").update(display_name="Shadowfax")
    Courier.objects.filter(display_name="Shadowfax Special").update(display_name="Shadowfax")


class Migration(migrations.Migration):

    dependencies = [
        ("courier", "0038_add_courier_code"),
    ]

    operations = [
        migrations.RunPython(normalize_display_names, migrations.RunPython.noop),
    ]
